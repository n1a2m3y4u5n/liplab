import { useCallback, useEffect, useRef, useState } from 'react'
import { learningAPI, soundAPI } from '../api'
import { applyCoarticulation } from '../lib/coarticulation'
import { retimeFrames, joinSegments, frameAt, overrideFor, pickSource, VISUAL_LEAD_MS } from '../lib/soundSync'

// '소리와 함께 다시 보기'(C17, 아이디어 나21). 답한 뒤에만 연다: 소리와 함께 한 번(아바타는 소리의 음절 시각에 맞춰 움직인다) →
// 소리 없이 한 번 더 → 원래 화면(반복 재생)으로. 레슨 아바타(MouthAvatar)에 override 프레임을 넘겨 같은 캔버스에서 재생한다.
//  - texts: 다시 볼 글 조각들. 보통 하나, 1단계 같은지 다른지(AX) 문항은 두 음절(사이 600ms 쉼, 문항과 같은 간격).
//  - answered: 답을 확인했는가. false면 아무것도 하지 않는다(정상 레슨에서 답 전에 소리를 틀지 않는다).
//  - enabled: 소리 조건이 켜져 있는가. 켜져 있고 답했으면 소리·프레임을 미리 받아 둔다(누르는 순간 바로 재생해야 모바일 Safari가 막지 않는다).
//  - onPlayed: 소리 재생이 시작되면 한 번 부른다(시행 기록의 sound_replay 표시).
// 반환 { phase: 'idle'|'loading'|'sound'|'silent'|'unavailable', frame(아바타 override 또는 null), start, stop, ready }

const AX_GAP_MS = 600

