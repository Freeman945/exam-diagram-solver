import fs from 'node:fs'
import path from 'node:path'

import { isImagePath } from './paths.js'

/**
 * Thin, explicit wrapper around the Harness `llm` service.
 *
 * It exists for three reasons:
 *   - every internal call must be one place, so cost and failure handling are
 *     visible;
 *   - images must be real `ImageBlock`s (native multimodal input), never OCR
 *     text substituted for the picture;
 *   - model output must be parsed as JSON, with one repair attempt, because a
 *     probe that "looked like JSON" is not a data structure.
 */

const MEDIA_TYPES = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
}

export class LlmError extends Error {
  constructor(message, { code = 'llm_error', details = null } = {}) {
    super(message)
    this.name = 'LlmError'
    this.code = code
    this.details = details
  }
}

export function createLlmClient({ ctx, config, logger }) {
  const metrics = {
    calls: 0,
    jsonCalls: 0,
    inputTokens: 0,
    outputTokens: 0,
    reasoningTokens: 0,
    byPurpose: {},
    model: null,
    provider: null,
  }
  const imageCache = new Map()

  function selection(overrides = {}) {
    const base = ctx.get('agentDefaultModel')?.currentSelection?.() ?? {}
    return {
      provider: overrides.provider || config.provider || base.provider,
      model: overrides.model || config.model || base.model,
      reasoningEffort: overrides.reasoningEffort || config.reasoningEffort || base.reasoningEffort,
    }
  }

  function requireLlm() {
    const llm = ctx.get('llm')
    if (!llm) throw new LlmError('the Harness llm service is unavailable', { code: 'LLM_UNAVAILABLE' })
    return llm
  }

  async function readiness(overrides = {}) {
    const llm = requireLlm()
    const route = selection(overrides)
    if (!route.provider || !route.model) {
      throw new LlmError('no provider/model is configured for internal calls', { code: 'LLM_NO_ROUTE' })
    }
    let info
    try {
      info = await llm.resolveModelInfo(route.provider, route.model)
    } catch (error) {
      throw new LlmError(`cannot resolve model ${route.provider}/${route.model}: ${error.message}`, {
        code: 'LLM_MODEL_UNRESOLVED',
      })
    }
    const modalities = info.inputModalities ?? ['text']
    return {
      ...route,
      modalities,
      acceptsImages: modalities.includes('image'),
      contextWindow: info.context?.contextWindow ?? null,
    }
  }

  async function prepareImages(images) {
    const attachments = ctx.get('attachments')
    const blocks = []
    for (const item of images ?? []) {
      if (!item) continue
      if (typeof item === 'object' && item.type === 'image' && item.attachment?.attachmentId) {
        blocks.push({ type: 'image', attachment: item.attachment })
        continue
      }
      const filePath = typeof item === 'string' ? item : item.path
      if (!filePath) continue
      const resolved = path.resolve(filePath)
      if (!isImagePath(resolved)) {
        throw new LlmError(`unsupported image file: ${resolved}`, { code: 'LLM_UNSUPPORTED_IMAGE' })
      }
      const cacheKey = `${resolved}:${fs.statSync(resolved).mtimeMs}`
      if (imageCache.has(cacheKey)) {
        blocks.push({ type: 'image', attachment: imageCache.get(cacheKey) })
        continue
      }
      if (!attachments?.saveImage) {
        throw new LlmError('image attachments are unavailable in this Harness build', { code: 'LLM_NO_ATTACHMENTS' })
      }
      let data
      try {
        data = fs.readFileSync(resolved)
      } catch (error) {
        throw new LlmError(`cannot read image ${resolved}: ${error.message}`, { code: 'IMAGE_READ_FAILED' })
      }
      const mediaType = MEDIA_TYPES[path.extname(resolved).toLowerCase()] ?? 'image/png'
      let ref
      try {
        ref = await attachments.saveImage({ data: new Uint8Array(data), mediaType, name: path.basename(resolved) })
      } catch (error) {
        throw new LlmError(`cannot attach image ${resolved}: ${error.message}`, { code: 'IMAGE_ATTACH_FAILED' })
      }
      imageCache.set(cacheKey, ref)
      blocks.push({ type: 'image', attachment: ref })
    }
    return blocks
  }

  function buildMessages({ prompt, images }) {
    const content = [{ type: 'text', text: prompt }]
    for (const block of images) content.push(block)
    return [{ role: 'user', content }]
  }

  /**
   * One streamed completion. Returns the assistant text plus finish metadata.
   */
  async function complete({ system, prompt, images = [], route = null, maxTokens = 4096, temperature = 0.2, purpose = 'unknown', signal }) {
    const llm = requireLlm()
    const resolvedRoute = route ?? (await readiness())
    const imageBlocks = await prepareImages(images)
    if (imageBlocks.length > 0 && !resolvedRoute.acceptsImages) {
      throw new LlmError(
        `model ${resolvedRoute.provider}/${resolvedRoute.model} does not accept image input, but this step needs the original picture`,
        { code: 'LLM_NO_VISION' },
      )
    }

    const request = {
      provider: resolvedRoute.provider,
      model: resolvedRoute.model,
      messages: buildMessages({ prompt, images: imageBlocks }),
      maxTokens,
      temperature,
      signal,
    }
    if (system) request.system = system
    if (resolvedRoute.reasoningEffort) request.reasoningEffort = resolvedRoute.reasoningEffort

    let deltaText = ''
    let blockText = ''
    let finish = null
    const started = Date.now()
    for await (const chunk of llm.stream(request)) {
      if (chunk.type === 'text-delta') deltaText += chunk.text
      else if (chunk.type === 'block-end' && chunk.block?.type === 'text') blockText += chunk.block.text
      else if (chunk.type === 'usage') {
        metrics.inputTokens += chunk.usage?.inputTokens ?? 0
        metrics.outputTokens += chunk.usage?.outputTokens ?? 0
        metrics.reasoningTokens += chunk.usage?.reasoningTokens ?? 0
      } else if (chunk.type === 'finish') finish = chunk.reason
    }

    metrics.calls += 1
    metrics.model = resolvedRoute.model
    metrics.provider = resolvedRoute.provider
    metrics.byPurpose[purpose] = (metrics.byPurpose[purpose] ?? 0) + 1

    const text = (blockText || deltaText).trim()
    if (finish?.kind === 'error') {
      throw new LlmError(`model call failed (${purpose}): ${finish.failure?.message ?? 'unknown failure'}`, {
        code: 'LLM_CALL_FAILED',
        details: finish.failure,
      })
    }
    if (finish?.kind === 'max-tokens') {
      logger.warn(`model output hit maxTokens during ${purpose}; JSON may be truncated`)
    }
    if (!text) {
      if (finish?.kind === 'max-tokens') {
        throw new LlmError(
          `model hit the ${maxTokens}-token output limit before producing an answer (${purpose}); reasoning consumed the budget`,
          { code: 'LLM_TRUNCATED' },
        )
      }
      throw new LlmError(`model returned an empty response (${purpose})`, { code: 'LLM_EMPTY' })
    }
    logger.stage(`llm:${purpose}`, {
      ms: Date.now() - started,
      chars: text.length,
      images: imageBlocks.length,
      model: resolvedRoute.model,
      finish: finish?.kind ?? 'unknown',
    })
    return { text, finish: finish?.kind ?? 'unknown' }
  }

  /**
   * Ask for JSON and return the parsed value. A single retry is issued when
   * the first response is not usable JSON - models occasionally wrap JSON in
   * prose even when told not to.
   */
  async function json({ system, prompt, images = [], route = null, maxTokens = 4096, temperature = 0.15, purpose = 'json', signal, attempts = 2 }) {
    let lastError = null
    let currentPrompt = prompt
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const { text } = await complete({
        system,
        prompt: currentPrompt,
        images,
        route,
        maxTokens,
        temperature,
        purpose,
        signal,
      })
      try {
        const parsed = extractJson(text)
        metrics.jsonCalls += 1
        return { data: parsed, raw: text, attempts: attempt }
      } catch (error) {
        lastError = error
        logger.warn(`JSON parse failed on attempt ${attempt} for ${purpose}: ${error.message}`)
        currentPrompt =
          `${prompt}\n\n` +
          `Your previous reply could not be parsed as JSON (${error.message}).\n` +
          `Reply again with ONLY one valid JSON value - no prose, no markdown fences, no comments.\n` +
          `Previous reply (truncated):\n${text.slice(0, 1200)}`
      }
    }
    throw new LlmError(`model did not return valid JSON for ${purpose}: ${lastError?.message ?? 'unknown'}`, {
      code: 'LLM_INVALID_JSON',
    })
  }

  return { readiness, complete, json, metrics, prepareImages, selection }
}

/**
 * Extract the first complete JSON object/array from a model response.
 * Handles code fences, leading prose and trailing commentary.
 */
export function extractJson(text) {
  if (typeof text !== 'string' || !text.trim()) throw new Error('empty response')
  let cleaned = text.trim().replace(/^\uFEFF/, '')
  const fence = cleaned.match(/```(?:json|JSON)?\s*([\s\S]*?)```/)
  if (fence) cleaned = fence[1].trim()
  try {
    return JSON.parse(cleaned)
  } catch {
    // fall through to structural scan
  }
  const start = cleaned.search(/[[{]/)
  if (start < 0) throw new Error('no JSON object found')
  const opening = cleaned[start]
  const closing = opening === '{' ? '}' : ']'
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = start; index < cleaned.length; index += 1) {
    const char = cleaned[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') {
      inString = true
      continue
    }
    if (char === opening) depth += 1
    else if (char === closing) {
      depth -= 1
      if (depth === 0) {
        const candidate = cleaned.slice(start, index + 1)
        try {
          return JSON.parse(candidate)
        } catch (error) {
          throw new Error(`malformed JSON: ${error.message}`)
        }
      }
    }
  }
  throw new Error('unterminated JSON value')
}
