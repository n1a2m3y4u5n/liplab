import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TONE_MIN_FRAMES, finalTone, riseFallTone, semitones, toneDirection, toneMissed } from './speakTone.js'

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

test('문장 끝 억양은 마지막 음절의 상승을 전체 중앙값과 비교해 잡는다', () => {
  // 평서 하강 뒤 마지막 음절만 올린 의문문: 예전 앞 30% 대 뒤 30% 평균은 평평(1.33반음 미만), 새 척도는 올림
  const q = [220, 218, 215, 212, 208, 205, 200, 198, 195, 192, 190, 188, 186, 210, 235, 245]
  const head = q.slice(0, Math.round(q.length * 0.3)), tail = q.slice(Math.floor(q.length * 0.7))
  const avg = (a) => a.reduce((x, y) => x + y, 0) / a.length
  assert.ok(Math.abs(semitones(avg(head), avg(tail))) < 1.33)
  const { ref, final } = finalTone(q)
  assert.ok(semitones(ref, final) > 1.33)
  // 옥타브 튐 한 프레임은 끝값을 흔들지 않는다
  const s = [220, 215, 210, 205, 200, 195, 190, 185, 180, 175, 400, 170]
  const t = finalTone(s)
  assert.ok(semitones(t.ref, t.final) < -1.33)
  assert.deepEqual(finalTone([200, 210]), { ref: 0, final: 0 })
})

test('운율 올리기·내리기: 끝의 옥타브 튐 프레임으로는 통과하지 않는다', () => {
  const dir = (ps) => { const r = riseFallTone(ps); return semitones(r.start, r.end) }
  const flat = Array(22).fill(200)
  // 예전 앞·뒤 30% 평균은 아래 두 경우를 올리기 100점·내리기 합격으로 봤다
  const avg = (a) => a.reduce((x, y) => x + y, 0) / a.length
  const old = (ps) => semitones(avg(ps.slice(0, Math.round(ps.length * 0.3))), avg(ps.slice(Math.floor(ps.length * 0.7))))
  assert.ok(old([...flat, 400]) >= 1.65)
  assert.ok(old([...flat, 100, 100]) <= -1.65)
  assert.ok(Math.abs(dir([...flat, 400])) < 1.65, '끝 한 프레임 옥타브 위')
  assert.ok(Math.abs(dir([...flat, 100, 100])) < 1.65, '끝 두 프레임 반 옥타브 아래')
  assert.ok(Math.abs(dir([...flat, 400, 400, 200, 200])) < 1.65, '끝 가까이 연속 두 프레임 튐')
  assert.ok(Math.abs(dir([...flat.slice(0, 18), 400, 200, 400, 200, 200])) < 1.65, '끝 구간에 흩어진 튐')
  // 튐이 있어도 판정을 흔들지 않는다(toneMissed는 서버와 같은 값을 본다)
  const r = riseFallTone([...flat, 400])
  assert.equal(toneMissed({ pitchStart: r.start, pitchEnd: r.end }, 'rise'), true)
})

test('운율 올리기·내리기: 진짜 올림·내림은 그대로 통과하고, 유성 프레임이 모자라면 판정하지 않는다', () => {
  const rise = [...Array(15).fill(200), ...Array.from({ length: 8 }, (_, i) => 200 + 6.25 * (i + 1))]   // 끝 약 0.5초에 200→250Hz
  const fall = [...Array(12).fill(220), ...Array.from({ length: 10 }, (_, i) => 220 - 6 * (i + 1))]    // 220→160Hz
  const up = riseFallTone(rise), down = riseFallTone(fall)
  assert.ok(semitones(up.start, up.end) >= 1.65)
  assert.ok(semitones(down.start, down.end) <= -1.65)
  // 올리며 한 프레임 튀어도 통과는 그대로
  const bumpy = rise.slice(); bumpy[17] = 420
  assert.ok(semitones(riseFallTone(bumpy).start, riseFallTone(bumpy).end) >= 1.65)
  // 녹음 루프 trace({t, hz}, 무성 null)도 받는다. 앞 무음은 건너뛴다
  const trace = [...Array(10)].map((_, i) => ({ t: i * 0.067, hz: null }))
    .concat(rise.map((hz, i) => ({ t: 0.67 + i * 0.067, hz })))
  assert.deepEqual(riseFallTone(trace), up)
  const short = riseFallTone([200, 210, 220, 235, 250, 260, 270])   // 끝 100ms를 빼면 5프레임
  assert.ok(short.n < TONE_MIN_FRAMES)
  assert.equal(short.start, 0)
  assert.equal(short.end, 0)
})
