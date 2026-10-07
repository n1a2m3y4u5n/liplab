/**
 * 소리 듣기(청능훈련) 트랙의 재생(Web Audio). 계산은 lib/listenMix.js에 두고 여기서는 소리를 받고 섞어 튼다.
 *
 *  - 소리: 소리 조건(C17)의 미리 합성한 서버 음성. GET /api/sound?text=&voice= → {available, sources, duration_ms, syllables}.
 *    파일은 받아서 풀고(decodeAudioData) RMS를 재 두었다가 목표 크기로 맞춘다. 못 받으면 null(화면이 '소리 준비 전'으로 알린다).
 *  - 잡음: /api/sound/noise/babble.{ogg,m4a}(여러 목소리를 겹친 잡담 잡음, 반복 재생).
 *  - 크기: 말+소음 전체 크기를 학습자가 맞춘 편안한 크기에 고정(listenMix.mixLevels). 끝에 제한기(-1 dBFS)를 둔다.
 *    말소리 크기는 무음을 뺀 활성 음성 레벨(ITU-T P.56, listenMix.activeLevel)이다. 전체 RMS를 쓰면 합성음 앞뒤 무음만큼 실제 SNR이
 *    표시값보다 높아진다(HINT·Matrix 검사도 무음을 뺀 레벨로 SNR을 정한다, docs/listen-advance-plan-2026-10.md F1).
 *  - 전화 소리: 오프라인으로 300 ~ 3400 Hz 8차 대역 통과 → 8 kHz 표본화 → G.711 μ-law 8비트 양자화한 소리를 미리 만든다(phoneClip).
 *    논문의 전화 모의는 6~9차 필터를 썼다(Liu 2009 등). 실제 통신망의 손실·코덱 차이는 재현하지 않는다.
 *  - 천천히: <audio>의 playbackRate 0.8(음높이 유지)로 같은 연결에 흘린다.
 *  - Ling 6소리: 오프라인으로 합성한다(대역을 정확히 맞추려고). 모음·콧소리는 톱니파를 공명 필터로, 쉬·스는 띠 잡음.
 *  - 재생은 한 번에 하나다. stopAll과 새 playClip은 재생 세대(playGen)를 올리고, 준비(재개·전화·방·보코더 렌더) 중에 세대가 바뀌면
 *    시작하지 않는다(빠르게 두 번 누르거나 렌더 중 다음 문항으로 가도 소리가 겹치지 않게). playClip은 실패해도 던지지 않고 false를 준다.
 *  - 메모리: 받은 소리는 개수 상한 캐시(CLIP_CACHE_MAX)에 두고, 전화·방·보코더 판은 원본 소리에 묶어(WeakMap) 원본이 버려지면 함께 버린다.
 */
import api from '../api'
import { mixLevels, gainFor, rmsOf, pickSource, activeLevel, createLru } from './listenMix'

let ctx = null
let limiter = null

// 재개 약속이 풀리지 않을 때(사용자 동작 밖에서 부른 resume을 Safari가 붙잡아 두는 경우) 재생 준비가 멈추지 않게 기다리는 상한
const RESUME_WAIT_MS = 800
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

export function audioContext() {
  if (!ctx) {
    const Ctx = window.AudioContext || window.webkitAudioContext
    ctx = new Ctx()
    limiter = ctx.createDynamicsCompressor()
    limiter.threshold.value = -1
    limiter.knee.value = 0
    limiter.ratio.value = 20
    limiter.attack.value = 0.002
    limiter.release.value = 0.1
    master = ctx.createGain()
    limiter.connect(master)
    syncMute()
  }
  return ctx
}

// 자동 점검(브라우저 테스트)용 음소거: window.__liplabMute = true 또는 localStorage·sessionStorage 'liplab_mute' = '1'이면 스피커에
// 아예 잇지 않는다(이득 0만으로 두지 않음). 재생 흐름·길이·끝남 이벤트는 그대로 돈다. 학습자 화면에는 이 스위치가 없다.
let master = null
let wired = false
export function isMuted() {
  try {
    return window.__liplabMute === true || window.localStorage?.getItem('liplab_mute') === '1'
      || window.sessionStorage?.getItem('liplab_mute') === '1'
  } catch { return window.__liplabMute === true }
}
function syncMute() {
  if (!master || !ctx) return
  const mute = isMuted()
  master.gain.value = mute ? 0 : 1
  if (mute && wired) { try { master.disconnect() } catch { /* 이미 끊김 */ } wired = false }
  if (!mute && !wired) { master.connect(ctx.destination); wired = true }
}

