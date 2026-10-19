/**
 * Prompt library. Kept in one file so the instructions can be reviewed,
 * diffed and tested as a unit. Every prompt demands a single JSON value and
 * forbids inventing conditions that are not visible.
 */

export const PROBLEM_SCHEMA_CARD = `ProblemSpec JSON:
{
  "subject": "math|physics|unknown",
  "grade_level": "primary|middle_school|high_school|university|unknown",
  "problem_type": "equation_solving|inequality|function_analysis|trigonometry|geometry_proof|geometry_computation|analytic_geometry|vector|solid_geometry|calculus|probability_statistics|kinematics|dynamics|work_energy|momentum|electrostatics|circuit|magnetism|electromagnetic_induction|optics|waves|experiment|other",
  "question_format": "multiple_choice|fill_blank|written_solution|proof|unknown",
  "raw_text": "逐字转录的题干（保留换行）",
  "conditions": [{"text": "已知条件", "source": "image|ocr|inferred"}],
  "questions": [{"text": "所求问题", "index": 1}],
  "options": [{"label": "A", "text": "选项内容"}],
  "symbols": [{"name": "v", "meaning": "速度", "unit": "m/s", "value": "..."}],
  "equations": [{"text": "x**2-5*x+6=0", "latex": "", "role": "given|target|definition", "label": ""}],
  "visual_objects": [{"id": "A", "kind": "point|segment|line|ray|circle|arc|angle|triangle|polygon|vector|axis|object|incline|pulley|string|spring|battery|resistor|ammeter|voltmeter|switch|lamp|capacitor|inductor|lens|mirror|ray_of_light|unknown", "label": "A", "attributes": {}}],
  "visual_relations": [{"type": "collinear|perpendicular|parallel|equal_length|point_on_segment|point_on_circle|concyclic|right_angle|angle_equals|midpoint|bisects|tangent|similar|congruent|force|velocity|current|electric_field", "objects": ["A", "BC"], "value": "", "confidence": 0.9}],
  "requires_diagram": null,
  "diagram_role": null,
  "diagram_type_hint": null,
  "uncertainties": [{"issue": "看不清的地方", "impact": "对解题的影响", "alternative": "另一种可能"}],
  "recognition_confidence": 0.0
}`

export const DIAGRAM_SCHEMA_CARD = `DiagramSpec JSON（只能取下面一种 type，字段名必须一致）:

1) 平面几何：
{"type":"geometry","title":"","points":{"A":[0,0],"B":[4,0]},"segments":[["A","B"]],"auxiliary_segments":[["A","D"]],"rays":[{"from":"A","to":"B"}],"lines":[["A","B"]],"polygons":[{"points":["A","B","C"],"fill":"#eff6ff"}],"circles":[{"center":"O","through":"A","label":""}],"arcs":[{"center":"O","radius":2,"start_angle":0,"end_angle":90}],"arrows":[{"from":"A","to":"B","label":"v"}],"marks":[{"type":"right_angle","at":"D","arms":["A","B"]},{"type":"equal_length","segments":[["A","B"],["A","C"]],"tick":1},{"type":"parallel","segments":[["A","B"]],"tick":1},{"type":"angle","at":"A","arms":["B","C"],"label":"60°"}],"labels":{"A":true},"label_offsets":{"A":[10,-8]}}

2) 函数/坐标系（type 用 "function" 时只给 expression，用 "coordinate" 时可给多条 curves）：
{"type":"function","title":"","expression":"x**2-2*x-3","variable":"x","x_range":[-5,5],"y_range":[-6,6],"grid":true,"mark_key_points":true,"axis_labels":{"x":"x","y":"y"}}
{"type":"coordinate","curves":[{"expr":"1/x","label":"y=1/x","style":"solid"}],"points":[{"x":1,"y":1,"label":"P","style":"filled"}],"guides":[{"from":[1,0],"to":[1,1]}],"grid":true}

3) 受力图（角度：0=向右，90=向上，必须与解题判断一致）：
{"type":"force","title":"","object":{"shape":"block|dot|incline","label":"m"},"incline_angle":30,"forces":[{"label":"mg","angle_deg":270,"magnitude":10,"unit":"N"}],"velocity":{"label":"v","angle_deg":0},"acceleration":{"label":"a","angle_deg":0},"axes":true}

4) 电路（必须闭合；节点名即接线点，可省略 nodes 由程序自动布局）：
{"type":"circuit","title":"","nodes":{"A":[0,0],"B":[4,0]},"components":[{"kind":"battery|resistor|ammeter|voltmeter|switch|lamp|capacitor|inductor|rheostat","from":"A","to":"B","label":"R1","value":"6Ω","polarity":"normal"}],"current_arrows":[{"from":"A","to":"B","label":"I"}]}

5) 光路：
{"type":"optics","title":"","surfaces":[{"kind":"mirror|interface|lens|screen","from":[0,-2],"to":[0,2],"label":""}],"rays":[{"points":[[-3,2],[0,0],[3,2]],"label":"反射光线"}],"normals":[{"from":[-1,0],"to":[1,0]}],"axis":{"from":[-5,0],"to":[5,0]},"focal_points":[{"at":[-2,0],"label":"F"}]}`

