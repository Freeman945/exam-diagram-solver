import { spawn } from 'node:child_process'
import path from 'node:path'

import { ensureDir } from './paths.js'

/**
 * Bridge to the Python engine.
 *
 * Protocol: one JSON document on stdin, one JSON document on stdout. The Node
 * side owns no scientific logic, so every numeric or symbolic answer comes from
 * a process whose output can be reproduced outside the plugin.
 */

const MAX_OUTPUT_BYTES = 16 * 1024 * 1024
const PROBE_TIMEOUT_MS = 30_000

export class EngineError extends Error {
  constructor(message, { code = 'engine_error', details = null } = {}) {
    super(message)
    this.name = 'EngineError'
    this.code = code
    this.details = details
  }
}

function pythonCandidates(config) {
  const candidates = []
  const add = (value, source) => {
    if (value && !candidates.some((item) => item.path === value)) candidates.push({ path: value, source })
  }
  if (config.pythonPath) add(config.pythonPath, 'config')
  add(process.env.EXAM_SOLVER_PYTHON, 'env:EXAM_SOLVER_PYTHON')
  const venv = path.join(config.pluginRoot, '.venv')
  add(path.join(venv, 'Scripts', 'python.exe'), 'project venv')
  add(path.join(venv, 'bin', 'python'), 'project venv')
  add(process.env.DSH_PYTHON, 'env:DSH_PYTHON')
  add('python', 'PATH')
  add('python3', 'PATH')
  add('py', 'PATH')
  return candidates
}

function probePython(executable, { cwd, env }) {
  return new Promise((resolve) => {
    let settled = false
    const finish = (result) => {
      if (settled) return
      settled = true
      resolve(result)
    }
    let child
    try {
      child = spawn(executable, ['-c', 'import sys, sympy; print(sys.version.split()[0]); print(sympy.__version__)'], {
        cwd,
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch (error) {
      finish({ ok: false, error: error.message })
      return
    }
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf8')
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf8').slice(-2000)
    })
    child.on('error', (error) => finish({ ok: false, error: error.message }))
    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        // ignore
      }
      finish({ ok: false, error: 'probe timed out' })
    }, PROBE_TIMEOUT_MS)
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code === 0) {
        const [pythonVersion, sympyVersion] = stdout.trim().split(/\r?\n/)
        finish({ ok: true, pythonVersion, sympyVersion })
      } else {
        finish({ ok: false, error: (stderr || `exit code ${code}`).trim() })
      }
    })
  })
}

