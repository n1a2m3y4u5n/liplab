import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'

/**
 * 연습 탭 허브 (Figma 리디자인 05) — 단계와 무관하게 자유롭게 고르는 연습 모드 카드.
 * 각 카드는 기존 연습 화면으로 연결한다. 파스텔 아이콘칩 + 3D 카드(디자인 토큰).
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
      className="card flex flex-col items-start gap-3.5 text-left transition-transform hover:-translate-y-0.5"
    >
      <span className="icon-chip" style={{ backgroundColor: card.chip }}>
        <img src={card.icon} alt="" className="h-6 w-6" />
      </span>
      <span className="text-[19px] font-bold tracking-[-0.38px] text-ink">{card.title}</span>
      <span className="text-sm leading-relaxed text-ink-muted">{card.desc}</span>
    </button>
  )
}

export default function PracticeHub() {
  const navigate = useNavigate()
  return (
    <AppShell active="practice" title="연습" description="단계와 상관없이 언제든 자유롭게 연습할 수 있어요.">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {CARDS.map((c) => (
          <PracticeCard key={c.key} card={c} onClick={() => navigate(c.to)} />
        ))}
      </div>
    </AppShell>
  )
}