export const ANSWER_SCHEMA_CARD = `AnswerSpec JSON:
{
  "problem_type": "与题目一致",
  "strategy": "一句话说明解题思路",
  "steps": [{"step": 1, "content": "写在卷面上的内容（公式/推导/结论）", "reason": "依据（定理、定律、定义）", "score_relevance": "key|normal|minor"}],
  "final_answer": "最终答案（含单位；证明题写结论）",
  "verification": [
    {"kind": "equation_substitution", "equation": "x**2-5*x+6=0", "assignments": {"x": "2"}},
    {"kind": "identity", "lhs": "sin(2*x)", "rhs": "2*sin(x)*cos(x)", "variables": ["x"]},
    {"kind": "derivative", "expression": "x**3", "variable": "x", "claimed": "3*x**2"},
    {"kind": "integral", "expression": "2*x", "variable": "x", "claimed": "x**2", "lower": "0", "upper": "1"},
    {"kind": "numeric", "expression": "sqrt(3)/2", "expected": "0.8660254", "tolerance": 1e-6},
    {"kind": "unit_check", "value": "10", "unit": "m/s", "dimension": "velocity"}
  ],
  "diagram_refs": [],
  "confidence": 0.0
}`

const LANGUAGE_RULE = {
  zh: '使用与题目相同的语言书写解答（通常为中文）。数学符号保持规范。',
  en: 'Write the solution in English unless the problem itself is in another language.',
}

export function systemPrompt(role) {
  return (
    `你是一名资深的中国中学数学/物理教师与命题研究者，熟悉中高考评分标准。` +
    `你只输出一个严格的 JSON 值：不要 Markdown 代码围栏，不要解释，不要多余文字。` +
    `你不臆造题目条件：看不清或信息不足时，必须写入 uncertainties 并降低置信度。` +
    `当前任务：${role}`
  )
}

