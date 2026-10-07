import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import WatermarkCard from '../components/WatermarkCard'
import { reviewAPI, learningAPI, tasksAPI } from '../api'
import useStore from '../store/useStore'
import { mergeBadges } from '../lib/badges'
import { dueCounts, dueStartPath, rewardMessage } from '../lib/reviewDue'
import useFocusTrap from '../hooks/useFocusTrap'

/**
 * 과제 탭 (Figma 137:17 · 모바일 238:160) — 일일 과제 진행/보상 + 주간 도전 + 배지.
 * 과제 목록·목표·보상 XP와 달성 판정은 서버(backend/daily_tasks.py)가 한다. 화면을 열면 POST /api/tasks/claim으로
 * 달성했지만 받지 않은 보상을 받고(과제마다 하루·한 주에 한 번, KST) 응답의 과제 목록을 그린다. 받은 것이 있으면 토스트를 띄운다.
 * 배지는 GET /api/analysis/overview(backend/analytics.py). 불러오기 전에는 미획득으로 보인다.
 * 오른쪽 패널은 과제 탭 구성(스탯 + 레벨 진행 + 복습할 항목, 137:151).
 * 크기는 lg 미만이 모바일 프레임 값, lg 이상이 데스크톱 프레임 값이다.
 * 10월: 서버가 '소리 듣기 15분' 과제(key가 listen으로 시작, 또는 to가 /listen/…)를 주면 그 줄은 트랙색 청록으로 그리고,
 * 채우기 전에는 눌러서 오늘의 듣기(/listen/today?from=tasks)로 간다. 분 단위 과제라 'n / 15분'으로 적는다(unit이 오면 그것).
 */
const isListenTask = (t) => /^listen/.test(t?.key || '') || /^\/listen\//.test(t?.to || '')

/** 오늘 남은 시간(137:190 "오늘 남은 시간 N시간") — 자정까지 남은 시간을 올림한 정수. */
function hoursLeftToday() {
  const now = new Date()
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  return Math.max(1, Math.ceil((midnight - now) / 3600000))
}

/** 과제 한 줄(139:18 / 238:254): 완료 원 + 제목·n / n + 진행 막대 + 보상 칩.
 * 달성했는데 아직 못 받은 보상(받기 요청 실패)은 칩을 눌러 다시 받는다(onClaim). */
