#!/usr/bin/env node
/**
 * Offline smoke test: load the plugin with a stub Cordis context and exercise
 * the Python bridge without installing anything into the Harness profile.
 *
 *   node scripts/smoke-engine.mjs
 */
import assert from 'node:assert/strict'

import { createPlugin } from '../lib/plugin.js'

const registered = []
const ctx = {
  get: () => undefined,
  effect: (factory) => factory(),
  tools: {
    register: (tool) => {
      registered.push(tool)
      return () => {}
    },
  },
}

const plugin = createPlugin(ctx, { quality: 'fast' })
for (const tool of plugin.tools) ctx.tools.register(tool)
const names = registered.map((tool) => tool.name).sort()
console.log(`registered ${names.length} tools: ${names.join(', ')}`)

const expected = [
  'exam_analyze_image',
  'exam_create_diagram_spec',
  'exam_decide_diagram',
  'exam_engine_status',
  'exam_grade_answer',
  'exam_reconstruct_diagram',
  'exam_render_answer',
  'exam_render_diagram',
  'exam_solve_problem',
  'exam_validate_diagram',
  'exam_validate_solution',
  'solve_exam_image',
]
for (const name of expected) assert.ok(names.includes(name), `missing tool ${name}`)
assert.equal(names.length, expected.length)

const statusTool = registered.find((tool) => tool.name === 'exam_engine_status')
const status = await statusTool.execute({}, { signal: new AbortController().signal })
console.log('engine status:', JSON.stringify(status.engine, null, 2))
assert.equal(status.engine.ok, undefined)
assert.ok(status.engine.features.sympy, 'SymPy must be available')
assert.ok(status.engine.resolvedPython.path, 'a Python path must be resolved')

const analyzeTool = registered.find((tool) => tool.name === 'exam_analyze_image')
const schema = analyzeTool.parameters
assert.ok(schema.properties.imagePaths)

plugin.dispose()
console.log('\nSMOKE OK')
