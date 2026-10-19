import fs from 'node:fs'
import path from 'node:path'

import { timestampCompact } from './paths.js'

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 }

/**
 * Minimal structured logger.
 *
 * Two rules matter for a published plugin:
 *   1. the console stays quiet unless something is wrong,
 *   2. the on-disk run log never contains user images or (by default) the
 *      transcribed problem text.
 */
export function createLogger({ prefix = 'exam-diagram-solver', level = 'info', logDir = null, logProblemText = false } = {}) {
  const threshold = LEVELS[level] ?? LEVELS.info
  const filePath = logDir ? path.join(logDir, `${timestampCompact()}.jsonl`) : null
  const lines = []

  function write(levelName, message, data) {
    if ((LEVELS[levelName] ?? LEVELS.info) < threshold) return
    const record = { time: new Date().toISOString(), level: levelName, message }
    if (data !== undefined) record.data = redact(data, logProblemText)
    if (levelName === 'error') console.error(`[${prefix}] ${message}`, data ?? '')
    else if (levelName === 'warn') console.warn(`[${prefix}] ${message}`, data ?? '')
    else if (levelName === 'debug') console.log(`[${prefix}] ${message}`, data ?? '')
    if (filePath) lines.push(JSON.stringify(record))
  }

  function flush() {
    if (!filePath || lines.length === 0) return
    try {
      fs.appendFileSync(filePath, lines.join('\n') + '\n', 'utf8')
      lines.length = 0
    } catch {
      // Logging must never break a solve.
    }
  }

  return {
    debug: (message, data) => write('debug', message, data),
    info: (message, data) => write('info', message, data),
    warn: (message, data) => write('warn', message, data),
    error: (message, data) => write('error', message, data),
    stage: (name, data) => write('info', `stage:${name}`, data),
    flush,
    filePath,
  }
}

const TEXT_KEYS = new Set(['raw_text', 'problemText', 'rawText', 'prompt', 'content', 'final_answer'])

function redact(value, logProblemText, key = '') {
  if (!logProblemText && TEXT_KEYS.has(key) && typeof value === 'string') {
    return `[redacted ${value.length} chars]`
  }
  if (Array.isArray(value)) return value.map((item) => redact(item, logProblemText))
  if (value && typeof value === 'object') {
    const result = {}
    for (const [name, item] of Object.entries(value)) result[name] = redact(item, logProblemText, name)
    return result
  }
  return value
}
