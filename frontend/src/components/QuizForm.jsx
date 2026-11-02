import { useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { MotionPanel } from './UI'

// 문장 점수 색 — 기준은 예전 그대로 80/60(핸드오프 §3.2는 음소·정답률 기준만 정한다), 색은 good/warn/bad 토큰.
const TONE = {
  good: { card: 'bg-good-tint border-good-line', text: 'text-good' },
  warn: { card: 'bg-warn-tint border-warn/35', text: 'text-warn-strong' },
  bad: { card: 'bg-bad-tint border-bad-line', text: 'text-bad' },
}
const toneOf = (score) => TONE[score >= 80 ? 'good' : score >= 60 ? 'warn' : 'bad']

/**
 * QuizForm Component
 * Handles user answer input and displays scoring feedback
 *
 * Props:
 * - onSubmit: Callback(answer) when user submits answer
 * - loading: Boolean indicating submission is in progress
 * - result: Scoring result object or null
 * - correctAnswer: The correct sentence (revealed after submission)
 * - initialAnswer: 처음 칸에 넣어 둘 답(자음 피드백 뒤 '정답 보기'로 첫 답을 결과와 함께 보일 때)
 */
export default function QuizForm({
  onSubmit,
  onRetry,
  loading = false,
  result = null,
  correctAnswer = '',
  label = '입모양을 보고 문장을 입력하세요',
  placeholder = '여기에 읽은 문장을 입력하세요...',
  initialAnswer = '',
}) {
  const [answer, setAnswer] = useState(initialAnswer)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (answer.trim() && !loading) {
      onSubmit(answer.trim())
    }
  }

  const handleRetry = () => {
    setAnswer('')
    onRetry?.()
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="answer" className="label">
            {label}
          </label>
          <textarea
            id="answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={loading || result !== null}
            className="input-field resize-none h-24"
            placeholder={placeholder}
            required
          />
        </div>

        {!result && (
          <button
            type="submit"
            disabled={loading || !answer.trim()}
            className="btn-primary w-full"
          >
            {loading ? (
              <span className="flex items-center justify-center">
                <div className="spinner w-5 h-5 border-4 border-white border-t-transparent rounded-full mr-2" />
                채점 중...
              </span>
            ) : (
              '제출하기'
            )}
          </button>
        )}
      </form>

      {/* Result Display */}
      <AnimatePresence>
        {result && (
          <MotionPanel
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {/* Score Display */}
            <div
              role="status"
              aria-live="polite"
              className={`card ${toneOf(result.score).card}`}
            >
              <div className="text-center">
                <MotionPanel
                  className={`text-6xl font-bold mb-2 ${toneOf(result.score).text}`}
                >
                  {Math.round(result.score)}
                </MotionPanel>
                <p className="text-lg font-semibold text-ink mb-3">
                  {result.feedback?.message || '수고하셨습니다!'}
                </p>

                {/* XP가 0이면(연습으로만 채점 등) 칩을 그리지 않는다. 숫자 0을 &&에 두면 화면에 '0'이 찍힌다. */}
                {result.xp_gained > 0 && (
                  <div className="inline-flex items-center bg-primary-100 text-primary-700 px-4 py-2 rounded-full font-medium">
                    경험치 +{result.xp_gained}
                  </div>
                )}
              </div>

              {/* Phoneme Accuracy Breakdown */}
              {result.phoneme_accuracy && (
                <div className="mt-6 space-y-2">
                  <h4 className="font-semibold text-ink text-sm">
                    소리별 정답률
                  </h4>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-white rounded-lg p-3 text-center">
                      <p className="text-xs text-ink-muted mb-1">초성</p>
                      <p className="text-lg font-bold text-ink">
                        {result.phoneme_accuracy.initial}%
                      </p>
                    </div>
                    <div className="bg-white rounded-lg p-3 text-center">
                      <p className="text-xs text-ink-muted mb-1">중성</p>
                      <p className="text-lg font-bold text-ink">
                        {result.phoneme_accuracy.medial}%
                      </p>
                    </div>
                    <div className="bg-white rounded-lg p-3 text-center">
                      <p className="text-xs text-ink-muted mb-1">종성</p>
                      <p className="text-lg font-bold text-ink">
                        {result.phoneme_accuracy.final}%
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Specific Feedback */}
              {result.feedback?.specific_tip && (
                <div className="mt-4 bg-bookmark-tint border border-bookmark-line rounded-lg p-3">
                  <p className="text-sm text-bookmark-dark">
                    <strong>팁:</strong> {result.feedback.specific_tip}
                  </p>
                </div>
              )}
            </div>

            {/* Answer Comparison */}
            <div className="card">
              <h4 className="font-semibold text-ink mb-3">답변 비교</h4>
              <div className="space-y-2">
                <div className="bg-surface-muted rounded-lg p-3">
                  <p className="text-xs text-ink-muted mb-1">정답</p>
                  <p className="text-base font-medium text-ink">
                    {correctAnswer}
                  </p>
                </div>
                <div className="bg-bookmark-tint rounded-lg p-3">
                  <p className="text-xs text-ink-muted mb-1">입력한 답</p>
                  <p className="text-base font-medium text-bookmark-dark">
                    {answer}
                  </p>
                </div>
              </div>
            </div>

            {/* New Level Achievement */}
            {result.new_level && result.new_level > (result.old_level || 0) && (
              <MotionPanel kind="complete"
                className="card bg-track-tint text-track-dark text-center"
              >
                <p className="text-xl font-bold">레벨 업!</p>
                <p className="text-lg">레벨 {result.new_level} 달성</p>
              </MotionPanel>
            )}

            {/* Retry button */}
            {onRetry && (
              <button
                onClick={handleRetry}
                className="w-full py-2.5 rounded-lg border-2 border-primary-400 text-primary-600 font-medium hover:bg-primary-50 transition-colors text-sm"
              >
                같은 문장 다시 도전
              </button>
            )}
          </MotionPanel>
        )}
      </AnimatePresence>
    </div>
  )
}
