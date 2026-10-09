import { useRef, useState, useEffect, useCallback } from 'react'
import { toBlendshapeMap, pickCalibrationFrame, saveCalibration } from '../lib/mouthScore'
import { mediaErrorMessage } from '../lib/mediaError'
import { VISEME_PLAIN } from '../lib/visemeLabels'

/**
 * 입모양 본뜨기(개인 캘리브레이션, 축 D 보정).
 * 각 viseme(대표 음절)를 사용자가 직접 지으면 그 순간 blendshape를 모아 평균내 개인
 * 기준 프로파일로 저장한다. 자음 음절은 ㅏ가 붙어 있어 정점 대신 자음 자세를 뽑는다. 규칙 근사값 대신 '내 얼굴 실측'으로 채점 정확도를 높인다.
 * 영상·계수는 기기 안에서만 처리하고 localStorage에만 저장한다.
 *
 * 얼굴 모델은 부모(WebcamMouthCheck)의 useFaceLandmarker 인스턴스(landmarkerRef·modelStatus)를 받아 쓴다. 예전에는 부모 인스턴스가
 * 살아 있는 채 자기 FaceLandmarker를 하나 더 만들어, 본뜨는 동안 모델이 2개 올라갔다(지금 1개). 부모 검출 루프는 본뜨기를 열 때
 * stop()으로 멈추고 두 곳 모두 시각이 performance.now()라 VIDEO 모드의 단조 증가 조건을 지킨다. 모델은 부모가 닫는다.
 */
const COLLECT_MS = 1500 // 한 입모양을 본뜨는 수집 시간

// cons가 있는 단계는 자음 기준이다. 자음+ㅏ 음절이라 궤적의 정점은 ㅏ이므로, 자음 자세(양순음은 입술이 닫힌 순간,
// 나머지는 모음이 열리기 직전)를 뽑는다(lib/mouthScore.js pickCalibrationFrame).
const STEPS = [
  { id: 1, syl: '마', name: '양순음', cons: 'ㅁ' }, { id: 2, syl: '아', name: '개방모음' },
  { id: 3, syl: '이', name: '전설모음' }, { id: 4, syl: '우', name: '원순모음' },
  { id: 5, syl: '어', name: '중설모음' }, { id: 6, syl: '다', name: '치경음', cons: 'ㄷ' },
  { id: 7, syl: '가', name: '연구개음', cons: 'ㄱ' }, { id: 8, syl: '하', name: '성문음', cons: 'ㅎ' },
  { id: 9, syl: '와', name: '이중모음' }, { id: 10, syl: '자', name: '경구개음', cons: 'ㅈ' },
]

function stepGuide(step) {
  if (step.id === 1) return `버튼을 누르고 「${step.syl}」를 한 번 발음하세요. 입술이 붙는 순간을 본떠요`
  if (step.cons) return `버튼을 누르고 「${step.syl}」를 한 번 발음하세요. ㅏ로 벌어지기 직전의 「${step.cons}」 입모양을 본떠요`
  return `「${step.syl}」를 발음하는 입모양을 만들고 버튼을 누르세요`
}

export default function MouthCalibration({ landmarkerRef, modelStatus, onDone, onCancel }) {
  const videoRef = useRef(null)
  const rafRef = useRef(null)
  const lastVideoTimeRef = useRef(-1)   // 마지막으로 검출한 카메라 프레임 시각(새 프레임만 검출)
  const streamRef = useRef(null)
  const collectRef = useRef(null) // 수집 중이면 프레임 배열
  const capturedRef = useRef({})
  const captureTimerRef = useRef(null)
  const [status, setStatus] = useState('loading') // loading | running | error | saving | done
  const [stepIdx, setStepIdx] = useState(0)
  const [collecting, setCollecting] = useState(false)
  const [errMsg, setErrMsg] = useState('')

  const loop = useCallback(() => {
    const fl = landmarkerRef.current
    const video = videoRef.current
    // 새 카메라 프레임일 때만 검출한다(LipReadCheck·WebcamMouthCheck와 같은 방식). 화면 갱신마다 검출하면 30 fps 카메라의
    // 같은 프레임이 60 Hz 화면에서 2번, 120 Hz 화면에서 4번 들어갔다(초당 60~120회 → 30회). 1.5초 수집은 약 45프레임이라
    // frames.length >= 5 조건에는 영향이 없다.
    if (fl && video && video.readyState >= 2 && video.currentTime !== lastVideoTimeRef.current) {
      lastVideoTimeRef.current = video.currentTime
      try {
        const res = fl.detectForVideo(video, performance.now())
        const bs = toBlendshapeMap(res.faceBlendshapes?.[0])
        if (collectRef.current && Object.keys(bs).length) collectRef.current.push(bs)
      } catch { /* 프레임 스킵 */ }
    }
    rafRef.current = requestAnimationFrame(loop)
  }, [landmarkerRef])

  // 웹캠 시작. 부모가 모델을 받는 중이면 기다리고('카메라 준비 중…'), 받지 못했으면 모델 오류를 안내한다.
  useEffect(() => {
    if (modelStatus === 'error') {
      setStatus('error')
      setErrMsg('입모양 모델을 가져오지 못했어요. 네트워크를 확인해 주세요.')
      return undefined
    }
    if (modelStatus !== 'ready') return undefined
    let cancelled = false
    ;(async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 480, height: 360 } })
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        videoRef.current.srcObject = stream
        await videoRef.current.play()
        // 재생을 기다리는 사이 닫혔다(스트림은 정리 함수가 이미 멈췄다) → 루프를 시작하지 않는다
        if (cancelled) return
        lastVideoTimeRef.current = -1
        setStatus('running')
        rafRef.current = requestAnimationFrame(loop)
      } catch (e) {
        if (!cancelled) {
          setStatus('error')
          setErrMsg(mediaErrorMessage(e, 'camera'))
        }
      }
    })()
    return () => {
      cancelled = true
      clearTimeout(captureTimerRef.current)   // 본뜨는 중에 닫으면 저장·onDone을 부르지 않는다
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
      // 얼굴 모델은 부모(useFaceLandmarker)의 것이라 여기서 닫지 않는다
    }
  }, [loop, modelStatus])

  const capture = useCallback(() => {
    if (collecting || status !== 'running') return
    setCollecting(true)
    collectRef.current = []
    captureTimerRef.current = setTimeout(() => {
      const frames = collectRef.current || []
      collectRef.current = null
      setCollecting(false)
      const step = STEPS[stepIdx]
      if (frames.length >= 5) {
        // 모음은 궤적의 정점, 자음은 자음 자세(ㅏ 벌림 이전)를 대표 입모양으로 삼는다
        capturedRef.current[step.id] = pickCalibrationFrame(frames, step.id)
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
              「{step.syl}」 입모양 — {VISEME_PLAIN[step.id]?.look || step.name}
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
        {status === 'done' && <div className="absolute inset-0 grid place-items-center text-sm font-bold text-white">본뜨기를 마쳤어요!</div>}
      </div>
      {status === 'running' && (
        <div className="mt-2 flex flex-col items-center gap-1">
          <p className="text-center text-xs text-gray-500">{stepGuide(step)}</p>
          <button type="button" onClick={capture} disabled={collecting}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40">
            이 입모양 본뜨기
          </button>
        </div>
      )}
    </div>
  )
}
