import test from 'node:test'
import assert from 'node:assert/strict'
import { compareLockToInstalled } from './check_node_lock.mjs'

const lock = { packages: { '': {}, 'node_modules/vite': { version: '6.4.5' }, 'node_modules/react': { version: '19.2.4' },
  'node_modules/@esbuild/win32-x64': { version: '0.25.0', optional: true } } }

test('같은 판이면 어긋남 없음, 선택 의존 미설치는 정상', () => {
  const have = { 'node_modules/vite': '6.4.5', 'node_modules/react': '19.2.4' }
  assert.deepEqual(compareLockToInstalled(lock, (k) => have[k] ?? null), [])
})
test('판이 다르면 알려 준다', () => {
  const have = { 'node_modules/vite': '5.4.21', 'node_modules/react': '19.2.4' }
  assert.deepEqual(compareLockToInstalled(lock, (k) => have[k] ?? null), [{ name: 'vite', lock: '6.4.5', installed: '5.4.21' }])
})
test('필수 패키지가 없으면 실패', () => {
  const have = { 'node_modules/vite': '6.4.5' }
  assert.equal(compareLockToInstalled(lock, (k) => have[k] ?? null).length, 1)
})
