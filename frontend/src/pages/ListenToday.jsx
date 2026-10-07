import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listenAPI } from '../api'
import { stopAll } from '../lib/listenAudio'
import { TASK_TITLE, blockData, fmtGoalMinutes, todayTotals, pct } from '../lib/listenFlow'
import BottomBar from '../components/listen/BottomBar'
import ListenBlocks from '../components/listen/ListenBlocks'
import ListenComplete from '../components/listen/ListenComplete'
import ListenFrame from '../components/listen/ListenFrame'
import StateCard from '../components/listen/StateCard'
import { TRAIN_TASK } from '../components/listen/tasks'
import { Card, Heading, Skeleton } from '../components/listen/ui'

/**
 * 오늘의 듣기 15분: /listen/today (GET /api/listen/today, backend listen_curriculum.today_plan).
 * 계획의 블록(소리 확인 → 약한 소리 짝 → 문장 → 대화)을 차례로 한다. 블록마다 GET /api/listen/stage/{n}을 받아 앞에서 n문항만 내고,
 * 4단계는 검사 안내 없이 훈련 문장만 낸다. 답은 단계 레슨과 같이 세고(숙달에 들어감), 블록 사이에는 짧은 전환 화면을 둔다.
 * 끝에는 오늘 연습한 분·문항을 15분 목표와 비교한다(끝난 뒤 계획을 다시 받아 서버가 센 오늘 분을 쓴다).
 * 학습 경로 소리 듣기 트랙의 레슨 카드와 과제 탭의 '소리 듣기 15분'에서 들어온다(?from=tasks면 과제 탭으로 돌아간다).
 */

/** 블록 하나: 단계 문항을 받아 앞 n문항으로 과제를 연다. 잠겼거나 못 받으면 건너뛸 수 있게 한다. */
function TodayBlock({ block, ctx, onDone }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let on = true
    setData(null)
    setErr(false)
    listenAPI.getStage(block.stage).then((d) => { if (on) setData(blockData(d, block.n)) }).catch(() => { if (on) setErr(true) })
    return () => { on = false }
  }, [block.stage, block.n, nonce])
  const finish = useMemo(() => ({ onDone }), [onDone])
  if (err) {
    return <StateCard title="이 연습을 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러오거나, 이 연습은 건너뛰어요."
      actions={[{ label: '다시 불러오기', onClick: () => setNonce((n) => n + 1) }, { label: '이 연습 건너뛰기', onClick: () => onDone(null) }]} />
  }
  if (!data || !ctx.voiceList) return <Skeleton />
  const Task = TRAIN_TASK[data.mode]
  if (data.status === 'locked' || !Task) {
    return <StateCard title="이 연습은 아직 열리지 않았어요" body="학습 경로에서 앞 단계를 마치면 열려요." actions={[{ label: '다음 연습으로', onClick: () => onDone(null) }]} />
  }
  return (
    <Task data={data} settings={ctx.settings} voices={ctx.voices} onProgress={ctx.onProgress} onExit={() => onDone(null)} exitLabel="이 연습 건너뛰기"
      finish={finish} noisy={data.mode === 'noise'} active={ctx.active} />
  )
}

