/**
 * Boundary normalisation for model output.
 *
 * The JSON Schemas stay strict; this layer fixes the predictable, harmless
 * deviations (aliases, a string where an object is expected, a segment written
 * "AB" instead of ["A","B"]) so a near-correct plan is not failed for style.
 * Anything it cannot fix is left for the strict validator to report.
 */

const SUBJECTS = new Set(['math', 'physics'])
const GRADES = new Set(['primary', 'middle_school', 'high_school', 'university', 'unknown'])
const TYPES = new Set([
  'equation_solving',
  'inequality',
  'function_analysis',
  'trigonometry',
  'geometry_proof',
  'geometry_computation',
  'analytic_geometry',
  'vector',
  'solid_geometry',
  'calculus',
  'probability_statistics',
  'kinematics',
  'dynamics',
  'work_energy',
  'momentum',
  'electrostatics',
  'circuit',
  'magnetism',
  'electromagnetic_induction',
  'optics',
  'waves',
  'experiment',
  'other',
])
const FORMATS = new Set(['multiple_choice', 'fill_blank', 'written_solution', 'proof', 'unknown'])

const VISUAL_KINDS = new Set([
  'point',
  'segment',
  'line',
  'ray',
  'circle',
  'arc',
  'angle',
  'triangle',
  'polygon',
  'vector',
  'axis',
  'object',
  'incline',
  'pulley',
  'string',
  'spring',
  'battery',
  'resistor',
  'ammeter',
  'voltmeter',
  'switch',
  'lamp',
  'capacitor',
  'inductor',
  'lens',
  'mirror',
  'ray_of_light',
  'unknown',
])

const RELATION_TYPES = new Set([
  'collinear',
  'perpendicular',
  'parallel',
  'equal_length',
  'point_on_segment',
  'point_on_circle',
  'concyclic',
  'right_angle',
  'angle_equals',
  'midpoint',
  'bisects',
  'tangent',
  'similar',
  'congruent',
  'force',
  'velocity',
  'current',
  'electric_field',
  'unknown',
])

const RELATION_ALIASES = {
  lies_on: 'point_on_segment',
  on_segment: 'point_on_segment',
  on_line: 'collinear',
  same_line: 'collinear',
  perpendicular_to: 'perpendicular',
  parallel_to: 'parallel',
  equal: 'equal_length',
  equidistant: 'equal_length',
  rightangle: 'right_angle',
  cyclic: 'concyclic',
  on_circle: 'point_on_circle',
  center: 'midpoint',
}

const TYPE_ALIASES = {
  algebra: 'equation_solving',
  equation: 'equation_solving',
  equations: 'equation_solving',
  solve_equation: 'equation_solving',
  inequality_solving: 'inequality',
  function: 'function_analysis',
  functions: 'function_analysis',
  graph: 'function_analysis',
  geometry: 'geometry_computation',
  plane_geometry: 'geometry_proof',
  geometry_calculation: 'geometry_computation',
  analytic: 'analytic_geometry',
  coordinate_geometry: 'analytic_geometry',
  vectors: 'vector',
  stereometry: 'solid_geometry',
  derivative: 'calculus',
  integral: 'calculus',
  statistics: 'probability_statistics',
  probability: 'probability_statistics',
  motion: 'kinematics',
  mechanics: 'dynamics',
  newton: 'dynamics',
  force: 'dynamics',
  energy: 'work_energy',
  electric: 'electrostatics',
  electric_field: 'electrostatics',
  electrical_circuit: 'circuit',
  circuits: 'circuit',
  magnetic: 'magnetism',
  induction: 'electromagnetic_induction',
  optical: 'optics',
  wave: 'waves',
  experimental: 'experiment',
}

const GRADE_ALIASES = {
  elementary: 'primary',
  primary_school: 'primary',
  小学: 'primary',
  junior: 'middle_school',
  junior_high: 'middle_school',
  middle: 'middle_school',
  middle_school: 'middle_school',
  junior_middle: 'middle_school',
  初中: 'middle_school',
  senior: 'high_school',
  senior_high: 'high_school',
  high: 'high_school',
  高中: 'high_school',
  college: 'university',
  undergraduate: 'university',
  大学: 'university',
}

