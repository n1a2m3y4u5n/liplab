import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mixLevels, clampGainDb, pickSource, voiceRoles, voiceFor, axVoices, fitFramesToAudio, snrLabel, contrastText,
  readSettings, writeSettings, REF_DBFS, gainFor, rmsOf, activeLevel, createLru, usableVoices } from './listenMix.js'

const db = (x) => 20 * Math.log10(x)

test('전체 크기는 SNR과 관계없이 같고 비율만 바뀐다', () => {
  const quiet = mixLevels(-10)
  assert.equal(quiet.noise, 0)
  assert.ok(Math.abs(db(quiet.speech) - (REF_DBFS - 10)) < 1e-9)
  for (const snr of [-10, -3, 0, 5, 25]) {
    const m = mixLevels(-10, snr)
    const total = Math.sqrt(m.speech ** 2 + m.noise ** 2)
    assert.ok(Math.abs(db(total) - (REF_DBFS - 10)) < 1e-9, `snr ${snr}`)
    assert.ok(Math.abs(db(m.speech) - db(m.noise) - snr) < 1e-9)
  }
})

test('편안한 크기는 -30 ~ 0 dB로 자른다', () => {
  assert.equal(clampGainDb(5), 0)
  assert.equal(clampGainDb(-50), -30)
  assert.equal(clampGainDb('x'), -10)
  assert.equal(gainFor(0.1, 0), 0)
  assert.ok(Math.abs(rmsOf([1, -1, 1, -1]) - 1) < 1e-12)
})

test('브라우저가 풀 수 있는 형식을 고른다', () => {
  const src = [{ url: 'a.ogg', type: 'audio/ogg; codecs=opus' }, { url: 'a.m4a', type: 'audio/mp4' }]
  assert.equal(pickSource(src, (t) => (t.includes('ogg') ? '' : 'maybe')), 'a.m4a')
  assert.equal(pickSource(src, (t) => (t.includes('ogg') ? 'probably' : 'maybe')), 'a.ogg')
  assert.equal(pickSource([], () => 'maybe'), null)
})

test('목소리가 셋 이상이면 마지막은 검사 전용', () => {
  assert.deepEqual(voiceRoles([{ id: 'f1' }, { id: 'm1' }, { id: 'f2' }, { id: 'm2' }]), { train: ['f1', 'm1', 'f2'], test: 'm2' })
  assert.deepEqual(voiceRoles([{ id: 'f1' }]), { train: ['f1'], test: 'f1' })
  assert.deepEqual(voiceRoles([]), { train: [''], test: '' })
  assert.equal(voiceFor(['a', 'b', 'c'], 4, 1), 'c')
  assert.equal(voiceFor(['a', 'b', 'c'], 4, 0, 'blocked', 1), 'b')   // 묶음 안에서는 문항이 바뀌어도 같은 목소리
  assert.equal(voiceFor(['a', 'b', 'c'], 7, 0, 'blocked', 1), 'b')
})

test('피할 목소리(avoid_voices)는 건너뛰고 다음 목소리, 모두 걸리면 원래 목소리', () => {
  const tr = ['m1', 'f1', 'm2', 'f2']
  assert.equal(voiceFor(tr, 1, 0, 'mixed', 0, ['f1']), 'm2')            // 차례가 f1이면 다음 m2
  assert.equal(voiceFor(tr, 3, 0, 'mixed', 0, ['f2']), 'm1')            // 끝에서 처음으로 돈다
  assert.equal(voiceFor(tr, 3, 0, 'mixed', 0, ['f2', 'm1']), 'f1')
  assert.equal(voiceFor(tr, 0, 0, 'mixed', 0, ['f1']), 'm1')            // 차례가 걸리지 않으면 그대로
  assert.equal(voiceFor(tr, 2, 0, 'mixed', 0, []), 'm2')
  assert.equal(voiceFor(tr, 2, 0, 'mixed', 0, null), 'm2')
  assert.equal(voiceFor(tr, 2, 0, 'mixed', 0, tr), 'm2')                // 모두 걸리면 원래 목소리
  assert.equal(voiceFor(tr, 2, 0, 'mixed', 0, ['x']), 'm2')             // 모르는 id는 무시
})

test('묶음 모드에서도 피할 목소리를 건너뛴다(그 문항만)', () => {
  const tr = ['m1', 'f1', 'm2', 'f2']
  // 묶음 1의 목소리는 f1. 걸린 문항만 m2로, 다른 문항은 f1 그대로
  assert.equal(voiceFor(tr, 5, 0, 'blocked', 1, ['f1']), 'm2')
  assert.equal(voiceFor(tr, 6, 0, 'blocked', 1, []), 'f1')
  assert.equal(voiceFor(tr, 7, 0, 'blocked', 1, ['f1', 'm2', 'f2']), 'm1')
  assert.equal(voiceFor(tr, 7, 0, 'blocked', 1, tr), 'f1')
})