/**
 * 사용자 동작(누름) 안에서 동기로 불러 오디오를 깨운다. iOS Safari·Chrome은 사용자 동작 밖에서 부른 resume을 막으므로, 재생 전에
 * 다른 await(Ling 합성 등)가 있는 경로도 누른 순간 먼저 이것을 거치게 한다. iOS는 전화·알림 뒤 'interrupted'가 되므로 running이
 * 아니면 모두 깨운다. 반환: resume 약속(실패는 삼킨다).
 */
function primeAudio() {
  const c = audioContext()
  syncMute()
  if (c.state === 'running') return Promise.resolve()
  try { return Promise.resolve(c.resume()).catch(() => {}) } catch { return Promise.resolve() }
}

async function resume() {
  const p = primeAudio()
  if (ctx.state !== 'running') await Promise.race([p, wait(RESUME_WAIT_MS)])
  return ctx
}

/** 재생을 위해 오디오를 깨운다(출력 지연 값은 재생 중에만 의미가 있다). */
export async function ensureAudio() {
  return resume()
}

/**
 * 브라우저가 알린 출력 지연(ms, 블루투스 지연이 들어 있을 수 있음). 모르면 null.
 * Safari 18.4 전에는 없고, 재생 중이 아니면 0이며, 블루투스에서는 실제보다 작게 나온다는 보고가 있다(docs/listen-advance-evidence-2026-10.md).
 */
export function outputLatencyMs() {
  const v = ctx?.outputLatency
  return Number.isFinite(v) && v > 0 ? Math.round(v * 1000) : null
}

/**
 * 소리+입모양 시행에서 입모양을 늦출 시간. 소리가 입모양보다 앞서는 것은 30~45 ms만 넘어도 시청각 통합이 깨지지만, 늦는 것은
 * 170~200 ms까지 견딘다. 그래서 알려진 지연의 80%만, 250 ms까지만 보정한다(덜 보정해서 소리가 앞서지 않게).
 */
export function avOffsetMs() {
  const lat = outputLatencyMs()
  return lat ? Math.min(250, Math.round(lat * 0.8)) : 0
}

const canPlay = (type) => {
  try { return new Audio().canPlayType(type) } catch { return '' }
}

// `${voice}\n${text}` → Promise<clip|null>. 한 묶음(소리 구별 12문항 = 소리 24개, 대화 8문항 = 말·다른 말 16개)과 앞 묶음 일부가
// 들어가는 크기. 문장 3초 기준 40개면 풀어 둔 소리가 약 23 MB다(48 kHz 모노 float32). 화면이 쥔 소리는 버려져도 화면에서 계속 쓸 수 있다.
export const CLIP_CACHE_MAX = 40
const clipCache = createLru(CLIP_CACHE_MAX)

/**
 * 글 하나의 소리와 못 받은 이유. {clip, error}: clip은 {buffer, rms, url, duration_ms, syllables} 또는 null,
 * error는 null | 'not_prepared'(서버에 아직 합성된 소리가 없음, 404·available false) | 'network'(목록·파일을 받지 못함: 연결 끊김·
 * 시간 초과·5xx) | 'decode'(받았지만 이 브라우저가 풀지 못함, 풀 수 있는 형식이 없음 포함).
 * 예전에는 모두 null이라 화면이 '준비 전'과 '연결 끊김'을 가르지 못했다. 실패는 기억하지 않는다(다음에 다시 받는다).
 */
export function loadClipResult(text, voice = '') {
  const key = `${voice}\n${text}`
  if (!clipCache.has(key)) {
    const p = (async () => {
      let d
      try {
        const r = await api.get('/sound', { params: voice ? { text, voice } : { text }, validateStatus: (s) => s === 200 || s === 404 })
        d = r.status === 404 ? null : r.data
      } catch { return { clip: null, error: 'network' } }
      if (!d?.available) return { clip: null, error: 'not_prepared' }
      const url = pickSource(d.sources, canPlay)
      if (!url) return { clip: null, error: 'decode' }
      let buf
      try {
        const res = await fetch(url)
        if (!res.ok) return { clip: null, error: res.status === 404 ? 'not_prepared' : 'network' }
        buf = await res.arrayBuffer()
      } catch { return { clip: null, error: 'network' } }
      try {
        const buffer = await audioContext().decodeAudioData(buf.slice(0))
        const ch = buffer.getChannelData(0)
        return { clip: { buffer, rms: activeLevel(ch, buffer.sampleRate) || rmsOf(ch), url, duration_ms: d.duration_ms || Math.round(buffer.duration * 1000),
          syllables: d.syllables || null, voice: d.voice ?? voice }, error: null }
      } catch { return { clip: null, error: 'decode' } }
    })()
    clipCache.set(key, p)
    p.then((v) => { if (!v.clip && clipCache.get(key) === p) clipCache.delete(key) })
  }
  return clipCache.get(key)
}

