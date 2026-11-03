import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

// lipreadRoiModel.js를 후보 ID(C65)가 켜진 환경으로 불러, 매니페스트 해석·sha256 대조·결합 분기를 확인한다(ORT는 가짜).
const root = new URL('./', import.meta.url)
const source = readFileSync(new URL('lipreadRoiModel.js', root), 'utf8')
const bytes = new Uint8Array([9, 8, 7, 6, 5])
const good = createHash('sha256').update(bytes).digest('hex')

async function loadWith({ id, manifest, files, inputNames = ['roi_z'], fusionFlag = '0' }) {
  const calls = { create: 0 }
  globalThis.fetch = async (url) => {
    const f = url === '/models/lipread/manifest.json' ? manifest : files[url]
    if (f === undefined) return { ok: false, json: async () => ({}), arrayBuffer: async () => new ArrayBuffer(0) }
    return { ok: true, json: async () => f, arrayBuffer: async () => (f instanceof Uint8Array ? f.buffer.slice(f.byteOffset, f.byteOffset + f.byteLength) : new ArrayBuffer(0)) }
  }
  globalThis.__ortStub = { env: { wasm: {} }, InferenceSession: { create: async () => { calls.create++; return { inputNames, release: async () => {} } } } }
  const code = source
    .replaceAll("from './", `from '${root.href}`)
    .replaceAll('import.meta.env', `({ VITE_LIPREAD_MODEL: '${id}', VITE_LIPREAD_FUSION: '${fusionFlag}' })`)
    .replace("await import('onnxruntime-web')", 'globalThis.__ortStub')
  const mod = await import(`data:text/javascript;base64,${Buffer.from(code + `\n// ${Math.random()}`).toString('base64')}`)
  return { mod, calls }
}
const entry = (patch = {}) => ({ models: { C65: { model: '/models/lipread/C65/m.onnx', meta: '/models/lipread/C65/m.meta.json', inputs: ['roi_z'], sha256: good, ...patch } } })

test('sha256이 맞으면 세션을 만들고 fusion은 inputs로 정한다', async () => {
  const { mod, calls } = await loadWith({ id: 'C65', manifest: entry(), files: { '/models/lipread/C65/m.onnx': bytes, '/models/lipread/C65/m.meta.json': { n_vocab: 53 } } })
  assert.equal(await mod.lipreadRoiAvailable(), true)
  const loaded = await mod.loadLipreadRoi()
  assert.ok(loaded && loaded.fusion === false)
  assert.equal(calls.create, 1)
})
test('sha256이 다르면 세션을 만들지 않고 null(칸 숨김)', async () => {
  const { mod, calls } = await loadWith({ id: 'C65', manifest: entry({ sha256: 'b'.repeat(64) }), files: { '/models/lipread/C65/m.onnx': bytes, '/models/lipread/C65/m.meta.json': {} } })
  assert.equal(await mod.loadLipreadRoi(), null)
  assert.equal(calls.create, 0)
})
test('매니페스트에 없는 ID면 null', async () => {
  const { mod, calls } = await loadWith({ id: 'NOPE', manifest: entry(), files: {} })
  assert.equal(await mod.loadLipreadRoi(), null)
  assert.equal(calls.create, 0)
})
test('inputs에 lips가 있으면 결합 세션(입력 이름도 확인)', async () => {
  const ok = await loadWith({ id: 'C65', manifest: entry({ inputs: ['roi_z', 'lips'] }), inputNames: ['roi_z', 'lips'], files: { '/models/lipread/C65/m.onnx': bytes, '/models/lipread/C65/m.meta.json': {} } })
  assert.equal((await ok.mod.loadLipreadRoi()).fusion, true)
  const bad = await loadWith({ id: 'C65', manifest: entry({ inputs: ['roi_z', 'lips'] }), inputNames: ['roi_z'], files: { '/models/lipread/C65/m.onnx': bytes, '/models/lipread/C65/m.meta.json': {} } })
  assert.equal(await bad.mod.loadLipreadRoi(), null)
})
test('플래그 미설정이면 매니페스트를 아예 부르지 않는다', async () => {
  let manifestFetched = false
  const { mod } = await loadWith({ id: '', manifest: entry(), files: {} })
  const real = globalThis.fetch
  globalThis.fetch = async (u, ...r) => { if (String(u).includes('manifest')) manifestFetched = true; return real(u, ...r) }
  await mod.lipreadRoiAvailable()
  assert.equal(manifestFetched, false)
})
