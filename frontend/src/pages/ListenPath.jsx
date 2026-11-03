import { lsGet, lsSet } from '../lib/safeStorage'
import LearnHeader from '../components/learn/LearnHeader'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { DOKA_ASSETS } from '../components/DokaNode'
import LearnExtras from '../components/learn/LearnExtras'
import { Row, RowList, SectionTitle, StageMark } from '../components/learn/LearnRows'
import GuideModal from '../components/GuideModal'
import Modal from '../components/Modal'
import ListenNotice from '../components/listen/ListenNotice'
import { QuotaBar } from '../components/listen/QuotaProgress'
import { listenAPI } from '../api'
import { kstDate, quotaView, recommendedStage } from '../lib/listenQuota'

export default function ListenPath() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [notice, setNotice] = useState(() => lsGet('liplab_listen_notice') !== '1')
  const [guide, setGuide] = useState(false)
  const [retry, setRetry] = useState(0)
  const [skip, setSkip] = useState(false)
  const [skipping, setSkipping] = useState(false)
  const [skipError, setSkipError] = useState(false)
  useEffect(() => {
    let live = true
    listenAPI.getCurriculum().then((d) => { if (live) { setData(d); setError(false) } }).catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [retry])
  const rec = recommendedStage(data)
  const stages = data?.stages || []
  const index = stages.findIndex((s) => s.stage === (params.has('stage') ? Number(params.get('stage')) : rec))
  const stage = stages[index < 0 ? 0 : index]
  const q = quotaView(stage?.quota)
  const locked = stage?.status === 'locked'
  const closeNotice = () => { lsSet('liplab_listen_notice', '1'); setNotice(false) }
  const start = () => navigate(`/learn/listening?stage=${stage.stage}`)
  const doSkip = async () => {
    setSkipping(true); setSkipError(false)
    try { await listenAPI.skip(stage.stage); setSkip(false); setRetry((n) => n + 1) }
    catch { setSkipError(true) }
    finally { setSkipping(false) }
  }
  const pastDays = (stage?.quota?.days || []).filter((d) => d.date < kstDate() && d.met).length
  const pick = (st) => { setParams({ track: 'listen', stage: st.stage }, { replace: true }); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  // 11/03: 날짜 길(지나온 날·오늘·내일·숙달 노드)과 고정 시트를 '지금 단계' 카드 하나와 단계 목록으로 바꿨다. 버튼과 동작은 그대로다.
  return <AppShell active="learn">
    <div className="learn-hub mx-auto grid w-full max-w-[1120px] grid-cols-1 gap-5 lg:gap-6 min-[1180px]:grid-cols-[minmax(0,1fr)_360px] min-[1180px]:gap-x-8">
      <div className="min-[1180px]:col-span-2"><LearnHeader /></div>
      <div className="flex min-w-0 flex-col gap-5 lg:gap-6">
        {error ? <div role="alert" className="rounded-16 border border-line bg-white p-5"><h1 className="text-[17px] font-bold">경로를 가져오지 못했어요</h1><button className="btn-secondary btn-md mt-3" onClick={() => setRetry((n) => n + 1)}>다시 가져오기</button></div> : !stage ? <p role="status" className="text-ink-muted">불러오는 중…</p> : <>
          <section aria-labelledby="learn-now" className="flex flex-col gap-4 rounded-16 border border-line bg-white p-5 lg:gap-5 lg:p-7">
            <div className="flex items-center gap-4">
              <span className="relative size-[56px] shrink-0 lg:size-[72px]" aria-hidden>
                <img src={locked ? DOKA_ASSETS.locked : DOKA_ASSETS.listen.current} alt="" className="absolute max-w-none" style={{ top: '-7%', left: '-12%', width: '124%', height: '124%' }} />
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-1 leading-figma">
                <h1 id="learn-now" className="break-keep text-[22px] font-bold tracking-[-0.44px] text-ink lg:text-[28px] lg:tracking-[-0.56px]">{stage.title}</h1>
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[14px] text-ink-muted lg:text-[15px]">
                  <span>{stage.stage + 1}단계</span>
                  {stage.status === 'mastered' ? <span className="font-semibold text-good-text">✓ 숙달</span> : stage.levels ? <span role="img" aria-label={`연습 ${stage.level || 1}/${stage.levels}`} className="flex h-4 items-end gap-[3px]">{Array.from({ length: stage.levels }, (_, i) => i + 1).map((n) => <span key={n} className={`w-1.5 rounded-sm border border-track ${n <= (stage.level || 1) ? 'bg-track' : ''}`} style={{ height: `${n * 3 + 3}px` }} />)}</span> : null}
                  {pastDays > 0 && <span>· 지나온 날 {pastDays}일</span>}
                  {data?.is_demo ? <span className="rounded-full bg-track-tint px-2 py-0.5 text-[12px] font-semibold text-track-dark">체험용 · 모든 단계 열림</span> : data?.is_beta ? <span className="rounded-full bg-track-tint px-2 py-0.5 text-[12px] font-semibold text-track-dark">베타 · 모든 단계 열림</span> : null}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button className="btn-secondary px-3.5 py-2 text-[14px]" onClick={() => setGuide(true)}>가이드</button>
                <button className="btn-secondary size-11 p-0" aria-label="소리 듣기 안내" onClick={() => setNotice(true)}>
                  <svg aria-hidden viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" className="mx-auto size-5"><circle cx="10" cy="10" r="7.5" /><path d="M10 9v5M10 6.2v.1" /></svg>
                </button>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-[14px] font-semibold leading-figma">
                <span className="text-ink">오늘 몫 <span className="tabular-nums">{q.filled} / {q.total}</span></span>
                <span className="tabular-nums text-ink-muted">약 {Math.max(0, (q.total - q.filled) * 4)}분 남음</span>
              </div>
              <QuotaBar quota={stage.quota} />
            </div>

            <div className="flex flex-col gap-2.5 sm:flex-row sm:flex-wrap">
              <button id="listen-start" disabled={locked} onClick={q.met ? () => navigate('/records?track=listen') : start} className="btn-primary btn-lg w-full sm:w-auto sm:min-w-[220px]">{locked ? '잠김' : q.met ? '결과 보기' : q.done || stage.quota?.partial_n ? `다음 묶음 듣기 (${q.filled + 1}/${q.total})` : '오늘 몫 시작하기'}</button>
              {locked && <button onClick={() => setSkip(true)} className="btn-secondary btn-md">건너뛰기</button>}
              {q.met && <button onClick={start} className="btn-secondary btn-md">한 묶음 더 하기</button>}
              <button onClick={() => navigate('/learn/listening?stage=0')} className="btn-secondary btn-md text-track-dark">{data.ling_today ? '✓ 소리 확인' : '소리 확인 · 1분'}</button>
              {stage.stage === 4 && <button className="btn-secondary btn-md text-track-dark" onClick={() => navigate('/learn/listening?stage=4&test=1')}>처음 검사</button>}
            </div>
            {data.placement?.available && !data.placement?.completed && <button className="btn-secondary btn-md w-full" onClick={() => navigate('/learn/listening?placement=1')}>시작 단계 정하기</button>}
          </section>

          <section aria-labelledby="learn-stages" className="flex flex-col gap-2.5">
            <SectionTitle id="learn-stages" aside={<span className="text-[13px] font-semibold tabular-nums text-ink-muted">{stages.filter((s) => s.status === 'mastered').length} / {stages.length} 숙달</span>}>전체 단계</SectionTitle>
            <RowList label="전체 단계">
              {stages.map((s) => {
                const isView = s.stage === stage.stage
                const mark = s.status === 'mastered' ? 'mastered' : s.status === 'locked' ? 'locked' : isView ? 'current' : 'open'
                return <Row key={s.stage}
                  lead={<StageMark status={mark} no={s.stage + 1} />}
                  title={`${s.stage + 1}. ${s.title}`}
                  desc={s.desc}
                  meta={isView ? '보는 중' : s.status === 'mastered' ? '숙달' : s.status === 'locked' ? '잠김' : s.stage === rec ? '추천' : null}
                  metaClass={isView || s.stage === rec ? 'text-track-dark' : 'text-ink-muted'}
                  current={isView}
                  onClick={isView ? undefined : () => pick(s)} />
              })}
            </RowList>
          </section>
        </>}
      </div>
      <aside className="flex min-w-0 flex-col gap-5 lg:gap-6" aria-label="연습과 자료">
        <LearnExtras track="listen" />
      </aside>
      {guide && <GuideModal open onClose={() => setGuide(false)} initialKey="listening" />}
      <Modal open={skip} onClose={() => { if (!skipping) setSkip(false) }} title="정말로 건너뛰시겠어요?" cardClass="border border-warn">
        {skipError && <p role="alert" className="text-[14px] text-bad-text">단계를 열지 못했어요</p>}
        <div className="flex gap-2.5"><button disabled={skipping} onClick={() => setSkip(false)} className="btn-secondary btn-md flex-1">아니오</button><button disabled={skipping} onClick={doSkip} className="btn-primary btn-md flex-1">{skipping ? '여는 중' : '예, 건너뛸게요'}</button></div>
      </Modal>
      {notice && <ListenNotice onClose={closeNotice} />}
    </div>
  </AppShell>
}
