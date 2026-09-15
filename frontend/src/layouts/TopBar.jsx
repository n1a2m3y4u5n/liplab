import { Link } from 'react-router-dom'
import useStore from '../store/useStore'

// 전역 상단 바(리디자인 스펙 2.2) — 로고 · 스트릭 · XP/레벨 · 캐릭터 미니 위젯 자리.
// 데이터는 useStore의 user(AuthGate가 /auth/me로 동기화)에서만 읽는다 — 새 API 호출을 만들지 않는다.
// 비주얼은 Figma 확정 전까지 구조 고정용 최소 스타일.
export default function TopBar() {
  const user = useStore((s) => s.user)
  const streak = user?.streak_count ?? 0
  const level = user?.current_level ?? 1
  const xp = user?.total_xp ?? 0

  return (
    <div className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-[1440px] items-center gap-4 px-4 py-2 sm:px-6">
        <Link to="/dashboard" className="text-lg font-black tracking-tight text-slate-900">LIPLAB</Link>

        <div className="ml-auto flex items-center gap-3 text-sm font-bold text-slate-700">
          <span title="연속 학습일">🔥 {streak}일</span>
          <span title="레벨 · 누적 경험치">Lv.{level} · {xp.toLocaleString()} XP</span>
          {/* 캐릭터 미니 위젯 자리 — 디자인 확정 후 실제 캐릭터로 교체 */}
          <span aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-full bg-sky-100">🙂</span>
        </div>
      </div>
    </div>
  )
}
