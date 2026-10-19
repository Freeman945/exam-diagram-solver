import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { decideDiagramRequirement } from '../../lib/decide.js'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const CASES = fs
  .readFileSync(path.join(ROOT, 'benchmark', 'cases.jsonl'), 'utf8')
  .split(/\r?\n/)
  .filter((line) => line.trim())
  .map((line) => JSON.parse(line))

function problemOf(entry) {
  return {
    subject: entry.subject,
    grade_level: entry.grade,
    problem_type: entry.problem_type,
    question_format: entry.question_format,
    raw_text: entry.text,
    visual_objects: entry.has_figure ? [{ id: 'A', kind: 'point' }] : [],
    visual_relations: [],
    uncertainties: [],
  }
}

test('benchmark file loads', () => {
  assert.ok(CASES.length >= 30)
})

for (const entry of CASES) {
  test(`${entry.id}: diagram decision matches the labelled expectation`, () => {
    const decision = decideDiagramRequirement(problemOf(entry))
    assert.equal(
      decision.required,
      entry.needs_diagram,
      `${entry.id}: expected required=${entry.needs_diagram}, got ${decision.required} (${decision.reason})`,
    )
    if (entry.needs_diagram) {
      assert.equal(decision.diagram_type, entry.diagram_type, `${entry.id}: diagram type`)
    }
  })
}
