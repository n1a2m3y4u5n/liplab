import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import useStore from '../store/useStore'
import { reviewAPI } from '../api'

/**
 * 과제 탭 (Figma 리디자인 05) — 일일 과제 진행/보상 + 주간 도전 + 배지.
 * 게이미피케이션 화면(전용 백엔드 없음): 스트릭/레벨은 useStore, 복습수는 reviewAPI에서 읽고
 * 과제/배지는 그 값으로부터 파생해 표시한다.
 */
function TaskRow({ label, cur, total, xp }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3.5">
      {done ? (
        <img src="/ui/task-done.svg" alt="" className="h-[26px] w-[26px]" />
      ) : (
        <span className="h-[26px] w-[26px] shrink-0 rounded-full border-2 border-line" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
        <div className="flex items-center justify-between text-[15px] font-bold">
          <span className="text-ink">{label}</span>
          <span className="text-[13px] text-primary-500">{cur} / {total}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#ededf3]">
          <div className="h-full rounded-full bg-primary-500" style={{ width: `${Math.min(100, (cur / total) * 100)}%` }} />
        </div>
      </div>
      <span className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold ${done ? 'bg-primary-100 text-primary-700' : 'bg-[#f3f3f7] text-[#8a8a9b]'}`}>+{xp} XP</span>
    </div>
  )
}

// desc: 배지 획득 조건 한 줄 설명, percent: 전체 사용자 중 획득 비율(게이미피케이션 카피)
// 정확도 90% 배지의 desc/percent는 Figma 313:33 확정값. 나머지는 라벨에 맞춰 작성.
const BADGES = [
  { label: '첫 걸음', icon: '/ui/medal-0.svg', earned: true, desc: '첫 학습을 마치고 여정을 시작하기', percent: 63 },
  { label: '7일 연속', icon: '/ui/medal-1.svg', earned: true, desc: '이레 동안 하루도 빠짐없이 학습하기', percent: 34 },
  { label: '입모양 마스터', icon: '/ui/medal-2.svg', earned: true, desc: '모든 입모양 그룹을 완벽하게 익히기', percent: 21 },
  { label: '정확도 90%', shape: 'check', earned: true, desc: '한 레슨에서 정확도 90% 이상을 달성하기', percent: 8 },
  { label: '100문제 돌파', icon: '/ui/medal-3.svg', earned: true, desc: '누적 100문제를 풀어내기', percent: 47 },
  { label: '복습왕', icon: '/ui/medal-4.svg', earned: true, desc: '예정된 복습을 미루지 않고 모두 끝내기', percent: 26 },
  { label: '자유 발화', icon: '/ui/medal-5.svg', earned: true, desc: '대화 실전 단계에서 자유롭게 말해보기', percent: 15 },
  { label: '수어 탐험', icon: '/ui/medal-6.svg', earned: false, desc: '한국수어 학습을 처음으로 경험하기', percent: 52 },
  { label: '30일 연속', icon: '/ui/medal-7.svg', earned: false, desc: '한 달 내내 학습 스트릭을 이어가기', percent: 6 },
  { label: '새벽 학습', icon: '/ui/medal-8.svg', earned: false, desc: '새벽 시간에 학습을 완료하기', percent: 11 },
  { label: '완주', icon: '/ui/medal-9.svg', earned: false, desc: '전체 커리큘럼을 끝까지 마치기', percent: 4 },
  { label: '레벨 5', shape: 'lock', earned: false, desc: '학습을 반복해 레벨 5에 도달하기', percent: 13 },
]

/** 배지 아이콘 그래픽(그리드·모달 공용). px로 크기를 받아 medal 이미지 또는 check/lock 도형을 렌더. */
function BadgeMedal({ b, px }) {
  const box = { height: px, width: px }
  if (b.icon) return <img src={b.icon} alt="" style={box} />
  if (b.shape === 'check') {
    return (
      <span className="flex items-center justify-center rounded-full bg-emerald-100" style={box}>
        <span className="rotate-45 rounded-sm bg-emerald-500"
          style={{ height: px * 0.36, width: px * 0.36, clipPath: 'polygon(40% 100%, 0 60%, 15% 45%, 40% 70%, 85% 15%, 100% 30%)' }} />
      </span>
    )
  }
  return (
    <span className="flex items-center justify-center rounded-full bg-gray-100" style={box}>
      <span className="rounded-md bg-gray-300" style={{ height: px * 0.43, width: px * 0.43 }} />
    </span>
  )
}

function Badge({ b, onSelect }) {
  return (
    <button type="button" onClick={() => onSelect(b)}
      className={`flex flex-col items-center gap-2 rounded-2xl outline-none transition-transform hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-primary-400 ${b.earned ? '' : 'opacity-50'}`}>
      <BadgeMedal b={b} px={56} />
      <span className="text-center text-[11.5px] font-bold text-ink">{b.label}</span>
    </button>
  )
}

/**
 * 배지 상세 모달 (Figma 313:33) — §3.5 예외: 흰 카드 없이 배경 블러 위에 배지를 크게 띄운다.
 * 공용 Modal.jsx(흰 카드+X) 재사용 금지. 전용 오버레이 + 중앙 세로 스택.
 * 배경 클릭·ESC로 닫힘.
 */
function BadgeDetailModal({ badge, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  if (!badge) return null
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#0d081c]/80 p-6 backdrop-blur-[9px]"
      onClick={onClose} role="dialog" aria-modal="true" aria-label={badge.label}>
      <div className="flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
        {/* 글로우 데코(배지 없음) 뒤 + 배지 중앙 */}
        <div className="relative flex items-center justify-center" style={{ height: 200, width: 200 }}>
          <img src="/ui/lp-313-33-glow-ring.svg" alt="" aria-hidden="true"
            className="pointer-events-none absolute inset-0 h-full w-full" />
          <div className={`relative z-10 ${badge.earned ? '' : 'opacity-60'}`}>
            <BadgeMedal b={badge} px={92} />
          </div>
        </div>

        {/* 제목·부제·희귀도 칩 */}
        <div className="mt-6 flex flex-col items-center gap-2.5">
          <h2 className="text-center text-[32px] font-bold tracking-[-0.64px] text-white">{badge.label}</h2>
          <p className="max-w-[320px] text-center text-[15px] font-normal text-white opacity-70">{badge.desc}</p>
          <span className="rounded-full border-[1.5px] border-white/20 bg-white/[0.12] px-[18px] py-[9px]">
            <span className="text-[15px] text-white">전체 사용자 중 </span>
            <span className="text-[18px] font-bold text-[#6ee7b7]">{badge.percent}%</span>
            <span className="text-[15px] text-white">가 획득했어요</span>
          </span>
        </div>

        {/* 닫기 */}
        <button type="button" onClick={onClose}
          className="mt-8 w-[220px] rounded-[14px] border-2 border-b-[5px] border-[#d4d4de] bg-white py-[15px] text-[17px] font-bold text-[#1a1a2e]">
          닫기
        </button>
      </div>
    </div>
  )
}

export default function TasksPage() {
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const [due, setDue] = useState(null)
  const [selectedBadge, setSelectedBadge] = useState(null)
  useEffect(() => {
    reviewAPI.getDue().then((d) => setDue((d.items || []).length)).catch(() => setDue(0))
  }, [])
  const reviewDone = due === 0 ? 1 : 0
  const earned = BADGES.filter((b) => b.earned).length

  return (
    <AppShell active="task" title="과제" description="매일 조금씩 채우면 보상이 쌓여요.">
      {/* 오늘의 과제 */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">오늘의 과제</p>
          <span className="text-[13px] text-ink-muted">오늘 안에 채워요</span>
        </div>
        <div className="mt-4 flex flex-col gap-4">
          <TaskRow label="오늘의 복습 정리" cur={reviewDone} total={1} xp={10} />
          <TaskRow label="독화 학습 1회" cur={0} total={1} xp={15} />
          <TaskRow label="학습 2회 채우기" cur={1} total={2} xp={20} />
        </div>
      </section>

      {/* 이번 주 도전 */}
      <section className="relative w-full overflow-hidden rounded-[20px] border-2 border-b-[5px] border-[#6d3fc4] p-6"
        style={{ backgroundImage: 'linear-gradient(168deg, #a78bfa 0%, #7d53de 71%)' }}>
        <div className="flex max-w-[462px] flex-col gap-2.5">
          <p className="text-[13px] font-bold tracking-[0.26px] text-white/80">특별 과제</p>
          <p className="text-[23px] font-bold tracking-[-0.46px] text-white">이번 주 5일 학습하기</p>
          <div className="flex justify-between text-sm font-bold text-white/90">
            <span>{Math.min(5, Math.max(0, user?.streak_count || 3))} / 5일</span>
            <span>+100 XP</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-white/30">
            <div className="h-full rounded-full bg-white" style={{ width: `${(Math.min(5, Math.max(0, user?.streak_count || 3)) / 5) * 100}%` }} />
          </div>
        </div>
        <div className="pointer-events-none absolute right-6 top-6 hidden h-[104px] w-[104px] items-center justify-center rounded-full bg-white/[0.18] sm:flex">
          <img src="/ui/trophy.svg" alt="" className="h-14 w-14" />
        </div>
      </section>

      {/* 배지 */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">배지</p>
          <span className="text-[13px] text-ink-muted">{earned} / {BADGES.length}개 획득</span>
        </div>
        <div className="mt-4 grid grid-cols-4 gap-y-5 sm:grid-cols-6">
          {BADGES.map((b) => <Badge key={b.label} b={b} onSelect={setSelectedBadge} />)}
        </div>
      </section>

      <BadgeDetailModal badge={selectedBadge} onClose={() => setSelectedBadge(null)} />
    </AppShell>
  )
}
