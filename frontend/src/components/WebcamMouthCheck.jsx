import { useRef, useState, useEffect, useCallback } from 'react'
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'
import { toBlendshapeMap, scorePercent, coachHint, loadCalibration } from '../lib/mouthScore'
import { faceSignals, FACE_SIGNAL_LABELS } from '../lib/faceCues'
import { lipGeometry, LIP_GEOMETRY_LABELS } from '../lib/lipGeometry'
import { curriculumAPI } from '../api'
import MouthCalibration from './MouthCalibration'

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
  const [recorded, setRecorded] = useState(false)
  const [faceSig, setFaceSig] = useState(null) // 입술 너머 얼굴 신호(축 K, 보조)
  const [geo, setGeo] = useState(null)         // 입술 기하 지표(그림8, 결정론적 보조)
  const bestRef = useRef(0)
  const [profiles, setProfiles] = useState(() => loadCalibration())
  const [showCalib, setShowCalib] = useState(false)
  const calibrated = !!profiles
  const winRef = useRef([]) // 최근 점수 창(발음 정점 포착용)

  // 목표 viseme이 바뀌면 최고점·기록·점수창 초기화
  useEffect(() => { bestRef.current = 0; winRef.current = []; setRecorded(false) }, [visemeId])

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
        const inst = scorePercent(bs, visemeId, profiles)
        const win = winRef.current
        win.push(inst)
        if (win.length > 25) win.shift() // 약 1초 창
        const s = Math.max(...win) // 최근 창의 최고점(발음 정점을 잡아 안정적으로 표시)
        setScore(s)
        if (s > bestRef.current) bestRef.current = s
        setHint(coachHint(bs, visemeId, profiles))
        setFaceSig(faceSignals(bs)) // 입술 너머 신호(K)
        setGeo(lipGeometry(res.faceLandmarks?.[0])) // 입술 기하 지표(그림8) — 좌표 기반 결정론적 보조
      } else {
        setScore(null)
        setHint('얼굴이 화면에 잘 보이게 해주세요')
        setFaceSig(null)
        setGeo(null)
      }
    } catch { /* 프레임 스킵 */ }
    rafRef.current = requestAnimationFrame(loop)
  }, [visemeId, profiles])

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

  const record = useCallback(async () => {
    try {
      await curriculumAPI.recordMouth(visemeId, bestRef.current)
      setRecorded(true)
    } catch { /* 기록 실패는 조용히 무시 */ }
  }, [visemeId])

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

  if (showCalib) {
    return (
      <MouthCalibration
        onDone={() => { setProfiles(loadCalibration()); setShowCalib(false) }}
        onCancel={() => setShowCalib(false)}
      />
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-bold text-gray-900">웹캠으로 따라하기 {visemeName ? `— ${visemeName}` : ''}</h4>
        <span className="text-[10px] text-gray-400">영상은 기기 안에서만 처리 · 저장/전송 안 함</span>
      </div>
      <div className="relative overflow-hidden rounded-lg bg-gray-900" style={{ aspectRatio: '4/3' }}>
        <video ref={videoRef} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        {status === 'running' && score !== null && (
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent px-3 pb-2 pt-8">
            <div className="flex items-baseline gap-1">
              <span className={`text-4xl font-black leading-none ${scoreColor(score)}`}>{score}</span>
              <span className="text-sm text-white/70">점</span>
            </div>
            <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-white/25">
              <div className={`h-full rounded-full transition-all duration-150 ${score >= 75 ? 'bg-emerald-400' : score >= 45 ? 'bg-amber-400' : 'bg-rose-400'}`}
                style={{ width: `${score}%` }} />
            </div>
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
      {status === 'running' && faceSig && (
        <div className="mt-2">
          <p className="mb-1 text-center text-[10px] text-gray-400">입술 너머 신호 (보조·실험)</p>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(FACE_SIGNAL_LABELS).map(([k, label]) => (
              <div key={k} className="text-center">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
                  <div className="h-full rounded-full bg-slate-400 transition-all" style={{ width: `${Math.round((faceSig[k] || 0) * 100)}%` }} />
                </div>
                <span className="mt-0.5 block text-[10px] text-gray-500">{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {status === 'running' && geo && (
        <div className="mt-2">
          <p className="mb-1 text-center text-[10px] text-gray-400">입술 기하 지표 (좌표 기반·양안거리 정규화)</p>
          <div className="grid grid-cols-5 gap-1.5">
            {Object.entries(LIP_GEOMETRY_LABELS).map(([k, label]) => (
              <div key={k} className="rounded-md bg-slate-50 py-1 text-center">
                <span className="block text-[11px] font-bold tabular-nums text-slate-700">{geo[k]}</span>
                <span className="mt-0.5 block text-[9px] text-slate-400">{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="mt-2 flex flex-col items-center gap-1.5">
        {status === 'running' ? (
          <div className="flex gap-2">
            <button type="button" onClick={record} disabled={recorded}
              className="rounded-lg bg-emerald-600 px-4 py-1.5 text-sm font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50">
              {recorded ? '기록됨 ✓' : '익힘 기록'}
            </button>
            <button type="button" onClick={stop} className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-bold text-gray-700 hover:bg-gray-50">멈추기</button>
          </div>
        ) : (
          <button type="button" onClick={start} disabled={status === 'loading' || status === 'error'}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40">
            카메라 켜기
          </button>
        )}
        <button type="button" onClick={() => setShowCalib(true)}
          className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800">
          {calibrated ? '✓ 내 얼굴 맞춤 적용됨 · 다시 본뜨기' : '정확도 높이기 — 내 입모양 본뜨기'}
        </button>
      </div>
    </div>
  )
}
