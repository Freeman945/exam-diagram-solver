/**
 * Final presentation.
 *
 * The user sees: what kind of problem this is, the figure (only when one is
 * genuinely needed), the exam-style solution, the final answer, and honest
 * recognition warnings. Internal JSON, stage timings and prompts stay out of
 * this rendering.
 */

const LABELS = {
  zh: {
    type: '题目类型',
    diagram: '图示',
    solution: '解答',
    final: '最终答案',
    warnings: '识别提醒',
    check: '自检',
    method: '方法总结',
    pitfalls: '易错点',
    confidence: '识别置信度',
    verified: '程序校验通过',
    verifyFailed: '程序校验未通过',
    estimate: '内部估分',
    estimateNote: '仅为系统内部估计，不代表真实考试评分',
    steps: '步骤',
    answer: '答案',
    diagramFailed: '作图未成功',
    noUnit: '注意单位',
  },
  en: {
    type: 'Problem type',
    diagram: 'Diagram',
    solution: 'Solution',
    final: 'Final answer',
    warnings: 'Recognition notes',
    check: 'Self-check',
    method: 'Method',
    pitfalls: 'Common mistakes',
    confidence: 'Recognition confidence',
    verified: 'Programmatic checks passed',
    verifyFailed: 'Programmatic checks failed',
    estimate: 'Internal score estimate',
    estimateNote: 'Internal estimate only; not a real exam mark',
    steps: 'Step',
    answer: 'Answer',
    diagramFailed: 'Diagram generation failed',
    noUnit: 'Check units',
  },
}

const TYPE_LABELS = {
  equation_solving: '解方程',
  inequality: '不等式',
  function_analysis: '函数与图象',
  trigonometry: '三角函数',
  geometry_proof: '平面几何证明',
  geometry_computation: '平面几何计算',
  analytic_geometry: '解析几何',
  vector: '向量',
  solid_geometry: '立体几何',
  calculus: '导数与积分',
  probability_statistics: '概率统计',
  kinematics: '运动学',
  dynamics: '动力学',
  work_energy: '功与能',
  momentum: '动量',
  electrostatics: '静电场',
  circuit: '电路',
  magnetism: '磁场',
  electromagnetic_induction: '电磁感应',
  optics: '光学',
  waves: '机械波与振动',
  experiment: '实验题',
  other: '综合题',
}

const GRADE_LABELS = {
  primary: '小学',
  middle_school: '初中',
  high_school: '高中',
  university: '大学',
  unknown: '',
}

const SUBJECT_LABELS = { math: '数学', physics: '物理', unknown: '未判定' }

const MODE_LABELS = { concise: '精简', exam: '考试作答', teaching: '教学讲解' }

function escapeMarkdown(text) {
  return String(text ?? '').replace(/\r\n/g, '\n')
}