test('소리 구별 두 목소리: 건너뛴 결과가 겹치면 둘째 칸을 옮긴다', () => {
  const tr = ['m1', 'f1', 'm2', 'f2']
  assert.deepEqual(axVoices(tr, 0, [0, 1], 'mixed', 0, []), ['m1', 'f1'])
  assert.deepEqual(axVoices(tr, 0, [0, 1], 'mixed', 0, ['f1']), ['m1', 'm2'])
  // 첫 칸 m1이 걸려 f1로 가면 둘째 칸(f1)과 겹친다 → 둘째 칸은 m2
  assert.deepEqual(axVoices(tr, 0, [0, 1], 'mixed', 0, ['m1']), ['f1', 'm2'])
  // 같은 칸 문항은 두 소리가 같은 목소리(건너뛴 뒤에도)
  assert.deepEqual(axVoices(tr, 0, [0, 0], 'mixed', 0, ['m1']), ['f1', 'f1'])
  assert.deepEqual(axVoices(tr, 0, undefined, 'blocked', 2, ['m2']), ['f2', 'f2'])
  // 남은 목소리가 하나뿐이면 피하는 것이 먼저라 겹친 채로 둔다
  assert.deepEqual(axVoices(tr, 0, [0, 1], 'mixed', 0, ['m1', 'f1', 'm2']), ['f2', 'f2'])
  // 모두 걸리면 원래 두 목소리
  assert.deepEqual(axVoices(tr, 1, [0, 1], 'mixed', 0, tr), ['f1', 'm2'])
  // 묶음 모드 칸 [0, 1]
  assert.deepEqual(axVoices(tr, 9, [0, 1], 'blocked', 3, ['f2']), ['m1', 'f1'])
})

test('입모양 프레임을 소리 길이에 맞춘다', () => {
  const frames = [{ viseme: 1, duration_ms: 100, text_index: 0 }, { viseme: 2, duration_ms: 100, text_index: 0 },
    { viseme: 6, duration_ms: 200, text_index: 1 }]
  const k = fitFramesToAudio(frames, 800)
  assert.equal(Math.round(k.reduce((a, f) => a + f.duration_ms, 0)), 800)
  const s = fitFramesToAudio(frames, 900, [{ i: 0, t0: 100, t1: 400 }, { i: 1, t0: 500, t1: 800 }])
  // 앞 쉼 100, 음절0 300, 사이 쉼 100, 음절1 300
  assert.equal(s[0].viseme, 15)
  assert.equal(Math.round(s.reduce((a, f) => a + f.duration_ms, 0)), 800)
  assert.equal(s.filter((f) => f.viseme === 15).length, 2)
})

test('표시 문구', () => {
  assert.equal(snrLabel(6), '말이 소음보다 6 dB 커요')
  assert.equal(snrLabel(-2), '소음이 말보다 2 dB 커요')
  assert.equal(contrastText([{ slot: 'onset', target: 'ㅂ', heard: 'ㅍ', syllable: 0 }]), '1번째 음절의 첫소리 ㅂ을(를) ㅍ(으)로 들었어요')
})

test('설정은 기기에만 저장하고 깨진 값이면 없음으로', () => {
  const mem = new Map()
  const st = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) }
  assert.equal(readSettings(st), null)
  assert.ok(writeSettings({ gainDb: 7, device: 'ci', route: 'stream' }, st))
  assert.deepEqual(readSettings(st), { gainDb: 0, device: 'ci', route: 'stream', at: null })
  mem.set('liplab_listen_settings', '{')
  assert.equal(readSettings(st), null)
  const broken = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
  assert.equal(readSettings(broken), null)
  assert.equal(writeSettings({ gainDb: 0 }, broken), false)
})

test('활성 음성 레벨은 무음 길이에 흔들리지 않는다', () => {
  const sr = 16000
  const tone = (sec, amp) => Float32Array.from({ length: sr * sec }, (_, i) => amp * Math.sin(2 * Math.PI * 300 * i / sr) * (0.6 + 0.4 * Math.sin(2 * Math.PI * 3 * i / sr)))
  const speech = tone(1.5, 0.3)
  const pad = (sec) => new Float32Array(Math.round(sr * sec))
  const cat = (...xs) => { const out = new Float32Array(xs.reduce((a, x) => a + x.length, 0)); let o = 0; for (const x of xs) { out.set(x, o); o += x.length } return out }
  const short = cat(pad(0.2), speech, pad(0.2))
  const long = cat(pad(1.0), speech, pad(1.0))
  const dB = (x) => 20 * Math.log10(x)
  assert.ok(dB(rmsOf(short)) - dB(rmsOf(long)) > 2)                       // 전체 RMS는 무음이 길수록 낮아진다
  assert.ok(Math.abs(dB(activeLevel(short, sr)) - dB(activeLevel(long, sr))) < 0.3)
  assert.ok(Math.abs(dB(activeLevel(long, sr)) - dB(rmsOf(speech))) < 1)  // 말소리 구간 RMS와 1 dB 안
  assert.equal(activeLevel(new Float32Array(100), sr), 0)
})

