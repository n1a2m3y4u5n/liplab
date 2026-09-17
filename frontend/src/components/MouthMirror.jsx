import { useRef, useState, useCallback, useEffect } from 'react'
import AvatarVRM from './AvatarVRM'
import useFaceLandmarker from '../hooks/useFaceLandmarker'
import { toBlendshapeMap } from '../lib/mouthScore'
import { mirrorWeights, hasFaceSignal, mirrorActivity } from '../lib/mouthMirror'

/**
 * 아바타 거울 모드 (고도화 축 F).
 *
 * 계획서 3.6: 독화가 막히는 이유 중 하나는 "같은 말이라도 화자마다 입모양이 달라 낯선
 * 얼굴은 좀처럼 읽히지 않는다"는 점이다. 거울 모드는 학습자 자신의 입모양을 **평소 배우던
 * 그 아바타 얼굴로** 바꿔 보여 준다. 내가 만든 입모양이 학습 화면에서 어떻게 보이는지를
 * 같은 기준으로 확인할 수 있다.
 *
 * 영상은 서버로 전송하지 않고 브라우저 안에서만 처리한다(계획서 4.9).
 */
export default function MouthMirror({ compareVisemeId = null, compareLabel = '' }) {
  const videoRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  // 웹캠은 초당 30프레임으로 값을 갱신한다. 상태로 올리면 매 프레임 리렌더가 나므로
  // 아바타에는 ref로 넘기고, 화면 표시용 요약값만 상태로 둔다.
  const mirrorRef = useRef(null)
  const { landmarkerRef, status: modelStatus, errMsg: modelErr } = useFaceLandmarker()

  const [camStatus, setCamStatus] = useState('idle') // idle | running | error
  const [camErr, setCamErr] = useState('')
  const [faceOK, setFaceOK] = useState(true)
  const [activity, setActivity] = useState(0)

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
      if (hasFaceSignal(bs)) {
        const next = mirrorWeights(bs, mirrorRef.current)
        mirrorRef.current = next
        setFaceOK(true)
        setActivity(mirrorActivity(next))
      } else {
        // 얼굴을 놓쳤을 때: 마지막 표정에 아바타를 얼려두면 사용자는 여전히 미러링
        // 중이라고 오해한다. 중립으로 되돌리고 안내를 띄운다.
        mirrorRef.current = mirrorWeights({}, mirrorRef.current)
        setFaceOK(false)
        setActivity(0)
      }
    } catch { /* 프레임 스킵 */ }
    rafRef.current = requestAnimationFrame(loop)
  }, [landmarkerRef])

  const start = useCallback(async () => {
    if (!landmarkerRef.current) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: 480, height: 360 },
      })
      streamRef.current = stream
      videoRef.current.srcObject = stream
      await videoRef.current.play()
      setCamStatus('running')
      rafRef.current = requestAnimationFrame(loop)
    } catch {
      setCamStatus('error')
      setCamErr('카메라를 사용할 수 없어요. 권한을 허용해 주세요.')
    }
  }, [loop, landmarkerRef])

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    // 아바타를 viseme 구동으로 되돌린다(ref를 비우면 AvatarVRM이 매핑 경로를 탄다).
    mirrorRef.current = null
    setCamStatus('idle')
    setFaceOK(true)
    setActivity(0)
  }, [])

  // 언마운트 정리 — 카메라 스트림이 남아 표시등이 켜진 채로 있지 않게.
  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
  }, [])

  const running = camStatus === 'running'
  const disabled = modelStatus !== 'ready' || camStatus === 'error'

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-bold text-gray-900">
          아바타 거울 {compareLabel ? `— ${compareLabel}` : ''}
        </h4>
        <span className="text-[10px] text-gray-400">영상은 기기 안에서만 처리 · 저장/전송 안 함</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {/* 내 얼굴 — 실제 거울처럼 좌우 반전 */}
        <div className="relative overflow-hidden rounded-lg bg-gray-900" style={{ aspectRatio: '4/3' }}>
          <video ref={videoRef} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
          <span className="absolute left-1.5 top-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white">
            내 입
          </span>
          {!running && (
            <div className="absolute inset-0 grid place-items-center px-2 text-center text-xs text-white/70">
              {modelStatus === 'loading' ? '모델 불러오는 중…'
                : modelStatus === 'error' ? modelErr
                  : camStatus === 'error' ? camErr
                    : '아래 버튼으로 시작'}
            </div>
          )}
        </div>

        {/* 아바타 — 내 입모양을 그대로 따라 함 */}
        <div className="relative overflow-hidden rounded-lg bg-gray-100" style={{ aspectRatio: '4/3' }}>
          <AvatarVRM visemeId={compareVisemeId ?? 15} mirrorRef={mirrorRef} />
          <span className="absolute left-1.5 top-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white">
            아바타
          </span>
        </div>
      </div>

      {running && (
        <div className="mt-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              className="h-full rounded-full bg-slate-500 transition-all duration-100"
              style={{ width: `${Math.round(activity * 100)}%` }}
            />
          </div>
          <p className="mt-1 text-center text-xs text-gray-500" aria-live="polite">
            {faceOK ? '입을 움직이면 아바타가 따라 합니다' : '얼굴이 화면에 잘 보이게 해주세요'}
          </p>
        </div>
      )}

      <div className="mt-2 flex justify-center">
        {running ? (
          <button
            type="button"
            onClick={stop}
            className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-bold text-gray-700 hover:bg-gray-50"
          >
            멈추기
          </button>
        ) : (
          <button
            type="button"
            onClick={start}
            disabled={disabled}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40"
          >
            거울 켜기
          </button>
        )}
      </div>
    </div>
  )
}
