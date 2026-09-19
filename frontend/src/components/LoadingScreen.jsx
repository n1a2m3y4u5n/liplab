/**
 * 로딩 화면 (Figma 리디자인 08) — 라우트 전환·데모 로그인 대기 시 표시.
 * 마스코트 + 보라 스피너 + 문구. 디자인 토큰만 사용(브랜드 일관).
 */
export default function LoadingScreen({ label = '불러오는 중…' }) {
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
