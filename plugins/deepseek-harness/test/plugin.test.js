import test from 'node:test'
import assert from 'node:assert/strict'
import * as plugin from '../src/index.js'
import { harness } from './helpers.js'

// The actual Cordis registries exercise dependency injection and effect cleanup.
// Only the agent model and credential persistence are replaced in these tests.
test('loads without credentials, registers help, and unloads its command', async () => {
  const { ctx, fiber } = await harness()
  try {
    assert.ok(ctx.commands.find({}, 'aiboard'))
    assert.equal(ctx.tools.schemas().length, 0)
  } finally { await fiber.dispose() }
  assert.equal(ctx.commands.find({}, 'aiboard'), undefined)
  await ctx.fiber.dispose()
})

test('configuration rejects short tool timeouts and invalid namespaces', () => {
  assert.throws(() => plugin.Config({ toolCallTimeoutMs: 1000 }))
  assert.throws(() => plugin.Config({ serverName: 'bad namespace' }))
  assert.equal(plugin.Config({}).serverUrl, 'https://aiboard.orangecc.art')
})
