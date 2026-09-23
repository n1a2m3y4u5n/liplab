import { useEffect, useRef, useState, useCallback } from 'react'
import AvatarVRM from './AvatarVRM'
import { avatarAPI } from '../api'

/**
 * 음성구동 아바타(계획서 축 A4) — 실제 음성 → 52 ARKit 블렌드셰이프 립싱크.
 *
 * 텍스트→비심(engine.py) 경로와 달리, 사용자가 녹음/업로드한 '진짜 음성'을 화자 불변
 * 음성 특징(WavLM, backend/models/kr_a4_wavlm.pt)으로 받아 BiGRU 헤드가 얼굴 블렌드셰이프를 직접 회귀한다
 * (미학습 화자 jawOpen r≈0.66, 20화자 교차검증 — 평가 화자로 에폭을 고른 낙관치).
 * public/a2f-examples는 9/16에 이전 wav2vec2 8화자 모델로 미리 계산한 결과다. 프레임(30fps)을 오디오 재생과 동기화해 bsFrameRef로 아바타에 흘린다.
 *
 * 서버에 A4 모델/토치가 없으면 status=false → 기능을 숨기고 텍스트 경로만 노출(전시 빌드 안전).
 */
export default function Audio2FaceAvatar() {
  const [available, setAvailable] = useState(null) // null=확인중, false=미지원, true=지원
  const [state, setState] = useState('idle')       // idle | recording | processing | playing | error
  const [err, setErr] = useState(null)
  const [nFrames, setNFrames] = useState(0)
  const [examples, setExamples] = useState([])     // 프리컴퓨트 예시(torch 없는 배포에서도 시연)
  const [exLabel, setExLabel] = useState('')

  const bsFrameRef = useRef(null)     // 현재 프레임 {name:value} — AvatarVRM이 매 프레임 읽음
  const framesRef = useRef([])        // 미리 만든 프레임 객체 배열
  const fpsRef = useRef(30)
  const rafRef = useRef(null)
  const audioElRef = useRef(null)
  const audioUrlRef = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => {
    let alive = true
    avatarAPI.audio2faceStatus()
      .then((s) => { if (alive) setAvailable(!!s.available) })
      .catch(() => { if (alive) setAvailable(false) })
    // 프리컴퓨트 예시 로드(라이브 모델 없어도 A4 예측을 시연) — 실패해도 조용히 무시
    fetch('/a2f-examples/examples.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (alive && j) setExamples(Object.keys(j).sort().map((k) => ({ id: k, ...j[k] }))) })
      .catch(() => {})
    return () => {
      alive = false
      stopPlayback()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
    }
  }, [])

  const stopPlayback = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    bsFrameRef.current = null
    if (audioElRef.current) { try { audioElRef.current.pause() } catch { /* noop */ } }
  }, [])

  // 오디오 재생 시각에 맞춰 프레임을 bsFrameRef에 흘린다.
  const playSynced = useCallback(() => {
    const audio = audioElRef.current
    const frames = framesRef.current
    const fps = fpsRef.current
    if (!frames.length) return
    setState('playing')
    const tick = () => {
      const t = audio ? audio.currentTime : 0
      let idx = Math.floor(t * fps)
      if (idx >= frames.length) idx = frames.length - 1
      bsFrameRef.current = frames[idx]
      if (audio && (audio.ended || audio.paused)) {
        // 재생 종료 → 잠시 마지막 프레임 유지 후 rest 복귀
        bsFrameRef.current = null
        setState('idle')
        rafRef.current = null
        return
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    if (audio) {
      audio.currentTime = 0
      audio.play().catch(() => { /* 자동재생 차단 시 무음으로 프레임만 */ })
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [])

  const process = useCallback(async (blob) => {
    setErr(null); setState('processing')
    try {
      const res = await avatarAPI.audio2face(blob)
      const names = res.names || []
      const frames = (res.frames || []).map((row) => {
        const o = {}
        for (let i = 0; i < names.length; i++) o[names[i]] = row[i]
        return o
      })
      framesRef.current = frames
      fpsRef.current = res.fps || 30
      setNFrames(frames.length)
      if (!frames.length) { setState('idle'); setErr('음성이 너무 짧아요.'); return }
      // 오디오 엘리먼트 준비(동기 재생용)
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = URL.createObjectURL(blob)
      if (!audioElRef.current) audioElRef.current = new Audio()
      audioElRef.current.src = audioUrlRef.current
      audioElRef.current.onloadeddata = () => playSynced()
      audioElRef.current.load()
    } catch (e) {
      const code = e?.response?.status
      setErr(code === 503 ? '서버에 음성구동 아바타 모델이 아직 없어요.' : '분석에 실패했어요.')
      setState('error')
    }
  }, [playSynced])

  const startRec = useCallback(async () => {
    setErr(null); chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      streamRef.current = stream
      const rec = new MediaRecorder(stream)
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        if (blob.size > 500) process(blob)
        else { setErr('녹음이 비었어요.'); setState('idle') }
      }
      rec.start()
      recorderRef.current = rec
      setState('recording')
    } catch {
      setErr('마이크 권한을 허용해 주세요.')
    }
  }, [process])

  const stopRec = useCallback(() => {
    const rec = recorderRef.current
    if (rec && rec.state !== 'inactive') rec.stop()
  }, [])

  const onFile = useCallback((e) => {
    const f = e.target.files?.[0]
    if (f) process(f)
    e.target.value = ''
  }, [process])

  // 프리컴퓨트 예시 재생(라이브 모델 없이 A4 예측 시연) — 오디오 + 미리 계산한 블렌드셰이프 동기
  const playExample = useCallback((ex) => {
    const names = ex.names || []
    framesRef.current = (ex.frames || []).map((row) => {
      const o = {}; for (let i = 0; i < names.length; i++) o[names[i]] = row[i]; return o
    })
    fpsRef.current = ex.fps || 30
    setNFrames(framesRef.current.length); setExLabel(ex.text || ''); setErr(null)
    if (!audioElRef.current) audioElRef.current = new Audio()
    audioElRef.current.src = `/a2f-examples/clip_${ex.id}.wav`
    audioElRef.current.onloadeddata = () => playSynced()
    audioElRef.current.load()
  }, [playSynced])

  // 라이브 모델도 없고 예시도 없으면 조용히 숨김(전시 안전)
  if (available === false && examples.length === 0) return null

  return (
    <div className="card w-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-gray-900">내 목소리로 아바타 움직이기</h3>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 font-medium">AI 음성구동 · A4</span>
      </div>
      <p className="text-sm text-gray-500 mb-3">
        {available === true
          ? '직접 말하거나 음성 파일을 올리면, 그 소리에서 입·턱·표정 움직임을 예측해 아바타가 따라 합니다.'
          : '아래 예시 음성을 누르면, A4 모델이 그 소리에서 예측한 입모양으로 아바타가 립싱크합니다.'}
      </p>
      <div className="relative w-full rounded-2xl overflow-hidden shadow-lg bg-gradient-to-b from-slate-800 to-slate-900"
        style={{ height: '320px' }}>
        <AvatarVRM visemeId={15} bsFrameRef={bsFrameRef} />
        <div className="absolute top-3 left-3 bg-black/50 backdrop-blur-sm text-white px-2.5 py-1 rounded-lg text-xs">
          음성구동 아바타 · A4
        </div>
        {state === 'playing' && (
          <div className="absolute top-3 right-3 bg-green-500/90 text-white px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" /> 립싱크 중
          </div>
        )}
        {/* 자막(축 접근성) — 청각장애 대상이라 지금 립싱크하는 문장을 화면에 함께 보여준다. */}
        {exLabel && (
          <div role="status" aria-live="polite"
            className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-3 pt-10 text-center">
            <span className="text-white text-base font-semibold">
              {state === 'playing' && <span className="mr-1">🔊</span>}“{exLabel}”
            </span>
          </div>
        )}
      </div>

      {/* 라이브 녹음/업로드 — 서버에 A4 모델(torch)이 있을 때만 */}
      {available === true && (
        <div className="mt-3 flex items-center gap-2">
          {state === 'recording' ? (
            <button onClick={stopRec} className="flex-1 py-2.5 rounded-lg bg-red-500 hover:bg-red-600 text-white font-medium">
              ⏹ 녹음 종료 → 립싱크
            </button>
          ) : (
            <button
              onClick={startRec}
              disabled={state === 'processing'}
              className="flex-1 py-2.5 rounded-lg bg-primary-500 hover:bg-primary-600 disabled:opacity-50 text-white font-medium"
            >
              {state === 'processing' ? '분석 중…' : '🎙 말하고 아바타로 보기'}
            </button>
          )}
          <label className="py-2.5 px-3 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm cursor-pointer">
            파일
            <input type="file" accept="audio/*" onChange={onFile} className="hidden" />
          </label>
        </div>
      )}

      {/* 예시 음성(프리컴퓨트) — 어디서나 A4 예측 시연 */}
      {examples.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-gray-500 mb-1.5">예시 음성으로 보기 {available === true ? '(또는 위에서 직접 말하기)' : ''}</p>
          <div className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button key={ex.id} onClick={() => playExample(ex)} disabled={state === 'playing'}
                className="px-3 py-1.5 rounded-full border border-violet-200 bg-violet-50 text-violet-700 text-sm hover:bg-violet-100 disabled:opacity-50">
                ▶ {ex.text}
              </button>
            ))}
          </div>
        </div>
      )}

      {available === null && <p className="mt-2 text-xs text-gray-400">모델 확인 중…</p>}
      {/* 상태·오류 안내(접근성) — 스크린리더가 처리/오류 변화를 소리로 읽어 준다 */}
      <p role="status" aria-live="assertive" className={err ? 'mt-2 text-xs text-amber-600' : 'sr-only'}>
        {err || (state === 'processing' ? '음성 분석 중입니다' : state === 'playing' ? '아바타 립싱크 재생 중' : '')}
      </p>
      {nFrames > 0 && !err && (
        <p className="mt-2 text-xs text-gray-400">
          {exLabel ? `"${exLabel}" — ` : '실제 음성에서 '}{nFrames}프레임({(nFrames / fpsRef.current).toFixed(1)}초)의 얼굴 움직임을 A4가 예측했어요.
        </p>
      )}
      <p className="mt-1 text-[11px] text-gray-400 leading-relaxed">
        직접 녹음한 음성은 화자 불변 음성특징(WavLM, 20화자 학습) 모델이 입모양을 예측합니다. 처음 듣는 화자의
        입 벌림 상관은 r≈0.66인데, 평가 화자로 학습 시점을 고른 값이라 실제보다 높게 나왔을 수 있어요.
        미리 준비한 예시 5개는 이전 모델(wav2vec2, 8화자)로 계산해 둔 결과입니다.
      </p>
    </div>
  )
}
