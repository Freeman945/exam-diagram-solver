import fs from 'node:fs'

/**
 * Agent-facing tool surface.
 *
 * The main entry (`solve_exam_image`) orchestrates the whole pipeline. The
 * stage tools are exposed too, so an agent can inject its own reasoning at a
 * single step without paying for the whole run.
 */

const OBJECT_SCHEMA = { type: 'object', additionalProperties: true }

function stringSchema(description, extra = {}) {
  return { type: 'string', description, ...extra }
}

function numberSchema(description, { default: defaultValue, minimum, maximum } = {}) {
  const schema = { type: 'number', description }
  if (defaultValue !== undefined) schema.default = defaultValue
  if (minimum !== undefined) schema.minimum = minimum
  if (maximum !== undefined) schema.maximum = maximum
  return schema
}

function enumSchema(description, values, defaultValue) {
  const schema = { type: 'string', enum: values, description }
  if (defaultValue !== undefined) schema.default = defaultValue
  return schema
}

function stringArraySchema(description) {
  return { type: 'array', items: { type: 'string' }, description }
}

function specSchema(description) {
  return { type: 'object', description, additionalProperties: true }
}

function idSchema(description) {
  return { type: 'string', description }
}

function jsonRender(value, limit = 6000) {
  const text = JSON.stringify(value, null, 2)
  return [{ type: 'text', text: text.length > limit ? `${text.slice(0, limit)}\n…（已截断）` : text }]
}

function answerBrief(answer) {
  const lines = []
  if (answer?.strategy) lines.push(`思路：${answer.strategy}`)
  for (const [index, step] of (answer?.steps ?? []).entries()) {
    const reason = step.reason ? `（${step.reason}）` : ''
    lines.push(`${index + 1}. ${step.content}${reason}`)
  }
  if (answer?.final_answer) {
    lines.push('')
    lines.push(`**最终答案**：${answer.final_answer}`)
  }
  return lines.join('\n')
}

function wrapErrors(error) {
  const code = error?.code || error?.name || 'EXAM_SOLVER_ERROR'
  const detail = error?.code ? `[${code}] ` : ''
  const wrapped = new Error(`${detail}${error?.message ?? String(error)}`)
  wrapped.name = code
  if (error?.details) wrapped.details = error.details
  return wrapped
}

