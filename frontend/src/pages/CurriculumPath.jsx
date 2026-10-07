import { Fragment, useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import DokaNode, { DokaConnector } from '../components/DokaNode'
import GuideModal from '../components/GuideModal'
import LoadingScreen from '../components/LoadingScreen'
import RetentionPrompt from '../components/RetentionPrompt'
import { curriculumAPI, speakAPI, listenAPI } from '../api'
import { goalMinutes } from '../lib/listenFlow'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma 58:11 독화 / 171:38 발화, 모바일 232:35 — lg 미만 반응형). DOKA 마스코트 노드.
 * 독화·발화 두 트랙이 같은 화면을 쓰고 색만 다르다. ?track=speak 이면 AppShell이 data-track="speak"를 달아
 * 트랙 토큰(bg-track·text-track·.btn-primary)이 분홍이 된다(§3.1).
 *  - 독화: curriculumAPI.getStages() → 1~4단계(입모양·단어·문장·대화)
 *  - 발화: speakAPI.getCurriculum() → 0~5단계(발성·운율·모음·자음·단어·문장), /learn/speaking?stage=N
 * 상태: 진행중(58:11) · 잠김+건너뛰기 말풍선(78:8) · 건너뛰기 확인(79:5) · 해금(80:6).
 *
 * Figma는 한 단계의 레슨 6개를 노드로 그리고 좌우 화살표로 단계 페이지를 넘기지만, 백엔드에는 레슨 단위 데이터가
 * 없어 노드 = 단계로 둔다(의도된 차이). 화살표는 보고 있는 단계(배너·레슨 카드)를 앞뒤 단계로 옮긴다.
 * 건너뛰기: 독화는 배치 API(setTrack start_stage)가, 발화는 speakAPI.skip이 서버 포인터를 옮겨 그 단계를 연다.
 * 연 뒤에는 단계를 다시 받아 경로에 머물고, 연 단계가 현재 노드가 되어 레슨 카드가 뜬다(80:6).
 * 소리 듣기 트랙은 레슨 카드 아래에 '오늘의 듣기'(15분 회기, /listen/today, 오늘 한 분 / 15분)를 보조 버튼으로 두고(독화의 짝 맞추기와 같은 자리),
 * 안내 줄에서 소리 교실(/listen/classroom)과 결과(/analysis/listening)로 간다.
 */

// ── 독화 트랙 ─────────────────────────────────────────────────────────────
// 문장·대화 단계는 시나리오 선택(ScenarioHub)을 거쳐야 currentScenario가 세팅된 뒤 레슨(/practice·/conversation)이 뜬다.
// 바로 보내면 시나리오가 없어 레슨이 되돌려보내므로(9/25 '학습 시작하기를 눌러도 아무 일 없음') /learn/scenario로 진입하고,
// 대화 단계는 연습 방법을 'AI 대화'로 골라 둔다.
const READ_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario', conversation: '/learn/scenario?mode=conversation' }
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(backend/main.py _STAGE1~4_MIN_ATTEMPTS = 8·6·5·4와 같게).
// 9/28부터 서버가 단계마다 min_attempts·mastery(·pass)를 실어 보내므로 이 표는 응답에 없을 때만 쓴다.
const READ_TOTAL = { viseme: 8, word: 6, sentence: 5, conversation: 4 }
const TRACK_LABEL = { read: '독화', speak: '발화', listen: '소리 듣기' }
const TRACKS = Object.keys(TRACK_LABEL)