/** 글 하나의 소리. {buffer, rms, url, duration_ms, syllables} 또는 null(준비 전·실패, 이유는 loadClipResult). */
export function loadClip(text, voice = '') {
  return loadClipResult(text, voice).then((r) => r.clip)
}

/** 시험용: 캐시에 든 소리 수. */
export function clipCacheSize() { return clipCache.size }

let voicesP = null
/** 목소리 목록 [{id, label, sex}]. 못 받으면 기본 목소리 하나. */
export function loadVoices() {
  if (!voicesP) {
    voicesP = api.get('/sound/voices').then((r) => (r.data?.voices?.length ? r.data.voices : [{ id: '', label: '기본' }]))
      .catch(() => { voicesP = null; return [{ id: '', label: '기본' }] })
  }
  return voicesP
}

const noiseP = new Map()
/** 잡음 {buffer, rms} 또는 null. name: babble(8명 이상 잡담, 기본)·talker1_f·talker1_m(경쟁 화자 1명)·talker2·ssn(말소리 모양 정상 잡음). */
export function loadNoise(name = 'babble') {
  if (!noiseP.has(name)) {
    const p = (async () => {
      const order = canPlay('audio/ogg; codecs=opus') ? ['ogg', 'm4a'] : ['m4a', 'ogg']
      for (const ext of order) {
        try {
          const res = await fetch(`/api/sound/noise/${name}.${ext}`)
          if (!res.ok) continue
          const buffer = await audioContext().decodeAudioData(await res.arrayBuffer())
          const rms = rmsOf(buffer.getChannelData(0))   // 잡음은 쉬지 않고 이어지므로 전체 RMS
          if (rms > 0) return { buffer, rms, name }
        } catch { /* 다음 형식 */ }
      }
      return null
    })()
    noiseP.set(name, p)
    p.then((v) => { if (!v) noiseP.delete(name) })
  }
  return noiseP.get(name)
}

// 버터워스 8차(2차 단 4개) 단별 Q
const BUTTER8_Q = [0.5098, 0.6013, 0.9000, 2.5629]

/** 실시간 전화 대역(천천히 재생처럼 미리 만든 판을 못 쓸 때). 미리 만든 판과 같은 8차 고역 + 8차 저역. 반환: 마지막 필터. */
function phoneFilter(c, input) {
  let node = input
  for (const q of BUTTER8_Q) {
    const hp = c.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 300; hp.Q.value = q
    node.connect(hp); node = hp
  }
  for (const q of BUTTER8_Q) {
    const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 3400; lp.Q.value = q
    node.connect(lp); node = lp
  }
  return node
}

// 원본 소리 → 만든 판의 약속. 같은 소리를 빠르게 두 번 눌러도 한 번만 렌더한다. 실패하면 지워 다음에 다시 만든다
function memo(cache, clip, make) {
  if (cache.has(clip)) return cache.get(clip)
  const p = make().catch(() => null)
  cache.set(clip, p)
  p.then((v) => { if (!v && cache.get(clip) === p) cache.delete(clip) })
  return p
}

const phoneCache = new WeakMap()

/** 전화 소리판: 8차 대역 통과(300 ~ 3400 Hz) → 8 kHz → μ-law 8비트. 실패하면 null(재생은 실시간 필터로 대신한다). */
export function phoneClip(clip) {
  if (!clip?.buffer) return Promise.resolve(null)
  return memo(phoneCache, clip, () => renderPhone(clip))
}