const FORMAT_ALIASES = {
  mcq: 'multiple_choice',
  choice: 'multiple_choice',
  multiple_choice_question: 'multiple_choice',
  selection: 'multiple_choice',
  选择: 'multiple_choice',
  blank: 'fill_blank',
  fill: 'fill_blank',
  fill_in_the_blank: 'fill_blank',
  填空: 'fill_blank',
  solution: 'written_solution',
  free_response: 'written_solution',
  calculation: 'written_solution',
  written: 'written_solution',
  answer: 'written_solution',
  proof_question: 'proof',
  prove: 'proof',
  证明: 'proof',
}

const DIAGRAM_ALIASES = {
  plane_geometry: 'geometry',
  geometric: 'geometry',
  graph: 'function',
  plot: 'function',
  function_graph: 'function',
  coordinate_system: 'coordinate',
  free_body: 'force',
  free_body_diagram: 'force',
  force_analysis: 'force',
  circuit_diagram: 'circuit',
  electrical: 'circuit',
  light_ray: 'optics',
  ray_diagram: 'optics',
  data: 'chart',
}

const COMPONENT_ALIASES = {
  voltage_source: 'battery',
  source: 'battery',
  cell: 'battery',
  power_source: 'battery',
  bulb: 'lamp',
  light: 'lamp',
  meter_a: 'ammeter',
  meter_v: 'voltmeter',
  variable_resistor: 'rheostat',
  potentiometer: 'rheostat',
  coil: 'inductor',
  condensor: 'capacitor',
  condenser: 'capacitor',
}

const MARK_ALIASES = {
  right_angle_mark: 'right_angle',
  rightangle: 'right_angle',
  perpendicular_mark: 'right_angle',
  equal: 'equal_length',
  equal_segments: 'equal_length',
  parallel_mark: 'parallel',
  angle_mark: 'angle',
}

const SURFACE_ALIASES = {
  flat_mirror: 'mirror',
  plane_mirror: 'mirror',
  boundary: 'interface',
  convex_lens: 'lens',
  concave_lens: 'lens',
  projection_screen: 'screen',
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function asArray(value) {
  if (Array.isArray(value)) return value
  if (value === undefined || value === null) return []
  return [value]
}

function asString(value, fallback = '') {
  if (value === undefined || value === null) return fallback
  if (typeof value === 'string') return value
  return String(value)
}

function asNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function clamp(value, min, max, fallback) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.min(max, Math.max(min, number))
}

function normalizeSubject(value, problemType, subjectHint) {
  const text = asString(value).toLowerCase()
  if (SUBJECTS.has(text)) return text
  if (subjectHint === 'math' || subjectHint === 'physics') return subjectHint
  if (['math', 'algebra', 'geometry', 'calculus'].some((key) => text.includes(key))) return 'math'
  if (['physic', 'mechanic', 'electric', 'optic'].some((key) => text.includes(key))) return 'physics'
  const physicsTypes = new Set([
    'kinematics',
    'dynamics',
    'work_energy',
    'momentum',
    'electrostatics',
    'circuit',
    'magnetism',
    'electromagnetic_induction',
    'optics',
    'waves',
    'experiment',
  ])
  return physicsTypes.has(problemType) ? 'physics' : problemType === 'other' ? 'unknown' : 'math'
}

function normalizeType(value) {
  const text = asString(value).trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (TYPES.has(text)) return text
  if (TYPE_ALIASES[text]) return TYPE_ALIASES[text]
  for (const [alias, type] of Object.entries(TYPE_ALIASES)) {
    if (text.includes(alias)) return type
  }
  return 'other'
}

function normalizeGrade(value) {
  const text = asString(value).trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (GRADES.has(text)) return text
  return GRADE_ALIASES[text] ?? 'unknown'
}

function normalizeFormat(value) {
  const text = asString(value).trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (FORMATS.has(text)) return text
  return FORMAT_ALIASES[text] ?? 'unknown'
}

function normalizeDiagramHint(value) {
  if (!value) return null
  const text = asString(value).trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (['geometry', 'coordinate', 'function', 'force', 'circuit', 'optics', 'chart', 'none'].includes(text)) {
    return text
  }
  return DIAGRAM_ALIASES[text] ?? null
}

