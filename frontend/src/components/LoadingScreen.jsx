/**
 * 로딩 / 스플래시 (Figma 리디자인 08 로딩).
 * variant='plain'(기본, Figma "로딩/기본 데스크톱") — 흰 배경 + 마스코트 + 라벨 + 점 3개: 라우트 전환 대기.
 * variant='brand' (Figma "로딩/독화·발화") — 브랜드 그라데이션 + 헤일로 마스코트 + 점 + 팁 카드: 첫 진입/스플래시.
 *   track='perception'(보라, 기본) | 'language'(핑크)로 그라데이션·팁을 전환한다.
 */
const TRACK_UI = {
  // Figma 그라데이션 값 그대로(151.9deg, 3-stop).
  perception: {
    gradient: 'linear-gradient(151.93deg, #a78bfa 0%, #8b5cf6 39.286%, #6d3fc4 71.429%)',
    badge: 'TMI',
    tip: ['LIPLAB의 마스코트는', '비교적 오랫동안 디자인 했어요.'],
  },
  language: {
    gradient: 'linear-gradient(151.93deg, #fb7185 0%, #ec4899 39.286%, #be185d 71.429%)',
    badge: '학습 팁',
    tip: ['발화 학습 때 크게 말해보세요.', '점수뿐만 아니라 자신감도 올라갈 거예요!'],
  },
}

// 점 3개(Figma Dots) — 순차 펄스.
function Dots({ className = 'bg-primary-500' }) {
  return (
    <div className="flex gap-[7px]">
      {[0, 1, 2].map((i) => (
        <span key={i} className={`h-[9px] w-[9px] animate-pulse rounded-full ${className}`} style={{ animationDelay: `${i * 180}ms` }} />
      ))}
    </div>
  )
}

export default function LoadingScreen({ label = '로딩 중', variant = 'plain', track = 'perception' }) {
  if (variant === 'plain') {
    // Figma "로딩 / 기본 (데스크톱)": 흰 배경, 마스코트 170px, 라벨 22px, 점 3개.
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-[37px] bg-white">
        <img src="/ui/mascot.svg" alt="" className="h-[150px] w-[150px]" />
        <p className="text-[22px] font-bold tracking-[-0.33px] text-ink-muted">{label}</p>
        <Dots />
      </div>
    )
  }

  const ui = TRACK_UI[track] || TRACK_UI.perception
  return (
    <div className="relative flex min-h-[100dvh] flex-col items-center justify-center overflow-hidden px-6"
      style={{ backgroundImage: ui.gradient }}>
      {/* 배경 블롭 2개 */}
      <div className="pointer-events-none absolute -left-40 -top-28 h-[520px] w-[520px] rounded-full bg-white/10" />
      <div className="pointer-events-none absolute -right-24 -bottom-24 h-[420px] w-[420px] rounded-full bg-white/10" />

      <div className="relative flex flex-col items-center gap-[34px]">
        {/* 헤일로 + 밝은 마스코트 */}
        <span className="flex h-[200px] w-[200px] items-center justify-center rounded-full bg-white/[0.16]">
          <img src="/ui/onb-mascot-light.svg" alt="" className="h-[150px] w-[150px]" />
        </span>
        <Dots className="bg-white/90" />
        {/* 팁 카드 */}
        <div className="flex w-full max-w-[560px] flex-col items-center gap-3 rounded-[20px] border-2 border-white/30 bg-white/[0.18] px-[30px] py-6">
          <span className="rounded-full bg-white/30 px-3.5 py-1.5 text-[12px] font-bold tracking-[0.24px] text-white">{ui.badge}</span>
          <p className="text-center text-[19px] font-bold leading-[1.65] tracking-[-0.285px] text-white">
            {ui.tip[0]}<br />{ui.tip[1]}
          </p>
        </div>
      </div>
    </div>
  )
}
