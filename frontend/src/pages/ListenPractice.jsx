import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { listenAPI } from '../api'
import { stopAll } from '../lib/listenAudio'
import {
  PRACTICE_MODES, CONDITIONS, NOISE_TYPES, practiceQuery, practiceApiParams, practiceTask, practiceActions, choiceLabel, normalizePlaces, contrastSegments,
  pct, fmtMinutes, josa,
} from '../lib/listenFlow'
import BottomBar from '../components/listen/BottomBar'
import ContrastRun from '../components/listen/ContrastRun'
import ListenComplete from '../components/listen/ListenComplete'
import ListenFrame from '../components/listen/ListenFrame'
import StateCard from '../components/listen/StateCard'
import { TRAIN_TASK } from '../components/listen/tasks'
import { Card, ChoiceGroup, Heading, Skeleton } from '../components/listen/ui'

/**
 * 소리 듣기 연습 모드: /listen/practice/:mode (연습 탭 '소리 듣기' 묶음, docs/listen-integration-api-2026-10.md).
 *  - contrast 소리 짝 집중 연습: 소리 짝 종류(또는 내가 자주 헷갈린 짝)를 고르고 같다·다르다 / 낱말 고르기
 *  - dictation 받아쓰기, noise_endless 소음 속 듣기: 고르지 않고 바로, 묶음이 끝나면 다음 묶음을 저절로 받는다(엔드리스).
 *    소음 속 듣기는 연습 계단을 작게 보인다. 나가기를 누르면 이번 연습 요약을 먼저 보인다.
 *  - scenario 상황별 대화 듣기: 장소를 고르고 대화 문항
 *  - conditions 듣기 조건 연습: 전화·울리는 방·잡음 종류를 고르고 그 조건으로만 듣는다
 * 고른 것은 주소 질의(?kind= · ?weak=1 · ?place= · ?condition=&noise=)로 남겨 새로 고쳐도 이어진다(lib/listenFlow.practiceQuery).
 * 답에는 practice_mode를 붙여 단계 숙달에 넣지 않는다. 과제 화면은 단계 레슨과 같은 컴포넌트다(components/listen/tasks).
 * 서버에 연습 API가 아직 없으면(404) '준비 중'으로, 소리 확인(Ling)을 한 번도 안 했으면(409) 소리 확인부터 하라고 알린다.
 * 소리 짝 문항은 같다·다르다와 낱말 고르기가 섞여 와서 ContrastRun이 종류별로 잇는다. 주소의 질의와 API 질의(contrast·cond·place)는
 * lib/listenFlow.practiceApiParams가 바꾼다(docs/listen-integration-api-2026-10.md).
 */

const HUB = '/practice/hub'

