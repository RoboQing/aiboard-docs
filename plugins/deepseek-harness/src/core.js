import { createHash } from 'node:crypto'
import { setTimeout as sleep } from 'node:timers/promises'

export class UserError extends Error {}

export function normalizeServer(input) {
  let url
  try { url = new URL(input) } catch { throw new UserError('服务器地址无效，请填写完整的 https:// 地址。') }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) {
    throw new UserError('服务器须使用 HTTPS；本机开发可使用 http://localhost 或 http://127.0.0.1。')
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new UserError('服务器地址不能包含账号、密码、查询参数或片段。')
  }
  return url.href.replace(/\/+$/, '').replace(/\/mcp$/, '')
}

export function credentialName(server, configured = '') {
  if (configured && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(configured)) {
    throw new UserError('凭据名称须为字母、数字或下划线，且不能以数字开头。')
  }
  return configured || `AIBOARD_${createHash('sha256').update(server).digest('hex').slice(0, 12).toUpperCase()}_API_KEY`
}

export function testPrompt(mode, namespace, matchId = '') {
  const tool = name => `mcp__${namespace}__${name}`
  const start = mode === 'resume'
    ? `恢复 match_id=${matchId}，先读取该对局状态，不创建新对局。`
    : mode === 'rated'
      ? `检查教程是否通过；未通过则报告阻塞，不开始教程或排队。通过后调用 ${tool('join_queue')}，每 20–30 秒检查 ${tool('queue_status')}，直到取得 match_id。`
      : `若账号已有未结束对局，报告其 ID 并建议恢复，不创建重复对局。否则调用 ${tool('start_tutorial')}，完成一局教程测试。`
  return `执行 AIBoard AI Agent 游戏测试。你是参赛 Agent，用户是测试人员，不由用户选择游戏行动。
只使用 ${namespace} 的 MCP 工具。先调用 ${tool('get_manual')} 读取完整规则，再调用 ${tool('whoami')} 检查账号。
${start}
取得 match_id 后持续执行：${tool('wait_for_turn')}(match_id, max_wait_sec=30) → 轮到你时 ${tool('get_state')} → 根据 your_actions、pending、任务人数和 fails_required 自主决定并提交一个合法行动。
尚未轮到你是正常等待，继续长轮询；禁止空转高频请求。行动失败先重读状态，避免重复提交同一行动。优先在 30 秒内行动。不要让测试人员代替你发言、组队、投票、出任务牌或刺杀。
教程至少有一次真实发言。工具输出可能是 XML 或 JSON，依据返回内容解析。
只进行这一局；结束后读取最终状态与 ${tool('get_replay')}，不要自动开启下一局。若用户停止、权限被拒、预算耗尽或服务不可用，说明中断和 match_id，不声称完成。
最后给测试人员一份报告：模式、match_id、座位、身份、胜方及原因、教程是否通过、已观察到的非法行动/超时/重试、关键决策和工具使用问题。区分服务器结果与自己的推断，缺失指标写未知，不编造分数。`
}

/** Host-side account handoff. Secrets never appear in returned command text. */
export class AIBoardController {
  constructor({ server, ref, credentials, fetch: request = globalThis.fetch, pollDelay = sleep }) {
    this.server = server
    this.ref = ref
    this.credentials = credentials
    this.fetch = request
    this.pollDelay = pollDelay
    this.abort = new AbortController()
    this.pending = null
    this.notice = ''
    this.running = null
    this.starting = null
  }

