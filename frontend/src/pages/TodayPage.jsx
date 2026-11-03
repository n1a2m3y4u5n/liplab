import usePageLoad from '../hooks/usePageLoad'
import { useLocation } from 'react-router-dom'
import { todayNext } from '../lib/todayNext'
import { todayReviewCount, todayReviewStart } from '../lib/reviewDue'
import { loadLastTrack } from '../lib/lastTrack'
import { taskLabel } from '../lib/iaLabels'
import ErrorScreen from '../components/ErrorScreen'
import LoadingScreen from '../components/LoadingScreen'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { reviewAPI, tasksAPI, curriculumAPI, speakAPI, listenAPI } from '../api'
import useStore from '../store/useStore'
import { rewardMessage } from '../lib/reviewDue'

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
        <span className="size-6 shrink-0 rounded-full border border-line lg:size-[26px]" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5 lg:gap-[7px]">
        <div className="flex items-start justify-between gap-2 font-bold leading-figma">
          {/* 완료한 과제 제목은 모바일(238:259)만 흐린 글자, 데스크톱(139:23)은 그대로 */}
          <span className={`min-w-0 flex-1 break-keep text-[14px] lg:text-[15px] ${done ? 'text-ink-muted lg:text-ink' : 'text-ink'}`}>{label}</span>
          <span className={`shrink-0 whitespace-nowrap text-[12px] lg:text-[13px] ${listen ? 'text-listen-dark' : 'text-primary-500'}`}>{cur} / {total}{unit}</span>
        </div>
        <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total} aria-valuenow={Math.min(cur, total)} aria-valuetext={`${cur} / ${total}${unit}`} className="h-[7px] overflow-hidden rounded-full bg-fill lg:h-2">
          <div className={`h-full rounded-full ${listen ? 'bg-listen' : 'bg-primary-500'}`} style={{ width: `${Math.min(100, (cur / total) * 100)}%` }} />
        </div>
      </div>
      {done && !claimed && onClaim
        ? <button type="button" onClick={onClaim} className={`${chip} ring-2 ring-primary-300`}>받기 +{xp} 경험치</button>
        : <span className={chip}>+{xp} 경험치</span>}
    </Row>
  )
}

// 배지 목록·설명·판정은 lib/badges.js(mergeBadges)와 backend/analytics.py가 담당한다.
// Figma(313:130)에 회색(미획득) 그림만 있는 배지 — 획득해도 색 있는 그림이 없어 그대로 보인다.
/** 보상 토스트: 화면 아래(모바일은 하단 탭 바 위)에 잠깐 떴다 사라진다. */
function RewardToast({ text }) {
  if (!text) return null
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-40 flex justify-center px-4 lg:bottom-8">
      <p role="status" aria-live="polite"
        className="rounded-full bg-surface-inverse px-5 py-3 text-[14px] font-bold leading-figma text-white shadow-lg">{text}</p>
    </div>
  )
}

