import { motion } from 'framer-motion'

/**
 * 3단계 문장 주관식의 자음 피드백(계획 C9). 첫 답이 합격선 아래일 때 정답 문장 대신 보인다.
 * 맞힌 낱말은 그대로, 틀린 낱말은 음절마다 첫소리 자음만 보인다(서버 word_feedback, backend/sentence_feedback.py).
 * 학습자는 이 단서를 보고 입모양을 다시 본 뒤 한 번 더 적는다. 숙달에는 첫 답만 들어간다.
 */
export default function ConsonantFeedback({ feedback }) {
  const words = feedback?.words || []
  if (words.length === 0) return null
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-16 border-2 border-warn/40 bg-warn-tint p-4" role="status" aria-live="polite">
      <p className="text-[15px] font-bold text-warn-text">
        {feedback.correct_words > 0 ? `${feedback.total_words}낱말 중 ${feedback.correct_words}낱말을 맞혔어요` : '조금 더 볼까요?'}
      </p>
      <p className="mt-1 text-[13px] text-ink-muted">
        맞힌 낱말은 그대로, 틀린 낱말은 글자마다 첫 자음만 보여요. 입모양을 다시 보고 한 번 더 적어 보세요.
      </p>
      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2">
        {words.map((w, i) => (w.correct ? (
          <span key={i} className="rounded-lg bg-white px-2 py-1 text-[18px] font-bold text-good-text">{w.text}</span>
        ) : (
          <span key={i} className="flex gap-1" aria-label={`틀린 낱말, 첫 자음 ${w.skeleton.join(' ')}`}>
            {w.skeleton.map((ch, j) => (
              <span key={j} className="flex size-8 items-center justify-center rounded-md border-2 border-warn/40 bg-white text-[16px] font-bold text-ink">
                {ch}
              </span>
            ))}
          </span>
        )))}
      </div>
    </motion.div>
  )
}
