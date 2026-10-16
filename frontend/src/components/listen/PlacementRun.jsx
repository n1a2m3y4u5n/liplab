import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import BottomBar from './BottomBar'
import ListenComplete from './ListenComplete'
import SoundCard from './SoundCard'
import StateCard from './StateCard'
import { useClip, useNoise } from './useClip'
import { useListenKeys, usePlayer } from './usePlayer'
import { Card, Heading, Option, Skeleton, inputClass } from './ui'

/**
 * 소리 듣기 시작 단계 정하기(배치검사 후보 D, /learn/listening?placement=1, docs/listen-placement3-2026-10.md 11절).
 * 서버 플래그 LISTEN_PLACEMENT가 켜졌을 때만 학습 화면에 들어가는 버튼이 생긴다. 문제는 서버가 하나씩 고르고(POST /api/listen/placement/next),
 * 화면은 지금까지의 답 전체를 보낸다(서버가 처음부터 다시 채점한다). 답은 연습 기록·숙달에 들어가지 않고, 정답은 알려 주지 않는다.
 * 문제마다 두 번까지 듣는다. 소리는 누를 때만 나온다. 끝나면 결과를 보이고 '이대로 시작하기'를 눌러야 적용한다(placement/apply).
 */
const STAGE_TITLE = { 3: '문장 알아듣기', 4: '소음 속 듣기', 5: '대화 듣기' }
const MAX_PLAYS = 2

