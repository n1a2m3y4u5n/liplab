import { useEffect, useState } from 'react'
import { learningAPI } from '../api'
import MouthAvatar from './MouthAvatar'

/**
 * 최소대립쌍 A/B 아바타(CLAUDE.md 트랙 2 백로그, 9/28): 틀린 문항에서 정답 단어와 내가 고른 단어의 입모양을 두 아바타로 나란히
 * 재생해 어디가 다른지(또는 원래 같은지) 눈으로 비교한다. WebGL 화면이 둘 늘어나므로 누를 때만 연다(WordStage).
 * sameLooking이면 두 입모양이 같은 무리라 입만으로는 가를 수 없다고 알린다.
 */
export default function MouthCompare({ target, chosen, sameLooking = false }) {
  const [frames, setFrames] = useState({})
  useEffect(() => {
    let alive = true
    for (const w of [target, chosen]) {
      learningAPI.getVisemes(w).then((f) => { if (alive) setFrames((p) => ({ ...p, [w]: f })) }).catch(() => {})
    }
    return () => { alive = false }
  }, [target, chosen])
  const col = (word, label, tone) => (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
      <p className={`text-[12px] font-bold ${tone}`}>{label} <span className="text-[15px]">{word}</span></p>
      <div className="h-[132px] overflow-hidden rounded-14 lg:h-[160px]">
        <MouthAvatar frames={frames[word] || []} height={null} className="h-full" />
      </div>
    </div>
  )
  return (
    <div className="space-y-2 rounded-16 border-2 border-line bg-white p-3">
      <div className="flex gap-3">
        {col(target, '정답', 'text-good-text')}
        {col(chosen, '내가 고른 말', 'text-bad-text')}
      </div>
      <p className="text-[12.5px] leading-snug text-ink-muted">
        {sameLooking
          ? '두 말은 입모양이 같은 무리라 입만 보고는 가를 수 없어요. 앞뒤 문맥으로 고르는 연습이 필요해요.'
          : '두 입모양이 달라지는 순간을 비교해 보세요. 반복해서 재생돼요.'}
      </p>
    </div>
  )
}
