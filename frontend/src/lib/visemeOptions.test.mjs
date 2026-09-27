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
