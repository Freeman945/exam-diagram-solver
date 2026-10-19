/**
 * In-memory artifact store shared by the stage tools.
 *
 * Passing a 10 KB ProblemSpec back through the model on every tool call wastes
 * context and invites transcription errors, so each stage returns a short id
 * and later stages accept either the id or the inline object.
 */
export function createArtifactStore({ limit = 80 } = {}) {
  const items = new Map()
  let counter = 0

  function prune() {
    while (items.size > limit) {
      const oldest = items.keys().next().value
      items.delete(oldest)
    }
  }

  return {
    put(kind, value) {
      counter += 1
      const id = `${kind}_${counter}`
      items.set(id, { id, kind, value, at: Date.now() })
      prune()
      return id
    },
    get(id) {
      if (typeof id !== 'string') return null
      return items.get(id)?.value ?? null
    },
    getEntry(id) {
      return items.get(id) ?? null
    },
    latest(kind) {
      let found = null
      for (const entry of items.values()) {
        if (entry.kind === kind) found = entry
      }
      return found
    },
    list() {
      return [...items.values()].map(({ id, kind, at }) => ({ id, kind, at }))
    },
    clear() {
      items.clear()
    },
    get size() {
      return items.size
    },
  }
}
