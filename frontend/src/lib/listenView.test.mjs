import { test } from 'node:test'
import assert from 'node:assert/strict'
import { listenKeyAction, playbackMs, sequenceMs, soundStatusText, fmtDb, fmtDuration, levelChangeText, testStep } from './listenView.js'

const ctx = { canPlay: true, optionCount: 4, canPick: true, canEnter: true }

test('스페이스는 듣기, 숫자는 보기, Enter는 확인', () => {
  assert.deepEqual(listenKeyAction({ key: ' ', targetTag: 'BODY' }, ctx), { type: 'play' })
  assert.deepEqual(listenKeyAction({ key: '3', targetTag: 'BODY' }, ctx), { type: 'pick', index: 2 })
  assert.deepEqual(listenKeyAction({ key: 'Enter', targetTag: 'DIV' }, ctx), { type: 'enter' })
})

test('보기 수를 넘는 숫자, 막힌 동작은 무시한다', () => {
  assert.equal(listenKeyAction({ key: '5', targetTag: 'BODY' }, ctx), null)
  assert.equal(listenKeyAction({ key: '0', targetTag: 'BODY' }, ctx), null)
  assert.equal(listenKeyAction({ key: ' ', targetTag: 'BODY' }, { ...ctx, canPlay: false }), null)
  assert.equal(listenKeyAction({ key: '1', targetTag: 'BODY' }, { ...ctx, canPick: false }), null)
  assert.equal(listenKeyAction({ key: 'Enter', targetTag: 'BODY' }, { ...ctx, canEnter: false }), null)
})

test('글 쓰는 칸·조합키·반복 키는 가로채지 않는다', () => {
  assert.equal(listenKeyAction({ key: ' ', targetTag: 'INPUT' }, ctx), null)
  assert.equal(listenKeyAction({ key: '1', targetTag: 'TEXTAREA' }, ctx), null)
  assert.equal(listenKeyAction({ key: 'Enter', targetTag: 'DIV', editable: true }, ctx), null)
  assert.equal(listenKeyAction({ key: '1', targetTag: 'BODY', metaKey: true }, ctx), null)
  assert.equal(listenKeyAction({ key: ' ', targetTag: 'BODY', repeat: true }, ctx), null)
})

test('버튼에 초점이 있으면 스페이스·Enter는 버튼이 받고, 숫자는 그대로 고른다', () => {
  assert.equal(listenKeyAction({ key: ' ', targetTag: 'BUTTON' }, ctx), null)
  assert.equal(listenKeyAction({ key: 'Enter', targetTag: 'button' }, ctx), null)
  assert.deepEqual(listenKeyAction({ key: '2', targetTag: 'BUTTON' }, ctx), { type: 'pick', index: 1 })
  assert.deepEqual(listenKeyAction({ code: 'Space', key: 'Unidentified', targetTag: 'MAIN' }, ctx), { type: 'play' })
})

test('재생 길이: 소음이 있으면 앞뒤 소음 구간을 더하고, 천천히는 늘인다', () => {
  assert.equal(playbackMs({ duration_ms: 1000 }), 1000)
  assert.equal(playbackMs({ duration_ms: 1000 }, { noise: {}, snrDb: 5 }), 1950)
  assert.equal(playbackMs({ duration_ms: 1000 }, { noise: {}, snrDb: 5, leadMs: 300 }), 1750)
  assert.equal(playbackMs({ duration_ms: 800 }, { rate: 0.8 }), 1000)
  assert.equal(playbackMs({ duration_ms: 1000 }, { noise: {}, snrDb: null }), 1000)   // SNR이 없으면 소음 없음
  assert.equal(playbackMs(null), 1400)
  assert.equal(sequenceMs([{ clip: { duration_ms: 500 } }, { clip: { duration_ms: 700 } }]), 1800)
  assert.equal(sequenceMs([{ silenceMs: 1400 }]), 1400)
})

test('상태 문구', () => {
  assert.equal(soundStatusText('playing', { part: 2, parts: 2 }), '두 번째 소리가 나오고 있어요')
  assert.equal(soundStatusText('playing'), '소리가 나오고 있어요')
  assert.equal(soundStatusText('done'), '소리가 끝났어요')
  assert.equal(soundStatusText('idle'), '버튼을 누르면 소리가 나와요')
})

test('dB·시간·수준 문구', () => {
  assert.equal(fmtDb(3), '+3 dB')
  assert.equal(fmtDb(-2.54), '-2.5 dB')
  assert.equal(fmtDb(0), '0 dB')
  assert.equal(fmtDb(null), '–')
  assert.equal(fmtDuration(185), '3분 5초')
  assert.equal(fmtDuration(45), '45초')
  assert.equal(levelChangeText(2, 3, 4), '수준이 올라갔어요 · 지금 3 / 4')
  assert.equal(levelChangeText(3, 2, 4), '수준이 내려갔어요 · 지금 2 / 4')
  assert.equal(levelChangeText(2, 2, 4), null)
})

test('검사 앞 연습 문장은 따로 세고, 진행은 검사 문장 기준이다', () => {
  const items = [...Array(5)].map((_, i) => ({ key: `testp:${i}`, practice: true }))
    .concat([...Array(20)].map((_, i) => ({ key: `test:A${i}`, practice: false })))
  assert.deepEqual(testStep(items, 0), { practice: true, no: 1, total: 5, nPractice: 5 })
  assert.deepEqual(testStep(items, 4), { practice: true, no: 5, total: 5, nPractice: 5 })
  assert.deepEqual(testStep(items, 5), { practice: false, no: 1, total: 20, nPractice: 5 })
  assert.deepEqual(testStep(items, 24), { practice: false, no: 20, total: 20, nPractice: 5 })
  // 연습이 없는 옛 응답
  assert.deepEqual(testStep([{ key: 'a' }, { key: 'b' }], 1), { practice: false, no: 2, total: 2, nPractice: 0 })
})
