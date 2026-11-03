import test from 'node:test'
import assert from 'node:assert/strict'
import { userLocalKeysToClear, clearUserKeys } from './localDataKeys.js'

function fakeStorage(init) {
  const m = new Map(Object.entries(init))
  return { get length() { return m.size }, key: (i) => [...m.keys()][i], removeItem: (k) => m.delete(k), getItem: (k) => m.get(k) ?? null, _m: m }
}

test('사용자 값 키만 고른다', () => {
  const keys = ['liplab_listen_settings', 'liplab_learner_info:7', 'liplab_learner_info:guest', 'liplab_mouth_calibration_v2',
    'liplab_sound_condition:7', 'liplab.nonsense.ms.2026-11-03', 'liplab_talker_lessons',
    'liplab.a11y', 'liplab_mute', 'liplab_sign_intro_seen', 'liplab_listen_notice', 'liplab_usage_device_id', 'other']
  assert.deepEqual(userLocalKeysToClear(keys).sort(), [
    'liplab.nonsense.ms.2026-11-03', 'liplab_learner_info:7', 'liplab_learner_info:guest', 'liplab_listen_settings',
    'liplab_mouth_calibration_v2', 'liplab_sound_condition:7', 'liplab_talker_lessons'].sort())
})

test('로그아웃 뒤 사용자 값 키가 남지 않고 기기 설정은 남는다', () => {
  const s = fakeStorage({ liplab_listen_settings: '{}', 'liplab_learner_info:3': '{}', liplab_mouth_calibration_v2: '{}',
    'liplab.a11y': '{}', liplab_mute: '1', liplab_usage_device_id: 'x' })
  clearUserKeys(s)
  assert.deepEqual([...s._m.keys()].sort(), ['liplab.a11y', 'liplab_mute', 'liplab_usage_device_id'])
})

test('저장소가 막혀 있어도 던지지 않는다', () => {
  assert.doesNotThrow(() => clearUserKeys({ get length() { throw new Error('blocked') } }))
  assert.doesNotThrow(() => clearUserKeys(undefined))
})