// 단계 이동 화살표 에셋 — 데스크톱 44 슬롯(58:11) / 모바일 38 슬롯(232:35). 둘 다 그림자 여백만큼 위 4·좌우 7 넘친다.
// 발화 모바일 프레임은 없어 데스크톱 분홍 에셋을 줄여 쓴다.
const ARROW = {
  read: {
    prev: '/ui/stage-arrow-prev.svg', next: '/ui/stage-arrow-next.svg',
    prevMobile: '/ui/lp-232-35-stage-arrow-prev.svg', nextMobile: '/ui/lp-232-35-stage-arrow-next.svg',
  },
  speak: {
    prev: '/ui/lp-171-38-stage-arrow-prev.svg', next: '/ui/lp-171-38-stage-arrow-next.svg',
    prevMobile: null, nextMobile: null,
  },
  listen: {
    prev: '/ui/listen-stage-arrow-prev.svg', next: '/ui/listen-stage-arrow-next.svg',
    prevMobile: null, nextMobile: null,
  },
}
const ARROW_OVERFLOW = { top: -4, left: -7, width: 'calc(100% + 14px)', height: 'calc(100% + 14px)' }
// 노드 간격(슬롯 + 연결선 − 겹침): 모바일 56+28−10 = 74, lg 76+58−16 = 118 — 모바일 화살표를 보고 있는 노드 높이에 맞춘다.
const PITCH_MOBILE = 74

function StageArrow({ dir, onClick, disabled, track, style }) {
  const a = ARROW[track] || ARROW.read
  const desktop = dir === 'prev' ? a.prev : a.next
  const mobile = (dir === 'prev' ? a.prevMobile : a.nextMobile) || desktop
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={dir === 'prev' ? '이전 단계' : '다음 단계'} style={style}
      className={`absolute z-10 size-[38px] transition top-[var(--arrow-top)] disabled:cursor-not-allowed disabled:opacity-30 enabled:hover:opacity-80 enabled:active:scale-95 lg:top-1/2 lg:size-11 lg:-translate-y-1/2 ${
        dir === 'prev' ? 'left-0.5 lg:left-[27px]' : 'right-0.5 lg:right-[52px]'}`}>
      <picture>
        <source media="(min-width: 1024px)" srcSet={desktop} />
        <img src={mobile} alt="" className="absolute max-w-none" style={ARROW_OVERFLOW} />
      </picture>
    </button>
  )
}

// 말풍선·팝오버 꼬리(Figma Tail face + Tail edge). 왼쪽을 가리키는 꼬리 16×22 — 테두리 선은 에셋 그대로(line)
// 또는 mask로 토큰 색을 칠한다(건너뛰기 확인의 앰버 테두리와 맞추려고).
function TailLeft({ className = '', edgeClass = '' }) {
  return (
    <span aria-hidden className={`pointer-events-none absolute h-[22px] w-4 ${className}`}>
      <img src="/ui/lp-80-6-tail-face.svg" alt="" className="absolute inset-0 size-full max-w-none" />
      {edgeClass
        ? <span className={`mask-icon absolute ${edgeClass}`} style={{ '--icon': 'url(/ui/lp-80-6-tail-edge.svg)', left: -1, top: -0.825, width: 17.566, height: 23.648 }} />
        : <img src="/ui/lp-80-6-tail-edge.svg" alt="" className="absolute max-w-none" style={{ left: -1, top: -0.825, width: 17.566, height: 23.648 }} />}
    </span>
  )
}

/** 두 트랙의 단계 목록을 같은 모양으로 정규화: { key, stage, no, title, route, status, attempts, total }
 *  + 사용법 가이드 '지금 내 상태' 카드용 desc·guide·mastery·pass(서버가 보내는 값을 버리지 않고 싣는다). */
function normalizeRead(stages) {
  return (stages || []).filter((s) => s.stage >= 1 && READ_ROUTE[s.key]).map((s) => ({
    key: s.key, stage: s.stage, no: s.stage, title: s.title, route: READ_ROUTE[s.key],
    status: s.status, attempts: s.attempts ?? 0, total: s.min_attempts || READ_TOTAL[s.key] || 8,
    desc: s.desc || '', mastery: s.mastery ?? null, pass: s.pass ?? null,
  }))
}
// 발화는 0단계(발성)부터 싣는다 — 백엔드가 0단계를 항상 열고 N단계는 N-1 숙달 시 해금하므로
// 빼면 새 사용자의 첫 노드가 잠긴 1단계가 된다. 표시 번호(no)는 1부터.
function normalizeSpeak(stages) {
  return (stages || []).map((s, i) => ({
    key: `speak-${s.stage}`, stage: s.stage, no: i + 1, title: s.title, route: `/learn/speaking?stage=${s.stage}`,
    status: s.status, attempts: s.attempts ?? 0, total: s.min_attempts || 8,
    desc: s.desc || '', guide: s.guide || '', mastery: s.mastery ?? null, pass: s.pass ?? null,
    probe: s.probe || null, gain: s.gain || null,   // 모음·자음 낱말 속 확인, 4·5단계 개인 향상 경로(speak_curriculum)
  }))
}

