import { useEffect, useRef, useState, useCallback } from 'react'
import AvatarVRM from './AvatarVRM'
import { avatarAPI } from '../api'
import { mediaErrorMessage } from '../lib/mediaError'

/**
 * 음성구동 아바타(계획서 축 A4) — 실제 음성 → 52 ARKit 블렌드셰이프 립싱크.
 *
 * 텍스트→비심(engine.py) 경로와 달리, 사용자가 녹음/업로드한 '진짜 음성'을 화자 불변
 * 음성 특징(WavLM, backend/models/kr_a4_wavlm.pt)으로 받아 BiGRU 헤드가 얼굴 블렌드셰이프를 직접 회귀한다
 * (미학습 화자 jawOpen r≈0.66, 20화자 교차검증 — 평가 화자로 에폭을 고른 낙관치).
 * public/a2f-examples는 macOS TTS(Yuna) 5문장을 지금 제품 모델(kr_a4_wavlm.pt)로 미리 계산한 결과다(9/23 재생성,
 * liplab-lab/tools/regen_a4_examples.py). 프레임(30fps)을 오디오 재생과 동기화해 bsFrameRef로 아바타에 흘린다.
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
  const [starting, setStarting] = useState(false)  // 마이크를 여는 중(권한 창 대기), 그동안 버튼을 막는다

  const bsFrameRef = useRef(null)     // 현재 프레임 {name:value} — AvatarVRM이 매 프레임 읽음
  const framesRef = useRef([])        // 미리 만든 프레임 객체 배열
  const fpsRef = useRef(30)
  const rafRef = useRef(null)
  const audioElRef = useRef(null)
  const audioUrlRef = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const aliveRef = useRef(true)       // 언마운트 뒤 늦게 끝난 권한 요청·분석 결과를 버린다
  const playTokenRef = useRef(0)      // 재생 회차. 새 재생·정지 때 올려 이전 루프와 play() 결과를 무시한다
  const startingRef = useRef(false)

  useEffect(() => {
    aliveRef.current = true
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
      aliveRef.current = false
      // 녹음 중에 화면을 떠나면 onstop이 분석 요청(POST)과 다른 화면에서의 재생을 시작하지 않게 끊고 멈춘다
      const rec = recorderRef.current
      if (rec) {
        rec.ondataavailable = null; rec.onstop = null
        try { if (rec.state !== 'inactive') rec.stop() } catch { /* noop */ }
        recorderRef.current = null
      }
      if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null }
      stopPlayback()
      const audio = audioElRef.current
      if (audio) { audio.removeAttribute('src'); try { audio.load() } catch { /* noop */ } }   // 받던 소리도 놓는다
      if (audioUrlRef.current) { URL.revokeObjectURL(audioUrlRef.current); audioUrlRef.current = null }
    }
  }, [])

  const stopPlayback = useCallback(() => {
    playTokenRef.current += 1
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    bsFrameRef.current = null
    if (audioElRef.current) { try { audioElRef.current.pause() } catch { /* noop */ } }
  }, [])

  const audioEl = () => {
    if (!audioElRef.current) audioElRef.current = new Audio()
    return audioElRef.current
  }

  // 오디오 재생 시각에 맞춰 프레임을 bsFrameRef에 흘린다. playPromise는 방금 부른 audio.play()의 결과다.
  // play()가 막히면(iOS·Safari 자동재생 정책, 재생할 수 없는 파일) 소리 없이 화면 시계(performance.now)로
  // 같은 속도로 흘려 아바타는 그대로 움직인다.
  const runFrames = useCallback((playPromise) => {
    const audio = audioElRef.current
    const frames = framesRef.current
    const fps = fpsRef.current
    if (!frames.length) return
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    const token = ++playTokenRef.current
    let silentFrom = null   // 무음 대체를 시작한 시각(ms). null이면 오디오 재생 시각을 따른다
    Promise.resolve(playPromise).catch(() => {
      if (token === playTokenRef.current) silentFrom = performance.now()
    })
    setState('playing')
    const tick = () => {
      if (token !== playTokenRef.current) return
      const t = silentFrom != null ? (performance.now() - silentFrom) / 1000 : (audio ? audio.currentTime : 0)
      const idx = Math.floor(t * fps)
      const ended = silentFrom != null ? idx >= frames.length : (!audio || audio.ended || audio.paused)
      if (ended) {
        // 재생 종료 → rest 복귀
        bsFrameRef.current = null
        setState('idle')
        rafRef.current = null
        return
      }
      bsFrameRef.current = frames[Math.min(idx, frames.length - 1)]
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [])

  const process = useCallback(async (blob) => {
    stopPlayback()   // 앞 재생 루프가 끝나며 상태를 idle로 되돌리지 않게 먼저 멈춘다
    setErr(null); setState('processing'); setExLabel('')   // 직접 녹음·파일은 예시 자막이 아니다
    try {
      const res = await avatarAPI.audio2face(blob)
      // 분석 중에 화면을 떠났다. 이 API는 요청 취소(AbortSignal)를 받지 않아 결과만 버린다(재생하지 않는다)
      if (!aliveRef.current) return
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
      const audio = audioEl()
      audio.src = audioUrlRef.current
      // 분석이 끝난 뒤라 탭(사용자 제스처) 밖이다 → 막히면 runFrames가 무음으로 프레임만 돌린다
      runFrames(audio.play())
    } catch (e) {
      if (!aliveRef.current) return
      const code = e?.response?.status
      setErr(code === 503 ? '서버에 음성구동 아바타 모델이 아직 없어요.' : '분석에 실패했어요.')
      setState('error')
    }
  }, [runFrames, stopPlayback])

  const startRec = useCallback(async () => {
    if (startingRef.current) return   // 권한 창이 떠 있는 동안 다시 눌러 마이크를 두 번 여는 것을 막는다
    startingRef.current = true; setStarting(true)
    // 재생 중이면 먼저 멈춘다. 재생 루프가 끝나며 상태를 idle로 돌려 '녹음 종료' 버튼이 사라지는 것을 막는다
    stopPlayback()
    setState((s) => (s === 'playing' ? 'idle' : s))
    setErr(null); chunksRef.current = []
    let stream = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      // 권한을 기다리는 사이 화면을 떠났다 → 연 마이크를 바로 닫는다
      if (!aliveRef.current) { stream.getTracks().forEach((t) => t.stop()); return }
      streamRef.current = stream
      const rec = new MediaRecorder(stream)
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        recorderRef.current = null
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        if (!aliveRef.current) return
        if (blob.size > 500) process(blob)
        else { setErr('녹음이 비었어요.'); setState('idle') }
      }
      rec.start()
      recorderRef.current = rec
      setState('recording')
    } catch (e) {
      // 마이크는 열렸는데 녹음기를 못 만든 경우(MediaRecorder 미지원 등)에도 연 마이크를 닫는다
      if (stream) stream.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      if (aliveRef.current) setErr(mediaErrorMessage(e, 'mic'))
    } finally {
      startingRef.current = false; setStarting(false)
    }
  }, [process, stopPlayback])

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
    stopPlayback()
    const names = ex.names || []
    framesRef.current = (ex.frames || []).map((row) => {
      const o = {}; for (let i = 0; i < names.length; i++) o[names[i]] = row[i]; return o
    })
    fpsRef.current = ex.fps || 30
    setNFrames(framesRef.current.length); setExLabel(ex.text || ''); setErr(null)
    const audio = audioEl()
    audio.src = `/a2f-examples/clip_${ex.id}.wav`
    // 앞서 녹음한 소리의 blob URL은 더 쓰지 않으니 놓는다
    if (audioUrlRef.current) { URL.revokeObjectURL(audioUrlRef.current); audioUrlRef.current = null }
    // 탭 안에서 바로 play()를 불러야 iOS·Safari에서도 소리가 난다(예전에는 onloadeddata에서 불러 막혔다)
    runFrames(audio.play())
  }, [runFrames, stopPlayback])

  // 녹음·분석 중(또는 마이크를 여는 중)에는 예시·파일을 막는다. 누르면 '녹음 종료'가 사라지고 녹음기는 계속 돌았다
  const busy = starting || state === 'recording' || state === 'processing'

  // 라이브 모델도 없고 예시도 없으면 조용히 숨김(전시 안전)
  if (available === false && examples.length === 0) return null

  return (
    // 카드 틀은 자유 발화 화면의 다른 카드(Figma 225:140 — 2px 테두리, r18, p22)와 맞춘다.
    <div className="w-full rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[17px] font-bold leading-figma text-ink">내 목소리로 아바타 움직이기</h3>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 font-bold">AI 음성구동 · A4</span>
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
            <span className="text-white text-base font-semibold">“{exLabel}”</span>
          </div>
        )}
      </div>

      {/* 라이브 녹음/업로드 — 서버에 A4 모델(torch)이 있을 때만 */}
      {available === true && (
        <div className="mt-3 flex items-center gap-2">
          {state === 'recording' ? (
            <button onClick={stopRec} className="flex-1 py-2.5 rounded-lg bg-red-500 hover:bg-red-600 text-white font-medium">
              녹음 종료 → 립싱크
            </button>
          ) : (
            <button
              onClick={startRec}
              disabled={state === 'processing' || starting}
              className="flex-1 py-2.5 rounded-lg bg-primary-500 hover:bg-primary-600 disabled:opacity-50 text-white font-medium"
            >
              {state === 'processing' ? '분석 중…' : '말하고 아바타로 보기'}
            </button>
          )}
          <label aria-disabled={busy}
            className={`py-2.5 px-3 rounded-lg bg-gray-100 text-gray-700 text-sm ${busy ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:bg-gray-200'}`}>
            파일
            <input type="file" accept="audio/*" onChange={onFile} disabled={busy} className="hidden" />
          </label>
        </div>
      )}

      {/* 예시 음성(프리컴퓨트) — 어디서나 A4 예측 시연 */}
      {examples.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-gray-500 mb-1.5">예시 음성으로 보기 {available === true ? '(또는 위에서 직접 말하기)' : ''}</p>
          <div className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button key={ex.id} onClick={() => playExample(ex)} disabled={state === 'playing' || busy}
                className="px-3 py-1.5 rounded-full border border-violet-200 bg-violet-50 text-violet-700 text-sm hover:bg-violet-100 disabled:opacity-50">
                {ex.text}
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
        미리 준비한 예시 5개는 합성 음성(TTS)이고, 입모양은 같은 모델로 미리 계산해 둔 결과입니다.
      </p>
    </div>
  )
}