function percent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${Math.round(Math.max(0, Math.min(1, number)) * 100)}%`
}

/**
 * @returns {{markdown: string, finalAnswer: string, sections: string[]}}
 */
export function renderFinalAnswer({
  problem,
  diagram,
  answer,
  validation,
  exam,
  answerMode = 'exam',
  language = 'zh',
  warnings = [],
  uncertainties = [],
  status = 'ok',
}) {
  const t = LABELS[language] ?? LABELS.zh
  const lines = []
  const sections = []

  const typeLabel = TYPE_LABELS[problem?.problem_type] ?? problem?.problem_type ?? '—'
  const gradeLabel = GRADE_LABELS[problem?.grade_level] ?? ''
  const subjectLabel = SUBJECT_LABELS[problem?.subject] ?? ''
  const confidence = Number(problem?.recognition_confidence ?? answer?.confidence ?? 0)
  lines.push(
    `**${t.type}**：${subjectLabel} · ${gradeLabel ? `${gradeLabel} · ` : ''}${typeLabel} · ${MODE_LABELS[answerMode] ?? answerMode}` +
      `　（${t.confidence} ${percent(confidence)}）`,
  )
  sections.push('type')

  if (diagram?.required && diagram?.files) {
    lines.push('')
    lines.push(`**${t.diagram}**：${diagram.role === 'final_answer' || diagram.role === 'both' ? '作答图' : '辅助图'}`)
    const svg = diagram.files.svg ? String(diagram.files.svg).replace(/\\/g, '/') : null
    const png = diagram.files.png ? String(diagram.files.png).replace(/\\/g, '/') : null
    if (svg) lines.push(`- SVG：\`${svg}\``)
    if (png) lines.push(`- PNG：\`${png}\``)
    if (diagram.summary) lines.push(`- ${diagram.summary}`)
    sections.push('diagram')
  } else if (diagram?.required && diagram?.error) {
    lines.push('')
    lines.push(`**${t.diagram}**：${t.diagramFailed}（${diagram.error}）`)
    sections.push('diagram')
  }

  lines.push('')
  lines.push(`**${t.solution}**`)
  const steps = Array.isArray(answer?.steps) ? answer.steps : []
  steps.forEach((step, index) => {
    const content = escapeMarkdown(step.content).trim()
    const reason = step.reason ? `（${escapeMarkdown(step.reason).trim()}）` : ''
    const marker = step.score_relevance === 'key' ? '**' : ''
    lines.push(`${marker}${index + 1}. ${content}${marker}${reason}`)
  })
  if (steps.length === 0) lines.push('_（未生成分步过程）_')
  sections.push('solution')

  lines.push('')
  lines.push(`**${t.final}**`)
  lines.push('')
  lines.push(`> ${escapeMarkdown(answer?.final_answer || '—').replace(/\n+/g, ' ')}`)
  sections.push('final')

  const notes = [...new Set([...(uncertainties ?? []).map(formatUncertainty), ...(warnings ?? [])].filter(Boolean))]
  if (notes.length) {
    lines.push('')
    lines.push(`**${t.warnings}**`)
    for (const note of notes.slice(0, 6)) lines.push(`- ${note}`)
    sections.push('warnings')
  }

  const checks = Array.isArray(validation?.checks) ? validation.checks : []
  const executed = checks.filter((check) => !check.skipped)
  const failed = executed.filter((check) => check.passed === false && check.severity === 'error')
  const verified = Boolean(validation?.passed) && failed.length === 0
  const scoreLine =
    exam && Number.isFinite(Number(exam.estimated_score))
      ? `${t.estimate} ${exam.estimated_score}/${exam.max_score}（${t.estimateNote}）`
      : null

  lines.push('')
  lines.push(`**${t.check}**`)
  lines.push(
    `- ${verified ? t.verified : t.verifyFailed}：${executed.length - failed.length}/${executed.length || 0} 项` +
      (failed.length ? `；未通过：${failed.slice(0, 3).map((check) => check.name).join('、')}` : ''),
  )
  if (scoreLine) lines.push(`- ${scoreLine}`)
  if (status !== 'ok') {
    lines.push(
      `- ${
        status === 'partial'
          ? '本次结果存在未解决的问题，建议核对后使用。'
          : '本次流程未能完成，请根据提示修正输入。'
      }`,
    )
  }
  sections.push('check')

  if (answerMode === 'teaching') {
    const notesList = Array.isArray(answer?.notes) ? answer.notes : []
    if (notesList.length) {
      lines.push('')
      lines.push(`**${t.method}**`)
      for (const note of notesList.slice(0, 6)) lines.push(`- ${escapeMarkdown(note)}`)
      sections.push('method')
    }
    const pitfalls = (exam?.lost_points ?? []).map((item) => item.reason).filter(Boolean)
    if (pitfalls.length) {
      lines.push('')
      lines.push(`**${t.pitfalls}**`)
      for (const pitfall of pitfalls.slice(0, 6)) lines.push(`- ${pitfall}`)
      sections.push('pitfalls')
    }
  }

  return {
    markdown: lines.join('\n').replace(/\n{3,}/g, '\n\n').trim(),
    finalAnswer: answer?.final_answer ?? '',
    sections,
  }
}

function formatUncertainty(item) {
  if (!item) return ''
  if (typeof item === 'string') return item
  const issue = String(item.issue ?? '').trim()
  if (!issue) return ''
  const impact = String(item.impact ?? '').trim()
  return impact ? `${issue}（影响：${impact}）` : issue
}