// 소리 듣기(청능훈련)도 0단계(소리 확인)부터. 단계마다 숙달 방식이 달라 진행 글과 막대를 단계별로 정한다(backend listen_curriculum):
//  - 0 소리 확인: 한 번 하면 숙달(매일 점검용) → '확인 n번', 막대는 했으면 가득
//  - 1·2 수준 단계: 맨 위 수준에서 10번 중 9·8번 → '수준 L / N', 막대는 수준 비율(시작 전은 '시작 전')
//  - 3·5 이동 평균 단계: 최소 시도 10·12번 → 'n / 최소', 시도를 채웠는데 숙달 전이면 '숙달 중'(경로 공통 규칙)
//  - 4 소음 속 듣기: 역치 기준 → 역치가 있으면 '역치 +x dB', 막대는 최소 20번 대비 시도
const LISTEN_TOTAL = { 0: 1, 1: 10, 2: 10, 3: 10, 4: 20, 5: 12 }
function listenProgress(s) {
  const attempts = s.attempts ?? 0
  if (s.stage === 0) return attempts ? { progText: `확인 ${attempts}번`, progPct: 100 } : { progText: '시작 전', progPct: 0 }
  if (s.status === 'mastered') return { progText: s.level ? `수준 ${s.level} / ${s.levels}` : '숙달', progPct: 100 }
  if (s.levels || s.level) {
    if (!s.level) return { progText: '시작 전', progPct: 0 }
    return { progText: `수준 ${s.level} / ${s.levels}`, progPct: Math.round((s.level / s.levels) * 100) }
  }
  if (s.srt_db != null) {
    return { progText: `역치 ${s.srt_db > 0 ? '+' : ''}${s.srt_db} dB`, progPct: Math.min(100, (attempts / LISTEN_TOTAL[4]) * 100) }
  }
  return {}
}
function normalizeListen(stages) {
  return (stages || []).map((s, i) => ({
    key: `listen-${s.stage}`, stage: s.stage, no: i + 1, title: s.title, route: `/learn/listening?stage=${s.stage}`,
    status: s.status, attempts: s.attempts ?? 0, total: LISTEN_TOTAL[s.stage] || 10,
    desc: s.desc || '', guide: s.guide || '', mastery: null, pass: null,
    ...listenProgress(s),
  }))
}

