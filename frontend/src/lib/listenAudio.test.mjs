// listenAudio(재생)의 흐름을 가짜 Web Audio로 확인한다. 실제 소리는 나지 않는다(스피커가 없는 node).
// 확인하는 것: 모든 재생 경로가 제한기(DynamicsCompressor)를 거쳐 출력에 닿는지, 음소거면 출력에 아예 닿지 않는지, 빠른 연속 재생·
// 준비 중 멈춤·쉼 중 멈춤에서 소리가 겹치지 않는지, 끝남 이벤트가 안 와도 보호 시간 뒤 소리까지 멈추는지, 재개가 풀리지 않아도
// 멈추지 않는지, 전화+천천히가 던지지 않는지, 소리 캐시 상한, 보코더 판 크기 정규화.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'

// ── 모듈 해석: '../api'는 가짜, 확장자 없는 './listenMix'는 .js로 ─────────────────
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === '../api' && context.parentURL?.endsWith('/listenAudio.js')) {
      return { url: 'data:text/javascript,export default globalThis.__fakeApi', shortCircuit: true }
    }
    if (specifier === './listenMix' && context.parentURL?.endsWith('/listenAudio.js')) {
      return next('./listenMix.js', context)
    }
    return next(specifier, context)
  },
})

const env = { autoEnd: true, offlineDelayMs: 0, offlineGain: 0.37, resume: 'ok', decodeFail: false, ctx: null, fetches: 0 }

class P {
  constructor(v = 0) { this.value = v }
  setValueAtTime(v) { this.value = v }
  linearRampToValueAtTime(v) { this.value = v }
  setTargetAtTime(v) { this.value = v }
  cancelScheduledValues() {}
}
class N {
  constructor(c, kind) { this.c = c; this.kind = kind; this.outs = new Set() }
  connect(n) { this.outs.add(n); return n }
  disconnect() { this.outs.clear() }
}
class Buf {
  constructor(ch, len, sr) { this.numberOfChannels = ch; this.length = len; this.sampleRate = sr; this.duration = len / sr; this.d = new Float32Array(len) }
  getChannelData() { return this.d }
  copyToChannel(a) { this.d.set(a.subarray(0, this.length)) }
}
class Src extends N {
  constructor(c) { super(c, 'src'); this.buffer = null; this.loop = false; this.playbackRate = new P(1); this.onended = null; this.state = 'idle' }
  start(when = 0) {
    if (this.state !== 'idle') throw new Error('InvalidStateError')
    this.state = 'playing'
    this.c.started.push(this)
    if (!this.loop && env.autoEnd && this.c.state === 'running') {
      const ms = (Math.max(0, when - this.c.currentTime) + this.buffer.duration / this.playbackRate.value) * 1000
      this.t = setTimeout(() => { if (this.state === 'playing') { this.state = 'ended'; this.onended?.() } }, ms)
    }
  }
  stop() {
    if (this.state === 'idle') throw new Error('InvalidStateError')
    if (this.state === 'playing') { this.state = 'stopped'; clearTimeout(this.t); setTimeout(() => this.onended?.(), 0) }
  }
}
class BaseCtx {
  constructor(sr) { this.sampleRate = sr; this.currentTime = 0; this.destination = new N(this, 'dest'); this.started = [] }
  createGain() { const n = new N(this, 'gain'); n.gain = new P(1); return n }
  createBiquadFilter() { const n = new N(this, 'biquad'); n.frequency = new P(); n.Q = new P(); return n }
  createWaveShaper() { return new N(this, 'shaper') }
  createConvolver() { return new N(this, 'conv') }
  createOscillator() { const n = new N(this, 'osc'); n.frequency = new P(); n.start = () => {}; return n }
  createBufferSource() { return new Src(this) }
  createBuffer(ch, len, sr) { return new Buf(ch, len, sr) }
}
class FakeCtx extends BaseCtx {
  constructor() {
    super(48000)
    this.state = 'running'
    this.media = []
    env.ctx = this
  }
  createDynamicsCompressor() {
    const n = new N(this, 'limiter')
    for (const k of ['threshold', 'knee', 'ratio', 'attack', 'release']) n[k] = new P()
    return n
  }
  createMediaElementSource(el) {
    if (el.ms) throw new Error('InvalidStateError: 이미 연결된 <audio>')
    const n = new N(this, 'media')
    n.el = el
    el.ms = n
    this.media.push(n)
    return n
  }
  resume() {
    if (env.resume === 'hang') return new Promise(() => {})
    this.state = 'running'
    return Promise.resolve()
  }
  decodeAudioData(ab) {
    if (env.decodeFail) return Promise.reject(new Error('EncodingError'))
    const x = new Float32Array(ab)
    const b = new Buf(1, x.length, this.sampleRate)
    b.d.set(x)
    return Promise.resolve(b)
  }
}
class FakeOffline extends BaseCtx {
  constructor(ch, len, sr) { super(sr); this.len = len }
  async startRendering() {
    if (env.offlineDelayMs) await new Promise((r) => setTimeout(r, env.offlineDelayMs))
    const out = new Buf(1, this.len, this.sampleRate)
    const first = this.started.find((s) => s.buffer && s.buffer.d)   // 첫 소스(말·섞은 소리)를 offlineGain배로 낸다
    if (first) { const n = Math.min(out.length, first.buffer.length); for (let i = 0; i < n; i += 1) out.d[i] = first.buffer.d[i] * env.offlineGain }
    return out
  }
}
class FakeAudio {
  constructor() { this.src = ''; this.muted = false; this.volume = 1; this.ls = {}; this.paused = true }
  canPlayType() { return 'maybe' }
  addEventListener(t, f) { (this.ls[t] ||= []).push(f) }
  play() {
    this.paused = false
    setTimeout(() => {
      for (const f of this.ls.playing || []) f()
      if (env.autoEnd) setTimeout(() => { if (!this.paused) this.onended?.() }, 30)
    }, 5)
    return Promise.resolve()
  }
  pause() { this.paused = true }
}