export default function PlacementRun({ settings, onProgress, onExit, onApplied, active }) {
  const [started, setStarted] = useState(false)
  const [run, setRun] = useState(null)          // 서버 응답 {session, done, item?, result?, n, max_items}
  const [answers, setAnswers] = useState([])
  const [picked, setPicked] = useState(null)
  const [typed, setTyped] = useState('')
  const [plays, setPlays] = useState(0)
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState(null)
  const [fatal, setFatal] = useState(null)
  const [applying, setApplying] = useState(false)
  const player = usePlayer()
  const inputRef = useRef(null)
  const it = run && !run.done ? run.item : null
  const kind = it?.kind
  const a = useClip(kind === 'pa' ? it.first : kind === 'pw' ? it.target : it?.text, it?.voice)
  const b = useClip(kind === 'pa' ? it.second : null, it?.voice)
  const nz = useNoise(kind === 'pn', 'babble')
  useEffect(() => { if (run) onProgress(run.n, run.max_items) }, [run, onProgress])
  useEffect(() => { setPicked(null); setTyped(''); setPlays(0); setErr(null); player.reset() }, [it?.key, player.reset])

  const send = async (list) => {
    setSending(true)
    setErr(null)
    try {
      const r = await listenAPI.placementNext({ session: run?.session ?? null, answers: list })
      setAnswers(list)
      setRun(r)
    } catch (e) {
      if (e?.response?.status === 409) setFatal(e.response.data?.detail || '지금은 시작 단계를 정할 수 없어요.')
      else if (e?.response) setFatal('답을 기록하지 못했어요. 처음부터 다시 해 주세요.')
      else setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 같은 답으로 다시 눌러 주세요.')
    }
    setSending(false)
  }
  const start = () => { setStarted(true); send([]) }
  const ready = a.state === 'ready' && (kind !== 'pa' || b.state === 'ready') && (kind !== 'pn' || nz.state === 'ready')
  const missing = a.state === 'missing' || (kind === 'pa' && b.state === 'missing') || (kind === 'pn' && nz.state === 'missing')
  const play = async () => {
    if (!ready || player.busy || plays >= MAX_PLAYS) return
    const opts = kind === 'pn' ? { gainDb: settings.gainDb, snrDb: it.snr_db, noise: nz.noise } : { gainDb: settings.gainDb }
    const seq = kind === 'pa' ? [{ clip: a.clip, opts }, { clip: b.clip, opts }] : [{ clip: a.clip, opts }]
    const ok = await player.play(seq)
    if (ok) {
      setPlays((p) => p + 1)
      if (kind === 'pq' || kind === 'pn') inputRef.current?.focus()
    }
  }
  const choice = kind === 'pa' ? ['같아요', '달라요'] : kind === 'pw' ? it.options : null
  const canSend = plays > 0 && !sending && (choice ? picked != null : !!typed.trim())
  const confirm = () => {
    if (!canSend) return
    player.stop()
    const ans = kind === 'pa' ? { item_key: it.key, same: picked === 0 }
      : kind === 'pw' ? { item_key: it.key, answer: it.options[picked] } : { item_key: it.key, answer: typed }
    send([...answers, ans])
  }
  const apply = async () => {
    setApplying(true)
    try {
      await listenAPI.placementApply({ session: run.session, answers })
      onApplied()
    } catch (e) {
      setFatal(e?.response?.data?.detail || '결과를 적용하지 못했어요. 인터넷 연결을 확인하고 다시 해 주세요.')
    }
    setApplying(false)
  }
  useListenKeys({ active: active && !!it && !fatal, onPlay: play, canPlay: ready && !player.busy && plays < MAX_PLAYS,
    optionCount: choice?.length || 0, canPick: !!choice && plays > 0 && !sending, onPick: setPicked, onEnter: confirm, canEnter: canSend })

  if (fatal) return <StateCard title={fatal} actions={[{ label: '학습 화면으로', onClick: onExit }]} />
  if (!started) {
    return (
      <div className="flex flex-col gap-4 lg:gap-5">
        <Heading title="어느 연습부터 할지 정해요" sub="몇 가지 소리를 듣고 답하면 1·2단계를 어느 수준부터 할지, 어느 단계까지 함께 열지 정해요." />
        <Card className="flex flex-col gap-2">
          <p className="break-keep text-[14px] leading-[1.7] text-ink-muted">5분쯤 걸리고, 문제는 16개를 넘지 않아요. 문제마다 두 번까지 들을 수 있어요.</p>
          <p className="break-keep text-[14px] leading-[1.7] text-ink-muted">정답은 알려 주지 않아요. 이 답은 연습 기록에 넣지 않아요.</p>
          <p className="break-keep text-[13px] leading-[1.7] text-ink-faint">청력을 진단하지 않아요. 연습을 어디서 시작할지만 정해요.</p>
        </Card>
        <BottomBar active={active} primary={{ label: '시작하기', onClick: start }} secondary={{ label: '나중에 할게요', onClick: onExit }} />
      </div>
    )
  }
  if (!run) return <Skeleton />
  if (run.done) {
    const r = run.result
    const opened = r.upper === 3 ? '3단계' : `3~${r.upper}단계`
    return (
      <ListenComplete title="어느 연습부터 할지 정했어요"
        sub={`1단계는 수준 ${r.level1}, 2단계는 수준 ${r.level2}부터 연습해요. ${opened}(${STAGE_TITLE[r.upper]}까지)도 함께 열려요. 1·2단계는 그대로 연습해서 숙달해요.`}
        stats={[{ label: '소리 구별 시작', value: `수준 ${r.level1} / 4`, main: true }, { label: '낱말 고르기 시작', value: `수준 ${r.level2} / 3`, main: true },
          { label: '함께 여는 단계', value: opened }]}
        primary={{ label: applying ? '적용하는 중' : '이대로 시작하기', onClick: applying ? undefined : apply }}
        secondary={{ label: '적용하지 않고 나가기', onClick: onExit }} />
    )
  }
  const title = kind === 'pa' ? '두 소리가 같나요, 다른가요?' : kind === 'pw' ? '들은 낱말을 골라요' : '문장을 듣고 들은 대로 써요'
  const meta = [`시작 단계 정하기 ${run.n + 1}번째 문제`, kind === 'pn' && '여러 사람이 떠드는 소리 속에서', '정답은 알려 주지 않아요'].filter(Boolean).join(' · ')
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title={title} meta={meta} sub={run.n === 0 ? '문제마다 두 번까지 들을 수 있어요.' : null} />
      {missing ? (
        <StateCard title="소리를 받지 못했어요" body="인터넷 연결을 확인하고 다시 받아 주세요. 소리가 준비되지 않았으면 나중에 다시 해 주세요."
          actions={[{ label: '다시 받기', onClick: () => { a.retry?.(); b.retry?.(); nz.retry?.() } }, { label: '학습 화면으로', onClick: onExit }]} />
      ) : (
        <>
          <SoundCard player={player} onPlay={play} clipState={ready ? 'ready' : 'loading'}
            label={kind === 'pa' ? '두 소리 듣기' : kind === 'pw' ? '낱말 듣기' : '문장 듣기'} plays={plays} maxPlays={MAX_PLAYS} />
          {choice ? (
            <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
              {choice.map((o, i) => (
                <Option key={o} index={i} label={o} big state={picked === i ? 'selected' : 'idle'} disabled={!plays || sending} waiting={!plays}
                  onClick={() => setPicked(i)} />
              ))}
            </div>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); confirm() }}>
              <label htmlFor="placement-answer" className="sr-only">들은 문장</label>
              <input id="placement-answer" ref={inputRef} value={typed} onChange={(e) => setTyped(e.target.value)} disabled={!plays || sending}
                autoComplete="off" enterKeyHint="done" placeholder={plays ? '들은 말을 써요' : '먼저 문장을 들어요'} className={inputClass} />
            </form>
          )}
          <BottomBar active={active} alert={err}
            hint={!plays ? '먼저 소리를 들어요' : choice ? (picked == null ? '보기를 골라요' : 'Enter로 다음 문제로 가요') : '들은 대로 쓰고 Enter'}
            primary={{ label: sending ? '보내는 중' : '다음', onClick: confirm, disabled: !canSend }} />
        </>
      )}
    </div>
  )
}
