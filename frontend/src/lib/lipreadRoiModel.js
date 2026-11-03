import { canLoadOptionalModel, configureWasm } from './modelCapability.js'
/**
 * 독화 ① 화소 입술 ROI 모델(빌드 플래그 VITE_LIPREAD_ROI=1일 때만, docs/lipread-roi-2026-10.md 13절).
 * 웹캠 프레임 → 입술 88×88 흑백(lipRoi.js, 학습 추출과 같은 계산) → int8 ONNX(onnxruntime-web, 판정 모델에서 앞단 정규화만 뺀 그래프) → 후보 단어를 CTC 로그우도로 채점
 * (판정과 같은 ctc_ll α=1, dup1, 75프레임 창). 화면에 돌려주는 모양은 lipreadModel.predictLipread와 같다({jamo, matched, ranked}).
 *
 * 모델(6.1 MB)은 git에 없다(공개 저장소). 빌드 전에 public/models/roi/에 복사한다(DEPLOY.md 11항). 없으면 메타 확인이 실패해
 * 칸이 지금처럼 조용히 숨는다.
 */
import { decomposeToJamo, logSoftmaxRows, rankByCtc } from './ctcScore.js'
import { extractRoiSequence, roiModelInput, rgbaToGray, landmarkGeometry, ROI_CROP } from './lipRoi.js'
import { landmarkLips80, coordinateSequence, fusionModelInput, fusionFeeds } from './lipFusion.js'
import { lipreadModelId } from './lipreadGate.js'
import { MANIFEST_URL, resolveModel, bytesMatchSha256 } from './lipreadManifest.js'

// 기본 끔. 모델은 로컬 시험용 서버에서만 읽으며 public/배포에 포함하지 않는다.
const FUSION = typeof import.meta.env !== 'undefined' && import.meta.env.VITE_LIPREAD_FUSION === '1'
function fusionUrl(value) {
  if (!import.meta.env?.DEV || !value) throw new Error('Fusion requires a local development model URL')
  const url = new URL(value)
  if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) throw new Error('Fusion requires loopback HTTP')
  return url.href
}
// 후보 모델 ID(VITE_LIPREAD_MODEL, 기본 끔). 비어 있으면 아래 매니페스트 경로는 전혀 타지 않고 지금 경로(R2/BS) 그대로다.
const MODEL_ID = lipreadModelId(import.meta.env)
let candidate = null   // 매니페스트에서 고른 항목 { model, meta, fusion, sha256 } 또는 null(없음·형식 오류)
let candidateTried = false
async function loadCandidate() {
  if (!candidateTried) {
    candidateTried = true
    try {
      const r = await fetch(MANIFEST_URL)
      candidate = r.ok ? resolveModel(await r.json(), MODEL_ID) : null
    } catch { candidate = null }
  }
  return candidate
}
function modelUrls() {
  return FUSION ? {
    model: fusionUrl(import.meta.env.VITE_LIPREAD_FUSION_MODEL_URL),
    meta: fusionUrl(import.meta.env.VITE_LIPREAD_FUSION_META_URL),
  } : { model: ONNX_URL, meta: META_URL }
}

const ONNX_URL = '/models/roi/kr_lipread_roi.web.onnx'
const META_URL = '/models/roi/kr_lipread_roi.web.meta.json'
const MAX_INVALID = 0.5   // 판정 창과 같은 규칙: 유효 프레임이 절반 미만이면 읽지 않는다

let ort = null
let session = null
let meta = null
let loading = null
let available = null
let sessionFusion = FUSION   // 지금 세션이 결합(roi_z + lips) 모델인가. 후보 경로가 아니면 늘 FUSION과 같다

export function lipreadRoiAvailable() {
  if (!available) {
    available = Promise.resolve().then(async () => fetch(MODEL_ID ? (await loadCandidate()).meta : modelUrls().meta))
      .then(async (r) => { if (r.ok) meta = await r.json(); return r.ok })
      .catch(() => false)
  }
  return available
}

/** 화면을 떠날 때 ORT 세션을 놓는다(저메모리 폰에서 세션이 쌓이지 않게, F15). 적재 중이면 끝나길 기다렸다 놓는다. 다시 쓰면 새로 적재한다. */
export async function releaseLipreadRoi() {
  const pending = loading
  let target = session
  session = null
  loading = null
  if (!target && pending) {
    try { const r = await pending; target = r?.session ?? r } catch { target = null }
    session = null
  }
  try { await target?.release?.() } catch { /* 이미 놓았거나 지원하지 않음 */ }
}

