// 지금 입모양을 보이는 가상 화자 표시(커리큘럼 계획 2-2). 아바타 카드 왼쪽 위의 작은 글자 하나만 둔다.
export default function TalkerChip({ talker }) {
  if (!talker) return null
  return (
    <span className="pointer-events-none absolute left-2 top-2 z-10 rounded-full bg-black/45 px-2 py-0.5 text-[11px] font-bold leading-4 text-white/90">
      {talker.label}
    </span>
  )
}
