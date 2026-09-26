import { useRef, useState, useEffect, useCallback } from 'react'
import { toBlendshapeMap, scorePercent, coachHint, loadCalibration } from '../lib/mouthScore'
import { faceSignals, FACE_SIGNAL_LABELS } from '../lib/faceCues'
import { lipGeometry, LIP_GEOMETRY_LABELS } from '../lib/lipGeometry'
import { predictK, K_FACE_KEYS, K_WIN } from '../lib/kModel'
import { errorEnds } from '../lib/correctionTrend'

// 입술 너머 얼굴 신호(축 K)는 연구 빌드(VITE_LIPLAB_RESEARCH=1)에서만 보인다. 화자 영상 200클립에서 K 비음 확률이
// 비음 음절과 같은 입모양 파열음 음절을 가르지 못해(음절 AUC 0.49, docs/cue-video-demo.md) 학습자 화면에서는
// 비음 막대와 J '울림' 기호 연결(K→J)을 끄고, 규칙 신호 막대도 함께 숨긴다(9/24 결정).
const K_RESEARCH = import.meta.env.VITE_LIPLAB_RESEARCH === '1'
import { curriculumAPI, articulationAPI } from '../api'
import { mediaErrorMessage } from '../lib/mediaError'
import useFaceLandmarker from '../hooks/useFaceLandmarker'
import MouthCalibration from './MouthCalibration'
import AvatarVRM from './AvatarVRM'
import VocalTract from './VocalTract'

/**
 * 웹캠 입모양 실시간 채점 (고도화 축 D).
 * MediaPipe Face Landmarker로 얼굴 blendshape를 브라우저에서 추출해 목표 비심과 비교한다.
 * 영상과 blendshape 원본은 기기 밖으로 나가지 않는다. 서버에는 조음 교정용 관찰 계수 3개(개구·원순·폐쇄)를
 * 0.8초마다 보내 교정 문구를 받고(저장하지 않음), '익힘 기록' 때 점수와 세션 처음·끝 오차 요약만 저장한다.
 *
 * 모델 로딩은 useFaceLandmarker 훅이 담당한다(축 F 거울 모드와 공용).
 */
function scoreColor(s) {
  if (s >= 75) return 'text-emerald-600'
  if (s >= 45) return 'text-amber-600'
  return 'text-rose-600'
}

// 점수 창 길이(ms). 발음 정점을 잡으려 최근 이만큼의 최고점을 보인다. 프레임 수가 아니라 시간으로 잘라
// 화면 주사율(60·120 Hz)과 카메라 fps에 관계없이 약 1초가 된다.
const WIN_MS = 1000

