import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  AX_ONSETS, AX_VOWELS, AX_CONSONANT_CONTEXT, AX_VOWEL_CONTEXT, AX_EXCLUDED_GROUP_PAIRS, AX_INSIDE, AX_PAIRS,
  AX_SAME_MAX_DIST, AX_DIFF_MIN_DIST, axPair, axCandidates, ambiguousGroups, groupDistanceRange, pickAxItems, axSlots, axExplain, axFrames,
} from './visemeAx.js'

// 결정론적 난수(mulberry32)
function rng(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

test('정답은 무리 소속: 바/마 같음, 바/아 다름, 다/가 같음(입 안쪽), 다/바 다름, 오/우 같음, 아/이 다름', () => {
  const key = (a, b) => axPair(a, b)?.same
  assert.equal(key('바', '마'), true)
  assert.equal(key('바', '아'), false)
  assert.equal(key('다', '가'), true)
  assert.equal(key('다', '바'), false)
  assert.equal(key('오', '우'), true)
  assert.equal(key('아', '이'), false)
  assert.equal(axPair('다', '가').inside, true)
  assert.equal(axPair('바', '마').inside, false)
  assert.deepEqual(axPair('마', '바'), { ...axPair('바', '마'), a: '마', b: '바', groups: [1, 1] })   // 순서만 바뀜
})

test('제외 목록은 화자 7명(기본 + 가상 6) 거리로 다시 계산한 것과 같다', () => {
  const groups = new Set()
  for (const [g] of Object.values(AX_ONSETS)) groups.add(g)
  const vowelGroups = new Set(Object.values(AX_VOWELS).map(([g]) => g))
  const key = (a, b) => [a, b].map((g) => (g == null ? 'n' : g)).sort().join('|')
  const got = new Set()
  for (const set of [groups, vowelGroups]) {
    const gs = [...set]
    for (let i = 0; i < gs.length; i++) for (let j = i + 1; j < gs.length; j++) if (ambiguousGroups(gs[i], gs[j])) got.add(key(gs[i], gs[j]))
  }
  assert.deepEqual([...got].sort(), AX_EXCLUDED_GROUP_PAIRS.map(([a, b]) => key(a, b)).sort())
  // 경구개 10 대 6·7·8은 입 안쪽 무리라도 0.22~0.29로 멀어 뺀다
  const [lo] = groupDistanceRange(10, 7)
  assert.ok(lo >= AX_SAME_MAX_DIST && lo < 0.3, String(lo))
})

test('낼 수 있는 짝은 모든 화자에서 같음이면 0.2 미만, 다름이면 0.3 이상이고 같음 짝은 엔진 길이 차 10ms 이하', () => {
  for (const p of AX_PAIRS) {
    const [lo, hi] = groupDistanceRange(p.groups[0], p.groups[1])
    if (p.same) assert.ok(p.groups[0] === p.groups[1] || hi < AX_SAME_MAX_DIST, `${p.a}/${p.b} ${hi}`)
    else assert.ok(lo >= AX_DIFF_MIN_DIST, `${p.a}/${p.b} ${lo}`)
  }
  assert.equal(axPair('자', '차'), null)   // 110 대 150ms: 모양이 아니라 길이로 갈린다
  assert.equal(axPair('아', '애'), null)   // 180 대 150ms
  assert.equal(axPair('다', '자'), null)   // 경구개 대 치경
  assert.equal(axPair('다', '아'), null)   // 입 안쪽 대 첫소리 없음(0.22~0.32)
  assert.equal(axPair('아', '어'), null)   // 모음 2 대 5(0.28~0.41)
  assert.equal(axPair('와', '오'), null)   // 이중모음은 쓰지 않는다
  assert.equal(axPair('밥', '맙'), null)   // 받침
  assert.equal(axPair('다', '고'), null)   // 두 자리가 다름
})

test('짝 목록의 네 칸(입 안쪽·보이는 × 같음·다름)이 모두 차 있고 입 안쪽 다름은 늘 입술 닫힘과의 짝', () => {
  for (const inside of [true, false]) for (const same of [true, false]) {
    assert.ok(AX_PAIRS.some((p) => p.inside === inside && p.same === same), `${inside} ${same}`)
  }
  for (const p of AX_PAIRS.filter((x) => x.inside && !x.same)) assert.ok(p.groups.includes(1), `${p.a}/${p.b}`)
  assert.equal(axCandidates().length, 78 * AX_CONSONANT_CONTEXT.length + 28 * AX_VOWEL_CONTEXT.length)
})

test('레슨마다 AX 2개: 입 안쪽 1·보이는 1, 번호는 7~12 가운데 서로 다른 둘', () => {
  const r = rng(7)
  let same = 0
  for (let k = 0; k < 500; k++) {
    const items = pickAxItems(r)
    assert.equal(items.length, 2)
    assert.equal(items.filter((p) => p.inside).length, 1)
    for (const p of items) {
      assert.deepEqual(axPair(p.a, p.b), p)   // 뒤집은 짝도 서버 규칙과 같은 판정
      same += p.same ? 1 : 0
    }
    const slots = [...axSlots(12, 6, 2, r)]
    assert.equal(slots.length, 2)
    assert.ok(slots.every((q) => q >= 7 && q <= 12))
  }
  assert.ok(same > 400 && same < 600, String(same))   // 같음·다름 반반
})

test('설명 문구: 입 안쪽 같음은 같아 보이는 무리 설명, 입 안쪽 다름은 입술 닫힘 쪽을 짚는다', () => {
  assert.equal(axExplain(axPair('다', '가')), '두 소리는 입 안에서 나서 입모양이 거의 같아요. 문맥으로 가려요.')
  assert.equal(axExplain(axPair('바', '다')), '「바」는 입술이 닫혀 보이고, 「다」는 입 안에서 나서 입모양이 거의 없어요.')
  assert.equal(axExplain(axPair('다', '바')), '「바」는 입술이 닫혀 보이고, 「다」는 입 안에서 나서 입모양이 거의 없어요.')
  assert.equal(axExplain(axPair('아', '이')), '입모양이 달라요. 「아」 입 크게 벌림, 「이」 입 옆으로 당김.')
  assert.equal(axExplain(axPair('아', '바')), '입모양이 달라요. 「아」 입술 안 닫힘, 「바」 입술 닫힘.')
  assert.match(axExplain(axPair('오', '우')), /입모양이 같아요/)
  for (const p of AX_PAIRS) assert.ok(axExplain(p).length > 0)
  assert.ok(!AX_INSIDE.has(1))
})

test('두 음절 프레임 사이에 중립 쉼을 넣는다', () => {
  const f = axFrames([{ viseme: 1, duration_ms: 110 }, { viseme: 2, duration_ms: 180 }], [{ viseme: 2, duration_ms: 180 }])
  assert.deepEqual(f.map((x) => x.viseme), [1, 2, 15, 2])
})
