/**
 * 축 D — 자체 립리딩(입모양 시퀀스 → 자모 CTC → 단어). onnxruntime-web 브라우저 추론.
 * OLKAVS로 학습한 경량 모델(LayerNorm→BiGRU→Linear, 입 27차원→자모 53). 영상·계수는 기기 밖으로
 * 나가지 않는다. 미학습화자 정확도가 낮아 '단어 단위 검증'(폐집합 후보 중 가장 가까운 단어)로
 * 범위를 한정한다(계획서 D). 모델/WASM 로드 실패 시 null(폴백).
 */
import * as ort from 'onnxruntime-web'
import { decomposeToJamo } from './ctcScore'

ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/'
ort.env.logLevel = 'error'

const ONNX_URL = '/models/kr_d_lipread.onnx'
const META_URL = '/models/kr_d_lipread.meta.json'

// 자모 분해(train_lipread.decompose와 같은 규칙)는 ctcScore.js에 둔다(노드 테스트에서 onnxruntime 없이 쓰려고).
export { decomposeToJamo }

function editDistance(a, b) {
  const m = a.length, n = b.length
  if (!m) return n
  if (!n) return m
  let prev = Array.from({ length: n + 1 }, (_, i) => i)
  for (let i = 1; i <= m; i++) {
    const cur = [i]
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
    }
    prev = cur
  }
  return prev[n]
}

let session = null
let meta = null
let loading = null

export async function loadLipread() {
  if (session && meta) return { session, meta }
  if (!loading) {
    loading = (async () => {
      try {
        const m = await fetch(META_URL).then((r) => r.json())
        const s = await ort.InferenceSession.create(ONNX_URL, { executionProviders: ['wasm'] })
        session = s; meta = m
        return { session, meta }
      } catch {
        return null
      }
    })()
  }
  return loading
}

/**
 * frames: [{blendshapeName: value, ...}] 시퀀스(웹캠 프레임별 blendshape 맵).
 * candidates: 폐집합 후보 단어 배열(있으면 가장 가까운 단어를 함께 반환).
 * 반환 {jamo, matched, ranked} 또는 null. jamo=디코드 자모열 문자열, matched=최근접 후보.
 */
export async function predictLipread(frames, candidates = []) {
  const loaded = await loadLipread()
  if (!loaded || !frames || frames.length < 10) return null
  const { session: s, meta: m } = loaded
  const keys = m.mouth_keys
  const T = frames.length
  try {
    const data = new Float32Array(T * keys.length)
    for (let t = 0; t < T; t++) {
      const f = frames[t] || {}
      for (let j = 0; j < keys.length; j++) data[t * keys.length + j] = f[keys[j]] || 0
    }
    const input = new ort.Tensor('float32', data, [1, T, keys.length])
    const out = await s.run({ bs: input })
    const logits = out.logits.data // (1,T,V) 평탄화
    const V = m.n_vocab
    // CTC 그리디 디코드: 프레임별 argmax → 반복 축약 + blank(0) 제거
    const ids = []
    let prev = -1
    for (let t = 0; t < T; t++) {
      let best = 0, bv = -Infinity
      for (let v = 0; v < V; v++) { const x = logits[t * V + v]; if (x > bv) { bv = x; best = v } }
      if (best !== prev && best !== 0) ids.push(best)
      prev = best
    }
    const decoded = ids.map((i) => m.vocab[i])          // 자모(호환) 배열
    const jamo = decoded.join('')
    let matched = null, ranked = []
    if (candidates.length) {
      ranked = candidates.map((w) => ({
        word: w,
        dist: editDistance(decoded, decomposeToJamo(w)),
      })).sort((a, b) => a.dist - b.dist)
      matched = ranked[0]?.word ?? null
    }
    return { jamo, matched, ranked }
  } catch {
    return null
  }
}