async function renderPhone(clip) {
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext
  const sr = 8000
  const oc = new OAC(1, Math.ceil(clip.buffer.duration * sr), sr)
  const src = oc.createBufferSource()
  src.buffer = clip.buffer
  phoneFilter(oc, src).connect(oc.destination)
  src.start(0)
  const out = await oc.startRendering()
  const x = out.getChannelData(0)
  // μ-law(μ=255) 압축 → 8비트 양자화 → 복원
  const MU = 255
  let peak = 0
  for (let i = 0; i < x.length; i += 1) peak = Math.max(peak, Math.abs(x[i]))
  const norm = peak > 0 ? 0.98 / peak : 1
  for (let i = 0; i < x.length; i += 1) {
    const v = x[i] * norm
    const y = Math.sign(v) * Math.log1p(MU * Math.abs(v)) / Math.log1p(MU)
    const qy = Math.round(y * 127) / 127
    x[i] = (Math.sign(qy) * (Math.expm1(Math.abs(qy) * Math.log1p(MU)) / MU)) / norm
  }
  return { buffer: out, rms: activeLevel(x, sr) || rmsOf(x), url: null, duration_ms: clip.duration_ms }
}

const roomCache = new WeakMap()   // 원본 소리 → Map(rt60 → 약속)

/**
 * 울리는 방 소리판(5단계 '울리는 방'). 지수 감쇠 잡음 임펄스 응답(RT60에서 60 dB 감쇠, 길이 RT60 × 1.2)을 오프라인으로 걸고, 직접음과
 * 잔향음 에너지를 같게 섞는다. 크기는 다시 활성 음성 레벨로 잰다. 합성 임펄스 응답이라 실제 방의 초기 반사는 재현하지 않는다.
 */
export function roomClip(clip, rt60 = 0.5) {
  if (!clip?.buffer) return Promise.resolve(null)
  if (!roomCache.has(clip)) roomCache.set(clip, new Map())
  const byRt = roomCache.get(clip)
  if (byRt.has(rt60)) return byRt.get(rt60)
  const p = renderRoom(clip, rt60).catch(() => null)
  byRt.set(rt60, p)
  p.then((v) => { if (!v && byRt.get(rt60) === p) byRt.delete(rt60) })
  return p
}

async function renderRoom(clip, rt60) {
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext
  const sr = clip.buffer.sampleRate
  const irLen = Math.round(sr * rt60 * 1.2)
  const oc = new OAC(1, clip.buffer.length + irLen, sr)
  const ir = oc.createBuffer(1, irLen, sr)
  const h = ir.getChannelData(0)
  let e = 0
  for (let i = 0; i < irLen; i += 1) {
    h[i] = (Math.random() * 2 - 1) * Math.exp(-6.91 * (i / sr) / rt60)
    e += h[i] * h[i]
  }
  const k = e > 0 ? 1 / Math.sqrt(e) : 1   // 잔향음 에너지 = 직접음 에너지
  for (let i = 0; i < irLen; i += 1) h[i] *= k
  const src = oc.createBufferSource()
  src.buffer = clip.buffer
  const conv = oc.createConvolver()
  conv.normalize = false
  conv.buffer = ir
  src.connect(conv).connect(oc.destination)
  src.connect(oc.destination)
  src.start(0)
  const out = await oc.startRendering()
  const x = out.getChannelData(0)
  return { buffer: out, rms: activeLevel(x, sr) || rmsOf(x), url: null, duration_ms: Math.round(out.duration * 1000) }
}

// ── 인공와우 모의(청인 예비 파일럿, docs/listen-advance-plan-2026-10.md V2) ─────────────────────────────
// 8채널 잡음 보코더(Shannon 1995 계열). 대역 200 ~ 7000 Hz를 Greenwood 함수로 나눠 각 대역의 포락선(전파 정류 → 160 Hz 저역 통과)으로
// 같은 대역의 잡음을 변조해 더한다. 소음 속 문항은 말과 소음을 먼저 섞은 뒤 보코더를 건다(어음처리기는 섞인 소리를 받는다).
// 청인 참여자가 '들리기 어려운 말소리'를 학습하는 조건을 만들 뿐, 실제 인공와우 청취를 재현하지는 않는다.
const VOC = { channels: 8, lo: 200, hi: 7000, envCut: 160 }
let simMode = null
/** 이 기기의 모의 청취 모드('ci' 또는 null). 소리 듣기 화면이 설정에서 정한다. playClip의 opts.sim이 없으면 이 값을 쓴다. */
export function setSimMode(mode) {
  simMode = mode === 'ci' ? 'ci' : null
  globalThis.__liplabListenSim = simMode   // api.js가 기록에 붙인다(순환 import를 피하려고 전역으로 넘김)
}
export function getSimMode() { return simMode }

export function greenwoodEdges(n = VOC.channels, lo = VOC.lo, hi = VOC.hi) {
  const A = 165.4, a = 2.1, k = 0.88
  const pos = (f) => Math.log10(f / A + k) / a
  const frq = (x) => A * (10 ** (a * x) - k)
  const x0 = pos(lo)
  const x1 = pos(hi)
  return Array.from({ length: n + 1 }, (_, i) => frq(x0 + ((x1 - x0) * i) / n))
}