export function recognitionPrompt({ subjectHint, gradeHint, language }) {
  const hints = []
  if (subjectHint && subjectHint !== 'auto') hints.push(`学科提示：${subjectHint}`)
  if (gradeHint && gradeHint !== 'auto') hints.push(`年级提示：${gradeHint}`)
  return `请识别图片中的整道题目，并输出 ProblemSpec JSON。

${PROBLEM_SCHEMA_CARD}

识别规则：
1. raw_text 逐字转录题干与设问，不要翻译、不要改写。上下标用文字表达清楚（如 x² 写成 x^2）。
2. equations 使用 SymPy 可解析写法：乘方用 **，分式用 /，根号用 sqrt()，π 用 pi，≤ 用 <=。
3. 若题目含图：visual_objects 列出图中的点、线段、圆、物体、元件、光线等；visual_relations 只列能确证的关系（共线、垂直、平行、等长、点在线上、点在圆上、共圆、直角、中点、相切等）。点用单字母名，线段用 "BC" 形式。
4. 图形看不清、文字被裁切、符号有歧义时，写入 uncertainties（说明 issue/impact/alternative），并降低 recognition_confidence。
5. 多个小问全部放入 questions，不要只取第一问。
6. requires_diagram 一律填 null，由后续程序判定。
7. 只输出 JSON，不要任何解释。${hints.length ? `\n${hints.join('\n')}` : ''}
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function relationsPrompt({ language }) {
  return `请只分析图片中的图形结构（忽略文字推理），输出 JSON：
{"visual_objects":[{"id":"A","kind":"point","label":"A"}],"visual_relations":[{"type":"perpendicular","objects":["AD","BC"],"confidence":0.9}],"uncertainties":[{"issue":"..."}],"diagram_type_hint":"geometry|coordinate|function|force|circuit|optics|chart|none"}

要求：
- 只描述图上确实画出的内容；看不见的关系不要猜。
- 角度、平行、等长等标记（直角符号、等长刻度、平行箭头）要转成 visual_relations。
- 物理图请识别：物体、斜面、绳、滑轮、电源、电阻、电表、光线、透镜、场方向。
- 点用单字母，线段用两个点名（如 "BC"）。
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function diagramPrompt({ problemSpec, diagramType, role, language }) {
  return `根据下面的题目信息，生成用于作答的 DiagramSpec JSON。

【题目】
${JSON.stringify(problemSpec, null, 2)}

【作图要求】
- 图的用途：${role === 'final_answer' || role === 'both' ? '正式作答图（会出现在最终答案里，必须规范、完整、可读）' : '辅助理解图'}
- 优先使用的图类型：${diagramType}
- 图形必须与题目条件严格一致：题目说垂直就垂直，说共线就共线，说等长就等长。
- 几何图中：边和已知线段用 segments，辅助线用 auxiliary_segments；lines 只用于真正向两端无限延伸的直线。不要用 lines 画普通线段。
- 只有题目条件明确给出时才画直角/等长/平行标记；本题要求证明的结论不要预先标成已知。
- 坐标自行设计，但要保证所有几何关系在数值上成立（相对误差 < 0.2%）。取点尽量简洁，例如把直角顶点放在原点。
- 图中必须标注题目涉及的点、已知量、关键角与长度；不需要标注无关的点。
- 不要添加题目没有的条件，也不要在图里写解题过程。
- 只输出一个 DiagramSpec JSON。

${DIAGRAM_SCHEMA_CARD}
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function diagramRepairPrompt({ previous, errors, problemSpec, language }) {
  return `你生成的 DiagramSpec 未通过校验，请修正后重新输出完整 JSON。

【题目】
${JSON.stringify(problemSpec, null, 2)}

【上一次的 DiagramSpec】
${JSON.stringify(previous, null, 2)}

【校验错误】
${errors.map((item) => `- ${item.path ?? '$'}: ${item.message ?? item}`).join('\n')}

要求：
- 逐条修正上面的错误；如果错误来自坐标不满足几何关系，请重新计算坐标。
- 保持题目要求的全部元素，不要删掉关键点或标记。
- 只输出修正后的 DiagramSpec JSON（不要解释）。
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function relationRepairPrompt({ previous, contradictions, language }) {
  return `你生成的图上，有一部分几何关系与题目矛盾，请修正坐标后重新输出完整 DiagramSpec。

【上一次的 DiagramSpec】
${JSON.stringify(previous, null, 2)}

【不成立的几何关系】
${contradictions.map((item) => `- ${item}`).join('\n')}

要求：调整相关点的坐标，使上述关系成立（误差 < 0.2%），其余图形保持不变。只输出修正后的 DiagramSpec JSON。
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function solvePrompt({ problemSpec, diagramSpec, answerMode, language, uncertainties }) {
  const detail =
    answerMode === 'concise'
      ? '选择题/填空题风格：只写必要步骤，2-4 步，直接给结果。'
      : answerMode === 'teaching'
        ? '教学风格：步骤完整，并在 reason 中解释方法、易错点和检查方式。'
        : '考试作答风格：步骤完整、依据明确、结论清晰，适合直接誊写到答题卡。'
  return `请解答下面的题目，输出 AnswerSpec JSON。

【题目】
${JSON.stringify(problemSpec, null, 2)}
${diagramSpec ? `\n【已有的作答图（坐标已确定，请与图保持一致）】\n${JSON.stringify(diagramSpec, null, 2)}\n` : ''}
${uncertainties?.length ? `\n【识别不确定项，解题时按给定假设处理并在答案中说明】\n${uncertainties.map((item) => `- ${item.issue}（影响：${item.impact ?? '未知'}）`).join('\n')}\n` : ''}
解题要求：
1. 先明确已知、未知与所用模型（物理题先确定研究对象、方向与正方向）。
2. 每一步写出公式和依据；证明题的逻辑链必须完整，禁止“显然”“易得”。
3. 物理量必须带单位，数值结果检查数量级是否合理；矢量说明方向。
4. final_answer 用一句结论性的话，包含全部小问的答案。
5. verification 至少给出 2 条能被程序验证的断言（能验证什么就给什么）：
   - 解方程的答案用 equation_substitution 回代；
   - 恒等式/化简用 identity；
   - 求导/积分用 derivative/integral；
   - 数值结果用 numeric（给出 expected 与 tolerance）；
   - 物理结果用 unit_check 声明量纲。
   断言必须与 final_answer 一致，不能为了通过而写无关的恒等式。
6. ${detail}
7. confidence 反映你对答案的把握（0-1）。识别不确定时降低它。

${ANSWER_SCHEMA_CARD}
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function examinerPrompt({ problemSpec, answerSpec, validationReport, maxScore, language }) {
  return `你现在是阅卷老师，只做评分与失分点诊断，不要重新解题。

【题目】
${JSON.stringify(problemSpec, null, 2)}

【学生答案】
${JSON.stringify(answerSpec, null, 2)}

【程序校验结果】（权威，不得与之矛盾）
${JSON.stringify(validationReport, null, 2)}

评分维度：
- 正确性：最终答案是否合理，是否与程序校验冲突；
- 步骤分：关键公式、关键推导、依据、中间结果、单位、作图；
- 表达：结论是否明确、符号是否定义、是否跳步；
- 作图：题目要求作图时是否有图、关键点是否标注。

输出 JSON：
{"estimated_score":0,"max_score":${maxScore},"lost_points":[{"reason":"具体失分点","estimated_loss":1,"fix":"怎么改"}],"strengths":["得分点"],"revision_required":true,"revision_instructions":["具体修改指令"]}

要求：
- 失分点必须具体、可执行，不要写空话。
- 程序校验失败时必须计入失分，且 revision_required=true。
- 总分不得超过 max_score。只输出 JSON。
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function revisionPrompt({ problemSpec, answerSpec, issues, diagramSpec, answerMode, language }) {
  return `请根据下面的问题清单修改答案，输出修正后的完整 AnswerSpec JSON。

【题目】
${JSON.stringify(problemSpec, null, 2)}
${diagramSpec ? `\n【作答图】\n${JSON.stringify(diagramSpec, null, 2)}\n` : ''}
【当前答案】
${JSON.stringify(answerSpec, null, 2)}

【必须修正的问题】
${issues.map((item) => `- ${item}`).join('\n')}

要求：
- 逐条解决问题；被程序验证判定为错误的结论必须改正，不得辩解。
- 修改后保持步骤完整、结论明确、单位齐全。
- verification 中的断言必须与新的 final_answer 一致。
- 只输出修正后的 AnswerSpec JSON，不要解释。
${answerMode === 'teaching' ? '可以在 reason 中补充方法与易错点。' : ''}
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}

export function finalizePrompt({ problemSpec, answerSpec, examReport, language }) {
  return `请把下面的答案整理成一份可以直接写进答题卡的规范答案。

【题目】
${JSON.stringify(problemSpec, null, 2)}

【答案】
${JSON.stringify(answerSpec, null, 2)}

【阅卷反馈】
${JSON.stringify(examReport, null, 2)}

输出 JSON：{"solution_markdown":"完整解答（Markdown，公式用行内 LaTeX 或纯文本）","final_answer":"最终答案","notes":["需要提醒学生的点"]}

要求：
- 保留全部关键步骤和依据，不要因压缩而丢分。
- 按阅卷反馈补齐失分点。
- 不要出现“程序验证”“评分”等内部术语。
- 只输出 JSON。
${LANGUAGE_RULE[language] ?? LANGUAGE_RULE.zh}`
}
