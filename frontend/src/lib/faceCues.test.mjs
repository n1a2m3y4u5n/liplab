// 입술 너머 얼굴 단서(축 K, 보조) 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { faceSignals, faceActivity } from './faceCues.js'

test('faceSignals: 세 신호를 0~1로 반환', () => {
  const s = faceSignals({ jawOpen: 0.5, noseSneerLeft: 0.4, noseSneerRight: 0.4, cheekPuff: 0.5 })
  for (const k of ['jaw_open', 'nasal', 'cheek_pressure']) {
    assert.ok(s[k] >= 0 && s[k] <= 1, `${k}는 0~1로 클램프`)
  }
  assert.equal(s.jaw_open, 0.5, '턱 개구도는 그대로')
})

test('faceSignals: 빈/누락 입력 방어', () => {
  const s = faceSignals(null)
  assert.deepEqual(s, { jaw_open: 0, nasal: 0, cheek_pressure: 0 }, 'null이면 전부 0')
})

test('faceSignals: 비음·볼압력이 값에 따라 커진다(클램프 상한 유지)', () => {
  const low = faceSignals({ noseSneerLeft: 0.1, noseSneerRight: 0.1 })
  const high = faceSignals({ noseSneerLeft: 0.9, noseSneerRight: 0.9 })
  assert.ok(high.nasal > low.nasal, '콧방울 움직임 클수록 nasal 커짐')
  assert.ok(high.nasal <= 1, '상한 1 유지')
})

test('faceActivity: 전체 활성도 0~1', () => {
  assert.equal(faceActivity({}), 0, '무입력은 0')
  const a = faceActivity({ jawOpen: 0.6, cheekPuff: 0.4 })
  assert.ok(a > 0 && a <= 1, '활성도는 0~1')
})
