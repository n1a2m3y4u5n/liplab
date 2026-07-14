import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { tactileAPI } from '../api'

/**
 * 촉각(타도마) 학습 — 얼굴 모형(아두이노)을 손으로 느끼며 말을 이해하는 훈련.
 * 청각장애인이 상대의 턱·입술·진동·기류를 손으로 느껴 말을 알아듣는 '타도마(Tadoma)' 방식을,
 * 3D 프린팅 얼굴 모형 + 웹(Web Serial)으로 재현한다.
 *  - 체험 모드: 문장을 골라 재생 → 손으로 느끼며 익힘
 *  - 퀴즈 모드: 모형이 단어를 '말해주고' → 무엇이었는지 맞히기(채점)
 * ※ Web Serial API는 Chrome/Edge(데스크톱)에서만 동작한다.
 */

const AIRFLOW_CODE = { none: 0, plosive: 1, fricative: 2 }
const PRESET = ['바다', '파도', '엄마', '아빠', '학교', '사과', '나무', '우유', '안녕하세요']
const QUIZ_WORDS = ['바다', '파도', '엄마', '아빠', '학교', '사과', '나무', '우유', '다리', '토끼', '기차', '구름']

export default function TactilePractice() {
  const navigate = useNavigate()
  const supported = typeof navigator !== 'undefined' && 'serial' in navigator

  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('')
  const [text, setText] = useState('바다')
  const [playing, setPlaying] = useState(false)
  const [playingLabel, setPlayingLabel] = useState('')
  const [mode, setMode] = useState('explore')   // 'explore' | 'quiz'

  const [quiz, setQuiz] = useState(null)         // {answer, options}
  const [quizResult, setQuizResult] = useState(null)
  const [score, setScore] = useState({ correct: 0, total: 0 })

  const portRef = useRef(null)
  const writerRef = useRef(null)
  const enc = useRef(new TextEncoder())

  const disconnect = async () => {
    try { writerRef.current?.releaseLock() } catch { /* noop */ }
    try { await portRef.current?.close() } catch { /* noop */ }
    writerRef.current = null; portRef.current = null; setConnected(false)
  }
  useEffect(() => () => { disconnect() }, [])

  const connect = async () => {
    try {
      const port = await navigator.serial.requestPort()
      await port.open({ baudRate: 9600 })
      portRef.current = port
      writerRef.current = port.writable.getWriter()
      setConnected(true); setStatus('얼굴 모형이 연결되었어요.')
    } catch (e) { setStatus('연결이 취소되었거나 실패했어요. ' + (e?.message || '')) }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  const sendLine = async (line) => {
    if (writerRef.current) await writerRef.current.write(enc.current.encode(line + '\n'))
  }

  const playSequence = async (seq, showLabels = true) => {
    setPlaying(true)
    for (const p of seq) {
      if (showLabels) setPlayingLabel(p.label)
      const a = AIRFLOW_CODE[p.airflow] ?? 0
      await sendLine(`${p.jaw},${p.lip},${p.voicing},${a},${p.duration_ms}`)
      await sleep(p.duration_ms + 40)   // 하드웨어가 유지하는 동안 대기
    }
    await sendLine('0,0,0,0,0')          // 정지(휴지)
    setPlayingLabel(''); setPlaying(false)
  }

  const playText = async (t) => {
    if (!connected) { setStatus('먼저 얼굴 모형을 연결하세요.'); return }
    if (playing) return
    try {
      const d = await tactileAPI.getSequence(t)
      await playSequence(d.sequence, true)
    } catch { setStatus('음소 시퀀스를 불러오지 못했어요.') }
  }

  const newQuiz = () => {
    const answer = QUIZ_WORDS[Math.floor(Math.random() * QUIZ_WORDS.length)]
    const opts = new Set([answer])
    while (opts.size < 4) opts.add(QUIZ_WORDS[Math.floor(Math.random() * QUIZ_WORDS.length)])
    setQuiz({ answer, options: [...opts].sort(() => Math.random() - 0.5) })
    setQuizResult(null)
  }
  const playQuiz = async () => {
    if (!quiz || playing) return
    if (!connected) { setStatus('먼저 얼굴 모형을 연결하세요.'); return }
    const d = await tactileAPI.getSequence(quiz.answer)
    await playSequence(d.sequence, false)   // 라벨 숨김 — 손으로만 느끼게
  }
  const answerQuiz = (opt) => {
    if (!quiz || quizResult) return
    const ok = opt === quiz.answer
    setQuizResult({ ok, picked: opt })
    setScore((s) => ({ correct: s.correct + (ok ? 1 : 0), total: s.total + 1 }))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">🖐️ 촉각 학습 (타도마)</h1>
            <p className="text-sm text-gray-500">얼굴 모형의 턱·입술·진동·바람을 손으로 느끼며 말을 이해해요</p>
          </div>
          <button onClick={() => { disconnect(); navigate('/dashboard') }} className="text-gray-500 hover:text-gray-800 text-sm">✕ 나가기</button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* 브라우저 안내 */}
        {!supported ? (
          <div className="card border-l-4 border-amber-400 bg-amber-50">
            <p className="font-semibold text-amber-800">이 브라우저에서는 하드웨어 연결이 지원되지 않아요.</p>
            <p className="text-sm text-amber-700 mt-1">촉각 학습은 <b>데스크톱 Chrome 또는 Edge</b>에서만 얼굴 모형(USB)에 연결할 수 있어요(Web Serial API). Chrome/Edge로 접속해 주세요.</p>
          </div>
        ) : (
          <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
            ⓘ 하드웨어 연결(Web Serial)은 <b>데스크톱 Chrome·Edge</b>에서만 동작합니다. USB로 얼굴 모형을 연결한 뒤 아래 버튼을 눌러주세요.
          </div>
        )}

        {/* 시작 전 준비 — 펌웨어 다운로드 */}
        <div className="card">
          <p className="font-semibold text-gray-900 mb-2">시작하기 전에</p>
          <ol className="text-sm text-gray-600 space-y-1 mb-3 list-decimal list-inside">
            <li>아래 펌웨어(.ino)를 내려받아 <b>아두이노 IDE</b>로 얼굴 모형(Uno)에 업로드하세요.</li>
            <li>USB로 연결한 뒤, 아래 <b>얼굴 모형 연결</b> 버튼을 누르세요.</li>
          </ol>
          <a href="/liplab_face.ino" download="liplab_face.ino"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 text-white text-sm font-semibold hover:bg-gray-900">
            ⬇ 아두이노 펌웨어 다운로드 (liplab_face.ino)
          </a>
          <p className="text-xs text-gray-400 mt-2">배선·핀 연결 방법은 파일 상단 주석에 정리되어 있어요.</p>
        </div>

        {/* 연결 */}
        <div className="card flex items-center justify-between">
          <div>
            <p className="font-semibold text-gray-900">얼굴 모형 연결</p>
            <p className="text-sm text-gray-500">{connected ? '🟢 연결됨' : '⚪ 연결 안 됨'}{status ? ` · ${status}` : ''}</p>
          </div>
          {connected ? (
            <button onClick={disconnect} className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50">연결 해제</button>
          ) : (
            <button onClick={connect} disabled={!supported}
              className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-semibold hover:bg-primary-700 disabled:opacity-40">🔌 얼굴 모형 연결</button>
          )}
        </div>

        {/* 모드 탭 */}
        <div className="flex gap-2">
          {[['explore', '🖐️ 체험'], ['quiz', '❓ 퀴즈']].map(([id, label]) => (
            <button key={id} onClick={() => setMode(id)}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${mode === id ? 'bg-primary-500 text-white' : 'bg-white text-gray-500 border border-gray-200 hover:bg-gray-50'}`}>{label}</button>
          ))}
        </div>

        {mode === 'explore' ? (
          <div className="card space-y-4">
            <div>
              <p className="text-sm text-gray-500 mb-2">낱말·문장을 골라 재생하면 얼굴 모형이 그대로 재현해요. 손을 대고 느껴보세요.</p>
              <div className="flex flex-wrap gap-2 mb-3">
                {PRESET.map((w) => (
                  <button key={w} onClick={() => setText(w)}
                    className={`px-3 py-1.5 rounded-full text-sm border ${text === w ? 'border-primary-400 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}>{w}</button>
                ))}
              </div>
              <input value={text} onChange={(e) => setText(e.target.value)}
                className="input-field" placeholder="직접 입력 (한글 문장)" />
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => playText(text)} disabled={!connected || playing || !text.trim()}
                className="btn-primary px-6 py-3 disabled:opacity-50">{playing ? '재생 중…' : '▶ 재생 (느껴보기)'}</button>
              {playingLabel && <span className="text-2xl font-bold text-primary-600 animate-pulse">{playingLabel}</span>}
            </div>
          </div>
        ) : (
          <div className="card space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">모형이 단어를 '말해주면' 손으로 느끼고 무엇인지 맞혀보세요.</p>
              <span className="text-sm text-gray-500">점수 {score.correct}/{score.total}</span>
            </div>
            {!quiz ? (
              <button onClick={newQuiz} className="btn-primary w-full py-3">퀴즈 시작</button>
            ) : (
              <>
                <div className="flex gap-2">
                  <button onClick={playQuiz} disabled={!connected || playing}
                    className="flex-1 py-3 rounded-xl bg-primary-600 text-white font-semibold hover:bg-primary-700 disabled:opacity-50">
                    {playing ? '말하는 중…' : '🖐️ 다시 말해주기 (느끼기)'}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {quiz.options.map((opt) => {
                    const picked = quizResult?.picked === opt
                    const isAnswer = quizResult && opt === quiz.answer
                    const cls = quizResult
                      ? (isAnswer ? 'border-green-400 bg-green-50 text-green-700'
                        : picked ? 'border-red-300 bg-red-50 text-red-600' : 'border-gray-200 text-gray-400')
                      : 'border-gray-200 hover:border-primary-400 hover:bg-primary-50 text-gray-800'
                    return (
                      <button key={opt} onClick={() => answerQuiz(opt)} disabled={!!quizResult}
                        className={`py-3 rounded-xl border-2 text-lg font-bold transition-all ${cls}`}>{opt}</button>
                    )
                  })}
                </div>
                {quizResult && (
                  <div className={`p-3 rounded-lg text-sm text-center ${quizResult.ok ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>
                    {quizResult.ok ? '정답! 🎉' : `정답은 "${quiz.answer}" 였어요.`}
                    <button onClick={newQuiz} className="ml-3 underline font-semibold">다음 →</button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <p className="text-xs text-gray-400 text-center">
          ‘바다’와 ‘파도’처럼 입모양이 비슷한 말도, 진동(성대)과 바람(기류)의 차이로 촉각으로는 구별됩니다.
        </p>
      </main>
    </div>
  )
}
