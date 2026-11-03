// 후보 입술 읽기 모델을 '후보 ID 하나'로 고르는 매니페스트 해석(11/03 검토 M3·M4·M18). 순수 함수만 둔다.
//
// 기본은 지금과 같다: VITE_LIPREAD_MODEL이 없으면 lipreadModelId()가 null이고, 모델 주소는 아래 DEFAULT_MODEL(R2/BS 경로의 상수)뿐이다.
// 켜면(빌드 플래그, 판정 전에는 배포 설정에 넣지 않는다) /models/lipread/manifest.json(git 제외 폴더)에서 그 ID의 항목을 읽는다.
//   { "models": { "C65": { "model": "/models/lipread/C65/model.web.int8.onnx", "meta": "/models/lipread/C65/model.web.meta.json",
//                          "inputs": ["roi_z"], "sha256": "<model 파일의 sha256, 소문자 64자>" } } }
// - 결합 여부는 항목의 inputs에 'lips'가 있는지로 정한다(환경 변수나 개발용 loopback 주소가 아니다).
// - 주소는 /models/lipread/ 아래 같은 출처 경로만 받는다. sha256이 맞지 않으면 모델을 쓰지 않는다(칸이 조용히 숨는다).

export const MANIFEST_URL = '/models/lipread/manifest.json'
export const DEFAULT_MODEL = Object.freeze({
  model: '/models/roi/kr_lipread_roi.web.onnx',
  meta: '/models/roi/kr_lipread_roi.web.meta.json',
  fusion: false,
  sha256: null,
})

const SHA256_RE = /^[0-9a-f]{64}$/
const insideLipreadDir = (u) => typeof u === 'string' && u.startsWith('/models/lipread/') && !u.includes('..') && !u.includes('//') && !u.includes('?') && !u.includes('#')

/** 매니페스트와 후보 ID → { model, meta, fusion, sha256 } 또는 null(항목이 없거나 형식이 틀림). id가 비어 있으면 DEFAULT_MODEL. */
export function resolveModel(manifest, id) {
  if (!id) return DEFAULT_MODEL
  const e = manifest && typeof manifest === 'object' ? manifest.models?.[id] : null
  if (!e || !Array.isArray(e.inputs) || !e.inputs.includes('roi_z')) return null
  if (!insideLipreadDir(e.model) || !insideLipreadDir(e.meta) || !SHA256_RE.test(String(e.sha256 || ''))) return null
  const extra = e.inputs.filter((n) => n !== 'roi_z' && n !== 'lips')
  if (extra.length) return null
  return { model: e.model, meta: e.meta, fusion: e.inputs.includes('lips'), sha256: e.sha256 }
}

/** 바이트의 sha256(소문자 16진). */
export async function sha256Hex(bytes) {
  const d = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** 받은 바이트가 기대 sha256과 같을 때만 true. 기대값이 없으면 false(후보 경로는 항상 해시를 요구한다). */
export async function bytesMatchSha256(bytes, expected) {
  if (!SHA256_RE.test(String(expected || ''))) return false
  return (await sha256Hex(bytes)) === expected
}
