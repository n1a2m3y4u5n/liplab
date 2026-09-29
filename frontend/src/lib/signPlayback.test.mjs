// signPlayback 보조 함수 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { stageKey, nextIndex } from './signPlayback.js'

const zero = { type: 'sign', video_url: 'https://sldict.korean.go.kr/zero.mp4' }

test('stageKey: 같은 영상이 연달아 나와도 토큰마다 키가 달라 영상 요소를 새로 만든다', () => {
  const tokens = [zero, zero, zero, zero]   // 예전 10000 → 하나·영·영·영·영의 뒤 넷
  const keys = tokens.map((t, i) => stageKey(0, i, t))
  assert.equal(new Set(keys).size, tokens.length)
})

test('stageKey: 전체 재생을 다시 누르면 같은 위치라도 새 키', () => {
  assert.notEqual(stageKey(0, 0, zero), stageKey(1, 0, zero))
  assert.equal(stageKey(2, 3, zero), stageKey(2, 3, { ...zero }))
})

test('nextIndex: 끝까지 한 칸씩 가고 마지막에서 멈춘다', () => {
  const seen = [0]
  let i = 0
  for (;;) {
    const n = nextIndex(i, 4)
    if (n.done) { assert.equal(n.index, 3); break }
    i = n.index
    seen.push(i)
  }
  assert.deepEqual(seen, [0, 1, 2, 3])
  assert.deepEqual(nextIndex(0, 1), { index: 0, done: true })
})
