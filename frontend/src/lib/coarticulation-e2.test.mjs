import { test } from 'node:test'
import assert from 'node:assert/strict'
import { E2_CANDIDATES, COART_E2, applyCoarticulation, coartShape, coartWeight, lipEnvelope, curveLip } from './coarticulation.js'
import { VISEME_BLENDSHAPES as T, ACTIVE_MORPH_KEYS } from './visemeShapes.js'
import { TALKERS, talkerShapes } from './talkers.js'

test('E2 기본 끔, 낮은 w와 시간 곡선은 독립적이다', () => {
  assert.equal(COART_E2, null)
  assert.equal(coartWeight(null, 'low'), 0.3)
  assert.equal(coartWeight(null, 'curve'), 0.6)
  const f = [6, 4, 6, 14, 6].map(viseme => ({ viseme, duration_ms: 200 }))
  assert.equal(applyCoarticulation(f), f)
  const c = applyCoarticulation(f, true, 'both')
  assert.deepEqual(c.map(x => x.viseme), f.map(x => x.viseme))
  assert.deepEqual(c[0].coart_curve, { offset: 0, frameDuration: 200, start: 200, duration: 200, rounded: true })
  assert.equal(c[2].coart_curve.start, 200)
  assert.equal(c[4].coart_v, undefined)
  assert.equal(applyCoarticulation(f, true, 'low')[0].coart_curve, undefined)
})

test('시간 곡선: 앞 120/150ms·75% 유지·뒤 120ms 경계, 입술 외 모프 보존', () => {
  assert.equal(lipEnvelope(80, 200, 200), 0)
  assert.equal(lipEnvelope(50, 200, 200, true), 0)
  assert.equal(lipEnvelope(125, 200, 200, true), 0.5)
  assert.equal(lipEnvelope(200, 200, 200), 1)
  assert.equal(lipEnvelope(350, 200, 200), 1)
  assert.equal(lipEnvelope(410, 200, 200), 0.5)
  assert.equal(lipEnvelope(470, 200, 200), 0)
  const full = coartShape(T, 6, 4)
  const s = curveLip(T[6], full, { offset: 125, start: 200, duration: 200, rounded: true })
  assert.equal(s.jawOpen, T[6].jawOpen)
  assert.equal(s.mouthFunnel, (T[6].mouthFunnel || 0) + (full.mouthFunnel - (T[6].mouthFunnel || 0)) / 2)
})

test('E2 판별 기준 (d): curve 목표 통과, low·both 목표는 사전 탈락(부정 결과 보존)', () => {
  const classes = [1,2,3,4,5,6,7,8,9,10,11,12,13,14]
  const distance = (a,b) => Math.hypot(...ACTIVE_MORPH_KEYS.map(k => (a[k] || 0) - (b[k] || 0)))
  for (const candidate of Object.keys(E2_CANDIDATES)) {
  let min = Infinity
  for (const talker of [null, ...TALKERS]) {
    const table = talkerShapes(talker)
    for (const c of [6,7,8,10,12,13]) for (const v of [2,3,4,5]) {
      const shape = coartShape(table, c, v, coartWeight(talker, candidate))
      const ok = [6,7,8,10,v, ...(c >= 12 ? [12,13,1] : []), ...(v === 4 ? [4,9] : [])]
      const margin = Math.min(...classes.filter(x => !ok.includes(x)).map(x => distance(shape,T[x]))) - Math.min(...ok.map(x => distance(shape,T[x])))
      min = Math.min(min, margin)
    }
  }
  assert.ok(candidate === 'curve' ? min > 0 : min < 0, `${candidate}: ${min}`)
  console.log(`E2 ${candidate} (d) 최소 여백 ${min.toFixed(6)}`)
  }
})
