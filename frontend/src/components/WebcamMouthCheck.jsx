import { useRef, useState, useEffect, useCallback } from 'react'
import { toBlendshapeMap, scorePercent, coachHint, loadCalibration } from '../lib/mouthScore'
import { faceSignals, FACE_SIGNAL_LABELS } from '../lib/faceCues'
import { lipGeometry, LIP_GEOMETRY_LABELS } from '../lib/lipGeometry'
import { predictK, K_FACE_KEYS, K_WIN } from '../lib/kModel'
import { curriculumAPI, articulationAPI } from '../api'
import useFaceLandmarker from '../hooks/useFaceLandmarker'
import MouthCalibration from './MouthCalibration'
import AvatarVRM from './AvatarVRM'
import VocalTract from './VocalTract'

/**
 * 웹캠 입모양 실시간 채점 (고도화 축 D).
 * MediaPipe Face Landmarker로 얼굴 blendshape를 브라우저에서 추출해 목표 비심과 비교한다.
 * 영상·계수는 기기 밖으로 나가지 않는다(서버 전송 없음).
 *
 * 모델 로딩은 useFaceLandmarker 훅이 담당한다(축 F 거울 모드와 공용).
 */
function scoreColor(s) {
  if (s >= 75) return 'text-emerald-600'
  if (s >= 45) return 'text-amber-600'
  return 'text-rose-600'
}

