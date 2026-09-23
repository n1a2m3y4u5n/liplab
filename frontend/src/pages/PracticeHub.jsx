import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'

/**
 * 연습 탭 허브 (Figma 96:14 · 모바일 238:34) — 단계와 무관하게 자유롭게 고르는 연습 모드 카드.
 * 각 카드는 기존 연습 화면으로 연결한다. 탭 제목 아래 설명 문구는 없다(§4-05).
 * 카드: lg 이상은 세로형(96:125 — 52px 칩·19px 제목·설명), lg 미만은 가로 행(238:125 — 44px 칩·제목/설명·화살표).
 * 6번째 칸은 '공사 중' 카드(98:15, 데스크톱 전용 — 모바일 238:34에는 없다).
 */
const CARDS = [
  { key: 'multi', title: '다자 대화', desc: '여러 사람이 주고받는 대화를 읽어요', icon: '/ui/card-multi.svg', chip: '#e0f2fe', to: '/learn/conversation-multi' },
  { key: 'free', title: '자유 발화', desc: '내가 쓴 문장을 소리 내어 확인해요', icon: '/ui/card-free.svg', chip: '#ffe4e9', to: '/pronounce' },
  { key: 'scenario', title: '상황별 시나리오', desc: '카페·병원 등 상황을 골라 연습해요', icon: '/ui/card-scenario.svg', chip: '#fff3d6', to: '/learn/scenario' },
  { key: 'sign', title: '수어 함께 보기', desc: '문장을 수어로도 확인할 수 있어요', icon: '/ui/card-sign.svg', chip: '#dff7ec', to: '/learn/sign' },
  { key: 'endless', title: '엔드리스 학습', desc: '틀렸던 유형이 계속 나와요', icon: '/ui/tab-card-endless.svg', chip: '#e0e7ff', to: '/learn/endless' },
]

function PracticeCard({ card, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-3.5 rounded-16 border-2 border-b-5 border-line bg-white p-4 text-left transition-transform hover:-translate-y-0.5 lg:flex-col lg:items-start lg:rounded-20 lg:px-[22px] lg:py-6"
    >
      <span className="icon-chip-sm lg:icon-chip" style={{ backgroundColor: card.chip }}>
        <img src={card.icon} alt="" className="size-[22px] lg:size-6" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-[3px] leading-figma lg:gap-3.5">
        <span className="text-[16px] font-bold text-ink lg:text-[19px] lg:tracking-[-0.38px]">{card.title}</span>
        <span className="text-[12.5px] text-ink-muted lg:text-[14px] lg:leading-[1.65]">{card.desc}</span>
      </span>
      {/* 모바일 행 화살표(238:131 = review-arrow, 6×12 칸에 8×14 에셋) */}
      <span aria-hidden className="relative h-3 w-1.5 shrink-0 lg:hidden">
        <img src="/ui/review-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
      </span>
    </button>
  )
}

// 공사 중 간판(98:62)의 줄무늬 빗금 — Figma Hatch 14개(6×20, 35° 회전, 14px 간격)를 그대로 배치.
const HATCHES = Array.from({ length: 14 }, (_, i) => -25.47 + i * 14)

function Stripe({ top }) {
  return (
    <span aria-hidden className="absolute left-[-3px] h-2 w-[158px] overflow-hidden bg-amber-800" style={{ top }}>
      {HATCHES.map((left) => (
        <span key={left} className="absolute top-[-5px] flex h-[19.824px] w-[16.386px] items-center justify-center" style={{ left }}>
          <span className="h-5 w-1.5 rotate-[35deg] bg-amber-200" />
        </span>
      ))}
    </span>
  )
}

/**
 * 공사 중 카드(Figma 98:15 "Practice card / 준비 중") — 누를 수 없는 자리 카드.
 * 보라 그라데이션 3D 카드 위에 DOKA(98:16 = mascot.svg, 74px·4° 회전) + 기둥 2개(98:60/61) + 간판(98:62).
 * 그림 묶음(158×126)은 Figma 좌표 그대로 카드 안쪽(테두리 제외 364×174) 가운데에서 2px 아래에 둔다.
 */
function ConstructionCard() {
  return (
    <div className="relative hidden min-h-[181px] overflow-hidden rounded-20 border-2 border-b-5 border-primary-600 lg:block"
      style={{ backgroundImage: 'linear-gradient(159.75deg, #c4b5fd 0%, #8b5cf6 71.429%)' }}>
      <div className="absolute h-[126px] w-[158px]" style={{ left: 'calc(50% - 79px)', top: 'calc(50% - 61px)' }}>
        {/* DOKA — 회전 전 74px, 그림자 여백 inset -7% -12% -17% -12% */}
        <span aria-hidden className="absolute left-[38.84px] top-0 flex size-[78.98px] items-center justify-center">
          <span className="relative size-[74px] rotate-[4deg]">
            <img src="/ui/mascot.svg" alt="" className="absolute max-w-none" style={{ top: '-7%', left: '-12%', width: '124%', height: '124%' }} />
          </span>
        </span>
        {/* 기둥 */}
        <span aria-hidden className="absolute left-[31.5px] top-[86px] h-10 w-[11px] rounded-[3px] bg-yellow-700" />
        <span aria-hidden className="absolute left-[115.5px] top-[86px] h-10 w-[11px] rounded-[3px] bg-yellow-700" />
        {/* 간판 */}
        <div className="absolute left-0 top-12 h-[46px] w-[158px] overflow-hidden rounded-10 border-[3px] border-amber-700 bg-amber-400 shadow-[0px_5px_10px_-2px_rgba(51,26,0,0.28)]">
          <Stripe top={-3} />
          <Stripe top={35} />
          <p className="absolute inset-0 flex items-center justify-center text-[19px] font-bold leading-figma text-orange-900">공사 중</p>
        </div>
      </div>
    </div>
  )
}

export default function PracticeHub() {
  const navigate = useNavigate()
  return (
    <AppShell active="practice" title="연습">
      <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2 lg:gap-4">
        {CARDS.map((c) => (
          <PracticeCard key={c.key} card={c} onClick={() => navigate(c.to)} />
        ))}
        <ConstructionCard />
      </div>
    </AppShell>
  )
}
