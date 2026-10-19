import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { ensureDir } from './paths.js'

export const PLUGIN_NAME = 'exam-diagram-solver'
export const PLUGIN_VERSION = '0.1.0'

export const QUALITY_LEVELS = ['fast', 'balanced', 'high']
export const ANSWER_MODES = ['concise', 'exam', 'teaching']
export const LANGUAGES = ['zh', 'en']

/**
 * Documented JSON Schema for the Loader row's `config`.
 *
 * The Harness validates a `Config` export as a Standard Schema, which would
 * require a runtime dependency this plugin deliberately avoids. Instead the
 * same contract is enforced by {@link loadConfig}, which clamps numbers,
 * validates enums and warns about unknown keys.
 */
export const CONFIG_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    pythonPath: {
      type: 'string',
      description:
        'Absolute path to a Python 3.10+ interpreter with SymPy installed. Auto-detected when omitted.',
    },
    outputDir: {
      type: 'string',
      description:
        'Directory for generated diagrams and run records. Defaults to a temporary directory.',
    },
    quality: {
      type: 'string',
      enum: QUALITY_LEVELS,
      description: 'Pipeline depth: fast (no examiner), balanced (default), high (examiner + revisions).',
    },
    answerMode: {
      type: 'string',
      enum: ANSWER_MODES,
      description: 'Default answer style: concise, exam (default) or teaching.',
    },
    language: {
      type: 'string',
      enum: LANGUAGES,
      description: 'Output language for the final answer (default zh).',
    },
    maxRevisionRounds: {
      type: 'number',
      minimum: 0,
      maximum: 5,
      description: 'How many correction rounds the pipeline may run (default 2).',
    },
    maxDiagramRepairRounds: {
      type: 'number',
      minimum: 0,
      maximum: 5,
      description: 'How many times an invalid DiagramSpec may be repaired (default 2).',
    },
    provider: {
      type: 'string',
      description: 'Override the LLM provider for internal calls (defaults to the agent default).',
    },
    model: {
      type: 'string',
      description: 'Override the LLM model for internal calls (defaults to the agent default).',
    },
    reasoningEffort: {
      type: 'string',
      description: 'Override the reasoning effort for internal calls.',
    },
    diagramWidth: {
      type: 'number',
      minimum: 320,
      maximum: 2000,
      description: 'Rendered diagram width in pixels (default 760).',
    },
    diagramHeight: {
      type: 'number',
      minimum: 240,
      maximum: 2000,
      description: 'Rendered diagram height in pixels (default 560).',
    },
    dpi: {
      type: 'number',
      minimum: 72,
      maximum: 400,
      description: 'PNG preview resolution (default 140).',
    },
    timeoutSec: {
      type: 'number',
      minimum: 30,
      maximum: 3600,
      description: 'Timeout for one end-to-end solve (default 900).',
    },
    logProblemText: {
      type: 'boolean',
      description: 'Include transcribed problem text in local logs. Off by default for privacy.',
    },
  },
}

function numberOr(value, fallback, { min = -Infinity, max = Infinity } = {}) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.min(max, Math.max(min, number))
}

/**
 * Normalise raw plugin config into the fully resolved runtime config.
 * Never throws for a missing optional field; invalid values fall back.
 */
export function loadConfig(raw = {}) {
  const known = new Set(Object.keys(CONFIG_SCHEMA.properties ?? {}))
  const unknown = Object.keys(raw ?? {}).filter((key) => !known.has(key))
  if (unknown.length) {
    console.warn(`[exam-diagram-solver] ignoring unknown config keys: ${unknown.join(', ')}`)
  }
  const outputDir = path.resolve(
    raw.outputDir || process.env.EXAM_SOLVER_OUTPUT_DIR || path.join(os.tmpdir(), PLUGIN_NAME),
  )
  const runDir = path.join(outputDir, 'runs')
  const logDir = path.join(outputDir, 'logs')
  for (const dir of [outputDir, runDir, logDir]) ensureDir(dir)

  const moduleDir = path.dirname(fileURLToPath(import.meta.url))
  return {
    pluginRoot: path.resolve(moduleDir, '..'),
    outputDir,
    runDir,
    logDir,
    pythonPath: raw.pythonPath ? path.resolve(raw.pythonPath) : null,
    quality: QUALITY_LEVELS.includes(raw.quality) ? raw.quality : 'balanced',
    answerMode: ANSWER_MODES.includes(raw.answerMode) ? raw.answerMode : 'exam',
    language: LANGUAGES.includes(raw.language) ? raw.language : 'zh',
    maxRevisionRounds: Math.round(numberOr(raw.maxRevisionRounds, 2, { min: 0, max: 5 })),
    maxDiagramRepairRounds: Math.round(numberOr(raw.maxDiagramRepairRounds, 2, { min: 0, max: 5 })),
    provider: raw.provider || null,
    model: raw.model || null,
    reasoningEffort: raw.reasoningEffort || null,
    diagramWidth: Math.round(numberOr(raw.diagramWidth, 760, { min: 320, max: 2000 })),
    diagramHeight: Math.round(numberOr(raw.diagramHeight, 560, { min: 240, max: 2000 })),
    dpi: Math.round(numberOr(raw.dpi, 140, { min: 72, max: 400 })),
    timeoutSec: numberOr(raw.timeoutSec, 900, { min: 30, max: 3600 }),
    logProblemText: Boolean(raw.logProblemText),
  }
}

export function describeConfig(config) {
  return {
    plugin: PLUGIN_NAME,
    version: PLUGIN_VERSION,
    pythonPath: config.pythonPath ?? 'auto',
    outputDir: config.outputDir,
    quality: config.quality,
    answerMode: config.answerMode,
    language: config.language,
    maxRevisionRounds: config.maxRevisionRounds,
    maxDiagramRepairRounds: config.maxDiagramRepairRounds,
    model: config.model ?? 'agent default',
    timeoutSec: config.timeoutSec,
  }
}
