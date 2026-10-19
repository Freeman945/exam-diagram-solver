import assert from 'node:assert/strict'
import test from 'node:test'

import { renderFinalAnswer } from '../../lib/format.js'
import { mergeExamReports } from '../../lib/pipeline.js'

const problem = {
  subject: 'math',
  grade_level: 'high_school',
  problem_type: 'equation_solving',
  question_format: 'written_solution',
  raw_text: '解方程 x^2-5x+6=0',
  uncertainties: [{ issue: '常数项 6 的字迹略模糊', impact: '若为 8 则结果不同' }],
  recognition_confidence: 0.88,
}

const answer = {
  strategy: '因式分解',
  steps: [
    { step: 1, content: 'x^2-5x+6=(x-2)(x-3)', reason: '十字相乘', score_relevance: 'key' },
    { step: 2, content: '所以 x=2 或 x=3', reason: '零因子', score_relevance: 'key' },
  ],
  final_answer: '故 x=2 或 x=3。',
  notes: ['先移项再因式分解更安全。'],
  confidence: 0.95,
}

const validation = {
  passed: true,
  checks: [
    { name: 'equation_substitution', passed: true, severity: 'error', details: 'residual 0' },
    { name: 'answer:final_present', passed: true, severity: 'error', details: 'ok' },
  ],
  warnings: [],
}

const exam = {
  estimated_score: 11,
  max_score: 12,
  score_ratio: 0.92,
  lost_points: [{ reason: '未写出因式分解的依据', estimated_loss: 1 }],
  revision_required: false,
  source: 'internal_estimate',
}

test('final answer contains the required sections', () => {
  const { markdown } = renderFinalAnswer({
    problem,
    diagram: null,
    answer,
    validation,
    exam,
    answerMode: 'exam',
    language: 'zh',
    warnings: [],
    uncertainties: problem.uncertainties,
    status: 'ok',
  })
  assert.match(markdown, /题目类型/)
  assert.match(markdown, /解答/)
  assert.match(markdown, /最终答案/)
  assert.match(markdown, /识别提醒/)
  assert.match(markdown, /自检/)
  assert.match(markdown, /x=2 或 x=3/)
  assert.match(markdown, /常数项/)
})

test('teaching mode adds method and pitfalls but exam mode does not', () => {
  const teaching = renderFinalAnswer({
    problem,
    diagram: null,
    answer,
    validation,
    exam,
    answerMode: 'teaching',
    language: 'zh',
    warnings: [],
    uncertainties: [],
    status: 'ok',
  }).markdown
  assert.match(teaching, /方法总结/)
  assert.match(teaching, /易错点/)

  const examMode = renderFinalAnswer({
    problem,
    diagram: null,
    answer,
    validation,
    exam,
    answerMode: 'exam',
    language: 'zh',
    warnings: [],
    uncertainties: [],
    status: 'ok',
  }).markdown
  assert.doesNotMatch(examMode, /方法总结/)
})

test('English rendering uses English headings', () => {
  const { markdown } = renderFinalAnswer({
    problem,
    diagram: null,
    answer,
    validation,
    exam,
    answerMode: 'exam',
    language: 'en',
    warnings: [],
    uncertainties: [],
    status: 'ok',
  })
  assert.match(markdown, /Final answer/)
  assert.match(markdown, /Self-check/)
})

test('diagram files are listed when a diagram exists', () => {
  const { markdown } = renderFinalAnswer({
    problem,
    diagram: {
      required: true,
      role: 'final_answer',
      files: { svg: 'C:\\tmp\\diagram.svg', png: 'C:\\tmp\\diagram.png' },
      summary: '函数图象',
    },
    answer,
    validation,
    exam,
    answerMode: 'exam',
    language: 'zh',
    warnings: [],
    uncertainties: [],
    status: 'ok',
  })
  assert.match(markdown, /C:\/tmp\/diagram.svg/)
})

test('model examiner can only add concrete losses, never raise the score', () => {
  const merged = mergeExamReports(exam, {
    estimated_score: 12,
    max_score: 12,
    lost_points: [{ reason: '未说明自变量取值范围', estimated_loss: 0.5 }],
    strengths: ['步骤完整'],
    revision_required: true,
    revision_instructions: ['补写定义域'],
  })
  assert.equal(merged.max_score, 12)
  assert.equal(merged.estimated_score, 10.5)
  assert.equal(merged.revision_required, true)
  assert.ok(merged.lost_points.length >= 2)
  assert.ok(merged.strengths.includes('步骤完整'))
})

test('duplicate loss reasons are not double counted', () => {
  const merged = mergeExamReports(exam, {
    lost_points: [{ reason: '未写出因式分解的依据', estimated_loss: 2 }],
    revision_required: false,
  })
  assert.equal(merged.lost_points.length, exam.lost_points.length)
  assert.equal(merged.estimated_score, exam.estimated_score)
})
