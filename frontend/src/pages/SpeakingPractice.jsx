import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI, speakAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'

/**
 * 말하기 연습 (발화 피드백)
 * ------------------------------------------------------------------
 * 청각장애인은 자기 발음을 못 들어 피드백 루프가 끊겨 있다. 이 화면은 그 끊긴
 * 청각 피드백을 '눈/AI'로 대체한다.
 *  1) 말하는 동안 볼륨·톤(피치)·파형을 실시간으로 보여준다 (Web Audio, 서버 0).
 *  2) 녹음을 서버로 보내 Whisper가 받아쓰고, 기존 음운 채점으로 '어떤 소리가
 *     다르게 났는지' + Claude 발음 코칭을 돌려준다.
 */

// 자기상관 기반 기본주파수(피치) 추정: 마이크 시간영역 버퍼 → Hz
function autoCorrelate(buf, sampleRate) {
  const SIZE = buf.length
  let rms = 0
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i]
  rms = Math.sqrt(rms / SIZE)
  if (rms < 0.01) return -1
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
  const [words, setWords] = useState([])
  const [target, setTarget] = useState(null)
  const [frames, setFrames] = useState([])
  const [recording, setRecording] = useState(false)
  const [vol, setVol] = useState(0)
  const [pitch, setPitch] = useState(null)
  const [err, setErr] = useState(null)
  const [summary, setSummary] = useState(null)
  const [assessing, setAssessing] = useState(false)
  const [assessment, setAssessment] = useState(null)   // {transcript, score, confusions, coaching} | {error}

  const acRef = useRef(null)
  const analyserRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const volHist = useRef([])
  const pitchHist = useRef([])

  useEffect(() => {
    curriculumAPI.getWords()
      .then((d) => { const ws = d.words.map((w) => w.word); setWords(ws); pickWord(ws) })
      .catch(() => setErr('콘텐츠를 불러오지 못했어요.'))
    return () => teardown()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const pickWord = async (ws) => {
    const list = ws && ws.length ? ws : words
    if (!list.length) return
    const t = list[Math.floor(Math.random() * list.length)]
    setTarget(t); setFrames([]); setSummary(null); setAssessment(null)
    try { setFrames(await learningAPI.getVisemes(t)) } catch { /* ignore */ }
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
    closeAudio()
  }

  const start = async () => {
    setErr(null); setSummary(null); setAssessment(null)
    volHist.current = []; pitchHist.current = []; chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const AC = window.AudioContext || window.webkitAudioContext
      const ac = new AC(); acRef.current = ac
      const src = ac.createMediaStreamSource(stream)
      const analyser = ac.createAnalyser(); analyser.fftSize = 2048
      src.connect(analyser); analyserRef.current = analyser
      // 녹음(서버 전사용) — 미지원 브라우저면 시각화만 동작
      try {
        const rec = new MediaRecorder(stream)
        rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data) }
        rec.onstop = onRecStop
        rec.start()
        recorderRef.current = rec
      } catch { recorderRef.current = null }
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
      setAssessing(true)
      try {
        const r = await speakAPI.assess(target, blob)
        setAssessment(r)
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
    setSummary(computeSummary())
    const rec = recorderRef.current
    if (rec && rec.state !== 'inactive') rec.stop()   // → onRecStop (업로드) → closeAudio
    else closeAudio()
  }

  const computeSummary = () => {
    const vs = volHist.current, ps = pitchHist.current
    if (vs.length < 5) return { volMsg: '소리가 거의 안 잡혔어요. 마이크에 가까이서 말해보세요.', volOk: false, toneMsg: '', toneOk: null }
    const avgVol = vs.reduce((a, b) => a + b, 0) / vs.length
    let volMsg, volOk
    if (avgVol < 0.12) { volMsg = '너무 작았어요. 배에 힘을 주고 더 크게 말해보세요.'; volOk = false }
    else if (avgVol > 0.8) { volMsg = '조금 컸어요. 편하게 낮춰도 괜찮아요.'; volOk = true }
    else { volMsg = '볼륨이 적당했어요. 좋아요!'; volOk = true }
    let toneMsg, toneOk
    if (ps.length < 4) { toneMsg = '소리를 조금 더 이어서 내보면 톤을 볼 수 있어요.'; toneOk = null }
    else {
      const m = ps.reduce((a, b) => a + b, 0) / ps.length
      const sd = Math.sqrt(ps.reduce((a, b) => a + (b - m) ** 2, 0) / ps.length)
      if (sd < 12) { toneMsg = '톤이 평평했어요. 끝을 올리거나 내리며 억양을 넣어보세요.'; toneOk = false }
      else { toneMsg = '톤에 자연스러운 변화가 있었어요!'; toneOk = true }
    }
    return { volMsg, volOk, toneMsg, toneOk }
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
      const v = Math.min(1, rms * 4)
      volHist.current.push(v)
      drawWave(buf, v)
      if (frame % 4 === 0) {
        const p = autoCorrelate(buf, acRef.current.sampleRate)
        const hz = p > 70 && p < 500 ? Math.round(p) : null
        if (hz) pitchHist.current.push(hz)
        setVol(v); setPitch(hz)
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
    ctx.strokeStyle = v > 0.12 ? '#4f46e5' : '#cbd5e1'
    ctx.beginPath()
    const step = Math.max(1, Math.ceil(buf.length / W))
    for (let x = 0; x < W; x++) {
      const s = buf[x * step] || 0
      const y = H / 2 + s * (H / 2) * 0.9
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.stroke()
  }

  const volLabel = !recording ? '-' : vol < 0.12 ? '너무 작음' : vol > 0.8 ? '큼' : '적당'

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">말하기 연습</h1>
            <p className="text-sm text-gray-500">귀 대신 눈으로 — 내 목소리를 보면서 발음을 다듬어요</p>
          </div>
          <button onClick={() => { teardown(); navigate('/dashboard') }} className="text-gray-500 hover:text-gray-800 text-sm">✕ 나가기</button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card">
            <p className="text-sm text-gray-500 mb-1">이렇게 말해보세요</p>
            <p className="text-3xl font-bold text-gray-900 text-center py-2">{target || '…'}</p>
            <MouthAvatar frames={frames} height={230} />
            <p className="text-xs text-gray-400 mt-2 text-center">위 입모양을 참고해 또박또박 말해보세요</p>
          </div>

          <div className="card flex flex-col">
            {err && <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{err}</div>}

            <canvas ref={canvasRef} width={480} height={120}
              className="w-full rounded-xl bg-slate-50 border border-gray-100" style={{ height: 120 }} />

            <div className="mt-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1"><span>볼륨</span><span>{volLabel}</span></div>
              <div className="bg-gray-200 rounded-full h-3 overflow-hidden">
                <div className={`h-full rounded-full transition-[width] duration-75 ${vol < 0.12 ? 'bg-gray-300' : vol > 0.8 ? 'bg-amber-400' : 'bg-primary-500'}`}
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
              <h3 className="font-bold text-gray-900 mb-3">이번 발화 피드백</h3>
              <div className="space-y-2">
                <div className={`p-3 rounded-lg text-sm ${summary.volOk ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>🔊 {summary.volMsg}</div>
                {summary.toneMsg && (
                  <div className={`p-3 rounded-lg text-sm ${summary.toneOk === false ? 'bg-amber-50 text-amber-700' : summary.toneOk ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-600'}`}>🎵 {summary.toneMsg}</div>
                )}

                {/* 서버 발음 분석 (Whisper 전사 + 채점 + Claude 코칭) */}
                {assessing && (
                  <div className="p-3 rounded-lg bg-primary-50 text-primary-600 text-sm flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-primary-300 border-t-primary-600 rounded-full animate-spin" />
                    발음을 분석하는 중…
                  </div>
                )}
                {assessment && !assessment.error && (
                  <>
                    <div className="p-3 rounded-lg bg-white border border-gray-200 text-sm">
                      <span className="text-gray-400 text-xs">이렇게 들렸어요</span>
                      <p className="font-bold text-gray-900">"{assessment.transcript || '(잘 안 들렸어요)'}"</p>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-gray-500 shrink-0">발음 점수</span>
                      <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
                        <div className="bg-primary-500 h-full rounded-full" style={{ width: `${Math.min(assessment.score, 100)}%` }} />
                      </div>
                      <span className="font-semibold text-primary-600 shrink-0">{assessment.score}점</span>
                    </div>
                    {assessment.confusions?.length > 0 && (
                      <div className="p-2 rounded-lg bg-amber-50 text-amber-700 text-xs">
                        다르게 들린 소리: {assessment.confusions.map((c) => `${c.correct}→${c.confused_as}`).join(', ')}
                      </div>
                    )}
                    <div className="p-3 rounded-lg bg-primary-50 text-primary-800 text-sm">🗣️ {assessment.coaching}</div>
                  </>
                )}
                {assessment?.error && (
                  <div className="p-3 rounded-lg bg-gray-50 text-gray-500 text-sm">{assessment.error}</div>
                )}
              </div>

              <div className="flex gap-2 mt-4">
                <button onClick={() => { setSummary(null); setAssessment(null) }} className="flex-1 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50">다시 말하기</button>
                <button onClick={() => pickWord()} className="flex-1 btn-primary py-2 text-sm">다음 단어 →</button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  )
}