export default function WebcamMouthCheck({ visemeId, visemeName, articulationGuide = null }) {
  const videoRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const lastVideoTimeRef = useRef(-1)   // 마지막으로 검출한 카메라 프레임 시각(새 프레임만 검출)
  const camGenRef = useRef(0)           // 멈춤·본뜨기 전환·언마운트마다 올린다. 켜는 중이던 카메라가 늦게 오면 끈다
  const startingRef = useRef(false)
  const artSeqRef = useRef(0)           // 얼굴을 잡은 새 프레임을 처리할 때마다 올린다(교정 표본의 신선도)
  const sentSeqRef = useRef(0)          // 마지막으로 교정 표본을 보낸 시점의 artSeqRef
  const { landmarkerRef, status: modelStatus, errMsg: modelErr } = useFaceLandmarker()
  const [camStatus, setCamStatus] = useState('idle') // idle | running | error
  const [camErr, setCamErr] = useState('')
  const [starting, setStarting] = useState(false)   // 카메라를 여는 중(권한 창 대기), 그동안 버튼을 막는다
  const [score, setScore] = useState(null)
  const [hint, setHint] = useState('')
  const [recorded, setRecorded] = useState(false)
  const [faceSig, setFaceSig] = useState(null) // 입술 너머 얼굴 신호(축 K, 규칙 보조)
  const [geo, setGeo] = useState(null)         // 입술 기하 지표(그림8, 결정론적 보조)
  const [kPred, setKPred] = useState(null)     // 학습된 K 분류기 예측(유성/비음) — 연구 빌드에서만
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
  const errRef = useRef([])                          // 축 E-9: 교정 표본별 평균 |목표−관찰| (세션 처음·끝 비교용)
  const [errTrend, setErrTrend] = useState(null)     // { start, now } — 표본 4개 이상일 때만

  // 목표 viseme이 바뀌면 최고점·기록·점수창·교정 표본 초기화
  useEffect(() => {
    bestRef.current = 0; winRef.current = []; errRef.current = []
    setRecorded(false); setErrTrend(null)
  }, [visemeId])

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
    // 새 카메라 프레임일 때만 검출한다(LipReadCheck와 같은 방식). 화면 갱신마다 검출하면 같은 프레임이 60 Hz
    // 화면에서 2번, 120 Hz 화면에서 4번 들어가, 예전 '25프레임 = 약 1초' 창이 0.4초·0.2초로 줄었다.
    if (!fl || !video || video.readyState < 2 || video.currentTime === lastVideoTimeRef.current) {
      rafRef.current = requestAnimationFrame(loop)
      return
    }
    lastVideoTimeRef.current = video.currentTime
    try {
      const now = performance.now()
      const res = fl.detectForVideo(video, now)
      const bs = toBlendshapeMap(res.faceBlendshapes?.[0])
      if (Object.keys(bs).length) {
        liveBsRef.current = bs // 아바타 미러링용(같은 ARKit 이름 → morph target 직접 구동)
        // 축 E: 관찰 가능한 조음 차원 역추정(개구·원순·폐쇄). 혀는 웹캠 미관측이라 성도 도식이 규칙값 유지.
        artRef.current = {
          jaw: bs.jawOpen || 0,
          round: Math.max(bs.mouthPucker || 0, bs.mouthFunnel || 0),
          close: bs.mouthClose || 0,
        }
        artSeqRef.current += 1
        const curViseme = visemeIdRef.current   // 항상 현재 목표로 채점(옛 클로저 방지)
        const curProfiles = profilesRef.current
        const inst = scorePercent(bs, curViseme, curProfiles)
        const win = winRef.current
        win.push({ t: now, s: inst })
        while (win.length && now - win[0].t > WIN_MS) win.shift() // 최근 약 1초 창
        let s = 0 // 최근 창의 최고점(발음 정점을 잡아 안정적으로 표시)
        for (const w of win) if (w.s > s) s = w.s
        setScore(s)
        if (s > bestRef.current) bestRef.current = s
        setHint(coachHint(bs, curViseme, curProfiles))
        setGeo(lipGeometry(res.faceLandmarks?.[0])) // 입술 기하 지표(그림8) — 좌표 기반 결정론적 보조
        if (K_RESEARCH) {
          setFaceSig(faceSignals(bs)) // 입술 너머 규칙 신호(K 입력)
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
      // 탭이 가려졌거나 지난 표본 뒤로 얼굴을 잡은 새 프레임이 없으면 보내지 않는다(예전에는 멈춘 옛 계수를 계속 보냈다)
      if (document.hidden || artSeqRef.current === sentSeqRef.current) return
      sentSeqRef.current = artSeqRef.current
      const o = { ...artRef.current }
      setObs(o)
      if (corrBusyRef.current) return
      corrBusyRef.current = true
      articulationAPI.feedback(visemeId, o)
        .then((r) => {
          if (!r) return
          setCorrection(r)
          if (typeof r.error === 'number' && liveBsRef.current) {   // 얼굴이 잡힌 표본만
            const e = errRef.current
            e.push(r.error)
            if (e.length > 600) e.splice(5, 1)   // 약 8분 상한 — 처음 5개는 남긴다
            const ends = errorEnds(e)
            if (ends) setErrTrend({ start: ends.start, now: ends.end })
          }
        })
        .catch(() => {})
        .finally(() => { corrBusyRef.current = false })
    }, 800)
    return () => clearInterval(id)
  }, [status, visemeId])

  const stop = useCallback(() => {
    camGenRef.current += 1   // 켜는 중이던 카메라는 도착하는 대로 끈다
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
    // 축 E-9: 이번 세션의 처음·끝 오차 요약만 보낸다(관찰 계수 원본은 보내지 않는다)
    const ends = errorEnds(errRef.current)
    const session = ends ? { gap_start: ends.start, gap_end: ends.end, n_samples: errRef.current.length } : {}
    try {
      await curriculumAPI.recordMouth(visemeId, bestRef.current, session)
      setRecorded(true)
    } catch { /* 기록 실패는 조용히 무시 */ }
  }, [visemeId])

  const start = useCallback(async () => {
    if (!landmarkerRef.current || startingRef.current) return   // 권한 창 대기 중 두 번 눌림 방지
    startingRef.current = true; setStarting(true)
    const gen = camGenRef.current
    let stream = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 480, height: 360 } })
      // 권한을 기다리는 사이 멈춤·본뜨기 전환·언마운트가 있었다 → 켠 카메라를 바로 끈다
      const video = videoRef.current
      if (gen !== camGenRef.current || !video) { stream.getTracks().forEach((t) => t.stop()); return }
      streamRef.current = stream
      video.srcObject = stream
      await video.play()
      if (gen !== camGenRef.current) return   // 재생을 기다리는 사이 멈췄다(스트림은 stop·정리 함수가 이미 닫았다)
      lastVideoTimeRef.current = -1
      setCamStatus('running')
      rafRef.current = requestAnimationFrame(loop)
    } catch (e) {
      if (gen !== camGenRef.current) return
      if (stream) stream.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      setCamStatus('error')
      setCamErr(mediaErrorMessage(e, 'camera'))
    } finally {
      startingRef.current = false; setStarting(false)
    }
  }, [loop, landmarkerRef])

  // 언마운트 정리 (landmarker 자체는 useFaceLandmarker가 정리한다)
  useEffect(() => () => {
    camGenRef.current += 1
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
          <b>안 보이는 조음</b> — {articulationGuide}
        </p>
      )}
      {/* 축 E: 조음 교정 — 관찰 계수(개구·원순·폐쇄)를 목표와 비교해 방향을 제시하고 계수를 노출한다 */}
      {status === 'running' && correction && (
        <div className="mt-2 rounded-lg border border-sky-200 bg-sky-50/60 p-2">
          <p className="mb-1 text-center text-[10px] text-sky-600">조음 교정 · 관찰 계수 (축 E)</p>
          <p className="text-center text-sm font-semibold text-sky-900">
            {correction.ok ? '조음이 목표에 가까워요' : correction.primary}
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
          {errTrend && (
            <p className="mt-1 text-center text-[11px] tabular-nums text-sky-700">
              목표와의 차이 · 처음 {Math.round(errTrend.start * 100)} → 지금 {Math.round(errTrend.now * 100)}
            </p>
          )}
        </div>
      )}
      {K_RESEARCH && status === 'running' && faceSig && (
        <div className="mt-2">
          <p className="mb-1 text-center text-[10px] text-gray-400">입술 너머 신호 (연구용)</p>
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
      {/* 학습된 K 분류기 — 얼굴 표면신호로 '안 보이는' 비음 추정(계획서 K). 연구 빌드에서만, 기호와 잇지 않는다. */}
      {K_RESEARCH && status === 'running' && kPred && (
        <div className="mt-2 rounded-lg border border-violet-200 bg-violet-50/60 p-2">
          <p className="mb-1 text-center text-[10px] text-violet-600">입술 너머 자질 추정 · 학습모델(연구용, 음절 수준 검증 실패)</p>
          <div className="mx-auto max-w-[220px] text-center">
            <div className="h-2 w-full overflow-hidden rounded-full bg-violet-100">
              <div className="h-full rounded-full bg-violet-500 transition-all" style={{ width: `${Math.round(kPred.nasal * 100)}%` }} />
            </div>
            <span className="mt-0.5 block text-[11px] font-medium text-violet-700">
              비음(코울림) {Math.round(kPred.nasal * 100)}
            </span>
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
          // 카메라 오류(권한·장치) 뒤에는 다시 켜 볼 수 있게 둔다. 모델이 준비되지 않았을 때만 막는다
          <button type="button" onClick={start} disabled={modelStatus !== 'ready' || starting}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-bold text-white hover:bg-slate-700 disabled:opacity-40">
            카메라 켜기
          </button>
        )}
        <div className="flex items-center gap-3">
          {/* 본뜨기는 자기 카메라를 따로 연다. 이 화면의 카메라·교정 타이머를 먼저 멈춰, 가려진 채 옛 계수를 보내거나
              돌아왔을 때 검은 화면으로 남지 않게 한다(돌아오면 '카메라 켜기'로 다시 켠다). */}
          <button type="button" onClick={() => { stop(); setShowCalib(true) }}
            className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800">
            {calibrated ? '✓ 내 얼굴 맞춤 적용됨 · 다시 본뜨기' : '정확도 높이기 — 내 입모양 본뜨기'}
          </button>
          <button type="button" onClick={() => setShowMirror((v) => !v)}
            className="text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800">
            {showMirror ? '아바타 미러 끄기' : '아바타로 내 입모양 비추기'}
          </button>
        </div>
      </div>
    </div>
  )
}
