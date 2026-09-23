/**
 * 축 K — 얼굴 표면신호 → 유성성/비음성 추정(학습된 분류기, onnxruntime-web).
 * korean_ds로 학습(미학습화자 비음 AUC≈0.64, 유성 AUC≈0.55). 브라우저에서 30프레임(1초) 창의
 * 얼굴 8차원(FACE_KEYS)을 넣어 프레임평균 확률을 낸다. 모델/WASM 로드 실패 시 null(폴백).
 */
import * as ort from 'onnxruntime-web'

// WASM은 CDN에서(번들 비대화 방지). 실패해도 컴포넌트는 폴백.
ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/'
ort.env.logLevel = 'error'

export const K_FACE_KEYS = ['jawOpen', 'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight',
  'noseSneerLeft', 'noseSneerRight', 'mouthPressLeft', 'mouthPressRight']
export const K_WIN = 30

let session = null
let loading = null

export async function loadK() {
  if (session) return session
  if (!loading) {
    loading = ort.InferenceSession
      .create('/k-model/facecue_k.onnx', { executionProviders: ['wasm'] })
      .then((s) => { session = s; return s })
      .catch(() => null)
  }
  return loading
}

const sigmoid = (x) => 1 / (1 + Math.exp(-x))

export const K_FPS = 30   // 학습 영상 프레임률 — 창 30프레임이 1초

/** 창 하나(Float32Array(30*8))의 프레임별 비음 확률 Float32Array(30) 또는 null. */
async function nasalFrames(win) {
  const s = await loadK()
  if (!s) return null
  try {
    const out = await s.run({ face: new ort.Tensor('float32', win, [1, K_WIN, K_FACE_KEYS.length]) })
    const logits = out.logits.data
    const p = new Float32Array(K_WIN)
    for (let i = 0; i < K_WIN; i++) p[i] = sigmoid(logits[i * 2 + 1])
    return p
  } catch {
    return null
  }
}

/**
 * 발화 중 얼굴 8차원 시계열 → 프레임별 비음 확률 [[t초, p], …] (발음채점 K→B 보조 입력, K-5).
 * rows[i]는 K_FACE_KEYS 순서의 값, times[i]는 녹음 시작 기준 초. 기기마다 녹화 프레임률이 달라(대개 20fps)
 * 학습 조건(30fps, 30프레임 창)에 맞게 선형 보간한 격자로 추론한다. 모델을 못 쓰거나 너무 짧으면 null.
 */
export async function nasalTrack(rows, times, maxPoints = 1500) {
  if (!rows?.length || rows.length !== times?.length || rows.length < 5) return null
  const D = K_FACE_KEYS.length
  const t0 = times[0]
  const n = Math.min(maxPoints, Math.floor((times[times.length - 1] - t0) * K_FPS) + 1)
  if (n < 5) return null
  const grid = new Float32Array(n * D)
  const gt = new Array(n)
  let j = 0
  for (let i = 0; i < n; i++) {
    const t = t0 + i / K_FPS
    gt[i] = t
    while (j < times.length - 2 && times[j + 1] < t) j++
    const ta = times[j]
    const tb = times[j + 1]
    const a = tb > ta ? Math.max(0, Math.min(1, (t - ta) / (tb - ta))) : 0
    for (let d = 0; d < D; d++) grid[i * D + d] = rows[j][d] * (1 - a) + rows[j + 1][d] * a
  }
  const out = []
  for (let st = 0; st < n; st += K_WIN) {
    const win = new Float32Array(K_WIN * D)
    for (let i = 0; i < K_WIN; i++) {
      const src = Math.min(n - 1, st + i)            // 마지막 창은 끝 프레임을 되풀이해 채운다
      win.set(grid.subarray(src * D, src * D + D), i * D)
    }
    const p = await nasalFrames(win)
    if (!p) return null
    for (let i = 0; i < K_WIN && st + i < n; i++) {
      out.push([Math.round(gt[st + i] * 1000) / 1000, Math.round(p[i] * 1000) / 1000])
    }
  }
  return out
}

/** win: Float32Array(30*8), FACE_KEYS 순서. 반환 {voiced, nasal} 0~1 또는 null. */
export async function predictK(win) {
  const s = await loadK()
  if (!s) return null
  try {
    const t = new ort.Tensor('float32', win, [1, K_WIN, K_FACE_KEYS.length])
    const out = await s.run({ face: t })
    const logits = out.logits.data // (1,30,2) 평탄화
    let v = 0, n = 0
    for (let i = 0; i < K_WIN; i++) { v += sigmoid(logits[i * 2]); n += sigmoid(logits[i * 2 + 1]) }
    return { voiced: v / K_WIN, nasal: n / K_WIN }
  } catch {
    return null
  }
}
