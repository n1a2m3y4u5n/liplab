import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { reviewAPI } from '../../api'

// 대시보드 좌측 학습자 카드 — 레벨·XP 링, 연속 학습, 오늘의 과제
export default function LearnerProfileCard({ user, statistics, calendarData }) {
  const navigate = useNavigate()
  const [dueReviewCount, setDueReviewCount] = useState(null)

  useEffect(() => {
    let active = true
    reviewAPI.getDue()
      .then((data) => {
        if (active) setDueReviewCount((data?.items || []).length)
      })
      .catch(() => {
        if (active) setDueReviewCount(null)
      })
    return () => { active = false }
  }, [])

  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const totalXp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const levelStartXp = 100 * ((level - 1) ** 2)
  const nextLevelXp = 100 * (level ** 2)
  const usesLevelBand = totalXp >= levelStartXp
  const earnedThisLevel = usesLevelBand ? totalXp - levelStartXp : totalXp
  const xpNeededThisLevel = usesLevelBand ? nextLevelXp - levelStartXp : nextLevelXp
  const remainingXp = Math.max(0, xpNeededThisLevel - earnedThisLevel)
  const xpPercent = Math.min(100, Math.max(0, (earnedThisLevel / Math.max(1, xpNeededThisLevel)) * 100))
  const streak = Math.max(0, user?.streak_count || 0)
  // 활동 캘린더·백엔드가 UTC 날짜 키를 쓰므로 '오늘' 판정도 UTC로 통일(시간대 경계 불일치 방지)
  const todayKey = new Date().toISOString().slice(0, 10)
  const todaySessions = Number(calendarData?.[todayKey] || 0)
  const displayName = user?.username || 'LIPLAB 학습자'
  const initial = displayName.trim().slice(0, 1).toUpperCase() || 'L'
  const tasks = [
    {
      id: 'review',
      label: '오늘의 복습 정리',
      detail: dueReviewCount == null ? '복습 항목 확인하기' : dueReviewCount > 0 ? `${dueReviewCount}개가 기다리고 있어요` : '오늘 복습을 모두 정리했어요',
      completed: dueReviewCount === 0,
      to: '/review/today',
    },
    {
      id: 'practice',
      label: '독화 학습 1회',
      detail: todaySessions >= 1 ? '첫 학습을 완료했어요' : '짧게 시작해도 좋아요',
      completed: todaySessions >= 1,
      to: '/learn/scenario',   // 완료 판정(문장 Progress)과 링크를 일치시킴
    },
    {
      id: 'challenge',
      label: '오늘의 학습 2회 채우기',
      detail: `${Math.min(todaySessions, 2)} / 2회 완료`,
      completed: todaySessions >= 2,
      to: '/learn/scenario',
    },
  ]

  return (
    <aside
      className="flex h-full min-h-[460px] flex-col overflow-hidden rounded-[24px] border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-4 shadow-[0_16px_45px_rgba(15,23,42,0.08)] lg:min-h-0"
      aria-labelledby="learner-profile-heading"
    >
      <div className="flex items-center gap-3">
        <div
          className="relative grid h-[102px] w-[102px] shrink-0 place-items-center rounded-full p-[6px] shadow-[0_12px_28px_rgba(101,163,13,0.2)]"
          style={{ background: `conic-gradient(#84cc16 0% ${xpPercent}%, #e2e8f0 ${xpPercent}% 100%)` }}
          role="progressbar"
          aria-label={`레벨 ${level} 경험치`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(xpPercent)}
        >
          <div className="grid h-full w-full place-items-center rounded-full bg-white p-1">
            <div className="grid h-full w-full place-items-center rounded-full bg-gradient-to-br from-sky-100 via-cyan-50 to-lime-100 text-3xl font-black text-sky-700 ring-1 ring-sky-100">
              {initial}
            </div>
          </div>
          <span className="absolute -bottom-1 rounded-full bg-slate-950 px-2.5 py-0.5 text-[9px] font-black text-white shadow-lg">
            {Math.round(xpPercent)}%
          </span>
        </div>

        <div className="min-w-0 flex-1 text-left">
          <p className="text-[9px] font-black tracking-[0.14em] text-lime-700">MY PROFILE</p>
          <h2 id="learner-profile-heading" className="mt-1 truncate text-lg font-black tracking-tight text-slate-950">{displayName}</h2>
          <span className="mt-0.5 block text-sm font-black text-sky-600">Lv {level}</span>
          <p className="mt-1 text-[10px] font-bold leading-tight text-slate-500">다음 레벨까지<br /><b className="text-slate-800">{remainingXp.toLocaleString()} XP</b></p>
          <div className="mt-2 flex items-center justify-between text-[8px] font-bold text-slate-400">
            <span>{earnedThisLevel.toLocaleString()}</span>
            <span>/ {xpNeededThisLevel.toLocaleString()} XP</span>
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-2xl border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 px-2.5 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span aria-hidden="true" className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-orange-500 text-sm shadow-sm">🔥</span>
            <div className="min-w-0 text-left">
              <p className="truncate text-xs font-black text-amber-950">{streak}일 연속 학습</p>
              <p className="text-[9px] font-medium text-amber-700">오늘도 기록을 이어가세요</p>
            </div>
          </div>
          <div className="flex shrink-0 gap-1" aria-label={`최근 연속 학습 ${streak}일`}>
            {Array.from({ length: 7 }, (_, index) => (
              <span
                key={index}
                className={`h-2 w-2 rounded-full ${index < Math.min(streak, 7) ? 'bg-orange-500' : 'bg-amber-200'}`}
                aria-hidden="true"
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex min-h-0 flex-1 flex-col rounded-[18px] bg-slate-50 p-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-black text-slate-900">오늘의 과제</h3>
          <span className="rounded-full bg-lime-100 px-2 py-1 text-[9px] font-black text-lime-700">
            {tasks.filter((task) => task.completed).length}/{tasks.length} 완료
          </span>
        </div>
        <ul className="mt-2 space-y-1">
          {tasks.map((task) => (
            <li key={task.id}>
              <button
                type="button"
                onClick={() => navigate(task.to)}
                className="group flex w-full items-center gap-2 rounded-xl bg-white px-2 py-1.5 text-left ring-1 ring-slate-100 transition hover:-translate-y-0.5 hover:ring-lime-300 focus:outline-none focus:ring-2 focus:ring-lime-400"
              >
                <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-md text-[10px] font-black ${task.completed ? 'bg-lime-500 text-white' : 'border-2 border-slate-300 bg-white text-transparent'}`} aria-hidden="true">
                  ✓
                </span>
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-[11px] font-black ${task.completed ? 'text-slate-500 line-through' : 'text-slate-800'}`}>{task.label}</span>
                  <span className="block truncate text-[9px] font-medium text-slate-400">{task.detail}</span>
                </span>
                <span aria-hidden="true" className="text-xs font-black text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-lime-600">›</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
