import { useState } from 'react'
import { splitFirstSentence } from '../lib/learnerProfile'

/**
 * 짧은 힌트(계획 2-6): short이면 첫 문장만 먼저 보이고 나머지는 '더 보기'로 펼친다. 내용은 줄이지 않는다.
 * 선천·아동기 손실로 답한 학습자의 기본값이다(lib/learnerProfile.learnerDefaults). short가 아니면 글 전체를 그대로 보인다.
 */
export default function ShortText({ text, short, className = '' }) {
  const [open, setOpen] = useState(false)
  if (!short) return <span className={className}>{text}</span>
  const { first, rest } = splitFirstSentence(text)
  return (
    <span className={className}>
      {first}
      {rest && (open
        ? <> {rest}</>
        : <> <button type="button" onClick={() => setOpen(true)} className="font-bold text-track underline underline-offset-2">더 보기</button></>)}
    </span>
  )
}
