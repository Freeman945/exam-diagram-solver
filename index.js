import { PLUGIN_NAME, PLUGIN_VERSION } from './lib/config.js'
import { createPlugin } from './lib/plugin.js'

export const name = PLUGIN_NAME
export const version = PLUGIN_VERSION
export const inject = ['tools']

/**
 * exam-diagram-solver - 拍题高分解答与自动作图助手.
 *
 * Registers tools that turn a photographed problem into a verified,
 * exam-style answer with a programmatically drawn diagram:
 *
 *   image -> multimodal ProblemSpec -> diagram decision -> DiagramSpec ->
 *   validation -> SVG/PNG -> solving -> SymPy/unit validation -> examiner ->
 *   revision -> final answer
 *
 * The plugin reads images only from paths given to a tool or from the latest
 * image the user attached to the current session. It never writes the source
 * image anywhere and keeps its own artifacts in a temporary directory.
 */
export function apply(ctx, config) {
  const plugin = createPlugin(ctx, config)

  for (const tool of plugin.tools) {
    ctx.effect(() => ctx.tools.register(tool))
  }

  ctx.effect(() => () => {
    plugin.dispose()
  })
}
