import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'
import { roiModelInput } from '../frontend/src/lib/lipRoi.js'
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const ort = require('onnxruntime-web')
ort.env.wasm.numThreads = 1
ort.env.logLevel = 'error'
const BASE = '58a63a5efce98216260c9d21297535cb81411118'
const root = new URL('../frontend/src/lib/', import.meta.url)
const before = execFileSync('git', ['show', `${BASE}:frontend/src/lib/lipreadRoiModel.js`], { encoding:'utf8' })
const after = readFileSync(new URL('lipreadRoiModel.js', root), 'utf8')
async function load(source) {
  source = source.replaceAll("from './", `from '${root.href}`).replaceAll('import.meta.env', "({ VITE_LIPREAD_FUSION: '0' })")
  return import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
}
const baseline = await load(before), current = await load(after)
const path = new URL('../frontend/public/models/roi/kr_lipread_roi.web.onnx', import.meta.url)
const model = readFileSync(path)
const session = await ort.InferenceSession.create(new Uint8Array(model), { executionProviders:['wasm'] })
try {
  const roi = Array.from({ length:61 }, (_,t) => Uint8Array.from({ length:88*88 }, (_,i) => (i*13+t*7)%256))
  const input = roiModelInput(roi)
  const old = await baseline.runRoiModel(session,input.data,input.T,ort)
  const now = await current.runRoiModel(session,input.data,input.T,ort)
  const a = Buffer.from(old.buffer,old.byteOffset,old.byteLength), b = Buffer.from(now.buffer,now.byteOffset,now.byteLength)
  assert.equal(a.equals(b),true,'Real R2 logits must match byte for byte')
  const meta = JSON.parse(readFileSync(new URL('../frontend/public/models/roi/kr_lipread_roi.web.meta.json', import.meta.url),'utf8'))
  const words = ['가','나','다','마']
  const scoreA = baseline.scoreLogits(old,input.T,meta.n_vocab,meta.vocab,words,meta.alpha??1)
  const scoreB = current.scoreLogits(now,input.T,meta.n_vocab,meta.vocab,words,meta.alpha??1)
  assert.deepEqual(scoreA,scoreB)
  const hash = (value) => createHash('sha256').update(value).digest('hex')
  const result = {status:'passed',baseline:BASE,model_sha256:hash(model),T:input.T,
    data:'Synthetic 61 ROI frames, edge padded to 75; no evaluation data',
    real_R2_logits_byte_identical:true,logit_bytes:a.length,logits_sha256:hash(a),
    scores_json_byte_identical:JSON.stringify(scoreA)===JSON.stringify(scoreB),
    scores_sha256:hash(JSON.stringify(scoreA)),runtime:'onnxruntime-web WASM CPU, one thread'}
  writeFileSync(process.argv[2],JSON.stringify(result,null,2))
  console.log(JSON.stringify(result))
} finally { await session.release() }
