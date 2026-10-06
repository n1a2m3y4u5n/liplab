import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizeAnswers, toggleDevice, learnerDefaults, BASE_DEFAULTS, hasAnswers, describeDefaults, splitFirstSentence,
  loadAnswers, saveAnswers, clearAnswers, storageKey,
} from './learnerProfile.js'

// 계획 2-6 설계: 선천·아동기 → 읽기 부담 줄인 보기 + 짧은 힌트, 성인기 → 말하기 운율·마찰음 추천,
// 보청기·인공와우 → 소리 조건 추천(저장만), 수어 사용 → 수어 보기 켜기. 답하지 않으면 지금 동작 그대로.

test('답하지 않으면 기본값은 지금 동작 그대로', () => {
  assert.deepEqual(learnerDefaults({}), { ...BASE_DEFAULTS })
  assert.deepEqual(learnerDefaults(null), { ...BASE_DEFAULTS })
  assert.equal(hasAnswers({}), false)
  assert.deepEqual(describeDefaults(learnerDefaults({})), [])
})

test('선천·아동기 손실 → 읽기 부담 줄인 보기와 짧은 힌트', () => {
  const d = learnerDefaults({ onset: 'early' })
  assert.equal(d.readingLoad, 'reduced')
  assert.equal(d.shortHints, true)
  assert.deepEqual(d.speakFocus, [])
  assert.equal(d.signView, false)
  assert.equal(d.soundCondition, false)
})

test('성인기 손실 → 말하기는 운율과 마찰음부터, 읽기 기본값은 그대로', () => {
  const d = learnerDefaults({ onset: 'adult' })
  assert.deepEqual(d.speakFocus, ['prosody', 'fricative'])
  assert.equal(d.readingLoad, 'standard')
  assert.equal(d.shortHints, false)
})

test('보청기·인공와우 → 소리 조건 추천, 없음이면 추천 안 함', () => {
  assert.equal(learnerDefaults({ devices: ['hearing_aid'] }).soundCondition, true)
  assert.equal(learnerDefaults({ devices: ['cochlear_implant'] }).soundCondition, true)
  assert.equal(learnerDefaults({ devices: ['hearing_aid', 'cochlear_implant'] }).soundCondition, true)
  assert.equal(learnerDefaults({ devices: ['none'] }).soundCondition, false)
})

test('수어 사용 → 수어 보기 켜기', () => {
  assert.equal(learnerDefaults({ sign: 'yes' }).signView, true)
  assert.equal(learnerDefaults({ sign: 'no' }).signView, false)
})

test('여러 답은 서로 독립으로 합쳐진다', () => {
  const d = learnerDefaults({ onset: 'early', devices: ['cochlear_implant'], sign: 'yes' })
  assert.deepEqual(d, { readingLoad: 'reduced', shortHints: true, signView: true, speakFocus: [], soundCondition: true })
  assert.equal(describeDefaults(d).length, 4)
})

test('모르는 값은 버리고, 없음은 다른 기기와 함께 남지 않는다', () => {
  assert.deepEqual(normalizeAnswers({ onset: 'teen', devices: ['x', 'hearing_aid', 'hearing_aid'], sign: 'maybe' }),
    { onset: null, devices: ['hearing_aid'], sign: null })
  assert.deepEqual(normalizeAnswers({ devices: ['none', 'cochlear_implant'] }).devices, ['cochlear_implant'])
  assert.deepEqual(normalizeAnswers({ devices: ['cochlear_implant', 'hearing_aid'] }).devices, ['hearing_aid', 'cochlear_implant'])
  assert.deepEqual(normalizeAnswers('깨진 값'), { onset: null, devices: [], sign: null })
})

test('기기 토글: 없음을 고르면 다른 기기를 지우고, 기기를 고르면 없음을 지운다', () => {
  assert.deepEqual(toggleDevice([], 'hearing_aid'), ['hearing_aid'])
  assert.deepEqual(toggleDevice(['hearing_aid'], 'cochlear_implant'), ['hearing_aid', 'cochlear_implant'])
  assert.deepEqual(toggleDevice(['hearing_aid', 'cochlear_implant'], 'none'), ['none'])
  assert.deepEqual(toggleDevice(['none'], 'hearing_aid'), ['hearing_aid'])
  assert.deepEqual(toggleDevice(['hearing_aid'], 'hearing_aid'), [])
})

test('짧은 힌트: 첫 문장과 나머지로 한 번만 나눈다', () => {
  assert.deepEqual(splitFirstSentence('가장 크게 벌어지는 모음. 문장에서 눈에 잘 띄는 닻이 된다.'),
    { first: '가장 크게 벌어지는 모음.', rest: '문장에서 눈에 잘 띄는 닻이 된다.' })
  assert.deepEqual(splitFirstSentence('한 문장뿐이에요.'), { first: '한 문장뿐이에요.', rest: '' })
  assert.deepEqual(splitFirstSentence('물음표? 다음 문장! 셋째.'), { first: '물음표?', rest: '다음 문장! 셋째.' })
  assert.deepEqual(splitFirstSentence(''), { first: '', rest: '' })
})

test('저장은 계정마다 다른 키, 서버가 아닌 넘겨받은 저장소에만', () => {
  const store = new Map()
  const fake = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) }
  assert.equal(loadAnswers(7, fake), null)
  saveAnswers(7, { onset: 'early', sign: 'yes' }, fake)
  assert.ok(store.has(storageKey(7)) && !store.has(storageKey(8)))
  assert.deepEqual(loadAnswers(7, fake), { onset: 'early', devices: [], sign: 'yes' })
  assert.equal(loadAnswers(8, fake), null)
  clearAnswers(7, fake)
  assert.equal(loadAnswers(7, fake), null)
})

test('저장소가 막혀도 이 창에서는 기억한다', () => {
  const blocked = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') }, removeItem() { throw new Error('blocked') } }
  saveAnswers('u1', { onset: 'adult' }, blocked)
  assert.deepEqual(loadAnswers('u1', blocked), { onset: 'adult', devices: [], sign: null })
  clearAnswers('u1', blocked)
  assert.equal(loadAnswers('u1', blocked), null)
})
