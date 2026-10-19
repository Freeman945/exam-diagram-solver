import assert from 'node:assert/strict'
import test from 'node:test'

import { decideDiagramRequirement } from '../../lib/decide.js'

const base = {
  subject: 'math',
  grade_level: 'high_school',
  problem_type: 'equation_solving',
  question_format: 'written_solution',
  raw_text: '解方程 x^2-5x+6=0',
  conditions: [],
  questions: [{ text: '求 x', index: 1 }],
  options: [],
  symbols: [],
  equations: [],
  visual_objects: [],
  visual_relations: [],
  uncertainties: [],
  recognition_confidence: 0.95,
}

test('equation solving without a draw request needs no diagram', () => {
  const decision = decideDiagramRequirement(base)
  assert.equal(decision.required, false)
  assert.equal(decision.role, 'none')
  assert.equal(decision.diagram_type, 'none')
})

test('multiple choice is not forced to draw', () => {
  const decision = decideDiagramRequirement({
    ...base,
    problem_type: 'function_analysis',
    question_format: 'multiple_choice',
    raw_text: '函数 y=x^2-2x-3 的最小值是（ ）',
  })
  assert.equal(decision.required, true)
  assert.equal(decision.role, 'auxiliary')
  assert.equal(decision.diagram_type, 'function')
})

test('an explicit drawing request makes the figure part of the answer', () => {
  const decision = decideDiagramRequirement({
    ...base,
    problem_type: 'function_analysis',
    raw_text: '请画出函数 y=x^2-2x-3 的图象，并写出顶点坐标。',
  })
  assert.equal(decision.required, true)
  assert.equal(decision.role, 'final_answer')
  assert.ok(decision.applied_rules.includes('question_asks_to_draw'))
})

test('a geometry problem with a given figure produces an auxiliary rebuild', () => {
  const decision = decideDiagramRequirement({
    ...base,
    problem_type: 'geometry_proof',
    question_format: 'proof',
    raw_text: '如图，在△ABC中，AB=AC，D是BC的中点。求证：AD⊥BC。',
    visual_objects: [{ id: 'A', kind: 'point' }, { id: 'B', kind: 'point' }],
    visual_relations: [{ type: 'equal_length', objects: ['AB', 'AC'] }],
  })
  assert.equal(decision.required, true)
  assert.equal(decision.role, 'auxiliary')
  assert.equal(decision.diagram_type, 'geometry')
  assert.ok(decision.applied_rules.includes('figure_already_given'))
})

test('physics force analysis is drawn for the solution', () => {
  const decision = decideDiagramRequirement({
    ...base,
    subject: 'physics',
    problem_type: 'dynamics',
    raw_text: '质量 m=2kg 的物块在粗糙水平面上受到水平拉力 F=10N，求加速度。（g=10m/s²）',
  })
  assert.equal(decision.required, true)
  assert.equal(decision.role, 'both')
  assert.equal(decision.diagram_type, 'force')
})

test('kinematics calculation stays text-only', () => {
  const decision = decideDiagramRequirement({
    ...base,
    subject: 'physics',
    problem_type: 'kinematics',
    raw_text: '汽车以 2m/s² 匀加速行驶，初速度为 0，求 5s 后的速度。',
  })
  assert.equal(decision.required, false)
})

test('solid geometry is deferred instead of guessed', () => {
  const decision = decideDiagramRequirement({
    ...base,
    problem_type: 'solid_geometry',
    raw_text: '正方体 ABCD-A1B1C1D1 中，求异面直线 AB1 与 BC1 所成角。',
  })
  assert.equal(decision.required, false)
  assert.ok(decision.applied_rules.includes('solid_geometry_deferred'))
})

test('explicit hints override the rules', () => {
  assert.equal(decideDiagramRequirement(base, { hint: 'force' }).required, true)
  assert.equal(decideDiagramRequirement(base, { hint: 'none' }).required, false)
})

test('circuit problems keep the circuit diagram auxiliary', () => {
  const decision = decideDiagramRequirement({
    ...base,
    subject: 'physics',
    problem_type: 'circuit',
    raw_text: '如图所示的电路中，电源电动势为 6V，R1=2Ω，R2=4Ω，求电流。',
    visual_objects: [{ id: 'R1', kind: 'resistor' }],
  })
  assert.equal(decision.required, true)
  assert.equal(decision.diagram_type, 'circuit')
  assert.equal(decision.role, 'auxiliary')
})
