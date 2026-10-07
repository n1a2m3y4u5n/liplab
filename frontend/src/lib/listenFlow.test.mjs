import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  pct, skippedNote, completeActions, practiceQuery, practiceTask, normalizeStair, modeAvailability, blockData, todayTotals, fmtMinutes,
  lipDiffers, alternate, listenOverview, lingNotes, stairPoints, PRACTICE_MODES,
} from './listenFlow.js'

const params = (o) => new URLSearchParams(o)

test('정답률·넘긴 문항 문구', () => {
  assert.equal(pct(3, 4), '75%')
  assert.equal(pct(0, 0), '–')
  assert.equal(skippedNote(0), null)
  assert.match(skippedNote(2), /2문항/)
})

test('단계 레슨 끝 버튼: 0단계는 소리 구별로, 숙달하면 다음 단계, 아니면 한 묶음 더', () => {
  const calls = []
  const base = { reload: () => calls.push('reload'), onExit: () => calls.push('exit'), onStage: (n) => calls.push(`stage${n}`) }
  const s0 = completeActions({ ...base, stage: 0, mastered: false })
  assert.equal(s0.primary.label, '소리 구별 하러 가기')
  s0.primary.onClick()
  const s2 = completeActions({ ...base, stage: 2, mastered: true })
  assert.equal(s2.primary.label, '다음 단계로')
  s2.primary.onClick()
  const s5 = completeActions({ ...base, stage: 5, mastered: true })
  assert.equal(s5.primary.label, '한 묶음 더 하기')
  s5.primary.onClick()
  s5.secondary.onClick()
  assert.equal(s5.secondary.label, '학습 경로로')
  assert.deepEqual(calls, ['stage1', 'stage3', 'reload', 'exit'])
})

test('연습 주소 → 질의: 고를 것이 남으면 ready가 거짓', () => {
  assert.deepEqual(practiceQuery('contrast', params({})), { ready: false, query: {} })
  assert.deepEqual(practiceQuery('contrast', params({ kind: 'vowel' })), { ready: true, query: { kind: 'vowel' } })
  assert.deepEqual(practiceQuery('contrast', params({ weak: '1', kind: 'vowel' })), { ready: true, query: { weak: 1 } })
  assert.deepEqual(practiceQuery('scenario', { place: '병원' }), { ready: true, query: { place: '병원' } })
  assert.equal(practiceQuery('conditions', params({ condition: 'tv' })).ready, false)
  assert.deepEqual(practiceQuery('conditions', params({ condition: 'phone' })), { ready: true, query: { condition: 'phone' } })
  assert.deepEqual(practiceQuery('conditions', params({ condition: 'noise', noise: 'zzz' })), { ready: true, query: { condition: 'noise', noise: 'babble' } })
  assert.deepEqual(practiceQuery('conditions', params({ condition: 'noise', noise: 'ssn' })).query, { condition: 'noise', noise: 'ssn' })
  assert.equal(practiceQuery('dictation', params({})).ready, true)
  assert.equal(practiceQuery('nope', params({})).ready, false)
  assert.ok(PRACTICE_MODES.dictation.endless && PRACTICE_MODES.noise_endless.endless && !PRACTICE_MODES.contrast.endless)
})

test('연습 응답 → 과제: 이름이 있으면 그것, 없으면 첫 문항 모양', () => {
  assert.equal(practiceTask('contrast', { task: 'word_id', items: [{ first: 'a', second: 'b' }] }), 'word_id')
  assert.equal(practiceTask('contrast', { mode: 'contrast', items: [{ first: '바', second: '파' }] }), 'ax')
  assert.equal(practiceTask('contrast', { items: [{ target: '발', options: ['발', '팔'] }] }), 'word_id')
  assert.equal(practiceTask('scenario', { items: [{ line: '...', options: [] }] }), 'convo')
  assert.equal(practiceTask('dictation', { items: [{ text: '...' }] }), 'sentence')
  assert.equal(practiceTask('noise_endless', { items: [{ text: '...' }] }), 'noise')
  assert.equal(practiceTask('dictation', { items: [] }), null)
})

test('계단 응답 모양 맞추기와 연습 모드 목록', () => {
  assert.equal(normalizeStair(null), null)
  assert.deepEqual(normalizeStair({ next_db: 4 }), { ao: { next_db: 4 } })
  const two = { ao: { next_db: 2 }, av: { next_db: 0 } }
  assert.equal(normalizeStair(two), two)
  assert.equal(normalizeStair({ foo: 1 }), null)
  assert.deepEqual(modeAvailability([{ key: 'contrast', available: false, reason: '준비 중' }, { key: 'dictation' }, null]),
    { contrast: { available: false, reason: '준비 중' }, dictation: { available: true, reason: null } })
  assert.deepEqual(modeAvailability(undefined), {})
})

