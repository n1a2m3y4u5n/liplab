import { test } from 'node:test'
import assert from 'node:assert/strict'
import { VISEME_PLAIN, plainVisemeLabel, lessonPlainLabel } from './visemeLabels.js'

// backend/engine.py VISEME_MAP의 초성·중성 부분(예시 음절이 그 무리를 보이는지 확인용)
const ONSET = { 'ㅂ': 1, 'ㅃ': 1, 'ㅍ': 1, 'ㅁ': 1, 'ㄷ': 6, 'ㄸ': 6, 'ㅌ': 6, 'ㄴ': 6, 'ㄹ': 6, 'ㅅ': 6, 'ㅆ': 6,
  'ㄱ': 7, 'ㄲ': 7, 'ㅋ': 7, 'ㅎ': 8, 'ㅈ': 10, 'ㅉ': 10, 'ㅊ': 10 }
const VOWEL = { 'ㅏ': 2, 'ㅐ': 2, 'ㅑ': 2, 'ㅒ': 2, 'ㅣ': 3, 'ㅔ': 3, 'ㅖ': 3, 'ㅗ': 4, 'ㅛ': 4, 'ㅜ': 4, 'ㅠ': 4, 'ㅓ': 5, 'ㅕ': 5, 'ㅡ': 5,
  'ㅘ': 9, 'ㅙ': 9, 'ㅚ': 9, 'ㅝ': 9, 'ㅞ': 9, 'ㅟ': 9, 'ㅢ': 9 }
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'.split('')
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'.split('')
const split = (syl) => {
  const c = syl.charCodeAt(0) - 0xac00
  return { cho: CHO[Math.floor(c / 588)], jung: JUNG[Math.floor((c % 588) / 28)], jong: c % 28 }
}
const QUIZ = [1, 2, 3, 4, 5, 9]

test('입모양 무리 10개 모두 쉬운 이름이 있고, 퀴즈 무리 여섯은 서로 다르다', () => {
  for (let v = 1; v <= 10; v++) assert.ok(plainVisemeLabel(v), String(v))
  const labels = QUIZ.map(plainVisemeLabel)
  assert.equal(new Set(labels).size, labels.length)
})

test('보기 이름은 전문 용어·자모 목록 없이 짧다(예전 평균 16.3자)', () => {
  const jargon = /양순|개방|전설|원순|중설|이중|치경|연구개|성문|경구개|[ㄱ-ㅎㅏ-ㅣ]/
  for (let v = 1; v <= 10; v++) assert.ok(!jargon.test(plainVisemeLabel(v)), plainVisemeLabel(v))
  const mean = QUIZ.reduce((s, v) => s + plainVisemeLabel(v).length, 0) / QUIZ.length
  assert.ok(mean <= 12, `평균 ${mean.toFixed(1)}자`)
  assert.equal(plainVisemeLabel(1), '입술 닫힘 (바·마)')
  assert.equal(plainVisemeLabel(2), '입 크게 벌림 (아)')
})

test('예시 음절은 받침 없는 한 글자이고 그 무리의 입모양을 보인다(자음 무리는 초성, 모음 무리는 첫소리 없는 모음)', () => {
  for (const [v, p] of Object.entries(VISEME_PLAIN)) {
    assert.ok(p.ex.length >= 1)
    for (const syl of p.ex) {
      assert.equal(syl.length, 1)
      const { cho, jung, jong } = split(syl)
      assert.equal(jong, 0, syl)
      const got = cho === 'ㅇ' ? VOWEL[jung] : ONSET[cho]
      assert.equal(got, Number(v), `${syl} → ${got}, 기대 ${v}`)
    }
  }
})

test('레슨 객체 이름: 쉬운 이름 우선, 없으면 서버 이름', () => {
  assert.equal(lessonPlainLabel({ viseme_id: 4, name: '원순모음' }), '입술 둥글게 (오·우)')
  assert.equal(lessonPlainLabel({ viseme_id: 99, name: '새 무리' }), '새 무리')
  assert.equal(lessonPlainLabel(null), '')
})