export function normalizeProblemSpec(raw, { subjectHint = 'auto', gradeHint = 'auto' } = {}) {
  const source = isObject(raw) ? raw : {}
  const problemType = normalizeType(source.problem_type)
  const spec = {
    subject: normalizeSubject(source.subject, problemType, subjectHint),
    grade_level:
      normalizeGrade(source.grade_level) !== 'unknown'
        ? normalizeGrade(source.grade_level)
        : normalizeGrade(gradeHint),
    problem_type: problemType,
    question_format: normalizeFormat(source.question_format),
    raw_text: asString(source.raw_text).trim(),
    conditions: asArray(source.conditions)
      .map((item) => ({
        text: asString(isObject(item) ? item.text : item).trim(),
        source: ['image', 'ocr', 'inferred'].includes(item?.source) ? item.source : 'image',
      }))
      .filter((item) => item.text),
    questions: asArray(source.questions)
      .map((item, index) => ({
        text: asString(isObject(item) ? item.text : item).trim(),
        index: Math.max(1, Math.round(asNumber(item?.index, index + 1))),
      }))
      .filter((item) => item.text),
    options: asArray(source.options)
      .map((item) => ({
        label: asString(item?.label ?? '').trim(),
        text: asString(item?.text ?? item).trim(),
      }))
      .filter((item) => item.label && item.text),
    symbols: asArray(source.symbols)
      .map((item) => ({
        name: asString(item?.name ?? item).trim(),
        meaning: asString(item?.meaning).trim() || undefined,
        unit: asString(item?.unit).trim() || undefined,
        value: asString(item?.value).trim() || undefined,
      }))
      .filter((item) => item.name),
    equations: asArray(source.equations)
      .map((item) => {
        if (typeof item === 'string') return { text: item.trim() }
        return {
          text: asString(item?.text ?? item?.latex).trim(),
          latex: asString(item?.latex).trim() || undefined,
          role: ['given', 'target', 'definition'].includes(item?.role) ? item.role : undefined,
          label: asString(item?.label).trim() || undefined,
        }
      })
      .filter((item) => item.text),
    visual_objects: asArray(source.visual_objects)
      .map((item) => {
        const kindText = asString(item?.kind).trim().toLowerCase()
        return {
          id: asString(item?.id ?? item?.label ?? '').trim(),
          kind: VISUAL_KINDS.has(kindText) ? kindText : 'unknown',
          label: asString(item?.label).trim() || undefined,
          attributes: isObject(item?.attributes) ? item.attributes : undefined,
        }
      })
      .filter((item) => item.id),
    visual_relations: asArray(source.visual_relations)
      .map((item) => {
        const rawType = asString(item?.type).trim().toLowerCase().replace(/[\s-]+/g, '_')
        const type = RELATION_TYPES.has(rawType) ? rawType : RELATION_ALIASES[rawType] ?? 'unknown'
        return {
          type,
          objects: asArray(item?.objects).map((name) => asString(name).trim()).filter(Boolean),
          value: typeof item?.value === 'number' ? item.value : asString(item?.value).trim() || undefined,
          confidence: Number.isFinite(Number(item?.confidence))
            ? clamp(item.confidence, 0, 1, 0.85)
            : 0.85,
        }
      })
      .filter((item) => item.type && item.objects.length > 0),
    requires_diagram: null,
    diagram_role: null,
    diagram_type_hint: normalizeDiagramHint(source.diagram_type_hint),
    uncertainties: asArray(source.uncertainties)
      .map((item) => ({
        issue: asString(isObject(item) ? item.issue : item).trim(),
        impact: asString(item?.impact).trim() || undefined,
        alternative: asString(item?.alternative).trim() || undefined,
      }))
      .filter((item) => item.issue),
    recognition_confidence: clamp(source.recognition_confidence, 0, 1, 0.7),
  }
  if (!spec.questions.length && spec.raw_text) spec.questions.push({ text: spec.raw_text, index: 1 })
  return spec
}

function normalizePairs(value) {
  return asArray(value)
    .map((item) => {
      if (Array.isArray(item) && item.length === 2) return [asString(item[0]), asString(item[1])]
      if (isObject(item) && item.from && item.to) return [asString(item.from), asString(item.to)]
      if (typeof item === 'string') {
        const compact = item.replace(/[\s,，-]/g, '')
        if (compact.length === 2) return [compact[0], compact[1]]
      }
      return null
    })
    .filter(Boolean)
}

