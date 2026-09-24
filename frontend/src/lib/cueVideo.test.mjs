// cueVideo 보조 함수 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  PACK_KIND, parsePack, syllableWindows, activeIndex, nearestSample, cueAnchor, nasalPolyline,
} from './cueVideo.js'

const syl = (t0) => ({ t0, t1: t0 + 0.02, cues: [] })

test('parsePack: 종류가 다르면 거절하고, 음절 없는 클립은 뺀다', () => {
  assert.throws(() => parsePack({ kind: 'other', clips: [] }), /묶음/)
  const p = parsePack({ kind: PACK_KIND, clips: [{ video: 'a.mp4', syllables: [syl(0.1)] }, { video: 'b.mp4', syllables: [] }] })
  assert.equal(p.clips.length, 1)
  assert.throws(() => parsePack({ kind: PACK_KIND, clips: [{ video: 'b.mp4', syllables: [] }] }), /클립/)
})

test('syllableWindows: 다음 음절 앞에서 끊고, 쉼에서는 HOLD만큼만 보인다', () => {
  const w = syllableWindows([syl(0.2), syl(0.4), syl(1.5)], 0.05, 0.35)
  assert.deepEqual(w.map((x) => [+x.start.toFixed(3), +x.end.toFixed(3)]), [[0.15, 0.35], [0.35, 0.75], [1.45, 1.85]])
})

test('activeIndex: 구간 안이면 그 음절, 쉼이면 -1', () => {
  const w = syllableWindows([syl(0.2), syl(0.4), syl(1.5)], 0.05, 0.35)
  assert.equal(activeIndex(w, 0.1), -1)
  assert.equal(activeIndex(w, 0.2), 0)
  assert.equal(activeIndex(w, 0.36), 1)
  assert.equal(activeIndex(w, 1.0), -1)
  assert.equal(activeIndex(w, 1.6), 2)
  assert.equal(activeIndex(w, 9), -1)
})

test('nearestSample·cueAnchor: 가장 가까운 입 위치 오른쪽에 기호를 둔다', () => {
  const mouth = [[0, 0.5, 0.6, 0.1], [0.033, 0.52, 0.61, 0.1], [0.067, 0.54, 0.62, 0.1]]
  assert.deepEqual(nearestSample(mouth, 0.04), mouth[1])
  assert.equal(nearestSample([], 1), null)
  const a = cueAnchor(mouth[1])
  assert.ok(Math.abs(a.x - 0.58) < 1e-9 && a.y === 0.61)
  assert.deepEqual(cueAnchor(null), { x: 0.62, y: 0.6 })
})

test('nasalPolyline: 시각과 확률을 SVG 좌표로', () => {
  assert.equal(nasalPolyline([[0, 1], [2, 0.5]], 2, 100, 40), '0.0,0.0 100.0,20.0')
  assert.equal(nasalPolyline([], 2, 100, 40), '')
})