const store = new Map()
const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) }
globalThis.window = { AudioContext: FakeCtx, OfflineAudioContext: FakeOffline, localStorage: storage, sessionStorage: storage }
globalThis.Audio = FakeAudio
const SR = 48000
const tone = (sec, amp = 0.3, padSec = 0) => {
  const n = Math.round(SR * sec)
  const p = Math.round(SR * padSec)
  const x = new Float32Array(n + 2 * p)
  for (let i = 0; i < n; i += 1) x[p + i] = amp * Math.sin(2 * Math.PI * 220 * i / SR)
  return x
}
globalThis.fetch = async (url) => {
  env.fetches += 1
  return { ok: true, arrayBuffer: async () => tone(0.05).buffer }
}
globalThis.__fakeApi = {
  get: async (path, cfg) => {
    if (path === '/sound' && cfg.params.text === '준비 전') return { status: 404, data: { available: false } }
    if (path === '/sound' && cfg.params.text === '연결 끊김') throw new Error('Network Error')
    if (path === '/sound') return { status: 200, data: { available: true, sources: [{ url: `/a/${encodeURIComponent(cfg.params.text)}.ogg`, type: 'audio/ogg' }] } }
    return { status: 200, data: {} }
  },
}

const A = await import('./listenAudio.js')
const { mixLevels } = await import('./listenMix.js')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const clipOf = (x, url = null) => { const b = new Buf(1, x.length, SR); b.d.set(x); return { buffer: b, rms: 0.2, url, duration_ms: Math.round(b.duration * 1000) } }
function reach(node, kind, seen = new Set()) {
  if (node.kind === kind) return true
  if (seen.has(node)) return false
  seen.add(node)
  for (const o of node.outs) if (reach(o, kind, seen)) return true
  return false
}
function viaLimiterToSpeaker(node, seen = new Set(), passed = false) {
  if (node.kind === 'dest') return passed
  if (seen.has(node)) return false
  seen.add(node)
  const p = passed || node.kind === 'limiter'
  for (const o of node.outs) if (viaLimiterToSpeaker(o, seen, p)) return true
  return false
}
const lastSrc = () => env.ctx.started[env.ctx.started.length - 1]
const playingCount = () => env.ctx.started.filter((s) => s.state === 'playing' && !s.loop).length

test('모든 재생 경로가 제한기를 거쳐 출력에 닿는다(보통·전화·방·보코더·소음·천천히)', async () => {
  const clip = clipOf(tone(0.04, 0.3, 0.01), '/a/x.ogg')
  const noise = { buffer: clipOf(tone(1.0)).buffer, rms: 0.2 }
  const cases = [{}, { phone: true }, { room: 0.3 }, { sim: 'ci' }, { snrDb: 5, noise, leadMs: 10 }, { sim: 'ci', snrDb: 5, noise, leadMs: 10 }]
  for (const o of cases) {
    const before = env.ctx?.started.length || 0
    assert.equal(await A.playClip(clip, { gainDb: -10, ...o }), true, JSON.stringify(Object.keys(o)))
    const mine = env.ctx.started.slice(before)
    assert.ok(mine.length >= 1)
  }
  // 그래프는 끝나면 끊기므로 재생 중에 확인한다
  for (const o of cases) {
    const p = A.playClip(clip, { gainDb: -10, ...o })
    await sleep(2)
    for (const s of env.ctx.started.filter((x) => x.state === 'playing')) assert.ok(viaLimiterToSpeaker(s), `제한기 우회: ${JSON.stringify(Object.keys(o))}`)
    await p
  }
  // 천천히(<audio> → MediaElementSource)도 같은 길
  const p = A.playClip(clip, { gainDb: -10, rate: 0.8 })
  await sleep(2)
  const me = env.ctx.media[env.ctx.media.length - 1]
  assert.ok(me && viaLimiterToSpeaker(me))
  assert.equal(await p, true)
})