test('오늘의 듣기 블록은 앞 n문항, 소리 확인은 그대로', () => {
  const d = { mode: 'ax', items: [1, 2, 3, 4, 5] }
  assert.deepEqual(blockData(d, 3).items, [1, 2, 3])
  assert.deepEqual(blockData(d, 9).items, [1, 2, 3, 4, 5])
  assert.equal(d.items.length, 5)   // 원본은 그대로
  const ling = { mode: 'ling', sequence: ['m', 'silent'] }
  assert.equal(blockData(ling, 1), ling)
})

test('오늘 요약: 서버 분이 있으면 그것, 없으면 시작 전 + 이번 회기', () => {
  const results = [{ n: 10, c: 8, elapsed: 240 }, { n: 8, c: 4, elapsed: 360 }]
  const a = todayTotals(results, { done: { minutes: 12.34 }, targetMin: 15 })
  assert.equal(a.minutes, 12.3)
  assert.equal(a.n, 18)
  assert.equal(a.c, 12)
  assert.equal(a.goalPct, 82)
  assert.equal(a.reached, false)
  const b = todayTotals(results, { before: { minutes: 6 } })
  assert.equal(b.sessionMinutes, 10)
  assert.equal(b.minutes, 16)
  assert.equal(b.goalPct, 100)
  assert.equal(b.reached, true)
  assert.equal(todayTotals([]).accuracy, null)
  assert.equal(fmtMinutes(0.4), '1분 미만')
  assert.equal(fmtMinutes(6.6), '7분')
  assert.equal(fmtMinutes(null), '0분')
})

test('입모양이 다른 짝: 서버 표시가 먼저, 없으면 입모양 프레임 비교', () => {
  assert.equal(lipDiffers({ lip_differs: true }, null), true)
  assert.equal(lipDiffers({}, { same_mouth: true }), false)
  assert.equal(lipDiffers(null, { lip: 'differs' }), true)
  // 바·마: 같은 입모양(전환 프레임 12는 무시, 이어지는 같은 입모양은 하나)
  const a = [{ viseme: 1 }, { viseme: 12 }, { viseme: 5 }]
  const b = [{ viseme: 1 }, { viseme: 1 }, { viseme: 5 }]
  assert.equal(lipDiffers({}, {}, { a, b }), false)
  assert.equal(lipDiffers({}, {}, { a, b: [{ viseme: 3 }, { viseme: 5 }] }), true)
  assert.equal(lipDiffers({}, {}, null), null)
  assert.equal(lipDiffers({}, {}, { a: [], b }), null)
  assert.deepEqual(alternate('A', 'B', 2), ['A', 'B', 'A', 'B'])
  assert.deepEqual(alternate('A', 'B', 0), ['A', 'B'])
})

test('분석 탭 듣기 칸: 요약 칸이 있으면 그것, 없으면 결과 요약에서', () => {
  assert.deepEqual(listenOverview({ listen: { srt_db: 3.5, week_minutes: 40, ax_accuracy: 0.8 } }),
    { srt: 3.5, weekMinutes: 40, axAccuracy: 0.8, has: true })
  const s = { training: { srt_ao_db: null }, tests: [{ srt_db: 6 }, { srt_db: 4 }], days: [{ minutes: 5.2 }, { minutes: 3.1 }],
    ax_kinds: [{ n: 10, correct: 7 }, { n: 10, correct: 9 }] }
  assert.deepEqual(listenOverview({}, s), { srt: 4, weekMinutes: 8, axAccuracy: 0.8, has: true })
  assert.equal(listenOverview({}, { days: [{ n: 0 }] }).has, false)
  assert.equal(listenOverview(null, null).has, false)
})

test('소리 확인 안내와 계단 점', () => {
  const ok = lingNotes({ heard: ['m', 'u', 'a', 'i', 'sh', 's'], missed: [], dropped: [], reliable: true })
  assert.equal(ok.sub, '여섯 소리가 모두 들렸어요.')
  assert.equal(ok.notes.filter(Boolean).length, 0)
  const bad = lingNotes({ heard: ['m'], missed: ['s'], dropped: ['s'], reliable: false, false_alarms: 2 })
  assert.match(bad.notes.filter(Boolean)[0], /스 소리/)
  assert.match(bad.notes.filter(Boolean)[1], /2번/)
  assert.deepEqual(stairPoints([], 100, 20), [])
  const pts = stairPoints([{ snr: 10, correct: true }, { snr: 8, correct: false }, { snr: 'x' }, { snr: 12, correct: true }], 100, 20)
  assert.equal(pts.length, 3)
  assert.equal(pts[0].x, 0)
  assert.equal(pts[2].x, 100)
  assert.ok(pts[2].y < pts[1].y)   // 큰 SNR이 위
  assert.ok(pts.every((p) => p.y >= 0 && p.y <= 20))
})