async function vocodeBuffer(buffer) {
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext
  const sr = buffer.sampleRate
  const oc = new OAC(1, buffer.length, sr)
  const edges = greenwoodEdges()
  const src = oc.createBufferSource()
  src.buffer = buffer
  const nb = oc.createBuffer(1, buffer.length, sr)
  const nd = nb.getChannelData(0)
  for (let i = 0; i < nd.length; i += 1) nd[i] = Math.random() * 2 - 1
  const noise = oc.createBufferSource()
  noise.buffer = nb
  const rect = oc.createWaveShaper()
  const curve = new Float32Array(1025)
  for (let i = 0; i < curve.length; i += 1) curve[i] = Math.abs((i / 512) - 1)
  rect.curve = curve
  const band = (input, f1, f2) => {
    const fc = Math.sqrt(f1 * f2)
    const q = fc / (f2 - f1)
    let node = input
    for (let j = 0; j < 2; j += 1) {   // 2단(4차) 대역 통과
      const bp = oc.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = fc; bp.Q.value = q
      node.connect(bp); node = bp
    }
    return node
  }
  for (let c = 0; c < edges.length - 1; c += 1) {
    const sb = band(src, edges[c], edges[c + 1])
    const r = oc.createWaveShaper(); r.curve = curve
    sb.connect(r)
    let env = r
    for (let j = 0; j < 2; j += 1) {
      const lp = oc.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = VOC.envCut; lp.Q.value = 0.707
      env.connect(lp); env = lp
    }
    const carrier = band(noise, edges[c], edges[c + 1])
    const vca = oc.createGain()
    vca.gain.value = 0
    env.connect(vca.gain)     // 포락선이 잡음 대역의 크기를 정한다
    carrier.connect(vca)
    const post = band(vca, edges[c], edges[c + 1])
    post.connect(oc.destination)
  }
  src.start(0)
  noise.start(0)
  return oc.startRendering()
}

const vocCache = new WeakMap()

/** 보코더 판(소음 없음). */
export function vocodedClip(clip) {
  if (!clip?.buffer) return Promise.resolve(null)
  return memo(vocCache, clip, async () => {
    const out = await vocodeBuffer(clip.buffer)
    const x = out.getChannelData(0)
    return { buffer: out, rms: activeLevel(x, out.sampleRate) || rmsOf(x), url: null, duration_ms: clip.duration_ms }
  })
}

/**
 * 말과 소음을 SNR로 먼저 섞은 뒤 보코더를 건 판. 앞 leadMs·뒤 300 ms는 소음만.
 * 크기: 섞기 전 소리는 말(활성 레벨) + 소음의 합이 기준 크기 mixLevels(0)이 되게 만들었으므로, 보코더가 바꾼 비율(출력 RMS / 입력 RMS)만큼
 * 기준 크기를 옮긴 값을 이 판의 크기로 돌려준다. 예전에는 출력 전체 RMS를 썼는데, SNR이 높으면 앞뒤 소음만 구간과 말 사이 쉼이 거의
 * 무음이라 RMS가 낮게 나와 그만큼 더 크게 틀었다(보코더 없는 판보다 최대 몇 dB 큼, 편안한 크기 고정 원칙 위반).
 */
export async function vocodedMix(clip, noise, snrDb, leadMs = 500) {
  if (!clip?.buffer || !noise?.buffer) return null
  try {
    const sr = clip.buffer.sampleRate
    const lead = Math.round((leadMs / 1000) * sr)
    const tail = Math.round(0.3 * sr)
    const len = lead + clip.buffer.length + tail
    const mix = new Float32Array(len)
    const sp = clip.buffer.getChannelData(0)
    const nz = noise.buffer.getChannelData(0)
    const lv = mixLevels(0, snrDb)
    const gs = gainFor(lv.speech, clip.rms)
    const gn = gainFor(lv.noise, noise.rms)
    const off = Math.floor(Math.random() * Math.max(1, nz.length - len))
    for (let i = 0; i < len; i += 1) mix[i] = gn * nz[(off + i) % nz.length]
    for (let i = 0; i < sp.length; i += 1) mix[lead + i] += gs * sp[i]
    const buf = audioContext().createBuffer(1, len, sr)
    buf.copyToChannel(mix, 0)
    const out = await vocodeBuffer(buf)
    const x = out.getChannelData(0)
    const inRms = rmsOf(mix)
    const rms = inRms > 0 ? mixLevels(0).speech * (rmsOf(x) / inRms) : rmsOf(x)
    return { buffer: out, rms, url: null, duration_ms: Math.round(out.duration * 1000) }
  } catch { return null }
}