function Row({ title, desc, right, onClick, tone = null }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-surface-sunken ${tone === 'track' ? 'bg-track-tint hover:bg-track-tint' : ''}`}>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma">
        <span className={`text-[16px] font-bold ${tone === 'track' ? 'text-track-dark' : 'text-ink'}`}>{title}</span>
        {desc && <span className="break-keep text-[13px] leading-snug text-ink-muted">{desc}</span>}
      </span>
      {right && <span className="shrink-0 text-[12px] font-bold text-ink-muted">{right}</span>}
      <img src="/ui/review-arrow.svg" alt="" aria-hidden className="shrink-0" />
    </button>
  )
}

function RowList({ children }) {
  return <div className="flex flex-col divide-y-[1.5px] divide-line overflow-hidden rounded-18 border-2 border-line bg-white lg:rounded-22">{children}</div>
}

const failState = (e) => (e?.response?.status === 404 ? 'missing' : e?.response?.status === 409 ? 'ling' : 'network')

/** 소리 짝 고르기: 내가 자주 헷갈린 짝 + 종류별(GET /api/listen/contrasts). */
function ContrastChooser({ onPick, onClassroom }) {
  const [kinds, setKinds] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { listenAPI.contrasts().then((k) => setKinds(Array.isArray(k) ? k : k?.kinds || [])).catch((e) => setErr(failState(e))) }, [])
  return (
    <div className="flex animate-fade-in flex-col gap-4 lg:gap-5">
      <Heading title="어떤 소리 짝을 연습할까요?" sub="고른 종류의 짝만 이어서 나와요. 들어 보고 싶으면 소리 교실에서 먼저 들어 봐도 돼요." />
      <RowList>
        <Row tone="track" title="내가 자주 헷갈린 짝" desc="낱말 고르기에서 자주 틀린 소리부터 나와요" onClick={() => onPick({ weak: '1' })} />
        {(kinds || []).map((k) => (
          <Row key={k.kind} title={k.label} desc={k.desc} right={k.pairs?.length ? `짝 ${k.pairs.length}개` : null} onClick={() => onPick({ kind: k.kind })} />
        ))}
      </RowList>
      {!kinds && !err && <Skeleton />}
      {err && <p className="text-center text-[13px] text-ink-muted">{err === 'missing' ? '종류별 목록은 준비 중이에요. 자주 헷갈린 짝으로 연습할 수 있어요.' : '종류 목록을 불러오지 못했어요.'}</p>}
      <button type="button" onClick={onClassroom} className="min-h-[44px] self-center rounded-13 px-4 text-[13px] font-bold text-track-dark underline-offset-4 hover:underline">
        소리 교실에서 먼저 들어 보기
      </button>
    </div>
  )
}

/** 장소 고르기(GET /api/listen/practice/scenario/places). */
function PlaceChooser({ onPick, onExit }) {
  const [places, setPlaces] = useState(null)
  const [err, setErr] = useState(null)
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    setErr(null)
    listenAPI.scenarioPlaces().then((p) => setPlaces(normalizePlaces(p))).catch((e) => setErr(failState(e)))
  }, [nonce])
  if (err) return <NotReady kind={err} onRetry={() => setNonce((n) => n + 1)} onExit={onExit} />
  if (!places) return <Skeleton />
  return (
    <div className="flex animate-fade-in flex-col gap-4 lg:gap-5">
      <Heading title="어디에서 듣는 말일까요?" sub="장소를 고르면 그곳에서 들을 법한 말이 나와요. 못 알아들으면 다시·천천히·다른 말로 되물어도 돼요." />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:gap-3">
        {places.map((p) => (
          <button key={p.key} type="button" onClick={() => onPick({ place: p.key })}
            className="flex min-h-[64px] flex-col items-start justify-center gap-0.5 rounded-14 border-2 border-b-5 border-line bg-white px-4 py-3 text-left transition-colors hover:border-track lg:rounded-16">
            <span className="break-keep text-[16px] font-bold leading-snug text-ink">{p.label}</span>
            {p.n != null && <span className="text-[12px] text-ink-muted">{p.n}문항</span>}
          </button>
        ))}
      </div>
    </div>
  )
}

/** 듣기 조건 고르기: 전화 · 울리는 방 · 잡음(종류). */
function ConditionChooser({ onPick, active }) {
  const [cond, setCond] = useState('phone')
  const [noise, setNoise] = useState('babble')
  return (
    <div className="flex animate-fade-in flex-col gap-4 lg:gap-5">
      <Heading title="어떤 조건에서 들어 볼까요?" sub="일상에서 듣기 어려운 조건을 하나 골라 그 조건으로만 연습해요. 전체 소리 크기는 맞춘 크기를 넘지 않아요." />
      <Card className="flex flex-col gap-5">
        <ChoiceGroup legend="듣기 조건" options={CONDITIONS} value={cond} onChange={setCond} cols="grid-cols-1" />
        {cond === 'noise' && <ChoiceGroup legend="잡음 종류" options={NOISE_TYPES} value={noise} onChange={setNoise} cols="grid-cols-1 sm:grid-cols-2" />}
      </Card>
      <BottomBar active={active} hint="고른 뒤 시작해요" primary={{ label: '시작하기', onClick: () => onPick(cond === 'noise' ? { condition: cond, noise } : { condition: cond }) }} />
    </div>
  )
}

function NotReady({ kind, onRetry, onExit, reason }) {
  const navigate = useNavigate()
  if (kind === 'ling') {
    return <StateCard title="먼저 오늘의 소리 확인을 해요" body="음·우·아·이·쉬·스가 들리는지 한 번 확인하면 연습이 열려요. 1분쯤 걸려요."
      actions={[{ label: '소리 확인 하러 가기', onClick: () => { stopAll(); navigate('/learn/listening?stage=0') } }, { label: '연습 탭으로', onClick: onExit }]} />
  }
  return kind === 'missing' || kind === 'unavailable' ? (
    <StateCard title="이 연습은 준비 중이에요" body={reason || '곧 열려요. 지금은 학습 경로의 소리 듣기 단계로 연습해 주세요.'} actions={[{ label: '연습 탭으로', onClick: onExit }]} />
  ) : (
    <StateCard title="연습을 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러와 주세요."
      actions={[{ label: '다시 불러오기', onClick: onRetry }, { label: '연습 탭으로', onClick: onExit }]} />
  )
}

const EMPTY_BODY = {
  contrast: '아직 자주 헷갈린 소리 짝이 없어요. 낱말 고르기를 조금 더 하면 생겨요. 종류를 골라 연습할 수도 있어요.',
}

/** 연습 회기: 문항을 받아 과제를 연다. 엔드리스면 묶음이 끝날 때 다음 묶음을 받는다. */
function PracticeSession({ mode, query, ctx, onExit, onChoose, summaryOpen, tally, setTally, onMeta }) {
  const meta = PRACTICE_MODES[mode]
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [batch, setBatch] = useState(0)
  const carry = useRef({ stair: null, trace: [] })
  const qkey = JSON.stringify(query)
  useEffect(() => {
    let on = true
    setRes(null)
    setErr(null)
    listenAPI.practice(mode, practiceApiParams(mode, query)).then((r) => { if (on) { setRes(r || {}); onMeta?.(r || {}) } })
      .catch((e) => { if (on) setErr(failState(e)) })
    return () => { on = false }
  }, [mode, qkey, batch])   // eslint-disable-line react-hooks/exhaustive-deps
  const onAnswered = useCallback((correct) => setTally((t) => ({ ...t, n: t.n + 1, c: t.c + (correct ? 1 : 0) })), [setTally])
  // 엔드리스는 묶음 번호가 뜻이 없어 진행 글을 '지금까지 n문항'으로 쓴다(막대는 이번 묶음 안 진행)
  const doneN = tally.n
  const ctxProgress = ctx.onProgress
  const onProgress = useCallback((cur, total, label = null) => ctxProgress(cur, total, meta.endless ? `지금까지 ${doneN}문항` : label),
    [ctxProgress, meta.endless, doneN])
  const reload = () => { stopAll(); setBatch((b) => b + 1) }
  const finish = useMemo(() => (meta.endless
    ? { onDone: (r) => { carry.current = { stair: r?.stair || carry.current.stair, trace: r?.trace || carry.current.trace }; setBatch((b) => b + 1) } }
    : { actions: () => practiceActions({ mode, reload, onChoose, onExit }) }), [mode, batch])   // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <NotReady kind={err} onRetry={reload} onExit={onExit} />
  if (!res || !ctx.voiceList) return <Skeleton />
  if (res.available === false) return <NotReady kind="unavailable" reason={res.reason} onExit={onExit} />
  const segments = mode === 'contrast' ? contrastSegments(res.items) : null
  const task = segments ? (segments.length ? 'contrast' : null) : practiceTask(mode, res)
  const Task = task === 'contrast' ? ContrastRun : task ? TRAIN_TASK[task] : null
  if (!res.items?.length || !Task) {
    if (meta.endless && tally.n > 0) {
      return <StateCard title="오늘 준비한 문장을 다 들었어요" body="내일 새 문장으로 이어 해요." actions={[{ label: '연습 탭으로', onClick: onExit }]} />
    }
    return <StateCard title="지금 낼 문항이 없어요" body={res.reason || EMPTY_BODY[mode] || '나중에 다시 해 주세요.'}
      actions={[...(meta.chooseAgain ? [{ label: meta.chooseAgain, onClick: onChoose }] : []), { label: '연습 탭으로', onClick: onExit }]} />
  }
  // 소음 속 듣기 연습은 계단 이름이 practice_ao다(응답 condition). 문장 과제가 그 이름의 계단에서 다음 SNR을 읽는다
  const data = { ...res, stair: res.stair || carry.current.stair, trace: carry.current.trace, status: undefined,
    next_condition: res.next_condition || res.condition }
  // 듣기 조건 연습: 조건은 고정, 잔향 시간·잡음 종류·SNR은 문항마다 올 수 있다(SentenceTask가 문항 값을 먼저 쓴다)
  const condition = mode === 'conditions' ? {
    kind: res.cond || query.condition, noise: res.noise || query.noise, rt60: res.room_rt60?.[0], snrDb: res.snr_db ?? res.noise_snr_db,
    label: choiceLabel(mode, query),
  } : null
  return (
    <Task key={`${mode}:${qkey}:${batch}`} data={data} settings={ctx.settings} voices={ctx.voices} onProgress={onProgress} onExit={onExit}
      exitLabel="연습 탭으로" finish={finish} active={ctx.active && !summaryOpen} answerExtra={{ practice_mode: mode }} onAnswered={onAnswered}
      noisy={task === 'noise'} showStair={mode === 'noise_endless'} condition={condition}
      segments={segments} label={res.contrast?.label} />
  )
}

export default function ListenPractice() {
  const navigate = useNavigate()
  const { mode } = useParams()
  const [params, setParams] = useSearchParams()
  const meta = PRACTICE_MODES[mode]
  const { ready, query } = practiceQuery(mode, params)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [tally, setTally] = useState({ n: 0, c: 0, start: Date.now() })
  const [kinds, setKinds] = useState([])
  const [places, setPlaces] = useState([])
  const [metaLabel, setMetaLabel] = useState(null)   // 응답이 알려 준 고른 것의 이름(소리 짝 contrast.label)
  const onMeta = useCallback((r) => setMetaLabel(r?.contrast?.label || null), [])
  // 다른 연습으로 옮기면(같은 화면이 주소만 바뀜) 이번 연습 합계와 멈춤 요약을 비운다
  useEffect(() => { setSummaryOpen(false); setTally({ n: 0, c: 0, start: Date.now() }) }, [mode])
  useEffect(() => { if (mode === 'contrast' && query.kind) listenAPI.contrasts().then((k) => setKinds(Array.isArray(k) ? k : k?.kinds || [])).catch(() => {}) }, [mode, query.kind])
  useEffect(() => { if (mode === 'scenario' && query.place) listenAPI.scenarioPlaces().then((p) => setPlaces(normalizePlaces(p))).catch(() => {}) }, [mode, query.place])
  const toHub = () => { stopAll(); navigate(HUB) }
  const choose = () => { stopAll(); setParams({}, { replace: false }) }
  const pick = (q) => setParams(q)
  // 엔드리스는 나가기 전에 이번 연습 요약을 보인다(문항을 하나라도 풀었으면)
  const exit = () => {
    if (meta?.endless && ready && tally.n > 0 && !summaryOpen) { stopAll(); setSummaryOpen(true); return }
    toHub()
  }
  if (!meta) {
    return (
      <ListenFrame kicker="소리 듣기 연습" onExit={toHub} showProgress={false}>
        {() => <StateCard title="없는 연습이에요" actions={[{ label: '연습 탭으로', onClick: toHub }]} />}
      </ListenFrame>
    )
  }
  const label = !ready ? null
    : mode === 'scenario' ? places.find((p) => p.key === query.place)?.label || query.place
      : (mode === 'contrast' && !query.weak && metaLabel) || choiceLabel(mode, query, kinds)
  return (
    <ListenFrame key={`${mode}:${ready}`} kicker={`소리 듣기 연습 · ${meta.title}${label ? ` · ${label}` : ''}`} onExit={exit} exitAria="나가기, 연습 탭으로"
      showProgress={ready}>
      {(ctx) => (
        <>
          {!ready && mode === 'contrast' && <ContrastChooser onPick={pick} onClassroom={() => navigate('/listen/classroom')} />}
          {!ready && mode === 'scenario' && <PlaceChooser onPick={pick} onExit={toHub} />}
          {!ready && mode === 'conditions' && <ConditionChooser onPick={pick} active={ctx.active} />}
          {ready && (
            <PracticeSession mode={mode} query={query} ctx={ctx} onExit={toHub} onChoose={choose} onMeta={onMeta}
              summaryOpen={summaryOpen} tally={tally} setTally={setTally} />
          )}
          {summaryOpen && (
            <ListenComplete title={`${josa(meta.title, '을', '를')} 멈췄어요`} sub="원할 때 다시 이어서 하면 돼요."
              stats={[{ label: '푼 문항', value: `${tally.n}문항`, main: true }, { label: '통과', value: pct(tally.c, tally.n) },
                { label: '연습한 시간', value: fmtMinutes((Date.now() - tally.start) / 60000) }]}
              primary={{ label: '계속하기', onClick: () => setSummaryOpen(false) }} secondary={{ label: '연습 탭으로', onClick: toHub }} />
          )}
        </>
      )}
    </ListenFrame>
  )
}
