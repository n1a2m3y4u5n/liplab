import { rmsOf, activeLevel } from './listenMix.js'
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

export { phoneFilter, vocodeBuffer }
