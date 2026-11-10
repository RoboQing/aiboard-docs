import { Context } from '@deepseek-ai/cordis'
import { CommandRuntime } from '@deepseek-ai/dsh-commands'
import { ToolsService } from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import * as plugin from '../src/index.js'

export async function harness(config = {}, key = undefined) {
  const ctx = new Context()
  const values = new Map()
  const credentials = {
    describe: async ref => ({ configured: Boolean(key || values.get(ref)), writable: true }),
    resolve: async ref => (key || values.get(ref)) ? { value: key || values.get(ref), source: 'file' } : undefined,
    set: async (ref, value) => { values.set(ref, value); await ctx.parallel('credentials/reference-updated', ref) },
  }
  ctx.provide('credentials', credentials)
  await ctx.plugin(SystemPrompt, {}).await()
  await ctx.plugin(ToolsService).await()
  await ctx.plugin(CommandRuntime).await()
  const fiber = ctx.plugin(plugin, config)
  await fiber.await()
  return { ctx, fiber, credentials }
}

