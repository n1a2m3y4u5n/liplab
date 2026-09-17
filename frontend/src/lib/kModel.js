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
