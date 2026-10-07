import { useCallback, useEffect, useRef, useState } from 'react'
import { playClip, silence, stopAll } from '../../lib/listenAudio'
import { listenKeyAction, sequenceMs } from '../../lib/listenView'

/**
 * 재생기. play(steps)는 소리를 차례로 튼다(steps: [{clip, opts}] 또는 [{silenceMs}]). 재생 중 다시 누르면 무시하고,
 * stop·reset(문항이 바뀔 때)은 소리를 멈추고 늦게 끝난 재생이 화면을 건드리지 못하게 한다(토큰).
 * phase: idle | playing | done. everDone은 이 문항에서 한 번이라도 끝까지 들었는가.
 * 소리 끄기(localStorage liplab_mute=1, lib/listenAudio.isMuted)는 playClip이 지킨다.
 */
const PLAYER0 = { phase: 'idle', part: 1, parts: 1, totalMs: 0, run: 0, everDone: false }
export function usePlayer() {
  const [st, setSt] = useState(PLAYER0)
  const tok = useRef(0)
  const busyRef = useRef(false)
  const reset = useCallback(() => { tok.current += 1; busyRef.current = false; stopAll(); setSt(PLAYER0) }, [])
  const stop = useCallback(() => {
    tok.current += 1
    busyRef.current = false
    stopAll()
    setSt((s) => (s.phase === 'playing' ? { ...s, phase: s.everDone ? 'done' : 'idle' } : s))
  }, [])
  const play = useCallback(async (steps, gapMs = 600) => {
    if (busyRef.current || !steps?.length) return false
    busyRef.current = true
    const id = ++tok.current
    setSt((s) => ({ ...s, phase: 'playing', part: 1, parts: steps.length, totalMs: sequenceMs(steps, gapMs), run: s.run + 1 }))
    let ok = true
    try {
      for (let i = 0; i < steps.length; i += 1) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, gapMs))
          if (tok.current !== id) return false
          setSt((s) => ({ ...s, part: i + 1 }))
        }
        const step = steps[i]
        const r = step.silenceMs != null ? await silence(step.silenceMs) : await playClip(step.clip, step.opts || {})
        if (tok.current !== id) return false
        if (!r) { ok = false; break }
      }
    } catch { ok = false }
    if (tok.current !== id) return false
    busyRef.current = false
    setSt((s) => ({ ...s, phase: ok || s.everDone ? 'done' : 'idle', everDone: s.everDone || ok }))
    return ok
  }, [])
  useEffect(() => () => { tok.current += 1; stopAll() }, [])
  return { ...st, busy: st.phase === 'playing', play, stop, reset }
}

/** 화면 키보드(lib/listenView.listenKeyAction). cfg는 매 렌더 최신 값을 읽는다. active=false면 듣지 않는다. */
export function useListenKeys(cfg) {
  const ref = useRef(cfg)
  useEffect(() => { ref.current = cfg })
  useEffect(() => {
    const onKey = (e) => {
      const c = ref.current
      if (!c || c.active === false || e.defaultPrevented) return
      const t = e.target
      const a = listenKeyAction(
        { key: e.key, code: e.code, repeat: e.repeat, altKey: e.altKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, targetTag: t?.tagName, editable: !!t?.isContentEditable },
        { canPlay: !!c.onPlay && c.canPlay !== false, optionCount: c.optionCount || 0, canPick: !!c.onPick && c.canPick !== false,
          canEnter: !!c.onEnter && c.canEnter !== false })
      if (!a) return
      e.preventDefault()
      if (a.type === 'play') c.onPlay()
      else if (a.type === 'pick') c.onPick(a.index)
      else c.onEnter()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

/**
 * 묶음 집계: 문항 수·정답 수·넘긴 수·이번 묶음에서 처음 숙달했는가·걸린 시간.
 * onAnswered(correct)를 주면 답마다 알린다(엔드리스 연습이 묶음을 넘어 합계를 낸다).
 */
export function useStageTally(initialStatus, onAnswered = null) {
  const [t, setT] = useState({ n: 0, c: 0, skipped: 0, mastered: false })
  const start = useRef(Date.now())
  const cb = useRef(onAnswered)
  cb.current = onAnswered
  const add = (correct, status) => {
    setT((s) => ({ ...s, n: s.n + 1, c: s.c + (correct ? 1 : 0),
      mastered: s.mastered || (status === 'mastered' && initialStatus !== 'mastered') }))
    cb.current?.(!!correct)
  }
  const skip = () => setT((s) => ({ ...s, skipped: s.skipped + 1 }))
  const elapsed = () => Math.floor((Date.now() - start.current) / 1000)
  return { ...t, add, skip, elapsed }
}
