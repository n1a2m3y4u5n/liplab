import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import { voiceFor } from '../../lib/listenMix'
import { NOISE_TYPES, pct, skippedNote } from '../../lib/listenFlow'
import { fmtDuration } from '../../lib/listenView'
import BottomBar from './BottomBar'
import { TaskEnd } from './ListenComplete'
import SoundCard from './SoundCard'
import { missingCard, noiseMissingCard } from './StateCard'
import { useClip, useNoise, usePrefetch } from './useClip'
import { useListenKeys, usePlayer, useStageTally } from './usePlayer'
import { Card, Heading, Option, optionState } from './ui'

/**
 * 대화 듣기(5단계). 장소에서 들을 법한 말을 듣고 내용을 고른다. 못 알아들으면 다시·천천히·다른 말로 되묻는다(감점 없음).
 * 단계 레슨에서는 듣기 조건(조용함·소음·전화·울리는 방)을 처음 듣기 전에 고른다. 상황별 대화 듣기·듣기 조건 연습·오늘의 듣기에서도 쓴다.
 *  - condition을 주면 조건을 고정하고 고르는 줄을 숨긴다(듣기 조건 연습). {kind, noise?, rt60?, snrDb?}
 */
const NOISE_LABEL = { ...Object.fromEntries(NOISE_TYPES.map((n) => [n.key, n.label])), talker2: '두 사람 말소리' }
const COND_LABEL = { quiet: '조용함', noise: '소음', phone: '전화', room: '울리는 방' }

