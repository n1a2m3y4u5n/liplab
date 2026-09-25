// 팀원 아바타 60px. 사진이 있으면 사진, 없으면 연보라 원 안의 DOKA(Figma 372:98). 가이드 11번 탭과 랜딩이 함께 쓴다.
const MASCOT_OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }

export default function TeamAvatar({ m }) {
  if (m.photo) return <img src={m.photo} alt="" className="size-[60px] shrink-0 rounded-full object-cover" />
  return (
    <span aria-hidden className="relative size-[60px] shrink-0 overflow-hidden rounded-full bg-primary-100">
      <span className="absolute left-[9px] top-[10px] size-[42px]">
        <img src="/ui/lp-372-98-guide-mascot.svg" alt="" className="absolute max-w-none" style={MASCOT_OVERFLOW} />
      </span>
    </span>
  )
}
