import { useEffect, useRef, useState } from 'react'
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'

/**
 * MediaPipe Face Landmarker 로더 (축 D 웹캠 채점 · 축 F 아바타 미러링 공용).
 *
 * 두 기능이 같은 모델·같은 초기화 절차를 쓰므로 여기로 모았다. 영상은 브라우저 안에서만
 * 처리되고 서버로 가지 않는다(계획서 4.7·4.9의 원칙).
 *
 * @returns {{landmarkerRef, status, errMsg}} status: 'loading' | 'ready' | 'error'
 */
const MP_VERSION = '1.0.1'
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}/wasm`
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

export default function useFaceLandmarker() {
  const landmarkerRef = useRef(null)
  const [status, setStatus] = useState('loading')
  const [errMsg, setErrMsg] = useState('')

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
        // 언마운트 후 늦게 도착한 로드는 즉시 정리한다(누수 방지).
        if (cancelled) { fl.close?.(); return }
        landmarkerRef.current = fl
        setStatus('ready')
      } catch {
        if (!cancelled) {
          setStatus('error')
          setErrMsg('모델을 불러오지 못했어요. 네트워크를 확인해 주세요.')
        }
      }
    })()
    return () => {
      cancelled = true
      landmarkerRef.current?.close?.()
      landmarkerRef.current = null
    }
  }, [])

  return { landmarkerRef, status, errMsg }
}