let current = null
let playGen = 0   // 재생 세대: stopAll·새 playClip마다 올린다. 준비 중(await 뒤) 세대가 바뀌었으면 그 재생은 시작하지 않는다

/** 지금 재생 중인 소리(준비 중인 것과 끝난 뒤 잡음 꼬리 포함)를 멈춘다. */
export function stopAll() {
  playGen += 1
  const cur = current
  current = null
  cur?.stop()
}

/** 지금 소리가 나는 중인가(끝난 뒤 잡음 꼬리 포함). 시험·점검용. */
export function isPlaying() { return current != null }

/**
 * 소리 하나를 튼다. opts: gainDb(편안한 크기), snrDb(null이면 소음 없음), noise(loadNoise 결과), phone(전화 대역), rate(1 또는 0.8),
 * leadMs(소음을 말보다 먼저 트는 시간, 기본 500), room(잔향 시간 초), sim('ci'면 보코더),
 * onStart(delayMs)(말소리가 delayMs 뒤 그래프에서 나온다는 알림, 출력 장치 지연은 빼고. 보코더·전화·방 판을 만드는 시간이 지난 뒤
 * 불리므로 소리+입모양 시행은 이것에 맞춰 입모양을 시작해야 한다).
 * 반환: Promise<boolean>(말이 끝나면 true, 멈췄거나 시작하지 못하면 false). 앞선 재생은 멈춘다. 던지지 않는다.
 */
export async function playClip(clip, opts = {}) {
  if (!clip) return false
  stopAll()
  const gen = playGen
  try {
    return await playInner(clip, opts, gen)
  } catch (e) {
    if (gen === playGen) stopAll()
    console.warn('[listenAudio] 재생 실패', e)   // eslint-disable-line no-console
    return false
  }
}

