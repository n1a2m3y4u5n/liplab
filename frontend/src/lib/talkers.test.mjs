import { test } from 'node:test'
import assert from 'node:assert/strict'
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS } from './visemeShapes.js'
import { transitionTime } from './visemeTiming.js'
import {
  TALKERS, TRAINING_TALKERS, HELD_OUT_TALKERS, DEFAULT_TALKER, RANGES, TALKER_BLOCK,
  scaleShape, talkerShapes, applyTalkerTiming, applyTalkerCycle, lessonTalker, talkerById, atNaturalRate, unitNoise,
} from './talkers.js'

// 판별 기준(docs/talker-variation.md 7절, 5절 결과를 본 뒤 바꾼 기준). 벡터는 아바타가 얼굴에 쓰는 모프 가중치(jawOpen = 턱 뼈 각도),
// 거리는 유클리드. 14·15는 기본 목표가 같은 빈 자세라 '쉼' 하나로 본다.
//  (a) 퀴즈 무리 1·2·3·4·5·9: 다른 모든 기본 목표보다 자기 기본 목표에 가깝다.
//  (b) 입 안쪽 무리 6·7·8·10: 가장 가까운 입 안쪽 무리 기본 목표가 가장 가까운 퀴즈 무리 기본 목표보다 가깝다(서로는 가를 수 없는 무리).
//  (c) 전환 11·12·13(engine: 받침 1·6·7에서 다음 초성 조음 위치로 가는 사이 모양, 11→1·12→6·13→7): 가장 가까운 기본 목표가 자기거나
//      잇는 무리 1·6·7. 12·13은 도착 무리 6·7이 (b)에서 서로 가를 수 없는 무리라 서로 가까운 것도 허용한다.
const CLASSES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
const QUIZ = [1, 2, 3, 4, 5, 9]
const LOW = [6, 7, 8, 10]
const ALLOWED = { 11: [11, 1, 6, 7], 12: [12, 13, 1, 6, 7], 13: [13, 12, 1, 6, 7] }
const vec = (shape) => ACTIVE_MORPH_KEYS.map((k) => shape[k] || 0)
const dist = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]))
const DEFAULTS = Object.fromEntries(CLASSES.map((v) => [v, vec(VISEME_BLENDSHAPES[v])]))

function nearest(t, set) {
  let d = Infinity
  let who = null
  for (const u of set) { const x = dist(t, DEFAULTS[u]); if (x < d) { d = x; who = u } }
  return [d, who]
}

// 입모양 v마다 {rule, margin, rival}: margin = 허용 밖 기본 목표까지의 최소 거리 − 허용 안 기본 목표까지의 최소 거리
function margins(talker) {
  return CLASSES.filter((v) => v !== 14).map((v) => {
    const t = vec(scaleShape(VISEME_BLENDSHAPES[v], talker, v))
    const ok = QUIZ.includes(v) ? [v] : LOW.includes(v) ? LOW : ALLOWED[v]
    const bad = LOW.includes(v) ? QUIZ : CLASSES.filter((u) => !ok.includes(u))
    const [dIn] = nearest(t, ok)
    const [dOut, rival] = nearest(t, bad)
    return { v, rule: QUIZ.includes(v) ? 'a' : LOW.includes(v) ? 'b' : 'c', margin: dOut - dIn, rival }
  })
}

test('판별 기준(7절): 가상 화자 6명 모두 (a)(b)(c)를 만족한다', () => {
  const worst = {}
  for (const t of TALKERS) {
    for (const m of margins(t)) {
      assert.ok(m.margin > 0, `${t.label} 입모양 ${m.v}(${m.rule})이 ${m.rival} 쪽으로 넘어갔다(여백 ${m.margin.toFixed(5)})`)
      if (!worst[m.rule] || m.margin < worst[m.rule].margin) worst[m.rule] = { ...m, talker: t.label }
    }
  }
  // 최소 여백 보고(docs/talker-variation.md 7.3절). jawOpen 0.01 = 턱 0.3°.
  for (const r of ['a', 'b', 'c']) {
    const w = worst[r]
    console.log(`(${r}) 최소 여백 ${w.margin.toFixed(4)} (${w.talker}, 입모양 ${w.v} 대 ${w.rival})`)
  }
})

test('판별 기준은 비어 있지 않다: 지시 범위를 크게 넘는 화자는 걸린다', () => {
  const extreme = { ...DEFAULT_TALKER, id: 'x', amp: 1.6, coart: 1.6, protrusion: 0.3 }
  assert.ok(margins(extreme).some((m) => m.margin <= 0))
})

