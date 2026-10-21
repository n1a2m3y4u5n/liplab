/**
 * S4 스트리밍 채점용 녹음 조각 보내기(docs/scorer-stream-latency-2026-10.md 9절). 빌드 플래그 VITE_DGOP_STREAM=1일 때만 쓴다(기본 끔).
 * 녹음하는 동안 마이크 소리를 16 kHz 16비트 PCM으로 바꿔 1초씩 서버(/api/speak/stream/{id}/chunk)에 보낸다. 서버가 4초 덩어리마다
 * 미리 순전파해 두고, 녹음이 끝나면 /api/speak/assess에 stream_id와 남은 1초 미만 조각(stream_tail)을 붙여 마지막 창과 채점만 한다. 녹음 파일(webm)은 예전처럼 함께 보내므로
 * 세션이 실패해도 서버가 예전 경로로 채점한다.
 */
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {}
export const DGOP_STREAM_ENABLED = ENV.VITE_DGOP_STREAM === '1'
export const STREAM_RATE = 16000

/**
 * 이어 받는 리샘플러(창 씌운 sinc, 정규화). inRate → outRate. push는 새로 나온 출력 표본을, flush는 남은 것을 돌려준다.
 * 조각을 어떻게 나눠 넣어도 결과가 같다(speakStream.test.mjs). 출력 길이는 floor(입력 길이 × outRate / inRate).
 */
export function createResampler(inRate, outRate = STREAM_RATE, zeroCrossings = 16) {
  const step = inRate / outRate
  const fc = 0.5 * Math.min(1, outRate / inRate) * 0.92     // 차단 주파수(입력 표본당 주기), 출력 나이퀴스트의 92%
  const W = zeroCrossings / (2 * fc)                         // 창 반폭(입력 표본)
  let buf = new Float32Array(0)
  let base = 0          // buf[0]의 입력 위치
  let total = 0         // 받은 입력 표본 수
  let k = 0             // 다음 출력 번호
  const kernel = (x) => {
    if (Math.abs(x) >= W) return 0
    const a = 2 * fc * x
    const s = a === 0 ? 1 : Math.sin(Math.PI * a) / (Math.PI * a)
    return s * (0.5 + 0.5 * Math.cos((Math.PI * x) / W))
  }
  const emit = (final) => {
    const out = []
    const maxK = Math.floor((total * outRate) / inRate)
    while (k < maxK) {
      const t = k * step
      if (!final && t + W >= total) break      // 오른쪽 창 소리가 아직 안 왔다
      const lo = Math.max(0, Math.ceil(t - W)), hi = Math.min(total - 1, Math.floor(t + W))
      let acc = 0, wsum = 0
      for (let n = lo; n <= hi; n++) {
        const w = kernel(n - t)
        acc += w * buf[n - base]
        wsum += w
      }
      out.push(wsum ? acc / wsum : 0)
      k++
    }
    const keepFrom = Math.max(base, Math.floor(k * step - W) - 1)
    if (keepFrom > base) { buf = buf.slice(keepFrom - base); base = keepFrom }
    return Float32Array.from(out)
  }
  return {
    push(x) {
      const nb = new Float32Array(buf.length + x.length)
      nb.set(buf); nb.set(x, buf.length)
      buf = nb; total += x.length
      return emit(false)
    },
    flush() { return emit(true) },
  }
}

/** float(−1~1) → 16비트 정수(자르고 반올림). */
export function toPcm16(x) {
  const out = new Int16Array(x.length)
  for (let i = 0; i < x.length; i++) {
    const v = Math.max(-1, Math.min(1, x[i]))
    out[i] = Math.round(v < 0 ? v * 32768 : v * 32767)
  }
  return out
}

