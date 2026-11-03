// 후보 모델 배선(VITE_LIPREAD_MODEL) 미설정 때 기존 경로와 같은지 확인한다(11/03 검토 묶음 D). 관문이 돌린다.
//   node scripts/lipread_off_identity.mjs [결과.json]
// 기준은 배선 전 커밋(BASE)의 lipreadRoiModel.js다. 같은 모델로 아래가 바이트까지 같아야 한다:
//   grab 프레임(gray·geom), 모델 입력 바이트, logits, 채점 결과(JSON). 또 모델 주소가 기존 상수와 같아야 한다.
// 실제 영상·평가 자료를 쓰지 않는다(합성 프레임). 모델 파일이 없으면 모델 부분은 건너뛰고 그 사실을 결과에 적는다.
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'
import { roiModelInput } from '../frontend/src/lib/lipRoi.js'
import { DEFAULT_MODEL } from '../frontend/src/lib/lipreadManifest.js'

const BASE = 'f81919e6'   // 후보 배선 전(묶음 D 이전)
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const ort = require('onnxruntime-web')
ort.env.wasm.numThreads = 1
ort.env.logLevel = 'error'
const root = new URL('../frontend/src/lib/', import.meta.url)
const before = execFileSync('git', ['show', `${BASE}:frontend/src/lib/lipreadRoiModel.js`], { encoding: 'utf8' })
const after = readFileSync(new URL('lipreadRoiModel.js', root), 'utf8')

async function load(source) {
  source = source.replaceAll("from './", `from '${root.href}`).replaceAll('import.meta.env', '({})')
  return import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
}
const baseline = await load(before), current = await load(after)
const hash = (v) => createHash('sha256').update(v).digest('hex')

// 모델 주소: 기존 상수와 같은 문자열
for (const [k, key] of [['ONNX_URL', 'model'], ['META_URL', 'meta']]) {
  const m = before.match(new RegExp(`const ${k} = '([^']+)'`))
  assert.equal(m?.[1], DEFAULT_MODEL[key], `${k} must equal DEFAULT_MODEL.${key}`)
}

// grab: 가짜 비디오·캔버스로 같은 프레임이 나오는지
const W = 96, H = 64
const rgba = Uint8ClampedArray.from({ length: W * H * 4 }, (_, i) => (i * 31 + 7) % 256)
globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: () => ({ drawImage() {}, getImageData: () => ({ data: rgba }) }) }) }
const video = { videoWidth: W, videoHeight: H, currentTime: 1.25 }
const landmarks = Array.from({ length: 478 }, (_, i) => ({ x: 0.3 + (i % 20) * 0.02, y: 0.3 + (i % 17) * 0.02, z: 0 }))
const fa = baseline.grabRoiFrame(video, landmarks, {}), fb = current.grabRoiFrame(video, landmarks, {})
const norm = (f) => JSON.stringify({ t: f.t, W: f.W, H: f.H, geom: f.geom, lips: f.lips ?? null, gray: hash(Buffer.from(f.gray.buffer, f.gray.byteOffset, f.gray.byteLength)) })
assert.equal(norm(fa), norm(fb), 'grab frames must be identical')

const result = { status: 'passed', base: BASE, url_constants_equal: true, grab_identical: true, grab_sha256: hash(norm(fa)),
  data: 'synthetic frames; no evaluation or user data', runtime: 'onnxruntime-web WASM CPU, one thread' }
const modelPath = new URL('../frontend/public/models/roi/kr_lipread_roi.web.onnx', import.meta.url)
if (existsSync(modelPath)) {
  const model = readFileSync(modelPath)
  const session = await ort.InferenceSession.create(new Uint8Array(model), { executionProviders: ['wasm'] })
  try {
    const roi = Array.from({ length: 61 }, (_, t) => Uint8Array.from({ length: 88 * 88 }, (_, i) => (i * 13 + t * 7) % 256))
    const input = roiModelInput(roi)
    const old = await baseline.runRoiModel(session, input.data, input.T, ort)
    const now = await current.runRoiModel(session, input.data, input.T, ort)
    const a = Buffer.from(old.buffer, old.byteOffset, old.byteLength), b = Buffer.from(now.buffer, now.byteOffset, now.byteLength)
    assert.equal(a.equals(b), true, 'logits must match byte for byte')
    const meta = JSON.parse(readFileSync(new URL('../frontend/public/models/roi/kr_lipread_roi.web.meta.json', import.meta.url), 'utf8'))
    const words = ['가', '나', '다', '마']
    const sa = baseline.scoreLogits(old, input.T, meta.n_vocab, meta.vocab, words, meta.alpha ?? 1)
    const sb = current.scoreLogits(now, input.T, meta.n_vocab, meta.vocab, words, meta.alpha ?? 1)
    assert.equal(JSON.stringify(sa), JSON.stringify(sb), 'scores must match')
    Object.assign(result, { model_sha256: hash(model), input_bytes_sha256: hash(Buffer.from(input.data.buffer, input.data.byteOffset, input.data.byteLength)),
      logits_identical: true, logits_sha256: hash(a), scores_sha256: hash(JSON.stringify(sa)) })
  } finally { await session.release() }
} else { result.model = 'skipped: R2 model file not present' }
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(result, null, 2))
console.log(JSON.stringify(result))
