import { useRef, useState, useEffect, useCallback } from 'react'
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'
import { toBlendshapeMap, averageBlendshapes, saveCalibration } from '../lib/mouthScore'

/**
 * 입모양 본뜨기(개인 캘리브레이션, 축 D 보정).
 * 각 viseme(대표 음절)를 사용자가 직접 지으면 그 순간 blendshape를 모아 평균내 개인
 * 기준 프로파일로 저장한다. 규칙 근사값 대신 '내 얼굴 실측'으로 채점 정확도를 높인다.
 * 영상·계수는 기기 안에서만 처리하고 localStorage에만 저장한다.
 */
const MP_VERSION = '1.0.1'
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
const COLLECT_MS = 1500 // 한 입모양을 본뜨는 수집 시간

const STEPS = [
  { id: 1, syl: '마', name: '양순음' }, { id: 2, syl: '아', name: '개방모음' },
  { id: 3, syl: '이', name: '전설모음' }, { id: 4, syl: '우', name: '원순모음' },
  { id: 5, syl: '어', name: '중설모음' }, { id: 6, syl: '다', name: '치경음' },
  { id: 7, syl: '가', name: '연구개음' }, { id: 8, syl: '하', name: '성문음' },
  { id: 9, syl: '와', name: '이중모음' }, { id: 10, syl: '자', name: '경구개음' },
]

export default function MouthCalibration({ onDone, onCancel }) {
  const videoRef = useRef(null)
  const landmarkerRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const collectRef = useRef(null) // 수집 중이면 프레임 배열
  const capturedRef = useRef({})
  const [status, setStatus] = useState('loading') // loading | running | error | saving | done
  const [stepIdx, setStepIdx] = useState(0)
  const [collecting, setCollecting] = useState(false)
  const [errMsg, setErrMsg] = useState('')

  const loop = useCallback(() => {
    const fl = landmarkerRef.current
    const video = videoRef.current
    if (fl && video && video.readyState >= 2) {
      try {
        const res = fl.detectForVideo(video, performance.now())
        const bs = toBlendshapeMap(res.faceBlendshapes?.[0])
        if (collectRef.current && Object.keys(bs).length) collectRef.current.push(bs)
      } catch { /* 프레임 스킵 */ }
    }
    rafRef.current = requestAnimationFrame(loop)
  }, [])

  // 모델 로드 + 웹캠 시작
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const vision = await FilesetResolver.forVisionTasks(WASM_URL)
        const fl = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
          outputFaceBlendshapes: true, runningMode: 'VIDEO', numFaces: 1,
        })
        if (cancelled) { fl.close?.(); return }
        landmarkerRef.current = fl
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 480, height: 360 } })
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        videoRef.current.srcObject = stream
        await videoRef.current.play()
        setStatus('running')
        rafRef.current = requestAnimationFrame(loop)
      } catch {
        if (!cancelled) { setStatus('error'); setErrMsg('카메라나 모델을 불러오지 못했어요. 권한·네트워크를 확인해 주세요.') }
      }
    })()
    return () => {
      cancelled = true
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
      landmarkerRef.current?.close?.()
    }
  }, [loop])

  const capture = useCallback(() => {
    if (collecting || status !== 'running') return
    setCollecting(true)
    collectRef.current = []
    setTimeout(() => {
      const frames = collectRef.current || []
      collectRef.current = null
      setCollecting(false)
      const step = STEPS[stepIdx]
      if (frames.length >= 5) {
        capturedRef.current[step.id] = averageBlendshapes(frames)
      }
      if (stepIdx + 1 < STEPS.length) {
        setStepIdx(stepIdx + 1)
      } else {
        setStatus('saving')
        saveCalibration(capturedRef.current)
        setStatus('done')
        onDone?.(capturedRef.current)
      }
    }, COLLECT_MS)
  }, [collecting, status, stepIdx, onDone])

  const step = STEPS[stepIdx]

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-bold text-gray-900">입모양 본뜨기 <span className="text-xs font-medium text-gray-500">{stepIdx + 1}/{STEPS.length}</span></h4>
        <button type="button" onClick={onCancel} className="text-xs text-gray-400 hover:text-gray-700">닫기</button>
      </div>
      <div className="relative overflow-hidden rounded-lg bg-gray-900" style={{ aspectRatio: '4/3' }}>
        <video ref={videoRef} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        {status === 'running' && (
          <div className="absolute inset-x-0 top-2 text-center">
            <span className="rounded-full bg-black/55 px-3 py-1 text-sm font-bold text-white backdrop-blur-sm">
              「{step.syl}」 입모양 — {step.name}
            </span>
          </div>
        )}
        {collecting && (
          <div className="absolute inset-0 grid place-items-center bg-black/30">
            <span className="animate-pulse text-lg font-black text-white">본뜨는 중…</span>
          </div>
        )}
        {status === 'loading' && <div className="absolute inset-0 grid place-items-center text-sm text-white/70">카메라 준비 중…</div>}
        {status === 'error' && <div className="absolute inset-0 grid place-items-center px-4 text-center text-sm text-white/80">{errMsg}</div>}
        {status === 'done' && <div className="absolute inset-0 grid place-items-center text-sm font-bold text-white">본뜨기 완료! 🎉</div>}
      </div>
      {status === 'running' && (
        <div className="mt-2 flex flex-col items-center gap-1">
          <p className="text-center text-xs text-gray-500">「{step.syl}」를 발음하는 입모양을 만들고 버튼을 누르세요</p>
          <button type="button" onClick={capture} disabled={collecting}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40">
            이 입모양 본뜨기
          </button>
        </div>
      )}
    </div>
  )
}
