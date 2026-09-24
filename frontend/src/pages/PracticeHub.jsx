import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'

/**
 * 연습 탭 허브 (Figma 96:14 · 모바일 238:34) — 단계와 무관하게 자유롭게 고르는 연습 모드 카드.
 * 각 카드는 기존 연습 화면으로 연결한다. 탭 제목 아래 설명 문구는 없다(§4-05).
 * 카드: lg 이상은 세로형(96:125 — 52px 칩·19px 제목·설명), lg 미만은 가로 행(238:125 — 44px 칩·제목/설명·화살표).
 * 6번째 칸은 Figma의 '공사 중' 자리(98:15)에 '입모양 교실'을 둔다 — 웹캠 따라 하기·조음 교정·아바타 거울·
 * 성도 실험(축 D·E·F·K)이 모인 입모양 학습 자료(/learn/viseme?tab=learn)로, 다른 진입점이 없던 화면이다.
 */
const CARDS = [
  { key: 'multi', title: '다자 대화', desc: '여러 사람이 주고받는 대화를 읽어요', icon: '/ui/card-multi.svg', chip: 'bg-pastel-sky', to: '/learn/conversation-multi' },
  { key: 'free', title: '자유 발화', desc: '내가 쓴 문장을 소리 내어 확인해요', icon: '/ui/card-free.svg', chip: 'bg-pastel-pink', to: '/pronounce' },
  { key: 'scenario', title: '상황별 시나리오', desc: '카페·병원 등 상황을 골라 연습해요', icon: '/ui/card-scenario.svg', chip: 'bg-pastel-amber', to: '/learn/scenario' },
  { key: 'sign', title: '수어 함께 보기', desc: '문장을 수어로도 확인할 수 있어요', icon: '/ui/card-sign.svg', chip: 'bg-pastel-mint', to: '/learn/sign' },
  { key: 'endless', title: '엔드리스 학습', desc: '틀렸던 유형이 계속 나와요', icon: '/ui/tab-card-endless.svg', chip: 'bg-pastel-indigo', to: '/learn/endless' },
  { key: 'mouth', title: '입모양 교실', desc: '웹캠으로 따라 하고 안 보이는 혀 위치도 확인해요', icon: '/ui/nav-learn.svg', chip: 'bg-pastel-violet', to: '/learn/viseme?tab=learn' },
]

function PracticeCard({ card, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-3.5 rounded-16 border-2 border-b-5 border-line bg-white p-4 text-left transition-transform hover:-translate-y-0.5 lg:flex-col lg:items-start lg:rounded-20 lg:px-[22px] lg:py-6"
    >
      <span className={`icon-chip-sm lg:icon-chip ${card.chip}`}>
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

export default function PracticeHub() {
  const navigate = useNavigate()
  return (
    <AppShell active="practice" title="연습">
      <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2 lg:gap-4">
        {CARDS.map((c) => (
          <PracticeCard key={c.key} card={c} onClick={() => navigate(c.to)} />
        ))}
      </div>
    </AppShell>
  )
}
