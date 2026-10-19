#!/usr/bin/env node
/**
 * Portable test runner: `node --test` glob handling differs between Node 20
 * and 22+, so discover the files here and pass them explicitly.
 */
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const DIRECTORY = path.join(ROOT, 'tests', 'node')

const files = fs
  .readdirSync(DIRECTORY)
  .filter((name) => name.endsWith('.test.mjs'))
  .sort()
  .map((name) => path.join(DIRECTORY, name))

if (files.length === 0) {
  console.error('no test files found in tests/node')
  process.exit(1)
}

console.log(`running ${files.length} test files with node ${process.version}`)
const result = spawnSync(process.execPath, ['--test', ...files], { stdio: 'inherit', cwd: ROOT })
process.exit(result.status ?? 1)