test('전화 + 천천히는 던지지 않고 전화 대역 필터를 거친다(예전에는 phoneFilter가 없어 ReferenceError)', async () => {
  const clip = clipOf(tone(0.04), '/a/p.ogg')
  const p = A.playClip(clip, { gainDb: -10, phone: true, rate: 0.8 })
  await sleep(3)
  const me = env.ctx.media[env.ctx.media.length - 1]
  assert.ok(me.el.src.endsWith('/a/p.ogg'))
  let n = 0
  let x = me
  while (x && x.kind !== 'limiter') { if (x.kind === 'biquad') n += 1; x = [...x.outs][0] }
  assert.equal(n, 8)                      // 고역 4단 + 저역 4단
  assert.equal(await p, true)
})

test('음소거면 출력에 아예 잇지 않는다(이득 0이 아니라 연결 없음), <audio>도 음소거', async () => {
  store.set('liplab_mute', '1')
  try {
    assert.equal(A.isMuted(), true)
    const clip = clipOf(tone(0.04), '/a/m.ogg')
    for (const o of [{}, { phone: true }, { sim: 'ci' }, { rate: 0.8 }]) {
      const p = A.playClip(clip, { gainDb: 0, ...o })
      await sleep(3)
      for (const s of env.ctx.started.filter((x) => x.state === 'playing')) assert.equal(reach(s, 'dest'), false)
      for (const m of env.ctx.media) assert.equal(reach(m, 'dest'), false)
      if (o.rate) assert.equal(env.ctx.media[env.ctx.media.length - 1].el.muted, true)
      await p
    }
  } finally {
    store.delete('liplab_mute')
  }
  await A.ensureAudio()
  assert.equal(A.isMuted(), false)
})

test('빠르게 두 번 누르면 앞 재생은 시작하지 않는다(보코더 렌더 중 겹침)', async () => {
  env.offlineDelayMs = 40
  try {
    const a = clipOf(tone(0.05))
    const b = clipOf(tone(0.05))
    const before = env.ctx.started.length
    const p1 = A.playClip(a, { sim: 'ci' })
    await sleep(5)
    const p2 = A.playClip(b, {})
    await sleep(60)                        // a의 렌더가 끝났을 때
    assert.ok(playingCount() <= 1)
    assert.equal(await p1, false)
    assert.equal(await p2, true)
    const mine = env.ctx.started.slice(before)
    assert.equal(mine.length, 1)           // b 하나만 실제로 시작했다
    assert.equal(mine[0].buffer, b.buffer)
  } finally {
    env.offlineDelayMs = 0
  }
})

test('준비(전화 판 렌더) 중 stopAll이면 시작하지 않는다', async () => {
  env.offlineDelayMs = 30
  try {
    const before = env.ctx.started.length
    const p = A.playClip(clipOf(tone(0.05)), { phone: true })
    await sleep(5)
    A.stopAll()
    assert.equal(await p, false)
    await sleep(40)
    assert.equal(env.ctx.started.length, before)
  } finally {
    env.offlineDelayMs = 0
  }
})

test('두 소리 사이 쉼에 멈추면 둘째 소리를 내지 않는다', async () => {
  const a = clipOf(tone(0.03))
  const b = clipOf(tone(0.03))
  const before = env.ctx.started.length
  const p = A.playPair(a, b, {}, 150)
  await sleep(80)                          // a는 끝났고 쉬는 중
  A.stopAll()
  assert.equal(await p, false)
  assert.deepEqual(env.ctx.started.slice(before).map((s) => s.buffer), [a.buffer])
})

test('끝남 이벤트가 안 오면 보호 시간 뒤 풀고 소리도 멈춘다', async () => {
  env.autoEnd = false
  try {
    const t = Date.now()
    const p = A.playClip(clipOf(tone(0.02)), {})
    await sleep(2)
    const s = lastSrc()
    assert.equal(await p, true)
    const ms = Date.now() - t
    assert.ok(ms >= 1450 && ms < 2500, `${ms} ms`)
    assert.notEqual(s.state, 'playing')    // 예전에는 풀기만 하고 소리는 계속 남았다
    assert.equal(A.isPlaying(), false)
  } finally {
    env.autoEnd = true
  }
})