/** 시작 전: 오늘 한 분(15분 목표 막대)과 블록 목록. */
function TodayIntro({ plan, onStart, active }) {
  const total = plan.blocks.reduce((a, b) => a + (b.minutes || 0), 0)
  const doneMin = plan.done_today?.minutes || 0
  const target = plan.target_min || 15
  return (
    <div className="flex animate-fade-in flex-col gap-4 lg:gap-5">
      <Heading title="오늘의 듣기" sub={`하루 ${target}분, 아래 순서대로 이어서 해요. 블록 사이에 쉬어 가도 돼요.`} />
      <Card className="flex flex-col gap-2.5">
        <div className="flex items-baseline justify-between gap-3 leading-figma">
          <p className="text-[14px] font-bold text-ink-muted">오늘 연습한 시간</p>
          <p className="text-[15px] font-bold text-track-dark">{fmtGoalMinutes(doneMin)}<span className="font-normal text-ink-faint"> / {target}분</span></p>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-fill">
          <div className="h-full rounded-full bg-track" style={{ width: `${Math.min(100, (doneMin / target) * 100)}%` }} />
        </div>
      </Card>
      <ol className="flex flex-col overflow-hidden rounded-18 border-2 border-line bg-white lg:rounded-22">
        {plan.blocks.map((b, i) => (
          <li key={`${b.stage}-${i}`} className={`flex items-center gap-4 px-5 py-4 ${i ? 'border-t-1.5 border-line' : ''}`}>
            <span aria-hidden className="flex size-8 shrink-0 items-center justify-center rounded-full bg-track-tint text-[14px] font-bold text-track-dark">{i + 1}</span>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma">
              <p className="text-[16px] font-bold text-ink">{TASK_TITLE[b.mode] || `${b.stage + 1}단계`}</p>
              {b.why && b.why !== TASK_TITLE[b.mode] && <p className="break-keep text-[13px] text-ink-muted">{b.why}</p>}
            </div>
            <span className="shrink-0 text-[13px] font-bold text-ink-muted">{b.mode === 'ling' ? '1분' : `약 ${Math.max(1, Math.round(b.minutes || 0))}분`}</span>
          </li>
        ))}
      </ol>
      <BottomBar active={active} hint={`모두 약 ${Math.max(1, Math.round(total))}분`} primary={{ label: '시작하기', onClick: onStart }} />
    </div>
  )
}

