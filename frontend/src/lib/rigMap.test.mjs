// 음성 구동·거울 경로 리그 보정 사상(lib/rigMap, docs/viseme-calibration-2026-10.md 5절) 검사. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { RIG_MAP, RIG_MAP_INPUTS, mapRawFrame } from './rigMap.js'

const frame = (o) => ({ eyeBlinkLeft: 0.4, browInnerUp: 0.2, ...o })

test('출력은 0~1, 좌우 모프는 같은 값, 사상 밖 계수는 그대로 넘긴다', () => {
  const out = mapRawFrame(frame({ jawOpen: 0.3, mouthClose: 0.05, mouthPucker: 0.5, mouthSmileLeft: 0.2, mouthSmileRight: 0.0 }))
  for (const [k, v] of Object.entries(out)) assert.ok(v >= 0 && v <= 1, `${k}=${v}`)
  for (const k of ['mouthSmile', 'mouthStretch', 'mouthUpperUp', 'mouthLowerDown', 'mouthPress']) {
    assert.equal(out[`${k}Left`], out[`${k}Right`], k)
  }
  assert.equal(out.eyeBlinkLeft, 0.4)
  assert.equal(out.browInnerUp, 0.2)
})

test('입력 좌우를 바꿔도(거울 영상) 결과가 같다', () => {
  const a = mapRawFrame(frame({ mouthSmileLeft: 0.3, mouthSmileRight: 0.1, mouthPressLeft: 0.2 }))
  const b = mapRawFrame(frame({ mouthSmileLeft: 0.1, mouthSmileRight: 0.3, mouthPressRight: 0.2 }))
  for (const k of Object.keys(RIG_MAP)) {
    const key = ['mouthSmile', 'mouthStretch', 'mouthUpperUp', 'mouthLowerDown', 'mouthPress'].includes(k) ? `${k}Left` : k
    assert.ok(Math.abs(a[key] - b[key]) < 1e-12, k)
  }
})

test('사람 계수에서 입술을 닫고 턱을 연 모양이면 아바타 mouthClose와 턱이 함께 커진다(V13 리그 한계 보정의 방향)', () => {
  const open = mapRawFrame(frame({ jawOpen: 0.12, mouthClose: 0.0 }))
  const sealed = mapRawFrame(frame({ jawOpen: 0.12, mouthClose: 0.1 }))
  assert.ok(sealed.mouthClose > open.mouthClose + 0.05)
  assert.ok(sealed.jawOpen > open.jawOpen)
})

test('같은 원본 객체는 다시 계산하지 않고 같은 결과 객체를 돌려준다', () => {
  const f = frame({ jawOpen: 0.2 })
  assert.equal(mapRawFrame(f), mapRawFrame(f))
  assert.equal(mapRawFrame(null), null)
  assert.equal(RIG_MAP_INPUTS.length, 13)
  for (const [, [b, w]] of Object.entries(RIG_MAP)) { assert.equal(w.length, 13); assert.ok(Number.isFinite(b)) }
})
