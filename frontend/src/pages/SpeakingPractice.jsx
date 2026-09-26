import { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { curriculumAPI, learningAPI, speakAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import BookmarkButton from '../components/BookmarkButton'
import useBookmark from '../lib/useBookmark'
import LoadingScreen from '../components/LoadingScreen'
import Modal from '../components/Modal'
import { getSpeakingStageMenuItem } from '../config/speakingNavigation'
import { toBlendshapeMap, scorePercent, loadCalibration } from '../lib/mouthScore'
import { scoreTone, scoreLevel } from '../lib/scoreTone'
import { VOWEL_IDS } from '../lib/vtlShapes'
import { mediaErrorMessage } from '../lib/mediaError'

// 혀 위치 성도 단면(E-6) — 모음 결과를 열 때만 받는다(그림 코드와 윤곽 자료 모두 지연 로드)
const VocalTractVTL = lazy(() => import('../components/VocalTractVTL'))

/**
 * 말하기 연습 (발화 피드백) — 발화 레슨(핸드오프 §4-04). /learn/speaking 과 /review/speaking/session 이 같이 쓴다.
 * Figma: 말하기 전 175:21 · 녹음 중 175:49 · 결과 176:21 · 자세히 보기 182:21 · 결과(아쉬움) 186:21,
 *        모바일 236:34 · 237:34(lg 미만). 루트에 data-track="speak"를 달아 트랙색(버튼·진행률·단어 카드)이 분홍이 된다.
 *  1) 말하는 동안 볼륨·톤(피치)·파형 실시간 (Web Audio) — 귀 대신 눈.
 *  2) 녹음을 서버로 → Whisper 전사 + 기존 음운 채점 + Claude 코칭.
 * 점수·음소 칩 색은 lib/scoreTone(§3.2: 70 이상 초록 · 45~69 주황 · 45 미만 빨강).
 * 발성·운율 단계(지표 모드)는 Figma 프레임이 없어 결과 상세에 목소리 곡선·지표를 그대로 둔다.
 */

// Figma 발화 화면 에셋 — public/ui (닫기는 독화 레슨과 같은 91:12 Close)
const IC = {
  close: '/ui/lp-91-12-close.svg',
  mic: '/ui/speak-mic.svg',
  recording: '/ui/speak-recording.svg',   // 96×96(펄스 링 포함) — 72 슬롯에 -16.67%씩 넘친다(175:79)
  doka: '/ui/lp-303-32-doka.svg',         // 코칭 "DOKA의 한마디"(303:32)
}
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // DOKA SVG 그림자 여백(Figma inset)
// 레슨 시작 전 트랙 로딩(§4-10 223:50)을 최소 이만큼은 보인다 — 데이터가 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000
// 결과 바 버튼(176:71 / 모바일 237:80) — 데스크톱 28/15·16px, lg 미만은 반반 폭 r13·15px
const RESULT_BTN = 'btn-bar flex-1 max-lg:rounded-13 max-lg:px-0 max-lg:text-[15px] lg:flex-none lg:px-7 lg:text-[16px]'

// 캔버스·SVG에 쓸 토큰 색 — 루트(data-track="speak") 기준으로 CSS 변수를 읽는다.
const cssVar = (el, name) => (el ? getComputedStyle(el).getPropertyValue(name).trim() : '') || 'gray'

// /api/viseme 실패 안내(아바타만 멈추고 녹음·채점은 된다). 다음 문항에서 받으면 이 안내만 지운다.
const VISEME_ERR = '입모양 자료를 불러오지 못해 아바타가 움직이지 않아요. 녹음과 채점은 그대로 할 수 있어요.'

// 지표 모드 점수 이름: 서버가 드릴마다 다른 것을 잰다(backend/speak_curriculum.py _score_prosody).
// 발성(voicing)은 길이 60% + 크기 40%라 '길이·크기'로 따로 붙인다.
const PROSODY_SCORE_LABEL = { long: '길이', rise: '억양', fall: '억양', soft: '작게 말하기', loud: '크게 말하기' }

// AudioContext.close()는 이미 닫히는 중이면 거부된 약속을 돌려준다 → 삼켜서 처리되지 않은 거부를 막는다
const closeContext = (ac) => {
  if (!ac || ac.state === 'closed') return
  try { Promise.resolve(ac.close()).catch(() => {}) } catch { /* noop */ }
}

// 자기상관 기반 기본주파수(피치) 추정
function autoCorrelate(buf, sampleRate) {
  const SIZE = buf.length
  let rms = 0
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i]
  rms = Math.sqrt(rms / SIZE)
  if (rms < 0.006) return -1
  let r1 = 0, r2 = SIZE - 1
  const thres = 0.2
  for (let i = 0; i < SIZE / 2; i++) if (Math.abs(buf[i]) < thres) { r1 = i; break }
  for (let i = 1; i < SIZE / 2; i++) if (Math.abs(buf[SIZE - i]) < thres) { r2 = SIZE - i; break }
  const b = buf.slice(r1, r2)
  const n = b.length
  if (n < 8) return -1
  const c = new Array(n).fill(0)
  for (let i = 0; i < n; i++) for (let j = 0; j < n - i; j++) c[i] += b[j] * b[j + i]
  let d = 0
  while (d < n - 1 && c[d] > c[d + 1]) d++
  let maxval = -1, maxpos = -1
  for (let i = d; i < n; i++) if (c[i] > maxval) { maxval = c[i]; maxpos = i }
  let T0 = maxpos
  if (T0 <= 0) return -1
  const x1 = c[T0 - 1] || 0, x2 = c[T0], x3 = c[T0 + 1] || 0
  const a = (x1 + x3 - 2 * x2) / 2, bb = (x3 - x1) / 2
  if (a) T0 = T0 - bb / (2 * a)
  return sampleRate / T0
}

export default function SpeakingPractice() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const stageNo = searchParams.get('stage') != null ? parseInt(searchParams.get('stage'), 10) : null
  const reviewMode = searchParams.get('review') != null || location.pathname === '/review/speaking/session'   // 발음 복습 모드
  const selectedStageMenuItem = getSpeakingStageMenuItem(stageNo)

  const [words, setWords] = useState([])
  const [target, setTarget] = useState(null)
  const [frames, setFrames] = useState([])
  const [stageInfo, setStageInfo] = useState(null)   // 단계 콘텐츠(있으면 단계 모드)
  const [reviewItems, setReviewItems] = useState(null)  // null=로딩, []=비어있음
  const [itemIdx, setItemIdx] = useState(0)
  const [progress, setProgress] = useState(null)     // 단계 진행률(마지막 채점 결과)
  const [recording, setRecording] = useState(false)
  const [vol, setVol] = useState(0)
  const [pitch, setPitch] = useState(null)
  const [err, setErr] = useState(null)
  const [retry, setRetry] = useState(0)   // 로드 실패 시 '다시 불러오기'로 effect 재실행
  const [summary, setSummary] = useState(null)
  const [assessing, setAssessing] = useState(false)
  const [assessment, setAssessment] = useState(null)
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
  const metricMode = mode === 'voicing' || mode === 'prosody'   // 지표 기반(전사 없음)
  const reviewEmpty = reviewMode && Array.isArray(reviewItems) && reviewItems.length === 0

  const acRef = useRef(null)
  const analyserRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
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
        const vs = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
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
        .catch(() => { if (!cancelled) setErr('복습을 불러오지 못했어요.') })
    } else if (stageNo != null) {
      speakAPI.getStage(stageNo)
        .then((d) => {
          if (cancelled) return
          setStageInfo(d)
          applyItem(d.items, 0)
        })
        .catch(() => { if (!cancelled) setErr('단계를 불러오지 못했어요.') })
    } else {
      curriculumAPI.getWords()
        .then((d) => {
          if (cancelled) return
          const ws = d.words.map((w) => w.word)
          setWords(ws)
          pickWord(ws)
        })
        .catch(() => { if (!cancelled) setErr('콘텐츠를 불러오지 못했어요.') })
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

  // 다음 항목(단계·복습) 또는 다음 단어(자유)
  const nextItem = () => {
    if ((reviewMode || stageNo != null) && items.length) applyItem(items, (itemIdx + 1) % items.length)
    else pickWord()
  }

  // 다시 말하기: 채점 중이던 이전 시도의 결과는 버린다(시도 번호를 올린다)
  const resetAttempt = () => { attemptRef.current += 1; setSummary(null); setAssessment(null); setAssessing(false); setShowDetail(false) }

  const closeAudio = () => {
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null }
    closeContext(acRef.current)
    acRef.current = null; analyserRef.current = null
  }

  const teardown = () => {
    mediaGenRef.current += 1   // 아직 열리는 중인 마이크·카메라·모델은 도착하는 대로 닫힌다
    attemptRef.current += 1    // 채점 중이던 결과도 버린다
    landmarkerLoadRef.current = null
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    const rec = recorderRef.current
    if (rec) { rec.onstop = null; try { if (rec.state !== 'inactive') rec.stop() } catch { /* noop */ } recorderRef.current = null }
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
      stream = await navigator.mediaDevices.getUserMedia({
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
      try {
        const rec = new MediaRecorder(stream)
        rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data) }
        rec.onstop = () => onRecStop(attempt)
        rec.start()
        recorderRef.current = rec
      } catch { recorderRef.current = null }
      startRef.current = performance.now()
      setRecording(true)
      loop()
    } catch (e) {
      // 마이크는 열렸는데 그 뒤(AudioContext·분석기)에서 실패해도 연 장치를 닫는다
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
    closeAudio()
    if (attempt !== attemptRef.current) return
    if (blob.size > 500 && target) {
      const s = summaryRef.current || {}
      const metrics = {
        loudness: s.loudness ?? 0, pitch_range: s.pitchRange ?? 0, duration: s.duration ?? 0,
        pitch_start: s.pitchStart ?? 0, pitch_end: s.pitchEnd ?? 0,
      }
      // 복습 세션이면 review=true → 백엔드가 채점/코칭만 하고 단계 숙달·해금은 건드리지 않음
      const opts = assessStage != null ? { stage: assessStage, drill, review: reviewMode } : {}
      // 축 B: 웹캠 미러로 버퍼된 입모양이 있으면 함께 보낸다. 서버는 입모양 점수를 소리 점수와 따로 돌려준다.
      const mc = computeMouthConfidence()
      if (mc != null) {
        opts.mouth_confidence = mc
        const track = await buildMouthTrack()
        if (track) opts.mouth_track = JSON.stringify(track)
      }
      if (attempt !== attemptRef.current) return
      setAssessing(true)
      try {
        const res = await speakAPI.assess(target, blob, metrics, opts)
        if (attempt !== attemptRef.current) return
        setAssessment(res)
        if (res.progress) setProgress(res.progress)
      } catch (e) {
        if (attempt !== attemptRef.current) return
        setAssessment({ error: e?.response?.data?.detail || '발음 분석에 실패했어요. 잠시 후 다시 시도해 주세요.' })
      } finally {
        if (attempt === attemptRef.current) setAssessing(false)
      }
    }
  }

  const stop = () => {
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

  const computeSummary = () => {
    const raw = volHist.current, ps = pitchHist.current
    const dur = startRef.current ? Math.round((performance.now() - startRef.current) / 100) / 10 : 0
    if (!raw.length) {
      return { micIssue: true, loudness: 0, volMsg: '마이크 소리가 안 잡혔어요. 권한/연결을 확인하고 가까이서 말해보세요.', volOk: false, toneMsg: '', toneOk: null, pitchRange: 0, duration: dur }
    }
    const peak = raw.reduce((m, v) => (v > m ? v : m), 0)
    const voiced = raw.filter((v) => v > 0.01)   // 발성 프레임만 (무음 제외 → '항상 작음' 버그 방지)
    const voicedAvg = voiced.length ? voiced.reduce((a, b) => a + b, 0) / voiced.length : 0
    const loudness = Math.max(0, Math.min(100, Math.round(((voicedAvg - 0.01) / 0.13) * 100)))

    let volMsg, volOk, micIssue = false
    if (peak < 0.008) { volMsg = '마이크 소리가 거의 안 잡혔어요. 권한/연결을 확인하고 가까이서 말해보세요.'; volOk = false; micIssue = true }
    else if (loudness < 40) { volMsg = `목소리가 작아요(크기 ${loudness}/100). 배에 힘을 주고 더 크게 말해보세요.`; volOk = false }
    else if (loudness > 92) { volMsg = `조금 컸어요(크기 ${loudness}/100). 편하게 낮춰도 괜찮아요.`; volOk = true }
    else { volMsg = `볼륨 적당해요(크기 ${loudness}/100). 좋아요!`; volOk = true }

    let pitchRange = 0, pitchMean = 0, pitchStart = 0, pitchEnd = 0, toneMsg, toneOk = null
    if (ps.length >= 4) {
      const sorted = [...ps].sort((a, b) => a - b)
      const lo = sorted[Math.floor(sorted.length * 0.1)]
      const hi = sorted[Math.floor(sorted.length * 0.9)]
      pitchRange = Math.round(hi - lo)
      pitchMean = Math.round(ps.reduce((a, b) => a + b, 0) / ps.length)
      // 억양 방향 판정용: 앞 30% vs 뒤 30% 평균
      const head = ps.slice(0, Math.max(1, Math.round(ps.length * 0.3)))
      const tail = ps.slice(Math.floor(ps.length * 0.7))
      pitchStart = Math.round(head.reduce((a, b) => a + b, 0) / head.length)
      pitchEnd = Math.round(tail.reduce((a, b) => a + b, 0) / tail.length)
      if (pitchRange < 25) { toneMsg = `톤이 평평했어요(억양 폭 ${pitchRange}Hz). 끝을 올리거나 내리며 억양을 넣어보세요.`; toneOk = false }
      else { toneMsg = `톤에 자연스러운 변화가 있었어요(억양 폭 ${pitchRange}Hz)!`; toneOk = true }
    } else {
      toneMsg = '소리를 조금 더 이어서 내보면 억양을 볼 수 있어요.'
    }
    return { micIssue, loudness, volMsg, volOk, pitchRange, pitchMean, pitchStart, pitchEnd, toneMsg, toneOk, duration: dur }
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
    : (drill || stageInfo?.title || selectedStageMenuItem?.label || '발음 연습')
  const heading = prompt || '이 단어를 소리 내어 말해보세요'

  // 결과 점수·판정
  const phones = (!metricMode && assessment && !assessment.error && assessment.acoustic_dgop?.phones) || []
  const scoreNum = assessment && !assessment.error ? assessment.score
    : (metricMode && summary ? summary.loudness : null)
  // 지표 모드는 서버가 잰 것에 맞춰 이름을 붙인다. 서버 점수 전(또는 실패)에는 위처럼 소리 크기를 보이므로 '목소리 크기'.
  const scoreLabel = !metricMode ? '발음 정확도'
    : !(assessment && !assessment.error) ? '목소리 크기'
      : mode === 'voicing' ? '길이·크기'
        : (PROSODY_SCORE_LABEL[drill] || '운율')
  const good = assessment && !assessment.error
    ? (assessment.passed ?? (assessment.score >= 65))
    : (summary ? (summary.volOk && summary.toneOk !== false) : null)
  const phoneScore = (p) => Math.round((p.dgop ?? 0) * 100)
  const goodCount = phones.filter((p) => scoreLevel(phoneScore(p), 'phone') === 'good').length
  const fbSub = good
    ? (phones.length ? `${phones.length}개 중 ${goodCount}개 소리를 정확히 냈어요` : (summary?.volMsg || '잘 전달됐어요'))
    : '소리가 잘 전달되지 않았어요'
  const fbTitle = good ? '잘했어요!' : '조금 더 연습해요'
  // 나가기 → 발화 커리큘럼 경로(?track=speak). /dashboard는 독화 경로로 리다이렉트된다.
  const exit = () => { teardown(); navigate(reviewMode ? '/review/speaking' : '/learn/path?track=speak') }

  const exitError = err && !stageInfo && !reviewMode && stageNo != null && !target

  // 입모양 점수 — 기본은 채점 점수(소리)와 따로 보인다(mouth). 서버가 연구용 융합(LIPLAB_AV_FUSION=1)을 켜면
  // 예전 '소리 + 입모양 융합'(182:77)을 보이고, 그때 소리 점수는 융합 전 음향 점수(audio_score)로 보충한다.
  const mouthRes = assessment && !assessment.error ? assessment.mouth : null
  const fusion = assessment && !assessment.error ? assessment.av_fusion : null
  const vowelFb = assessment && !assessment.error ? assessment.vowel_feedback : null   // 모음 포먼트 교정(축 E)
  const fusionAudio = fusion ? (fusion.audio_score ?? assessment.audio_score ?? assessment.dgop?.score_calibrated ?? null) : null

  // 레슨 시작 전 = 발화 트랙 로딩(223:50 / 모바일 243:101) — 첫 문항·복습 목록을 받는 동안 + 최소 표시 시간.
  const pending = !err && (reviewMode ? reviewItems === null : stageNo != null ? !stageInfo : !target)
  if (pending || !introDone) return <LoadingScreen variant="brand" track="language" />

  return (
    <div data-track="speak" className="flex min-h-[100dvh] flex-col bg-page">
      {/* 진행 헤더(175:22 / 모바일 236:35) — X + 트랙(분홍) 진행바 + n / 전체 */}
      <div className="mx-auto w-full max-w-[676px] px-[18px] pt-[18px] lg:pt-7">
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={exit} aria-label="나가기" className="shrink-0">
            <img src={IC.close} alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-[width] duration-500" style={{ width: `${barPct}%` }} />
          </div>
          {total && <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{cur} / {total}</span>}
        </div>
      </div>

      <main className="mx-auto w-full max-w-[676px] flex-1 px-[18px] pb-8 pt-6 lg:pt-5">
          {exitError ? (
            <div className="flex flex-col items-center gap-2 rounded-22 border-2 border-line bg-white px-6 py-16 text-center">
              <p className="text-lg font-bold text-ink">단계를 불러오지 못했어요</p>
              <p className="mb-3 text-sm text-ink-faint">{err} 네트워크를 확인하고 다시 시도해 주세요.</p>
              <div className="flex justify-center gap-2">
                <button type="button" onClick={() => setRetry((n) => n + 1)} className="btn-primary px-6 py-2.5 text-sm">다시 불러오기</button>
                <button type="button" onClick={() => { teardown(); navigate('/learn/path?track=speak') }} className="btn-secondary px-6 py-2.5 text-sm">발화 커리큘럼으로</button>
              </div>
            </div>
          ) : reviewEmpty ? (
            <div className="flex flex-col items-center gap-2 rounded-22 border-2 border-line bg-white px-6 py-16 text-center">
              <p className="text-lg font-bold text-ink">복습할 발음이 없어요</p>
              <p className="mb-3 text-sm text-ink-faint">최근 발음이 다 좋았어요. 단계 연습을 이어가 볼까요?</p>
              <button type="button" onClick={() => { teardown(); navigate('/review/speaking') }} className="btn-primary px-6 py-2.5 text-sm">목록으로</button>
            </div>
          ) : (
          <div className="flex flex-col gap-4 lg:gap-5">
            {/* 질문 + 북마크(175:28 · 328:49 / 모바일 236:71 · 328:70) — 북마크는 트랙과 무관한 브랜드색 */}
            <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
              <p className="text-[12px] font-bold text-track lg:text-[13px]">{category}</p>
              <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[28px] lg:tracking-[-0.7px]">{heading}</h1>
              <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-5" />
            </div>

            {/* 말할 단어(175:31 / 모바일 236:74) — 가운데 정렬 분홍 카드. 들어보기 버튼 없음(§3.4 청각장애 대상) */}
            <div className="flex items-center justify-center rounded-16 bg-track-tint py-[18px] pl-[22px] pr-4 lg:rounded-18 lg:py-5 lg:pl-7 lg:pr-5">
              <p className="text-center text-[32px] font-bold leading-figma tracking-[-0.64px] text-track-dark lg:text-[38px] lg:tracking-[-0.76px]">{target || '…'}</p>
            </div>

            {err && !exitError && (
              <div className="rounded-14 border border-bad-line bg-bad-tint p-3 text-sm text-bad-text">{err}</div>
            )}

            {!summary ? (
              <>
                {/* 입모양(175:36 560×300 / 모바일 236:79 전체 폭×200) — 3D 아바타 + 안내 */}
                <div className="mx-auto w-full max-w-[560px] overflow-hidden rounded-18 border-2 border-line bg-white lg:rounded-22">
                  <div className="px-4 pt-4 lg:pt-6">
                    <MouthAvatar frames={frames} height={null} className="h-[134px] lg:h-[209px]" />
                  </div>
                  <p className="pb-5 pt-2.5 text-center text-[13px] font-bold leading-figma text-ink-faint lg:pb-[34px] lg:pt-3 lg:text-[14px]">
                    {metricMode ? '아래 그래프로 목소리 크기·억양을 확인해요' : '입모양을 따라 해보세요'}
                  </p>
                </div>

                {/* 웹캠 미러 — 내 입모양을 거울처럼 띄워 목표 아바타와 비교(따라 말하기). Figma 175:21에는 없지만
                    분석의 입모양 점수(소리와 따로 보임)의 입력이 여기서만 나와 남긴다. */}
                <div className="mx-auto w-full max-w-[560px]">
                  <button type="button" onClick={toggleMirror} aria-pressed={mirrorOn} disabled={mirrorBusy}
                    className={`btn-secondary w-full py-2.5 text-[14px] ${mirrorOn ? 'bg-track-tint text-track-dark' : ''}`}>
                    {mirrorOn ? '웹캠 끄기' : '웹캠 미러 — 내 입모양 보기'}
                  </button>
                  {mirrorOn && (
                    <div className="mt-2 overflow-hidden rounded-14 bg-slate-900">
                      <video ref={attachVideo} autoPlay muted playsInline
                        className="w-full" style={{ transform: 'scaleX(-1)', maxHeight: 220, objectFit: 'cover' }} />
                      <p className="py-1 text-center text-[11px] text-white/70">거울처럼 좌우 반전 · 위 아바타 입모양과 내 입을 나란히 비교해보세요</p>
                    </div>
                  )}
                </div>

                {/* 실시간 파형·볼륨·피치(녹음 중) — 귀 대신 눈. 사용법 가이드 '발화 레슨'의 실시간 피드백 */}
                {recording && (
                  <div className="mx-auto w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:rounded-22">
                    <canvas ref={canvasRef} width={480} height={120}
                      className="w-full rounded-14 border border-fill bg-surface-muted" style={{ height: 120 }} />
                    <div className="mt-4">
                      <div className="mb-1 flex justify-between text-xs text-ink-muted"><span>볼륨</span><span>{volLabel}</span></div>
                      <div className="h-3 overflow-hidden rounded-full bg-fill">
                        <div className={`h-full rounded-full transition-[width] duration-75 ${vol < 0.15 ? 'bg-fill-strong' : vol > 0.95 ? 'bg-warn' : 'bg-track'}`}
                          style={{ width: `${Math.round(vol * 100)}%` }} />
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-sm">
                      <span className="text-ink-muted">톤 (피치)</span>
                      <span className="font-bold text-track-dark">{pitch ? `${pitch} Hz` : '…'}</span>
                    </div>
                  </div>
                )}

                {/* 이 단계 숙달 진행 — 레슨 안에서 해금을 알려 주는 유일한 자리라 남긴다(사용자 결정 대기) */}
                {progress && (
                  <div className="mx-auto w-full max-w-[560px]">
                    <div className="mb-1 flex justify-between text-xs text-ink-muted">
                      <span>이 단계 숙달</span><span>{progress.mastery_score}% · {progress.attempts}회</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-fill">
                      <div className="h-full bg-track transition-[width]" style={{ width: `${Math.min(progress.mastery_score, 100)}%` }} />
                    </div>
                    {progress.mastered && <p className="mt-1 text-xs font-bold text-good-text">이 단계를 숙달했어요! 다음 단계가 열렸어요.</p>}
                  </div>
                )}
              </>
            ) : (
              /* 발음 결과(176:36 560×320 / 모바일 237:50) — 점수 + 음소 칩(§3.2) + 자세히 보기 */
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className="mx-auto flex w-full max-w-[560px] flex-col items-center gap-3.5 rounded-18 border-2 border-line bg-white px-4 py-[18px] lg:gap-0 lg:rounded-22 lg:px-6 lg:py-[30px]">
                <div className="flex flex-col items-center gap-0.5 font-bold leading-figma lg:gap-1">
                  <p className={`text-[44px] tracking-[-1.32px] lg:text-[52px] lg:tracking-[-1.56px] ${scoreTone(scoreNum, 'phone').text}`}>
                    {assessing && scoreNum == null ? '…' : scoreNum != null ? `${scoreNum}%` : '-'}
                  </p>
                  <p className="text-[13px] text-ink-faint lg:text-[14px]">{scoreLabel}</p>
                </div>

                {phones.length > 0 && (
                  <div className="flex flex-wrap justify-center gap-2 lg:mt-[33px] lg:gap-2.5">
                    {phones.map((p, i) => {
                      const v = phoneScore(p)
                      return (
                        <div key={i} title={`정확도 ${v} · 신뢰도 ${Math.round((p.confidence ?? 0) * 100)}`}
                          className={`flex size-12 items-center justify-center rounded-13 border-2 lg:size-[52px] lg:rounded-14 ${scoreTone(v, 'phone').chip}`}>
                          <span className="text-[20px] font-bold leading-figma lg:text-[22px]">{p.label || '·'}</span>
                        </div>
                      )
                    })}
                  </div>
                )}

                {assessing && !metricMode && (
                  <div className="flex items-center gap-2 text-sm text-track-dark lg:mt-6">
                    <span className="spinner size-4 rounded-full border-2 border-speak/40 border-t-speak-dark" />
                    발음을 분석하는 중…
                  </div>
                )}

                {/* 자세히 보기(179:21 / 모바일 237:74) — 쉐브론 없음 */}
                <button type="button" onClick={() => setShowDetail(true)}
                  className="btn-secondary rounded-[12px] border-b-4 px-[26px] py-3 text-[14px] lg:mt-[30px] lg:rounded-14 lg:border-b-5 lg:px-[30px] lg:py-[15px] lg:text-[16px]">
                  자세히 보기
                </button>
              </motion.div>
            )}
          </div>
          )}
      </main>

      {/* 하단 바 — 말하기 전/녹음 중: 마이크 바(175:40 / 236:83) · 결과: 피드백 바(176:66 · 186:55 / 237:76) */}
      {!exitError && !reviewEmpty && (
        summary ? (
          <div className={`sticky bottom-0 w-full border-t-2 ${good ? 'border-good/35 bg-good-tint' : 'border-bad/35 bg-bad-tint'}`}>
            <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
              <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] font-bold leading-figma lg:gap-1 ${good ? 'text-good-text' : 'text-bad-text'}`}>
                <p className="text-[19px] tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{assessing && !metricMode ? '분석 중…' : fbTitle}</p>
                <p className="text-[13px] opacity-80 lg:truncate lg:text-[14px]">{assessing && !metricMode ? '발음을 분석하고 있어요' : fbSub}</p>
              </div>
              {/* 버튼: 통과 = 다시 말하기 / 계속하기, 아쉬움 = 넘어가기 / 다시 말하기(§4-04). lg 미만은 반반 폭. */}
              <div className="flex w-full gap-2.5 lg:w-auto lg:shrink-0">
                {good ? (
                  <>
                    <button type="button" onClick={resetAttempt} className={`btn-secondary border-good-line text-good-text ${RESULT_BTN}`}>다시 말하기</button>
                    <button type="button" onClick={nextItem} className={`btn-good ${RESULT_BTN}`}>{reviewMode || stageNo != null ? '계속하기' : '다음 단어'}</button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={nextItem} className={`btn-secondary border-bad-line text-bad-text ${RESULT_BTN}`}>넘어가기</button>
                    <button type="button" onClick={resetAttempt} className={`btn-bad ${RESULT_BTN}`}>다시 말하기</button>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="sticky bottom-0 w-full border-t-2 border-line bg-white">
            <div className="mx-auto flex max-w-[676px] flex-col items-center gap-2.5 px-[18px] pb-[calc(26px+env(safe-area-inset-bottom))] pt-[18px] lg:h-[148px] lg:justify-center lg:gap-3 lg:py-0">
              {!recording ? (
                <button type="button" onClick={start} aria-label="눌러서 말하기" disabled={starting}
                  className="flex size-[72px] items-center justify-center rounded-full border-2 border-b-6 border-track-dark bg-track transition-transform hover:scale-105 active:scale-95">
                  <img src={IC.mic} alt="" className="size-8" />
                </button>
              ) : (
                <button type="button" onClick={stop} aria-label="멈추고 결과 보기" className="relative size-[72px] transition-transform hover:scale-105 active:scale-95">
                  <img src={IC.recording} alt="" className="absolute max-w-none animate-pulse"
                    style={{ top: '-16.67%', left: '-16.67%', width: '133.33%', height: '133.33%' }} />
                </button>
              )}
              <p className={`text-[14px] font-bold leading-figma lg:text-[15px] ${recording ? 'text-track-dark' : 'text-ink-faint'}`}>
                {recording ? '듣고 있어요' : '눌러서 말하기'}
              </p>
            </div>
          </div>
        )
      )}

      {/* 자세히 보기(182:21 · 182:68) — 공통 모달(§3.5: 딤 + 흰 카드 + 원형 X, 바깥 클릭·Esc로 닫힘).
          이렇게 들렸어요 · 음소별 정확도 · 소리+입모양 융합 점수 · DOKA의 한마디 */}
      {summary && (
        <Modal open={showDetail} onClose={closeDetail} title="발음 분석" maxW="max-w-[600px]" gap="gap-3.5">
          {((assessment && !assessment.error && assessment.transcript != null) || phones.length > 0 || fusion?.visual_score != null || mouthRes?.score != null) && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {/* 이렇게 들렸어요(182:73) */}
              {assessment && !assessment.error && assessment.transcript != null && (
                <div className="flex min-h-[140px] flex-col items-center justify-center gap-2 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5 sm:min-h-[207px]">
                  <p className="text-[13px] font-bold leading-figma text-ink-muted">이렇게 들렸어요</p>
                  <p className="text-center text-[34px] font-bold leading-figma tracking-[-0.68px] text-ink">"{assessment.transcript || '(잘 안 들렸어요)'}"</p>
                </div>
              )}

              <div className="flex flex-col gap-3">
                {/* 음소별 발음 정확도(182:88) */}
                {phones.length > 0 && (
                  <div className="flex flex-col items-center gap-2.5 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
                    <p className="text-[13px] font-bold leading-figma text-ink-muted">음소별 발음 정확도</p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {phones.map((p, i) => {
                        const v = phoneScore(p)
                        return (
                          <div key={i} className={`flex flex-col items-center gap-0.5 rounded-[11px] border-1.5 px-[15px] py-[9px] font-bold leading-figma ${scoreTone(v, 'phone').chip}`}>
                            <span className="text-[18px]">{p.label || '·'}</span>
                            <span className="text-[11px] opacity-80">{v}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* 입모양 점수 — 웹캠 미러로 입모양을 잰 시도에만 값이 있다. 발음 점수에는 섞지 않는다 */}
                {mouthRes && mouthRes.score != null && (
                  <div className="flex flex-col items-center gap-1.5 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
                    <p className="text-[13px] font-bold leading-figma text-ink-muted">입모양 점수</p>
                    <span className="text-[19px] font-bold leading-figma text-track-dark">{Math.round(mouthRes.score)}</span>
                    <p className="text-center text-[11px] leading-relaxed text-ink-faint">웹캠으로 본 입모양이에요. 발음 점수에는 섞지 않고 따로 보여 줘요.</p>
                  </div>
                )}

                {/* 소리 + 입모양 융합 점수(182:77) — 서버가 연구용 융합을 켰을 때만 */}
                {fusion && fusion.visual_score != null && (
                  <div className="flex flex-col items-center gap-2.5 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
                    <p className="text-[13px] font-bold leading-figma text-ink-muted">소리 + 입모양 융합 점수</p>
                    <div className="flex items-center gap-[9px] leading-figma">
                      {fusionAudio != null && (
                        <>
                          <span className="text-[15px] text-ink-soft">소리 {Math.round(fusionAudio)}</span>
                          <span className="text-[13px] text-inactive-line">+</span>
                        </>
                      )}
                      <span className="text-[15px] text-ink-soft">입모양 {Math.round(fusion.visual_score)}</span>
                      <span className="text-[13px] text-inactive-line">→</span>
                      <span className="text-[19px] font-bold text-track-dark">{Math.round(fusion.score)}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 혀 위치(축 E-2·E-6) — 모음 단계에서 녹음의 F1·F2로 추정한 혀 모양을 목표 모음(점선) 위에 겹친다.
              포먼트는 화자 크기(speaker_scale)로 나눠 기준 화자 눈금으로 옮긴 뒤 VocalTractLab 격자에서 찾는다. */}
          {vowelFb && VOWEL_IDS[vowelFb.vowel] && (
            <div className="flex flex-col gap-3 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5 sm:flex-row sm:items-center">
              <div className="w-full shrink-0 sm:w-[220px]">
                <Suspense fallback={<div className="aspect-[4/3] w-full animate-pulse rounded-lg bg-white" />}>
                  <VocalTractVTL phoneme={VOWEL_IDS[vowelFb.vowel]} legend targetLabel={vowelFb.vowel}
                    estimate={{ f1: vowelFb.f1 / (vowelFb.speaker_scale || 1), f2: vowelFb.f2 / (vowelFb.speaker_scale || 1) }} />
                </Suspense>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <p className="text-[13px] font-bold leading-figma text-ink-muted">혀 위치 · 목표 {vowelFb.vowel}</p>
                {(vowelFb.messages || []).map((m, i) => (
                  <p key={i} className="text-[14px] leading-[1.6] text-ink">{m}</p>
                ))}
                <p className="text-[11px] leading-relaxed text-ink-faint">
                  목소리 공명(F1 {vowelFb.f1}Hz · F2 {vowelFb.f2}Hz)으로 추정한 한 가지 예시예요. 같은 소리를 내는 혀 모양은 여럿일 수 있어요.
                </p>
              </div>
            </div>
          )}

          {/* 발성·운율(지표 모드)은 Figma 프레임이 없다 — 이 단계의 유일한 결과라 지표와 목소리 곡선을 둔다 */}
          {metricMode && (
            <>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="목소리 크기" value={`${summary.loudness}/100`} />
                <Stat label="억양 폭" value={`${summary.pitchRange}Hz`} />
                <Stat label="길이" value={`${summary.duration}s`} />
              </div>
              {summary.trace && summary.trace.length >= 3 && !summary.micIssue && (
                <div className="rounded-14 border-1.5 border-fill bg-white p-3">
                  <p className="mb-1 text-xs text-ink-muted">내 목소리 곡선</p>
                  <PitchEnergyGraph trace={summary.trace} summary={summary} />
                </div>
              )}
            </>
          )}

          {/* DOKA의 한마디(182:106 — DOKA 303:32 · 제목 303:39 · 구분선 303:40) */}
          {assessment?.coaching && (
            <div className="flex items-center gap-2.5 rounded-14 bg-track-tint px-4 py-3.5">
              <span className="relative size-[34px] shrink-0">
                <img src={IC.doka} alt="" className="absolute max-w-none" style={OVERFLOW} />
              </span>
              <p className="shrink-0 whitespace-nowrap text-[14px] font-bold leading-figma text-track-dark">DOKA의 한마디</p>
              <span aria-hidden className="h-4 w-[1.5px] shrink-0 rounded-[1px] bg-speak-dark/30" />
              <p className="min-w-0 flex-1 text-[14px] leading-[1.6] text-track-dark">{assessment.coaching}</p>
            </div>
          )}

          {assessment?.error && (
            <div className="rounded-14 bg-surface-muted p-3 text-sm text-ink-muted">{assessment.error}</div>
          )}
        </Modal>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-surface-muted p-2 text-center">
      <p className="text-[10px] text-ink-faint">{label}</p>
      <p className="text-sm font-bold text-ink">{value}</p>
    </div>
  )
}

/**
 * 피치·강세 그래프 — 청각장애 학습자가 자기 발음을 '들을' 수 없으니 곡선으로 '본다'.
 *  위 레인: 억양(높낮이). 평균 피치를 중심으로 ±90Hz 매핑 → 기준 목소리 높이와 무관하게
 *           '변화량'만 곡선으로 드러난다(평평하게 말하면 가운데 점선에 붙은 평평한 선).
 *  아래 레인: 목소리 크기(에너지 포락선) + '적정' 기준 점선. 자주 아래로 내려가면 너무 작았다는 뜻.
 *  발화 트랙 토큰(--speak)으로 배색.
 */
function PitchEnergyGraph({ trace, summary }) {
  if (!trace || trace.length < 3) return null
  const W = 480, H = 250
  const padL = 40, padR = 12, padT = 16, padB = 22
  const innerW = W - padL - padR
  const last = trace[trace.length - 1]
  const tMax = Math.max(summary?.duration || 0, last.t || 0.1, 0.1)
  const X = (t) => padL + (t / tMax) * innerW

  // 위: 억양 레인 / 아래: 크기 레인
  const pTop = padT, pBot = padT + 92
  const eTop = pBot + 26, eBot = H - padB

  // 억양: 평균 중심 ±90Hz
  const voiced = trace.filter((s) => s.hz)
  const center = summary?.pitchMean ||
    (voiced.length ? Math.round(voiced.reduce((a, b) => a + b.hz, 0) / voiced.length) : 180)
  const span = 90
  const PY = (hz) => {
    const c = Math.max(center - span, Math.min(center + span, hz))
    return pBot - ((c - (center - span)) / (2 * span)) * (pBot - pTop)
  }
  const segs = []
  let cur = []
  for (const s of trace) {
    if (s.hz) cur.push([X(s.t), PY(s.hz)])
    else { if (cur.length > 1) segs.push(cur); cur = [] }
  }
  if (cur.length > 1) segs.push(cur)

  // 점들을 부드럽게 통과하는 곡선(Catmull-Rom → 3차 베지어)
  const smooth = (pts, t = 0.18) => {
    if (pts.length < 2) return ''
    if (pts.length === 2) return `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)} L${pts[1][0].toFixed(1)} ${pts[1][1].toFixed(1)}`
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2
      const c1x = p1[0] + (p2[0] - p0[0]) * t, c1y = p1[1] + (p2[1] - p0[1]) * t
      const c2x = p2[0] - (p3[0] - p1[0]) * t, c2y = p2[1] - (p3[1] - p1[1]) * t
      d += ` C${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`
    }
    return d
  }

  // 크기: 에너지 포락선(면적) — 이동평균으로 지터 완화 후 부드러운 상단선
  const eMax = 0.14
  const EY = (rms) => eBot - Math.min(1, Math.max(0, rms) / eMax) * (eBot - eTop)
  const yTh = EY(0.062)   // ≈ 크기 40/100 (적정 기준선)
  const rmsArr = trace.map((s) => s.rms)
  const topPts = trace.map((s, i) => {
    const a = rmsArr[i - 1] ?? rmsArr[i], b = rmsArr[i], c = rmsArr[i + 1] ?? rmsArr[i]
    return [X(s.t), EY((a + b + c) / 3)]
  })
  const topLine = smooth(topPts)
  const areaFill = topLine + ` L${X(last.t).toFixed(1)} ${eBot} L${X(trace[0].t).toFixed(1)} ${eBot} Z`

  const flat = summary?.toneOk === false
  const quiet = summary?.volOk === false && !summary?.micIssue
  const midY = (pTop + pBot) / 2

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 260 }}
           role="img" aria-label="발음 피치·강세 그래프">
        {/* 레인 배경 */}
        <rect x={padL} y={pTop} width={innerW} height={pBot - pTop} rx="8" style={{ fill: 'var(--speak-tint)' }} />
        <rect x={padL} y={eTop} width={innerW} height={eBot - eTop} rx="8" style={{ fill: 'var(--fill)' }} />

        {/* 억양 기준선(평균=평평의 기준) */}
        <line x1={padL} y1={midY} x2={W - padR} y2={midY} strokeOpacity="0.45" strokeWidth="1" strokeDasharray="4 4" style={{ stroke: 'var(--speak)' }} />
        {/* 억양 곡선 */}
        {segs.map((pts, i) => (
          <path key={i} d={smooth(pts)} fill="none" strokeWidth="2.5"
                strokeLinejoin="round" strokeLinecap="round" style={{ stroke: 'var(--speak)' }} />
        ))}

        {/* 크기 포락선(면적 + 부드러운 상단선) + 적정 기준선 */}
        <path d={areaFill} fillOpacity="0.16" stroke="none" style={{ fill: 'var(--speak)' }} />
        <path d={topLine} fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ stroke: 'var(--speak)' }} />
        <line x1={padL} y1={yTh} x2={W - padR} y2={yTh} strokeWidth="1" strokeDasharray="5 4" style={{ stroke: 'var(--warn)' }} />
        <text x={W - padR} y={yTh - 3} textAnchor="end" fontSize="9" style={{ fill: 'var(--warn-strong)' }}>적정</text>

        {/* 레인 라벨 */}
        <text x="4" y={midY - 3} fontSize="10" fontWeight="600" style={{ fill: 'var(--speak)' }}>억양</text>
        <text x="4" y={midY + 9} fontSize="8" style={{ fill: 'var(--ink-faint)' }}>높낮이</text>
        <text x="4" y={(eTop + eBot) / 2 + 3} fontSize="10" fontWeight="600" style={{ fill: 'var(--ink-muted)' }}>크기</text>

        {/* 시간축 */}
        <text x={padL} y={H - 5} fontSize="9" style={{ fill: 'var(--ink-faint)' }}>0s</text>
        <text x={W - padR} y={H - 5} textAnchor="end" fontSize="9" style={{ fill: 'var(--ink-faint)' }}>{tMax.toFixed(1)}s</text>
      </svg>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-muted">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-[2px] w-3 bg-speak" /> 억양선</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-3 border border-speak bg-speak-tint" /> 목소리 크기</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 border-t border-dashed border-warn" /> 적정 크기</span>
      </div>
      <div className="mt-1 space-y-0.5">
        {flat && <p className="text-[11px] text-warn-text">억양선이 가운데 점선을 거의 안 벗어났어요 → 문장 끝에서 선을 올리거나 내려보세요.</p>}
        {quiet && <p className="text-[11px] text-warn-text">크기 곡선이 적정선 아래로 자주 내려갔어요 → 배에 힘을 주고 더 크게.</p>}
        {!flat && !quiet && <p className="text-[11px] text-good-text">억양선과 크기 곡선이 잘 살아있어요.</p>}
      </div>
    </div>
  )
}
