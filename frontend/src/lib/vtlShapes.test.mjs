// vtlShapes 조회·그리기 보조 검사. 실제 자산(public/vtl/*.json, scripts/vtl_build_assets.py 결과)과
// 손으로 만든 작은 격자 두 가지로 확인한다. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  bark, warpToVtl, rankStates, nearestGridState, estimateOutline, blendOutlines,
  phonemeById, segment, tonguePolygon, centroid, velicPort, toPoints, VISEME_TO_VTL, VOWEL_IDS, VISEME_GROUP_VTL,
} from './vtlShapes.js'

const load = (name) => JSON.parse(readFileSync(new URL(`../../public/vtl/${name}`, import.meta.url), 'utf8'))
const grid = load('vowel_grid.json')
const shapes = load('shapes.json')
const ko = grid.vowels.map((v) => v.ko)

test('bark: 단조 증가, 1 kHz 근처 약 8.5 Bark', () => {
  assert.ok(Math.abs(bark(1000) - 8.53) < 0.02)
  assert.ok(bark(300) < bark(1000) && bark(1000) < bark(2500))
})

test('자산 구조: 모든 상태와 음소의 폴리라인 점 수가 같다', () => {
  const lens = shapes.phonemes[0].o.map((p) => p.length)
  assert.equal(lens.length, shapes.parts.length)
  for (const p of shapes.phonemes) assert.deepEqual(p.o.map((q) => q.length), lens, p.id)
  for (const s of grid.states) assert.deepEqual(s.o.map((q) => q.length), lens)
  assert.deepEqual(grid.parts, shapes.parts)
  assert.equal(grid.vowels.length, 8)
  assert.deepEqual(new Set(grid.states.map((s) => s.r)), new Set([0, 1]))
})

test('비심·모음 대응의 음소 id가 모두 shapes.json에 있다', () => {
  for (const id of Object.values(VISEME_TO_VTL)) assert.ok(phonemeById(shapes, id), id)
  for (const g of Object.values(VISEME_GROUP_VTL)) for (const id of g.ids) assert.ok(phonemeById(shapes, id), id)
  // 비음 짝은 연구개가 열려 있고 구강음은 닫혀 있다(설명과 형상이 맞는지)
  for (const [oral, nasal] of [['b', 'm'], ['d', 'n'], ['g', 'ng']]) {
    assert.equal(phonemeById(shapes, oral).velum, 0)
    assert.ok(phonemeById(shapes, nasal).velum > 0.5)
  }
  for (const [k, id] of Object.entries(VOWEL_IDS)) {
    const p = phonemeById(shapes, id)
    assert.equal(p.ko, k)
    assert.equal(p.kind, 'vowel')
  }
})

test('warpToVtl: 목표 모음 위에서는 그 모음의 VTL 포먼트(Bark)로 정확히 옮긴다', () => {
  for (const v of grid.vowels) {
    const [z1, z2] = warpToVtl(grid, v.target[0], v.target[1])
    assert.ok(Math.abs(z1 - bark(v.vtl[0])) < 1e-9 && Math.abs(z2 - bark(v.vtl[1])) < 1e-9, v.ko)
  }
})

test('nearestGridState: 목표 모음 위(제 원순 층)에서는 그 모음 꼭짓점 상태를 고른다', () => {
  for (const v of grid.vowels) {
    const hit = nearestGridState(grid, v.target[0], v.target[1], { round: v.round })
    assert.ok(hit.distance < 1e-9, `${v.ko} ${hit.distance}`)
    assert.deepEqual(hit.state.w, [[ko.indexOf(v.ko), 1]], v.ko)
    assert.equal(hit.state.r, v.round)
    const p = phonemeById(shapes, v.id)
    assert.deepEqual(hit.outline, p.o, `${v.ko} 꼭짓점 윤곽 = shapes.json 모음 윤곽`)
  }
})