export default function CurriculumPath() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const track = TRACKS.includes(searchParams.get('track')) ? searchParams.get('track') : 'read'
  const [data, setData] = useState({ read: null, speak: null, listen: null })
  const [failed, setFailed] = useState({ read: false, speak: false, listen: false })   // 트랙별 단계 조회 실패(빈 경로 대신 다시 불러오기)
  const [skipTarget, setSkipTarget] = useState(null)  // 건너뛰기 확인 중인 단계 key
  const [viewIdx, setViewIdx] = useState(null)        // 화살표로 보고 있는 단계(null = 현재 단계)
  const [guideOpen, setGuideOpen] = useState(false)
  const closeGuide = useCallback(() => setGuideOpen(false), [])
  const [today, setToday] = useState(null)   // 소리 듣기 오늘의 회기({target_min, done_today}), 못 받으면 null
  useEffect(() => {
    if (track !== 'listen') return undefined
    let on = true
    listenAPI.today().then((t) => { if (on) setToday(t) }).catch(() => { if (on) setToday(null) })
    return () => { on = false }
  }, [track])

  // 두 트랙을 한 번에 받아 두면 스위처 전환이 즉시 된다. 건너뛴 뒤에도 같은 함수로 다시 받는다.
  const load = useCallback(() => Promise.all([
    curriculumAPI.getStages().then((d) => {
      setData((p) => ({ ...p, read: normalizeRead(d.stages), readTrack: d.track }))
      setFailed((f) => ({ ...f, read: false }))
    }).catch(() => {
      setData((p) => ({ ...p, read: p.read || [] }))
      setFailed((f) => ({ ...f, read: true }))
    }),
    speakAPI.getCurriculum().then((d) => {
      setData((p) => ({ ...p, speak: normalizeSpeak(d.stages) }))
      setFailed((f) => ({ ...f, speak: false }))
    }).catch(() => {
      setData((p) => ({ ...p, speak: p.speak || [] }))
      setFailed((f) => ({ ...f, speak: true }))
    }),
    listenAPI.getCurriculum().then((d) => {
      setData((p) => ({ ...p, listen: normalizeListen(d.stages) }))
      setFailed((f) => ({ ...f, listen: false }))
    }).catch(() => {
      setData((p) => ({ ...p, listen: p.listen || [] }))
      setFailed((f) => ({ ...f, listen: true }))
    }),
  ]), [])
  // 다시 불러오기: 보고 있는 트랙을 로딩으로 돌리고 두 트랙을 다시 받는다
  const retry = () => { setData((p) => ({ ...p, [track]: null })); load() }
  useEffect(() => { load() }, [load])
  useEffect(() => { setSkipTarget(null); setViewIdx(null) }, [track])

  const learn = data[track]
  // 데이터 로딩 = 기본 로딩(§4-10 256:34 / 모바일 256:48)
  if (!learn) return <LoadingScreen />

  const list = learn
  // 현재 단계 = 열린 단계 중 가장 뒤(건너뛰기로 연 단계가 현재가 된다). 그 앞의 열린 단계는 지나온 단계로 보인다.
  const openIdx = list.map((s, i) => (s.status === 'in_progress' || s.status === 'unlocked' ? i : -1)).filter((i) => i >= 0)
  const currentIdx = openIdx.length ? openIdx[openIdx.length - 1] : -1
  const nextLockedIdx = currentIdx >= 0 ? currentIdx + 1 : list.findIndex((s) => s.status === 'locked')
  const nodeStatus = (s, i) => {
    if (s.status === 'mastered') return 'mastered'
    if (i === currentIdx) return 'current'
    if (i < currentIdx && s.status !== 'locked') return 'mastered'   // 건너뛰고 지나온 단계
    if (i === nextLockedIdx && s.status === 'locked') return 'skip'   // 다음 잠긴 단계 = 건너뛰기 후보
    return 'locked'
  }
  const vIdx = Math.min(list.length - 1, Math.max(0, viewIdx ?? (currentIdx >= 0 ? currentIdx : 0)))
  const view = list[vIdx]
  const viewStatus = view ? nodeStatus(view, vIdx) : 'locked'
  const viewOpen = viewStatus === 'mastered' || viewStatus === 'current'   // 레슨 카드를 띄울 수 있는 단계
  const progTotal = view?.total || 8
  const progCur = Math.min(progTotal, view?.attempts ?? 0)
  // 진행률은 숙달 최소 시도 대비 시도 수다. 시도를 다 채워도 정답률이 모자라면 아직 숙달 전이라(서버 _bump_stage_progress),
  // 그때는 막대를 끝까지 채우지 않고 수 대신 '숙달 중'으로 적는다(경로 노드가 완료로 보이는 단계는 그대로 둔다).
  const progPending = viewStatus !== 'mastered' && progCur >= progTotal
  const progLabel = view?.progText || (progPending ? '숙달 중' : `${progCur} / ${progTotal}`)
  const progPct = view?.progPct ?? (progPending ? 90 : (progCur / progTotal) * 100)
  const loadFailed = list.length === 0 && failed[track]   // 단계를 못 받아 빈 경로 → 안내와 다시 불러오기
  const startLabel = (view?.attempts ?? 0) === 0 ? '학습 시작하기' : '이어서 학습하기'   // 80:6 / 58:11
  const skipStage = list.find((s) => s.key === skipTarget) || null
  // 뜻 없는 말 짝 맞추기(C10): 1·2단계 사이의 하루 10분 과제. 2단계가 열린 뒤 1·2단계 카드에 보조 버튼으로 둔다(숙달에는 들어가지 않음)
  const wordStage = track === 'read' ? list.find((s) => s.key === 'word') : null
  const showNonsense = !!wordStage && wordStage.status !== 'locked' && (view?.key === 'viseme' || view?.key === 'word')
  // 소리 듣기: 단계를 하나라도 열었으면 오늘의 듣기(블록 회기)를 보조 버튼으로 둔다. 오늘 한 분을 함께 적는다
  const showToday = track === 'listen' && list.some((s) => s.status !== 'locked')
  const todayMin = goalMinutes(today?.done_today?.minutes)   // 과제 '소리 듣기 15분'처럼 내림(반올림하면 14.6분이 15 / 15로 보였다)
  const todayGoal = today?.target_min || 15
  const extraBtn = (cls) => (showNonsense ? (
    <button type="button" onClick={() => navigate('/learn/nonsense')} className={`btn-secondary w-full ${cls}`}>
      뜻 없는 말 짝 맞추기 <span className="font-normal text-ink-muted">· 하루 10분</span>
    </button>
  ) : showToday ? (
    <button type="button" onClick={() => navigate('/listen/today')} className={`btn-secondary w-full text-track-dark ${cls}`}>
      오늘의 듣기 <span className="font-normal text-ink-muted">· {todayMin > 0 ? `${Math.min(todayMin, todayGoal)} / ${todayGoal}분` : `하루 ${todayGoal}분`}</span>
    </button>
  ) : null)
  const hasExtra = showNonsense || showToday

  // 사용법 가이드는 지금 트랙의 레슨 탭으로 열고, 그 탭 맨 위에 보고 있는 단계의 상태를 보여 준다(가이드 점검 4절 A안).
  const guideTab = track === 'speak' ? 'speaking' : track === 'listen' ? 'listening' : 'reading'
  const nextIdx = vIdx + 1
  const nextStage = list[nextIdx] || null
  const nextSt = nextStage ? nodeStatus(nextStage, nextIdx) : null
  const viewLabel = viewStatus === 'mastered' ? (view?.status === 'mastered' ? '숙달' : '지나온 단계')
    : viewStatus === 'current' ? (progPending ? '숙달 중' : (view?.attempts ?? 0) === 0 ? '시작 전' : '진행 중')
      : viewStatus === 'skip' ? '건너뛸 수 있음' : '잠김'
  const guideContext = view ? {
    tab: guideTab, track, trackLabel: TRACK_LABEL[track], no: view.no, title: view.title, desc: view.desc, guide: view.guide,
    statusLabel: viewLabel, open: viewOpen, progLabel, progPct,
    minAttempts: view.total, mastery: view.mastery, pass: view.pass, probe: view.probe, gain: view.gain,
    next: nextStage && {
      no: nextStage.no, title: nextStage.title,
      open: nextSt === 'mastered' || nextSt === 'current', skip: nextSt === 'skip',
    },
  } : null

  const switchTrack = (k) => setSearchParams(k === 'read' ? {} : { track: k }, { replace: true })
  const doSkip = async (s) => {
    try {
      if (track === 'read') await curriculumAPI.setTrack(data.readTrack || 'perception', s.stage)   // 학습자의 트랙은 그대로
      else if (track === 'listen') await listenAPI.skip(s.stage)
      else await speakAPI.skip(s.stage)
    } catch { /* 실패하면 잠긴 채로 둔다(다시 받은 상태가 그대로 보인다) */ }
    setSkipTarget(null)
    setViewIdx(null)
    await load()
  }
  const go = (d) => { setSkipTarget(null); setViewIdx(Math.min(list.length - 1, Math.max(0, vIdx + d))) }

  return (
    <AppShell active="learn">
      <div className="mx-auto flex w-full max-w-[752px] flex-col items-center gap-3.5 lg:gap-6">
        {/* 트랙 스위처(171:18 / 모바일 233:34 전체 폭) */}
        <div className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1 lg:w-auto lg:rounded-14">
          {Object.entries(TRACK_LABEL).map(([k, label]) => (
            <button key={k} type="button" onClick={() => switchTrack(k)} aria-pressed={track === k}
              className={`flex-1 rounded-10 py-[9px] text-[14px] font-bold leading-figma transition lg:flex-none lg:px-[26px] lg:py-2.5 lg:text-[15px] ${
                track === k ? 'bg-white text-track shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]' : 'text-ink-faint'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* 유닛 헤더(61:12 / 모바일 233:39) — 트랙색 + 3D 하단테두리 + 가이드(사용법 가이드 모달) */}
        <div className="flex w-full items-center gap-3.5 rounded-16 border-b-4 border-track-dark bg-track py-[15px] pl-[17px] pr-[13px] text-white lg:rounded-18 lg:border-b-5 lg:py-5 lg:pl-[26px] lg:pr-5">
          <div className="flex min-w-0 flex-1 flex-col gap-[3px] font-bold leading-figma lg:gap-1">
            <span className="text-[11px] opacity-[0.85] lg:text-[13px]">{TRACK_LABEL[track]} · {view ? `${view.no}단계` : '학습'}</span>
            <span className="truncate text-[18px] tracking-[-0.36px] lg:text-[24px] lg:tracking-[-0.48px]">{view?.title || '커리큘럼'}</span>
          </div>
          <button type="button" onClick={() => setGuideOpen(true)}
            className="shrink-0 rounded-10 border-1.5 border-white/35 bg-white/[0.18] px-3 py-[7px] text-[12px] font-bold leading-figma text-white transition hover:bg-white/30 lg:rounded-[12px] lg:border-2 lg:border-white/40 lg:px-[18px] lg:py-3 lg:text-[14px]">
            가이드
          </button>
        </div>

        {/* 소리 듣기: 진단·치료가 아니라는 안내(설계 8절, 첫 화면과 결과에 둔다)와 결과 화면으로 가는 길 */}
        {track === 'listen' && !loadFailed && (
          <div className="flex w-full items-center justify-between gap-3 rounded-14 bg-surface-sunken px-4 py-2.5">
            <p className="min-w-0 break-keep text-[12px] leading-[1.6] text-ink-muted lg:text-[13px]">소리 듣기는 청력을 진단하거나 치료하지 않아요.</p>
            <div className="flex shrink-0 items-center">
              <button type="button" onClick={() => navigate('/listen/classroom')}
                className="min-h-[44px] rounded-10 px-2 text-[13px] font-bold text-track-dark hover:underline">소리 교실</button>
              <span aria-hidden className="h-3 w-px bg-line-strong" />
              <button type="button" onClick={() => navigate('/analysis/listening')}
                className="min-h-[44px] rounded-10 px-2 text-[13px] font-bold text-track-dark hover:underline">결과 보기</button>
            </div>
          </div>
        )}

        {/* 지연 유지 검사(C7): 사후 검사 뒤 정해진 날수가 지났을 때만 조용히 권한다(막지 않음, 볼 때가 아니면 그리지 않음) */}
        <RetentionPrompt />

        {/* 단계를 불러오지 못했으면 빈 경로 대신 안내와 다시 불러오기(여러 명 대화의 실패 카드와 같은 모양) */}
        {loadFailed && (
          <div className="card flex w-full flex-col items-center gap-3 py-16 text-center">
            <p role="alert" className="text-[15px] font-bold text-ink">학습 경로를 불러오지 못했어요.</p>
            <button type="button" onClick={retry} className="btn-primary">다시 불러오기</button>
          </div>
        )}

        {/* 경로(61:18 / 모바일 233:45) — 모바일은 가운데, 데스크톱은 왼쪽(x 130)에 노드 열을 두고 오른쪽에 카드 */}
        <div className={`relative w-full py-2 ${hasExtra ? 'max-lg:pb-[226px]' : 'max-lg:pb-[170px]'} ${loadFailed ? 'hidden' : ''}`}
          style={{ '--arrow-top': `${8 + vIdx * PITCH_MOBILE + 9}px` }}>
          {list.length > 1 && (
            <>
              <StageArrow dir="prev" track={track} disabled={vIdx <= 0} onClick={() => go(-1)} />
              <StageArrow dir="next" track={track} disabled={vIdx >= list.length - 1} onClick={() => go(1)} />
            </>
          )}

          <div className="mx-auto flex w-[56px] flex-col items-center lg:mx-0 lg:ml-[130px] lg:w-[76px]">
            {list.map((s, i) => {
              const st = nodeStatus(s, i)
              const clickable = st !== 'locked'
              const onClick = () => {
                if (st === 'skip') { setViewIdx(i); setSkipTarget(s.key) }
                else if (clickable) navigate(s.route)
              }
              return (
                <Fragment key={s.key}>
                  {i > 0 && <DokaConnector done={list[i - 1].status === 'mastered'} />}
                  <div className="relative">
                    <button type="button" disabled={!clickable} onClick={onClick}
                      aria-label={`${s.no}단계 ${s.title}${st === 'mastered' ? ' 완료' : st === 'current' ? ' 진행 중' : st === 'skip' ? ' 건너뛰기 가능' : ' 잠김'}`}
                      className={clickable ? 'block cursor-pointer' : 'block cursor-not-allowed'}>
                      <DokaNode status={st} track={track} />
                    </button>

                    {/* 건너뛰기 말풍선(78:131) — 같은 경로 위 현재 노드를 가리지 않게 노드 오른쪽에 둔다 */}
                    {st === 'skip' && skipTarget !== s.key && (
                      <button type="button" onClick={() => { setViewIdx(i); setSkipTarget(s.key) }}
                        className="absolute left-full top-1/2 z-10 ml-4 -translate-y-1/2 whitespace-nowrap rounded-13 border-2 border-line bg-white px-2.5 py-2 text-[12px] font-bold leading-figma text-track-dark shadow-[0px_6px_16px_-2px_rgba(26,13,64,0.1)] lg:ml-[34px] lg:rounded-14 lg:px-5 lg:py-3 lg:text-[15px]">
                        여기로 건너뛸까요?
                        <TailLeft className="left-[-15px] top-1/2 -translate-y-1/2" />
                      </button>
                    )}

                    {/* 건너뛰기 확인(79:100) — 데스크톱은 노드 오른쪽 팝오버, 모바일은 아래 시트 */}
                    {st === 'skip' && skipTarget === s.key && (
                      <div className="absolute left-full z-20 ml-[34px] hidden w-[360px] flex-col gap-3.5 rounded-20 border-2 border-warn bg-white p-6 shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)] lg:flex"
                        style={{ bottom: 'calc(50% - 21.5px)' }}>
                        <TailLeft className="bottom-[8.5px] left-[-15px]" edgeClass="text-warn" />
                        <p className="text-[21px] font-bold leading-figma tracking-[-0.42px] text-ink">정말로 건너뛰시겠어요?</p>
                        <div className="flex gap-2.5">
                          <button type="button" onClick={() => setSkipTarget(null)} className="btn-secondary flex-1 whitespace-nowrap px-2 py-[15px] text-[16px]">아니오</button>
                          <button type="button" onClick={() => doSkip(s)} className="btn-primary flex-1 whitespace-nowrap px-2 py-[15px] text-[16px]">예, 건너뛸게요</button>
                        </div>
                      </div>
                    )}

                    {/* 레슨 카드(75:12 · 80:115) — 보고 있는 단계 노드 오른쪽(데스크톱). 모바일은 아래 시트. */}
                    {i === vIdx && viewOpen && (
                      <div className="absolute left-full z-10 ml-[34px] hidden w-[360px] flex-col gap-3.5 rounded-20 border-2 border-line bg-white px-6 py-[22px] shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)] lg:flex"
                        style={{ bottom: hasExtra ? 'calc(50% - 100.5px)' : 'calc(50% - 37.5px)' }}>
                        {/* 짝 맞추기 버튼(높이 49 + 간격 14)이 붙으면 카드가 위 배너를 덮지 않게 아래로 늘리고 꼬리도 그만큼 올린다 */}
                        <TailLeft className={`${hasExtra ? 'bottom-[87.5px]' : 'bottom-[24.5px]'} left-[-15px]`} />
                        <p className="text-[22px] font-bold leading-figma tracking-[-0.44px] text-ink">{s.title}</p>
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center justify-between text-[13px] font-bold leading-figma">
                            <span className="text-ink-muted">진행률</span>
                            <span className="text-track">{progLabel}</span>
                          </div>
                          <div className="h-[10px] overflow-hidden rounded-full bg-fill">
                            <div className="h-full rounded-full bg-track" style={{ width: `${progPct}%` }} />
                          </div>
                        </div>
                        {/* 처음이면 80:125 "학습 시작하기"(r15·py17·17px), 이어서면 75:23 "이어서 학습하기"(btn-lg) */}
                        <button type="button" onClick={() => navigate(s.route)}
                          className={(s.attempts ?? 0) === 0 ? 'btn-primary w-full rounded-15 py-[17px] text-[17px]' : 'btn-primary btn-lg w-full'}>
                          {startLabel}
                        </button>
                        {extraBtn('py-3 text-[15px]')}
                      </div>
                    )}
                  </div>
                </Fragment>
              )
            })}
          </div>
        </div>

        {/* 레슨 시트(모바일 233:61) — 탭 바 바로 위. 건너뛰기 확인 중이면 확인(79:100)을 이 자리에 띄운다. */}
        {skipStage ? (
          <div className="fixed inset-x-0 bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] z-20 flex flex-col gap-[11px] rounded-t-22 border-t-2 border-warn bg-white px-[18px] pb-5 pt-[18px] shadow-sheet lg:hidden">
            <p className="text-[17px] font-bold leading-figma text-ink">정말로 건너뛰시겠어요?</p>
            <div className="flex gap-2.5">
              <button type="button" onClick={() => setSkipTarget(null)} className="btn-secondary flex-1 whitespace-nowrap px-2 py-4 text-[16px]">아니오</button>
              <button type="button" onClick={() => doSkip(skipStage)} className="btn-primary flex-1 whitespace-nowrap px-2 py-4 text-[16px]">예, 건너뛸게요</button>
            </div>
          </div>
        ) : view && viewOpen && (
          <div className="fixed inset-x-0 bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] z-20 flex flex-col gap-[11px] rounded-t-22 border-t-2 border-line bg-white px-[18px] pb-5 pt-[18px] shadow-sheet lg:hidden">
            <div className="flex items-center justify-between gap-3 font-bold leading-figma">
              <p className="min-w-0 truncate text-[17px] text-ink">{view.title}</p>
              <span className="shrink-0 text-[13px] text-track">{progLabel}</span>
            </div>
            <div className="h-[9px] overflow-hidden rounded-full bg-fill">
              <div className="h-full rounded-full bg-track" style={{ width: `${progPct}%` }} />
            </div>
            <button type="button" onClick={() => navigate(view.route)} className="btn-primary w-full py-4 text-[16px]">{startLabel}</button>
            {extraBtn('py-3 text-[15px]')}
          </div>
        )}
      </div>

      <GuideModal open={guideOpen} onClose={closeGuide} initialKey={guideTab} context={guideContext} />
    </AppShell>
  )
}