export function createTools({ ctx, config, engine, llm, pipeline, store, images, logger }) {
  const tools = []

  function guarded(handler) {
    return async (args, exec) => {
      try {
        return await handler(args ?? {}, exec)
      } catch (error) {
        throw wrapErrors(error)
      } finally {
        logger.flush?.()
      }
    }
  }

  function resolveProblem(args) {
    if (args.problemSpec && typeof args.problemSpec === 'object') {
      return { spec: args.problemSpec, id: null }
    }
    if (args.problemSpecId) {
      const spec = store.get(args.problemSpecId)
      if (!spec) throw Object.assign(new Error(`unknown problemSpecId: ${args.problemSpecId}`), { code: 'UNKNOWN_SPEC_ID' })
      return { spec, id: args.problemSpecId }
    }
    const latest = store.latest('problem')
    if (latest) return { spec: latest.value, id: latest.id }
    throw Object.assign(
      new Error('缺少 problemSpec。请先调用 exam_analyze_image（或直接传入 problemSpec 对象）。'),
      { code: 'MISSING_PROBLEM_SPEC' },
    )
  }

  function resolveDiagram(args) {
    if (args.diagram && typeof args.diagram === 'object') return { spec: args.diagram, id: null }
    if (args.diagramId) {
      const spec = store.get(args.diagramId)
      if (!spec) throw Object.assign(new Error(`unknown diagramId: ${args.diagramId}`), { code: 'UNKNOWN_SPEC_ID' })
      return { spec, id: args.diagramId }
    }
    const latest = store.latest('diagram')
    if (latest) return { spec: latest.value, id: latest.id }
    throw Object.assign(new Error('缺少 DiagramSpec。请先调用 exam_create_diagram_spec。'), {
      code: 'MISSING_DIAGRAM_SPEC',
    })
  }

  function resolveAnswer(args) {
    if (args.answerSpec && typeof args.answerSpec === 'object') return { spec: args.answerSpec, id: null }
    if (args.answerSpecId) {
      const spec = store.get(args.answerSpecId)
      if (!spec) throw Object.assign(new Error(`unknown answerSpecId: ${args.answerSpecId}`), { code: 'UNKNOWN_SPEC_ID' })
      return { spec, id: args.answerSpecId }
    }
    const latest = store.latest('answer')
    if (latest) return { spec: latest.value, id: latest.id }
    throw Object.assign(new Error('缺少 AnswerSpec。请先调用 exam_solve_problem。'), { code: 'MISSING_ANSWER_SPEC' })
  }

  async function attachPreview(result) {
    const png = result?.diagram?.files?.png
    if (!png || !fs.existsSync(png)) return null
    const attachments = ctx.get('attachments')
    if (!attachments?.saveImage) return null
    try {
      const data = fs.readFileSync(png)
      return await attachments.saveImage({
        data: new Uint8Array(data),
        mediaType: 'image/png',
        name: 'exam-diagram.png',
      })
    } catch (error) {
      logger.warn(`could not attach diagram preview: ${error.message}`)
      return null
    }
  }

  // ------------------------------------------------------------------- main

  tools.push({
    name: 'solve_exam_image',
    description:
      '拍题主入口：对一张（或多张）题目图片执行完整流程——多模态识别 → 结构化 ProblemSpec → 判断是否需要作图 → 生成并校验 DiagramSpec → 程序化绘图 → 规范解题 → SymPy/量纲验证 → 模拟阅卷 → 必要时自动修正 → 输出可誊写的答案与图。' +
      '用户上传题目照片后可以直接无参数调用（会自动使用本次对话最新的题目图片），也可传 imagePaths 指定本机图片。' +
      '只支持数学与物理；图片模糊或信息不足时会明确给出不确定性而不是编造条件。',
    timeoutMs: Math.round(config.timeoutSec * 1000),
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        imagePaths: stringArraySchema('题目图片的绝对路径列表。省略时使用当前对话中最新上传的图片。'),
        subjectHint: enumSchema('学科提示（可选）', ['auto', 'math', 'physics'], 'auto'),
        gradeHint: enumSchema('年级提示（可选）', ['auto', 'middle_school', 'high_school', 'university'], 'auto'),
        answerMode: enumSchema('答案风格：concise 精简 / exam 考试作答（默认）/ teaching 教学讲解', ['concise', 'exam', 'teaching']),
        quality: enumSchema('流程深度：fast 快速（不阅卷不修正）/ balanced 默认 / high 深校验', ['fast', 'balanced', 'high']),
        diagram: enumSchema('作图策略：auto 按规则判断 / force 强制作图 / none 不作图', ['auto', 'force', 'none'], 'auto'),
        maxRevisionRounds: numberSchema('最大自动修正轮数（0-3）', { minimum: 0, maximum: 3 }),
      },
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (args, value) => {
        const blocks = [{ type: 'text', text: value.final || value.finalAnswer || '（无输出）' }]
        if (value.preview) blocks.push({ type: 'image', attachment: value.preview })
        return blocks
      },
    },
    execute: guarded(async (args, exec) => {
      const resolved = images.resolve(exec.agent, args)
      const imageBlocks = images.toLlmImages(resolved)
      logger.info(`solve_exam_image: ${resolved.source} image(s)`, { names: resolved.names })
      const result = await pipeline.solveImage({
        imageBlocks,
        subjectHint: args.subjectHint ?? 'auto',
        gradeHint: args.gradeHint ?? 'auto',
        answerMode: args.answerMode ?? config.answerMode,
        quality: args.quality ?? config.quality,
        diagramHint: args.diagram === 'auto' ? null : args.diagram ?? null,
        signal: exec.signal,
      })
      const preview = await attachPreview(result)
      const finalResult = { ...result, preview: preview ?? null, imageSource: resolved.source }
      logger.info(`solve_exam_image done: ${finalResult.status}`, {
        runId: finalResult.runId,
        durationMs: finalResult.metrics.durationMs,
        revisionRounds: finalResult.metrics.revisionRounds,
      })
      return finalResult
    }),
  })

  // ------------------------------------------------------------ recognition

  tools.push({
    name: 'exam_analyze_image',
    description:
      '只做识别：把题目图片转成结构化 ProblemSpec（学科、题型、条件、问题、公式、图中对象与关系、不确定项、识别置信度）。' +
      '需要单独检查识别质量、或想自己在后续步骤里接管推理时使用。图片会以原生多模态方式送入模型，不做“先 OCR 再丢图”。',
    timeoutMs: 300_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        imagePaths: stringArraySchema('题目图片绝对路径；省略时使用当前对话最新图片。'),
        subjectHint: enumSchema('学科提示', ['auto', 'math', 'physics'], 'auto'),
        gradeHint: enumSchema('年级提示', ['auto', 'middle_school', 'high_school', 'university'], 'auto'),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const resolved = images.resolve(exec.agent, args)
      const imageBlocks = images.toLlmImages(resolved)
      const { spec, warnings } = await pipeline.analyzeProblem({
        imageBlocks,
        subjectHint: args.subjectHint ?? 'auto',
        gradeHint: args.gradeHint ?? 'auto',
        signal: exec.signal,
      })
      const problemSpecId = store.put('problem', spec)
      return { problemSpec: spec, problemSpecId, warnings, imageSource: resolved.source }
    }),
  })

  tools.push({
    name: 'exam_reconstruct_diagram',
    description:
      '重建题目“已有图形”的结构：输出图中的点、线、圆、物体、元件、光线等对象，以及共线/垂直/平行/等长/点在线上/点在圆上/共圆等关系。' +
      '用于题目本身给了图、需要把图读懂而不只是读文字的场景。返回合并后的 ProblemSpec。',
    timeoutMs: 300_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        imagePaths: stringArraySchema('题目图片绝对路径；省略时使用当前对话最新图片。'),
        problemSpec: specSchema('已有的 ProblemSpec（可选，提供会合并结果）'),
        problemSpecId: idSchema('已有 ProblemSpec 的 id（可选）'),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const resolved = images.resolve(exec.agent, args)
      const { spec } = resolveProblem(args)
      const merged = await pipeline.reconstructRelations({
        problemSpec: spec,
        imageBlocks: images.toLlmImages(resolved),
        signal: exec.signal,
      })
      return merged
    }),
  })

  // ---------------------------------------------------------------- diagram

  tools.push({
    name: 'exam_decide_diagram',
    description:
      '判断这道题是否需要作图，以及图属于“辅助图”还是“正式作答图”。判断基于题型、题干中的作图要求、是否已有图形等可解释规则，并返回命中的规则。',
    timeoutMs: 60_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        problemSpec: specSchema('ProblemSpec（可选）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
        hint: enumSchema('强制策略', ['auto', 'force', 'none'], 'auto'),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args) => {
      const { spec } = resolveProblem(args)
      const decision = pipeline.decideDiagramRequirement(spec, {
        hint: args.hint === 'auto' ? null : args.hint ?? null,
      })
      return { ...decision, reasoning: '规则判定，可用于复核' }
    }),
  })

  tools.push({
    name: 'exam_create_diagram_spec',
    description:
      '根据 ProblemSpec 设计 DiagramSpec（决定“画什么”），并调用程序完成严格 Schema 校验与几何关系校验；不通过时会按错误信息自动修正（有次数上限）。' +
      '返回的 DiagramSpec 可以直接交给 exam_render_diagram。',
    timeoutMs: 420_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        problemSpec: specSchema('ProblemSpec（可选）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
        diagramType: enumSchema('指定图类型', ['auto', 'geometry', 'coordinate', 'function', 'force', 'circuit', 'optics', 'chart'], 'auto'),
        role: enumSchema('图的用途', ['auxiliary', 'final_answer', 'both'], 'auxiliary'),
        imagePaths: stringArraySchema('题目图片路径（可选，帮助对齐原图）'),
        maxRepairRounds: numberSchema('最大修正次数', { minimum: 0, maximum: 4 }),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const { spec } = resolveProblem(args)
      const decision = {
        required: true,
        role: args.role ?? 'auxiliary',
        diagram_type:
          args.diagramType && args.diagramType !== 'auto'
            ? args.diagramType
            : spec.diagram_type_hint ?? 'geometry',
        reason: '由 exam_create_diagram_spec 显式请求',
        applied_rules: ['explicit_tool_call'],
      }
      let imageBlocks = []
      try {
        const resolved = images.resolve(exec.agent, args)
        imageBlocks = images.toLlmImages(resolved)
      } catch {
        imageBlocks = []
      }
      const runDir = engine.runDir(`diagram-${Date.now()}`)
      const result = await pipeline.planDiagram({
        problemSpec: spec,
        decision,
        imageBlocks,
        runDir,
        signal: exec.signal,
      })
      const diagramId = result.spec ? store.put('diagram', result.spec) : null
      return {
        diagramSpec: result.spec,
        diagramId,
        validation: result.validation,
        files: result.files,
        attempts: result.attempts,
        error: result.error,
        warnings: result.warnings,
      }
    }),
  })

  tools.push({
    name: 'exam_validate_diagram',
    description:
      '检查 DiagramSpec 与题目条件是否矛盾：共线是否真的共线、垂直是否真的垂直、等长/共圆/点在线上是否成立，并做结构自检（重点重名、零长线段、未定义点）。返回逐项检查结果。',
    timeoutMs: 120_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        diagram: specSchema('DiagramSpec（可选）'),
        diagramId: idSchema('DiagramSpec id（可选）'),
        problemSpec: specSchema('ProblemSpec（可选，用于提取几何关系）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const { spec: diagram } = resolveDiagram(args)
      let problem = null
      try {
        problem = resolveProblem(args).spec
      } catch {
        problem = null
      }
      const report = await pipeline.engineCall(
        'validate_diagram',
        { diagram, problemSpec: problem ?? {} },
        exec.signal,
        120_000,
      )
      return report
    }),
  })

  tools.push({
    name: 'exam_render_diagram',
    description:
      '把已验证的 DiagramSpec 渲染成 SVG（矢量，规范输出）和 PNG（预览）。也可渲染手动编写的 DiagramSpec；绘图完全由程序完成，不依赖模型“画图”。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        diagram: specSchema('DiagramSpec（可选）'),
        diagramId: idSchema('DiagramSpec id（可选）'),
        basename: stringSchema('输出文件名（不含扩展名）', { default: 'diagram' }),
        width: numberSchema('宽度像素', { default: config.diagramWidth, minimum: 320, maximum: 2000 }),
        height: numberSchema('高度像素', { default: config.diagramHeight, minimum: 240, maximum: 2000 }),
        formats: {
          type: 'array',
          items: { type: 'string', enum: ['svg', 'png'] },
          description: '输出格式（默认 svg + png）',
        },
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const { spec: diagram } = resolveDiagram(args)
      const runDir = engine.runDir(`render-${Date.now()}`)
      const data = await pipeline.engineCall(
        'render_diagram',
        {
          diagram,
          outDir: runDir,
          basename: String(args.basename ?? 'diagram').replace(/[^\w.-]+/g, '_'),
          width: args.width ?? config.diagramWidth,
          height: args.height ?? config.diagramHeight,
          dpi: config.dpi,
          formats: args.formats ?? ['svg', 'png'],
        },
        exec.signal,
        120_000,
      )
      return { ...data, diagramId: store.put('diagram', diagram) }
    }),
  })

  // ------------------------------------------------------------------ solve

  tools.push({
    name: 'exam_solve_problem',
    description:
      '根据结构性 ProblemSpec（可附 DiagramSpec）给出规范解答，输出 AnswerSpec：策略、分步内容与依据、最终答案、可机器验证的断言、置信度。' +
      '如果已有题目图片，建议同时传 imagePaths，让模型在解题时再次对照原图。',
    timeoutMs: 420_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        problemSpec: specSchema('ProblemSpec（可选）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
        diagram: specSchema('DiagramSpec（可选）'),
        diagramId: idSchema('DiagramSpec id（可选）'),
        imagePaths: stringArraySchema('题目图片路径（可选）'),
        answerMode: enumSchema('答案风格', ['concise', 'exam', 'teaching'], 'exam'),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const { spec } = resolveProblem(args)
      let diagramSpec = null
      try {
        diagramSpec = resolveDiagram(args).spec
      } catch {
        diagramSpec = null
      }
      let imageBlocks = []
      try {
        imageBlocks = images.toLlmImages(images.resolve(exec.agent, args))
      } catch {
        imageBlocks = []
      }
      const answer = await pipeline.solveProblem({
        problemSpec: spec,
        diagramSpec,
        imageBlocks,
        answerMode: args.answerMode ?? config.answerMode,
        signal: exec.signal,
      })
      const answerSpecId = store.put('answer', answer)
      return { answerSpec: answer, answerSpecId, markdown: answerBrief(answer) }
    }),
  })

  tools.push({
    name: 'exam_validate_solution',
    description:
      '用程序独立验证解答：SymPy 回代方程、检查恒等式/导数/积分、数值比对，物理题检查单位与量纲并做数量级合理性检查；如有 DiagramSpec，还会检查图与题目是否一致。' +
      '返回 ValidationReport（逐项通过/失败、矛盾点、修改建议）。',
    timeoutMs: 300_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        problemSpec: specSchema('ProblemSpec（可选）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
        answerSpec: specSchema('AnswerSpec（可选）'),
        answerSpecId: idSchema('AnswerSpec id（可选）'),
        diagram: specSchema('DiagramSpec（可选）'),
        diagramId: idSchema('DiagramSpec id（可选）'),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const { spec: problem } = resolveProblem(args)
      const { spec: answer } = resolveAnswer(args)
      let diagramSpec = null
      try {
        diagramSpec = resolveDiagram(args).spec
      } catch {
        diagramSpec = null
      }
      const report = await pipeline.validateSolution({
        problemSpec: problem,
        answerSpec: answer,
        diagramSpec,
        signal: exec.signal,
      })
      return { ...report, validationId: store.put('validation', report) }
    }),
  })

  tools.push({
    name: 'exam_grade_answer',
    description:
      '模拟阅卷老师：按正确性、步骤分、表达、作图四个维度给出失分点与修改指令，并返回内部估分（不是真实考试分数）。' +
      '规则评分始终执行；配置 quality=high 时还会叠加模型阅卷意见。',
    timeoutMs: 300_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        problemSpec: specSchema('ProblemSpec（可选）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
        answerSpec: specSchema('AnswerSpec（可选）'),
        answerSpecId: idSchema('AnswerSpec id（可选）'),
        validationReport: specSchema('ValidationReport（可选；缺省会自动验证）'),
        diagramRendered: { type: 'boolean', description: '是否已经生成了图' },
        diagramRole: enumSchema('图的用途', ['none', 'auxiliary', 'final_answer', 'both'], 'none'),
        maxScore: numberSchema('满分（可选，默认按题型）', { minimum: 1, maximum: 100 }),
      },
    },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: guarded(async (args, exec) => {
      const { spec: problem } = resolveProblem(args)
      const { spec: answer } = resolveAnswer(args)
      const validation =
        args.validationReport && typeof args.validationReport === 'object'
          ? args.validationReport
          : await pipeline.validateSolution({ problemSpec: problem, answerSpec: answer, signal: exec.signal })
      const report = await pipeline.gradeSolution({
        problemSpec: problem,
        answerSpec: answer,
        validation,
        diagram: { rendered: Boolean(args.diagramRendered), role: args.diagramRole ?? 'none' },
        answerMode: args.answerMode ?? config.answerMode,
        signal: exec.signal,
      })
      return { ...report, examId: store.put('exam', report) }
    }),
  })

  tools.push({
    name: 'exam_render_answer',
    description:
      '把 ProblemSpec / AnswerSpec / ValidationReport / ExamReport 组装成面向学生的最终答案（Markdown）：题目类型、图示、规范解答、最终答案、必要的识别提醒与自检摘要。不暴露内部 JSON 与流程日志。',
    timeoutMs: 60_000,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        problemSpec: specSchema('ProblemSpec（可选）'),
        problemSpecId: idSchema('ProblemSpec id（可选）'),
        answerSpec: specSchema('AnswerSpec（可选）'),
        answerSpecId: idSchema('AnswerSpec id（可选）'),
        validationReport: specSchema('ValidationReport（可选）'),
        examReport: specSchema('ExamReport（可选）'),
        answerMode: enumSchema('答案风格', ['concise', 'exam', 'teaching'], 'exam'),
        diagramFiles: specSchema('图文件路径 {"svg":"...","png":"..."}（可选）'),
        diagramRole: enumSchema('图的用途', ['none', 'auxiliary', 'final_answer', 'both'], 'none'),
      },
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (args, value) => [{ type: 'text', text: value.markdown ?? '' }],
    },
    execute: guarded(async (args) => {
      const { renderFinalAnswer } = await import('./format.js')
      const { spec: problem } = resolveProblem(args)
      const { spec: answer } = resolveAnswer(args)
      const rendered = renderFinalAnswer({
        problem,
        diagram: {
          required: Boolean(args.diagramFiles?.svg || args.diagramFiles?.png),
          role: args.diagramRole ?? 'none',
          files: args.diagramFiles ?? null,
          summary: null,
          error: null,
        },
        answer,
        validation: args.validationReport ?? null,
        exam: args.examReport ?? null,
        answerMode: args.answerMode ?? config.answerMode,
        language: config.language,
        warnings: [],
        uncertainties: problem.uncertainties ?? [],
        status: 'ok',
      })
      return rendered
    }),
  })

  // ----------------------------------------------------------------- status

  tools.push({
    name: 'exam_engine_status',
    description:
      '诊断插件运行环境：Python 解释器与 SymPy/matplotlib 是否可用、内部调用所使用的模型是否支持图片输入、输出目录是否可写、已缓存的结构化结果数量。安装后或报错时先调用它。',
    parameters: { type: 'object', additionalProperties: false, properties: {} },
    output: { schema: { type: 'object', additionalProperties: true }, render: (args, value) => jsonRender(value) },
    execute: async () => {
      const report = { plugin: 'exam-diagram-solver', config: { ...config, pluginRoot: config.pluginRoot } }
      try {
        report.engine = await engine.status()
      } catch (error) {
        report.engine = { ok: false, error: { code: error.code ?? 'ENGINE_UNAVAILABLE', message: error.message } }
      }
      try {
        const route = await llm.readiness()
        report.model = {
          provider: route.provider,
          model: route.model,
          reasoningEffort: route.reasoningEffort ?? null,
          acceptsImages: route.acceptsImages,
          modalities: route.modalities,
          contextWindow: route.contextWindow,
        }
      } catch (error) {
        report.model = { ok: false, error: { code: error.code ?? 'LLM_UNAVAILABLE', message: error.message } }
      }
      report.artifacts = store.list().slice(-10)
      report.outputDir = config.outputDir
      return report
    },
  })

  return tools
}
