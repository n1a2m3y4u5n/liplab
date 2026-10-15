import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { VISEME_V3_ENABLED, V3_TABLE, framesToV3Coeffs, scaleV3ForTalker, scheduleSegments } from './visemeV3.js'
import { mapRawFrame } from './rigMap.js'

const here = (p) => fileURLToPath(new URL(p, import.meta.url))
const frames = JSON.parse(readFileSync(here('../../../scripts/data/v3_selftest_frames.json'), 'utf8'))
const ref = JSON.parse(readFileSync(here('../../../scripts/data/v3_selftest_ref.json'), 'utf8'))

test('플래그는 기본으로 꺼져 있다', () => {
  assert.equal(VISEME_V3_ENABLED, false)
})

test('표는 집계 칸만 담는다(칸마다 20구간·5명 이상)', () => {
  assert.equal(V3_TABLE.min_seg, 20)
  assert.equal(V3_TABLE.min_spk, 5)
  assert.ok(Object.keys(V3_TABLE.cells).length > 100)
  for (const v of Object.values(V3_TABLE.cells)) assert.equal(v.length, 13)
})

test('파이썬 구현(scripts/v3_avatar.py)과 같은 계수를 낸다', () => {
  for (const r of ref) {
    const c = frames.find((x) => x.name === r.name)
    const out = framesToV3Coeffs(c.frames, { speed: r.speed, model: { ...V3_TABLE, seal: r.seal } })
    assert.equal(out.length, r.n, r.name)
    let worst = 0
    out.forEach((o, k) => {
      for (const [key, v] of Object.entries(r.coeffs[k])) worst = Math.max(worst, Math.abs((o[key] ?? 0) - v))
      for (const key of Object.keys(o)) if (!(key in r.coeffs[k])) worst = Math.max(worst, Math.abs(o[key]))
    })
    assert.ok(worst < 2e-4, `${r.name} seal ${r.seal}: 최대 차이 ${worst}`)
  }
})

test('일정은 renderText·LipSyncPlayer3D와 같은 길이를 쓴다', () => {
  const s = scheduleSegments([{ viseme: 2, duration_ms: 200 }, { viseme: 14, duration_ms: 100 }], 2, 400)
  assert.deepEqual(s.segs, [[2, 0.4, 0.5], [14, 0.5, 0.55]])
  assert.equal(s.end, 0.55)
})

test('양순 표시는 rigMap에서 아바타 mouthClose를 턱 쪽으로 올리고 출력에는 남지 않는다', () => {
  const f = { jawOpen: 0.3, mouthClose: 0.02, _seal: 1 }
  const out = mapRawFrame(f)
  assert.ok(out.mouthClose >= out.jawOpen - 1e-9)
  assert.equal('_seal' in out, false)
  const g = mapRawFrame({ jawOpen: 0.3, mouthClose: 0.02 })
  assert.ok(g.mouthClose < g.jawOpen)
})

test('기본 얼굴은 그대로, 가상 화자는 표 평균에서의 차이에 배율', () => {
  const c = framesToV3Coeffs(frames[0].frames)
  assert.equal(scaleV3ForTalker(c, { amp: 1, width: 1, protrusion: 1 }), c)
  const s = scaleV3ForTalker(c, { amp: 1.2, width: 1, protrusion: 1 })
  const mu = V3_TABLE.mu[0]
  const k = c.findIndex((o) => Math.abs(o.jawOpen - mu) > 0.02)
  assert.ok(Math.abs(s[k].jawOpen - mu) > Math.abs(c[k].jawOpen - mu))
  assert.equal(s[k].mouthFunnel, c[k].mouthFunnel)
})

test('문장 하나 계산은 빠르다(20ms 아래)', () => {
  const t0 = performance.now()
  for (let i = 0; i < 20; i++) framesToV3Coeffs(frames[0].frames)
  assert.ok((performance.now() - t0) / 20 < 20)
})
