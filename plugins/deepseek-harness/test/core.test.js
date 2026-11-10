import test from 'node:test'
import assert from 'node:assert/strict'
import { AIBoardController, normalizeServer, credentialName, testPrompt } from '../src/core.js'

const reply = (body, status = 200) => new Response(JSON.stringify(body), { status })
const pairing = { code: 'ABCD-EFGH', device_secret: 'device-secret-test', expires_at: new Date(Date.now() + 600000).toISOString(), poll_interval_sec: 5 }
const tick = () => new Promise(resolve => setImmediate(resolve))
async function until(predicate) {
  for (let i = 0; i < 100; i++) { if (predicate()) return; await tick() }
  throw new Error('condition did not settle')
}
function credentials() {
  const values = new Map()
  return { values, describe: async ref => ({ configured: values.has(ref), writable: true }), resolve: async ref => values.has(ref) ? { value: values.get(ref) } : undefined, set: async (ref, value) => { values.set(ref, value) } }
}
function make(fetch, extra = {}) {
  return new AIBoardController({ server: 'https://board.test', ref: 'BOARD_KEY', credentials: credentials(), fetch, pollDelay: tick, ...extra })
}

test('normalizes MCP addresses and keeps credentials specific to a server', () => {
  assert.equal(normalizeServer('https://board.test/mcp/'), 'https://board.test')
  assert.equal(normalizeServer('http://127.0.0.1:8080'), 'http://127.0.0.1:8080')
  assert.notEqual(credentialName('https://one.test'), credentialName('https://two.test'))
  assert.equal(credentialName('https://one.test', 'CUSTOM_KEY'), 'CUSTOM_KEY')
  for (const value of ['http://board.test', 'https://user:key@board.test', 'https://board.test/?token=key', 'file:///tmp/board']) assert.throws(() => normalizeServer(value))
  assert.throws(() => credentialName('https://board.test', '${BAD}'))
})

test('pairing hides secrets, reuses concurrent requests, and saves approved key', async () => {
  let starts = 0
  const controller = make(async (url, options) => {
    assert.equal(options.redirect, 'error')
    if (options.method === 'POST') { starts++; await tick(); return reply(pairing, 201) }
    assert.match(url, /secret=device-secret-test/)
    return reply({ status: 'approved', api_key: 'aib_live_test_key' })
  })
  const outputs = await Promise.all([controller.connect(), controller.connect()])
  assert.equal(starts, 1)
  assert.equal(outputs[0], outputs[1])
  assert.ok(!outputs[0].includes(pairing.device_secret))
  await until(() => controller.credentials.values.has('BOARD_KEY'))
  assert.equal(controller.credentials.values.get('BOARD_KEY'), 'aib_live_test_key')
  assert.equal(controller.pending, null)
  assert.ok(!controller.notice.includes('aib_live'))
  await controller.dispose()
})

test('a one-shot delivered key is retained on save failure without polling twice', async () => {
  let polls = 0
  let saves = 0
  const store = credentials()
  const save = store.set
  store.set = async (...args) => { if (++saves === 1) throw new Error('disk unavailable'); return save(...args) }
  const controller = make(async (_url, options) => options.method === 'POST' ? reply(pairing) : (polls++, reply({ status: 'approved', api_key: 'aib_live_saved' })), { credentials: store })
  await controller.connect()
  await until(() => store.values.has('BOARD_KEY'))
  assert.equal(polls, 1)
  assert.equal(saves, 2)
  await controller.dispose()
})

test('denied pairings stop and can be restarted', async () => {
  let starts = 0
  const controller = make(async (_url, options) => options.method === 'POST' ? (starts++, reply(pairing)) : reply({ error: 'denied' }, 403))
  await controller.connect()
  await until(() => controller.pending === null)
  assert.match(controller.notice, /拒绝/)
  await controller.connect()
  assert.equal(starts, 2)
  await controller.dispose()
})

test('disposal cancels pending polling and clears device secrets', async () => {
  let polls = 0
  const controller = make(async () => { polls++; return reply(pairing) }, {
    pollDelay: (_ms, _value, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })),
  })
  await controller.connect()
  const pending = controller.pending
  await controller.dispose()
  assert.equal(polls, 1)
  assert.equal(pending.secret, '')
  assert.equal(controller.pending, null)
})

test('HTTP failures never echo credentials or response bodies', async () => {
  const controller = make(async () => reply({ error: 'Bearer SECRET' }, 401))
  await assert.rejects(controller.request('/api/v1/me', { key: 'SECRET' }), error => !error.message.includes('SECRET') && /授权无效/.test(error.message))
  await controller.dispose()
})

test('tutorial/rated/resume prompts delegate decisions to the tested Agent', () => {
  for (const mode of ['tutorial', 'rated', 'resume']) {
    const prompt = testPrompt(mode, 'testboard', 'match-123')
    assert.match(prompt, /mcp__testboard__wait_for_turn/)
    assert.match(prompt, /自主决定/)
    assert.match(prompt, /只进行这一局/)
    assert.match(prompt, /缺失指标写未知/)
    if (mode === 'resume') assert.match(prompt, /match_id=match-123/)
    if (mode === 'rated') assert.match(prompt, /未通过则报告阻塞/)
  }
})