function silentWavUrl() {
  // 0.05초 무음 WAV. 누른 순간 같은 audio 요소로 한 번 재생해 두면 뒤에 비동기로 바꾼 소리도 모바일에서 막히지 않는다
  const n = 400
  const b = new Uint8Array(44 + n)
  const dv = new DataView(b.buffer)
  const w = (o, s) => { for (let i = 0; i < s.length; i++) b[o + i] = s.charCodeAt(i) }
  w(0, 'RIFF'); dv.setUint32(4, 36 + n, true); w(8, 'WAVEfmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true)
  dv.setUint16(22, 1, true); dv.setUint32(24, 8000, true); dv.setUint32(28, 8000, true); dv.setUint16(32, 1, true)
  dv.setUint16(34, 8, true); w(36, 'data'); dv.setUint32(40, n, true); b.fill(128, 44)
  let s = ''
  for (const x of b) s += String.fromCharCode(x)
  return `data:audio/wav;base64,${btoa(s)}`
}

export default function useSoundReplay({ texts, answered, enabled, onPlayed }) {
  const [phase, setPhase] = useState('idle')
  const [frame, setFrame] = useState(null)
  const audioRef = useRef(null)
  const runRef = useRef(0)
  const rafRef = useRef(0)
  const timerRef = useRef(0)
  const prepRef = useRef(null)          // { key, promise, data }
  const onPlayedRef = useRef(onPlayed)
  onPlayedRef.current = onPlayed
  const list = (Array.isArray(texts) ? texts : [texts]).filter((t) => typeof t === 'string' && t.trim())
  const key = list.join('\u0001')

  const audio = () => {
    if (!audioRef.current && typeof Audio !== 'undefined') {
      audioRef.current = new Audio()
      audioRef.current.preload = 'auto'
    }
    return audioRef.current
  }

  const stop = useCallback(() => {
    runRef.current += 1
    cancelAnimationFrame(rafRef.current)
    clearTimeout(timerRef.current)
    const a = audioRef.current
    if (a) { try { a.pause() } catch { /* noop */ } }
    setFrame(null)
    setPhase('idle')
  }, [])

  // 문항이 바뀌거나 답 전으로 돌아가면 멈추고 준비한 것을 버린다
  useEffect(() => { stop(); prepRef.current = null }, [key, answered, stop])
  useEffect(() => () => stop(), [stop])

  const prepare = useCallback(() => {
    if (prepRef.current?.key === key) return prepRef.current.promise
    const canPlay = (t) => audio()?.canPlayType(t) || ''
    const promise = Promise.all(list.map(async (t) => {
      const [info, frames] = await Promise.all([soundAPI.lookup(t), learningAPI.getVisemes(t)])
      if (!info) return null
      const url = pickSource(info.sources, canPlay)
      if (!url) return null
      // 파일을 미리 받아 브라우저 캐시에 넣어 둔다(1년 immutable). 누른 뒤 받기 시작하면 첫 소리가 늦는다
      try { fetch(url).catch(() => {}) } catch { /* noop */ }
      return { url, durationMs: info.duration_ms, schedule: retimeFrames(applyCoarticulation(frames), info.syllables, info.duration_ms) }
    })).then((parts) => (parts.length && parts.every(Boolean) ? { parts, ...joinSegments(parts, AX_GAP_MS) } : null))
      .catch(() => null)
    const rec = { key, promise, data: undefined }
    promise.then((d) => { rec.data = d })
    prepRef.current = rec
    return promise
  }, [key])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (answered && enabled && list.length) prepare() }, [answered, enabled, key, prepare])   // eslint-disable-line react-hooks/exhaustive-deps

  const drive = (run, schedule, clock) => {
    let last
    const tick = () => {
      if (runRef.current !== run) return
      const e = frameAt(schedule, clock() + VISUAL_LEAD_MS)
      if (e !== last) { last = e; setFrame(overrideFor(e)) }
      rafRef.current = requestAnimationFrame(tick)
    }
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)
  }

  const start = useCallback(async () => {
    if (!answered || !list.length) return
    const a = audio()
    if (!a) return
    const run = ++runRef.current
    // 누른 순간(사용자 동작 안에서) 무음으로 한 번 재생해 둔다
    try { a.src = silentWavUrl(); a.play().catch(() => {}) } catch { /* noop */ }
    setPhase('loading')
    const data = prepRef.current?.key === key && prepRef.current.data !== undefined ? prepRef.current.data : await prepare()
    if (runRef.current !== run) return
    if (!data) {
      setPhase('unavailable')
      timerRef.current = setTimeout(() => { if (runRef.current === run) setPhase('idle') }, 3500)
      return
    }
    // 1) 소리와 함께: 조각마다 소리를 틀고, 아바타는 소리의 재생 시각(currentTime)을 따른다. 조각 사이 쉼은 벽시계로
    let clock = () => 0
    setPhase('sound')
    drive(run, data.schedule, () => clock())
    let played = false
    try {
      for (let k = 0; k < data.parts.length; k++) {
        const off = data.segments[k].offset
        if (k > 0) {
          const g0 = performance.now()
          const base = data.segments[k - 1].offset + data.segments[k - 1].durationMs
          clock = () => base + (performance.now() - g0)
          await new Promise((r) => { timerRef.current = setTimeout(r, AX_GAP_MS) })
          if (runRef.current !== run) return
        }
        await new Promise((resolve, reject) => {
          a.onended = () => resolve()
          a.onerror = () => reject(new Error('audio'))
          a.src = data.parts[k].url
          clock = () => off + a.currentTime * 1000
          a.play().then(() => {
            if (!played) { played = true; try { onPlayedRef.current?.() } catch { /* 기록 실패는 무시 */ } }
          }).catch(reject)
        })
        if (runRef.current !== run) return
      }
    } catch {
      if (runRef.current !== run) return
      setPhase('unavailable')
      setFrame(null)
      cancelAnimationFrame(rafRef.current)
      timerRef.current = setTimeout(() => { if (runRef.current === run) setPhase('idle') }, 3500)
      return
    }
    // 2) 소리 없이 한 번 더: 같은 시각표를 벽시계로
    setPhase('silent')
    setFrame(overrideFor(null))
    await new Promise((r) => { timerRef.current = setTimeout(r, 500) })
    if (runRef.current !== run) return
    const t0 = performance.now()
    clock = () => performance.now() - t0
    drive(run, data.schedule, () => clock())
    await new Promise((r) => { timerRef.current = setTimeout(r, data.total + 300) })
    if (runRef.current !== run) return
    cancelAnimationFrame(rafRef.current)
    setFrame(null)
    setPhase('idle')
  }, [answered, key, prepare])   // eslint-disable-line react-hooks/exhaustive-deps

  return { phase, frame, start, stop, ready: !!prepRef.current?.data }
}
