import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { resolveModel, DEFAULT_MODEL, bytesMatchSha256, sha256Hex, MANIFEST_URL } from './lipreadManifest.js'
import { lipreadModelId } from './lipreadGate.js'

const SHA = 'a'.repeat(64)
const manifest = { models: {
  C65: { model: '/models/lipread/C65/m.onnx', meta: '/models/lipread/C65/m.meta.json', inputs: ['roi_z'], sha256: SHA },
  D75: { model: '/models/lipread/D75/m.onnx', meta: '/models/lipread/D75/m.meta.json', inputs: ['roi_z', 'lips'], sha256: SHA },
} }

test('플래그 미설정이면 id가 null이고 기존 URL 그대로', () => {
  assert.equal(lipreadModelId({}), null)
  assert.equal(lipreadModelId({ VITE_LIPREAD_MODEL: '' }), null)
  assert.equal(lipreadModelId({ VITE_LIPREAD_MODEL: '0' }), null)
  assert.equal(resolveModel(manifest, null), DEFAULT_MODEL)
  assert.equal(DEFAULT_MODEL.model, '/models/roi/kr_lipread_roi.web.onnx')
  assert.equal(DEFAULT_MODEL.meta, '/models/roi/kr_lipread_roi.web.meta.json')
  assert.equal(DEFAULT_MODEL.fusion, false)
  assert.equal(MANIFEST_URL, '/models/lipread/manifest.json')
})
test('id가 있으면 매니페스트 항목, 결합 여부는 inputs의 lips', () => {
  assert.equal(lipreadModelId({ VITE_LIPREAD_MODEL: ' C65 ' }), 'C65')
  assert.deepEqual(resolveModel(manifest, 'C65'), { model: '/models/lipread/C65/m.onnx', meta: '/models/lipread/C65/m.meta.json', fusion: false, sha256: SHA })
  assert.equal(resolveModel(manifest, 'D75').fusion, true)
})
test('없는 id·잘못된 항목은 null', () => {
  assert.equal(resolveModel(manifest, 'X'), null)
  assert.equal(resolveModel(null, 'C65'), null)
  const bad = (patch) => resolveModel({ models: { C65: { ...manifest.models.C65, ...patch } } }, 'C65')
  assert.equal(bad({ sha256: 'zz' }), null)
  assert.equal(bad({ inputs: ['lips'] }), null)
  assert.equal(bad({ inputs: ['roi_z', 'foo'] }), null)
  assert.equal(bad({ model: 'http://127.0.0.1:1/m.onnx' }), null)
  assert.equal(bad({ model: '/models/lipread/../roi/m.onnx' }), null)
  assert.equal(bad({ meta: '/other/m.json' }), null)
})
test('sha256 불일치면 false, 일치하면 true, 기대값이 없으면 false', async () => {
  const bytes = new Uint8Array([1, 2, 3, 4])
  const want = createHash('sha256').update(bytes).digest('hex')
  assert.equal(await sha256Hex(bytes), want)
  assert.equal(await bytesMatchSha256(bytes, want), true)
  const flipped = Uint8Array.from(bytes); flipped[0] ^= 1
  assert.equal(await bytesMatchSha256(flipped, want), false)
  assert.equal(await bytesMatchSha256(bytes, null), false)
})
