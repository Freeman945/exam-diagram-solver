/**
 * Decide whether a diagram is needed - deterministically.
 *
 * The decision is rule based on purpose: it must be explainable in the final
 * report and reproducible in tests. The model does not get to invent a reason
 * to draw, and the plugin never draws just to show off.
 */

const DRAW_KEYWORDS = [
  '画出',
  '作出',
  '作图',
  '画图',
  '绘制',
  '画函数',
  '图像',
  '图象',
  '描点',
  '受力图',
  '受力分析图',
  '光路图',
  '电路图',
  '示意图',
]

const FORCE_KEYWORDS = ['受力分析', '受力图', '受力', '合力', '分解', '斜面', '摩擦力', '拉力', '支持力', '牛顿']

const DIAGRAM_TYPE_BY_PROBLEM = {
  equation_solving: 'none',
  inequality: 'none',
  function_analysis: 'function',
  trigonometry: 'coordinate',
  geometry_proof: 'geometry',
  geometry_computation: 'geometry',
  analytic_geometry: 'coordinate',
  vector: 'coordinate',
  solid_geometry: 'none',
  calculus: 'function',
  probability_statistics: 'chart',
  kinematics: 'coordinate',
  dynamics: 'force',
  work_energy: 'force',
  momentum: 'coordinate',
  electrostatics: 'force',
  circuit: 'circuit',
  magnetism: 'force',
  electromagnetic_induction: 'circuit',
  optics: 'optics',
  waves: 'coordinate',
  experiment: 'chart',
  other: 'none',
}

function textOf(problemSpec) {
  const parts = [problemSpec?.raw_text ?? '']
  for (const question of problemSpec?.questions ?? []) parts.push(question?.text ?? '')
  for (const condition of problemSpec?.conditions ?? []) parts.push(condition?.text ?? '')
  for (const option of problemSpec?.options ?? []) parts.push(option?.text ?? '')
  return parts.join('\n')
}

function asksToDraw(text) {
  return DRAW_KEYWORDS.some((keyword) => text.includes(keyword))
}

/**
 * @returns {{required: boolean, reason: string, role: 'auxiliary'|'final_answer'|'both'|'none', diagram_type: string, applied_rules: string[]}}
 */
export function decideDiagramRequirement(problemSpec, { hint = null } = {}) {
  const rules = []
  const text = textOf(problemSpec)
  const problemType = String(problemSpec?.problem_type ?? 'other')
  const subject = String(problemSpec?.subject ?? 'unknown')
  const format = String(problemSpec?.question_format ?? 'unknown')
  const hasVisual = (problemSpec?.visual_objects ?? []).length > 0 || (problemSpec?.visual_relations ?? []).length > 0
  const typeHint = problemSpec?.diagram_type_hint && problemSpec.diagram_type_hint !== 'none'
    ? String(problemSpec.diagram_type_hint)
    : DIAGRAM_TYPE_BY_PROBLEM[problemType] ?? 'none'

  if (hint === 'force') return finish(true, '调用方明确要求作图。', 'final_answer', typeHint, ['explicit_hint'])
  if (hint === 'none') return finish(false, '调用方明确要求不作图。', 'none', 'none', ['explicit_hint'])

  if (problemSpec?.requires_diagram === false) {
    return finish(false, '题目识别阶段判断不需要作图。', 'none', 'none', ['recognized_requires_diagram_false'])
  }

  if (asksToDraw(text)) {
    rules.push('question_asks_to_draw')
    const role = 'final_answer'
    return finish(
      true,
      '题目明确要求作图（出现“画出/作出/作图”等表述），图必须出现在答案中。',
      role,
      typeHint === 'none' ? inferTypeFromText(text) : typeHint,
      rules,
    )
  }

  if (problemType === 'solid_geometry') {
    return finish(
      false,
      '立体几何题的三维示意图难以从文本可靠重建，本版本不自动生成（避免画错）。',
      'none',
      'none',
      ['solid_geometry_deferred'],
    )
  }

  if (problemType === 'geometry_proof' || problemType === 'geometry_computation') {
    rules.push('geometry_problem')
    if (hasVisual) {
      rules.push('figure_already_given')
      return finish(
        true,
        '题目自带几何图；重绘一张用于校验点线关系与辅助线推理（辅助图，不作为作答必需）。',
        'auxiliary',
        'geometry',
        rules,
      )
    }
    return finish(
      true,
      '几何题没有现成图，需要按题意重建图形以支持推理与检查。',
      'auxiliary',
      'geometry',
      rules,
    )
  }

  if (problemType === 'function_analysis' || problemType === 'calculus') {
    rules.push('function_problem')
    return finish(
      true,
      '函数题需要图象来观察单调性、极值与交点，程序会先用 SymPy 求关键点再绘图。',
      'auxiliary',
      'function',
      rules,
    )
  }

  if (problemType === 'trigonometry' || problemType === 'analytic_geometry' || problemType === 'vector') {
    rules.push('coordinate_problem')
    return finish(true, '解析几何/三角/向量题用坐标系图辅助定位与检验。', 'auxiliary', 'coordinate', rules)
  }

  if (problemType === 'circuit' || problemType === 'electromagnetic_induction') {
    rules.push('circuit_problem')
    return finish(
      hasVisual,
      hasVisual ? '题目给出电路图，重建拓扑用于检查连接关系与电流方向。' : '电路题建议用电图核对拓扑。',
      'auxiliary',
      'circuit',
      rules,
    )
  }

  if (subject === 'physics' && FORCE_KEYWORDS.some((keyword) => text.includes(keyword))) {
    rules.push('physics_force_analysis')
    return finish(
      true,
      '物理题涉及受力分析，受力图是规范解答的一部分。',
      'both',
      'force',
      rules,
    )
  }

  if (problemType === 'optics') {
    rules.push('optics_problem')
    return finish(true, '光学题需要光路图核对法线、入射角与反射/折射方向。', 'both', 'optics', rules)
  }

  if (problemType === 'kinematics' || problemType === 'momentum' || problemType === 'waves') {
    rules.push('kinematics_problem')
    return finish(false, '运动学/动量/波动计算题通常不需要附加图，纯计算即可。', 'none', 'coordinate', rules)
  }

  if (problemType === 'probability_statistics' || problemType === 'experiment') {
    rules.push('data_problem')
    return finish(false, '数据题只有在题目给出作图要求时才需要图。', 'none', 'chart', rules)
  }

  if (format === 'multiple_choice' || format === 'fill_blank') {
    rules.push('objective_question')
    return finish(false, '客观题通常不需要作图。', 'none', 'none', rules)
  }

  rules.push('default_no_diagram')
  return finish(false, '没有足够理由生成图；强制作图会降低答案的规范性。', 'none', 'none', rules)
}

function inferTypeFromText(text) {
  if (text.includes('受力')) return 'force'
  if (text.includes('电路')) return 'circuit'
  if (text.includes('光路')) return 'optics'
  if (text.includes('函数') || text.includes('图象') || text.includes('图像')) return 'function'
  return 'geometry'
}

function finish(required, reason, role, diagramType, appliedRules) {
  return {
    required: Boolean(required),
    reason,
    role: required ? role : 'none',
    diagram_type: required ? diagramType : 'none',
    applied_rules: appliedRules,
  }
}
