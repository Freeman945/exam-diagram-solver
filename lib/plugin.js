import { PLUGIN_NAME, PLUGIN_VERSION, describeConfig, loadConfig } from './config.js'
import { createImageResolver } from './images.js'
import { createLlmClient } from './llm.js'
import { createLogger } from './logger.js'
import { createPipeline } from './pipeline.js'
import { createEngine } from './python.js'
import { createArtifactStore } from './state.js'
import { createTools } from './tools.js'

/**
 * Compose the plugin: configuration, logging, the Python bridge, the internal
 * LLM client, shared artifacts, the pipeline and the tool surface.
 */
export function createPlugin(ctx, rawConfig = {}) {
  const config = loadConfig(rawConfig ?? {})
  const logger = createLogger({
    prefix: PLUGIN_NAME,
    level: 'info',
    logDir: config.logDir,
    logProblemText: config.logProblemText,
  })

  const engine = createEngine(config, logger)
  const llm = createLlmClient({ ctx, config, logger })
  const store = createArtifactStore()
  const images = createImageResolver({ ctx, config, logger })
  const pipeline = createPipeline({ ctx, config, engine, llm, logger, store })
  const tools = createTools({ ctx, config, engine, llm, pipeline, store, images, logger })

  logger.info(`loaded ${PLUGIN_NAME}@${PLUGIN_VERSION}`, {
    config: describeConfig(config),
    tools: tools.map((tool) => tool.name),
  })

  return {
    name: PLUGIN_NAME,
    version: PLUGIN_VERSION,
    config,
    configSummary: describeConfig(config),
    engine,
    llm,
    pipeline,
    store,
    images,
    tools,
    dispose() {
      logger.flush()
    },
  }
}
