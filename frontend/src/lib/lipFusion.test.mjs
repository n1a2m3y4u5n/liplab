import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { landmarkLips80, coordinateSequence, fusionModelInput, fusionFeeds, round4 } from './lipFusion.js'
import { roiModelInput } from './lipRoi.js'

test('결측 격자, 중복 프레임과 보간 마스크를 보존한다', () => {
  const v = (n) => Array(80).fill(n)
  const seq = coordinateSequence([{ t: 0, lips: v(1) }, { t: 1, lips: v(2) },
    { t: 67, lips: null }, { t: 100, lips: v(8) }])
  assert.deepEqual(seq.src, [1, 1, 2, 3])
  assert.deepEqual(seq.det, [true, false, false, true])
  assert.deepEqual(seq.lips.map((x) => x[0]), [2, 4, 6, 8])
  assert.deepEqual(seq.interpolated, [false, true, true, false])
  const empty = coordinateSequence([{ t: 0, lips: null }])
  assert.equal(empty.allMissing, true)
  assert.equal(empty.lips[0].every((x) => x === 0), true)
  const edges = coordinateSequence([{ t: 0 }, { t: 33, lips: v(2) }, { t: 67, lips: v(4) }, { t: 100 }])
  assert.deepEqual(edges.lips.map((x) => x[0]), [2, 2, 4, 4])
  assert.deepEqual(edges.det, [false, true, true, false])
  assert.equal(landmarkLips80([], 640, 360), null)
  assert.equal(round4(0.0625), 0.0625)
})

test('ROI와 좌표 선택 및 75 길이 채우기가 같은 인덱스를 쓴다', () => {
  const roi = [0, 1, 2].map((n) => new Uint8Array(88 * 88).fill(n * 50))
  const seq = coordinateSequence([0, 1, 2].map((n) => ({ t: n * 1000 / 30, lips: Array(80).fill(n) })))
  const input = fusionModelInput(roi, seq, [2, 0])
  assert.equal(input.T, 75)
  assert.deepEqual(input.data, roiModelInput([roi[2], roi[0]]).data)
  for (let i = 0; i < 75; i++) assert.equal(input.lips[i * 80], input.indices[i])
  const feeds = fusionFeeds({ Tensor: class { constructor(type, data, dims) { Object.assign(this, { type, data, dims }) } } }, input.data, 75, input.lips)
  assert.deepEqual(feeds.roi_z.dims, [1, 75, 80, 80])
  assert.deepEqual(feeds.lips.dims, [1, 75, 80])
  assert.throws(() => fusionFeeds({}, input.data, 75, input.lips, ['roi', 'bad']))
})

async function modelModule(source, env) {
  source = source.replaceAll("from './", `from '${new URL('./', import.meta.url).href}`)
    .replaceAll('import.meta.env', JSON.stringify(env))
  return import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
}

test('플래그 끔: 수정 전 grab, 입력 바이트, logits 및 채점 결과와 동일하다', async () => {
  const before = execFileSync('git', ['show', '58a63a5efce98216260c9d21297535cb81411118:frontend/src/lib/lipreadRoiModel.js'], { encoding: 'utf8' })
  const after = readFileSync(new URL('./lipreadRoiModel.js', import.meta.url), 'utf8')
  const baseline = await modelModule(before, {})
  const current = await modelModule(after, { VITE_LIPREAD_FUSION: '0' })
  const video = { videoWidth: 2, videoHeight: 2, currentTime: 0.25 }
  const holder = () => ({ canvas: { width: 2, height: 2 }, ctx: { drawImage() {}, getImageData: () => ({ data: new Uint8Array(16).fill(127) }) } })
  assert.deepEqual(current.grabRoiFrame(video, null, holder()), baseline.grabRoiFrame(video, null, holder()))
  const data = Float32Array.from({ length: 75 * 80 * 80 }, (_, i) => (i % 127) / 127)
  const calls = []
  const ort = { Tensor: class { constructor(type, data, dims) { Object.assign(this, { type, data, dims }) } } }
  const session = { run: async (feeds) => { calls.push(feeds); return { logits: { data: Float32Array.from([1, 2, 3, 4, 3, 2]) } } } }
  const a = await baseline.runRoiModel(session, data, 75, ort)
  const b = await current.runRoiModel(session, data, 75, ort, new Float32Array(6000))
  assert.deepEqual(calls[0], calls[1])
  assert.deepEqual(Buffer.from(a.buffer), Buffer.from(b.buffer))
  assert.deepEqual(baseline.scoreLogits(a, 2, 3, ['', 'ㄱ', 'ㅏ'], ['가']), current.scoreLogits(b, 2, 3, ['', 'ㄱ', 'ㅏ'], ['가']))
})

test('플래그 켬 runRoiModel은 두 입력만 전달한다', async () => {
  const source = readFileSync(new URL('./lipreadRoiModel.js', import.meta.url), 'utf8')
  const current = await modelModule(source, { VITE_LIPREAD_FUSION: '1' })
  let received
  const session = { inputNames: ['lips', 'roi_z'], run: async (feeds) => { received = feeds; return { logits: { data: new Float32Array(3) } } } }
  const ort = { Tensor: class { constructor(type, data, dims) { Object.assign(this, { type, data, dims }) } } }
  await current.runRoiModel(session, new Float32Array(75 * 6400), 75, ort, new Float32Array(75 * 80))
  assert.deepEqual(Object.keys(received), ['roi_z', 'lips'])
  assert.deepEqual(received.lips.dims, [1, 75, 80])
})