export default function ConvoTask({ data, settings, voices, onProgress, onExit, finish, active, exitLabel = '학습 화면으로',
  answerExtra = null, onAnswered = null, condition = null }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [condPick, setCond] = useState('quiet')
  const cond = condition?.kind || condPick
  const [picked, setPicked] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [repairs, setRepairs] = useState([])
  const [plays, setPlays] = useState(0)
  const [repairTotal, setRepairTotal] = useState(0)
  const tally = useStageTally(data.status, onAnswered)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const line = useClip(it?.line, voice)
  const para = useClip(it?.paraphrase, voice)
  const nx = items[k + 1]
  usePrefetch(nx ? [[nx.line, voiceFor(voices.train, k + 1, 0, data.voice_mode, data.voice_block)]] : [])
  // 소음 조건은 문항마다 잡음 종류를 돌린다(경쟁 화자 1명이 인공와우 사용자에게 가장 어렵고 화자 수 효과는 단조롭지 않아 한 축으로
  // 쓰지 않는다, Chen 2020). talker2는 일반화 확인용으로 훈련에 쓰지 않는다. 조건을 고정했으면 고른 잡음만 쓴다
  const noiseName = condition?.noise || (data.noise_types || ['babble'])[k % (data.noise_types?.length || 1)]
  const nz = useNoise(cond === 'noise', noiseName)
  const snrDb = condition?.snrDb ?? data.noise_snr_db ?? 5
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setPicked(null); setErr(null); setRepairs([]); setPlays(0); player.reset(); t0.current = Date.now() }, [k, player.reset])
  // 울리는 방은 문항마다 잔향 시간을 돌린다(여러 방에서 훈련할 때 새 방으로 옮겨 갔다)
  const rt = condition?.rt60 ?? (data.room_rt60 || [0.5])[k % (data.room_rt60?.length || 1)]
  const opts = { gainDb: settings.gainDb, phone: cond === 'phone', snrDb: cond === 'noise' ? snrDb : null, noise: cond === 'noise' ? nz.noise : null,
    room: cond === 'room' ? rt : null }
  const ready = line.state === 'ready' && (cond !== 'noise' || nz.state === 'ready')
  const play = async (clip, extra = {}, repair = null) => {
    if (!clip || player.busy) return
    if (repair && !res) { setRepairs((r) => [...r, repair]); setRepairTotal((n) => n + 1) }
    const ok = await player.play([{ clip, opts: { ...opts, ...extra } }])
    if (ok && !res) setPlays((p) => p + 1)
  }
  const canAnswer = plays > 0 && !res && !sending
  const confirm = async () => {
    if (!canAnswer || picked == null) return
    player.stop()
    setSending(true)
    setErr(null)
    try {
      const r = await listenAPI.answer({ stage: 5, item_key: it.key, choice: picked, condition: cond, snr_db: cond === 'noise' ? snrDb : null,
        // 소음 조건이면 들려준 잡음 이름을 늘 남긴다(listen_attempts.noise). 예전에는 조건을 고정했을 때만 보내, 문항마다 잡음을 돌리는
        // 5단계와 상황별 대화 듣기 연습에서는 어떤 잡음으로 들었는지가 비어 있었다
        repairs, plays, rt_ms: Date.now() - t0.current, voice, route: settings.route, ...(cond === 'noise' ? { noise: noiseName } : {}),
        ...(answerExtra || {}) })
      setRes(r)
      tally.add(r.correct, r.status)
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  const next = () => { player.stop(); setK(k + 1) }
  const skip = () => { tally.skip(); next() }
  useListenKeys({ active: active && !!it, onPlay: () => play(line.clip), canPlay: ready && !player.busy, optionCount: it?.options?.length || 0,
    canPick: canAnswer, onPick: setPicked,
    onEnter: res ? next : line.state === 'missing' ? skip : confirm, canEnter: res ? true : line.state === 'missing' || (canAnswer && picked != null) })

  if (!it) {
    const result = { stage: 5, n: tally.n, c: tally.c, skipped: tally.skipped, mastered: tally.mastered, elapsed: tally.elapsed(), repairs: repairTotal }
    return (
      <TaskEnd finish={finish} result={result}
        title={tally.n ? '이번 대화를 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={tally.mastered ? '대화 듣기를 숙달했어요.' : null}
        stats={tally.n ? [{ label: '정답률', value: pct(tally.c, tally.n), note: `${tally.n}문제 중 ${tally.c}문제`, main: true },
          { label: '되물은 횟수', value: `${repairTotal}번`, note: '되묻기는 감점이 없어요' }, { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }] : []}
        notes={[skippedNote(tally.skipped)]} />
    )
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      {!condition && (
        <div className="flex gap-1 rounded-13 bg-surface-sunken p-1" role="radiogroup" aria-label="듣기 조건">
          {(data.conditions || ['quiet']).map((c) => (
            <button key={c} type="button" role="radio" aria-checked={cond === c} disabled={plays > 0 && cond !== c} onClick={() => setCond(c)}
              className={`min-h-[44px] flex-1 rounded-10 px-1 text-[14px] font-bold disabled:cursor-not-allowed disabled:opacity-50 ${cond === c ? 'bg-white text-track-dark shadow-seg' : 'text-ink-muted'}`}>
              {COND_LABEL[c]}
            </button>
          ))}
        </div>
      )}
      <Heading title={it.question}
        meta={[it.place, cond === 'noise' ? NOISE_LABEL[noiseName] || '소음' : condition ? COND_LABEL[cond] : null].filter(Boolean).join(' · ') || null}
        sub={k === 0 && !plays ? (condition ? '못 알아들으면 되물어도 돼요. 되묻기는 감점이 없어요.' : '듣기 조건은 처음 듣기 전에 골라요. 못 알아들으면 되물어도 돼요.') : null} />
      {line.state === 'missing' ? missingCard(line, skip) : cond === 'noise' && nz.state === 'missing' ? noiseMissingCard(nz, onExit, exitLabel) : (
        <>
          <SoundCard player={player} onPlay={() => play(line.clip)} clipState={ready ? 'ready' : 'loading'} label={res ? '글을 보며 다시 듣기' : plays ? '처음 말 다시 듣기' : '말 듣기'} plays={plays}>
            {plays > 0 && !res && (
              <div className="mt-4 grid grid-cols-3 gap-2 border-t-2 border-line pt-4" role="group" aria-label="되묻기">
                <button type="button" onClick={() => play(line.clip, {}, 'again')} disabled={player.busy} className="btn-secondary px-1 py-2.5 text-[14px]">다시</button>
                <button type="button" onClick={() => play(line.clip, { rate: 0.8 }, 'slow')} disabled={player.busy} className="btn-secondary px-1 py-2.5 text-[14px]">천천히</button>
                <button type="button" onClick={() => play(para.clip, {}, 'rephrase')} disabled={player.busy || para.state !== 'ready'} className="btn-secondary px-1 py-2.5 text-[14px]">다른 말로</button>
              </div>
            )}
          </SoundCard>
          <div className="flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:gap-3">
            {it.options.map((o, i) => (
              <Option key={o} index={i} label={o} state={optionState(i, { picked, result: res, answer: res?.answer })}
                disabled={!canAnswer} waiting={!plays && !res} onClick={() => setPicked(i)} />
            ))}
          </div>
          {res && (
            <Card className="flex flex-col gap-1.5">
              <p className="text-[13px] font-bold text-ink-muted">들려준 말</p>
              <p className="break-keep text-[17px] font-bold leading-snug text-ink">“{res.line}”</p>
            </Card>
          )}
          <BottomBar active={active} tone={res ? (res.correct ? 'good' : 'bad') : null}
            title={res ? (res.correct ? '정답이에요!' : '아쉬워요') : null}
            sub={res ? `정답은 ${res.answer + 1}번이에요` : null}
            hint={!plays ? '먼저 말을 들어요' : picked == null ? `답을 골라요 · 1~${it.options.length} 키` : 'Enter로 확인해요'}
            alert={err}
            primary={res ? { label: '계속하기', onClick: next } : { label: sending ? '보내는 중' : '확인', onClick: confirm, disabled: !canAnswer || picked == null }} />
        </>
      )}
    </div>
  )
}