function normalizePointValue(value) {
  if (Array.isArray(value) && value.length >= 2) return [asNumber(value[0]), asNumber(value[1])]
  if (isObject(value)) return [asNumber(value.x), asNumber(value.y)]
  return null
}

export function normalizeDiagramSpec(raw) {
  if (!isObject(raw)) return raw
  const typeText = asString(raw.type).trim().toLowerCase().replace(/[\s-]+/g, '_')
  const type = DIAGRAM_ALIASES[typeText] ?? typeText
  const base = { ...raw, type }
  delete base.notes

  if (type === 'geometry') {
    const points = {}
    for (const [name, value] of Object.entries(isObject(raw.points) ? raw.points : {})) {
      const point = normalizePointValue(value)
      if (point) points[asString(name)] = point
    }
    const segments = normalizePairs(raw.segments)
    const spec = {
      type: 'geometry',
      title: asString(raw.title).trim() || undefined,
      points,
      segments,
      auxiliary_segments: normalizePairs(raw.auxiliary_segments),
      rays: asArray(raw.rays)
        .map((item) => ({ from: asString(item?.from), to: asString(item?.to) }))
        .filter((item) => item.from && item.to),
      lines: normalizePairs(raw.lines),
      polygons: asArray(raw.polygons)
        .map((item) => ({
          points: asArray(item?.points ?? item).map((name) => asString(name)),
          fill: asString(item?.fill).trim() || undefined,
          style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
        }))
        .filter((item) => item.points.length >= 3),
      circles: asArray(raw.circles)
        .map((item) => ({
          center: asString(item?.center ?? item?.centre),
          radius: Number.isFinite(Number(item?.radius)) ? Number(item.radius) : undefined,
          through: asString(item?.through).trim() || undefined,
          label: asString(item?.label).trim() || undefined,
          style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
        }))
        .filter((item) => item.center && (item.radius || item.through)),
      arcs: asArray(raw.arcs)
        .map((item) => ({
          center: asString(item?.center),
          radius: asNumber(item?.radius),
          start_angle: asNumber(item?.start_angle),
          end_angle: asNumber(item?.end_angle),
          style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
        }))
        .filter((item) => item.center && item.radius > 0),
      arrows: asArray(raw.arrows)
        .map((item) => ({
          from: asString(item?.from),
          to: asString(item?.to),
          label: asString(item?.label).trim() || undefined,
          style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
        }))
        .filter((item) => item.from && item.to),
      marks: asArray(raw.marks)
        .map((item) => {
          const markType = MARK_ALIASES[asString(item?.type).trim().toLowerCase()] ?? asString(item?.type).trim()
          if (markType === 'right_angle') {
            return { type: 'right_angle', at: asString(item?.at), arms: normalizePairs([item?.arms])[0] ?? undefined }
          }
          if (markType === 'equal_length' || markType === 'parallel') {
            return {
              type: markType,
              segments: normalizePairs(item?.segments),
              tick: Number.isFinite(Number(item?.tick)) ? Math.round(Number(item.tick)) : 1,
            }
          }
          if (markType === 'angle') {
            return {
              type: 'angle',
              at: asString(item?.at),
              arms: normalizePairs([item?.arms])[0] ?? undefined,
              label: asString(item?.label).trim() || undefined,
            }
          }
          return null
        })
        .filter(Boolean),
      labels: isObject(raw.labels)
        ? Object.fromEntries(Object.entries(raw.labels).map(([key, value]) => [key, Boolean(value)]))
        : {},
      label_offsets: isObject(raw.label_offsets)
        ? Object.fromEntries(
            Object.entries(raw.label_offsets)
              .map(([key, value]) => [key, normalizePointValue(value)])
              .filter(([, value]) => value),
          )
        : {},
    }
    return stripUndefined(spec)
  }

  if (type === 'function' || type === 'coordinate') {
    const curves = asArray(raw.curves)
      .map((item) => ({
        expr: asString(item?.expr ?? item?.expression).trim(),
        variable: asString(item?.variable).trim() || undefined,
        domain: Array.isArray(item?.domain) && item.domain.length === 2 ? item.domain.map(Number) : undefined,
        label: asString(item?.label).trim() || undefined,
        style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
      }))
      .filter((item) => item.expr)
    return stripUndefined({
      type: type === 'function' && !curves.length ? 'function' : curves.length ? 'coordinate' : type,
      title: asString(raw.title).trim() || undefined,
      expression: asString(raw.expression ?? raw.expr).trim() || undefined,
      variable: asString(raw.variable).trim() || undefined,
      domain: Array.isArray(raw.domain) && raw.domain.length === 2 ? raw.domain.map(Number) : undefined,
      x_range: Array.isArray(raw.x_range) && raw.x_range.length === 2 ? raw.x_range.map(Number) : undefined,
      y_range: Array.isArray(raw.y_range) && raw.y_range.length === 2 ? raw.y_range.map(Number) : undefined,
      curves: curves.length ? curves : undefined,
      points: asArray(raw.points)
        .map((item) => ({
          x: asNumber(item?.x ?? item?.[0]),
          y: asNumber(item?.y ?? item?.[1]),
          label: asString(item?.label).trim() || undefined,
          style: item?.style === 'open' ? 'open' : 'filled',
        }))
        .filter((item) => Number.isFinite(item.x) && Number.isFinite(item.y)),
      guides: asArray(raw.guides)
        .map((item) => ({
          from: normalizePointValue(item?.from),
          to: normalizePointValue(item?.to),
          style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
        }))
        .filter((item) => item.from && item.to),
      grid: raw.grid === undefined ? true : Boolean(raw.grid),
      axis_labels: isObject(raw.axis_labels)
        ? { x: asString(raw.axis_labels.x).trim() || 'x', y: asString(raw.axis_labels.y).trim() || 'y' }
        : { x: 'x', y: 'y' },
      mark_key_points: raw.mark_key_points === undefined ? true : Boolean(raw.mark_key_points),
    })
  }

  if (type === 'force') {
    const objectShape = asString(raw.object?.shape).trim().toLowerCase()
    return stripUndefined({
      type: 'force',
      title: asString(raw.title).trim() || undefined,
      object: {
        shape: ['block', 'dot', 'incline'].includes(objectShape)
          ? objectShape
          : Number(raw.incline_angle) > 0
            ? 'incline'
            : 'block',
        label: asString(raw.object?.label).trim() || undefined,
      },
      incline_angle: Number.isFinite(Number(raw.incline_angle)) ? Number(raw.incline_angle) : undefined,
      forces: asArray(raw.forces)
        .map((item) => ({
          label: asString(item?.label).trim() || 'F',
          angle_deg: asNumber(item?.angle_deg ?? item?.angle),
          magnitude: Number.isFinite(Number(item?.magnitude)) ? Number(item.magnitude) : undefined,
          unit: asString(item?.unit).trim() || undefined,
          style: item?.style === 'dashed' ? 'dashed' : 'solid',
          origin: normalizePointValue(item?.origin) ?? undefined,
        }))
        .filter((item) => Number.isFinite(item.angle_deg)),
      velocity: isObject(raw.velocity)
        ? { label: asString(raw.velocity.label).trim() || 'v', angle_deg: asNumber(raw.velocity.angle_deg) }
        : undefined,
      acceleration: isObject(raw.acceleration)
        ? { label: asString(raw.acceleration.label).trim() || 'a', angle_deg: asNumber(raw.acceleration.angle_deg) }
        : undefined,
      axes: Boolean(raw.axes),
      coordinate_note: asString(raw.coordinate_note).trim() || undefined,
    })
  }

  if (type === 'circuit') {
    const nodes = {}
    for (const [name, value] of Object.entries(isObject(raw.nodes) ? raw.nodes : {})) {
      const point = normalizePointValue(value)
      if (point) nodes[asString(name)] = point
    }
    return stripUndefined({
      type: 'circuit',
      title: asString(raw.title).trim() || undefined,
      nodes: Object.keys(nodes).length ? nodes : undefined,
      components: asArray(raw.components)
        .map((item) => {
          const kindText = asString(item?.kind).trim().toLowerCase()
          return {
            kind: COMPONENT_ALIASES[kindText] ?? kindText,
            from: asString(item?.from),
            to: asString(item?.to),
            label: asString(item?.label).trim() || undefined,
            value: asString(item?.value).trim() || undefined,
            polarity: item?.polarity === 'reversed' ? 'reversed' : 'normal',
          }
        })
        .filter((item) => item.kind && item.from && item.to),
      current_arrows: asArray(raw.current_arrows)
        .map((item) => ({
          from: asString(item?.from),
          to: asString(item?.to),
          label: asString(item?.label).trim() || undefined,
        }))
        .filter((item) => item.from && item.to),
      notes: asArray(raw.notes).map((item) => asString(item)).filter(Boolean).slice(0, 4),
    })
  }

  if (type === 'optics') {
    return stripUndefined({
      type: 'optics',
      title: asString(raw.title).trim() || undefined,
      surfaces: asArray(raw.surfaces)
        .map((item) => {
          const kindText = asString(item?.kind).trim().toLowerCase()
          return {
            kind: SURFACE_ALIASES[kindText] ?? kindText,
            from: normalizePointValue(item?.from),
            to: normalizePointValue(item?.to),
            label: asString(item?.label).trim() || undefined,
          }
        })
        .filter((item) => item.from && item.to),
      rays: asArray(raw.rays)
        .map((item) => ({
          points: asArray(item?.points).map(normalizePointValue).filter(Boolean),
          label: asString(item?.label).trim() || undefined,
          style: ['solid', 'dashed', 'dotted'].includes(item?.style) ? item.style : undefined,
        }))
        .filter((item) => item.points.length >= 2),
      normals: asArray(raw.normals)
        .map((item) => ({ from: normalizePointValue(item?.from), to: normalizePointValue(item?.to) }))
        .filter((item) => item.from && item.to),
      axis: isObject(raw.axis)
        ? { from: normalizePointValue(raw.axis.from), to: normalizePointValue(raw.axis.to) }
        : undefined,
      focal_points: asArray(raw.focal_points)
        .map((item) => ({ at: normalizePointValue(item?.at), label: asString(item?.label).trim() || undefined }))
        .filter((item) => item.at),
      labels: asArray(raw.labels)
        .map((item) => ({ at: normalizePointValue(item?.at), text: asString(item?.text) }))
        .filter((item) => item.at && item.text),
    })
  }

  if (type === 'chart') {
    return stripUndefined({
      type: 'chart',
      title: asString(raw.title).trim() || undefined,
      kind: ['line', 'bar', 'scatter'].includes(raw.kind) ? raw.kind : 'line',
      series: asArray(raw.series)
        .map((item) => ({
          label: asString(item?.label).trim() || undefined,
          points: asArray(item?.points)
            .map((point) => (Array.isArray(point) && point.length >= 2 ? [asNumber(point[0]), asNumber(point[1])] : null))
            .filter(Boolean),
        }))
        .filter((item) => item.points.length > 0),
      x_label: asString(raw.x_label).trim() || undefined,
      y_label: asString(raw.y_label).trim() || undefined,
    })
  }

  return base
}

