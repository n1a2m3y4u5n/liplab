import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import useStore from '../store/useStore'

/**
 * 프로필 탭 (Figma 리디자인 05) — 내 프로필(그라데이션) + 통계 + 설정 메뉴 + 로그아웃.
 * 이름·레벨·XP는 useStore. 메뉴는 기존 화면으로 이동한다.
 */
function StatCol({ icon, label, value, color }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1.5 py-1.5">
      <div className="flex items-center gap-1.5">
        <img src={icon} alt="" className="h-[18px] w-[18px]" />
        <span className="text-[13px] font-bold text-[#7a7a8c]">{label}</span>
      </div>
      <span className="text-[27px] font-bold tracking-[-0.68px]" style={{ color }}>{value}</span>
    </div>
  )
}

function MenuRow({ title, sub, onClick, first }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full items-center justify-between px-[22px] py-[18px] text-left hover:bg-gray-50 ${first ? '' : 'border-t-[1.5px] border-line'}`}>
      <span className="flex flex-col gap-0.5">
        <span className="text-[16px] font-bold text-ink">{title}</span>
        <span className="text-[13px] text-ink-muted">{sub}</span>
      </span>
      <img src="/ui/menu-arrow.svg" alt="" className="h-3.5 w-[7px]" />
    </button>
  )
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const logout = useStore((s) => s.logout)
  const [note, setNote] = useState('')

  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const xp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const PER = 500
  const inLevel = xp % PER
  const name = user?.username || '게스트'
  const days = Math.max(0, user?.streak_count || statistics?.days_learned || 0)
  const lessons = statistics?.lessons_completed ?? statistics?.completed_lessons ?? '—'

  const soon = (t) => setNote(`${t}은(는) 준비 중이에요.`)

  return (
    <AppShell active="profile" title="프로필">
      {/* 내 프로필 */}
      <section className="relative w-full overflow-hidden rounded-[22px] border-2 border-b-[5px] border-[#6d3fc4] p-6 sm:p-8"
        style={{ backgroundImage: 'linear-gradient(166deg, #a78bfa 0%, #7d53de 71%)' }}>
        <div className="flex items-center gap-6">
          <div className="flex h-[100px] w-[100px] shrink-0 items-center justify-center rounded-full border-4 border-white/90 bg-white/20 text-4xl font-black text-white shadow-lg">
            {name[0]}
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            <div className="flex items-center gap-2.5">
              <span className="truncate text-[26px] font-bold tracking-[-0.52px] text-white">{name}</span>
              <span className="shrink-0 rounded-full bg-white/25 px-3 py-1 text-[13px] font-bold text-white">Lv.{level}</span>
            </div>
            <div className="flex justify-between text-[13px] font-bold text-white">
              <span className="opacity-85">다음 레벨까지</span>
              <span>{inLevel.toLocaleString()} / {PER} XP</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-white/30">
              <div className="h-full rounded-full bg-white" style={{ width: `${(inLevel / PER) * 100}%` }} />
            </div>
          </div>
        </div>
      </section>

      {/* 통계 */}
      <section className="flex w-full items-center py-2">
        <StatCol icon="/ui/stat-calendar.svg" label="학습한 날" value={`${days}일`} color="#5f3ab8" />
        <span className="h-[46px] w-px bg-line" />
        <StatCol icon="/ui/stat-check.svg" label="완료한 레슨" value={typeof lessons === 'number' ? `${lessons}개` : lessons} color="#047857" />
        <span className="h-[46px] w-px bg-line" />
        <StatCol icon="/ui/stat-starplus.svg" label="누적 XP" value={xp.toLocaleString()} color="#b45309" />
      </section>

      {/* 설정 */}
      <section className="card-flat w-full !p-0">
        <MenuRow first title="사용법 가이드" sub="처음이라면 여기부터" onClick={() => navigate('/guide')} />
        <MenuRow title="자가진단 다시 하기" sub="지금 수준으로 단계 재추천" onClick={() => navigate('/learn/placement')} />
        <MenuRow title="알림 설정" sub="학습 리마인더 시간" onClick={() => soon('알림 설정')} />
        <MenuRow title="계정 설정" sub="이름·이메일·비밀번호" onClick={() => soon('계정 설정')} />
      </section>
      {note && <p className="w-full text-center text-[13px] text-ink-muted">{note}</p>}

      <button type="button" onClick={() => { logout(); navigate('/dashboard') }}
        className="w-full rounded-2xl border-2 border-b-[5px] border-line bg-white py-4 text-[15px] font-bold text-ink-muted transition-all active:translate-y-[3px] active:border-b-2">
        로그아웃
      </button>
    </AppShell>
  )
}