function TaskRow({ label, cur, total, xp, claimed, onClick, onClaim, listen = false, unit = '' }) {
  const done = cur >= total
  const chip = `shrink-0 rounded-full px-[9px] py-[5px] text-[11px] font-bold leading-figma lg:px-3 lg:py-1.5 lg:text-[12px] ${done ? (listen ? 'bg-listen-tint text-listen-dark' : 'bg-primary-100 text-primary-700') : 'bg-surface-sunken text-ink-faint'}`
  // onClick을 주면(오늘의 복습 정리 → 예정 복습) 같은 모양의 버튼으로 그린다.
  const Row = onClick ? 'button' : 'div'
  return (
    <Row {...(onClick ? { type: 'button', onClick } : {})} className={`flex items-center gap-3 lg:gap-3.5 ${onClick ? 'w-full text-left' : ''}`}>
      {done ? (
        <img src="/ui/task-done.svg" alt="" className="size-6 shrink-0 lg:size-[26px]" />
      ) : (
        <span className="size-6 shrink-0 rounded-full border-2 border-line lg:size-[26px]" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5 lg:gap-[7px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          {/* 완료한 과제 제목은 모바일(238:259)만 흐린 글자, 데스크톱(139:23)은 그대로 */}
          <span className={`text-[14px] lg:text-[15px] ${done ? 'text-ink-muted lg:text-ink' : 'text-ink'}`}>{label}</span>
          <span className={`text-[12px] lg:text-[13px] ${listen ? 'text-listen-dark' : 'text-primary-500'}`}>{cur} / {total}{unit}</span>
        </div>
        <div className="h-[7px] overflow-hidden rounded-full bg-fill lg:h-2">
          <div className={`h-full rounded-full ${listen ? 'bg-listen' : 'bg-primary-500'}`} style={{ width: `${Math.min(100, (cur / total) * 100)}%` }} />
        </div>
      </div>
      {done && !claimed && onClaim
        ? <button type="button" onClick={onClaim} className={`${chip} ring-2 ring-primary-300`}>받기 +{xp} XP</button>
        : <span className={chip}>+{xp} XP</span>}
    </Row>
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
      <span className={`flex items-center justify-center rounded-full bg-pastel-mint ${size}`}>
        <span className="size-[39.3%] rotate-45 rounded-[18%] bg-emerald-500" />
      </span>
    )
  }
  return (
    <span className={`flex items-center justify-center rounded-full bg-inactive-bg ${size}`}>
      <span className="size-[44.6%] rounded-[20%] bg-inactive-glyph" />
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
 * 배경 클릭·ESC로 닫힘. 열린 동안 포커스를 모달 안에 가두고, 닫히면 누른 배지로 포커스를 돌려준다(hooks/useFocusTrap).
 */
function BadgeDetailModal({ badge, onClose }) {
  const dialogRef = useFocusTrap(!!badge, onClose)
  if (!badge) return null
  const figmaMark = badge.shape === 'check' && badge.earned
  return (
    <div ref={dialogRef} className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-overlay-deep/80 p-6 backdrop-blur-[9px]"
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
              <span className="text-[18px] font-bold text-chart-onDark">{badge.percent}%</span>
              <span className="text-[15px] text-white">가 획득했어요</span>
            </span>
          )}
        </div>

        {/* 닫기(313:230) */}
        <button type="button" onClick={onClose}
          className="mt-8 w-[220px] rounded-14 border-2 border-b-5 border-line-strong bg-white py-[15px] text-[17px] font-bold leading-figma text-ink transition-all active:translate-y-[1px] active:border-b-2">
          닫기
        </button>
      </div>
    </div>
  )
}

/** 보상 토스트: 화면 아래(모바일은 하단 탭 바 위)에 잠깐 떴다 사라진다. */
function RewardToast({ text }) {
  if (!text) return null
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-40 flex justify-center px-4 lg:bottom-8">
      <p role="status" aria-live="polite"
        className="rounded-full bg-slate-900 px-5 py-3 text-[14px] font-bold leading-figma text-white shadow-lg">{text}</p>
    </div>
  )
}

export default function TasksPage() {
  const navigate = useNavigate()
  const [due, setDue] = useState(null)
  const [ov, setOv] = useState(null)
  const [tasks, setTasks] = useState(null)
  const [toast, setToast] = useState('')
  const [selectedBadge, setSelectedBadge] = useState(null)

  // 받은 보상을 화면 스탯(XP·레벨)에 바로 반영하고 토스트를 띄운다
  const applyClaim = (res) => {
    setTasks(res)
    if (!res?.xp_gained) return
    const st = useStore.getState()
    const upd = { total_xp: res.total_xp, current_level: res.current_level }
    st.updateUser(upd)
    if (st.statistics) st.setStatistics({ ...st.statistics, ...upd })
    setToast(rewardMessage(res.claimed))
  }
  const claim = () => tasksAPI.claim().then(applyClaim)

  useEffect(() => {
    let on = true
    reviewAPI.getDue().then((d) => on && setDue(dueCounts(d))).catch(() => on && setDue(null))
    learningAPI.getAnalysisOverview().then((o) => on && setOv(o)).catch(() => on && setOv(null))
    // 받기에 실패하면(요청 제한 등) 목록만 읽는다. 못 받은 보상은 칩의 '받기'로 다시 받는다.
    // 받은 응답은 on과 상관없이 반영한다(개발 모드 StrictMode의 두 번째 요청은 이미 받아 0 XP라 첫 응답을 버리면 토스트가 사라진다)
    tasksAPI.claim().then(applyClaim)
      .catch(() => tasksAPI.get().then((t) => on && setTasks(t)).catch(() => {}))
    return () => { on = false }
  }, [])
  useEffect(() => {
    if (!toast) return undefined
    const t = setTimeout(() => setToast(''), 3200)
    return () => clearTimeout(t)
  }, [toast])

  const daily = tasks?.daily || []
  const week = tasks?.weekly?.[0]
  const weekCur = week?.cur ?? 0
  const weekTotal = week?.total || 5
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
        {/* 오늘의 복습 정리: 예정 복습(독화·말하기, /api/review/due)이 남아 있으면 눌러서 그 복습 세션으로 간다(독화 먼저) */}
        {daily.map((t) => {
          const listen = isListenTask(t)
          const open = t.key === 'review_clear' && !t.done && due?.total > 0 ? () => navigate(dueStartPath(due, '/review'))
            : listen && !t.done ? () => navigate(t.to && t.to.startsWith('/listen/') ? t.to : '/listen/today?from=tasks') : undefined
          return (
            <TaskRow key={t.key} label={t.label} cur={Math.round(t.cur)} total={t.total} xp={t.xp} claimed={t.claimed} listen={listen}
              unit={t.unit || (listen ? '분' : '')} onClick={open} onClaim={() => claim().catch(() => {})} />
          )
        })}
        {!tasks && <p className="py-3 text-center text-[13px] text-ink-muted">과제를 불러오는 중…</p>}
      </section>

      {/* 이번 주 도전 (141:18 / 238:285) — 워터마크 DOKA(306:32 / 306:39, -20°, 잘림) */}
      <WatermarkCard as="section"
        deco={{
          src: '/ui/lp-137-17-deco-doka.svg', size: 165, top: -61.22, right: -61.21, inset: [-7, -12, -17, -12],
          lg: { size: 198, top: -73.06, right: -73.06 },
        }}
        className="h-[132px] w-full rounded-18 border-2 border-b-5 border-primary-600 bg-[linear-gradient(158.74deg,var(--brand-light)_0%,var(--brand)_70.92%)] pl-[18px] pt-[21px] lg:h-[158px] lg:rounded-20 lg:bg-[linear-gradient(167.63deg,var(--brand-light)_0%,var(--brand)_70.92%)] lg:pl-[26px] lg:pt-[26px]">
        <div className="flex w-[250px] max-w-full flex-col gap-[9px] font-bold leading-figma text-white lg:w-[462px] lg:gap-2.5">
          <p className="text-[11px] tracking-[0.22px] opacity-80 lg:text-[13px] lg:tracking-[0.26px]">특별 과제</p>
          <p className="text-[18px] tracking-[-0.36px] lg:text-[23px] lg:tracking-[-0.46px]">{week?.label ?? '\u00a0'}</p>
          <div className="flex justify-between text-[12px] lg:text-[14px]">
            <span className="opacity-90">{week ? `${weekCur} / ${weekTotal}일` : '…'}</span>
            <span className="opacity-90">{week ? `${week.claimed ? '받음 ' : ''}+${week.xp} XP` : ''}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/30 lg:h-3">
            <div className="h-full rounded-full bg-white" style={{ width: `${Math.min(100, (weekCur / weekTotal) * 100)}%` }} />
          </div>
        </div>
      </WatermarkCard>

      {/* 배지 (313:130) — 데스크톱만. 모바일 238:160에는 이 카드가 없어 lg 미만에서는 숨긴다(9/24 결정).
          모바일에서는 분석 탭 '전체 통계'의 획득 배지 수로 본다. */}
      <section className="hidden w-full flex-col gap-[18px] rounded-18 border-2 border-line bg-white p-5 lg:flex lg:p-[22px] lg:[@media(max-height:860px)]:gap-3.5 lg:[@media(max-height:860px)]:p-[18px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">배지</p>
          <span className="text-[13px] text-ink-muted">{earned} / {badges.length}개 획득</span>
        </div>
        <div className="grid grid-cols-4 gap-x-3 gap-y-[18px] sm:grid-cols-6">
          {badges.map((b) => <Badge key={b.key} b={b} onSelect={setSelectedBadge} />)}
        </div>
      </section>

      <BadgeDetailModal badge={selectedBadge} onClose={() => setSelectedBadge(null)} />
      <RewardToast text={toast} />
    </AppShell>
  )
}
