import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI, scoreAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'

/**
 * 대화형 독화 연습 모드
 * AI와 자연스러운 대화를 나누며 독화 능력 향상
 */

const MAX_TURNS = 6

export default function Conversation() {
  const navigate = useNavigate()
  const currentScenario = useStore((state) => state.currentScenario)
  const user = useStore((state) => state.user)

  const [messages, setMessages] = useState([]) // {role: 'ai'|'user', text: string, visemes: []}
  const [currentAIVisemes, setCurrentAIVisemes] = useState([])
  const [currentAIText, setCurrentAIText] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [userInput, setUserInput] = useState('')
  const [phase, setPhase] = useState('watching') // 'watching' | 'answering' | 'done'
  const [revealedText, setRevealedText] = useState(false)
  const [turnCount, setTurnCount] = useState(0)
  const [scores, setScores] = useState([])

  const chatBottomRef = useRef(null)

  useEffect(() => {
    if (!currentScenario) {
      navigate('/dashboard')
      return
    }
    // Start with first AI message
    sendAIMessage([])
  }, [])

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendAIMessage = async (history) => {
    setIsLoading(true)
    setRevealedText(false)
    setPhase('watching')

    try {
      const response = await learningAPI.getConversationTurn(
        currentScenario.situation,
        currentScenario.level,
        history
      )

      const visemeData = await learningAPI.getVisemes(response.text)
      setCurrentAIVisemes(visemeData)
      setCurrentAIText(response.text)
      setIsPlaying(true)

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
      setCurrentAIVisemes(visemeData)
      setCurrentAIText(fallbackText)
      setIsPlaying(true)

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
    let turnScore = null
    try {
      const r = await scoreAPI.score(currentAIText, answer)
      turnScore = r.score
    } catch { /* 채점 실패해도 대화는 진행 */ }

    setMessages((prev) => [...prev, { role: 'user', text: answer, score: turnScore }])
    if (turnScore != null) setScores((prev) => [...prev, turnScore])

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
    navigate('/dashboard')
  }

  if (!currentScenario) return null

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50 flex flex-col">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 shrink-0">
        <div className="max-w-6xl mx-auto px-4 py-3 flex justify-between items-center">
          <div>
            <h1 className="text-lg font-bold text-gray-900">대화 연습</h1>
            <p className="text-xs text-gray-500">{currentScenario.situation} · 레벨 {currentScenario.level}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">
              {turnCount}/{MAX_TURNS} 대화
            </span>
            <div className="w-20 bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-primary-500 h-full rounded-full transition-all"
                style={{ width: `${(turnCount / MAX_TURNS) * 100}%` }}
              />
            </div>
            <button
              onClick={handleFinish}
              className="text-gray-400 hover:text-gray-700 text-sm"
            >
              ✕
            </button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden max-w-6xl mx-auto w-full px-4 py-4 gap-4">
        {/* Left: Avatar player */}
        <div className="w-80 shrink-0 flex flex-col gap-3">
          <div className="card flex-1">
            <p className="text-xs font-semibold text-gray-500 mb-2">입모양 읽기</p>
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-12 gap-2">
                <div className="w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                <p className="text-xs text-gray-400">AI가 응답 중...</p>
              </div>
            ) : (
              <LipSyncPlayer3D
                visemes={currentAIVisemes}
                isPlaying={isPlaying}
                onComplete={handlePlaybackDone}
                loop={false}
              />
            )}
          </div>

          {/* Reveal text button */}
          {phase === 'answering' && !revealedText && (
            <button
              onClick={handleRevealText}
              className="w-full py-2 text-sm rounded-lg bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors font-medium"
            >
              무슨 말인지 보기
            </button>
          )}

          {revealedText && currentAIText && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800 font-medium"
            >
              "{currentAIText}"
            </motion.div>
          )}
        </div>

        {/* Right: Chat history + input */}
        <div className="flex-1 flex flex-col gap-3">
          {/* Chat messages */}
          <div className="flex-1 card overflow-y-auto" style={{ maxHeight: '400px' }}>
            <p className="text-xs font-semibold text-gray-400 mb-3">대화 기록</p>
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
                      className={`max-w-xs px-3 py-2 rounded-xl text-sm ${
                        msg.role === 'user'
                          ? 'bg-primary-500 text-white rounded-br-sm'
                          : msg.revealed
                          ? 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm shadow-sm'
                          : 'bg-gray-100 text-gray-400 italic rounded-bl-sm'
                      }`}
                    >
                      {msg.role === 'ai' && !msg.revealed
                        ? '(입모양을 보고 맞춰보세요)'
                        : msg.text}
                      {msg.role === 'user' && msg.score != null && (
                        <span className="block mt-0.5 text-[10px] opacity-80">이해도 {msg.score}점</span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              <div ref={chatBottomRef} />
            </div>
          </div>

          {/* Input area */}
          {phase === 'answering' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="card"
            >
              <p className="text-sm font-medium text-gray-700 mb-2">
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
                  onClick={handleSendAnswer}
                  disabled={!userInput.trim()}
                  className="btn-primary px-5 disabled:opacity-50"
                >
                  전송
                </button>
              </div>
            </motion.div>
          )}

          {phase === 'watching' && !isLoading && (
            <div className="card text-center py-4 text-sm text-gray-500">
              입모양 애니메이션을 보고 있는 중... 재생이 끝나면 답변할 수 있습니다.
            </div>
          )}

          {phase === 'done' && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="card text-center py-6"
            >
              <div className="text-4xl mb-2">대화 완료</div>
              {scores.length > 0 && (
                <p className="text-lg font-bold text-primary-600 mb-1">
                  평균 이해도 {Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)}점
                </p>
              )}
              <p className="text-gray-600 mb-4">
                {MAX_TURNS}번의 대화를 완료했습니다!
              </p>
              <button onClick={handleFinish} className="btn-primary">
                대시보드로 돌아가기
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  )
}