test('normalize=false: 입력 Hz를 VTL 포먼트와 그대로 비교한다', () => {
  for (const v of grid.vowels) {
    const hit = nearestGridState(grid, v.vtl[0], v.vtl[1], { round: v.round, normalize: false })
    assert.ok(hit.distance < 0.02, v.ko)
  }
  // 목표값을 그대로 넣으면 꼭짓점이 아닌 상태가 더 가까운 모음이 있다(옮김이 필요한 이유).
  const off = grid.vowels.filter((v) => {
    const hit = nearestGridState(grid, v.target[0], v.target[1], { round: v.round, normalize: false })
    return !(hit.state.w.length === 1 && hit.state.w[0][0] === ko.indexOf(v.ko))
  })
  assert.ok(off.length >= 1)
})

test('rankStates: 거리는 Bark 유클리드, 오름차순', () => {
  const r = rankStates(grid, 500, 1500, { layer: 0 })
  assert.ok(r.every((x) => x.state.r === 0))
  for (let i = 1; i < r.length; i += 1) assert.ok(r[i - 1].distance <= r[i].distance)
  const [q1, q2] = warpToVtl(grid, 500, 1500)
  const s = r[0].state
  assert.ok(Math.abs(r[0].distance - Math.hypot(q1 - bark(s.f[0]), q2 - bark(s.f[1]))) < 1e-12)
})

test('입술 층: 같은 포먼트라도 round에 따라 입술 층이 바뀐다', () => {
  const u = grid.vowels.find((v) => v.ko === 'ㅜ')
  assert.equal(nearestGridState(grid, u.target[0], u.target[1], { round: 1 }).state.r, 1)
  assert.equal(nearestGridState(grid, u.target[0], u.target[1], { round: 0 }).state.r, 0)
  assert.equal(nearestGridState(grid, u.target[0], u.target[1], { round: 0.7 }).state.r, 1)
})

test('estimateOutline: 꼭짓점에서는 그 윤곽, round 0.5는 두 층 결과의 평균', () => {
  const a = grid.vowels.find((v) => v.ko === 'ㅏ')
  const est = estimateOutline(grid, a.target[0], a.target[1], { round: 0 })
  assert.deepEqual(est.outline, phonemeById(shapes, 'a').o)
  const e0 = estimateOutline(grid, 480, 1500, { round: 0 })
  const e1 = estimateOutline(grid, 480, 1500, { round: 1 })
  const eh = estimateOutline(grid, 480, 1500, { round: 0.5 })
  for (let k = 0; k < eh.outline.length; k += 1) {
    for (let j = 0; j < eh.outline[k].length; j += 1) {
      assert.ok(Math.abs(eh.outline[k][j] - (e0.outline[k][j] + e1.outline[k][j]) / 2) < 1e-9)
    }
  }
  // 둥글림 층은 입술이 앞으로 나온다(윗입술 끝 x가 더 크다)
  const tip = (o) => { const s = segment(grid, o, 'upperLip'); return Math.max(...s.filter((_, i) => i % 2 === 0)) }
  assert.ok(tip(e1.outline) > tip(e0.outline) + 20)
  assert.equal(estimateOutline(grid, NaN, 1500), null)
})

test('estimateOutline: 격자 사이에서 연속적으로 변한다(작은 이동 → 작은 윤곽 변화)', () => {
  const maxDiff = (p, q) => Math.max(...p.flatMap((poly, k) => poly.map((v, j) => Math.abs(v - q[k][j]))))
  const a = estimateOutline(grid, 520, 1600, { round: 0 }).outline
  const b = estimateOutline(grid, 525, 1610, { round: 0 }).outline
  const far = estimateOutline(grid, 300, 2300, { round: 0 }).outline
  assert.ok(maxDiff(a, b) < 40, `작은 이동 ${maxDiff(a, b)}`)    // 0.4 cm 미만
  assert.ok(maxDiff(a, far) > maxDiff(a, b))
})

test('blendOutlines: 무게 정규화, 빈 입력은 null', () => {
  const o1 = [[0, 0, 10, 10]]
  const o2 = [[10, 10, 20, 30]]
  assert.deepEqual(blendOutlines([o1, o2], [1, 3]), [[7.5, 7.5, 17.5, 25]])
  assert.equal(blendOutlines([], []), null)
})