export function normalizeAnswerSpec(raw) {
  const source = isObject(raw) ? raw : {}
  return {
    problem_type: asString(source.problem_type).trim() || undefined,
    strategy: asString(source.strategy).trim() || undefined,
    steps: asArray(source.steps)
      .map((item, index) => ({
        step: Math.max(1, Math.round(asNumber(item?.step, index + 1))),
        content: asString(item?.content ?? item).trim(),
        reason: asString(item?.reason).trim() || undefined,
        score_relevance: ['key', 'normal', 'minor'].includes(item?.score_relevance)
          ? item.score_relevance
          : 'normal',
      }))
      .filter((item) => item.content),
    final_answer: asString(source.final_answer).trim(),
    verification: asArray(source.verification).filter(isObject),
    diagram_refs: asArray(source.diagram_refs).map((item) => asString(item)).filter(Boolean),
    confidence: clamp(source.confidence, 0, 1, 0.7),
    notes: asArray(source.notes).map((item) => asString(item)).filter(Boolean).slice(0, 8),
  }
}

function stripUndefined(value) {
  if (Array.isArray(value)) return value.map(stripUndefined)
  if (isObject(value)) {
    const result = {}
    for (const [key, item] of Object.entries(value)) {
      if (item === undefined) continue
      result[key] = stripUndefined(item)
    }
    return result
  }
  return value
}
