import test from 'node:test'
import assert from 'node:assert/strict'
import { DGOP_STREAM_ENABLED, createResampler, toPcm16, createChunkUploader, startSpeakStream } from './speakStream.js'

const sine = (n, rate, hz, amp = 0.5) => Float32Array.from({ length: n }, (_, i) => amp * Math.sin((2 * Math.PI * hz * i) / rate))
const runAll = (rs, x, pieces) => {
  const outs = []
  let i = 0
  for (const p of pieces) { outs.push(rs.push(x.subarray(i, i + p))); i += p }
  outs.push(rs.push(x.subarray(i)))
  outs.push(rs.flush())
  const n = outs.reduce((a, o) => a + o.length, 0)
  const y = new Float32Array(n)
  let o = 0
  for (const a of outs) { y.set(a, o); o += a.length }
  return y
}

test('플래그는 기본 끔', () => {
  assert.equal(DGOP_STREAM_ENABLED, false)
})

test('48 kHz → 16 kHz: 길이는 floor(N/3), 440 Hz 사인의 크기와 위상이 지켜진다', () => {
  const x = sine(48000, 48000, 440)
  const y = runAll(createResampler(48000), x, [])
  assert.equal(y.length, 16000)
  const ref = sine(16000, 16000, 440)
  let maxErr = 0
  for (let i = 200; i < 15800; i++) maxErr = Math.max(maxErr, Math.abs(y[i] - ref[i]))
  assert.ok(maxErr < 0.01, `오차 ${maxErr}`)
})

test('높은 소리(7.8 kHz 위)는 16 kHz로 접히지 않고 거의 사라진다', () => {
  const x = sine(48000, 48000, 12000)
  const y = runAll(createResampler(48000), x, [])
  let rms = 0
  for (let i = 200; i < 15800; i++) rms += y[i] * y[i]
  rms = Math.sqrt(rms / 15600)
  assert.ok(rms < 0.01, `rms ${rms}`)
})

test('조각을 어떻게 나눠 넣어도 결과가 같다(44.1 kHz 포함)', () => {
  for (const rate of [48000, 44100, 16000]) {
    const x = sine(Math.round(rate * 1.3), rate, 300)
    const a = runAll(createResampler(rate), x, [])
    const b = runAll(createResampler(rate), x, [1, 4096, 4096, 17, 333, 4096, 9000])
    assert.equal(a.length, Math.floor((x.length * 16000) / rate))
    assert.deepEqual(Array.from(a), Array.from(b))
  }
})

test('toPcm16은 자르고 반올림한다', () => {
  assert.deepEqual(Array.from(toPcm16(Float32Array.from([0, 0.5, -1, 1, 2, -2]))), [0, 16384, -32768, 32767, 32767, -32768])
})

test('조각 보내기: 1초씩 차례로, 마지막은 남은 만큼, 실패하면 멈춘다', async () => {
  const sent = []
  let busy = false
  const up = createChunkUploader({
    chunkSamples: 100,
    send: async (pcm) => { assert.equal(busy, false); busy = true; await new Promise((r) => setTimeout(r, 1)); sent.push(pcm.length); busy = false },
  })
  up.push(new Float32Array(30)); up.push(new Float32Array(150)); up.push(new Float32Array(75))
  const st = await up.flush()
  assert.deepEqual(sent, [100, 100, 55])
  assert.equal(st.sent, 255)
  const bad = createChunkUploader({ chunkSamples: 10, send: async () => { throw new Error('x') } })
  bad.push(new Float32Array(25))
  assert.equal((await bad.flush()).failed, true)
})

function fakeAudio(rate) {
  const edges = []
  const node = (name) => ({ name, connect: (d) => edges.push([name, d.name]), disconnect: (d) => edges.push([name, 'x', d ? d.name : '*']) })
  const proc = node('proc')
  const ac = {
    sampleRate: rate, destination: { name: 'dest' },
    createScriptProcessor: () => proc,
    createGain: () => ({ ...node('mute'), gain: { value: 1 } }),
  }
  return { ac, source: node('src'), proc, edges }
}

test('startSpeakStream: 녹음 소리를 16 kHz PCM 조각으로 보내고 stream_id를 돌려준다', async () => {
  const { ac, source, proc, edges } = fakeAudio(48000)
  const chunks = []
  const api = { streamStart: async () => ({ stream_id: 'abc' }), streamChunk: async (id, pcm) => { chunks.push([id, pcm.length]) } }
  const ctl = startSpeakStream({ ac, source, api })
  const x = sine(48000 * 2 + 4096, 48000, 200)
  for (let i = 0; i < x.length; i += 4096) proc.onaudioprocess({ inputBuffer: { getChannelData: () => x.subarray(i, i + 4096) } })
  const id = await ctl.finish()
  assert.equal(id, 'abc')
  assert.deepEqual(chunks.map((c) => c[1]), [16000, 16000, Math.floor((x.length * 16000) / 48000) - 32000])
  assert.ok(chunks.every((c) => c[0] === 'abc'))
  assert.deepEqual(edges.slice(0, 3), [['src', 'proc'], ['proc', 'mute'], ['mute', 'dest']])
  assert.equal(proc.onaudioprocess, null)
})

test('startSpeakStream: 세션을 못 열면 null(예전 경로로 채점)', async () => {
  const { ac, source, proc } = fakeAudio(16000)
  const api = { streamStart: async () => { throw new Error('404') }, streamChunk: async () => { throw new Error('안 불려야 함') } }
  const ctl = startSpeakStream({ ac, source, api })
  proc.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(20000) } })
  assert.equal(await ctl.finish(), null)
})
