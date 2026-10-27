import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import DokaNode from '../components/DokaNode'
import GuideModal from '../components/GuideModal'
import Modal from '../components/Modal'
import ListenNotice from '../components/listen/ListenNotice'
import { QuotaBar, QuotaRing } from '../components/listen/QuotaProgress'
import { listenAPI } from '../api'
import { kstDate, pathDays, quotaView, recommendedStage } from '../lib/listenQuota'

function DayNode({ label, state, quota, current, onClick }) {
  return <div className="flex flex-col items-center gap-1.5">
    <button disabled={!onClick} onClick={onClick} aria-label={`${label}${current ? `, 오늘 몫 ${quotaView(quota).done}/${quotaView(quota).total}` : ''}`}
      className={`relative flex items-center justify-center ${current ? 'size-[80px] lg:size-[109px]' : 'size-14 lg:size-[76px]'}`}>
      <DokaNode status={current ? 'current' : state} track="listen" />
      {current && <QuotaRing quota={quota} className="pointer-events-none absolute inset-0 size-full" />}
    </button>
    <span className={`text-[13px] ${current ? 'font-bold text-track-dark' : 'text-ink-muted'}`}>{label}</span>
  </div>
}

export default function ListenPath() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [notice, setNotice] = useState(() => localStorage.getItem('liplab_listen_notice') !== '1')
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
  const days = pathDays(stage?.quota, kstDate())
  const closeNotice = () => { localStorage.setItem('liplab_listen_notice', '1'); setNotice(false) }
  const start = () => navigate(`/learn/listening?stage=${stage.stage}`)
  const doSkip = async () => {
    setSkipping(true); setSkipError(false)
    try { await listenAPI.skip(stage.stage); setSkip(false); setRetry((n) => n + 1) }
    catch { setSkipError(true) }
    finally { setSkipping(false) }
  }
  return <AppShell active="learn">
    <div className="mx-auto flex w-full max-w-[752px] flex-col items-center gap-3 lg:gap-6">
      <div className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1 lg:w-auto">
        {[['read', '독화'], ['speak', '발화'], ['listen', '소리 듣기']].map(([key, label]) => <button key={key} aria-pressed={key === 'listen'} onClick={() => navigate(`/learn/path?track=${key}`)}
          className={`min-h-11 flex-1 rounded-10 px-4 text-[14px] font-bold lg:flex-none lg:px-[26px] ${key === 'listen' ? 'bg-white text-track shadow-seg' : 'text-ink-muted'}`}>{label}</button>)}
      </div>
      {data?.is_demo && <span className="self-start rounded-full bg-track-tint px-3 py-1.5 text-[12px] font-bold text-track-dark">체험용 · 모든 단계 열림</span>}
      {error ? <div role="alert" className="rounded-20 border-2 border-line bg-white p-5"><h1>경로를 가져오지 못했어요</h1><button className="btn-secondary btn-md mt-3" onClick={() => setRetry((n) => n + 1)}>다시 가져오기</button></div> : !stage ? <p role="status">불러오는 중</p> : <>
        <div className="flex min-h-[96px] w-full items-center justify-between gap-3 rounded-16 border-b-4 border-track-dark bg-track px-[18px] py-3.5 text-white lg:rounded-20 lg:p-6">
          <div className="flex min-w-0 flex-col gap-1"><span className="text-[12px] font-bold">소리 듣기 · {stage.stage + 1}단계</span><h1 className="text-[20px] font-black lg:text-[24px]">{stage.title}</h1>
            {stage.status === 'mastered' ? <span className="text-[12px] font-bold">✓ 숙달</span> : stage.levels ? <span role="img" aria-label={`연습 ${stage.level || 1}/${stage.levels}`} className="flex h-4 items-end gap-[3px]">{Array.from({ length: stage.levels }, (_, i) => i + 1).map((n) => <span key={n} className={`w-1.5 rounded-sm border border-white ${n <= (stage.level || 1) ? 'bg-white' : ''}`} style={{ height: `${n * 3 + 3}px` }} />)}</span> : null}
          </div>
          <div className="flex gap-2"><button className="min-h-11 rounded-14 border-2 border-white/50 px-3 text-[14px] font-bold" onClick={() => setGuide(true)}>가이드</button><button className="size-11 rounded-14 border-2 border-white/50 text-xl" aria-label="소리 듣기 안내" onClick={() => setNotice(true)}>ⓘ</button></div>
        </div>
        {data.placement?.available && !data.placement?.completed && <button className="btn-secondary btn-md w-full" onClick={() => navigate('/learn/listening?placement=1')}>시작 단계 정하기</button>}
        <div className="relative flex w-full justify-center pb-[285px] pt-1 lg:min-h-[550px] lg:justify-start lg:pb-5 lg:pl-[110px]" style={{ '--card-top': `${Math.max(0, days.length * 124 - 24)}px` }}>
          <div className="flex flex-col items-center">
            {days.length > 1 && <span className="mb-1 text-[13px] text-ink-muted lg:hidden">지나온 날 {stage.quota.days.filter((d) => d.date < kstDate() && d.met).length}일</span>}
            {days.map((day, i) => <div key={day.date} className={`${i < days.length - 1 ? 'hidden lg:flex' : 'flex'} flex-col items-center`}><DayNode label={day.date.slice(5).replace('-', '/')} state="mastered" /><span className="my-1 h-7 w-[5px] rounded-full bg-track lg:h-10" /></div>)}
            {stage.stage === 4 && <button className="btn-secondary btn-md mb-5 text-track-dark" onClick={() => navigate('/learn/listening?stage=4&test=1')}>◇ 처음 검사</button>}
            <div className="relative flex items-center">
              {['prev', 'next'].map((dir, i) => <button key={dir} aria-label={i ? '다음 단계' : '이전 단계'} disabled={i ? index >= stages.length - 1 : index <= 0}
                onClick={() => setParams({ track: 'listen', stage: stages[index + (i ? 1 : -1)].stage })}
                className={`absolute top-4 size-11 disabled:opacity-30 lg:top-7 ${i ? 'left-[115px] lg:left-[124px]' : 'right-[115px] lg:right-[100px]'}`}><img src={`/ui/listen-stage-arrow-${dir}.svg`} alt="" className="size-full" /></button>)}
              <DayNode label={locked ? `${stage.title} · 잠김` : '오늘'} quota={stage.quota} current={!locked && stage.stage === rec} state={locked ? 'locked' : q.met ? 'mastered' : 'skip'} onClick={locked ? () => setSkip(true) : () => document.getElementById('listen-start')?.focus()} />
            </div>
            <span className="my-1 h-7 w-[5px] rounded-full bg-fill-strong lg:h-10" /><DayNode label="내일" state="locked" />
            <span className="my-1 h-7 w-[5px] rounded-full bg-fill-strong lg:h-10" /><DayNode label="숙달" state={stage.status === 'mastered' ? 'mastered' : 'locked'} />
            <div className="mt-6 flex gap-4 text-[13px] font-bold text-track-dark"><button onClick={() => navigate('/listen/classroom')} className="min-h-11">소리 교실</button><button onClick={() => navigate('/analysis/listening')} className="min-h-11">결과 보기</button></div>
          </div>
          <section aria-label="오늘 몫" className="fixed inset-x-0 bottom-[var(--tabbar-h,78px)] z-20 flex flex-col gap-3 rounded-t-22 bg-white px-[18px] pb-2 pt-[18px] shadow-sheet lg:absolute lg:inset-x-auto lg:bottom-auto lg:left-[300px] lg:top-[var(--card-top)] lg:w-[310px] lg:rounded-20 lg:border-2 lg:border-line lg:p-5 lg:shadow-card">
            <div className="flex items-center justify-between gap-2"><h2 className="text-[20px] font-black">오늘 몫 {q.filled} / {q.total}</h2><button onClick={() => navigate('/learn/listening?stage=0')} className="btn-secondary min-h-11 px-2 text-[12px] text-track-dark">{data.ling_today ? '✓ 소리 확인' : '소리 확인 · 1분'}</button></div>
            <div className="flex items-center gap-3"><QuotaBar quota={stage.quota} /><span className="text-[14px] font-bold text-ink-muted">◷ {Math.max(0, (q.total - q.filled) * 4)}분</span></div>
            <button id="listen-start" disabled={locked} onClick={q.met ? () => navigate('/analysis/listening') : start} className="btn-primary min-h-[56px] w-full rounded-16 text-[17px]">{locked ? '잠김' : q.met ? '결과 보기' : q.done || stage.quota?.partial_n ? `다음 묶음 듣기 (${q.filled + 1}/${q.total})` : '오늘 몫 시작하기'}</button>
            {locked && <button onClick={() => setSkip(true)} className="btn-secondary btn-md">건너뛰기</button>}
            {q.met && <button onClick={start} className="btn-secondary btn-md">한 묶음 더 하기</button>}
            <button onClick={() => navigate('/listen/today')} className="min-h-11 text-[15px] font-bold text-track-dark">⤨ 오늘의 듣기 · 15분</button>
          </section>
        </div>
      </>}
      {guide && <GuideModal open onClose={() => setGuide(false)} initialKey="listening" />}
      <Modal open={skip} onClose={() => { if (!skipping) setSkip(false) }} title="정말로 건너뛰시겠어요?" cardClass="border-2 border-warn">
        {skipError && <p role="alert" className="text-[14px] text-bad-text">단계를 열지 못했어요</p>}
        <div className="flex gap-2.5"><button disabled={skipping} onClick={() => setSkip(false)} className="btn-secondary btn-md flex-1">아니오</button><button disabled={skipping} onClick={doSkip} className="btn-primary btn-md flex-1">{skipping ? '여는 중' : '예, 건너뛸게요'}</button></div>
      </Modal>
      {notice && <ListenNotice onClose={closeNotice} />}
    </div>
  </AppShell>
}