async function playInner(clip, opts, gen) {
  const live = () => gen === playGen
  const c = await resume()
  if (!live()) return false
  let { snrDb = null, noise = null, leadMs = noise && snrDb != null ? 500 : 0, phone = false } = opts
  const { gainDb = -10, rate = 1 } = opts
  // 전화 소리는 미리 만든 판을 쓴다. 천천히 재생은 <audio>라 같은 대역의 실시간 필터로 대신하고, 크기는 미리 만든 판의 레벨을 쓴다
  // (300 Hz 아래가 빠진 만큼 원본 레벨보다 작으므로 원본 레벨로 맞추면 천천히만 더 작게 들린다)
  let levelRms = null
  if (phone) {
    const pc = await phoneClip(clip)
    if (!live()) return false
    if (pc && rate === 1) { clip = pc; phone = false } else if (pc) levelRms = pc.rms
  }
  // 울리는 방: 미리 만든 잔향판(천천히 재생에는 걸지 않는다)
  if (opts.room && rate === 1) {
    const rc = await roomClip(clip, opts.room)
    if (!live()) return false
    if (rc) clip = rc
  }
  // 인공와우 모의: 보코더 판으로 바꾸고(소음은 먼저 섞음), 재생 속도는 버퍼 재생 속도로 대신한다
  let vocoded = false
  let speechInBufferMs = 0   // 판 안에서 말소리가 시작하는 시각(보코더 판은 소음만 앞부분을 안에 담는다)
  if ((opts.sim ?? simMode) === 'ci') {
    const mixed = noise && snrDb != null
    const vc = mixed ? await vocodedMix(clip, noise, snrDb, leadMs) : await vocodedClip(clip)
    if (!live()) return false
    if (vc) {
      clip = vc
      vocoded = true
      if (mixed) speechInBufferMs = leadMs
      noise = null
      snrDb = null
      levelRms = null
      leadMs = 0
    }
  }
  const lv = mixLevels(gainDb, noise && snrDb != null ? snrDb : null)
  const out = c.createGain()
  out.gain.value = 1
  out.connect(limiter)
  const into = (node) => (phone ? phoneFilter(c, node).connect(out) : node.connect(out))
  let noiseSrc = null
  let ng = null
  const noiseGain = noise && snrDb != null ? gainFor(lv.noise, noise.rms) : 0
  if (noise && snrDb != null) {
    noiseSrc = c.createBufferSource()
    noiseSrc.buffer = noise.buffer
    noiseSrc.loop = true
    ng = c.createGain()
    ng.gain.value = 0
    noiseSrc.connect(ng)
    into(ng)
    const t0 = c.currentTime
    ng.gain.setValueAtTime(0, t0)
    ng.gain.linearRampToValueAtTime(noiseGain, t0 + 0.15)   // 잡음은 짧게 키우며 시작(딸깍 소리 없게)
    noiseSrc.start(t0, Math.random() * Math.max(0, noise.buffer.duration - 1))
  }
  const sg = c.createGain()
  sg.gain.value = gainFor(lv.speech, levelRms || clip.rms)
  into(sg)
  let resolve
  const finished = new Promise((r) => { resolve = r })
  let settled = false
  let guard = null
  const finish = (ok) => { if (settled) return; settled = true; clearTimeout(guard); resolve(ok) }
  let el = null
  let me = null
  let src = null
  let cleaned = false
  const cleanup = () => {
    if (cleaned) return
    cleaned = true
    try { src?.stop() } catch { /* 이미 멈춤 */ }
    try { el?.pause() } catch { /* 이미 멈춤 */ }
    try { noiseSrc?.stop() } catch { /* 이미 멈춤 */ }
    try { me?.disconnect() } catch { /* 끊김 */ }
    try { out.disconnect() } catch { /* 끊김 */ }
  }
  const handle = {
    stop: () => {
      finish(false)
      // 바로 끊으면 딸깍 소리가 날 수 있어 아주 짧게 줄인 뒤 끊는다
      try { out.gain.setTargetAtTime(0, c.currentTime, 0.01) } catch { /* 무시 */ }
      setTimeout(cleanup, 50)
    },
  }
  current = handle
  // 끝남 이벤트가 오지 않을 때(창이 가려져 오디오가 멈춤, 출력 장치가 바뀜 등) 화면이 '듣는 중'에 멈추지 않게 소리 길이 + 여유 뒤에
  // 풀고 소리도 멈춘다(예전에는 풀기만 해서 오디오가 되살아나면 다음 문항 소리와 겹쳤고 stopAll로도 멈출 수 없었다)
  const playMs = (clip.buffer?.duration || clip.duration_ms / 1000 || 3) * 1000 / Math.min(1, rate)
  const armGuard = (ms) => { clearTimeout(guard); guard = setTimeout(() => { cleanup(); finish(true) }, ms) }
  const started = (delayMs) => { try { opts.onStart?.(delayMs) } catch { /* 화면 콜백 오류는 재생을 막지 않는다 */ } }
  if (rate !== 1 && clip.url && !vocoded) {
    el = new Audio()
    el.crossOrigin = 'anonymous'
    el.src = clip.url
    if (isMuted()) { el.muted = true; el.volume = 0 }
    el.preservesPitch = true
    el.playbackRate = rate
    me = c.createMediaElementSource(el)
    me.connect(sg)
    el.onended = () => finish(true)
    el.onerror = () => { cleanup(); finish(false) }
    // 보호 시간은 실제로 소리가 나기 시작한 뒤부터 잰다(파일을 다시 받는 동안 끊지 않게). 그 전에는 받기 상한만 둔다
    el.addEventListener('playing', () => { armGuard(playMs + 1500); started(0) }, { once: true })
    armGuard(leadMs + 10000)
    setTimeout(() => { if (!settled) el.play().catch(() => { cleanup(); finish(false) }) }, leadMs)
  } else {
    src = c.createBufferSource()
    src.buffer = clip.buffer
    if (rate !== 1) src.playbackRate.value = rate
    src.connect(sg)
    src.onended = () => finish(true)
    src.start(c.currentTime + leadMs / 1000)
    armGuard(leadMs + playMs + 1500)
    started(leadMs + speechInBufferMs)
  }
  const ok = await finished
  if (current !== handle) return ok   // 멈춤(stopAll) 또는 새 재생: 정리는 stop이 한다
  if (noiseSrc && ok) {
    // 말이 끝난 뒤 잡음은 0.3초 더 두었다가 줄여 끈다. 그동안도 current로 두어 stopAll이 꼬리까지 멈추게 한다
    const t = c.currentTime + 0.3
    ng.gain.cancelScheduledValues(t)
    ng.gain.setValueAtTime(noiseGain, t)
    ng.gain.linearRampToValueAtTime(0, t + 0.15)
    setTimeout(() => { cleanup(); if (current === handle) current = null }, 500)
  } else {
    cleanup()
    current = null
  }
  return ok
}

