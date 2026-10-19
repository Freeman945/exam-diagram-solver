import fs from 'node:fs'
import path from 'node:path'

import { decideDiagramRequirement } from './decide.js'
import { renderFinalAnswer } from './format.js'
import { normalizeAnswerSpec, normalizeDiagramSpec, normalizeProblemSpec } from './normalize.js'
import { EngineError } from './python.js'
import { timestampCompact, safeBasename } from './paths.js'
import {
  ANSWER_SCHEMA_CARD,
  diagramPrompt,
  diagramRepairPrompt,
  examinerPrompt,
  recognitionPrompt,
  relationRepairPrompt,
  relationsPrompt,
  revisionPrompt,
  solvePrompt,
  systemPrompt,
} from './prompts.js'

/**
 * The end-to-end pipeline.
 *
 *   image -> recognize -> ProblemSpec -> decide -> DiagramSpec -> validate ->
 *   render -> solve -> AnswerSpec -> validate -> grade -> [revise -> ...] ->
 *   final markdown
 *
 * Every stage records what happened. The pipeline never claims success for a
 * step that failed: unresolved problems become `status: 'partial'` plus a
 * warning the user will see.
 */
export function createPipeline({ ctx, config, engine, llm, logger, store }) {
  const counters = { engineCalls: 0 }

  function llmBaseline() {
    const metrics = llm.metrics
    return {
      calls: metrics.calls,
      inputTokens: metrics.inputTokens,
      outputTokens: metrics.outputTokens,
      reasoningTokens: metrics.reasoningTokens,
      byPurpose: { ...metrics.byPurpose },
    }
  }

  function llmDelta(baseline) {
    const metrics = llm.metrics
    const byPurpose = {}
    for (const [purpose, count] of Object.entries(metrics.byPurpose)) {
      const delta = count - (baseline.byPurpose[purpose] ?? 0)
      if (delta > 0) byPurpose[purpose] = delta
    }
    return {
      calls: metrics.calls - baseline.calls,
      inputTokens: metrics.inputTokens - baseline.inputTokens,
      outputTokens: metrics.outputTokens - baseline.outputTokens,
      reasoningTokens: metrics.reasoningTokens - baseline.reasoningTokens,
      byPurpose,
    }
  }

  async function engineCall(op, payload, signal, timeoutMs = 180_000) {
    counters.engineCalls += 1
    return engine.run(op, payload, { signal, timeoutMs })
  }

  function nextRunId() {
    const random = Math.random().toString(36).slice(2, 7)
    return `${timestampCompact()}-${random}`
  }

  function recorder() {
    const stages = []
    return {
      stages,
      async run(name, fn) {
        const started = Date.now()
        logger.stage(name, { phase: 'start' })
        try {
          const value = await fn()
          stages.push({ name, ok: true, ms: Date.now() - started })
          logger.stage(name, { phase: 'done', ms: Date.now() - started })
          return value
        } catch (error) {
          stages.push({ name, ok: false, ms: Date.now() - started, error: String(error.message ?? error) })
          logger.stage(name, { phase: 'failed', ms: Date.now() - started, error: String(error.message ?? error) })
          throw error
        }
      },
    }
  }

  // ------------------------------------------------------------------ stages

  async function analyzeProblem({ imageBlocks, subjectHint, gradeHint, signal }) {
    await llm.readiness()
    const prompt = recognitionPrompt({ subjectHint, gradeHint, language: config.language })
    const warnings = []

    let response = await llm.json({
      system: systemPrompt('识别题目图片，产出 ProblemSpec'),
      prompt,
      images: imageBlocks,
      maxTokens: 7000,
      temperature: 0.1,
      purpose: 'recognize',
      signal,
    })
    let spec = normalizeProblemSpec(response.data, { subjectHint, gradeHint })
    let check = await engineCall('validate_spec', { kind: 'problem', spec }, signal, 60_000)

    if (!check.valid) {
      warnings.push(`识别结果结构不完整，已请求模型修正一次：${check.error_summary}`)
      response = await llm.json({
        system: systemPrompt('修正 ProblemSpec 结构'),
        prompt:
          `${prompt}\n\n上一次输出未通过结构校验：\n${check.error_summary}\n` +
          `请修正字段名与取值后重新输出完整的 ProblemSpec JSON（不要解释）。`,
        images: imageBlocks,
        maxTokens: 7000,
        temperature: 0.1,
        purpose: 'recognize_repair',
        signal,
      })
      spec = normalizeProblemSpec(response.data, { subjectHint, gradeHint })
      check = await engineCall('validate_spec', { kind: 'problem', spec }, signal, 60_000)
      if (!check.valid) {
        throw new EngineError(`题目识别结果无法通过结构校验：${check.error_summary}`, {
          code: 'RECOGNITION_INVALID',
          details: check.errors,
        })
      }
    }

    if (check.removed_top_level_keys?.length) {
      warnings.push(`识别结果中的未知字段已忽略：${check.removed_top_level_keys.join('、')}`)
    }
    return { spec: check.sanitized, warnings }
  }

  async function planDiagram({ problemSpec, decision, imageBlocks, runDir, signal }) {
    const prompt = diagramPrompt({
      problemSpec,
      diagramType: decision.diagram_type,
      role: decision.role,
      language: config.language,
    })
    const attempts = []
    let promptNext = prompt
    let diagram = null
    let report = null

    for (let attempt = 0; attempt <= config.maxDiagramRepairRounds; attempt += 1) {
      const response = await llm.json({
        system: systemPrompt('根据题目条件设计 DiagramSpec，坐标必须让几何关系成立'),
        prompt: promptNext,
        images: imageBlocks,
        maxTokens: 7000,
        temperature: 0.1,
        purpose: attempt === 0 ? 'diagram' : 'diagram_repair',
        signal,
      })
      diagram = normalizeDiagramSpec(response.data)

      try {
        report = await engineCall('validate_diagram', { diagram, problemSpec }, signal, 120_000)
      } catch (error) {
        if (error instanceof EngineError && error.code === 'invalid_diagram_spec') {
          const errors = error.details?.errors ?? []
          attempts.push({ attempt, phase: 'schema', errors })
          promptNext = diagramRepairPrompt({
            previous: diagram,
            errors: errors.length ? errors : [{ path: '$', message: error.message }],
            problemSpec,
            language: config.language,
          })
          continue
        }
        throw error
      }

      if (!report.passed) {
        attempts.push({ attempt, phase: 'relations', contradictions: report.contradictions })
        promptNext = relationRepairPrompt({
          previous: diagram,
          contradictions: report.contradictions,
          language: config.language,
        })
        continue
      }

      const basename = safeBasename(problemSpec?.problem_type ?? 'diagram')
      const rendered = await engineCall(
        'render_diagram',
        {
          diagram,
          outDir: runDir,
          basename: `${basename}-diagram`,
          width: config.diagramWidth,
          height: config.diagramHeight,
          dpi: config.dpi,
          formats: ['svg', 'png'],
        },
        signal,
        120_000,
      )
      attempts.push({ attempt, phase: 'rendered' })
      return {
        required: true,
        role: decision.role,
        type: decision.diagram_type,
        reason: decision.reason,
        applied_rules: decision.applied_rules,
        spec: diagram,
        validation: report,
        files: rendered.files,
        elements: rendered.elements,
        warnings: rendered.warnings ?? [],
        attempts,
        summary: diagram.title || `${decision.diagram_type} 图`,
        error: null,
      }
    }

    return {
      required: true,
      role: decision.role,
      type: decision.diagram_type,
      reason: decision.reason,
      applied_rules: decision.applied_rules,
      spec: diagram,
      validation: report,
      files: null,
      elements: null,
      warnings: [],
      attempts,
      summary: diagram?.title ?? null,
      error: `作图未通过校验（尝试 ${attempts.length} 次）`,
    }
  }

  async function solveProblem({ problemSpec, diagramSpec, imageBlocks, answerMode, signal }) {
    const prompt = solvePrompt({
      problemSpec,
      diagramSpec,
      answerMode,
      language: config.language,
      uncertainties: problemSpec.uncertainties,
    })
    const system = systemPrompt('给出规范、可判分的解答，并给出可机器验证的断言')

    let response = await llm.json({
      system,
      prompt,
      images: imageBlocks,
      maxTokens: 9000,
      temperature: 0.2,
      purpose: 'solve',
      signal,
    })
    let answer = normalizeAnswerSpec(response.data)
    let check = await engineCall('validate_spec', { kind: 'answer', spec: answer }, signal, 60_000)

    if (!check.valid) {
      logger.warn(`answer spec invalid, repairing once: ${check.error_summary}`)
      response = await llm.json({
        system,
        prompt:
          `${prompt}\n\n上一次输出未通过结构校验：\n${check.error_summary}\n` +
          `请修正后重新输出完整的 AnswerSpec JSON（不要解释）。\n\n${ANSWER_SCHEMA_CARD}`,
        images: imageBlocks,
        maxTokens: 9000,
        temperature: 0.2,
        purpose: 'solve_repair',
        signal,
      })
      answer = normalizeAnswerSpec(response.data)
      check = await engineCall('validate_spec', { kind: 'answer', spec: answer }, signal, 60_000)
      if (!check.valid) {
        throw new EngineError(`解答结构无法通过校验：${check.error_summary}`, {
          code: 'ANSWER_INVALID',
          details: check.errors,
        })
      }
    }
    return check.sanitized
  }

  async function validateSolution({ problemSpec, answerSpec, diagramSpec, signal }) {
    return engineCall(
      'validate_solution',
      { problemSpec, answerSpec, diagram: diagramSpec ?? undefined },
      signal,
      180_000,
    )
  }

  async function gradeSolution({ problemSpec, answerSpec, validation, diagram, answerMode, signal }) {
    const mechanical = await engineCall(
      'grade_answer',
      {
        problemSpec,
        answerSpec,
        validationReport: validation,
        diagram: { rendered: Boolean(diagram?.files), role: diagram?.role ?? 'none' },
        answerMode,
      },
      signal,
      60_000,
    )
    if (config.quality !== 'high') return mechanical

    try {
      const response = await llm.json({
        system: systemPrompt('以阅卷老师身份给出失分点与修改指令'),
        prompt: examinerPrompt({
          problemSpec,
          answerSpec,
          validationReport: validation,
          maxScore: mechanical.max_score,
          language: config.language,
        }),
        maxTokens: 4000,
        temperature: 0.1,
        purpose: 'examiner',
        signal,
      })
      return mergeExamReports(mechanical, response.data)
    } catch (error) {
      logger.warn(`model examiner unavailable, keeping the rule-based report: ${error.message}`)
      return {
        ...mechanical,
        notes: [...(mechanical.notes ?? []), '模型阅卷不可用，本次仅使用规则评分。'],
      }
    }
  }

  async function reviseAnswer({ problemSpec, answerSpec, issues, diagramSpec, answerMode, imageBlocks, signal }) {
    const response = await llm.json({
      system: systemPrompt('按问题清单修正答案，不得辩解或忽略'),
      prompt: revisionPrompt({
        problemSpec,
        answerSpec,
        issues,
        diagramSpec,
        answerMode,
        language: config.language,
      }),
      images: imageBlocks,
      maxTokens: 9000,
      temperature: 0.15,
      purpose: 'revision',
      signal,
    })
    const answer = normalizeAnswerSpec(response.data)
    const check = await engineCall('validate_spec', { kind: 'answer', spec: answer }, signal, 60_000)
    if (!check.valid) {
      throw new EngineError(`修正后的答案结构不合法：${check.error_summary}`, {
        code: 'REVISION_INVALID',
        details: check.errors,
      })
    }
    return check.sanitized
  }

  // -------------------------------------------------------------- full solve

  async function solveImage({
    imageBlocks,
    subjectHint = 'auto',
    gradeHint = 'auto',
    answerMode = config.answerMode,
    quality = config.quality,
    diagramHint = null,
    signal,
  }) {
    const runId = nextRunId()
    const runDir = engine.runDir(runId)
    const rec = recorder()
    const warnings = []
    const started = Date.now()
    const llmStart = llmBaseline()
    const engineStart = counters.engineCalls

    const { spec, warnings: recognitionWarnings } = await rec.run('recognize', () =>
      analyzeProblem({ imageBlocks, subjectHint, gradeHint, signal }),
    )
    warnings.push(...recognitionWarnings)

    const decision = decideDiagramRequirement(spec, { hint: diagramHint })
    let diagram = null
    if (decision.required) {
      try {
        diagram = await rec.run('diagram', () =>
          planDiagram({ problemSpec: spec, decision, imageBlocks, runDir, signal }),
        )
        warnings.push(...(diagram.warnings ?? []))
        if (diagram.error) {
          warnings.push(`${diagram.error}。${decision.role === 'final_answer' ? '本题要求作图，答案中的图缺失。' : '已跳过该图，继续文本解答。'}`)
        }
      } catch (error) {
        logger.warn(`diagram stage failed: ${error.message}`)
        diagram = {
          required: true,
          role: decision.role,
          type: decision.diagram_type,
          reason: decision.reason,
          spec: null,
          validation: null,
          files: null,
          error: error.message,
          warnings: [],
          attempts: [],
        }
        warnings.push(`作图失败：${error.message}`)
      }
    } else {
      diagram = {
        required: false,
        role: 'none',
        type: 'none',
        reason: decision.reason,
        applied_rules: decision.applied_rules,
        spec: null,
        validation: null,
        files: null,
        error: null,
        warnings: [],
        attempts: [],
      }
    }

    let answer = await rec.run('solve', () =>
      solveProblem({
        problemSpec: spec,
        diagramSpec: diagram?.spec ?? null,
        imageBlocks,
        answerMode,
        signal,
      }),
    )
    if (diagram?.files) answer.diagram_refs = [String(diagram.files.png ?? diagram.files.svg ?? '')].filter(Boolean)

    let validation = await rec.run('validate', () =>
      validateSolution({ problemSpec: spec, answerSpec: answer, diagramSpec: diagram?.spec, signal }),
    )
    let exam = await rec.run('grade', () =>
      gradeSolution({ problemSpec: spec, answerSpec: answer, validation, diagram, answerMode, signal }),
    )

    const maxRounds =
      quality === 'fast'
        ? 0
        : quality === 'high'
          ? config.maxRevisionRounds
          : Math.min(1, config.maxRevisionRounds)
    let revisionRounds = 0

    while (revisionRounds < maxRounds && needsRevision(validation, exam)) {
      revisionRounds += 1
      const issues = collectIssues(validation, exam)
      if (!issues.length) break
      try {
        answer = await rec.run(`revise:${revisionRounds}`, () =>
          reviseAnswer({
            problemSpec: spec,
            answerSpec: answer,
            issues,
            diagramSpec: diagram?.spec ?? null,
            answerMode,
            imageBlocks,
            signal,
          }),
        )
        validation = await rec.run(`validate:${revisionRounds}`, () =>
          validateSolution({ problemSpec: spec, answerSpec: answer, diagramSpec: diagram?.spec, signal }),
        )
        exam = await rec.run(`grade:${revisionRounds}`, () =>
          gradeSolution({ problemSpec: spec, answerSpec: answer, validation, diagram, answerMode, signal }),
        )
      } catch (error) {
        logger.warn(`revision round ${revisionRounds} failed: ${error.message}`)
        warnings.push(`第 ${revisionRounds} 轮修正未完成：${error.message}`)
        break
      }
    }

    if (!validation.passed) {
      warnings.push('程序校验仍有未通过的检查，结论需要人工核对。')
    }

    const diagramOk = !decision.required || Boolean(diagram?.files)
    const status = !answer?.final_answer ? 'failed' : diagramOk && validation.passed ? 'ok' : 'partial'

    const final = renderFinalAnswer({
      problem: spec,
      diagram,
      answer,
      validation,
      exam,
      answerMode,
      language: config.language,
      warnings,
      uncertainties: spec.uncertainties,
      status,
    })

    const metrics = {
      durationMs: Date.now() - started,
      engineCalls: counters.engineCalls - engineStart,
      llm: llmDelta(llmStart),
      stages: rec.stages,
      revisionRounds,
      diagramAttempts: diagram?.attempts?.length ?? 0,
      quality,
    }

    const result = {
      runId,
      runDir,
      status,
      answerMode,
      language: config.language,
      problem: spec,
      diagramDecision: decision,
      diagram,
      answer,
      validation,
      exam,
      final: final.markdown,
      finalAnswer: final.finalAnswer,
      warnings: [...new Set(warnings.filter(Boolean))],
      metrics,
      artifacts: {
        problemSpecId: store.put('problem', spec),
        answerSpecId: store.put('answer', answer),
        validationId: store.put('validation', validation),
        examId: store.put('exam', exam),
      },
    }

    await persistRunSummary(result, { problemSpec: spec })
    return result
  }

  async function persistRunSummary(result, { problemSpec }) {
    try {
      const summary = {
        runId: result.runId,
        status: result.status,
        answerMode: result.answerMode,
        quality: result.metrics.quality,
        durationMs: result.metrics.durationMs,
        subject: problemSpec.subject,
        problemType: problemSpec.problem_type,
        diagramType: result.diagram?.type ?? 'none',
        diagramRendered: Boolean(result.diagram?.files),
        validationPassed: result.validation?.passed,
        checks: (result.validation?.checks ?? []).length,
        failedChecks: (result.validation?.checks ?? []).filter(
          (check) => check.passed === false && check.severity === 'error',
        ).length,
        estimatedScore: result.exam?.estimated_score,
        maxScore: result.exam?.max_score,
        warnings: result.warnings.length,
        revisionRounds: result.metrics.revisionRounds,
        files: result.diagram?.files ?? null,
        llm: {
          calls: result.metrics.llm.calls,
          inputTokens: result.metrics.llm.inputTokens,
          outputTokens: result.metrics.llm.outputTokens,
        },
      }
      const record = config.logProblemText ? { ...summary, problem: problemSpec } : summary
      await fs.promises.writeFile(
        path.join(result.runDir, 'summary.json'),
        JSON.stringify(record, null, 2),
        'utf8',
      )
    } catch (error) {
      logger.warn(`could not write run summary: ${error.message}`)
    }
  }

  // ------------------------------------------------------- single-stage APIs

  async function reconstructRelations({ problemSpec, imageBlocks, signal }) {
    const prompt = relationsPrompt({ language: config.language })
    const response = await llm.json({
      system: systemPrompt('重建题目已有图形的结构关系'),
      prompt,
      images: imageBlocks,
      maxTokens: 5000,
      temperature: 0.1,
      purpose: 'reconstruct',
      signal,
    })
    const data = response.data ?? {}
    const merged = {
      ...problemSpec,
      visual_objects: Array.isArray(data.visual_objects) ? data.visual_objects : problemSpec.visual_objects,
      visual_relations: Array.isArray(data.visual_relations) ? data.visual_relations : problemSpec.visual_relations,
      uncertainties: Array.isArray(data.uncertainties) && data.uncertainties.length
        ? [...(problemSpec.uncertainties ?? []), ...data.uncertainties]
        : problemSpec.uncertainties,
      diagram_type_hint: data.diagram_type_hint ?? problemSpec.diagram_type_hint,
    }
    const normalized = normalizeProblemSpec(merged, { subjectHint: problemSpec.subject })
    const check = await engineCall('validate_spec', { kind: 'problem', spec: normalized }, signal, 60_000)
    return {
      problemSpec: check.sanitized,
      raw: data,
      valid: check.valid,
      errors: check.errors,
      problemSpecId: store.put('problem', check.sanitized),
    }
  }

  return {
    analyzeProblem,
    planDiagram,
    solveProblem,
    validateSolution,
    gradeSolution,
    reviseAnswer,
    solveImage,
    reconstructRelations,
    decideDiagramRequirement,
    engineCall,
    metrics: llm.metrics,
  }
}

