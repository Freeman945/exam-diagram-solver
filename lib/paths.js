import fs from 'node:fs'
import path from 'node:path'

/**
 * Create a directory if needed and return it. Throws a plain Error with a
 * stable message so tool execution can report a readable failure.
 */
export function ensureDir(dir) {
  try {
    fs.mkdirSync(dir, { recursive: true })
  } catch (error) {
    const wrapped = new Error(`cannot create directory ${dir}: ${error.message}`)
    wrapped.code = 'ENSURE_DIR_FAILED'
    throw wrapped
  }
  return dir
}

export function timestampCompact(date = new Date()) {
  const pad = (value, width = 2) => String(value).padStart(width, '0')
  return (
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}` +
    `-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}` +
    `-${pad(date.getMilliseconds(), 3)}`
  )
}

export function safeBasename(name, fallback = 'diagram') {
  const cleaned = String(name ?? '')
    .replace(/[^\w.\-]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return cleaned || fallback
}

export function isInside(parent, candidate) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate))
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
}

export const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif'])

export function isImagePath(candidate) {
  return IMAGE_EXTENSIONS.has(path.extname(String(candidate)).toLowerCase())
}

/**
 * Validate an image path without reading the bitmap: existence, type and size.
 * The plugin never copies or persists the user's source image.
 */
export function describeImageFile(candidate, { maxBytes = 25 * 1024 * 1024 } = {}) {
  const resolved = path.resolve(String(candidate))
  let stat
  try {
    stat = fs.statSync(resolved)
  } catch {
    throw Object.assign(new Error(`image not found: ${resolved}`), { code: 'IMAGE_NOT_FOUND' })
  }
  if (!stat.isFile()) {
    throw Object.assign(new Error(`not a file: ${resolved}`), { code: 'IMAGE_NOT_FILE' })
  }
  if (!isImagePath(resolved)) {
    throw Object.assign(new Error(`unsupported image extension: ${path.extname(resolved)}`), {
      code: 'IMAGE_UNSUPPORTED',
    })
  }
  if (stat.size > maxBytes) {
    throw Object.assign(new Error(`image is too large (${Math.round(stat.size / 1024)} KiB)`), {
      code: 'IMAGE_TOO_LARGE',
    })
  }
  return { path: resolved, bytes: stat.size, name: path.basename(resolved) }
}
