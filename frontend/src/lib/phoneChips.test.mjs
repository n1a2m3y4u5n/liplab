import test from 'node:test'
import assert from 'node:assert/strict'
import { phoneTone, phoneChipView, phoneValue } from './phoneChips.js'

test('신뢰도 표가 없으면 예전처럼 점수 색, 전체 참고 안내', () => {
  const phones = [{ label: 'ㄱ', dgop: 0.9 }, { label: 'ㅏ', dgop: 0.3 }]
  assert.equal(phoneTone(phones[0]).level, 'good')
  assert.equal(phoneTone(phones[1]).level, 'bad')
  const v = phoneChipView(phones, false)
  assert.equal(v.map, false)
  assert.equal(v.sure, 2)
  assert.equal(v.sureGood, 1)
  assert.match(v.note, /참고용/)
  assert.match(v.title, /\(참고\)/)
})

test('믿을 만한 소리만 색, 나머지는 회색 참고', () => {
  const phones = [
    { label: 'ㄱ', dgop: 0.2, reliable: true },
    { label: 'ㅓ', dgop: 0.2, reliable: false },
    { label: 'ㄴ', dgop: 0.95, reliable: true },
  ]
  assert.equal(phoneTone(phones[0]).level, 'bad')
  assert.equal(phoneTone(phones[1]).level, 'reference')
  assert.match(phoneTone(phones[1]).chip, /border-line/)
  const v = phoneChipView(phones, true)
  assert.equal(v.map, true)
  assert.equal(v.sure, 2)
  assert.equal(v.sureGood, 1)
  assert.match(v.note, /색이 있는 소리만 확정/)
  assert.equal(v.title, '소리별 발음 정확도')
})

test('믿을 만한 소리가 하나도 없으면 모두 참고 안내', () => {
  const v = phoneChipView([{ label: 'ㅏ', dgop: 0.9, reliable: false }], true)
  assert.equal(v.sure, 0)
  assert.match(v.note, /모두 참고/)
})

test('표시 값은 앱과 같은 반올림', () => {
  assert.equal(phoneValue({ dgop: 0.45 }), 45)
  assert.equal(phoneTone({ dgop: 0.45, reliable: true }).level, 'warn')
  assert.equal(phoneValue({}), 0)
  assert.equal(phoneChipView([], true).note, null)
})
