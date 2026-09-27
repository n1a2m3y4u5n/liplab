import { useRef, useState, useEffect, useCallback } from 'react'
import { toBlendshapeMap } from '../lib/mouthScore'
import { predictLipread, loadLipread, lipreadAvailable } from '../lib/lipreadModel'
import { resampleFrames } from '../lib/frameRate'
import { mediaErrorMessage } from '../lib/mediaError'
import { memoUntilFail } from '../lib/sharedRequest'

/**
 * 축 D — 기계가 내 입모양을 읽어본다(자체 립리딩). 사용자가 목표 단어를 입모양으로 말하면
 * 2.5초간 blendshape 시퀀스를 모아 학습 모델(onnxruntime-web)에 넣고, 폐집합 후보 중 가장
 * 가까운 단어를 '기계의 읽은 결과'로 보여준다. 영상·계수는 기기 밖으로 나가지 않는다.
 *
 * 정직: 미학습화자 정확도가 낮은 소형 실증 모델이라 '실험적 · 단어 단위 검증'으로 범위를 한정한다.
 * 모델·MediaPipe는 '카메라 켜기'를 눌렀을 때 받는다(단어 문제마다 이 칸이 뜨므로, 쓰지 않는 학습자가 20MB 넘게 받지 않게).
 */
const MP_VERSION = '1.0.1'
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
const REC_MS = 2500  // 녹화(수집) 길이
const SEQ_HZ = 60    // 모델 입력 속도. 30 fps 카메라면 프레임마다 두 번(벤치에서 검증한 제품 조건 dup2)

// MediaPipe 얼굴 모델은 모듈 전역에 한 번 만들어 문항끼리 나눈다(lipreadModel의 ONNX 세션과 같은 방식).
// 이 칸은 WordStage 결과 패널 안에 있어 문항마다 언마운트된다. 예전에는 그때 모델을 닫아, 다음 문항에서 카메라를 켤 때마다
// JS 번들·WASM·모델 로드와 GPU 초기화를 처음부터 다시 했다(문항마다 1회 → 앱을 연 동안 1회). 실패하면 비워 다시 받는다.
// VIDEO 모드 시각은 performance.now()라 인스턴스를 바꿔 써도 단조 증가한다.
const loadFaceLandmarker = memoUntilFail(async () => {
  const { FaceLandmarker, FilesetResolver } = await import('@mediapipe/tasks-vision')
  const vision = await FilesetResolver.forVisionTasks(WASM_URL)
  return FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
    outputFaceBlendshapes: true, runningMode: 'VIDEO', numFaces: 1,
  })
})

