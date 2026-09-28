import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI, scoreAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import LoadingScreen from '../components/LoadingScreen'
import useSlowWeak from '../hooks/useSlowWeak'

/**
 * 4단계 · 대화 실전 — AI와 자연스러운 대화를 나누며 독화 능력 향상.
 * 레슨 집중 모드(핸드오프 §3.4): AppShell 없이 전체 화면, 상단 X(나가기) + 진행률 바 + n / 전체(대화 턴).
 * 첫 AI 말을 받는 동안은 레슨 시작 전 트랙 로딩(§4-10 223:30)을 띄운다. 대화·채점 로직은 그대로다.
 */

const MAX_TURNS = 6
// 되묻기(docs/curriculum-roadmap.md 1-4): 실제 대화에서 못 알아들었을 때 쓰는 요청을 연습한다. 한 턴에 두 번까지이고 이해도 점수에서
// 빼지 않는다. '천천히'는 입모양 길이를 1/0.7배로 늘리고, '다른 말로'는 같은 뜻의 다른 문장(LLM, 실패하면 '천천히'로 대신)을 보인다.
const MAX_REPAIRS = 2
const SLOW_RATE = 0.7
const slowFrames = (frames) => frames.map((f) => ({
  ...f,
  duration_ms: Math.round((f.duration_ms || 0) / SLOW_RATE),
  ...(f.transition_ms != null ? { transition_ms: Math.round(f.transition_ms / SLOW_RATE) } : {}),
}))
// 대화 전 전략 카드(청각 재활 프로그램의 의사소통 전략 훈련)
const STRATEGIES = [
  ['되묻기', '못 알아들으면 "다시", "천천히", "다른 말로"를 부탁해요. 실제 대화에서도 그대로 쓸 수 있어요.'],
  ['자리와 빛', '상대 얼굴이 밝게 보이는 쪽에 앉고, 창을 등진 사람은 피해요.'],
  ['먼저 알리기', '"입을 보고 알아들어요. 저를 보고 말해 주세요."라고 미리 말해 두면 편해요.'],
]
// 레슨 시작 전 트랙 로딩을 최소 이만큼은 보인다 — 첫 응답이 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000