// ITU-T G.191 sv-p56(speech_voltmeter)을 그대로 옮긴 참조 구현: 문턱마다 유지 시간 카운터(hang[j])를 따로 두고,
// A_j = 10·log10(전체 제곱합 / 활성 표본 수), 아래 문턱부터 올라가며 A_j − C_j ≤ 15.9 dB인 첫 문턱과 그 앞 문턱 사이를 보간한다.
function svP56(x, fs) {
  const g = Math.exp(-1 / (fs * 0.03))
  const I = Math.ceil(0.2 * fs)
  const c = Array.from({ length: 15 }, (_, j) => 2 ** (j - 15))
  const a = new Array(15).fill(0)
  const hang = new Array(15).fill(I)
  let p = 0
  let q = 0
  let sq = 0
  for (const v of x) {
    sq += v * v
    p = g * p + (1 - g) * Math.abs(v)
    q = g * q + (1 - g) * p
    for (let j = 0; j < 15; j += 1) {
      if (q >= c[j]) { a[j] += 1; hang[j] = 0 } else if (hang[j] < I) { a[j] += 1; hang[j] += 1 }
    }
  }
  let prevA = null
  let prevC = null
  for (let j = 0; j < 15; j += 1) {
    if (a[j] < fs * 0.05) break
    const A = 10 * Math.log10(sq / a[j])
    const C = 20 * Math.log10(c[j])
    if (A - C <= 15.9) {
      if (prevA == null) return 10 ** (A / 20)
      const t = (prevA - prevC - 15.9) / ((prevA - prevC) - (A - C))
      return 10 ** ((prevA + t * (A - prevA)) / 20)
    }
    prevA = A
    prevC = C
  }
  return Math.sqrt(sq / x.length)
}

test('활성 음성 레벨은 G.191 sv-p56 참조 구현과 같다(쉼에 잔잡음·숨소리가 있어도)', () => {
  const sr = 16000
  let seed = 7
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648 - 0.5 }
  // 말소리처럼: 음절 덩어리 사이에 짧은 쉼(유지 시간 안)과 긴 쉼(밖), 쉼에는 −60 dB 잔잡음, 한 쉼에는 숨소리(−35 dB)
  const parts = []
  for (let k = 0; k < 6; k += 1) {
    const n = Math.round(sr * 0.25)
    parts.push(Float32Array.from({ length: n }, (_, i) => 0.25 * Math.sin(2 * Math.PI * (180 + 40 * k) * i / sr) * Math.sin(Math.PI * i / n)))
    const gap = k % 2 ? 0.12 : 0.6
    parts.push(Float32Array.from({ length: Math.round(sr * gap) }, (_, i) => 0.001 * rnd() + (i < sr * 0.1 && k === 2 ? 0.04 * rnd() : 0)))
  }
  const x = new Float32Array(parts.reduce((s, p) => s + p.length, 0))
  let o = 0
  for (const p of parts) { x.set(p, o); o += p.length }
  const dB = (v) => 20 * Math.log10(v)
  assert.ok(Math.abs(dB(activeLevel(x, sr)) - dB(svP56(x, sr))) < 0.01, `${dB(activeLevel(x, sr))} vs ${dB(svP56(x, sr))}`)
  // 정현파 하나(쉼 없음)는 RMS(진폭/√2)에 가깝다. 포락선이 처음에 차오르는 동안(시간 상수 30 ms 두 번)은 비활성이라 1초 신호에서
  // 약 0.1 dB 높게 나온다(참조 구현도 같다)
  const s = Float32Array.from({ length: sr }, (_, i) => 0.5 * Math.sin(2 * Math.PI * 440 * i / sr))
  assert.ok(Math.abs(dB(activeLevel(s, sr)) - dB(0.5 / Math.SQRT2)) < 0.15)
  assert.ok(Math.abs(dB(activeLevel(s, sr)) - dB(svP56(s, sr))) < 0.01)
})

test('개수 상한 캐시는 가장 오래 안 쓴 것부터 버린다', () => {
  const c = createLru(3)
  c.set('a', 1)
  c.set('b', 2)
  c.set('c', 3)
  assert.equal(c.get('a'), 1)          // a를 썼으므로 다음에 버릴 것은 b
  c.set('d', 4)
  assert.equal(c.size, 3)
  assert.equal(c.has('b'), false)
  assert.ok(c.has('a') && c.has('c') && c.has('d'))
  c.delete('a')
  assert.equal(c.size, 2)
})

test('usableVoices: 피할 목소리를 빼고, 모두 걸리면 전부', () => {
  assert.deepEqual(usableVoices(['m1', 'f1', 'm2', 'f2'], ['f1']), ['m1', 'm2', 'f2'])
  assert.deepEqual(usableVoices(['m1', 'f1'], ['m1', 'f1']), ['m1', 'f1'])
  assert.deepEqual(usableVoices(['m1', 'f1'], null), ['m1', 'f1'])
})
