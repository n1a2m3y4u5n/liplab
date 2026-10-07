import { useCallback, useEffect, useState } from 'react'
import { learningAPI } from '../../api'
import { loadClip, loadClipResult, loadNoise } from '../../lib/listenAudio'
import { readSettings, writeSettings, clampGainDb, fitFramesToAudio } from '../../lib/listenMix'

/** 소리 크기 설정(이 기기에만 저장, 학습자 정보 원칙 C6). save는 크기를 범위 안으로 자르고 저장 시각을 붙인다. */
export function useListenSettings() {
  const [s, setS] = useState(() => readSettings())
  const save = (v) => { const next = { ...v, gainDb: clampGainDb(v.gainDb), at: new Date().toISOString() }; writeSettings(next); setS(next) }
  return [s, save]
}

/**
 * 글 하나의 소리를 미리 받는다. state: 'loading' | 'ready' | 'missing'. reason(missing일 때): 'not_prepared' | 'network' | 'decode'
 * (lib/listenAudio.loadClipResult). retry를 부르면 다시 받는다(실패는 캐시하지 않는다).
 */
export function useClip(text, voice) {
  const [st, setSt] = useState({ clip: null, state: 'loading', reason: null })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let on = true
    if (!text) { setSt({ clip: null, state: 'missing', reason: null }); return undefined }
    setSt({ clip: null, state: 'loading', reason: null })
    loadClipResult(text, voice).then((r) => { if (on) setSt({ clip: r.clip, state: r.clip ? 'ready' : 'missing', reason: r.error }) })
    return () => { on = false }
  }, [text, voice, nonce])
  const retry = useCallback(() => setNonce((n) => n + 1), [])
  return { ...st, retry }
}

/** 잡음 파일. enabled가 false면 받지 않는다(state 'off'). */
export function useNoise(enabled, name = 'babble') {
  const [st, setSt] = useState({ noise: null, state: enabled ? 'loading' : 'off' })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let on = true
    if (!enabled) { setSt({ noise: null, state: 'off' }); return undefined }
    setSt({ noise: null, state: 'loading' })
    loadNoise(name).then((n) => { if (on) setSt({ noise: n, state: n ? 'ready' : 'missing' }) })
    return () => { on = false }
  }, [enabled, name, nonce])
  const retry = useCallback(() => setNonce((n) => n + 1), [])
  return { ...st, retry }
}

/** 다음 문항 소리를 미리 받아 둔다(넘길 때 '준비 중'이 덜 보이게). loadClip이 캐시한다. pairs: [[글, 목소리]] */
export function usePrefetch(pairs) {
  const key = pairs.map(([t, v]) => `${v}\n${t}`).join('|')
  useEffect(() => {
    const t = setTimeout(() => { for (const [text, voice] of pairs) if (text) loadClip(text, voice) }, 400)
    return () => clearTimeout(t)
  }, [key])   // eslint-disable-line react-hooks/exhaustive-deps
}

/** 소리+입모양 조건의 입모양 프레임. 소리 길이·음절 시각에 맞춘다(lib/listenMix.fitFramesToAudio). on이 false면 받지 않는다. */
export function useAvFrames(text, clip, on) {
  const [frames, setFrames] = useState(null)
  useEffect(() => {
    let alive = true
    setFrames(null)
    if (!on || !text || !clip) return undefined
    learningAPI.getVisemes(text).then((d) => {
      const fs = Array.isArray(d) ? d : d?.frames || []
      if (alive) setFrames(fitFramesToAudio(fs, clip.duration_ms, clip.syllables))
    }).catch(() => { if (alive) setFrames([]) })
    return () => { alive = false }
  }, [text, clip, on])
  return frames
}