export default function WebcamMouthCheck({ visemeId, visemeName, articulationGuide = null }) {
  const videoRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const { landmarkerRef, status: modelStatus, errMsg: modelErr } = useFaceLandmarker()
  const [camStatus, setCamStatus] = useState('idle') // idle | running | error
  const [camErr, setCamErr] = useState('')
  const [score, setScore] = useState(null)
  const [hint, setHint] = useState('')
  const [recorded, setRecorded] = useState(false)
  const [faceSig, setFaceSig] = useState(null) // 입술 너머 얼굴 신호(축 K, 규칙 보조)
  const [geo, setGeo] = useState(null)         // 입술 기하 지표(그림8, 결정론적 보조)
  const [kPred, setKPred] = useState(null)     // 학습된 K 분류기 예측(유성/비음)
  const kWinRef = useRef([])                    // 최근 K_WIN 프레임의 얼굴 8차원 버퍼
  const kBusyRef = useRef(false)
  const bestRef = useRef(0)
  const [profiles, setProfiles] = useState(() => loadCalibration())
  const [showCalib, setShowCalib] = useState(false)
  const calibrated = !!profiles
  const winRef = useRef([]) // 최근 점수 창(발음 정점 포착용)
  // RAF 루프가 항상 '현재' 목표·보정값을 보게 하는 ref (레슨 전환 후 옛 값으로 채점되던 버그 방지)
  const visemeIdRef = useRef(visemeId)
  const profilesRef = useRef(profiles)
  useEffect(() => { visemeIdRef.current = visemeId }, [visemeId])
  useEffect(() => { profilesRef.current = profiles }, [profiles])
  const liveBsRef = useRef(null) // 웹캠 실시간 blendshape → 아바타 미러링(축 F)
  const artRef = useRef({ jaw: 0, round: 0, close: 0 }) // 웹캠 역추정 조음(축 E, 관찰 차원)
  const [showMirror, setShowMirror] = useState(false)
  const [mirrorXray, setMirrorXray] = useState(false) // 미러 아바타 투명 두상(축 F)
  const [correction, setCorrection] = useState(null) // 축 E: 관찰 계수 목표 대비 교정
  const [obs, setObs] = useState(null)               // 표시용 관찰 계수 샘플
  const corrBusyRef = useRef(false)

  // 목표 viseme이 바뀌면 최고점·기록·점수창 초기화
  useEffect(() => { bestRef.current = 0; winRef.current = []; setRecorded(false) }, [visemeId])

  // 화면 표시용 통합 상태 — 카메라가 우선, 그다음 모델 로딩/오류.
  const status = camStatus === 'running' ? 'running'
    : camStatus === 'error' ? 'error'
      : modelStatus === 'loading' ? 'loading'
        : modelStatus === 'error' ? 'error'
          : 'idle'
  const errMsg = camStatus === 'error' ? camErr : modelErr

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
        liveBsRef.current = bs // 아바타 미러링용(같은 ARKit 이름 → morph target 직접 구동)
        // 축 E: 관찰 가능한 조음 차원 역추정(개구·원순·폐쇄). 혀는 웹캠 미관측이라 성도 도식이 규칙값 유지.
        artRef.current = {
          jaw: bs.jawOpen || 0,
          round: Math.max(bs.mouthPucker || 0, bs.mouthFunnel || 0),
          close: bs.mouthClose || 0,
        }
        const curViseme = visemeIdRef.current   // 항상 현재 목표로 채점(옛 클로저 방지)
        const curProfiles = profilesRef.current
        const inst = scorePercent(bs, curViseme, curProfiles)
        const win = winRef.current
        win.push(inst)
        if (win.length > 25) win.shift() // 약 1초 창
        const s = Math.max(...win) // 최근 창의 최고점(발음 정점을 잡아 안정적으로 표시)
        setScore(s)
        if (s > bestRef.current) bestRef.current = s
        setHint(coachHint(bs, curViseme, curProfiles))
        setFaceSig(faceSignals(bs)) // 입술 너머 규칙 신호(K 입력)
        setGeo(lipGeometry(res.faceLandmarks?.[0])) // 입술 기하 지표(그림8) — 좌표 기반 결정론적 보조
        // 학습된 K 분류기: 최근 30프레임 창을 모아 유성/비음 확률 추론(과부하 방지 위해 순차)
        const w = kWinRef.current
        w.push(K_FACE_KEYS.map((k) => bs[k] || 0))
        if (w.length > K_WIN) w.shift()
        if (w.length === K_WIN && !kBusyRef.current) {
          kBusyRef.current = true
          const flat = new Float32Array(K_WIN * K_FACE_KEYS.length)
          for (let i = 0; i < K_WIN; i++) for (let j = 0; j < K_FACE_KEYS.length; j++) flat[i * K_FACE_KEYS.length + j] = w[i][j]
          predictK(flat).then((r) => { if (r) setKPred(r) }).finally(() => { kBusyRef.current = false })
        }
      } else {
        liveBsRef.current = null
        setScore(null)
        setHint('얼굴이 화면에 잘 보이게 해주세요')
        setFaceSig(null)
        setGeo(null)
      }
    } catch { /* 프레임 스킵 */ }
    rafRef.current = requestAnimationFrame(loop)
  }, [landmarkerRef])  // 값은 ref로 읽으므로 루프 정체성을 고정(재구성/체인 단절 방지)

  // 축 E: 관찰 계수(개구·원순·폐쇄)를 목표 조음과 비교해 "입을 더 벌리세요" 식 교정을 낸다.
  // 프레임마다가 아니라 0.8초 주기로 백엔드(순수함수)에 보내 교정 문구·계수를 받는다(교정 로직 단일 소스).
  useEffect(() => {
    if (status !== 'running') { setCorrection(null); setObs(null); return }
    const id = setInterval(() => {
      const o = { ...artRef.current }
      setObs(o)
      if (corrBusyRef.current) return
      corrBusyRef.current = true
      articulationAPI.feedback(visemeId, o)
        .then((r) => { if (r) setCorrection(r) })
        .catch(() => {})
        .finally(() => { corrBusyRef.current = false })
    }, 800)
    return () => clearInterval(id)
  }, [status, visemeId])

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    liveBsRef.current = null
    kWinRef.current = []
    setCamStatus('idle')
    setScore(null)
    setHint('')
    setKPred(null)
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
      setCamStatus('running')
      rafRef.current = requestAnimationFrame(loop)
    } catch {
      setCamStatus('error')
      setCamErr('카메라를 사용할 수 없어요. 권한을 허용해 주세요.')
    }
  }, [loop, landmarkerRef])

  // 언마운트 정리 (landmarker 자체는 useFaceLandmarker가 정리한다)
  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
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
      <div className={showMirror ? 'grid grid-cols-2 gap-2' : ''}>
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
        {/* 아바타 미러링(축 F) — 웹캠에서 읽은 입모양을 아바타가 그대로 따라한다 */}
        {showMirror && (
          <div className="relative overflow-hidden rounded-lg bg-gradient-to-b from-slate-800 to-slate-900" style={{ aspectRatio: '4/3' }}>
            <AvatarVRM visemeId={15} bsFrameRef={liveBsRef} xray={mirrorXray} />
            <div className="absolute top-1.5 left-1.5 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white/80">아바타가 따라해요</div>
            <button type="button" onClick={() => setMirrorXray((v) => !v)}
              className="absolute top-1.5 right-1.5 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white/80 hover:bg-black/70">
              {mirrorXray ? '겉면' : '투명 두상'}
            </button>
          </div>
        )}
      </div>
      {/* 성도 역추정(축 E) — 웹캠에서 읽은 개구·원순·폐쇄로 내 조음 단면을 그린다(혀는 목표 규칙값) */}
      {showMirror && (
        <div className="mt-2 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-gray-200 bg-slate-900/95 p-1">
            <p className="px-1 pb-0.5 text-[10px] text-slate-300">내 조음(성도 추정)</p>
            <div className="h-24"><VocalTract visemeId={visemeId} articulationRef={artRef} /></div>
          </div>
          <div className="rounded-lg border border-gray-200 bg-slate-900/95 p-1">
            <p className="px-1 pb-0.5 text-[10px] text-slate-300">목표 조음</p>
            <div className="h-24"><VocalTract visemeId={visemeId} /></div>
          </div>
        </div>
      )}
      {status === 'running' && hint && (
        <p className="mt-2 text-center text-sm font-medium text-gray-700">{hint}</p>
      )}
      {articulationGuide && (
        <p className="mt-1 text-center text-xs text-sky-700">
          🔎 <b>안 보이는 조음</b> — {articulationGuide}
        </p>
      )}
      {/* 축 E: 조음 교정 — 관찰 계수(개구·원순·폐쇄)를 목표와 비교해 방향을 제시하고 계수를 노출한다 */}
      {status === 'running' && correction && (
        <div className="mt-2 rounded-lg border border-sky-200 bg-sky-50/60 p-2">
          <p className="mb-1 text-center text-[10px] text-sky-600">조음 교정 · 관찰 계수 (축 E)</p>
          <p className="text-center text-sm font-semibold text-sky-900">
            {correction.ok ? '👍 조음이 목표에 가까워요' : correction.primary}
          </p>
          {obs && (
            <div className="mt-1.5 grid grid-cols-3 gap-2">
              {[['jaw', '개구'], ['round', '원순'], ['close', '폐쇄']].map(([k, label]) => (
                <div key={k} className="text-center">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-sky-100">
                    <div className="h-full rounded-full bg-sky-500 transition-all" style={{ width: `${Math.round((obs[k] || 0) * 100)}%` }} />
                  </div>
                  <span className="mt-0.5 block text-[10px] text-sky-600">{label}</span>
                </div>
              ))}
            </div>
          )}
          {correction.cues && correction.cues.length > 1 && (
            <ul className="mt-1 space-y-0.5 text-center text-[11px] text-sky-700">
              {correction.cues.slice(1).map((c, i) => <li key={i}>· {c.text}</li>)}
            </ul>
          )}
        </div>
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
      {/* 학습된 K 분류기 — 얼굴 표면신호로 '안 보이는' 유성/비음 추정(계획서 K). 실험적. */}
      {status === 'running' && kPred && (
        <div className="mt-2 rounded-lg border border-violet-200 bg-violet-50/60 p-2">
          <p className="mb-1 text-center text-[10px] text-violet-600">입술 너머 자질 추정 · 학습모델(실험)</p>
          <div className="mx-auto max-w-[220px] text-center">
            <div className="h-2 w-full overflow-hidden rounded-full bg-violet-100">
              <div className="h-full rounded-full bg-violet-500 transition-all" style={{ width: `${Math.round(kPred.nasal * 100)}%` }} />
            </div>
            <span className="mt-0.5 block text-[11px] font-medium text-violet-700">비음(코울림) {Math.round(kPred.nasal * 100)}</span>
          </div>
          {/* 유성(성대울림)은 현재 모델 신뢰도가 우연 수준(AUC≈0.55)이라 표시하지 않는다(오해 방지). */}
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
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => setShowCalib(true)}
            className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800">
            {calibrated ? '✓ 내 얼굴 맞춤 적용됨 · 다시 본뜨기' : '정확도 높이기 — 내 입모양 본뜨기'}
          </button>
          <button type="button" onClick={() => setShowMirror((v) => !v)}
            className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800">
            {showMirror ? '아바타 미러 끄기' : '🪞 아바타로 내 입모양 비추기'}
          </button>
        </div>
      </div>
    </div>
  )
}
