import { describeImageFile } from './paths.js'

/**
 * Resolve the pictures a call should work on.
 *
 * Two sources are supported:
 *   - explicit `imagePaths` (files on the machine),
 *   - the most recent user message in this session that carries images.
 *
 * The second one is what makes `solve_exam_image` usable with no arguments
 * right after a photo is attached in chat. The original image is passed to the
 * model as a real image block; it is never replaced by OCR text.
 */
export function createImageResolver({ ctx, config, logger }) {
  function fromPaths(paths) {
    const list = (Array.isArray(paths) ? paths : [paths]).filter(Boolean)
    const described = list.map((item) => describeImageFile(item))
    return {
      blocks: described.map((item) => ({ type: 'path', path: item.path, name: item.name, bytes: item.bytes })),
      source: 'paths',
      names: described.map((item) => item.name),
      notes: [],
    }
  }

  function fromSession(agent) {
    const sessions = ctx.get('sessions')
    const agents = ctx.get('agents')
    const target = agent ?? agents?.currentInitiator?.()
    if (!target) return { blocks: [], source: 'session', names: [], notes: ['no active agent session'] }
    const session = sessions?.get?.(target.id)
    if (!session) return { blocks: [], source: 'session', names: [], notes: ['session is not available'] }
    let messages
    try {
      messages = session.deriveMessages?.() ?? []
    } catch (error) {
      logger.warn(`cannot derive session messages: ${error.message}`)
      return { blocks: [], source: 'session', names: [], notes: [error.message] }
    }
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index]
      if (message?.role !== 'user') continue
      const content = Array.isArray(message.content) ? message.content : []
      const images = content.filter((block) => block?.type === 'image' && block?.attachment?.attachmentId)
      if (images.length) {
        return {
          blocks: images,
          source: 'session',
          names: images.map((block) => block.attachment.name ?? 'uploaded image'),
          notes: [],
        }
      }
    }
    return { blocks: [], source: 'session', names: [], notes: ['no image found in the latest user message'] }
  }

  function resolve(agent, args = {}) {
    const explicit = args.imagePaths ?? args.imagePath ?? args.images
    if (explicit && (!Array.isArray(explicit) || explicit.length > 0)) {
      const resolved = fromPaths(explicit)
      if (!resolved.blocks.length) {
        throw Object.assign(new Error('imagePaths was provided but contained no usable path'), {
          code: 'NO_IMAGES',
        })
      }
      return resolved
    }
    const resolved = fromSession(agent)
    if (!resolved.blocks.length) {
      throw Object.assign(
        new Error(
          '没有找到题目图片。请直接在对话中上传题目照片，或传入 imagePaths（本机图片的绝对路径）。' +
            (resolved.notes?.length ? `（${resolved.notes.join('；')}）` : ''),
        ),
        { code: 'NO_IMAGES' },
      )
    }
    return resolved
  }

  /**
   * Convert resolved blocks into the `images` argument of the LLM client.
   * Path blocks are read by the client and stored as Harness attachments.
   */
  function toLlmImages(resolved) {
    const images = []
    for (const block of resolved.blocks) {
      if (block.type === 'path') images.push(block.path)
      else if (block.type === 'image' && block.attachment) images.push({ type: 'image', attachment: block.attachment })
    }
    return images
  }

  return { resolve, toLlmImages, fromPaths, fromSession, maxImages: 3 }
}