test('재개 약속이 풀리지 않아도(사용자 동작 밖 iOS) 재생 준비가 멈추지 않는다', async () => {
  env.resume = 'hang'
  env.ctx.state = 'suspended'
  env.autoEnd = false
  try {
    const t = Date.now()
    const ok = await A.playClip(clipOf(tone(0.02)), {})
    assert.equal(ok, true)                 // 보호 시간으로 풀림
    assert.ok(Date.now() - t < 4000)
  } finally {
    env.resume = 'ok'
    env.autoEnd = true
    await env.ctx.resume()
  }
})

test('잡음 꼬리(말이 끝난 뒤 0.45초)도 stopAll로 멈춘다', async () => {
  const noise = { buffer: clipOf(tone(1.0)).buffer, rms: 0.2 }
  const ok = await A.playClip(clipOf(tone(0.02)), { snrDb: 0, noise, leadMs: 5 })
  assert.equal(ok, true)
  const nz = env.ctx.started.filter((s) => s.loop).at(-1)
  assert.equal(nz.state, 'playing')
  assert.equal(A.isPlaying(), true)
  A.stopAll()
  await sleep(70)
  assert.equal(nz.state, 'stopped')
})

test('말소리 시작 알림(onStart)은 준비가 끝난 뒤 소음 앞부분만큼의 지연과 함께 온다', async () => {
  const noise = { buffer: clipOf(tone(1.0)).buffer, rms: 0.2 }
  const got = []
  await A.playClip(clipOf(tone(0.02)), { snrDb: 0, noise, leadMs: 300, onStart: (d) => got.push(d) })
  env.offlineDelayMs = 20
  try {
    const t = Date.now()
    let at = null
    await A.playClip(clipOf(tone(0.02)), { sim: 'ci', snrDb: 0, noise, leadMs: 300, onStart: (d) => { got.push(d); at = Date.now() - t } })
    assert.ok(at >= 18)                    // 보코더 렌더가 끝난 뒤
  } finally {
    env.offlineDelayMs = 0
  }
  assert.deepEqual(got, [300, 300])
})

test('못 받은 이유를 가른다: 준비 전(404)·연결 끊김·풀기 실패', async () => {
  assert.deepEqual(await A.loadClipResult('준비 전', 'v'), { clip: null, error: 'not_prepared' })
  assert.deepEqual(await A.loadClipResult('연결 끊김', 'v'), { clip: null, error: 'network' })
  env.decodeFail = true
  try {
    assert.equal((await A.loadClipResult('풀기 실패', 'v')).error, 'decode')
  } finally {
    env.decodeFail = false
  }
  const ok = await A.loadClipResult('정상', 'v')
  assert.equal(ok.error, null)
  assert.ok(ok.clip.buffer)
  assert.equal(await A.loadClip('준비 전', 'v'), null)   // 예전 형태(소리 또는 null)도 그대로
})

test('받은 소리 캐시는 상한을 넘지 않고, 풀기 실패는 기억하지 않는다', async () => {
  for (let i = 0; i < A.CLIP_CACHE_MAX + 20; i += 1) assert.ok(await A.loadClip(`글${i}`, 'v'))
  assert.ok(A.clipCacheSize() <= A.CLIP_CACHE_MAX)
  env.decodeFail = true
  try {
    assert.equal(await A.loadClip('깨진 파일', 'v'), null)
  } finally {
    env.decodeFail = false
  }
  const f = env.fetches
  assert.ok(await A.loadClip('깨진 파일', 'v'))   // 다시 받는다
  assert.equal(env.fetches, f + 1)
})

test('보코더 판(소음 먼저 섞음)의 크기는 SNR이 높아도 기준 크기 × 보코더 이득이다', async () => {
  // 말 앞뒤 무음 + 소음만 앞뒤 구간. 가짜 보코더는 입력을 0.37배로 낸다
  const sp = tone(0.6, 0.3, 0.3)
  const clip = clipOf(sp)
  const { activeLevel } = await import('./listenMix.js')
  clip.rms = activeLevel(sp, SR)
  const noise = { buffer: clipOf(tone(3.0, 0.2)).buffer, rms: 0.2 / Math.SQRT2 }
  const ref = mixLevels(0).speech
  const dB = (x) => 20 * Math.log10(x)
  for (const snr of [25, 10, -5]) {
    const v = await A.vocodedMix(clip, noise, snr, 500)
    assert.ok(Math.abs(dB(v.rms) - dB(ref * 0.37)) < 0.05, `snr ${snr}: ${dB(v.rms).toFixed(2)} vs ${dB(ref * 0.37).toFixed(2)}`)
  }
})
