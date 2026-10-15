import test from 'node:test'
import assert from 'node:assert/strict'
import { lipreadCheckMode, lipreadCheckVisible, lipreadCheckCopy } from './lipreadGate.js'

test('기본값은 지금과 같다(on, 보임, 실험 꼬리표)', () => {
  assert.equal(lipreadCheckMode({}), 'on')
  assert.equal(lipreadCheckVisible({}), true)
  assert.equal(lipreadCheckCopy({}).tag, '(축 D · 실험)')
})

test('research는 연구 빌드에서만 보이고 문구가 바뀐다', () => {
  assert.equal(lipreadCheckVisible({ VITE_LIPREAD_CHECK: 'research' }), false)
  assert.equal(lipreadCheckVisible({ VITE_LIPREAD_CHECK: 'research', VITE_LIPLAB_RESEARCH: '1' }), true)
  assert.equal(lipreadCheckCopy({ VITE_LIPREAD_CHECK: 'research' }).tag, '(연구 기능)')
})

test('off는 숨기고 모르는 값은 on', () => {
  assert.equal(lipreadCheckVisible({ VITE_LIPREAD_CHECK: 'off', VITE_LIPLAB_RESEARCH: '1' }), false)
  assert.equal(lipreadCheckMode({ VITE_LIPREAD_CHECK: 'yes' }), 'on')
})