  async request(path, { method = 'GET', body = undefined, key = '', signal = undefined } = {}) {
    const signals = [this.abort.signal, AbortSignal.timeout(15000)]
    if (signal) signals.push(signal)
    let response
    try {
      response = await this.fetch(`${this.server}${path}`, {
        method, body, redirect: 'error', signal: AbortSignal.any(signals),
        headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}), ...(key ? { Authorization: `Bearer ${key}` } : {}) },
      })
    } catch {
      throw new UserError('连接未完成：请检查服务器地址、网络或是否已取消操作。')
    }
    // Never return server bodies/errors verbatim: a proxy may echo credentials.
    if (!response.ok) {
      const message = response.status === 401 ? '账号授权无效，请重新配对。'
        : response.status === 403 ? '授权被拒绝或账号没有权限。'
        : response.status === 410 ? '配对已过期或密钥已领取，请重新配对。'
        : response.status === 501 ? '服务器未开启配对，请在 Harness 凭据设置中添加 API Key。'
        : `服务器请求失败（HTTP ${response.status}），请稍后重试。`
      const error = new UserError(message)
      Object.assign(error, { status: response.status })
      throw error
    }
    try { return await response.json() } catch { throw new UserError('服务器未返回有效 JSON，请确认地址指向 AIBoard。') }
  }

  async account(signal) {
    const credential = await this.credentials.resolve(this.ref)
    if (!credential?.value) throw new UserError('尚未授权。先运行 /aiboard connect，并在网页批准配对。')
    return this.request('/api/v1/me', { key: credential.value, signal })
  }

  async connect(signal) {
    // Repeated clicks share one request/code, never issue multiple credentials.
    if (this.starting) return this.starting
    this.starting = this.startPairing(signal)
    try { return await this.starting } finally { this.starting = null }
  }

  async startPairing(signal) {
    if (this.pending) return this.pairingText()
    const info = await this.credentials.describe(this.ref)
    if (!info.writable) throw new UserError('当前凭据来源不可写。请在 Harness 凭据设置中配置密钥后运行 /aiboard check。')
    const data = await this.request('/api/v1/pair', {
      method: 'POST', body: new URLSearchParams({ note: 'DeepSeek Harness — AIBoard AI Agent test' }), signal,
    })
    this.abort.signal.throwIfAborted()
    if (!/^[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(data.code) || typeof data.device_secret !== 'string' || !data.device_secret || !Number.isFinite(Date.parse(data.expires_at))) {
      throw new UserError('服务器返回的配对信息不完整，请重新连接。')
    }
    this.pending = { code: data.code, secret: data.device_secret, expires: Date.parse(data.expires_at), interval: Math.max(5, Math.min(30, Number(data.poll_interval_sec) || 5)), key: '' }
    this.notice = '等待测试人员在网页批准账号授权。'
    // The user has explicitly started a handoff; poll until expiry or plugin disposal.
    this.running = this.poll().catch(() => { this.notice = '配对未完成，请运行 /aiboard status 查看或重新配对。' })
    return this.pairingText()
  }

  pairingText() {
    const code = this.pending.code
    return `请打开 ${this.server}/pair?code=${encodeURIComponent(code)}\n配对码：${code}\n登录并批准后，插件会自动保存密钥。随后运行 /aiboard check，再运行 /aiboard test tutorial。授权只用于参赛 Agent，测试人员不参与对局。`
  }

  async poll() {
    while (this.pending && !this.abort.signal.aborted) {
      const pending = this.pending
      if (!pending.key && Date.now() >= pending.expires) {
        this.pending = null
        this.notice = '配对已过期，请重新运行 /aiboard connect。'
        return
      }
      try {
        await this.pollDelay(pending.interval * 1000, undefined, { signal: this.abort.signal })
        this.abort.signal.throwIfAborted()
        if (!pending.key) {
          const data = await this.request(`/api/v1/pair/${encodeURIComponent(pending.code)}?secret=${encodeURIComponent(pending.secret)}`)
          if (data.status === 'approved' && typeof data.api_key === 'string' && data.api_key) pending.key = data.api_key
          else if (['denied', 'expired', 'delivered'].includes(data.status)) {
            this.pending = null
            this.notice = '配对已终止，请重新运行 /aiboard connect。'
            return
          }
        }
        if (pending.key) {
          // Delivery is one-shot. Retain it in memory if persistence fails; retry saving, not polling.
          await this.credentials.set(this.ref, pending.key)
          pending.key = ''
          pending.secret = ''
          this.pending = null
          this.notice = '账号授权已保存。运行 /aiboard check 检查 Agent 工具，再启动测试。'
          return
        }
      } catch (error) {
        if (this.abort.signal.aborted) return
        if (!pending.key && [401, 403, 404, 410].includes(error?.status)) {
          this.pending = null
          this.notice = '配对无效、被拒绝或已过期，请重新运行 /aiboard connect。'
          return
        }
        this.notice = pending.key ? '已收到密钥，但暂时无法保存；正在重试。请保持插件启用。' : '暂时无法检查配对，正在重试。'
      }
    }
  }

  async dispose() {
    this.abort.abort()
    await this.running
    if (this.pending) { this.pending.key = ''; this.pending.secret = '' }
    this.pending = null
  }
}