test('ㅁ과 ㅂ은 연구개(목젖) 말고는 윤곽이 같다', () => {
  const b = phonemeById(shapes, 'b')
  const m = phonemeById(shapes, 'm')
  assert.equal(b.velum, 0)
  assert.ok(m.velum > 0.5)
  assert.ok(m.nasal && !b.nasal)
  const changed = (name) => {
    const k = shapes.parts.indexOf(name)
    return b.o[k].some((v, j) => v !== m.o[k][j])
  }
  assert.ok(changed('uvula'))
  for (const name of ['tongue', 'lower', 'larynx', 'epiglottis']) assert.ok(!changed(name), name)
  // 윗윤곽은 연구개 구간(점 0~6)만, 인두 뒷벽은 연구개에 닿는 맨 윗점만 다르다.
  const up = shapes.parts.indexOf('upper')
  const velumEnd = shapes.segments.velum[2]
  assert.deepEqual(b.o[up].slice((velumEnd + 1) * 2), m.o[up].slice((velumEnd + 1) * 2))
  const wall = shapes.parts.indexOf('wall')
  assert.deepEqual(b.o[wall].slice(0, -2), m.o[wall].slice(0, -2))
  assert.deepEqual(segment(shapes, b.o, 'upperLip'), segment(shapes, m.o, 'upperLip'))
  // 경구개 구간의 첫 점은 연구개와 이어지는 자리라 함께 움직인다. 그 뒤는 같다.
  assert.deepEqual(segment(shapes, b.o, 'palate').slice(2), segment(shapes, m.o, 'palate').slice(2))
  // 연구개 통로 위치는 목젖이 내려간 ㅁ에서 더 앞(목젖이 뒷벽에서 떨어짐)이다
  assert.ok(velicPort(shapes, m.o)[0] > velicPort(shapes, b.o)[0])
})

test('tonguePolygon·centroid: 혀 도형이 닫히고 중심이 혀 윤곽 범위 안에 있다', () => {
  for (const id of ['i', 'a', 'u', 'eu', 'g', 'd']) {
    const o = phonemeById(shapes, id).o
    const poly = tonguePolygon(shapes, o)
    const t = o[shapes.parts.indexOf('tongue')]
    assert.equal(poly[poly.length - 2], t[0])   // 혀뿌리로 돌아온다
    assert.equal(poly[poly.length - 1], t[1])
    const [cx, cy] = centroid(poly)
    const xs = t.filter((_, i) => i % 2 === 0)
    const ys = t.filter((_, i) => i % 2 === 1)
    assert.ok(cx > Math.min(...xs) && cx < Math.max(...xs), id)
    assert.ok(cy > Math.min(...ys) - 1 && cy < Math.max(...ys) + 200, id)
  }
  assert.deepEqual(centroid([0, 0, 2, 0, 2, 2, 0, 2]), [1, 1])
})

test('toPoints: 소수 한 자리 좌표쌍', () => {
  assert.equal(toPoints([1, 2, 3.25, 4]), '1.0,2.0 3.3,4.0')
})

test('작은 합성 격자: 옮김·층 선택·동률 처리', () => {
  const tiny = {
    vowels: [
      { ko: 'A', target: [300, 2000], vtl: [250, 1900], round: 0 },
      { ko: 'B', target: [700, 1200], vtl: [650, 1100], round: 0 },
    ],
    states: [
      { f: [250, 1900, 2500], r: 0, w: [[0, 1]], o: [[0, 0]] },
      { f: [650, 1100, 2500], r: 0, w: [[1, 1]], o: [[10, 10]] },
      { f: [250, 1500, 2500], r: 1, w: [[0, 1]], o: [[5, 0]] },
    ],
  }
  assert.deepEqual(nearestGridState(tiny, 300, 2000, { round: 0 }).state.w, [[0, 1]])
  assert.deepEqual(nearestGridState(tiny, 700, 1200, { round: 0 }).state.w, [[1, 1]])
  assert.equal(nearestGridState(tiny, 300, 2000, { round: 1 }).state.r, 1)
  // 두 모음 사이 옮김은 두 변위 사이에 있다
  const [z1] = warpToVtl(tiny, 500, 1600)
  const dA = bark(250) - bark(300)
  const dB = bark(650) - bark(700)
  assert.ok(z1 > bark(500) + Math.min(dA, dB) && z1 < bark(500) + Math.max(dA, dB))
  const est = estimateOutline(tiny, 300, 2000, { round: 0 })
  assert.deepEqual(est.outline, [[0, 0]])
})
