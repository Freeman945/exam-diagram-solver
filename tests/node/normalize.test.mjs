import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeAnswerSpec, normalizeDiagramSpec, normalizeProblemSpec } from '../../lib/normalize.js'

test('problem spec aliases are mapped onto the schema vocabulary', () => {
  const spec = normalizeProblemSpec({
    subject: 'Physics',
    grade_level: 'junior',
    problem_type: 'motion',
    question_format: 'mcq',
    raw_text: '某物体做匀加速直线运动',
    questions: ['求加速度'],
    equations: ['v = u + a*t'],
    visual_objects: [{ id: 'm1', kind: 'box', label: 'm' }],
    visual_relations: [{ type: 'parallel_to', objects: ['AB', 'CD'] }, { type: 'lies_on', objects: ['D', 'BC'] }],
    recognition_confidence: 1.4,
    requires_diagram: true,
  })
  assert.equal(spec.subject, 'physics')
  assert.equal(spec.grade_level, 'middle_school')
  assert.equal(spec.problem_type, 'kinematics')
  assert.equal(spec.question_format, 'multiple_choice')
  assert.equal(spec.visual_objects[0].kind, 'unknown')
  assert.equal(spec.visual_relations[0].type, 'parallel')
  assert.equal(spec.visual_relations[1].type, 'point_on_segment')
  assert.equal(spec.recognition_confidence, 1)
  assert.equal(spec.requires_diagram, null)
  assert.equal(spec.equations[0].text, 'v = u + a*t')
})

test('geometry diagram shorthand is expanded', () => {
  const spec = normalizeDiagramSpec({
    type: 'plane_geometry',
    points: { A: [0, 0], B: { x: 4, y: 0 }, C: [2, 3] },
    segments: ['AB', 'BC', ['C', 'A']],
    marks: [{ type: 'equal', segments: [['A', 'B'], ['A', 'C']] }, { type: 'rightangle', at: 'B', arms: ['A', 'C'] }],
    circles: [{ center: 'A', through: 'B' }],
  })
  assert.equal(spec.type, 'geometry')
  assert.deepEqual(spec.points.B, [4, 0])
  assert.deepEqual(spec.segments, [['A', 'B'], ['B', 'C'], ['C', 'A']])
  assert.equal(spec.marks[0].type, 'equal_length')
  assert.equal(spec.marks[1].type, 'right_angle')
  assert.equal(spec.circles[0].through, 'B')
})

test('circuit component aliases are mapped', () => {
  const spec = normalizeDiagramSpec({
    type: 'circuit_diagram',
    components: [
      { kind: 'voltage_source', from: 'A', to: 'B', value: '6V' },
      { kind: 'bulb', from: 'B', to: 'C' },
      { kind: 'variable_resistor', from: 'C', to: 'A' },
    ],
  })
  assert.equal(spec.type, 'circuit')
  assert.deepEqual(
    spec.components.map((item) => item.kind),
    ['battery', 'lamp', 'rheostat'],
  )
})

test('force diagram angles are kept numeric', () => {
  const spec = normalizeDiagramSpec({
    type: 'free_body',
    object: { shape: 'block', label: 'm' },
    forces: [
      { label: 'mg', angle: '270', magnitude: '20' },
      { label: 'N', angle_deg: 90, magnitude: 20 },
    ],
  })
  assert.equal(spec.type, 'force')
  assert.equal(spec.forces[0].angle_deg, 270)
  assert.equal(spec.forces[0].magnitude, 20)
})

test('answer spec is normalised and defaults are applied', () => {
  const answer = normalizeAnswerSpec({
    steps: [{ content: 'x=2' }, { content: 'x=3', reason: '零因子', score_relevance: 'key' }],
    final_answer: 'x=2 或 x=3',
  })
  assert.equal(answer.steps.length, 2)
  assert.equal(answer.steps[0].score_relevance, 'normal')
  assert.equal(answer.steps[1].score_relevance, 'key')
  assert.equal(answer.confidence, 0.7)
})
