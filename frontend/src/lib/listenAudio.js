/**
 * 소리 듣기(청능훈련) 트랙의 재생(Web Audio). 계산은 lib/listenMix.js에 두고 여기서는 소리를 받고 섞어 튼다.
 *
 *  - 소리: 소리 조건(C17)의 미리 합성한 서버 음성. GET /api/sound?text=&voice= → {available, sources, duration_ms, syllables}.
 *    파일은 받아서 풀고(decodeAudioData) RMS를 재 두었다가 목표 크기로 맞춘다. 못 받으면 null(화면이 '소리 준비 전'으로 알린다).
 *  - 잡음: /api/sound/noise/babble.{ogg,m4a}(여러 목소리를 겹친 잡담 잡음, 반복 재생).
 *  - 크기: 말+소음 전체 크기를 학습자가 맞춘 편안한 크기에 고정(listenMix.mixLevels). 끝에 제한기(-1 dBFS)를 둔다.
 *  - 전화 소리: 300 ~ 3400 Hz 대역만 통과(5단계 선택).
 *  - 천천히: <audio>의 playbackRate 0.8(음높이 유지)로 같은 연결에 흘린다.
 *  - Ling 6소리: 오프라인으로 합성한다(대역을 정확히 맞추려고). 모음·콧소리는 톱니파를 공명 필터로, 쉬·스는 띠 잡음.
 */
import api from '../api'
import { mixLevels, gainFor, rmsOf, pickSource } from './listenMix'

let ctx = null
let limiter = null

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
    master.gain.value = isMuted() ? 0 : 1
    limiter.connect(master).connect(ctx.destination)
  }
  return ctx
}

// 자동 점검(브라우저 테스트)용 음소거: window.__liplabMute = true 또는 sessionStorage 'liplab_mute' = '1'이면 출력 이득 0.
// 재생 흐름·길이·끝남 이벤트는 그대로 돈다. 학습자 화면에는 이 스위치가 없다.
let master = null
function isMuted() {
  try { return window.__liplabMute === true || window.sessionStorage?.getItem('liplab_mute') === '1' } catch { return window.__liplabMute === true }
}
function syncMute() {
  if (master) master.gain.value = isMuted() ? 0 : 1
}

async function resume() {
  const c = audioContext()
  syncMute()
  if (c.state === 'suspended') await c.resume()
  return c
}

const canPlay = (type) => {
  try { return new Audio().canPlayType(type) } catch { return '' }
}

const clipCache = new Map()   // `${voice}\n${text}` → Promise<clip|null>

/** 글 하나의 소리. {buffer, rms, url, duration_ms, syllables} 또는 null(준비 전·실패). */
export function loadClip(text, voice = '') {
  const key = `${voice}\n${text}`
  if (!clipCache.has(key)) {
    const p = (async () => {
      try {
        const r = await api.get('/sound', { params: voice ? { text, voice } : { text }, validateStatus: (s) => s === 200 || s === 404 })
        const d = r.data
        if (!d?.available) return null
        const url = pickSource(d.sources, canPlay)
        if (!url) return null
        const buf = await (await fetch(url)).arrayBuffer()
        const c = audioContext()
        const buffer = await c.decodeAudioData(buf.slice(0))
        return { buffer, rms: rmsOf(buffer.getChannelData(0)), url, duration_ms: d.duration_ms || Math.round(buffer.duration * 1000),
          syllables: d.syllables || null, voice: d.voice ?? voice }
      } catch { return null }
    })()
    clipCache.set(key, p)
    p.then((v) => { if (!v) clipCache.delete(key) })   // 실패는 기억하지 않는다(다음에 다시 받는다)
  }
  return clipCache.get(key)
}

let voicesP = null
/** 목소리 목록 [{id, label, sex}]. 못 받으면 기본 목소리 하나. */
export function loadVoices() {
  if (!voicesP) {
    voicesP = api.get('/sound/voices').then((r) => (r.data?.voices?.length ? r.data.voices : [{ id: '', label: '기본' }]))
      .catch(() => { voicesP = null; return [{ id: '', label: '기본' }] })
  }
  return voicesP
}

let noiseP = null
/** 잡담 잡음 {buffer, rms} 또는 null. */
export function loadNoise() {
  if (!noiseP) {
    noiseP = (async () => {
      const order = canPlay('audio/ogg; codecs=opus') ? ['babble.ogg', 'babble.m4a'] : ['babble.m4a', 'babble.ogg']
      for (const name of order) {
        try {
          const res = await fetch(`/api/sound/noise/${name}`)
          if (!res.ok) continue
          const buffer = await audioContext().decodeAudioData(await res.arrayBuffer())
          const rms = rmsOf(buffer.getChannelData(0))
          if (rms > 0) return { buffer, rms }
        } catch { /* 다음 형식 */ }
      }
      return null
    })()
    noiseP.then((v) => { if (!v) noiseP = null })
  }
  return noiseP
}

