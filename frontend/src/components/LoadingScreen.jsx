/**
 * 로딩 / 스플래시 (Figma 리디자인 08 로딩 · 브랜드 스플래시).
 * variant='plain'(기본) — 흰 배경 + 보라 스피너: 라우트 전환 대기.
 * variant='brand' — 보라 그라데이션 + 마스코트 + 워드마크 + 태그라인: 첫 진입/스플래시.
 */
export default function LoadingScreen({ label = '불러오는 중…', variant = 'plain' }) {
  if (variant === 'plain') {
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-5 bg-gray-50">
        <div className="relative flex h-24 w-24 items-center justify-center">
          <span className="absolute inset-0 animate-spin rounded-full border-4 border-primary-100 border-t-primary-500" />
          <img src="/ui/mascot.svg" alt="" className="h-14 w-14" />
        </div>
        <p className="text-[15px] font-bold text-ink-muted">{label}</p>
      </div>
    )
  }
  return (
    <div className="relative flex min-h-[100dvh] flex-col items-center justify-center overflow-hidden"
      style={{ backgroundImage: 'linear-gradient(160deg, #a78bfa 0%, #7d53de 72%)' }}>
      <div className="pointer-events-none absolute -left-16 top-24 h-64 w-64 rounded-full bg-white/10" />
      <div className="pointer-events-none absolute -right-10 bottom-16 h-72 w-72 rounded-full bg-white/10" />
      <div className="relative flex flex-col items-center gap-5 px-8 text-center">
        <span className="flex h-24 w-24 items-center justify-center rounded-[30px] bg-white/25 shadow-xl">
          <img src="/ui/mascot.svg" alt="" className="h-14 w-14" />
        </span>
        <span className="font-display text-[34px] leading-none tracking-[-1px] text-white">LIPLAB</span>
        <p className="text-[15px] font-medium leading-snug text-white/90">입모양이 보이기 시작하는 순간까지</p>
        <div className="mt-2 flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-white/80" style={{ animationDelay: `${i * 180}ms` }} />
          ))}
        </div>
      </div>
    </div>
  )
}
