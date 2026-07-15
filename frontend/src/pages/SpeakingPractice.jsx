import { useState, useEffect, useRef } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI, speakAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'
import { getSpeakingStageMenuItem } from '../config/speakingNavigation'

/**
 * 말하기 연습 (발화 피드백)
 *  1) 말하는 동안 볼륨·톤(피치)·파형 실시간 (Web Audio) — 귀 대신 눈.
 *  2) 녹음을 서버로 → Whisper 전사 + 기존 음운 채점 + Claude 코칭.
 * 정량 지표(목소리 크기 0~100, 억양 폭 Hz, 길이 s)를 함께 보여주고 코칭에도 반영한다.
 */

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
  const [summary, setSummary] = useState(null)
  const [assessing, setAssessing] = useState(false)
  const [assessment, setAssessment] = useState(null)
  const [mirrorOn, setMirrorOn] = useState(false)   // 웹캠 미러(따라 말하기)

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

  const toggleMirror = async () => {
    if (mirrorOn) {
      if (videoStreamRef.current) { videoStreamRef.current.getTracks().forEach((t) => t.stop()); videoStreamRef.current = null }
      if (videoRef.current) videoRef.current.srcObject = null
      setMirrorOn(false)
    } else {
      try {
        const vs = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
        videoStreamRef.current = vs
        setMirrorOn(true)
      } catch { setErr('웹캠을 쓸 수 없어요. 카메라 권한을 허용해 주세요.') }
    }
  }
  // <video>가 마운트된 뒤 스트림 연결(조건부 렌더 타이밍 대응)
  useEffect(() => {
    if (mirrorOn && videoRef.current && videoStreamRef.current) videoRef.current.srcObject = videoStreamRef.current
  }, [mirrorOn])

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
    setProgress(null)

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
  }, [stageNo, reviewMode])

  const loadFrames = async (t) => {
    const requestId = ++framesRequestRef.current
    setTarget(t); setFrames([]); setSummary(null); setAssessment(null)
    try {
      const nextFrames = await learningAPI.getVisemes(t)
      if (requestId === framesRequestRef.current) setFrames(nextFrames)
    } catch { /* ignore */ }
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

  const closeAudio = () => {
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null }
    if (acRef.current && acRef.current.state !== 'closed') { try { acRef.current.close() } catch { /* noop */ } }
    acRef.current = null; analyserRef.current = null
  }

  const teardown = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    const rec = recorderRef.current
    if (rec) { rec.onstop = null; try { if (rec.state !== 'inactive') rec.stop() } catch { /* noop */ } recorderRef.current = null }
    if (videoStreamRef.current) { videoStreamRef.current.getTracks().forEach((t) => t.stop()); videoStreamRef.current = null }
    closeAudio()
  }

  const start = async () => {
    setErr(null); setSummary(null); setAssessment(null)
    volHist.current = []; pitchHist.current = []; traceRef.current = []; chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      streamRef.current = stream
      const AC = window.AudioContext || window.webkitAudioContext
      const ac = new AC(); acRef.current = ac
      // 중요: 사용자 제스처 없이 만든 AudioContext는 suspended 상태로 시작할 수 있어
      // 분석 버퍼가 0으로만 읽힌다("소리 안 잡힘"의 주범) → 반드시 resume.
      if (ac.state === 'suspended') { try { await ac.resume() } catch { /* noop */ } }
      const src = ac.createMediaStreamSource(stream)
      const analyser = ac.createAnalyser(); analyser.fftSize = 2048
      src.connect(analyser); analyserRef.current = analyser
      try {
        const rec = new MediaRecorder(stream)
        rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data) }
        rec.onstop = onRecStop
        rec.start()
        recorderRef.current = rec
      } catch { recorderRef.current = null }
      startRef.current = performance.now()
      setRecording(true)
      loop()
    } catch {
      setErr('마이크를 쓸 수 없어요. 브라우저에서 마이크 권한을 허용해 주세요.')
    }
  }

  const onRecStop = async () => {
    const rec = recorderRef.current
    const blob = new Blob(chunksRef.current, { type: (rec && rec.mimeType) || 'audio/webm' })
    closeAudio()
    if (blob.size > 500 && target) {
      const s = summaryRef.current || {}
      const metrics = {
        loudness: s.loudness ?? 0, pitch_range: s.pitchRange ?? 0, duration: s.duration ?? 0,
        pitch_start: s.pitchStart ?? 0, pitch_end: s.pitchEnd ?? 0,
      }
      const opts = assessStage != null ? { stage: assessStage, drill } : {}
      setAssessing(true)
      try {
        const res = await speakAPI.assess(target, blob, metrics, opts)
        setAssessment(res)
        if (res.progress) setProgress(res.progress)
      } catch (e) {
        setAssessment({ error: e?.response?.data?.detail || '발음 분석에 실패했어요. 잠시 후 다시 시도해 주세요.' })
      } finally {
        setAssessing(false)
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
    ctx.lineWidth = 2
    ctx.strokeStyle = v > 0.15 ? '#4f46e5' : '#cbd5e1'
    ctx.beginPath()
    const step = Math.max(1, Math.ceil(buf.length / W))
    for (let x = 0; x < W; x++) {
      const s = buf[x * step] || 0
      const y = H / 2 + s * (H / 2) * 0.9
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.stroke()
  }

  const volLabel = !recording ? '-' : vol < 0.15 ? '작게' : vol > 0.95 ? '크게' : '좋아요'

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="speaking"
        title={reviewMode ? '말하기 복습' : selectedStageMenuItem?.label || stageInfo?.title || '말하기 학습'}
        description={reviewMode ? '틀렸던 발음을 다시 또박또박 연습해요' : (stageInfo?.guide || '귀 대신 눈으로 — 내 목소리를 보면서 발음을 다듬어요')}
        onExit={() => { teardown(); navigate(reviewMode ? '/review/speaking' : '/dashboard') }}
      />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {reviewEmpty ? (
          <div className="card text-center py-16">
            <div className="text-4xl mb-3">🎉</div>
            <p className="text-lg font-bold text-gray-900 mb-1">복습할 발음이 없어요</p>
            <p className="text-sm text-gray-500 mb-5">최근 발음이 다 좋았어요. 단계 연습을 이어가 볼까요?</p>
            <button onClick={() => { teardown(); navigate('/review/speaking') }} className="btn-primary px-6 py-2.5 text-sm">목록으로</button>
          </div>
        ) : (
        <>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card">
            <p className="text-sm text-gray-500 mb-1">{prompt ? '이렇게 해보세요' : '이렇게 말해보세요'}</p>
            {prompt && <p className="text-base font-semibold text-rose-600 text-center mb-1">{prompt}</p>}
            <div className="flex items-center justify-center gap-2 py-2">
              <p className="text-3xl font-bold text-gray-900">{target || '…'}</p>
            </div>
            <MouthAvatar frames={frames} height={230} />
            <p className="text-xs text-gray-400 mt-2 text-center">
              {metricMode ? '아래 그래프로 목소리 크기·억양을 확인해요' : '위 입모양을 참고해 또박또박 말해보세요'}
            </p>

            {/* 웹캠 미러 — 내 입모양을 거울처럼 띄워 목표 아바타와 비교(따라 말하기) */}
            <div className="mt-3">
              <button onClick={toggleMirror}
                className={`w-full py-2 rounded-lg text-sm font-medium transition-colors ${mirrorOn ? 'bg-rose-100 text-rose-700 hover:bg-rose-200' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                {mirrorOn ? '📷 웹캠 끄기' : '📷 웹캠 미러 — 내 입모양 보기'}
              </button>
              {mirrorOn && (
                <div className="mt-2 rounded-xl overflow-hidden bg-slate-900">
                  <video ref={videoRef} autoPlay muted playsInline
                    className="w-full" style={{ transform: 'scaleX(-1)', maxHeight: 220, objectFit: 'cover' }} />
                  <p className="text-[11px] text-center text-white/70 py-1">거울처럼 좌우 반전 · 위 아바타 입모양과 내 입을 나란히 비교해보세요</p>
                </div>
              )}
            </div>
            {progress && (
              <div className="mt-3">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>이 단계 숙달</span><span>{progress.mastery_score}% · {progress.attempts}회</span>
                </div>
                <div className="bg-gray-200 rounded-full h-1.5 overflow-hidden">
                  <div className="bg-rose-500 h-full transition-[width]" style={{ width: `${Math.min(progress.mastery_score, 100)}%` }} />
                </div>
                {progress.mastered && <p className="mt-1 text-xs font-semibold text-green-600">🎉 이 단계를 숙달했어요! 다음 단계가 열렸어요.</p>}
              </div>
            )}
          </div>

          <div className="card flex flex-col">
            {err && <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{err}</div>}

            <canvas ref={canvasRef} width={480} height={120}
              className="w-full rounded-xl bg-slate-50 border border-gray-100" style={{ height: 120 }} />

            <div className="mt-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1"><span>볼륨</span><span>{volLabel}</span></div>
              <div className="bg-gray-200 rounded-full h-3 overflow-hidden">
                <div className={`h-full rounded-full transition-[width] duration-75 ${vol < 0.15 ? 'bg-gray-300' : vol > 0.95 ? 'bg-amber-400' : 'bg-primary-500'}`}
                  style={{ width: `${Math.round(vol * 100)}%` }} />
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-gray-500">톤 (피치)</span>
              <span className="font-semibold text-primary-600">{pitch ? `${pitch} Hz` : (recording ? '…' : '-')}</span>
            </div>

            <div className="mt-auto pt-5">
              {!recording ? (
                <button onClick={start} className="btn-primary w-full py-3 text-base">🎤 눌러서 말하기</button>
              ) : (
                <button onClick={stop} className="w-full py-3 text-base rounded-xl bg-red-500 text-white font-semibold hover:bg-red-600 transition-colors">⏹ 멈추고 결과 보기</button>
              )}
            </div>
          </div>
        </div>

        <AnimatePresence>
          {summary && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card mt-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-gray-900">이번 발화 피드백</h3>
                {assessment && !assessment.error && assessment.passed != null && (
                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${assessment.passed ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                    {assessment.passed ? '성공 ✓' : '조금 더 연습'}
                  </span>
                )}
              </div>

              {/* 정량 지표 */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                <Stat label="목소리 크기" value={`${summary.loudness}/100`} />
                <Stat label="억양 폭" value={`${summary.pitchRange}Hz`} />
                <Stat label="길이" value={`${summary.duration}s`} />
                <Stat label="점수" value={assessment && !assessment.error ? `${assessment.score}점` : assessing ? '…' : '-'} />
              </div>

              {/* 내 목소리 곡선 — 억양(높낮이) + 크기를 시간축으로 '보이게' */}
              {summary.trace && summary.trace.length >= 3 && !summary.micIssue && (
                <div className="mb-3 p-3 rounded-xl bg-white border border-gray-100">
                  <p className="text-xs text-gray-500 mb-1">내 목소리 곡선</p>
                  <PitchEnergyGraph trace={summary.trace} summary={summary} />
                </div>
              )}

              <div className="space-y-2">
                {/* 발성·운율(지표 모드)은 드릴 목표와 상충할 수 있어 일반 크기/톤 메시지는 숨김 */}
                {!metricMode && (
                  <div className={`p-3 rounded-lg text-sm ${summary.volOk ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>🔊 {summary.volMsg}</div>
                )}
                {!metricMode && summary.toneMsg && (
                  <div className={`p-3 rounded-lg text-sm ${summary.toneOk === false ? 'bg-amber-50 text-amber-700' : summary.toneOk ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-600'}`}>🎵 {summary.toneMsg}</div>
                )}

                {assessing && (
                  <div className="p-3 rounded-lg bg-primary-50 text-primary-600 text-sm flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-primary-300 border-t-primary-600 rounded-full animate-spin" />
                    {metricMode ? '결과를 확인하는 중…' : '발음을 분석하는 중…'}
                  </div>
                )}
                {assessment && !assessment.error && (
                  <>
                    {assessment.transcript != null && (
                      <div className="p-3 rounded-lg bg-white border border-gray-200 text-sm">
                        <span className="text-gray-400 text-xs">이렇게 들렸어요</span>
                        <p className="font-bold text-gray-900">"{assessment.transcript || '(잘 안 들렸어요)'}"</p>
                      </div>
                    )}
                    {assessment.confusions?.length > 0 && (
                      <div className="p-2 rounded-lg bg-amber-50 text-amber-700 text-xs">
                        다르게 들린 소리: {assessment.confusions.map((c) => `${c.correct}→${c.confused_as}`).join(', ')}
                      </div>
                    )}
                    {assessment.coaching && (
                      <div className="p-3 rounded-lg bg-primary-50 text-primary-800 text-sm leading-relaxed">🗣️ {assessment.coaching}</div>
                    )}
                  </>
                )}
                {assessment?.error && (
                  <div className="p-3 rounded-lg bg-gray-50 text-gray-500 text-sm">{assessment.error}</div>
                )}
              </div>

              <div className="flex gap-2 mt-4">
                <button onClick={() => { setSummary(null); setAssessment(null) }} className="flex-1 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50">다시 말하기</button>
                <button onClick={nextItem} className="flex-1 btn-primary py-2 text-sm">{reviewMode || stageNo != null ? '다음 →' : '다음 단어 →'}</button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        </>
        )}
      </main>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="p-2 rounded-lg bg-gray-50 text-center">
      <p className="text-[10px] text-gray-400">{label}</p>
      <p className="font-bold text-gray-800 text-sm">{value}</p>
    </div>
  )
}

/**
 * 피치·강세 그래프 — 청각장애 학습자가 자기 발음을 '들을' 수 없으니 곡선으로 '본다'.
 *  위 레인: 억양(높낮이). 평균 피치를 중심으로 ±90Hz 매핑 → 기준 목소리 높이와 무관하게
 *           '변화량'만 곡선으로 드러난다(평평하게 말하면 가운데 점선에 붙은 평평한 선).
 *  아래 레인: 목소리 크기(에너지 포락선) + '적정' 기준 점선. 자주 아래로 내려가면 너무 작았다는 뜻.
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
        <rect x={padL} y={pTop} width={innerW} height={pBot - pTop} rx="8" fill="#eef2ff" />
        <rect x={padL} y={eTop} width={innerW} height={eBot - eTop} rx="8" fill="#f1f5f9" />

        {/* 억양 기준선(평균=평평의 기준) */}
        <line x1={padL} y1={midY} x2={W - padR} y2={midY} stroke="#a5b4fc" strokeWidth="1" strokeDasharray="4 4" />
        {/* 억양 곡선 */}
        {segs.map((pts, i) => (
          <path key={i} d={smooth(pts)} fill="none" stroke="#4f46e5" strokeWidth="2.5"
                strokeLinejoin="round" strokeLinecap="round" />
        ))}

        {/* 크기 포락선(면적 + 부드러운 상단선) + 적정 기준선 */}
        <path d={areaFill} fill="#6366f1" fillOpacity="0.16" stroke="none" />
        <path d={topLine} fill="none" stroke="#6366f1" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <line x1={padL} y1={yTh} x2={W - padR} y2={yTh} stroke="#f59e0b" strokeWidth="1" strokeDasharray="5 4" />
        <text x={W - padR} y={yTh - 3} textAnchor="end" fontSize="9" fill="#d97706">적정</text>

        {/* 레인 라벨 */}
        <text x="4" y={midY - 3} fontSize="10" fill="#6366f1" fontWeight="600">억양</text>
        <text x="4" y={midY + 9} fontSize="8" fill="#94a3b8">높낮이</text>
        <text x="4" y={(eTop + eBot) / 2 + 3} fontSize="10" fill="#64748b" fontWeight="600">크기</text>

        {/* 시간축 */}
        <text x={padL} y={H - 5} fontSize="9" fill="#94a3b8">0s</text>
        <text x={W - padR} y={H - 5} textAnchor="end" fontSize="9" fill="#94a3b8">{tMax.toFixed(1)}s</text>
      </svg>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-[11px] text-gray-500">
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-[2px] bg-primary-600" /> 억양선</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-2 bg-primary-100 border border-primary-500" /> 목소리 크기</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 border-t border-dashed border-amber-500" /> 적정 크기</span>
      </div>
      <div className="mt-1 space-y-0.5">
        {flat && <p className="text-[11px] text-amber-600">억양선이 가운데 점선을 거의 안 벗어났어요 → 문장 끝에서 선을 올리거나 내려보세요.</p>}
        {quiet && <p className="text-[11px] text-amber-600">크기 곡선이 적정선 아래로 자주 내려갔어요 → 배에 힘을 주고 더 크게.</p>}
        {!flat && !quiet && <p className="text-[11px] text-emerald-600">억양선과 크기 곡선이 잘 살아있어요 👍</p>}
      </div>
    </div>
  )
}