export function createEngine(config, logger) {
  const pythonDir = path.join(config.pluginRoot, 'python')
  const env = {
    ...process.env,
    PYTHONPATH: pythonDir,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    PYTHONUNBUFFERED: '1',
  }
  let resolved = null

  async function resolvePython() {
    if (resolved) return resolved
    const failures = []
    for (const candidate of pythonCandidates(config)) {
      const result = await probePython(candidate.path, { cwd: config.pluginRoot, env })
      if (result.ok) {
        resolved = { ...candidate, ...result }
        logger.info(`python engine ready: ${candidate.path} (python ${result.pythonVersion}, sympy ${result.sympyVersion})`)
        return resolved
      }
      failures.push({ path: candidate.path, source: candidate.source, error: result.error })
      if (candidate.source === 'config') break
    }
    const detail = failures.map((item) => `- ${item.path} (${item.source}): ${item.error}`).join('\n')
    throw new EngineError(
      `No Python interpreter with SymPy was found. Install it with:\n` +
        `  python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt\n` +
        `or set the plugin's pythonPath / EXAM_SOLVER_PYTHON.\nTried:\n${detail}`,
      { code: 'PYTHON_NOT_FOUND', details: failures },
    )
  }

  async function runRaw(request, { timeoutMs = 120_000, signal } = {}) {
    const python = await resolvePython()
    return new Promise((resolve, reject) => {
      let child
      try {
        child = spawn(python.path, ['-m', 'exam_solver'], {
          cwd: config.pluginRoot,
          env,
          windowsHide: true,
          stdio: ['pipe', 'pipe', 'pipe'],
        })
      } catch (error) {
        reject(new EngineError(`cannot start Python: ${error.message}`, { code: 'PYTHON_SPAWN_FAILED' }))
        return
      }

      let stdout = ''
      let stderr = ''
      let settled = false
      let timer = null

      const cleanup = () => {
        if (timer) clearTimeout(timer)
        if (signal) signal.removeEventListener('abort', onAbort)
      }
      const fail = (error) => {
        if (settled) return
        settled = true
        cleanup()
        reject(error)
      }
      const succeed = (value) => {
        if (settled) return
        settled = true
        cleanup()
        resolve(value)
      }
      const onAbort = () => {
        try {
          child.kill()
        } catch {
          // ignore
        }
        fail(new EngineError('cancelled', { code: 'ABORTED' }))
      }
      if (signal) {
        if (signal.aborted) {
          onAbort()
          return
        }
        signal.addEventListener('abort', onAbort, { once: true })
      }

      timer = setTimeout(() => {
        try {
          child.kill()
        } catch {
          // ignore
        }
        fail(new EngineError(`engine call timed out after ${Math.round(timeoutMs / 1000)}s`, { code: 'ENGINE_TIMEOUT' }))
      }, timeoutMs)

      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString('utf8')
        if (stdout.length > MAX_OUTPUT_BYTES) {
          try {
            child.kill()
          } catch {
            // ignore
          }
          fail(new EngineError('engine produced too much output', { code: 'ENGINE_OUTPUT_TOO_LARGE' }))
        }
      })
      child.stderr.on('data', (chunk) => {
        stderr = (stderr + chunk.toString('utf8')).slice(-8000)
      })
      child.on('error', (error) => fail(new EngineError(`engine process error: ${error.message}`, { code: 'ENGINE_SPAWN_FAILED' })))
      child.on('close', (code) => {
        if (settled) return
        const trimmed = stdout.trim()
        if (!trimmed) {
          fail(
            new EngineError(
              `engine exited with code ${code} and produced no output${stderr ? `:\n${stderr}` : ''}`,
              { code: 'ENGINE_CRASH', details: stderr },
            ),
          )
          return
        }
        let parsed
        try {
          parsed = JSON.parse(trimmed)
        } catch (error) {
          fail(
            new EngineError(`engine returned invalid JSON: ${error.message}`, {
              code: 'ENGINE_BAD_JSON',
              details: { stdout: trimmed.slice(0, 2000), stderr },
            }),
          )
          return
        }
        succeed(parsed)
      })

      try {
        child.stdin.write(JSON.stringify(request))
        child.stdin.end()
      } catch (error) {
        fail(new EngineError(`cannot write to engine: ${error.message}`, { code: 'ENGINE_WRITE_FAILED' }))
      }
    })
  }

  /**
   * Run one engine operation and return its data payload.
   * Throws EngineError with the engine's own error code on failure.
   */
  async function run(op, payload = {}, options = {}) {
    const response = await runRaw({ op, payload }, options)
    if (!response || response.ok !== true) {
      const error = response?.error ?? {}
      throw new EngineError(error.message || `engine operation ${op} failed`, {
        code: error.code || 'ENGINE_OPERATION_FAILED',
        details: error.details ?? null,
      })
    }
    return response.data
  }

  /** Run several operations in one process; returns an array of results. */
  async function runBatch(operations, options = {}) {
    const response = await runRaw({ ops: operations }, options)
    if (!response || !Array.isArray(response.results)) {
      throw new EngineError('engine returned an unexpected batch response', { code: 'ENGINE_BAD_BATCH' })
    }
    return response.results.map((entry) => {
      if (!entry.ok) {
        const error = entry.error ?? {}
        return { ok: false, op: entry.op, code: error.code, message: error.message, details: error.details }
      }
      return { ok: true, op: entry.op, data: entry.data }
    })
  }

  async function status() {
    const data = await run('status', {})
    const python = await resolvePython()
    return { ...data, resolvedPython: { path: python.path, source: python.source } }
  }

  function runDir(runId) {
    const dir = path.join(config.runDir, runId)
    ensureDir(dir)
    return dir
  }

  return { resolvePython, run, runBatch, status, runDir, describe: () => resolved }
}

export function isEngineError(error) {
  return error instanceof EngineError
}