export default function LipReadCheck({ target, candidates = [] }) {
  const videoRef = useRef(null)
  const landmarkerRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const framesRef = useRef([])       // [{t, bs}] 새 영상 프레임만
  const recStartRef = useRef(0)
  const lastVideoTimeRef = useRef(-1)
  const recordingRef = useRef(false)
  const camGenRef = useRef(0)       // 언마운트마다 올린다. 켜는 중이던 카메라가 늦게 오면 끈다
  const startingRef = useRef(false)
  const recTimerRef = useRef(null)
  const [status, setStatus] = useState('idle') // idle | loading | ready | recording | thinking | done | error
  const [result, setResult] = useState(null)   // {jamo, matched, ranked}
  const [errMsg, setErrMsg] = useState('')
  const [modelOK, setModelOK] = useState(null)  // 립리딩 모델 로드 가능 여부
  const [starting, setStarting] = useState(false) // 카메라를 여는 중(권한 창 대기), 그동안 버튼을 막는다

  // 모델이 배포돼 있는지만 작은 메타 파일로 확인한다(없으면 칸을 숨김). 모델 자체는 카메라를 켤 때 받는다.
  useEffect(() => {
    let cancelled = false
    lipreadAvailable().then((ok) => { if (!cancelled) setModelOK(!!ok) })
    return () => { cancelled = true }
  }, [])

  // MediaPipe 얼굴 모델은 카메라를 켤 때 받는다(JS 번들도 그때 불러온다). 한 번 만든 모델은 다음 문항도 쓰므로 닫지 않는다.
  const ensureLandmarker = useCallback(async (gen) => {
    if (landmarkerRef.current) return landmarkerRef.current
    const fl = await loadFaceLandmarker()
    if (gen !== camGenRef.current) return null   // 받는 사이 화면을 떠났다(모델은 닫지 않고 다음 문항이 쓴다)
    landmarkerRef.current = fl
    return fl
  }, [])

  const loop = useCallback(() => {
    const fl = landmarkerRef.current, video = videoRef.current
    // 새 영상 프레임일 때만 검출한다. 화면 갱신마다 검출하면 같은 프레임이 60 Hz 화면에서 2번, 120 Hz 화면에서 4번 들어간다
    if (fl && video && video.readyState >= 2 && video.currentTime !== lastVideoTimeRef.current) {
      lastVideoTimeRef.current = video.currentTime
      try {
        const now = performance.now()
        const res = fl.detectForVideo(video, now)
        const bs = toBlendshapeMap(res.faceBlendshapes?.[0])
        if (recordingRef.current && Object.keys(bs).length) framesRef.current.push({ t: now, bs })
      } catch { /* 프레임 스킵 */ }
    }
    rafRef.current = requestAnimationFrame(loop)
  }, [])

  const startCam = useCallback(async () => {
    if (startingRef.current) return   // 권한 창·모델 받기 대기 중 두 번 눌림 방지
    startingRef.current = true; setStarting(true)
    const gen = camGenRef.current
    let stream = null
    try {
      setStatus('loading')   // 처음이면 모델을 받는다(이미 받았으면 바로 넘어간다)
      const [fl, lip] = await Promise.all([ensureLandmarker(gen).catch(() => null), loadLipread()])
      if (gen !== camGenRef.current) return
      if (!fl || !lip) { setStatus('error'); setErrMsg('입모양 모델을 불러오지 못했어요. 다시 눌러 보세요.'); return }
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 480, height: 360 } })
      // 권한을 기다리는 사이 화면을 떠났다 → 켠 카메라를 바로 끈다
      const video = videoRef.current
      if (gen !== camGenRef.current || !video) { stream.getTracks().forEach((t) => t.stop()); return }
      streamRef.current = stream
      video.srcObject = stream
      await video.play()
      if (gen !== camGenRef.current) return   // 재생을 기다리는 사이 떠났다(스트림은 정리 함수가 이미 닫았다)
      setStatus('ready')
      rafRef.current = requestAnimationFrame(loop)
    } catch (e) {
      if (gen !== camGenRef.current) return
      if (stream) stream.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      setStatus('error'); setErrMsg(mediaErrorMessage(e, 'camera'))
    } finally {
      startingRef.current = false; setStarting(false)
    }
  }, [loop, ensureLandmarker])

  const record = useCallback(() => {
    if (status !== 'ready' && status !== 'done') return
    framesRef.current = []
    recStartRef.current = performance.now()
    recordingRef.current = true
    setResult(null)
    setStatus('recording')
    recTimerRef.current = setTimeout(async () => {
      recordingRef.current = false
      setStatus('thinking')
      const seq = resampleFrames(framesRef.current, recStartRef.current, REC_MS, SEQ_HZ)
      const r = await predictLipread(seq, candidates)
      setResult(r)
      setStatus('done')
    }, REC_MS)
  }, [status, candidates])

  // 정리: 카메라·타이머·검출 루프. 얼굴 모델은 모듈 전역(loadFaceLandmarker)이라 닫지 않는다.
  useEffect(() => () => {
    camGenRef.current += 1
    clearTimeout(recTimerRef.current)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
    landmarkerRef.current = null
  }, [])

  if (modelOK === false) return null  // 모델 없으면 조용히 숨김

  const hit = result?.matched && target && result.matched === target
  return (
    <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-bold text-violet-900">기계가 내 입모양 읽기 <span className="font-normal text-violet-500">(축 D · 실험)</span></h4>
        <span className="text-[10px] text-gray-400">영상은 기기 안에서만 처리</span>
      </div>
      <div className="relative overflow-hidden rounded-lg bg-gray-900" style={{ aspectRatio: '4/3' }}>
        <video ref={videoRef} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        {status === 'recording' && (
          <div className="absolute inset-x-0 top-0 flex items-center justify-center gap-1.5 bg-rose-600/90 py-1 text-xs font-bold text-white">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-white" /> “{target}” 입모양으로 말해보세요…
          </div>
        )}
        {(status === 'idle' || status === 'loading' || status === 'error') && (
          <div className="absolute inset-0 grid place-items-center px-4 text-center text-sm text-white/75">
            {status === 'loading' ? '모델 불러오는 중…' : status === 'error' ? errMsg : '카메라를 켜고 목표 단어를 소리 없이 말해보세요'}
          </div>
        )}
        {status === 'thinking' && (
          <div className="absolute inset-0 grid place-items-center bg-black/40 text-sm text-white">기계가 읽는 중…</div>
        )}
      </div>

      {result && status === 'done' && (
        <div className="mt-2 rounded-lg border border-violet-100 bg-white p-2.5">
          {result.matched ? (
            <p className="text-center text-sm">
              기계가 읽은 단어: <b className={hit ? 'text-emerald-600' : 'text-violet-800'}>“{result.matched}”</b>
              {target && <span className={`ml-2 text-xs font-bold ${hit ? 'text-emerald-600' : 'text-rose-500'}`}>{hit ? '목표와 일치 ✓' : `목표: ${target}`}</span>}
            </p>
          ) : (
            <p className="text-center text-sm text-gray-600">읽은 자모: <b className="text-violet-800">{result.jamo || '(불명확)'}</b></p>
          )}
          {result.ranked?.length > 1 && (
            <p className="mt-1 text-center text-[11px] text-gray-400">
              후보 근접순: {result.ranked.slice(0, 3).map((r) => r.word).join(' · ')}
            </p>
          )}
          <p className="mt-1 text-center text-[10px] text-gray-400">소형 실증 모델이라 자주 틀립니다. 입모양만으로 단어를 읽는 어려움을 보여주는 실험이에요.</p>
        </div>
      )}

      <div className="mt-2 flex justify-center gap-2">
        {status === 'idle' || status === 'loading' || status === 'error' ? (
          // 카메라·모델 오류 뒤에도 다시 켜 볼 수 있다. 받는 중·권한 창 대기 중에만 막는다
          <button type="button" onClick={startCam} disabled={status === 'loading' || starting}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40">
            카메라 켜기
          </button>
        ) : (
          <button type="button" onClick={record} disabled={status === 'recording' || status === 'thinking'}
            className="rounded-lg bg-violet-600 px-4 py-1.5 text-sm font-bold text-white hover:bg-violet-700 disabled:opacity-50">
            {status === 'recording' ? '읽는 중…' : status === 'done' ? '다시 읽히기' : `“${target}” 읽히기`}
          </button>
        )}
      </div>
    </div>
  )
}
