import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

/**
 * QuizForm Component
 * Handles user answer input and displays scoring feedback
 *
 * Props:
 * - onSubmit: Callback(answer) when user submits answer
 * - loading: Boolean indicating submission is in progress
 * - result: Scoring result object or null
 * - correctAnswer: The correct sentence (revealed after submission)
 */
export default function QuizForm({
  onSubmit,
  onRetry,
  loading = false,
  result = null,
  correctAnswer = '',
  label = '입모양을 보고 문장을 입력하세요',
  placeholder = '여기에 읽은 문장을 입력하세요...',
}) {
  const [answer, setAnswer] = useState('')

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
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4"
          >
            {/* Score Display */}
            <div
              className={`card ${
                result.score >= 80
                  ? 'bg-green-50 border-green-200'
                  : result.score >= 60
                  ? 'bg-yellow-50 border-yellow-200'
                  : 'bg-red-50 border-red-200'
              }`}
            >
              <div className="text-center">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 200 }}
                  className="text-6xl font-bold mb-2"
                  style={{
                    color:
                      result.score >= 80
                        ? '#10B981'
                        : result.score >= 60
                        ? '#F59E0B'
                        : '#EF4444',
                  }}
                >
                  {Math.round(result.score)}
                </motion.div>
                <p className="text-lg font-semibold text-gray-700 mb-3">
                  {result.feedback?.message || '수고하셨습니다!'}
                </p>

                {result.xp_gained && (
                  <div className="inline-flex items-center bg-primary-100 text-primary-700 px-4 py-2 rounded-full font-medium">
                    ⭐ +{result.xp_gained} XP
                  </div>
                )}
              </div>

              {/* Phoneme Accuracy Breakdown */}
              {result.phoneme_accuracy && (
                <div className="mt-6 space-y-2">
                  <h4 className="font-semibold text-gray-700 text-sm">
                    음소별 정확도
                  </h4>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-white rounded-lg p-3 text-center">
                      <p className="text-xs text-gray-600 mb-1">초성</p>
                      <p className="text-lg font-bold text-gray-900">
                        {result.phoneme_accuracy.initial}%
                      </p>
                    </div>
                    <div className="bg-white rounded-lg p-3 text-center">
                      <p className="text-xs text-gray-600 mb-1">중성</p>
                      <p className="text-lg font-bold text-gray-900">
                        {result.phoneme_accuracy.medial}%
                      </p>
                    </div>
                    <div className="bg-white rounded-lg p-3 text-center">
                      <p className="text-xs text-gray-600 mb-1">종성</p>
                      <p className="text-lg font-bold text-gray-900">
                        {result.phoneme_accuracy.final}%
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Specific Feedback */}
              {result.feedback?.specific_tip && (
                <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-sm text-blue-800">
                    💡 <strong>팁:</strong> {result.feedback.specific_tip}
                  </p>
                </div>
              )}
            </div>

            {/* Answer Comparison */}
            <div className="card">
              <h4 className="font-semibold text-gray-700 mb-3">답변 비교</h4>
              <div className="space-y-2">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-600 mb-1">정답</p>
                  <p className="text-base font-medium text-gray-900">
                    {correctAnswer}
                  </p>
                </div>
                <div className="bg-blue-50 rounded-lg p-3">
                  <p className="text-xs text-gray-600 mb-1">입력한 답</p>
                  <p className="text-base font-medium text-blue-900">
                    {answer}
                  </p>
                </div>
              </div>
            </div>

            {/* New Level Achievement */}
            {result.new_level && result.new_level > (result.old_level || 0) && (
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="card bg-gradient-to-r from-yellow-400 to-orange-500 text-white text-center"
              >
                <div className="text-4xl mb-2">🎉</div>
                <p className="text-xl font-bold">레벨 업!</p>
                <p className="text-lg">레벨 {result.new_level} 달성</p>
              </motion.div>
            )}

            {/* Retry button */}
            {onRetry && (
              <button
                onClick={handleRetry}
                className="w-full py-2.5 rounded-lg border-2 border-primary-400 text-primary-600 font-medium hover:bg-primary-50 transition-colors text-sm"
              >
                ↩ 같은 문장 다시 도전
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
