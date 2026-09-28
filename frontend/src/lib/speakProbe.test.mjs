// speakProbe 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { withProbes, nextIndex, hasProbes, probeStatusText } from './speakProbe.js'

const items = [{ target: '마' }, { target: '바' }, { target: '파' }]
const probes = [{ target: '코', sound: 'ㅋ' }, { target: '다리', sound: 'ㄷ' }]

test('withProbes: 맨 앞 또는 지금 문항 바로 뒤에 끼우고, 다시 끼우면 예전 것을 뺀다', () => {
  assert.deepEqual(withProbes(items, probes).map((x) => x.target), ['코', '다리', '마', '바', '파'])
  const mid = withProbes(items, probes, 1)
  assert.deepEqual(mid.map((x) => x.target), ['마', '바', '코', '다리', '파'])
  assert.ok(mid[2].probe && mid[3].probe && !mid[1].probe)
  assert.deepEqual(withProbes(mid, [{ target: '콩' }], 4).map((x) => x.target), ['마', '바', '파', '콩'])
  assert.deepEqual(withProbes(mid, []).map((x) => x.target), ['마', '바', '파'])
  assert.ok(hasProbes(mid) && !hasProbes(items))
})

test('nextIndex: 끝에서 처음으로 돌고, 숙달 뒤에는 확인 낱말을 건너뛴다', () => {
  const seq = withProbes(items, probes, 0)   // 마 코 다리 바 파
  assert.equal(nextIndex(seq, 0), 1)
  assert.equal(nextIndex(seq, 0, true), 3)
  assert.equal(nextIndex(seq, 1, true), 3)
  assert.equal(nextIndex(seq, 4), 0)
  assert.equal(nextIndex([], 0), 0)
})

test('probeStatusText: 확인 중일 때만 보인다', () => {
  assert.equal(probeStatusText(null), null)
  assert.equal(probeStatusText({ carryover: false, passed: 3, tried: 3, n: 3, need: 2 }), null)
  assert.match(probeStatusText({ carryover: true, passed: 1, tried: 3, n: 3, need: 2 }), /3번 중 1번 합격/)
  assert.match(probeStatusText({ carryover: true, passed: 0, tried: 0, n: 3, need: 2 }), /아직 확인 전/)
})
