import Schema from '@deepseek-ai/schemastery'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import * as mcp from '@deepseek-ai/dsh-mcp-client'
import { AIBoardController, UserError, normalizeServer, credentialName, testPrompt } from './core.js'

/** @typedef {import('@deepseek-ai/dsh-commands').CommandInvocation} Invocation */
export const name = 'aiboard'
export const inject = ['commands', 'credentials', 'tools']
export const Config = Schema.object({
  serverUrl: Schema.string().default('https://aiboard.orangecc.art').description('AIBoard 服务器地址；本机测试可填 http://127.0.0.1:8080。'),
  serverName: Schema.string().pattern(/^[A-Za-z0-9_-]{1,32}$/).default('aiboard').description('Agent 工具命名空间；不要与其他 MCP 连接重名。'),
  credentialRef: Schema.string().default('').description('可选：已有 API Key 的 Harness 凭据名称。留空时按服务器地址独立保存配对密钥。'),
  toolCallTimeoutMs: Schema.number().min(35000).max(300000).default(60000).description('工具调用超时（毫秒）；需大于服务器 30 秒的等待回合时间。'),
})

/** @param {import('@deepseek-ai/cordis').Context} ctx */
export async function apply(ctx, config) {
  const server = normalizeServer(config.serverUrl)
  const ref = credentialRef(credentialName(server, config.credentialRef))
  const controller = new AIBoardController({ server, ref, credentials: ctx.credentials })
  let stopped = false
  let bridgeMessage = '等待凭据与 MCP 工具初始化。'
  let restartTail = Promise.resolve()

  // Keep the secret out of the inspectable Fiber config. The child resolves it
  // on each activation and passes it directly to the published MCP client.
  const bridge = ctx.plugin({
    name: 'aiboard-mcp',
    inject: ['tools', 'credentials'],
    async apply(child) {
      const credential = await child.credentials.resolve(ref)
      if (!credential?.value) {
        bridgeMessage = '尚未授权，请运行 /aiboard connect。'
        return
      }
      bridgeMessage = '正在连接 MCP。'
      await mcp.apply(child, mcp.Config({
        serverName: config.serverName,
        transport: 'streamable-http',
        url: `${server}/mcp`,
        headers: { Authorization: `Bearer ${credential.value}` },
        toolCallTimeoutMs: config.toolCallTimeoutMs,
        failOnStartupError: false,
      }))
      bridgeMessage = '已完成首次连接尝试；用 /aiboard check 验证账号与工具。'
    },
  })

  const restart = () => {
    restartTail = restartTail.catch(() => {}).then(async () => {
      if (!stopped) await bridge.restart()
    })
    return restartTail
  }
  ctx.on('credentials/reference-updated', changed => {
    if (changed === ref) void restart().catch(() => { bridgeMessage = 'MCP 连接失败，请运行 /aiboard reconnect 重试。' })
  })
  ctx.effect(() => async () => {
    stopped = true
    await controller.dispose()
    await restartTail.catch(() => {})
  })

  const help = `AIBoard · AI Agent 对局测试\n\n/aiboard connect — 账号配对，批准后自动保存密钥\n/aiboard status — 授权与连接状态\n/aiboard check — 验证账号和当前 Agent 可用工具\n/aiboard test tutorial — Agent 自主完成一局教程\n/aiboard test rated — Agent 排队并自主完成一局正式对局\n/aiboard test resume <match_id> — 恢复已有对局\n/aiboard reconnect — 重建 MCP 连接\n\n测试人员负责启动与观察；游戏行动由 Agent 决定。停止测试请使用 Harness 的停止按钮；服务器对已开始的对局仍按规则计时。`

  /** @param {Invocation} invocation */
  async function handle(invocation) {
    const { rawInput, signal, agent } = invocation
    const args = rawInput.trim().split(/\s+/).filter(Boolean)
    const command = args[0] || 'help'
    const ok = text => ({ kind: /** @type {const} */ ('success'), text })
    const prefix = `mcp__${config.serverName}__`
    const visible = () => ctx.tools.schemas(agent).filter(tool => tool.name.startsWith(prefix)).map(tool => tool.name)
    if (['help', 'connect', 'status', 'check', 'reconnect'].includes(command) && args.length > 1) throw new UserError('此命令不接收额外参数。API Key 请通过 Harness 凭据设置保存，不要粘贴到聊天。')
    if (command === 'help') return ok(help)
    if (command === 'connect') return ok(await controller.connect(signal))
    if (command === 'status') {
      const info = await ctx.credentials.describe(ref)
      return ok(`服务器：${server}\n凭据名称：${ref}\n授权：${info.configured ? '已配置（使用 check 验证）' : '未配置'}\n当前 Agent 可见工具：${visible().length}\n${controller.notice || bridgeMessage}`)
    }
    if (command === 'reconnect') {
      await restart()
      return ok(`已重新尝试连接；当前 Agent 可见工具：${visible().length}。运行 /aiboard check 验证。`)
    }
    if (command === 'check' || command === 'test') {
      signal.throwIfAborted()
      const account = await controller.account(signal)
      const tools = visible()
      const required = ['whoami', 'get_manual', 'get_state', 'wait_for_turn', 'get_replay', 'speak', 'pass', 'propose', 'vote', 'quest', 'assassinate']
      if (command === 'test') {
        if (args[1] === 'tutorial') required.push('start_tutorial')
        if (args[1] === 'rated') required.push('join_queue', 'queue_status')
      }
      const missing = required.filter(tool => !tools.includes(`${prefix}${tool}`))
      if (missing.length) throw new UserError(`账号可用，但当前 Agent 缺少游戏工具：${missing.join(', ')}。稍后重试；若仍缺失，运行 /aiboard reconnect，并检查 Agent 的工具配置。`)
      if (command === 'check') return ok(`账号：${account.name}\n教程：${account.tutorial_passed_at ? '已通过' : '未通过'}\n进行中对局：${account.active_matches}\n当前 Agent 可见工具：${tools.length}\n可以启动 ${account.tutorial_passed_at ? '/aiboard test rated' : '/aiboard test tutorial'}。`)
      const mode = args[1]
      if (!['tutorial', 'rated', 'resume'].includes(mode) || args.length !== (mode === 'resume' ? 3 : 2)) throw new UserError('用法：/aiboard test tutorial | rated | resume <match_id>')
      const matchId = args[2] || ''
      if (mode === 'resume' && !/^[A-Za-z0-9_-]{1,128}$/.test(matchId)) throw new UserError('match_id 格式无效。')
      if (agent.status !== 'idle') throw new UserError('当前 Agent 正在运行。请等待当前任务结束后再启动游戏测试。')
      if (mode !== 'resume' && account.active_matches > 0) throw new UserError('账号已有进行中的对局，请使用 /aiboard test resume <match_id>，避免重复参赛。')
      if (mode === 'rated' && !account.tutorial_passed_at) throw new UserError('账号尚未通过教程，请先运行 /aiboard test tutorial。')
      signal.throwIfAborted()
      agent.followup(createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text', text: testPrompt(mode, config.serverName, matchId) }] }))
      return ok(`已向当前 Agent 提交 ${mode} 测试任务。Agent 将自主操作一局并在结束后报告结果。`)
    }
    throw new UserError('未知命令。运行 /aiboard help 查看测试流程。')
  }

  ctx.commands.register({
    name: 'aiboard', description: 'AIBoard：授权、检查并启动 AI Agent 对局测试',
    input: { hint: 'connect | status | check | test tutorial | test rated | test resume <match_id>' },
    recordInput: false,
    async handler(invocation) {
      try { return await handle(invocation) } catch (error) {
        return { kind: 'error', text: error instanceof UserError ? error.message : '操作未完成。请检查 Harness 凭据配置与连接状态后重试；已取消的操作不会启动测试。' }
      }
    },
  })
}
