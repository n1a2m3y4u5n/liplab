import useLessonCheckpoint from './useLessonCheckpoint'
import { requestTrackedMedia, startUsage, endUsage } from '../lib/track'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { curriculumAPI, learningAPI, speakAPI } from '../api'
import useBookmark from '../lib/useBookmark'
import { getSpeakingStageMenuItem } from '../config/speakingNavigation'
import { toBlendshapeMap, scorePercent, loadCalibration } from '../lib/mouthScore'
import { mediaErrorMessage } from '../lib/mediaError'
import { loadCoachingResult } from '../lib/speakCoaching'
import { startRecorder } from '../lib/speakRecorder'
import { finalTone, riseFallTone, toneDirection, toneMissed } from '../lib/speakTone'
import { metricVerdict, volumeFeedback } from '../lib/speakFeedback'
import { longestVoicedRun } from '../lib/voicing'
import { autoCorrelate } from '../lib/pitch'
import { PROBE_CATEGORY, PROBE_HEADING, hasProbes, nextIndex, probeStatusText, withProbes } from '../lib/speakProbe'
import { rateCueView } from '../lib/speakCue'
import { phoneChipView } from '../lib/phoneChips'
import { DGOP_STREAM_ENABLED, startSpeakStream } from '../lib/speakStream'
import { MAX_REC_MS, speakMark, INTRO_MS, cssVar, VISEME_ERR, PROSODY_SCORE_LABEL, closeContext } from '../components/speaking/speakingSupport'
export default function useSpeakingLesson() {
  useEffect(() => { startUsage('lesson', 'speaking'); return () => endUsage(false) }, [])
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const stageNo = searchParams.get('stage') != null ? parseInt(searchParams.get('stage'), 10) : null
  const reviewMode = searchParams.get('review') != null || location.pathname === '/review/speaking/session'   // 발음 복습 모드
  const selectedStageMenuItem = getSpeakingStageMenuItem(stageNo)

  const [checkpoint, saveCheckpoint, clearCheckpoint, submission] = useLessonCheckpoint('speaking')
  const [words, setWords] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'words') ? checkpoint.words : ([]))
  const [target, setTarget] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'target') ? checkpoint.target : (null))
  const [frames, setFrames] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'frames') ? checkpoint.frames : ([]))
  const [stageInfo, setStageInfo] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'stageInfo') ? checkpoint.stageInfo : (null))   // 단계 콘텐츠(있으면 단계 모드)
  const [reviewItems, setReviewItems] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'reviewItems') ? checkpoint.reviewItems : (null))  // null=로딩, []=비어있음
  const [itemIdx, setItemIdx] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'itemIdx') ? checkpoint.itemIdx : (0))
  const [progress, setProgress] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'progress') ? checkpoint.progress : (null))     // 단계 진행률(마지막 채점 결과)
  useEffect(() => { if (progress?.mastered) endUsage(true) }, [progress?.mastered])
  const [recording, setRecording] = useState(false)
  const [vol, setVol] = useState(0)
  const [pitch, setPitch] = useState(null)
  const [err, setErr] = useState(null)
  const [retry, setRetry] = useState(0)   // 로드 실패 시 '다시 불러오기'로 effect 재실행
  const [summary, setSummary] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'summary') ? checkpoint.summary : (null))
  const [assessing, setAssessing] = useState(false)
  const [assessment, setAssessment] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'assessment') ? checkpoint.assessment : (null))
  const [mirrorOn, setMirrorOn] = useState(false)   // 웹캠 미러(따라 말하기)
  const [showDetail, setShowDetail] = useState(false)   // 상세 분석 모달
  const [introDone, setIntroDone] = useState(false)  // 레슨 시작 전 트랙 로딩 최소 표시 시간
  const [starting, setStarting] = useState(false)      // 마이크를 여는 중(권한 창 대기), 그동안 마이크 버튼을 막는다
  const [mirrorBusy, setMirrorBusy] = useState(false)  // 웹캠을 여는 중, 그동안 미러 버튼을 막는다

  const items = reviewMode ? (reviewItems || []) : (stageInfo?.items || [])
  const curItem = items[itemIdx] || null
  const mode = reviewMode ? (curItem?.mode || 'word') : (stageInfo?.mode || (stageNo != null ? '' : 'word'))
  const assessStage = reviewMode ? (curItem?.stage ?? null) : stageNo   // 채점에 보낼 단계
  const drill = reviewMode ? null : (curItem?.drill || null)
  const prompt = reviewMode ? null : (curItem?.prompt || null)
  const isProbe = !reviewMode && !!curItem?.probe   // 모음·자음 단계의 낱말 속 소리 확인 문항(계획 2-5)
  const metricMode = mode === 'voicing' || mode === 'prosody'   // 지표 기반(전사 없음)
  const reviewEmpty = reviewMode && Array.isArray(reviewItems) && reviewItems.length === 0

  const acRef = useRef(null)
  const analyserRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const speakStreamRef = useRef(null)   // S4 스트리밍 녹음 세션(lib/speakStream, VITE_DGOP_STREAM=1일 때만)
  const volHist = useRef([])       // 원본 RMS(무음 포함)
  const pitchHist = useRef([])
  const traceRef = useRef([])      // {t, rms, hz|null} 시계열 — 결과 그래프용
  const startRef = useRef(0)
  const summaryRef = useRef(null)
  const framesRequestRef = useRef(0)
  const videoRef = useRef(null)          // 웹캠 미러 <video>
  const videoStreamRef = useRef(null)
  const landmarkerRef = useRef(null)     // MediaPipe FaceLandmarker(축 B AV융합용, 지연 로드)
  const mouthFramesRef = useRef([])      // 녹음 중 사용자 입모양 blendshape 버퍼
  const mouthTimesRef = useRef([])       // 위 버퍼 각 프레임의 녹음 시작 기준 시각(초) — 구간별 보완(B-6)
  const waveColorsRef = useRef(null)     // 파형 캔버스 색(토큰에서 한 번 읽음)
  const landmarkerLoadRef = useRef(null) // FaceLandmarker를 불러오는 중인 약속(두 벌 만들지 않게)
  const mediaGenRef = useRef(0)          // teardown마다 올린다. 그 전에 요청한 마이크·카메라·모델이 늦게 오면 닫고 버린다
  const attemptRef = useRef(0)           // 녹음 시도 번호(늦게 온 채점 결과가 지금 시도를 덮지 않게)
  const startingRef = useRef(false)
  const stopRef = useRef(null)           // 마이크 끊김·시간 초과 때 최신 stop을 부른다
  const autoStopRef = useRef(null)
  const mirrorBusyRef = useRef(false)

  // 미러가 켜지면 FaceLandmarker를 지연 로드(발음채점 시 입모양 신뢰도 산출 → AV 후기융합).
  // 불러오는 중이면 같은 약속을 돌려주고, 그사이 화면을 떠났으면(teardown) 다 만든 모델을 바로 닫는다.
  const ensureLandmarker = () => {
    if (landmarkerRef.current) return Promise.resolve(landmarkerRef.current)
    if (landmarkerLoadRef.current) return landmarkerLoadRef.current
    const gen = mediaGenRef.current
    const load = (async () => {
      let fl = null
      try {
        const { FaceLandmarker, FilesetResolver } = await import('@mediapipe/tasks-vision')
        const vision = await FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm')
        fl = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: { modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', delegate: 'GPU' },
          outputFaceBlendshapes: true, runningMode: 'VIDEO', numFaces: 1,
        })
      } catch { fl = null }
      if (gen !== mediaGenRef.current) { try { fl?.close?.() } catch { /* noop */ } return null }
      landmarkerLoadRef.current = null
      landmarkerRef.current = fl
      return fl
    })()
    landmarkerLoadRef.current = load
    return load
  }

  const toggleMirror = async () => {
    if (mirrorBusyRef.current) return   // 권한 창이 떠 있는 동안 다시 눌러 카메라를 두 번 여는 것을 막는다
    if (mirrorOn) {
      if (videoStreamRef.current) { videoStreamRef.current.getTracks().forEach((t) => t.stop()); videoStreamRef.current = null }
      if (videoRef.current) videoRef.current.srcObject = null
      setMirrorOn(false)
    } else {
      mirrorBusyRef.current = true; setMirrorBusy(true)
      const gen = mediaGenRef.current
      try {
        const vs = await requestTrackedMedia({ video: { facingMode: 'user' } })
        // 권한을 기다리는 사이 화면을 떠났거나 단계가 바뀌었다 → 켠 카메라를 바로 끈다
        if (gen !== mediaGenRef.current) { vs.getTracks().forEach((t) => t.stop()); return }
        videoStreamRef.current = vs
        setMirrorOn(true)
        ensureLandmarker()   // 미러 켜는 순간 모델 준비(비동기)
      } catch (e) {
        if (gen === mediaGenRef.current) setErr(mediaErrorMessage(e, 'camera'))
      } finally {
        mirrorBusyRef.current = false; setMirrorBusy(false)
      }
    }
  }
  // 미러 <video>는 결과 화면에서 사라졌다가 '다시 말하기'로 새로 붙는다 → 붙을 때마다 스트림을 연결한다(콜백 ref).
  // 예전에는 mirrorOn이 바뀔 때만 연결해, 두 번째 시도부터 화면이 검고 입모양 프레임도 모이지 않았다.
  const attachVideo = useCallback((el) => {
    videoRef.current = el
    if (el && videoStreamRef.current && el.srcObject !== videoStreamRef.current) el.srcObject = videoStreamRef.current
  }, [])

  const closeDetail = useCallback(() => setShowDetail(false), [])
  // 문항 북마크(328:49) — 발화 트랙으로 서버에 저장돼 말하기 복습에 나온다
  const [saved, toggleSaved] = useBookmark(target, { situation: '발화 연습', domain: 'speak' })
  // 레슨 시작 전 로딩 — 첫 진입에서 한 번만 최소 시간을 보장한다.
  useEffect(() => {
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [])

  // 녹음 중 버퍼된 입모양 vs 목표 비심열 → mouth_confidence(0~1). 각 목표 비심에 대해
  // 버퍼 최고 점수를 구해 평균(정렬 없이 '그 입모양이 한 번은 만들어졌나'를 잰다).
  // 점수는 방향(코사인) × 크기 정합(scorePercent/100, WebcamMouthCheck와 같은 척도). 코사인만 쓰면 턱 벌림 크기만
  // 다른 비심(2·5·7·8)을 가르지 못해 100 가까이로 포화한다(lib/mouthScore.js magnitudeMatch).
  const computeMouthConfidence = () => {
    const buf = mouthFramesRef.current
    if (!buf.length || !frames.length) return null
    const targetVis = [...new Set(frames.map((f) => f.viseme).filter((v) => v && v <= 10))]
    if (!targetVis.length) return null
    const profiles = loadCalibration() // 개인 얼굴 맞춤 기준(있으면 규칙 프로파일 대신 사용)
    let sum = 0
    for (const vid of targetVis) {
      let best = 0
      for (const bs of buf) { const c = scorePercent(bs, vid, profiles) / 100; if (c > best) best = c }
      sum += best
    }
    return Math.max(0, Math.min(1, sum / targetVis.length))
  }

  // 구간별 입모양(B-6): 프레임마다 입모양 그룹 1~10의 점수(0~1, 방향 × 크기)를 시각과 함께 보낸다. 서버는 음소(음절)가
  // 정렬된 시간 구간의 입모양 점수를 구해 따로 돌려준다(채점 점수에는 섞지 않는다, 9/24 융합 검증).
  // 얼굴 비음 추정(K-5)은 화자 영상 측정에서 비음 음절을 가르지 못해(docs/cue-video-demo.md) 보내지 않는다.
  const buildMouthTrack = async () => {
    const buf = mouthFramesRef.current
    const times = mouthTimesRef.current
    if (!buf.length || buf.length !== times.length) return null
    const profiles = loadCalibration()
    const visemes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    const rows = buf.slice(0, 1500).map((bs, i) => [
      Math.round(times[i] * 1000) / 1000,
      ...visemes.map((vid) => Math.round(Math.max(0, Math.min(1, scorePercent(bs, vid, profiles) / 100)) * 1000) / 1000),
    ])
    return { visemes, frames: rows }
  }

  useEffect(() => {
    let cancelled = false
    if (checkpoint?.target && retry === 0) return () => { teardown() }
    framesRequestRef.current += 1
    setErr(null)
    setStageInfo(null)
    setReviewItems(null)
    setItemIdx(0)
    setTarget(null)
    setFrames([])
    setSummary(null)
    setAssessment(null)
    setAssessing(false)
    setProgress(null)
    setShowDetail(false)

    if (reviewMode) {
      speakAPI.getReview()
        .then((d) => {
          if (cancelled) return
          setReviewItems(d.items || [])
          if (d.items?.length) applyItem(d.items, 0)
        })
        .catch(() => { if (!cancelled) setErr('복습을 가져오지 못했어요.') })
    } else if (stageNo != null) {
      speakAPI.getStage(stageNo)
        .then((d) => {
          if (cancelled) return
          // 숙달 점수에 이미 닿은 상태(낱말 속 소리 확인 중)면 확인 낱말부터 낸다
          const its = d.carryover && d.probes?.length ? withProbes(d.items, d.probes) : d.items
          setStageInfo({ ...d, items: its })
          applyItem(its, 0)
        })
        .catch(() => { if (!cancelled) setErr('단계를 가져오지 못했어요.') })
    } else {
      curriculumAPI.getWords()
        .then((d) => {
          if (cancelled) return
          const ws = d.words.map((w) => w.word)
          setWords(ws)
          pickWord(ws)
        })
        .catch(() => { if (!cancelled) setErr('콘텐츠를 가져오지 못했어요.') })
    }
    return () => {
      cancelled = true
      framesRequestRef.current += 1
      teardown()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stageNo, reviewMode, retry])

  const loadFrames = async (t) => {
    const requestId = ++framesRequestRef.current
    attemptRef.current += 1   // 문항이 바뀌면 이전 녹음의 늦은 채점 결과는 버린다
    setTarget(t); setFrames([]); setSummary(null); setAssessment(null); setAssessing(false); setShowDetail(false)
    setErr((e) => (e === VISEME_ERR ? null : e))
    try {
      const nextFrames = await learningAPI.getVisemes(t)
      if (requestId === framesRequestRef.current) setFrames(nextFrames)
    } catch {
      // 입모양 자료가 없으면 아바타가 가만히 있다 → 이유를 짧게 알린다
      if (requestId === framesRequestRef.current) setErr(VISEME_ERR)
    }
  }

  const applyItem = (its, idx) => {
    const it = its?.[idx]
    if (!it) return
    setItemIdx(idx)
    loadFrames(it.target)
  }

  const pickWord = async (ws) => {
    const list = ws && ws.length ? ws : words
    if (!list.length) return
    loadFrames(list[Math.floor(Math.random() * list.length)])
  }

  // 다음 항목(단계·복습) 또는 다음 단어(자유). 숙달한 뒤에는 남은 낱말 속 소리 확인 문항을 건너뛴다.
  const nextItem = () => {
    if ((reviewMode || stageNo != null) && items.length) applyItem(items, nextIndex(items, itemIdx, !!progress?.mastered))
    else pickWord()
  }

  // 레슨 중에 숙달 점수에 닿으면(낱말 속 소리 확인 시작) 확인 낱말을 받아 지금 문항 바로 뒤에 끼운다
  const probeFetchRef = useRef(false)
  const maybeAddProbes = (prog, at) => {
    if (reviewMode || stageNo == null || !prog?.probe?.carryover || prog.mastered) return
    if (probeFetchRef.current || hasProbes(stageInfo?.items)) return
    probeFetchRef.current = true
    const forStage = stageNo
    speakAPI.getStage(forStage)
      .then((d) => {
        // 그사이 다른 단계로 옮겼으면 버린다
        if (!d.probes?.length) return
        setStageInfo((s) => (s && s.stage === forStage && !hasProbes(s.items) ? { ...s, items: withProbes(s.items, d.probes, at) } : s))
      })
      .catch(() => { /* 확인 낱말을 못 받으면 다음에 단계에 들어올 때 받는다 */ })
      .finally(() => { probeFetchRef.current = false })
  }

  // 다시 말하기: 채점 중이던 이전 시도의 결과는 버린다(시도 번호를 올린다)
  const resetAttempt = () => { attemptRef.current += 1; setSummary(null); setAssessment(null); setAssessing(false); setShowDetail(false) }

  const closeAudio = () => {
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null }
    closeContext(acRef.current)
    acRef.current = null; analyserRef.current = null
  }

  const teardown = () => {
    clearTimeout(autoStopRef.current)
    mediaGenRef.current += 1   // 아직 열리는 중인 마이크·카메라·모델은 도착하는 대로 닫힌다
    attemptRef.current += 1    // 채점 중이던 결과도 버린다
    landmarkerLoadRef.current = null
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    const rec = recorderRef.current
    if (rec) { rec.onstop = null; try { if (rec.state !== 'inactive') rec.stop() } catch { /* noop */ } recorderRef.current = null }
    if (speakStreamRef.current) { speakStreamRef.current.end(); speakStreamRef.current = null }
    if (videoStreamRef.current) { videoStreamRef.current.getTracks().forEach((t) => t.stop()); videoStreamRef.current = null }
    if (landmarkerRef.current) { try { landmarkerRef.current.close?.() } catch { /* noop */ } landmarkerRef.current = null }
    setMirrorOn(false)   // 스트림을 닫았으니 미러 버튼도 꺼진 상태로 맞춘다(단계가 바뀌어 화면이 남는 경우)
    closeAudio()
  }

  const start = async () => {
    if (startingRef.current) return   // 권한 창이 떠 있는 동안 다시 눌러 마이크를 두 번 여는 것을 막는다
    startingRef.current = true; setStarting(true)
    const gen = mediaGenRef.current
    const attempt = ++attemptRef.current
    setErr(null); setSummary(null); setAssessment(null); setAssessing(false); setShowDetail(false)
    volHist.current = []; pitchHist.current = []; traceRef.current = []; chunksRef.current = []; mouthFramesRef.current = []; mouthTimesRef.current = []
    let stream = null
    try {
      // 크기를 재는 단계(발성, 운율 '크게'·'작게')는 자동 음량 조절(AGC)을 끈다. 켜 두면 브라우저가 작은 소리는 키우고
      // 큰 소리는 줄여 크기 점수가 실제 목소리와 달라진다. 나머지 단계는 예전 설정 그대로다.
      const measuresLoudness = mode === 'voicing' || drill === 'loud' || drill === 'soft'
      stream = await requestTrackedMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: !measuresLoudness },
      })
      // 권한을 기다리는 사이 화면을 떠났거나 단계가 바뀌었다 → 연 마이크를 바로 닫는다
      if (gen !== mediaGenRef.current) { stream.getTracks().forEach((t) => t.stop()); return }
      streamRef.current = stream
      const AC = window.AudioContext || window.webkitAudioContext
      const ac = new AC(); acRef.current = ac
      // 중요: 사용자 제스처 없이 만든 AudioContext는 suspended 상태로 시작할 수 있어
      // 분석 버퍼가 0으로만 읽힌다("소리 안 잡힘"의 주범) → 반드시 resume.
      if (ac.state === 'suspended') { try { await ac.resume() } catch { /* noop */ } }
      if (gen !== mediaGenRef.current) { stream.getTracks().forEach((t) => t.stop()); closeContext(ac); return }
      const src = ac.createMediaStreamSource(stream)
      const analyser = ac.createAnalyser(); analyser.fftSize = 2048
      src.connect(analyser); analyserRef.current = analyser
      // S4 스트리밍 채점(VITE_DGOP_STREAM=1, 기본 끔): 녹음 중 소리 조각을 서버에 미리 보낸다. 지표만 쓰는 발성·운율은 채점 모델을 쓰지 않아 뺀다.
      speakStreamRef.current = null
      if (DGOP_STREAM_ENABLED && !metricMode) {
        try { speakStreamRef.current = startSpeakStream({ ac, source: src, api: speakAPI }) } catch { speakStreamRef.current = null }
      }
      recorderRef.current = startRecorder(stream,
        (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data) },
        () => onRecStop(attempt))
      startRef.current = performance.now()
      setRecording(true)
      // 블루투스 끊김·통화 가로채기로 마이크가 끊기거나, 끄는 걸 잊고 오래 두면 지금까지 녹음분으로 마무리한다
      const endNow = () => { if (gen === mediaGenRef.current && recorderRef.current && recorderRef.current.state !== 'inactive') stopRef.current?.() }
      stream.getAudioTracks().forEach((t) => t.addEventListener('ended', endNow))
      clearTimeout(autoStopRef.current); autoStopRef.current = setTimeout(endNow, MAX_REC_MS)
      loop()
    } catch (e) {
      // 마이크는 열렸는데 그 뒤(AudioContext·분석기)에서 실패해도 연 장치를 닫는다
      recorderRef.current = null
      if (speakStreamRef.current) { speakStreamRef.current.end(); speakStreamRef.current = null }
      if (stream) stream.getTracks().forEach((t) => t.stop())
      closeAudio()
      if (gen === mediaGenRef.current) setErr(mediaErrorMessage(e, 'mic'))
    } finally {
      startingRef.current = false; setStarting(false)
    }
  }

  // attempt: 이 녹음을 시작할 때의 시도 번호. 그사이 '다시 말하기'·다음 문항·화면 이동으로 번호가 바뀌면
  // 채점을 보내지 않거나, 늦게 온 결과를 버린다(지금 시도의 '분석 중' 표시도 건드리지 않는다).
  const onRecStop = async (attempt) => {
    const rec = recorderRef.current
    const blob = new Blob(chunksRef.current, { type: (rec && rec.mimeType) || 'audio/webm' })
    const sctl = speakStreamRef.current
    speakStreamRef.current = null
    if (sctl) sctl.end()
    closeAudio()
    if (attempt !== attemptRef.current) return
    if (blob.size > 500 && target) {
      const s = summaryRef.current || {}
      const metrics = {
        loudness: s.loudness ?? 0, pitch_range: s.pitchRange ?? 0, duration: s.duration ?? 0,
        pitch_start: s.pitchStart ?? 0, pitch_end: s.pitchEnd ?? 0, pitch_frames: s.pitchFrames ?? null,
        pitch_ref: s.pitchRef || null, pitch_final: s.pitchFinal || null,
        voiced_duration: s.voicedDuration ?? null,
      }
      // 복습 세션이면 review=true → 백엔드가 채점/코칭만 하고 단계 숙달·해금은 건드리지 않음
      const opts = assessStage != null ? { stage: assessStage, drill, review: reviewMode, probe: isProbe } : {}
      // 축 B: 웹캠 미러로 버퍼된 입모양이 있으면 함께 보낸다. 서버는 입모양 점수를 소리 점수와 따로 돌려준다.
      const mc = computeMouthConfidence()
      if (mc != null) {
        opts.mouth_confidence = mc
        const track = await buildMouthTrack()
        if (track) opts.mouth_track = JSON.stringify(track)
      }
      if (sctl) {
        // 남은 1초 미만 조각은 채점 요청에 붙인다(왕복 한 번 줄임, 점수는 같다)
        const fin = await sctl.finishWithTail()
        if (fin) { opts.stream_id = fin.id; opts.stream_tail = fin.tail }
      }
      speakMark('speak:stream-done')
      if (attempt !== attemptRef.current) return
      setAssessing(true)
      try {
        // 점수부터 받고 Claude 코칭은 뒤따라 받는다(docs/scorer-stream-latency-2026-10.md 10절). 코칭 내용은 기다릴 때와 같다
        if (!submission.begin(target)) return
        const res = await speakAPI.assess(target, blob, metrics, { ...opts, coaching_async: true })
        submission.finish()
        speakMark('speak:score')
        if (attempt !== attemptRef.current) return
        setAssessment(res)
        if (res.progress) { setProgress(res.progress); maybeAddProbes(res.progress, itemIdx) }
        if (res.coaching_pending && res.coaching_id) loadCoaching(res.coaching_id, attempt)
      } catch (e) {
        if (attempt !== attemptRef.current) return
        setAssessment({ error: e?.response?.data?.detail || '발음 분석에 실패했어요. 잠시 후 다시 시도해 주세요.' })
      } finally {
        if (attempt === attemptRef.current) setAssessing(false)
      }
    }
  }

  // 점수는 유지하고 코칭만 재조회한다. 다른 시도로 넘어간 뒤 도착한 응답은 버린다.
  const loadCoaching = async (id, attempt) => {
    await loadCoachingResult({ id, request: speakAPI.coaching,
      isCurrent: () => attempt === attemptRef.current, update: setAssessment })
    speakMark('speak:coaching')
  }

  const stop = () => {
    speakMark('speak:stop', true)
    clearTimeout(autoStopRef.current)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    setRecording(false); setVol(0); setPitch(null)
    const s = computeSummary()
    s.trace = traceRef.current.slice()
    summaryRef.current = s
    setSummary(s)
    const rec = recorderRef.current
    if (rec && rec.state !== 'inactive') rec.stop()   // → onRecStop → 서버 분석
    else closeAudio()
  }

  stopRef.current = stop

  const computeSummary = () => {
    const raw = volHist.current, ps = pitchHist.current
    const dur = startRef.current ? Math.round((performance.now() - startRef.current) / 100) / 10 : 0
    if (!raw.length) {
      return { micIssue: true, loudness: 0, volMsg: '마이크 소리가 안 잡혔어요. 권한/연결을 확인하고 가까이서 말해보세요.', volOk: false, pitchRange: 0, duration: dur, voicedDuration: 0 }
    }
    const peak = raw.reduce((m, v) => (v > m ? v : m), 0)
    const voiced = raw.filter((v) => v > 0.01)   // 발성 프레임만 (무음 제외 → '항상 작음' 버그 방지)
    const voicedAvg = voiced.length ? voiced.reduce((a, b) => a + b, 0) / voiced.length : 0
    const loudness = Math.max(0, Math.min(100, Math.round(((voicedAvg - 0.01) / 0.13) * 100)))

    // '작게' 연습은 목표 구간(12~45)으로 본다(lib/speakFeedback)
    const { volMsg, volOk, micIssue } = volumeFeedback(loudness, peak, drill)

    // 억양 판정은 여기서 하지 않는다(연습마다 기준이 달라 lib/speakTone.js가 모드·드릴을 보고 한다)
    let pitchRange = 0, pitchMean = 0
    const { ref: pitchRef, final: pitchFinal } = finalTone(ps)   // 문장 끝 억양(5단계, 서버 sentence_direction)
    // 운율 올리기·내리기용 시작·끝 음높이(튐 제거·끝 100ms 제외, 유성 프레임이 모자라면 0)
    const { start: pitchStart, end: pitchEnd, n: pitchFrames } = riseFallTone(traceRef.current)
    if (ps.length >= 4) {
      const sorted = [...ps].sort((a, b) => a - b)
      const lo = sorted[Math.floor(sorted.length * 0.1)]
      const hi = sorted[Math.floor(sorted.length * 0.9)]
      pitchRange = Math.round(hi - lo)
      pitchMean = Math.round(ps.reduce((a, b) => a + b, 0) / ps.length)
    }
    // 발성 단계·'길게' 연습은 녹음 길이가 아니라 가장 길게 이어 낸 소리로 판정한다(lib/voicing)
    const voicedDuration = longestVoicedRun(traceRef.current)
    return { micIssue, loudness, volMsg, volOk, pitchRange, pitchMean, pitchStart, pitchEnd, pitchFrames, pitchRef, pitchFinal, duration: dur, voicedDuration }
  }

  const loop = () => {
    const analyser = analyserRef.current
    if (!analyser) return
    const buf = new Float32Array(analyser.fftSize)
    let frame = 0
    const tick = () => {
      if (!analyserRef.current) return
      analyser.getFloatTimeDomainData(buf)
      let rms = 0
      for (let i = 0; i < buf.length; i++) rms += buf[i] * buf[i]
      rms = Math.sqrt(rms / buf.length)
      volHist.current.push(rms)                       // 원본 RMS 저장
      const disp = Math.min(1, rms / 0.12)            // 표시용 스케일(0.12 RMS ≈ 꽉 참)
      drawWave(buf, disp)
      if (frame % 4 === 0) {
        const p = autoCorrelate(buf, acRef.current.sampleRate)
        const hz = p > 70 && p < 500 ? Math.round(p) : null
        if (hz) pitchHist.current.push(hz)
        traceRef.current.push({ t: (performance.now() - startRef.current) / 1000, rms, hz })
        setVol(disp); setPitch(hz)
      }
      // 축 B: 미러가 켜져 있으면 입모양 blendshape를 버퍼링(발화 중 입 형태 → 따로 보여 줄 입모양 점수)
      if (frame % 3 === 0 && landmarkerRef.current && videoRef.current && videoRef.current.readyState >= 2) {
        try {
          const r = landmarkerRef.current.detectForVideo(videoRef.current, performance.now())
          const bs = toBlendshapeMap(r.faceBlendshapes?.[0])
          if (Object.keys(bs).length) {
            mouthFramesRef.current.push(bs)
            mouthTimesRef.current.push((performance.now() - startRef.current) / 1000)
          }
        } catch { /* 프레임 스킵 */ }
      }
      frame++
      rafRef.current = requestAnimationFrame(tick)
    }
    tick()
  }

  const drawWave = (buf, v) => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    const W = cv.width, H = cv.height
    ctx.clearRect(0, 0, W, H)
    // 소리 있음 = 트랙 분홍, 무음 = 회색 — 토큰 색은 한 번만 읽어 둔다(매 프레임 getComputedStyle 방지)
    if (!waveColorsRef.current) waveColorsRef.current = { on: cssVar(cv, '--track'), off: cssVar(cv, '--fill-strong') }
    ctx.lineWidth = 2
    ctx.strokeStyle = v > 0.15 ? waveColorsRef.current.on : waveColorsRef.current.off
    ctx.beginPath()
    // 버퍼 전체(2048)를 캔버스 폭(480)에 고르게 편다. 예전 정수 간격(5)은 480×5가 버퍼를 넘어 오른쪽 약 15%가 평평했다.
    const ratio = buf.length / W
    for (let x = 0; x < W; x++) {
      const s = buf[Math.floor(x * ratio)] || 0
      const y = H / 2 + s * (H / 2) * 0.9
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.stroke()
  }

  const volLabel = !recording ? '-' : vol < 0.15 ? '작게' : vol > 0.95 ? '크게' : '좋아요'

  // 진행바 — 단계/복습이면 항목 진행(푼 문항 / 전체, 6 / 12), 자유면 숙달률
  const total = (reviewMode || stageNo != null) && items.length ? items.length : null
  const cur = total ? itemIdx + 1 : null
  const barPct = total ? ((itemIdx + (summary ? 1 : 0)) / total) * 100 : (progress ? Math.min(progress.mastery_score, 100) : 8)

  const category = reviewMode
    ? '말하기 복습'
    : isProbe ? PROBE_CATEGORY
      : (drill || stageInfo?.title || selectedStageMenuItem?.label || '발음 연습')
  const heading = isProbe ? PROBE_HEADING : (prompt || '이 단어를 소리 내어 말해보세요')
  const probeLine = progress?.mastered ? null : probeStatusText(progress?.probe)

  // 결과 점수·판정
  const phones = (!metricMode && assessment && !assessment.error && assessment.acoustic_dgop?.phones) || []
  const scoreNum = assessment && !assessment.error ? assessment.score
    : (metricMode && summary ? summary.loudness : null)
  // 지표 모드는 서버가 잰 것에 맞춰 이름을 붙인다. 서버 점수 전(또는 실패)에는 위처럼 소리 크기를 보이므로 '목소리 크기'.
  const scoreLabel = !metricMode ? '발음 점수'
    : !(assessment && !assessment.error) ? '목소리 크기'
      : mode === 'voicing' ? '길이·크기'
        : (PROSODY_SCORE_LABEL[drill] || '운율')
  const localGood = summary ? (summary.volOk && !toneMissed(summary, toneDirection(mode, drill))) : null
  // 소리별 칩(S2): 서버가 신뢰도 표로 reliable을 붙였으면 믿을 만한 소리만 색으로 확정하고 나머지는 회색 참고(lib/phoneChips)
  const chipView = phoneChipView(phones, assessment?.acoustic_dgop?.reliability_map)
  // 지표 모드: 서버 판정·note를 쓰고, 응답 전에는 판정하지 않는다(good null = '분석 중')
  const metricFb = metricMode ? metricVerdict({ assessment, assessing, summary, localGood }) : null
  const good = metricFb ? metricFb.good
    : assessment && !assessment.error ? (assessment.passed ?? (assessment.score >= 65)) : localGood
  // 판정 보류(S9): 점수가 합격선 ± 1 SEM(재검사 오차) 안이면 한 번으로는 판단하기 어렵다고 알리고 한 번 더 말하기를 권한다.
  // 숙달 계산은 서버의 passed 그대로다(docs/scoring-analyses-2026-10.md S14)
  const hold = !metricFb && !!(assessment && !assessment.error && assessment.hold)
  const fbSub = metricFb ? metricFb.sub
    : hold ? '점수가 합격선 근처예요. 한 번 더 말하면 더 정확히 알 수 있어요'
      : good ? (chipView.sure ? `${chipView.sure}개 중 ${chipView.sureGood}개 소리를 정확히 냈어요` : (summary?.volMsg || '잘 전달됐어요'))
        : '소리가 잘 전달되지 않았어요'
  const fbTitle = metricFb ? metricFb.title : hold ? '한 번 더 말해 볼까요?' : good ? '잘했어요!' : '조금 더 연습해요'
  const barTone = good == null ? 'border-line bg-white text-ink-muted' : hold ? 'border-warn/35 bg-warn-tint'
    : good ? 'border-good/35 bg-good-tint' : 'border-bad/35 bg-bad-tint'
  // 나가기 → 발화 커리큘럼 경로(?track=speak). /dashboard는 독화 경로로 리다이렉트된다.
  const exit = () => { teardown(); navigate(reviewMode ? '/review/speaking' : '/learn/path?track=speak') }

  const exitError = err && !stageInfo && !reviewMode && stageNo != null && !target

  // 입모양 점수 — 기본은 채점 점수(소리)와 따로 보인다(mouth). 서버가 연구용 융합(LIPLAB_AV_FUSION=1)을 켜면
  // 예전 '소리 + 입모양 융합'(182:77)을 보이고, 그때 소리 점수는 융합 전 음향 점수(audio_score)로 보충한다.
  const mouthRes = assessment && !assessment.error ? assessment.mouth : null
  const fusion = assessment && !assessment.error ? assessment.av_fusion : null
  const vowelFb = assessment && !assessment.error ? assessment.vowel_feedback : null   // 모음 포먼트 교정(축 E)
  const rateCue = assessment && !assessment.error ? rateCueView(assessment.sound_cue) : null   // 문장 말 빠르기(S7, 참고)
  const fusionAudio = fusion ? (fusion.audio_score ?? assessment.audio_score ?? assessment.dgop?.score_calibrated ?? null) : null

  // 레슨 시작 전 = 발화 트랙 로딩(223:50 / 모바일 243:101) — 첫 문항·복습 목록을 받는 동안 + 최소 표시 시간.
  const pending = !err && (reviewMode ? reviewItems === null : stageNo != null ? !stageInfo : !target)
  const recoveredRef = useRef(false)
  useEffect(() => {
    if (submission.sent && !recoveredRef.current) {
      recoveredRef.current = true; submission.finish()
      if ((!assessment || assessment.error) && submission.sent.question === itemIdx) nextItem()
    }
  }, [])
  if (target) saveCheckpoint({ words, target, frames, stageInfo, reviewItems, itemIdx, progress, summary, assessment })




return { exit, barPct, total, cur, exitError, err, setRetry, teardown, navigate, reviewEmpty, category, heading, saved, toggleSaved, target, summary, frames, metricMode, toggleMirror, mirrorOn, mirrorBusy, attachVideo, recording, canvasRef, volLabel, vol, pitch, progress, probeLine, scoreNum, assessing, scoreLabel, phones, chipView, setShowDetail, barTone, good, hold, fbTitle, fbSub, nextItem, resetAttempt, reviewMode, stageNo, start, starting, stop, showDetail, closeDetail, assessment, fusion, mouthRes, fusionAudio, vowelFb, rateCue, mode, drill, loadCoaching, attemptRef, pending, introDone }
}
