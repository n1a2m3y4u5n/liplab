import { test } from 'node:test'
import assert from 'node:assert/strict'
import { toneDirection, toneMissed } from './speakTone.js'

test('억양은 운율 올리기·내리기에서만 판정한다', () => {
  assert.equal(toneDirection('prosody', 'rise'), 'rise')
  assert.equal(toneDirection('prosody', 'fall'), 'fall')
  for (const [m, d] of [['voicing', null], ['prosody', 'long'], ['prosody', 'loud'], ['prosody', 'soft'], ['word', null], ['sentence', null]]) {
    assert.equal(toneDirection(m, d), null, `${m}/${d}`)
  }
})

test('발성(길게 아—)은 음높이가 평평해도 지적하지 않는다', () => {
  assert.equal(toneMissed({ pitchStart: 200, pitchEnd: 201, pitchRange: 3 }, toneDirection('voicing', null)), false)
})

test('방향은 서버와 같은 반음 기준(1.65), 폭이 커도 방향이 반대면 놓친 것', () => {
  assert.equal(toneMissed({ pitchStart: 200, pitchEnd: 220 }, 'rise'), false)
  assert.equal(toneMissed({ pitchStart: 200, pitchEnd: 210 }, 'rise'), true)
  assert.equal(toneMissed({ pitchStart: 220, pitchEnd: 180, pitchRange: 60 }, 'rise'), true)
  assert.equal(toneMissed({ pitchStart: 220, pitchEnd: 180 }, 'fall'), false)
  assert.equal(toneMissed({ pitchStart: 0, pitchEnd: 0 }, 'rise'), false, '음높이를 못 쟀으면 판정하지 않음')
})

test('반음이라 목소리 높이와 상관없다: 여성 220Hz의 +15Hz(1.1반음)는 부족, 남성 120Hz의 +15Hz(2.0반음)는 충분', () => {
  assert.equal(toneMissed({ pitchStart: 220, pitchEnd: 235 }, 'rise'), true)
  assert.equal(toneMissed({ pitchStart: 120, pitchEnd: 135 }, 'rise'), false)
})