test('매개변수는 지시 범위 안, 훈련 4명·검사 전용 2명, 성별·나이 표시 없음', () => {
  assert.equal(TRAINING_TALKERS.length, 4)
  assert.equal(HELD_OUT_TALKERS.length, 2)
  for (const t of TALKERS) {
    for (const [k, [lo, hi]] of Object.entries(RANGES)) {
      assert.ok(t[k] >= lo - 1e-9 && t[k] <= hi + 1e-9, `${t.id}.${k}=${t[k]} 범위 밖`)
    }
    assert.match(t.label, /^화자 \d$/)
  }
})

test('기본 화자는 지금 얼굴 그대로(모양 표·프레임이 같은 객체)', () => {
  assert.equal(talkerShapes(DEFAULT_TALKER), VISEME_BLENDSHAPES)
  assert.equal(talkerShapes(null), VISEME_BLENDSHAPES)
  const frames = [{ viseme: 1, duration_ms: 110, transition_ms: 30 }]
  assert.equal(applyTalkerTiming(frames, DEFAULT_TALKER, 5), frames)
  assert.equal(talkerById('nope'), DEFAULT_TALKER)
})

test('모양 표는 화자마다 한 번만 만든다(화면마다 새로 계산하지 않음)', () => {
  const t = TALKERS[0]
  assert.equal(talkerShapes(t), talkerShapes(t))
  // 닫는 모프(양순 폐쇄)는 바꾸지 않는다
  assert.equal(talkerShapes(t)[1].mouthClose, VISEME_BLENDSHAPES[1].mouthClose)
  assert.ok(Math.abs(talkerShapes(t)[2].jawOpen - VISEME_BLENDSHAPES[2].jawOpen * t.amp) < 1e-12)
})

test('타이밍: 속도·흔들림(±jitter 안)·결정론, 학습자 속도를 곱해도 전환이 프레임 60% 안에 끝난다', () => {
  const frames = [
    { viseme: 1, duration_ms: 110, transition_ms: 30 }, { viseme: 2, duration_ms: 180, transition_ms: 40 },
    { viseme: 7, duration_ms: 130, transition_ms: 35 }, { viseme: 12, duration_ms: 55, transition_ms: 20 },
    { viseme: 6, duration_ms: 50, transition_ms: 30 },
  ]
  for (const t of TALKERS) {
    const a = applyTalkerTiming(frames, t, 42)
    assert.deepEqual(a, applyTalkerTiming(frames, t, 42))
    a.forEach((f, i) => {
      const base = frames[i].duration_ms / t.rate
      assert.ok(Math.abs(f.duration_ms - base) <= base * t.jitter + 1, `${t.id} 프레임 ${i} 흔들림 초과`)
      for (const learner of [0.5, 0.75, 1, 1.25, 1.5, 2]) {
        const tt = transitionTime(f.transition_ms / learner, f.duration_ms / learner, 1)
        assert.ok(tt <= Math.max(16, (f.duration_ms / learner) * 0.6) + 1e-9)
      }
    })
  }
  for (let i = 0; i < 200; i++) { const u = unitNoise(7, i); assert.ok(u >= -1 && u <= 1) }
  const cyc = applyTalkerCycle([{ v: 15, ms: 250, t: 150 }, { v: 2, ms: 600 }], TALKERS[2], 1)
  assert.equal(cyc.length, 2)
  assert.equal(cyc[1].t, undefined)
})

test('레슨 화자: 다섯 레슨마다 첫 레슨은 기본 화자, 나머지에 훈련 화자 넷이 한 번씩, 검사 전용은 안 나온다', () => {
  assert.equal(TALKER_BLOCK, 5)
  for (const user of [1, 2, 99]) {
    for (let block = 0; block < 4; block++) {
      const got = Array.from({ length: 5 }, (_, i) => lessonTalker(user, 'word', block * 5 + i))
      assert.equal(got[0], DEFAULT_TALKER)
      assert.deepEqual(new Set(got.slice(1).map((t) => t.id)), new Set(TRAINING_TALKERS.map((t) => t.id)))
      assert.ok(got.every((t) => !t.heldOut))
    }
    assert.equal(lessonTalker(user, 'word', 7), lessonTalker(user, 'word', 7))
  }
})

test('검사용 1.0배 화자: 말 속도만 1로, 같은 객체를 돌려준다', () => {
  const h = HELD_OUT_TALKERS[0]
  const n = atNaturalRate(h)
  assert.equal(n.rate, 1)
  assert.equal(n.amp, h.amp)
  assert.equal(atNaturalRate(h), n)
  assert.equal(talkerShapes(n), talkerShapes(n))
})