export default function Conversation() {
  const navigate = useNavigate()
  const currentScenario = useStore((state) => state.currentScenario)
  const user = useStore((state) => state.user)

  const [messages, setMessages] = useState([]) // {role: 'ai'|'user', text: string, visemes: []}
  const [currentAIVisemes, setCurrentAIVisemes] = useState([])
  const shownAIVisemes = useSlowWeak(currentAIVisemes)   // 약한 입모양은 조금 천천히(연습 화면)
  const [currentAIText, setCurrentAIText] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [userInput, setUserInput] = useState('')
  const [phase, setPhase] = useState('watching') // 'watching' | 'answering' | 'done'
  const [revealedText, setRevealedText] = useState(false)
  const [turnCount, setTurnCount] = useState(0)
  const [scores, setScores] = useState([])

  const [introDone, setIntroDone] = useState(false)
  const [notice, setNotice] = useState('')   // 입모양을 받지 못해 재생 없이 답하게 됐을 때의 안내
  const [baseFrames, setBaseFrames] = useState([])   // 이번 턴 원래 속도 입모양(되묻기 '천천히'의 기준)
  const [repairs, setRepairs] = useState(0)          // 이번 턴 되묻기 횟수
  const [totalRepairs, setTotalRepairs] = useState(0)
  const [repairBusy, setRepairBusy] = useState(false)
  const [showTips, setShowTips] = useState(true)

  const chatBoxRef = useRef(null)    // 대화 기록 칸(자체 스크롤)
  const startedRef = useRef(false)   // 최초 AI 말풍선 중복 생성 방지(StrictMode)

  useEffect(() => {
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (!currentScenario) {
      // 상황이 없으면 대화를 시작할 수 없다. 상황 선택(AI 대화 모드)으로 보낸다(예전에는 /dashboard → 학습 경로로 되돌아가
      // 버튼이 아무 일도 안 하는 것처럼 보였다).
      navigate('/learn/scenario?mode=conversation', { replace: true })
      return
    }
    // StrictMode(개발)에서 이 effect가 두 번 실행되면 첫 AI 말풍선이 2개 생긴다.
    // ref 가드로 최초 1회만 대화를 시작한다.
    if (startedRef.current) return
    startedRef.current = true
    sendAIMessage([])
  }, [])

  useEffect(() => {
    // 새 말풍선이 보이게 대화 기록 칸만 끝으로 내린다(scrollIntoView는 휴대폰에서 창 전체를 끌어내렸다).
    const box = chatBoxRef.current
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // 받은 입모양으로 이번 턴 재생을 시작한다. 입모양이 비면(AI 문장·대체 문장 모두 못 받음) 재생 끝 알림(onComplete)이
  // 오지 않아 '재생이 끝나면 답변할 수 있습니다'에 멈추므로, 바로 답하는 단계로 넘기고 안내를 띄운다.
  const startTurn = (text, frames) => {
    const ok = Array.isArray(frames) && frames.length > 0
    setBaseFrames(ok ? frames : [])
    setRepairs(0)
    setCurrentAIVisemes(ok ? frames : [])
    setCurrentAIText(text)
    setIsPlaying(ok)
    if (!ok) {
      setPhase('answering')
      setNotice('입모양을 불러오지 못했어요. 무슨 말인지 보기로 문장을 확인할 수 있어요.')
    }
  }

  const sendAIMessage = async (history) => {
    setIsLoading(true)
    setRevealedText(false)
    setPhase('watching')
    setNotice('')

    try {
      const response = await learningAPI.getConversationTurn(
        currentScenario.situation,
        currentScenario.level,
        history
      )

      const visemeData = await learningAPI.getVisemes(response.text)
      startTurn(response.text, visemeData)

      // Add to chat history (hidden until played)
      setMessages((prev) => [
        ...prev,
        { role: 'ai', text: response.text, revealed: false }
      ])
    } catch (error) {
      console.error('Conversation error:', error)
      // Use fallback from scenario sentences
      const fallbackIdx = messages.filter((m) => m.role === 'ai').length
      const fallbackText = currentScenario.sentences?.[fallbackIdx] ||
        '안녕하세요. 무엇을 도와드릴까요?'

      const visemeData = await learningAPI.getVisemes(fallbackText).catch(() => [])
      startTurn(fallbackText, visemeData)

      setMessages((prev) => [
        ...prev,
        { role: 'ai', text: fallbackText, revealed: false }
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handlePlaybackDone = () => {
    setIsPlaying(false)
    setPhase('answering')
  }

  // 되묻기 — 다시 재생되는 동안은 답하는 칸을 닫는다(보는 중 표시)
  const replayWith = (frames, text) => {
    setRepairs((n) => n + 1)
    setTotalRepairs((n) => n + 1)
    setNotice('')
    if (text) setCurrentAIText(text)
    setCurrentAIVisemes(frames)
    setPhase('watching')
    setIsPlaying(true)
  }
  const handleRepair = async (kind) => {
    if (repairs >= MAX_REPAIRS || repairBusy || !baseFrames.length) return
    if (kind === 'again') return replayWith(baseFrames)
    if (kind === 'slow') return replayWith(slowFrames(baseFrames))
    setRepairBusy(true)
    try {
      const r = await learningAPI.rephraseTurn(currentAIText, currentScenario.situation, currentScenario.level)
      const frames = r?.text ? await learningAPI.getVisemes(r.text).catch(() => []) : []
      if (r?.text && frames.length) {
        // 바꾼 문장이 이번 턴의 정답이 된다(채점·말풍선). 원문은 말풍선에 함께 남긴다.
        setBaseFrames(frames)
        setMessages((prev) => prev.map((m, i) => (i === prev.length - 1 && m.role === 'ai' ? { ...m, text: r.text, orig: m.orig || m.text } : m)))
        replayWith(frames, r.text)
      } else {
        replayWith(slowFrames(baseFrames))
        setNotice('다른 말로 바꾸지 못해 천천히 다시 보여 드려요.')
      }
    } finally {
      setRepairBusy(false)
    }
  }

  const handleRevealText = () => {
    setRevealedText(true)
    // Also reveal in messages
    setMessages((prev) =>
      prev.map((m, i) => (i === prev.length - 1 ? { ...m, revealed: true } : m))
    )
  }

  const handleSendAnswer = async () => {
    if (!userInput.trim()) return

    const answer = userInput.trim()
    setUserInput('')

    // 이해도 채점 — 방금 본 AI 문장(currentAIText)과 비교 (음운 유사도 엔진 재사용)
    // '무슨 말인지 보기'로 문장을 본 뒤의 답은 연습으로만 채점한다(서버 practice_only: 4단계 숙달·XP에 넣지 않는다).
    // 끝 화면의 평균 이해도에도 넣지 않는다(말풍선의 점수는 그대로 보인다).
    const practiceOnly = revealedText
    let turnScore = null
    try {
      const r = await scoreAPI.score(currentAIText, answer, { practiceOnly })
      turnScore = r.score
    } catch { /* 채점 실패해도 대화는 진행 */ }

    setMessages((prev) => [...prev, { role: 'user', text: answer, score: turnScore }])
    if (turnScore != null && !practiceOnly) setScores((prev) => [...prev, turnScore])

    const newTurn = turnCount + 1
    setTurnCount(newTurn)

    if (newTurn >= MAX_TURNS) {
      setPhase('done')
      return
    }

    // Build history for next AI turn
    const history = [
      ...messages,
      { role: 'user', text: answer }
    ].map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }))

    await sendAIMessage(history)
  }

  const handleFinish = () => {
    navigate('/learn/path')
  }

  if (!currentScenario) return null

  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81) — 첫 AI 말(입모양)을 받는 동안 + 최소 표시 시간
  if (messages.length === 0 || !introDone) return <LoadingScreen variant="brand" track="perception" />

  return (
    <div className="flex min-h-[100dvh] flex-col bg-page">
      {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + 대화 턴 n / 6 */}
      <div className="mx-auto w-full max-w-6xl px-[18px] pt-[18px] lg:pt-7">
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={handleFinish} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${(turnCount / MAX_TURNS) * 100}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{turnCount} / {MAX_TURNS}</span>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 px-[18px] py-6 lg:flex-row lg:overflow-hidden lg:py-5">
        {/* Left: Avatar player — 모바일에선 위로 쌓이고, lg 이상에서만 좌측 고정폭 */}
        <div className="w-full lg:w-80 shrink-0 flex flex-col gap-3">
          <div className="card flex-1">
            <p className="mb-2 text-xs font-bold text-ink-muted">입모양 읽기 · {currentScenario.situation}</p>
            {isLoading ? (
              <div className="flex flex-col items-center justify-center gap-2 py-12">
                <div className="spinner size-8 rounded-full border-4 border-primary-200 border-t-primary-600" />
                <p className="text-xs text-ink-faint">AI가 응답 중...</p>
              </div>
            ) : (
              <LipSyncPlayer3D
                visemes={shownAIVisemes}
                isPlaying={isPlaying}
                onComplete={handlePlaybackDone}
                loop={false}
              />
            )}
          </div>

          {notice && (
            <div role="alert" className="rounded-14 border-2 border-bad-line bg-bad-tint px-4 py-2.5 text-[13.5px] font-bold text-bad-text">
              {notice}
            </div>
          )}

          {/* 되묻기: 답하기 전에 한 턴 두 번까지 */}
          {phase === 'answering' && !revealedText && baseFrames.length > 0 && (
            <div className="space-y-1.5">
              <div className="grid grid-cols-3 gap-2">
                {[['again', '다시'], ['slow', '천천히'], ['other', '다른 말로']].map(([k, label]) => (
                  <button key={k} type="button" onClick={() => handleRepair(k)}
                    disabled={repairs >= MAX_REPAIRS || repairBusy}
                    className="rounded-14 border-2 border-line bg-white py-2 text-[13.5px] font-bold text-ink transition hover:bg-fill disabled:opacity-40">
                    {k === 'other' && repairBusy ? '바꾸는 중…' : label}
                  </button>
                ))}
              </div>
              <p className="text-[12px] leading-snug text-ink-faint">
                {repairs >= MAX_REPAIRS ? '이번 말은 되묻기를 다 썼어요.' : `못 알아들었으면 부탁해 보세요. 점수는 그대로예요 (${MAX_REPAIRS - repairs}번 남음).`}
              </p>
            </div>
          )}

          {/* Reveal text button */}
          {phase === 'answering' && !revealedText && (
            <button
              type="button"
              onClick={handleRevealText}
              className="w-full rounded-14 bg-warn-tint py-2 text-sm font-bold text-warn-text transition hover:brightness-95"
            >
              무슨 말인지 보기
            </button>
          )}

          {revealedText && currentAIText && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-14 border border-good-line bg-good-tint p-3 text-sm font-bold text-good-text"
            >
              "{currentAIText}"
            </motion.div>
          )}
        </div>

        {/* Right: Chat history + input */}
        <div className="flex-1 flex flex-col gap-3">
          {/* 대화 전 전략 카드 — 첫 턴에만, 닫을 수 있다 */}
          {showTips && turnCount === 0 && (
            <div className="card space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-[13px] font-bold text-ink">대화할 때 쓰는 요령</p>
                <button type="button" onClick={() => setShowTips(false)} className="text-[12px] font-bold text-ink-faint hover:text-ink">닫기</button>
              </div>
              <dl className="grid grid-cols-[64px_1fr] gap-x-3 gap-y-1.5 text-[13px] leading-snug">
                {STRATEGIES.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="font-bold text-primary-600">{k}</dt>
                    <dd className="text-ink-muted">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {/* Chat messages */}
          <div ref={chatBoxRef} className="flex-1 card overflow-y-auto" style={{ maxHeight: '400px' }}>
            <p className="mb-3 text-xs font-bold text-ink-faint">대화 기록</p>
            <div className="space-y-3">
              <AnimatePresence>
                {messages.map((msg, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-xs rounded-14 px-3 py-2 text-sm ${
                        msg.role === 'user'
                          ? 'rounded-br-sm bg-primary-500 text-white'
                          : msg.revealed
                          ? 'rounded-bl-sm border border-line bg-white text-ink shadow-card'
                          : 'rounded-bl-sm bg-surface-sunken italic text-ink-faint'
                      }`}
                    >
                      {msg.role === 'ai' && !msg.revealed
                        ? '(입모양을 보고 맞춰보세요)'
                        : msg.text}
                      {msg.role === 'ai' && msg.revealed && msg.orig && (
                        <span className="block mt-0.5 text-[11px] text-ink-faint">처음 한 말: {msg.orig}</span>
                      )}
                      {msg.role === 'user' && msg.score != null && (
                        <span className="block mt-0.5 text-[10px] opacity-80">이해도 {msg.score}점</span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>

          {/* Input area */}
          {phase === 'answering' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="card"
            >
              <p className="mb-2 text-sm font-bold text-ink">
                무슨 말을 했나요? 읽은 내용을 답해보세요
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendAnswer()}
                  className="input-field flex-1"
                  placeholder="읽은 내용을 입력하세요..."
                  autoFocus
                />
                <button
                  type="button"
                  onClick={handleSendAnswer}
                  disabled={!userInput.trim()}
                  className="btn-primary px-5"
                >
                  전송
                </button>
              </div>
            </motion.div>
          )}

          {phase === 'watching' && !isLoading && (
            <div className="card py-4 text-center text-sm text-ink-muted">
              입모양 애니메이션을 보고 있는 중... 재생이 끝나면 답변할 수 있습니다.
            </div>
          )}

          {phase === 'done' && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="card text-center py-6"
            >
              <h2 className="mb-2 text-[26px] font-bold leading-figma tracking-[-0.65px] text-ink">대화 완료</h2>
              {scores.length > 0 && (
                <p className="mb-1 text-lg font-bold text-primary-600">
                  평균 이해도 {Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)}점
                </p>
              )}
              <p className="mb-4 text-ink-muted">
                {MAX_TURNS}번의 대화를 완료했습니다!
                {totalRepairs > 0 && <span className="block text-[13px]">되묻기 {totalRepairs}번. 실제 대화에서도 편하게 부탁해 보세요.</span>}
              </p>
              <button type="button" onClick={handleFinish} className="btn-primary">
                나가기
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  )
}