export default function TodayPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const uid = useStore((s) => s.user?.id)
  const [nextData, setNextData] = useState({})
  const [due, setDue] = useState(null)
  const [tasks, setTasks] = useState(null)
  const [toast, setToast] = useState('')

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

  const { loadState, retry: retryLoad } = usePageLoad(() => Promise.all([
      reviewAPI.getDue().catch(() => null),
      Promise.allSettled([curriculumAPI.getStages(), speakAPI.getCurriculum(), listenAPI.getCurriculum(), listenAPI.links()]),
      tasksAPI.claim().then((res) => { applyClaim(res); return res }).catch(() => tasksAPI.get().catch(() => null)),
    ]), ([d, o, t]) => {
      setDue(d)
      const [read, speak, listen, links] = o.map((r) => r.status === 'fulfilled' ? r.value : null)
      setNextData({ stages: read, speak, listen, links, lastTrack: loadLastTrack(uid, { read, speak, listen }) })
      setTasks(t)
  })
  useEffect(() => {
    if (!toast) return undefined
    const t = setTimeout(() => setToast(''), 3200)
    return () => clearTimeout(t)
  }, [toast])

  const daily = tasks?.daily || []
  const week = tasks?.weekly?.[0]
  const weekCur = week?.cur ?? 0
  const weekTotal = week?.total || 5
  const next = todayNext({ ...nextData, due, tasks })
  useEffect(() => {
    if (loadState !== 'ready' || !location.hash) return
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: 'start' })
  }, [loadState, location.hash])

  if (loadState !== 'ready') return (
    <AppShell active="today" title="오늘">
      {loadState === 'error'
        ? <ErrorScreen onRetry={retryLoad} onHome={() => navigate('/learn/path')} />
        : <LoadingScreen variant="inline" />}
    </AppShell>
  )

  return (
    <AppShell active="today" title="오늘">
      {/* 다음 할 일: 데스크톱은 설명 왼쪽 · 버튼 오른쪽 한 줄, 폰은 위아래 */}
      <section className="card-flat flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between lg:gap-6">
        <div className="flex min-w-0 flex-col gap-3">
          {next.line && <p className="break-keep text-[17px] font-semibold leading-snug text-ink">{next.line}</p>}
          {next.retry && <button className="btn-secondary min-h-11 self-start" onClick={retryLoad}>다시 가져오기</button>}
        </div>
        <button className="btn-primary btn-lg w-full shrink-0 lg:w-auto lg:min-w-[240px]" onClick={() => navigate(next.to, { state: next.state })}>{next.label}</button>
      </section>
      <div className="today-grid contents">
      {!due && <section className="card-flat flex flex-wrap items-center justify-between gap-2" role="alert"><p className="text-sm text-ink-muted">복습할 것을 가져오지 못했어요.</p><button className="btn-secondary min-h-11 px-3" onClick={retryLoad}>다시 가져오기</button></section>}
      {!next.review && todayReviewCount(due) > 0 && <section id="review" className="card-flat flex flex-col gap-3">
        <h2 className="text-[16px] font-semibold text-ink lg:text-[17px]">오늘 복습 <span className="tabular-nums">{todayReviewCount(due)}</span>개</h2>
        <div className="flex flex-wrap gap-2">{[['입모양 읽기', due?.count, '/review/scheduled'], ['말하기', due?.speak_count, '/review/speaking'], ...(nextData.links?.listen_started ? [['소리 듣기', due?.listen_count, '/listen/review']] : [])].filter(([, n]) => n > 0).map(([label, n, to]) => <button key={to} className="min-h-11 rounded-full bg-surface-sunken px-4 text-[14px] font-medium text-ink transition-colors hover:bg-surface-hover" onClick={() => navigate(to)}>{label} <span className="font-semibold tabular-nums">{n}</span>개</button>)}</div>
        <button className="btn-secondary btn-md" onClick={() => navigate(todayReviewStart(due))}>복습 시작하기</button>
      </section>}
      {nextData.links?.listen_started && <button className="card-flat min-h-11 text-left font-bold" onClick={() => navigate('/listen/today?from=today')}>오늘의 듣기 · 15분</button>}
      {/* 오늘의 과제 (137:187 / 238:250) */}
      <section id="tasks" className="flex w-full flex-col gap-3.5 rounded-16 border border-line bg-white p-[18px] lg:gap-[18px] lg:p-[22px]">
        <div className="flex items-start justify-between gap-2 font-bold leading-figma">
          <h2 className="text-[16px] text-ink lg:text-[17px]">오늘의 과제</h2>
          <span className="text-[12px] text-ink-muted lg:text-[13px]">오늘 남은 시간 {hoursLeftToday()}시간</span>
        </div>
        {/* 오늘의 복습 정리: 예정 복습(독화·말하기, /api/review/due)이 남아 있으면 눌러서 그 복습 세션으로 간다(독화 먼저) */}
        {daily.map((t) => {
          const listen = isListenTask(t)
          const open = t.key === 'review_clear' && !t.done && todayReviewCount(due) > 0 ? () => navigate(todayReviewStart(due))
            : listen && !t.done ? () => navigate(t.to && t.to.startsWith('/listen/') ? t.to : '/listen/today?from=tasks') : undefined
          return (
            <TaskRow key={t.key} label={taskLabel(t)} cur={Math.round(t.cur)} total={t.total} xp={t.xp} claimed={t.claimed} listen={listen}
              unit={t.unit || (listen ? '분' : '')} onClick={open} onClaim={() => claim().catch(() => setToast('보상을 받지 못했어요. 다시 눌러 주세요.'))} />
          )
        })}
        {tasks && daily.length === 0 && <p className="text-sm text-ink-muted">오늘의 과제가 없어요.</p>}
        {!tasks && <div role="alert" className="flex flex-wrap items-center justify-between gap-2 text-sm text-ink-muted"><p>과제를 가져오지 못했어요.</p><button className="btn-secondary min-h-11 px-3" onClick={retryLoad}>다시 가져오기</button></div>}
      </section>

      {/* 이번 주 도전 — 11/03부터 보라 바탕·워터마크 대신 흰 카드 + 트랙색 진행 막대 */}
      {week && <section className="flex w-full flex-col gap-3 rounded-16 border border-line bg-white p-[18px] leading-figma lg:p-[22px]">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[12px] font-medium text-ink-muted lg:text-[13px]">특별 과제</p>
          <span className="text-[12px] font-semibold text-primary-700 lg:text-[13px]">{week.claimed ? '받음 ' : ''}+{week.xp} 경험치</span>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <p className="break-keep text-[17px] font-semibold text-ink lg:text-[18px]">{week.label}</p>
          <span className="shrink-0 text-[14px] font-semibold tabular-nums text-ink">{weekCur} / {weekTotal}일</span>
        </div>
        <div role="progressbar" aria-label="이번 주 도전" aria-valuemin={0} aria-valuemax={weekTotal} aria-valuenow={Math.min(weekCur, weekTotal)} aria-valuetext={`${weekCur} / ${weekTotal}일`} className="h-2 overflow-hidden rounded-full bg-fill">
          <div className="h-full rounded-full bg-primary-500" style={{ width: `${Math.min(100, (weekCur / weekTotal) * 100)}%` }} />
        </div>
      </section>}

      </div>
      <RewardToast text={toast} />
    </AppShell>
  )
}
