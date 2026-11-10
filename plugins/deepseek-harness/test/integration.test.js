import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { once } from 'node:events'
import { setTimeout as sleep } from 'node:timers/promises'
import { harness } from './helpers.js'
import { credentialName } from '../src/core.js'
import { credentialRef } from '@deepseek-ai/dsh-credentials'

async function until(predicate) {
  for (let i = 0; i < 200; i++) { if (await predicate()) return; await sleep(25) }
  throw new Error('Timed out waiting for local AIBoard / MCP tools')
}

test('published Harness client connects to the real Go server and dispatches an Agent test', { skip: !process.env.AIBOARD_TEST_BINARY, timeout: 20000 }, async () => {
  const portServer = createServer().listen(0, '127.0.0.1')
  await once(portServer, 'listening')
  const port = portServer.address().port
  await new Promise(resolve => portServer.close(resolve))
  const server = `http://127.0.0.1:${port}`
  const child = spawn(process.env.AIBOARD_TEST_BINARY, ['-addr', `127.0.0.1:${port}`, '-dev-accounts', '1', '-mcp-format', 'json'], {
    cwd: new URL('../../../..', import.meta.url), stdio: ['ignore', 'ignore', 'pipe'],
    // Do not inherit deployment credentials or databases into a local test.
    env: { PATH: process.env.PATH, AIBOARD_DSN: '', AIBOARD_OIDC_CLIENT_ID: '' },
  })
  let logs = ''
  child.stderr.on('data', data => { logs += data.toString() })
  let fixture
  try {
    await until(async () => /aib_live_\S+/.test(logs) && await fetch(`${server}/healthz`).then(r => r.ok).catch(() => false))
    const key = logs.match(/aib_live_\S+/)[0]
    fixture = await harness({ serverUrl: server })
    const { ctx, fiber, credentials } = fixture
    assert.equal(ctx.tools.schemas().length, 0)
    await credentials.set(credentialRef(credentialName(server)), key)
    await until(() => ctx.tools.schemas().length === 23)
    const events = []
    const messages = []
    const agent = { status: 'idle', session: { append: (type, data) => { events.push({ type, data }) } }, followup: message => { messages.push(message); agent.status = 'running' } }
    const command = async line => (await ctx.commands.execute(agent, line, [], new AbortController().signal)).result
    const reconnect = await command('/aiboard reconnect')
    assert.equal(reconnect.kind, 'success', reconnect.text)
    assert.equal(ctx.tools.schemas().length, 23)
    assert.ok(!JSON.stringify(fiber.config).includes(key))
    const check = await command('/aiboard check')
    assert.equal(check.kind, 'success', check.text)
    assert.match(check.text, /dev-1/)
    assert.match(check.text, /23/)
    const rated = await command('/aiboard test rated')
    assert.equal(rated.kind, 'error')
    assert.equal(messages.length, 0)
    const result = await command('/aiboard test tutorial')
    assert.equal(result.kind, 'success', result.text)
    assert.equal(messages.length, 1)
    assert.match(messages[0].content[0].text, /自主决定/)
    assert.ok(!JSON.stringify(messages).includes(key))
    assert.equal((await command('/aiboard test tutorial')).kind, 'error')
    assert.equal(messages.length, 1)
    assert.ok(events.filter(e => e.type === 'command/run').every(e => !('args' in e.data)))
    assert.ok(!JSON.stringify(events).includes(key))
    // Invoke the registered MCP executors: this proves real transport/auth/schema compatibility.
    const execute = (name, args = {}) => ctx.tools.get(`mcp__aiboard__${name}`).execute(args, { signal: new AbortController().signal, agent })
    const me = await execute('whoami')
    assert.equal(JSON.parse(me.content[0].text).name, 'dev-1')
    const tutorial = await execute('start_tutorial')
    const started = JSON.parse(tutorial.content[0].text)
    assert.ok(started.id, JSON.stringify(started))
    const matchId = started.id
    const state = await execute('get_state', { match_id: matchId })
    assert.ok(state.content[0].text.length > 0)
    const pending = await execute('wait_for_turn', { match_id: matchId, max_wait_sec: 1 })
    assert.equal(JSON.parse(pending.content[0].text).your_turn, true)
    await execute('speak', { match_id: matchId, text: '测试发言：请根据任务结果和投票记录评估队伍。' })
    await fiber.dispose()
    assert.equal(ctx.tools.schemas().length, 0)
    assert.equal(ctx.commands.find(agent, 'aiboard'), undefined)
  } finally {
    if (fixture) await fixture.ctx.fiber.dispose()
    child.kill('SIGTERM')
    await once(child, 'exit').catch(() => {})
  }
})
