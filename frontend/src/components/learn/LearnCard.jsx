import { PRACTICE_MODES } from '../../lib/listenFlow'
// 소리 듣기 카드 그림(24px 선 그림, 청록). 그림 파일 대신 currentColor로 그려 트랙색을 따른다
const LISTEN_ICON = {
  contrast: <><path d="M4 9v6M8 6v12M12 9v6" /><path d="M16 7v10M20 10v4" opacity="0.55" /></>,
  dictation: <><path d="M4 18h9M4 13h12M4 8h16" /><path d="m17 19 4-4-2-2-4 4v2z" /></>,
  noise_endless: <><path d="M3 12h2l2-5 3 10 3-8 2 5 2-2h4" /></>,
  scenario: <><path d="M12 21s-6-5.5-6-10.5a6 6 0 0 1 12 0C18 15.5 12 21 12 21z" /><circle cx="12" cy="10.5" r="2" /></>,
  conditions: <><path d="M6 4h3l1.5 4-2 1.5a10 10 0 0 0 6 6l1.5-2 4 1.5V18a2 2 0 0 1-2 2A15 15 0 0 1 4 6a2 2 0 0 1 2-2z" /></>,
  classroom: <><path d="M4 6.5C4 5.7 4.7 5 5.5 5H11v14H5.5A1.5 1.5 0 0 1 4 17.5zM20 6.5c0-.8-.7-1.5-1.5-1.5H13v14h5.5c.8 0 1.5-.7 1.5-1.5z" /></>,
}
export const LISTEN_CARDS = [
  ...['contrast', 'dictation', 'noise_endless', 'scenario', 'conditions'].map((k) => ({ key: k, title: PRACTICE_MODES[k].title, desc: PRACTICE_MODES[k].desc, to: `/listen/practice/${k}` })),
  { key: 'classroom', title: '소리 교실', desc: '소리 짝을 여러 목소리로 들어 봐요', to: '/listen/classroom' },
]

function CardIcon({ card }) {
  if (card.icon) return <img src={card.icon} alt="" className="size-[22px] lg:size-6" />
  return (
    <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className="size-[22px] text-listen-dark lg:size-6">
      {LISTEN_ICON[card.key]}
    </svg>
  )
}

export function LearnCard({ card, onClick, off = null }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!!off}
      className="flex items-center gap-3.5 rounded-16 border border-line bg-white p-4 text-left transition-colors enabled:hover:border-line-strong enabled:hover:bg-surface-muted disabled:cursor-not-allowed lg:flex-col lg:items-start lg:px-[22px] lg:py-6"
    >
      {/* 11/03: 아이콘 칸은 카드마다 다른 파스텔 대신 중립 회색 한 가지(card.chip 값은 데이터에 남겨 두고 여기서는 쓰지 않는다) */}
      <span className={`icon-chip-sm lg:icon-chip bg-surface-sunken ${off ? 'opacity-50 grayscale' : ''}`}>
        <CardIcon card={card} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-[3px] leading-figma lg:gap-3.5">
        <span className={`text-[16px] font-semibold lg:text-[18px] lg:tracking-[-0.36px] ${off ? 'text-ink-muted' : 'text-ink'}`}>
          {card.title}{off && <span className="ml-2 align-middle text-[12px] font-bold text-ink-faint lg:text-[13px]">잠김</span>}
        </span>
        <span className="text-[13px] text-ink-muted lg:text-[14px] lg:leading-[1.6]">{typeof off === 'string' ? off : card.desc}</span>
      </span>
      {/* 모바일 행 화살표(238:131 = review-arrow, 6×12 칸에 8×14 에셋) */}
      <span aria-hidden className={`relative h-3 w-1.5 shrink-0 lg:hidden ${off ? 'opacity-0' : ''}`}>
        <img src="/ui/review-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
      </span>
    </button>
  )
}