/** 16 kHz 표본을 chunkSamples씩 모아 send(Int16Array)를 차례로 부른다(앞 조각이 끝난 뒤 다음 조각). 한 번 실패하면 더 보내지 않는다. */
export function createChunkUploader({ send, chunkSamples = STREAM_RATE }) {
  let pend = []
  let n = 0
  let chain = Promise.resolve()
  const state = { failed: false, sent: 0 }
  const ship = (parts, len) => {
    const f = new Float32Array(len)
    let o = 0
    for (const p of parts) { f.set(p, o); o += p.length }
    const pcm = toPcm16(f)
    chain = chain.then(async () => {
      if (state.failed) return
      try { await send(pcm); state.sent += pcm.length } catch { state.failed = true }
    })
  }
  const take = (len) => {
    const parts = []
    let need = len
    while (need > 0) {
      const p = pend[0]
      if (p.length <= need) { parts.push(p); pend.shift(); need -= p.length } else { parts.push(p.subarray(0, need)); pend[0] = p.subarray(need); need = 0 }
    }
    n -= len
    return parts
  }
  return {
    state,
    push(x) {
      if (!x || !x.length) return
      pend.push(x); n += x.length
      while (n >= chunkSamples) ship(take(chunkSamples), chunkSamples)
    },
    flush() {
      if (n > 0) { const len = n; ship(take(len), len) }
      return chain.then(() => state)
    },
    /** 보낸 조각이 다 끝나기를 기다리고, 아직 안 보낸 나머지(chunkSamples 미만)를 보내지 않고 16비트 PCM으로 돌려준다. */
    holdTail() {
      const len = n
      const f = new Float32Array(len)
      let o = 0
      for (const p of take(len)) { f.set(p, o); o += p.length }
      const tail = toPcm16(f)
      return chain.then(() => ({ ...state, tail }))
    },
  }
}

const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))])

/**
 * 녹음 하나의 스트리밍 세션. source(MediaStreamSource)에 소리 없는 처리 노드를 붙여 소리를 받는다(분석기·녹음기는 그대로).
 * end(): 받기를 멈춘다(녹음 정지 때). finish(): 남은 조각을 다 보내고 stream_id를, 실패면 null을 돌려준다.
 */
export function startSpeakStream({ ac, source, api, chunkSamples = STREAM_RATE }) {
  let id = null
  let failed = false
  let ended = false
  const ready = Promise.resolve().then(() => api.streamStart()).then((r) => { id = r && r.stream_id; if (!id) failed = true }).catch(() => { failed = true })
  const rs = createResampler(ac.sampleRate, STREAM_RATE)
  const up = createChunkUploader({
    chunkSamples,
    send: async (pcm) => {
      await ready
      if (failed || !id) throw new Error('세션 없음')
      await api.streamChunk(id, pcm)
    },
  })
  const proc = ac.createScriptProcessor(4096, 1, 1)
  const mute = ac.createGain()
  mute.gain.value = 0     // 처리 노드가 돌려면 출력에 이어져야 해서 소리 0으로 잇는다(스피커로 나가는 소리 없음)
  proc.onaudioprocess = (e) => { if (!ended) up.push(rs.push(e.inputBuffer.getChannelData(0))) }
  source.connect(proc); proc.connect(mute); mute.connect(ac.destination)
  const end = () => {
    if (ended) return
    ended = true
    proc.onaudioprocess = null
    try { source.disconnect(proc) } catch { /* 이미 끊김 */ }
    try { proc.disconnect(); mute.disconnect() } catch { /* 이미 끊김 */ }
    up.push(rs.flush())
  }
  const finish = async (timeoutMs = 4000) => {
    end()
    try { await withTimeout(up.flush(), timeoutMs) } catch { return null }
    await ready
    return failed || up.state.failed ? null : id
  }
  // 남은 조각을 따로 보내지 않고 채점 요청에 붙인다(stream_tail). 서버는 같은 순서로 넣으므로 점수는 finish()와 같고 왕복 한 번이 준다.
  // 돌려주는 값: { id, tail } 또는 실패면 null(예전 경로로 채점).
  const finishWithTail = async (timeoutMs = 4000) => {
    end()
    let st
    try { st = await withTimeout(up.holdTail(), timeoutMs) } catch { return null }
    await ready
    return failed || st.failed || !id ? null : { id, tail: st.tail }
  }
  return { end, finish, finishWithTail }
}
