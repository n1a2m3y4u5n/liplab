import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import WatermarkCard from '../components/WatermarkCard'
import { reviewAPI, learningAPI } from '../api'
import { mergeBadges } from '../lib/badges'

/**
 * 과제 탭 (Figma 137:17 · 모바일 238:160) — 일일 과제 진행/보상 + 주간 도전 + 배지.
 * 진행도는 실제 기록에서 온다: 복습 수는 reviewAPI, 오늘 회차·독화 활동·이번 주 학습일·배지는
 * GET /api/analysis/overview(backend/analytics.py). 불러오기 전에는 0·미획득으로 보인다.
 * 오른쪽 패널은 과제 탭 구성(스탯 + 레벨 진행 + 복습할 항목, 137:151).
 * 크기는 lg 미만이 모바일 프레임 값, lg 이상이 데스크톱 프레임 값이다.
 */

/** 오늘 남은 시간(137:190 "오늘 남은 시간 N시간") — 자정까지 남은 시간을 올림한 정수. */
function hoursLeftToday() {
  const now = new Date()
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  return Math.max(1, Math.ceil((midnight - now) / 3600000))
}

/** 과제 한 줄(139:18 / 238:254) — 완료 원 + 제목·n / n + 진행 막대 + 보상 칩. */
function TaskRow({ label, cur, total, xp }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3 lg:gap-3.5">
      {done ? (
        <img src="/ui/task-done.svg" alt="" className="size-6 shrink-0 lg:size-[26px]" />
      ) : (
        <span className="size-6 shrink-0 rounded-full border-2 border-line lg:size-[26px]" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5 lg:gap-[7px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          {/* 완료한 과제 제목은 모바일(238:259)만 흐린 글자, 데스크톱(139:23)은 그대로 */}
          <span className={`text-[14px] lg:text-[15px] ${done ? 'text-ink-muted lg:text-ink' : 'text-ink'}`}>{label}</span>
          <span className="text-[12px] text-primary-500 lg:text-[13px]">{cur} / {total}</span>
        </div>
        <div className="h-[7px] overflow-hidden rounded-full bg-fill lg:h-2">
          <div className="h-full rounded-full bg-primary-500" style={{ width: `${Math.min(100, (cur / total) * 100)}%` }} />
        </div>
      </div>
      <span className={`shrink-0 rounded-full px-[9px] py-[5px] text-[11px] font-bold leading-figma lg:px-3 lg:py-1.5 lg:text-[12px] ${done ? 'bg-primary-100 text-primary-700' : 'bg-surface-sunken text-ink-faint'}`}>+{xp} XP</span>
    </div>
  )
}

// 배지 목록·설명·판정은 lib/badges.js(mergeBadges)와 backend/analytics.py가 담당한다.
// Figma(313:130)에 회색(미획득) 그림만 있는 배지 — 획득해도 색 있는 그림이 없어 그대로 보인다.
const GREY_ONLY = new Set(['sign', 'streak30', 'dawn', 'complete', 'level5'])

/**
 * 배지 아이콘 그래픽(그리드·모달 공용). size는 Tailwind 크기 클래스.
 *  - icon: Figma 메달 에셋(medal-*.svg, 원 배경 포함)
 *  - shape 'check'(정확도 90%, 313:148): 연녹 원 + 45° 회전한 초록 마름모(22/56)
 *  - shape 'lock'(레벨 5, 313:181): 연회색 원(85%) + 회색 둥근 사각(25/56)
 * markOnly: 모달의 정확도 90% 마크(313:224) — 원 없이 큰 마름모만(92/130).
 */
function BadgeMedal({ b, size, markOnly = false }) {
  if (b.icon) return <img src={b.icon} alt="" className={`max-w-none ${size}`} />
  if (b.shape === 'check') {
    if (markOnly) {
      return (
        <span className={`flex items-center justify-center drop-shadow-[0_10px_12px_rgba(5,77,51,0.35)] ${size}`}>
          <span className="size-[70.77%] rotate-45 rounded-[17.4%] bg-emerald-500" />
        </span>
      )
    }
    return (
      <span className={`flex items-center justify-center rounded-full bg-[#dff7ec] ${size}`}>
        <span className="size-[39.3%] rotate-45 rounded-[18%] bg-emerald-500" />
      </span>
    )
  }
  return (
    <span className={`flex items-center justify-center rounded-full bg-[#f1f1f5] ${size}`}>
      <span className="size-[44.6%] rounded-[20%] bg-[#c2c2ce]" />
    </span>
  )
}

/** 배지 한 칸(313:135) — 메달 56 + 9 + 이름 11.5px. 미획득은 이름을 흐리게(55%), 색 메달은 회색조로. */
function Badge({ b, onSelect }) {
  const dim = !b.earned && !GREY_ONLY.has(b.key)
  return (
    <button type="button" onClick={() => onSelect(b)}
      className="flex min-w-0 flex-col items-center gap-[9px] rounded-2xl outline-none transition-transform hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-primary-400">
      <span className={dim ? 'opacity-50 grayscale' : ''}><BadgeMedal b={b} size="size-14" /></span>
      <span className={`text-center text-[11.5px] font-bold leading-figma ${b.earned ? 'text-ink' : 'text-ink-muted opacity-55'}`}>{b.label}</span>
    </button>
  )
}

/**
 * 배지 상세 모달 (Figma 313:33) — §3.5 예외: 흰 카드 없이 배경 블러 위에 배지를 크게 띄운다.
 * 공용 Modal.jsx(흰 카드+X) 재사용 금지. 전용 오버레이 + 중앙 세로 스택.
 * 글로우 420(313:215) 가운데 배지 마크 130(313:224), 문구 묶음(313:225)은 글로우 아래쪽에 40px 겹친다.
 * 모바일 프레임이 없어 lg 미만은 같은 비율로 줄인다(글로우 260 · 마크 80 · 겹침 25).
 * 정확도 90%(획득)는 Figma가 글로우와 마크를 한 에셋으로 내보낸 lp-313-33-glow.svg를 그대로 쓴다.
 * 배경 클릭·ESC로 닫힘.
 */
function BadgeDetailModal({ badge, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  if (!badge) return null
  const figmaMark = badge.shape === 'check' && badge.earned
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#0d081c]/80 p-6 backdrop-blur-[9px]"
      onClick={onClose} role="dialog" aria-modal="true" aria-label={badge.label}>
      <div className="flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
        {/* 글로우(링 3개·부드러운 빛·반짝이) 뒤 + 배지 마크 가운데 */}
        <div className="relative flex size-[260px] items-center justify-center lg:size-[420px]">
          <img src={figmaMark ? '/ui/lp-313-33-glow.svg' : '/ui/lp-313-33-glow-ring.svg'} alt="" aria-hidden="true"
            className="pointer-events-none absolute inset-0 size-full" />
          {!figmaMark && (
            <div className={`relative ${badge.earned || GREY_ONLY.has(badge.key) ? '' : 'opacity-60'}`}>
              <BadgeMedal b={badge} size="size-20 lg:size-[130px]" markOnly />
            </div>
          )}
        </div>

        {/* 제목·설명·희귀도 칩 */}
        <div className="relative -mt-[25px] flex flex-col items-center gap-2.5 lg:-mt-10">
          <h2 className="text-center text-[32px] font-bold leading-figma tracking-[-0.64px] text-white">{badge.label}</h2>
          <p className="max-w-[320px] text-center text-[15px] leading-figma text-white opacity-70">{badge.desc}</p>
          {/* 희귀도 칩: 계산 API가 없으면 숨긴다(핸드오프 §7-3). */}
          {badge.percent != null && (
            <span className="rounded-full border-[1.5px] border-white/[0.22] bg-white/[0.12] px-[18px] py-[9px] leading-figma">
              <span className="text-[15px] text-white">전체 사용자 중 </span>
              <span className="text-[18px] font-bold text-[#6ee7b7]">{badge.percent}%</span>
              <span className="text-[15px] text-white">가 획득했어요</span>
            </span>
          )}
        </div>

        {/* 닫기(313:230) */}
        <button type="button" onClick={onClose}
          className="mt-8 w-[220px] rounded-14 border-2 border-b-5 border-[#d4d4de] bg-white py-[15px] text-[17px] font-bold leading-figma text-ink transition-all active:translate-y-[1px] active:border-b-2">
          닫기
        </button>
      </div>
    </div>
  )
}

export default function TasksPage() {
  const [due, setDue] = useState(null)
  const [ov, setOv] = useState(null)
  const [selectedBadge, setSelectedBadge] = useState(null)
  useEffect(() => {
    reviewAPI.getDue().then((d) => setDue((d.items || []).length)).catch(() => setDue(null))
    learningAPI.getAnalysisOverview().then(setOv).catch(() => setOv(null))
  }, [])
  const reviewDone = due === 0 ? 1 : 0
  const weekDays = Math.min(5, ov?.week_days ?? 0)
  const badges = mergeBadges(ov?.badges)
  const earned = badges.filter((b) => b.earned).length

  return (
    <AppShell active="task" title="과제" rail="tasks">
      {/* 오늘의 과제 (137:187 / 238:250) */}
      <section className="flex w-full flex-col gap-3.5 rounded-16 border-2 border-line bg-white p-[18px] lg:gap-[18px] lg:rounded-18 lg:p-[22px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[16px] text-ink lg:text-[17px]">오늘의 과제</p>
          <span className="text-[12px] text-ink-muted lg:text-[13px]">오늘 남은 시간 {hoursLeftToday()}시간</span>
        </div>
        <TaskRow label="오늘의 복습 정리" cur={reviewDone} total={1} xp={10} />
        <TaskRow label="독화 학습 1회" cur={Math.min(1, ov?.today_read ?? 0)} total={1} xp={15} />
        <TaskRow label="학습 2회 채우기" cur={Math.min(2, ov?.today_sessions ?? 0)} total={2} xp={20} />
      </section>

      {/* 이번 주 도전 (141:18 / 238:285) — 워터마크 DOKA(306:32 / 306:39, -20°, 잘림) */}
      <WatermarkCard as="section"
        deco={{
          src: '/ui/lp-137-17-deco-doka.svg', size: 165, top: -61.22, right: -61.21, inset: [-7, -12, -17, -12],
          lg: { size: 198, top: -73.06, right: -73.06 },
        }}
        className="h-[132px] w-full rounded-18 border-2 border-b-5 border-primary-600 bg-[linear-gradient(158.74deg,#a78bfa_0%,#7d53de_70.92%)] pl-[18px] pt-[21px] lg:h-[158px] lg:rounded-20 lg:bg-[linear-gradient(167.63deg,#a78bfa_0%,#7d53de_70.92%)] lg:pl-[26px] lg:pt-[26px]">
        <div className="flex w-[250px] max-w-full flex-col gap-[9px] font-bold leading-figma text-white lg:w-[462px] lg:gap-2.5">
          <p className="text-[11px] tracking-[0.22px] opacity-80 lg:text-[13px] lg:tracking-[0.26px]">특별 과제</p>
          <p className="text-[18px] tracking-[-0.36px] lg:text-[23px] lg:tracking-[-0.46px]">이번 주 5일 학습하기</p>
          <div className="flex justify-between text-[12px] lg:text-[14px]">
            <span className="opacity-90">{weekDays} / 5일</span>
            <span className="opacity-90">+100 XP</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/30 lg:h-3">
            <div className="h-full rounded-full bg-white" style={{ width: `${(weekDays / 5) * 100}%` }} />
          </div>
        </div>
      </WatermarkCard>

      {/* 배지 (313:130) — 모바일 238:160에는 이 카드가 없다(유지 여부는 결정 필요, 보고서 참고) */}
      <section className="flex w-full flex-col gap-[18px] rounded-18 border-2 border-line bg-white p-5 lg:p-[22px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">배지</p>
          <span className="text-[13px] text-ink-muted">{earned} / {badges.length}개 획득</span>
        </div>
        <div className="grid grid-cols-4 gap-x-3 gap-y-[18px] sm:grid-cols-6">
          {badges.map((b) => <Badge key={b.key} b={b} onSelect={setSelectedBadge} />)}
        </div>
      </section>

      <BadgeDetailModal badge={selectedBadge} onClose={() => setSelectedBadge(null)} />
    </AppShell>
  )
}