/** 두 소리를 차례로(소리 구별). 사이 쉼 gapMs. 쉬는 동안 stopAll이나 다른 재생이 오면 둘째 소리는 내지 않는다. */
export async function playPair(a, b, opts = {}, gapMs = 600) {
  const ok = await playClip(a, opts)
  if (!ok) return false
  const gen = playGen
  await wait(gapMs)
  if (gen !== playGen) return false
  return playClip(b, opts)
}

// ── Ling 6소리 합성 ─────────────────────────────────────────────
const LING_SPEC = {
  m: { kind: 'voice', f0: 120, formants: [[250, 6, 1]], lowpass: 350 },
  u: { kind: 'voice', f0: 130, formants: [[330, 8, 1], [800, 8, 0.5], [2300, 10, 0.05]] },
  a: { kind: 'voice', f0: 130, formants: [[800, 7, 1], [1250, 8, 0.6], [2600, 10, 0.15]] },
  i: { kind: 'voice', f0: 130, formants: [[300, 8, 1], [2300, 10, 0.5], [3100, 10, 0.3]] },
  sh: { kind: 'noise', bands: [[2400, 1.2, 0.8], [3600, 1.5, 1]], highpass: 1800 },
  s: { kind: 'noise', bands: [[5500, 1.0, 1], [7500, 1.2, 0.8]], highpass: 4000 },
}
const lingCache = new Map()

/** Ling 소리 하나의 {buffer, rms}. 길이 1.4초, 앞뒤 0.1초에 걸쳐 크기를 올리고 내린다. */
export async function lingClip(key) {
  // 화면은 누른 순간 이것을 부르고 합성(await) 뒤에 playClip을 부른다. 그때는 사용자 동작 밖이라 iOS가 재개를 막으므로 여기서 먼저 깨운다
  try { primeAudio() } catch { /* 오디오가 없는 환경 */ }
  if (lingCache.has(key)) return lingCache.get(key)
  const spec = LING_SPEC[key]
  if (!spec) return null
  const sr = 48000
  const dur = 1.4
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext
  const oc = new OAC(1, Math.round(sr * dur), sr)
  const env = oc.createGain()
  env.gain.setValueAtTime(0, 0)
  env.gain.linearRampToValueAtTime(1, 0.1)
  env.gain.setValueAtTime(1, dur - 0.1)
  env.gain.linearRampToValueAtTime(0, dur)
  env.connect(oc.destination)
  let src
  const sum = oc.createGain()
  if (spec.kind === 'voice') {
    src = oc.createOscillator()
    src.type = 'sawtooth'
    src.frequency.value = spec.f0
    for (const [f, q, g] of spec.formants) {
      const bp = oc.createBiquadFilter()
      bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = q
      const gg = oc.createGain()
      gg.gain.value = g
      src.connect(bp).connect(gg).connect(sum)
    }
    if (spec.lowpass) {
      const lp = oc.createBiquadFilter()
      lp.type = 'lowpass'; lp.frequency.value = spec.lowpass
      sum.connect(lp).connect(env)
    } else sum.connect(env)
  } else {
    const nb = oc.createBuffer(1, Math.round(sr * dur), sr)
    const ch = nb.getChannelData(0)
    for (let i = 0; i < ch.length; i += 1) ch[i] = Math.random() * 2 - 1
    src = oc.createBufferSource()
    src.buffer = nb
    const hp = oc.createBiquadFilter()
    hp.type = 'highpass'; hp.frequency.value = spec.highpass
    src.connect(hp)
    for (const [f, q, g] of spec.bands) {
      const bp = oc.createBiquadFilter()
      bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = q
      const gg = oc.createGain()
      gg.gain.value = g
      hp.connect(bp).connect(gg).connect(sum)
    }
    sum.connect(env)
  }
  src.start(0)
  const buffer = await oc.startRendering()
  // 크기는 가운데(오르내림 제외) 구간으로 잰다
  const ch0 = buffer.getChannelData(0)
  const mid = ch0.subarray(Math.round(sr * 0.1), Math.round(sr * (dur - 0.1)))
  const clip = { buffer, rms: rmsOf(mid), url: null, duration_ms: dur * 1000 }
  lingCache.set(key, clip)
  return clip
}

/** 소리 없는 시행용: 같은 길이만큼 기다린다. */
export function silence(ms = 1400) {
  stopAll()
  return new Promise((r) => setTimeout(() => r(true), ms))
}
