import assert from 'node:assert/strict'
import test from 'node:test'

import { extractJson } from '../../lib/llm.js'

test('plain JSON object', () => {
  assert.deepEqual(extractJson('{"a":1}'), { a: 1 })
})

test('fenced JSON is unwrapped', () => {
  assert.deepEqual(extractJson('```json\n{"a":[1,2]}\n```'), { a: [1, 2] })
})

test('leading prose is ignored', () => {
  assert.deepEqual(extractJson('这是结果：\n{"ok":true}\n希望有帮助'), { ok: true })
})

test('braces inside strings do not terminate the scan', () => {
  assert.deepEqual(extractJson('{"text":"a } b { c","n":2}'), { text: 'a } b { c', n: 2 })
})

test('arrays are supported', () => {
  assert.deepEqual(extractJson('[{"x":1},{"x":2}]'), [{ x: 1 }, { x: 2 }])
})

test('invalid payload throws', () => {
  assert.throws(() => extractJson('no json here'))
})