export async function loadLipreadRoi() {
  if (!canLoadOptionalModel()) return null
  if (session && meta) return { session, meta, fusion: sessionFusion }
  if (!loading) {
    loading = (async () => {
      try {
        if (!ort) {
          ort = await import('onnxruntime-web')
          configureWasm(ort)
        }
        let s, m, fusion = FUSION
        if (MODEL_ID) {
          // 후보 경로: 매니페스트 항목의 sha256이 받은 바이트와 같을 때만 쓴다(틀리면 null → 칸이 조용히 숨는다)
          const entry = await loadCandidate()
          if (!entry) throw new Error('No manifest entry')
          const bytes = new Uint8Array(await fetch(entry.model).then((r) => { if (!r.ok) throw new Error('model fetch'); return r.arrayBuffer() }))
          if (!(await bytesMatchSha256(bytes, entry.sha256))) throw new Error('sha256 mismatch')
          m = meta || await fetch(entry.meta).then((r) => r.json())
          s = await ort.InferenceSession.create(bytes, { executionProviders: ['wasm'] })
          fusion = entry.fusion
          if (fusion ? (s.inputNames.length !== 2 || !s.inputNames.includes('roi_z') || !s.inputNames.includes('lips')) : !s.inputNames.includes('roi_z')) throw new Error('Unexpected inputs')
        } else {
          const urls = modelUrls()
          m = meta || await fetch(urls.meta).then((r) => r.json())
          s = await ort.InferenceSession.create(urls.model, { executionProviders: ['wasm'] })
          if (FUSION && (s.inputNames.length !== 2 || !s.inputNames.includes('roi_z') || !s.inputNames.includes('lips'))) throw new Error('Expected roi_z + lips')
        }
        session = s; meta = m; sessionFusion = fusion
        return { session, meta, fusion }
      } catch {
        loading = null
        return null
      }
    })()
  }
  return loading
}

/** 후보 단어 → 자모 id열(어휘에 없는 글자는 뺀다. train_lipread.decompose와 같은 분해). */
export function wordLabels(word, vocab) {
  const v2i = new Map(vocab.map((c, i) => [c, i]))
  return decomposeToJamo(word).map((c) => v2i.get(c)).filter((i) => i !== undefined && i > 0)
}

/** logits(T·V) → 그리디 자모열, 후보 ctc_ll 순위. 노드 대조 검사에서도 쓴다. */
export function scoreLogits(logits, T, V, vocab, candidates = [], alpha = 1) {
  let jamo = ''
  let prev = -1
  for (let t = 0; t < T; t++) {
    let best = 0, bv = -Infinity
    for (let v = 0; v < V; v++) { const x = logits[t * V + v]; if (x > bv) { bv = x; best = v } }
    if (best !== prev && best !== 0) jamo += vocab[best]
    prev = best
  }
  if (!candidates.length) return { jamo, matched: null, ranked: [] }
  const logp = logSoftmaxRows(logits, T, V)
  const { order, scores } = rankByCtc(logp, T, V, candidates.map((w) => wordLabels(w, vocab)), alpha)
  const ranked = order.map((i) => ({ word: candidates[i], score: scores[i] }))
  return { jamo, matched: ranked[0]?.word ?? null, ranked }
}

/** 모델 입력 roi_z(Float32Array T·80·80, lipRoi.roiModelInput) → logits Float32Array(T·V). */
export async function runRoiModel(s, data, T, ortMod = ort, lips = null) {
  if (FUSION || (MODEL_ID && sessionFusion)) {
    const out = await s.run(fusionFeeds(ortMod, data, T, lips, s.inputNames))
    return out.logits.data
  }
  const input = new ortMod.Tensor('float32', data, [1, T, ROI_CROP, ROI_CROP])
  const out = await s.run({ roi_z: input })
  return out.logits.data
}

/**
 * frames: [{t, gray, geom}] (녹화 중 새 영상 프레임마다, lipRoi.extractRoiSequence 참고), W·H: 영상 크기.
 * 반환 {jamo, matched, ranked} 또는 null.
 */
export async function predictLipreadRoi(frames, W, H, candidates = []) {
  const loaded = await loadLipreadRoi()
  if (!loaded || !frames || frames.length < 10) return null
  try {
    const seq = extractRoiSequence(frames, W, H)
    if (!seq) return null
    const nValid = seq.valid.filter(Boolean).length
    if (nValid < seq.valid.length * (1 - MAX_INVALID)) return null
    const fusion = !!loaded.fusion
    const input = fusion ? fusionModelInput(seq.roi, coordinateSequence(frames)) : roiModelInput(seq.roi)
    if (fusion && !input.valid.some(Boolean)) return null
    const { data, T } = input
    const logits = await runRoiModel(loaded.session, data, T, ort, input.lips)
    const V = loaded.meta.n_vocab
    return scoreLogits(logits, T, V, loaded.meta.vocab, candidates, loaded.meta.alpha ?? 1)
  } catch {
    return null
  }
}

/**
 * 녹화 중 새 영상 프레임 하나 → {t, gray, geom}. 검출기와 같은 영상 프레임을 캔버스에 그려 흑백으로 바꾼다(화면에 그리지 않음).
 * t는 영상 시각(video.currentTime, ms)이라 화면 주사율과 무관하게 카메라 프레임 간격을 따른다. 얼굴이 없으면 geom = null
 * (학습 추출처럼 그 프레임도 보간한 위치에서 자른다).
 */
export function grabRoiFrame(video, landmarks, holder) {
  const W = video.videoWidth, H = video.videoHeight
  if (!W || !H) return null
  if (!holder.canvas) holder.canvas = document.createElement('canvas')
  const c = holder.canvas
  if (c.width !== W || c.height !== H) { c.width = W; c.height = H; holder.ctx = null }
  if (!holder.ctx) holder.ctx = c.getContext('2d', { willReadFrequently: true })
  holder.ctx.drawImage(video, 0, 0, W, H)
  const gray = rgbaToGray(holder.ctx.getImageData(0, 0, W, H).data, W * H)
  const frame = { t: video.currentTime * 1000, gray, geom: landmarks ? landmarkGeometry(landmarks, W, H) : null, W, H }
  if (FUSION || candidate?.fusion) frame.lips = landmarkLips80(landmarks, W, H)
  return frame
}