function phoneFilter(c, input) {
  const hp = c.createBiquadFilter()
  hp.type = 'highpass'; hp.frequency.value = 300; hp.Q.value = 0.7
  const lp = c.createBiquadFilter()
  lp.type = 'lowpass'; lp.frequency.value = 3400; lp.Q.value = 0.7
  input.connect(hp).connect(lp)
  return lp
}

let current = null
/** 지금 재생 중인 소리를 멈춘다. */
export function stopAll() {
  const cur = current
  current = null
  cur?.stop()
}

/**
 * 소리 하나를 튼다. opts: gainDb(편안한 크기), snrDb(null이면 소음 없음), noise(loadNoise 결과), phone(전화 대역), rate(1 또는 0.8),
 * leadMs(소음을 말보다 먼저 트는 시간, 기본 500). 반환: Promise(말이 끝나면 풀림). 앞선 재생은 멈춘다.
 */
export async function playClip(clip, opts = {}) {
  if (!clip) return false
  stopAll()
  const c = await resume()
  const { gainDb = -10, snrDb = null, noise = null, phone = false, rate = 1, leadMs = noise && snrDb != null ? 500 : 0 } = opts
  const lv = mixLevels(gainDb, noise && snrDb != null ? snrDb : null)
  const out = c.createGain()
  out.gain.value = 1
  out.connect(limiter)
  const into = (node) => (phone ? phoneFilter(c, node).connect(out) : node.connect(out))
  const nodes = []
  let noiseSrc = null
  if (noise && snrDb != null) {
    noiseSrc = c.createBufferSource()
    noiseSrc.buffer = noise.buffer
    noiseSrc.loop = true
    const ng = c.createGain()
    ng.gain.value = 0
    noiseSrc.connect(ng)
    into(ng)
    const t0 = c.currentTime
    ng.gain.setValueAtTime(0, t0)
    ng.gain.linearRampToValueAtTime(gainFor(lv.noise, noise.rms), t0 + 0.15)   // 잡음은 짧게 키우며 시작(딸깍 소리 없게)
    noiseSrc.start(t0, Math.random() * Math.max(0, noise.buffer.duration - 1))
    nodes.push(noiseSrc, ng)
  }
  const sg = c.createGain()
  sg.gain.value = gainFor(lv.speech, clip.rms)
  into(sg)
  let done
  const finished = new Promise((r) => { done = r })
  let el = null
  let src = null
  const startAt = c.currentTime + leadMs / 1000
  if (rate !== 1 && clip.url) {
    el = new Audio(clip.url)
    el.preservesPitch = true
    el.playbackRate = rate
    el.crossOrigin = 'anonymous'
    const me = c.createMediaElementSource(el)
    me.connect(sg)
    el.onended = () => done(true)
    setTimeout(() => { el.play().catch(() => done(false)) }, leadMs)
  } else {
    src = c.createBufferSource()
    src.buffer = clip.buffer
    src.connect(sg)
    src.onended = () => done(true)
    src.start(startAt)
  }
  const handle = {
    stop: () => {
      try { src?.stop() } catch { /* 이미 멈춤 */ }
      try { el?.pause() } catch { /* 이미 멈춤 */ }
      try { noiseSrc?.stop() } catch { /* 이미 멈춤 */ }
      done(false)
      setTimeout(() => { try { out.disconnect() } catch { /* 끊김 */ } }, 50)
    },
  }
  current = handle
  // 끝남 이벤트가 오지 않을 때(창이 가려져 오디오가 멈춤, 출력 장치가 바뀜 등) 화면이 '듣는 중'에 멈추지 않게 소리 길이 + 여유 뒤에 푼다
  const guard = setTimeout(() => done(true), leadMs + (clip.buffer?.duration || clip.duration_ms / 1000 || 3) * 1000 / Math.min(1, rate) + 1500)
  const ok = await finished
  clearTimeout(guard)
  if (noiseSrc && current === handle) {
    // 말이 끝난 뒤 잡음은 0.3초 더 두었다가 줄여 끈다
    const ng = nodes[1]
    const t = c.currentTime + 0.3
    ng.gain.setValueAtTime(ng.gain.value, t)
    ng.gain.linearRampToValueAtTime(0, t + 0.15)
    setTimeout(() => { try { noiseSrc.stop() } catch { /* 이미 멈춤 */ } }, 500)
  }
  if (current === handle) current = null
  return ok
}

/** 두 소리를 차례로(소리 구별). 사이 쉼 gapMs. */
export async function playPair(a, b, opts = {}, gapMs = 600) {
  const ok = await playClip(a, opts)
  if (!ok) return false
  await new Promise((r) => setTimeout(r, gapMs))
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
