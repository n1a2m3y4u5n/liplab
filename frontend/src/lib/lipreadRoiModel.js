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

const ONNX_URL = '/models/roi/kr_lipread_roi.web.onnx'
const META_URL = '/models/roi/kr_lipread_roi.web.meta.json'
const MAX_INVALID = 0.5   // 판정 창과 같은 규칙: 유효 프레임이 절반 미만이면 읽지 않는다

let ort = null
let session = null
let meta = null
let loading = null
let available = null

export function lipreadRoiAvailable() {
  if (!available) {
    available = fetch(META_URL)
      .then(async (r) => { if (r.ok) meta = await r.json(); return r.ok })
      .catch(() => false)
  }
  return available
}

export async function loadLipreadRoi() {
  if (session && meta) return { session, meta }
  if (!loading) {
    loading = (async () => {
      try {
        if (!ort) {
          ort = await import('onnxruntime-web')
          ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/'
          ort.env.logLevel = 'error'
        }
        const m = meta || await fetch(META_URL).then((r) => r.json())
        const s = await ort.InferenceSession.create(ONNX_URL, { executionProviders: ['wasm'] })
        session = s; meta = m
        return { session, meta }
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
export async function runRoiModel(s, data, T, ortMod = ort) {
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
    const { data, T } = roiModelInput(seq.roi)
    const logits = await runRoiModel(loaded.session, data, T)
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
  return { t: video.currentTime * 1000, gray, geom: landmarks ? landmarkGeometry(landmarks, W, H) : null, W, H }
}
