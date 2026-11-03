import LearnHeader from '../components/learn/LearnHeader'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { DOKA_ASSETS } from '../components/DokaNode'
import LearnExtras from '../components/learn/LearnExtras'
import { Row, RowList, SectionTitle, StageMark } from '../components/learn/LearnRows'
import GuideModal from '../components/GuideModal'
import LoadingScreen from '../components/LoadingScreen'
import RetentionPrompt from '../components/RetentionPrompt'
import { curriculumAPI, speakAPI, listenAPI } from '../api'
import { goalMinutes } from '../lib/listenFlow'
import { pathNodeState } from '../lib/pathNodes'

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
import { TRACK_LABEL } from '../lib/iaLabels'
import { normalizeRead, normalizeSpeak } from '../lib/trackPath'
const TRACKS = Object.keys(TRACK_LABEL)

/** 두 트랙의 단계 목록을 같은 모양으로 정규화: { key, stage, no, title, route, status, attempts, total }
 *  + 사용법 가이드 '지금 내 상태' 카드용 desc·guide·mastery·pass(서버가 보내는 값을 버리지 않고 싣는다). */
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
      setData((p) => ({ ...p, listen: normalizeListen(d.stages), listenPlacement: d.placement || null }))
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
  // 현재 단계·노드 상태(lib/pathNodes): 열린 단계 중 가장 뒤가 현재, 그 앞의 열린 단계는 지나온 단계(✓). 소리 듣기는 숙달 전인 앞의 열린 단계를
  // ✓ 대신 열린 단계로 둔다(시작 단계 정하기가 1·2단계를 진행 중으로, 3~k단계를 열린 채로 둔다).
  const { currentIdx, nodeStatus } = pathNodeState(list, track)
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
  const showNonsense = false
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

  const open = (s) => navigate(s.route, { state: track === 'read' && s.stage >= 3 ? { from: 'path' } : undefined })
  // 단계 행의 오른쪽 상태 글자: 숙달 · 진행(n / 최소 시도) · 건너뛰기 · 잠김
  const rowMeta = (s, st) => {
    if (st === 'mastered') return s.status === 'mastered' ? '숙달' : '지나옴'
    if (st === 'current') {
      const total = s.total || 8
      const cur = Math.min(total, s.attempts ?? 0)
      return s.progText || (cur >= total ? '숙달 중' : cur === 0 ? '시작 전' : `${cur} / ${total}`)
    }
    if (st === 'skip') return '건너뛰기'
    return '잠김'
  }

  return (
    <AppShell active="learn">
      <div className="learn-hub mx-auto grid w-full max-w-[1120px] grid-cols-1 gap-5 lg:gap-6 min-[1180px]:grid-cols-[minmax(0,1fr)_360px] min-[1180px]:gap-x-8">
        <div className="min-[1180px]:col-span-2"><LearnHeader /></div>
        <h1 className="sr-only">{TRACK_LABEL[track]}</h1>

        <div className="flex min-w-0 flex-col gap-5 lg:gap-6">
          {/* 지연 유지 검사(C7): 볼 때가 아니면 그리지 않는다 */}
          <RetentionPrompt />

          {loadFailed ? (
            <div className="card flex w-full flex-col items-center gap-3 py-16 text-center">
              <p role="alert" className="text-[15px] font-bold text-ink">학습 단계를 가져오지 못했어요.</p>
              <button type="button" onClick={retry} className="btn-primary">다시 가져오기</button>
            </div>
          ) : view && (
            /* 지금 할 단계(11/03): 예전 경로의 레슨 카드·모바일 시트를 화면 맨 위 카드 하나로 합쳤다 */
            <section aria-labelledby="learn-now" className="flex flex-col gap-4 rounded-16 border border-line bg-white p-5 lg:gap-5 lg:p-7">
              <div className="flex items-center gap-4">
                {/* 마스코트(DOKA)는 지금 단계 카드에 하나만 크게 둔다. 그림은 그림자 여백까지 담아 칸보다 크다 */}
                <span className="relative size-[56px] shrink-0 lg:size-[72px]" aria-hidden>
                  <img src={viewOpen ? (DOKA_ASSETS[track] || DOKA_ASSETS.read).current : DOKA_ASSETS.locked} alt="" className="absolute max-w-none" style={{ top: '-7%', left: '-12%', width: '124%', height: '124%' }} />
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-1 leading-figma">
                  <h2 id="learn-now" className="break-keep text-[22px] font-bold tracking-[-0.44px] text-ink lg:text-[28px] lg:tracking-[-0.56px]">{view.title}</h2>
                  <p className="text-[14px] text-ink-muted lg:text-[15px]">{view.no}단계 · {viewLabel}{view.desc ? ` · ${view.desc}` : ''}</p>
                </div>
                <button type="button" onClick={() => setGuideOpen(true)} className="btn-secondary shrink-0 px-3.5 py-2 text-[14px]">가이드</button>
              </div>
              {viewOpen ? (
                <>
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between text-[14px] font-semibold leading-figma">
                      <span className="text-ink-muted">진행률</span>
                      <span className="tabular-nums text-track-dark">{progLabel}</span>
                    </div>
                    <div role="progressbar" aria-label={`${view.title} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progPct)} aria-valuetext={progLabel} className="h-2.5 overflow-hidden rounded-full bg-fill">
                      <div className="h-full rounded-full bg-track" style={{ width: `${progPct}%` }} />
                    </div>
                  </div>
                  <div className="flex flex-col gap-2.5 sm:flex-row">
                    <button type="button" onClick={() => open(view)} className="btn-primary btn-lg w-full sm:w-auto sm:min-w-[220px]">{startLabel}</button>
                    {extraBtn('sm:w-auto py-3 text-[15px]')}
                  </div>
                </>
              ) : (
                <p className="text-[14px] text-ink-muted">앞 단계를 마치면 열려요.</p>
              )}
            </section>
          )}

          {!loadFailed && list.length > 0 && (
            <section aria-labelledby="learn-stages" className="flex flex-col gap-2.5">
              <SectionTitle id="learn-stages" aside={<span className="text-[13px] font-semibold tabular-nums text-ink-muted">{list.filter((s) => s.status === 'mastered').length} / {list.length} 숙달</span>}>전체 단계</SectionTitle>
              <RowList label="전체 단계">
                {list.map((s, i) => {
                  const st = nodeStatus(s, i)
                  const confirming = st === 'skip' && skipTarget === s.key
                  return (
                    <Row key={s.key}
                      lead={<StageMark status={st} no={s.no} />}
                      title={`${s.no}. ${s.title}`}
                      desc={s.desc}
                      meta={rowMeta(s, st)}
                      metaClass={st === 'current' ? 'text-track-dark' : st === 'skip' ? 'text-track-dark' : 'text-ink-muted'}
                      current={st === 'current'}
                      onClick={st === 'locked' ? undefined : st === 'skip' ? () => setSkipTarget(confirming ? null : s.key) : () => open(s)}>
                      {/* 건너뛰기 확인: 그 행 바로 아래에 펼친다 */}
                      {confirming && (
                        <div className="flex flex-col gap-3 border-t border-warn/40 bg-warn-tint px-4 py-4 lg:px-5">
                          <p className="text-[15px] font-bold text-ink">정말로 건너뛰시겠어요?</p>
                          <div className="flex gap-2.5">
                            <button type="button" onClick={() => setSkipTarget(null)} className="btn-secondary btn-md flex-1">아니오</button>
                            <button type="button" onClick={() => doSkip(s)} className="btn-primary btn-md flex-1">예, 건너뛸게요</button>
                          </div>
                        </div>
                      )}
                    </Row>
                  )
                })}
              </RowList>
            </section>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-5 lg:gap-6" aria-label="연습과 자료">
          <LearnExtras track={track} />
        </aside>
      </div>

      <GuideModal open={guideOpen} onClose={closeGuide} initialKey={guideTab} context={guideContext} />
    </AppShell>
  )
}
