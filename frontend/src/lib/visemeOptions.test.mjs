import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pickVisemeDistractors, shapeDistance, MIN_SHAPE_DISTANCE } from './visemeOptions.js'

const lessons = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((v) => ({ viseme_id: v }))

test('중설모음(5)이 정답이면 화면에서 거의 같은 입 안쪽 무리(6·7·8·10)는 보기로 내지 않는다', () => {
  for (let i = 0; i < 200; i++) {
    const ids = pickVisemeDistractors(5, lessons).map((l) => l.viseme_id)
    assert.equal(ids.length, 3)
    assert.ok(!ids.some((v) => [5, 6, 7, 8, 10].includes(v)), String(ids))
  }
})

test('퀴즈 정답이 되는 무리(1·2·3·4·5·9)는 모두 오답 보기를 3개 이상 가진다', () => {
  for (const t of [1, 2, 3, 4, 5, 9]) {
    const n = lessons.filter((l) => l.viseme_id !== t && shapeDistance(t, l.viseme_id) >= MIN_SHAPE_DISTANCE).length
    assert.ok(n >= 3, `${t}: ${n}`)
  }
})

test('거리는 대칭이고 뚜렷이 다른 무리는 멀다', () => {
  assert.equal(shapeDistance(5, 7), shapeDistance(7, 5))
  assert.ok(shapeDistance(5, 7) < MIN_SHAPE_DISTANCE && shapeDistance(1, 2) > 0.5 && shapeDistance(3, 4) > 0.5)
})

test('12문항에 보이는 무리 6개가 두 번씩, 연달아 같은 무리 없음', async () => {
  const { balancedTargets } = await import('./visemeOptions.js')
  const groups = [1, 2, 3, 4, 5, 9]
  for (let k = 0; k < 200; k++) {
    const seq = balancedTargets(groups, 12)
    assert.equal(seq.length, 12)
    for (const g of groups) assert.equal(seq.filter((x) => x === g).length, 2)
    for (let i = 1; i < seq.length; i++) assert.notEqual(seq[i], seq[i - 1])
  }
})

// 서버 /api/curriculum/viseme-lessons와 같은 quizzable(visibility != 'low', backend/curriculum.py)
const VISIBILITY = { 1: 'high', 2: 'high', 3: 'high', 4: 'high', 5: 'medium', 6: 'low', 7: 'low', 8: 'low', 9: 'medium', 10: 'low' }
const served = Object.entries(VISIBILITY).map(([id, v]) => ({ viseme_id: Number(id), quizzable: v !== 'low' }))
const quizzable = served.filter((l) => l.quizzable)   // VisemeLiteracy·Review.jsx가 오답 후보로 넘기는 목록
const TARGETS = [1, 2, 3, 4, 5, 9]

test('오답은 정답 모집단(1·2·3·4·5·9) 안에서만 나오고, 정답마다 보기 3개가 찬다', () => {
  assert.deepEqual(quizzable.map((l) => l.viseme_id), TARGETS)
  for (const t of TARGETS) {
    for (let i = 0; i < 200; i++) {
      const ids = pickVisemeDistractors(t, quizzable).map((l) => l.viseme_id)
      assert.equal(ids.length, 3)
      assert.ok(ids.every((v) => v !== t && TARGETS.includes(v)), `${t}: ${ids}`)
    }
  }
})

// 정답이 무리마다 고르게 나올 때, 입을 보지 않고 보기 네 개의 구성만 보고 고르는 최적 추측의 정답률(전수 계산).
// 후보 전체는 pickVisemeDistractors(t, pool, Infinity)로 얻어 실제 거리 필터를 그대로 쓴다.
function optionSetOnlyAccuracy(pool) {
  const combos = (arr, k) => (k === 0 ? [[]] : arr.flatMap((x, i) => combos(arr.slice(i + 1), k - 1).map((c) => [x, ...c])))
  const joint = new Map()   // 보기 집합 → (정답 → 확률)
  for (const t of TARGETS) {
    const cands = pickVisemeDistractors(t, pool, Infinity).map((l) => l.viseme_id)
    const cs = combos(cands, 3)
    for (const c of cs) {
      const key = [t, ...c].sort((a, b) => a - b).join(',')
      const m = joint.get(key) || new Map()
      m.set(t, (m.get(t) || 0) + 1 / TARGETS.length / cs.length)
      joint.set(key, m)
    }
  }
  let acc = 0
  for (const m of joint.values()) acc += Math.max(...m.values())
  return acc
}

test('보기 구성만으로는 답이 좁혀지지 않는다: 최적 추측이 4지선다 찬스 0.25(예전 10개 후보는 0.554)', () => {
  assert.ok(Math.abs(optionSetOnlyAccuracy(quizzable) - 0.25) < 1e-9)
  assert.ok(optionSetOnlyAccuracy(served) > 0.5)   // 퀴즈에 나오지 않는 6·7·8·10이 섞이던 예전 호출
})