function needsRevision(validation, exam) {
  if (!validation?.passed) return true
  if (!exam) return false
  if (!exam.revision_required) return false
  return (exam.lost_points ?? []).some((item) => Number(item.estimated_loss) >= 0.5)
}

function collectIssues(validation, exam) {
  const issues = [
    ...(validation?.contradictions ?? []),
    ...(validation?.recommended_revision ?? []),
    ...((exam?.lost_points ?? []).map((item) => item.fix || item.reason)),
    ...(exam?.revision_instructions ?? []),
  ]
  const seen = new Set()
  const unique = []
  for (const issue of issues) {
    const text = String(issue ?? '').trim()
    if (!text || seen.has(text)) continue
    seen.add(text)
    unique.push(text)
  }
  return unique.slice(0, 10)
}

/**
 * Merge the rule-based report with the model examiner.
 *
 * The mechanical score is authoritative: the model may add a *concrete* lost
 * point the rules missed, but it can never raise the score.
 */
export function mergeExamReports(mechanical, model) {
  if (!model || typeof model !== 'object') return mechanical
  const base = {
    ...mechanical,
    lost_points: [...(mechanical.lost_points ?? [])],
    strengths: [...(mechanical.strengths ?? [])],
    revision_instructions: [...(mechanical.revision_instructions ?? [])],
    notes: [...(mechanical.notes ?? [])],
  }
  const known = new Set(base.lost_points.map((item) => normalizeReason(item.reason)))
  for (const item of Array.isArray(model.lost_points) ? model.lost_points : []) {
    const reason = String(item?.reason ?? '').trim()
    if (!reason) continue
    const key = normalizeReason(reason)
    if ([...known].some((existing) => existing.includes(key) || key.includes(existing))) continue
    const loss = Math.max(0, Math.min(Number(item.estimated_loss) || 0, base.max_score))
    if (loss <= 0) continue
    known.add(key)
    base.lost_points.push({ reason, estimated_loss: loss, fix: String(item.fix ?? '') || undefined })
  }
  for (const strength of Array.isArray(model.strengths) ? model.strengths : []) {
    const text = String(strength ?? '').trim()
    if (text && !base.strengths.includes(text)) base.strengths.push(text)
  }
  for (const instruction of Array.isArray(model.revision_instructions) ? model.revision_instructions : []) {
    const text = String(instruction ?? '').trim()
    if (text && !base.revision_instructions.includes(text)) base.revision_instructions.push(text)
  }
  const lost = base.lost_points.reduce((total, item) => total + Number(item.estimated_loss || 0), 0)
  base.estimated_score = Math.max(0, Math.round((base.max_score - lost) * 100) / 100)
  base.score_ratio = base.max_score ? Math.round((base.estimated_score / base.max_score) * 10000) / 10000 : 0
  base.revision_required = Boolean(mechanical.revision_required || model.revision_required)
  base.source = 'internal_estimate'
  if (model.revision_required && !base.revision_instructions.length) {
    base.revision_instructions.push('按阅卷意见补充关键步骤。')
  }
  return base
}

function normalizeReason(reason) {
  return String(reason ?? '')
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[\s，。；、,:：]/g, '')
    .slice(0, 24)
}