export default function ListenToday() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const back = params.get('from') === 'tasks' ? '/tasks' : '/learn/path?track=listen'
  const [plan, setPlan] = useState(null)
  const [err, setErr] = useState(null)   // 'missing'(아직 없는 API) | 'network'
  const [nonce, setNonce] = useState(0)
  const [step, setStep] = useState({ idx: 0, phase: 'intro' })
  // 끝난 뒤 다시 받은 오늘 기록. undefined = 받는 중(요약은 기다린다), null = 못 받음(시작 전 기록 + 이번 회기로 어림).
  // 예전에는 받기 전에 어림값으로 요약을 그렸다가 서버 분으로 바뀌어 '15분을 채웠어요'가 잠깐 보였다 사라질 수 있었다
  const [after, setAfter] = useState(undefined)
  useEffect(() => {
    let on = true
    setPlan(null)
    setErr(null)
    listenAPI.today().then((p) => { if (on) setPlan({ ...p, blocks: p?.blocks || [] }) })
      .catch((e) => { if (on) setErr(e?.response?.status === 404 ? 'missing' : 'network') })
    return () => { on = false }
  }, [nonce])
  const [doneBlocks, setDoneBlocks] = useState(0)
  const [endNow, setEndNow] = useState(false)
  const leave = () => { stopAll(); navigate(back) }
  // 마친 블록이 있으면 나가기 전에 오늘 요약을 먼저 보인다(요약에서 다시 누르면 나간다)
  const exit = () => {
    if (doneBlocks > 0 && step.phase !== 'end') { stopAll(); setEndNow(true); return }
    leave()
  }
  const onStep = useCallback((s) => setStep(s), [])
  useEffect(() => {
    if (step.phase !== 'end') return undefined
    let on = true
    listenAPI.today().then((p) => { if (on) setAfter(p?.done_today || null) }).catch(() => { if (on) setAfter(null) })
    return () => { on = false }
  }, [step.phase])

  const blocks = (plan?.blocks || []).map((b, i) => ({ ...b, key: `${i}:${b.stage}`, title: TASK_TITLE[b.mode] || `${b.stage + 1}단계` }))
  const cur = blocks[step.idx]
  const kicker = step.phase === 'run' && cur ? `오늘의 듣기 · ${step.idx + 1} / ${blocks.length} ${cur.title}` : '오늘의 듣기'
  return (
    <ListenFrame kicker={kicker} onExit={exit} exitAria="나가기">
      {(ctx) => (
        err ? (
          <StateCard title={err === 'missing' ? '오늘의 듣기를 준비하고 있어요' : '오늘의 계획을 불러오지 못했어요'}
            body={err === 'missing' ? '곧 열려요. 지금은 학습 경로에서 단계를 하나씩 이어 해 주세요.' : '인터넷 연결을 확인하고 다시 불러와 주세요.'}
            actions={err === 'missing' ? [{ label: '돌아가기', onClick: exit }] : [{ label: '다시 불러오기', onClick: () => setNonce((n) => n + 1) }, { label: '돌아가기', onClick: exit }]} />
        ) : !plan ? <Skeleton /> : blocks.length === 0 ? (
          <StateCard title="오늘 할 연습이 없어요" body="학습 경로에서 소리 듣기 단계를 열면 오늘의 듣기가 만들어져요." actions={[{ label: '돌아가기', onClick: exit }]} />
        ) : (
          <ListenBlocks blocks={blocks.map((b) => ({ ...b, run: ({ onDone }) => <TodayBlock block={b} ctx={ctx} onDone={onDone} /> }))}
            onStep={onStep} onProgress={ctx.onProgress} active={ctx.active} onResults={setDoneBlocks} endNow={endNow}
            intro={(start) => <TodayIntro plan={plan} onStart={start} active={ctx.active} />}
            renderSummary={(results) => {
              if (after === undefined) return <Skeleton />
              const t = todayTotals(results.map((x) => x.result), { done: after, before: plan.done_today, targetMin: plan.target_min || 15 })
              const target = plan.target_min || 15
              return (
                <ListenComplete title={t.reached ? `오늘 ${target}분을 채웠어요` : '오늘의 듣기를 마쳤어요'}
                  sub={t.reached ? '내일도 비슷한 시간에 이어 해요. 일주일에 5일쯤이 알맞아요.' : `${target}분까지 ${Math.max(1, t.left)}분쯤 남았어요. 남은 시간은 연습 탭에서 채워도 돼요.`}
                  stats={[{ label: '오늘 연습', value: `${fmtGoalMinutes(t.minutes)} / ${target}분`, main: true },
                    { label: '푼 문항', value: `${t.n}문항` }, { label: '정답률', value: pct(t.c, t.n) }]}
                  notes={[plan.review_due > 0 && `다시 들어 볼 낱말·문장이 ${plan.review_due}개 있어요. 복습 탭의 듣기 복습에서 할 수 있어요.`]}
                  primary={{ label: '돌아가기', onClick: leave }} secondary={{ label: '결과 보기', onClick: () => navigate('/analysis/listening') }}>
                  <div className="h-2.5 w-full overflow-hidden rounded-full bg-fill" role="img" aria-label={`목표 ${target}분 중 ${fmtGoalMinutes(t.minutes)}`}>
                    <div className="h-full rounded-full bg-track" style={{ width: `${t.goalPct}%` }} />
                  </div>
                  <ul className="flex w-full flex-col overflow-hidden rounded-18 border-2 border-line bg-white">
                    {results.map(({ block, result }, i) => (
                      <li key={block.key} className={`flex items-center justify-between gap-3 px-4 py-3 text-[14px] ${i ? 'border-t-1.5 border-line' : ''}`}>
                        <span className="font-bold text-ink">{block.title}</span>
                        <span className="text-ink-muted">{!result ? '건너뜀' : result.summary ? '점검함' : result.n ? `${result.c} / ${result.n}` : '–'}</span>
                      </li>
                    ))}
                  </ul>
                </ListenComplete>
              )
            }} />
        )
      )}
    </ListenFrame>
  )
}
