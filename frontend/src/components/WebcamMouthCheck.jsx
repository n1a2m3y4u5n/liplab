import { useRef, useState, useEffect, useCallback } from 'react'
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'
import { toBlendshapeMap, scorePercent, coachHint } from '../lib/mouthScore'

/**
 * 웹캠 입모양 실시간 채점 (고도화 축 D).
 * MediaPipe Face Landmarker로 얼굴 blendshape를 브라우저에서 추출해 목표 비심과 비교한다.
 * 영상·계수는 기기 밖으로 나가지 않는다(서버 전송 없음).
 */
const MP_VERSION = '1.0.1'
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

function scoreColor(s) {
  if (s >= 75) return 'text-emerald-600'
  if (s >= 45) return 'text-amber-600'
  return 'text-rose-600'
}

export default function WebcamMouthCheck({ visemeId, visemeName }) {
  const videoRef = useRef(null)
  const landmarkerRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const [status, setStatus] = useState('idle') // idle | loading | running | error
  const [score, setScore] = useState(null)
  const [hint, setHint] = useState('')
  const [errMsg, setErrMsg] = useState('')

  // 모델 로드(1회)
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        setStatus('loading')
        const vision = await FilesetResolver.forVisionTasks(WASM_URL)
        const fl = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
          outputFaceBlendshapes: true,
          runningMode: 'VIDEO',
          numFaces: 1,
        })
        if (cancelled) { fl.close?.(); return }
        landmarkerRef.current = fl
        setStatus('idle')
      } catch (e) {
        if (!cancelled) { setStatus('error'); setErrMsg('모델을 불러오지 못했어요. 네트워크를 확인해 주세요.') }
      }
    })()
    return () => { cancelled = true }
  }, [])

  const loop = useCallback(() => {
    const fl = landmarkerRef.current
    const video = videoRef.current
    if (!fl || !video || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(loop)
      return
    }
    try {
      const res = fl.detectForVideo(video, performance.now())
      const bs = toBlendshapeMap(res.faceBlendshapes?.[0])
      if (Object.keys(bs).length) {
        setScore(scorePercent(bs, visemeId))
        setHint(coachHint(bs, visemeId))
      } else {
        setScore(null)
        setHint('얼굴이 화면에 잘 보이게 해주세요')
      }
    } catch { /* 프레임 스킵 */ }
    rafRef.current = requestAnimationFrame(loop)
  }, [visemeId])

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    setStatus('idle')
    setScore(null)
    setHint('')
  }, [])

  const start = useCallback(async () => {
    if (!landmarkerRef.current) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 480, height: 360 } })
      streamRef.current = stream
      videoRef.current.srcObject = stream
      await videoRef.current.play()
      setStatus('running')
      rafRef.current = requestAnimationFrame(loop)
    } catch {
      setStatus('error')
      setErrMsg('카메라를 사용할 수 없어요. 권한을 허용해 주세요.')
    }
  }, [loop])

  // 언마운트 정리
  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
    landmarkerRef.current?.close?.()
  }, [])

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-bold text-gray-900">웹캠으로 따라하기 {visemeName ? `— ${visemeName}` : ''}</h4>
        <span className="text-[10px] text-gray-400">영상은 기기 안에서만 처리 · 저장/전송 안 함</span>
      </div>
      <div className="relative overflow-hidden rounded-lg bg-gray-900" style={{ aspectRatio: '4/3' }}>
        <video ref={videoRef} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        {status === 'running' && score !== null && (
          <div className="absolute left-2 top-2 rounded-lg bg-black/55 px-2.5 py-1 backdrop-blur-sm">
            <span className={`text-lg font-black ${scoreColor(score)}`}>{score}</span>
            <span className="ml-1 text-xs text-white/80">점</span>
          </div>
        )}
        {status !== 'running' && (
          <div className="absolute inset-0 grid place-items-center text-sm text-white/70">
            {status === 'loading' ? '모델 불러오는 중…' : status === 'error' ? errMsg : '아래 버튼으로 시작'}
          </div>
        )}
      </div>
      {status === 'running' && hint && (
        <p className="mt-2 text-center text-sm font-medium text-gray-700">{hint}</p>
      )}
      <div className="mt-2 flex justify-center">
        {status === 'running' ? (
          <button type="button" onClick={stop} className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-bold text-gray-700 hover:bg-gray-50">멈추기</button>
        ) : (
          <button type="button" onClick={start} disabled={status === 'loading' || status === 'error'}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40">
            카메라 켜기
          </button>
        )}
      </div>
    </div>
  )
}
