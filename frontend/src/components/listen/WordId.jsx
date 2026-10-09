import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import { voiceFor, contrastText } from '../../lib/listenMix'
import { pct, skippedNote } from '../../lib/listenFlow'
import { fmtDuration, levelChangeText } from '../../lib/listenView'
import BottomBar from './BottomBar'
import { TaskEnd } from './ListenComplete'
import SoundCard from './SoundCard'
import { missingCard } from './StateCard'
import { useClip, usePrefetch } from './useClip'
import { useListenKeys, usePlayer, useStageTally } from './usePlayer'
import { Card, Heading, Option, optionState } from './ui'

/**
 * 낱말 고르기(2단계). 소리만 듣고 보기에서 낱말을 고른다. 틀리면 어느 소리를 무엇으로 들었는지 알려 주고 정답·고른 말을 다시 들려준다.
 * 단계 레슨, 소리 짝 집중 연습(낱말 문항), 오늘의 듣기, 듣기 복습에서 쓴다.
 * data: {items:[{key, target, options, level?, review?, pick?, avoid_voices?}], level?, levels?, voice_mode, voice_block, guide, status}
 * 목소리는 voiceFor가 문항의 avoid_voices(정답 글을 구별되게 내지 못한 목소리)를 건너뛰어 고른다. 재생·미리 받기·답 기록이 같은 목소리다.
 * metaLabel을 주면 질문 아래 줄에 수준 대신 그 글을 쓴다(복습: '다시 듣는 낱말').
 */
export default function WordId({ data, settings, voices, onProgress, finish, active, answerExtra = null, onAnswered = null, metaLabel = null }) {
  const items = data.items || []
  const leveled = data.levels != null
  const [k, setK] = useState(0)
  const [res, setRes] = useState(null)
  const [picked, setPicked] = useState(null)
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [plays, setPlays] = useState(0)
  const [level, setLevel] = useState(data.level)
  const [change, setChange] = useState(null)
  const tally = useStageTally(data.status, onAnswered)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block, it?.avoid_voices)
  const target = useClip(it?.target, voice)
  const pickedWord = picked != null ? it?.options?.[picked] : null
  const heard = useClip(res && !res.correct ? pickedWord : null, voice)
  usePrefetch(items[k + 1] ? [[items[k + 1].target, voiceFor(voices.train, k + 1, 0, data.voice_mode, data.voice_block, items[k + 1].avoid_voices)]] : [])
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setPicked(null); setErr(null); setPlays(0); setChange(null); player.reset(); t0.current = Date.now() }, [k, player.reset])
  const play = async (clip = target.clip) => {
    if (!clip || player.busy) return
    const ok = await player.play([{ clip, opts: { gainDb: settings.gainDb } }])
    if (ok && clip === target.clip && !res) setPlays((p) => p + 1)
  }
  const canAnswer = plays > 0 && !res && !sending
  const confirm = async () => {
    if (!canAnswer || pickedWord == null) return
    player.stop()
    setSending(true)
    setErr(null)
    try {
      const r = await listenAPI.answer({ stage: 2, item_key: it.key, answer: pickedWord, level: it.level, plays, rt_ms: Date.now() - t0.current,
        voice, route: settings.route, pick: it.pick, ...(answerExtra || {}) })
      setRes(r)
      tally.add(r.correct, r.status)
      if (r.level != null && leveled) { setChange(levelChangeText(level, r.level, data.levels)); setLevel(r.level) }
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  const next = () => { player.stop(); setK(k + 1) }
  const skip = () => { tally.skip(); next() }
  useListenKeys({ active: active && !!it, onPlay: () => play(), canPlay: target.state === 'ready' && !player.busy, optionCount: it?.options?.length || 0,
    canPick: canAnswer, onPick: setPicked,
    onEnter: res ? next : target.state === 'missing' ? skip : confirm, canEnter: res ? true : target.state === 'missing' || (canAnswer && picked != null) })

  if (!it) {
    const result = { stage: 2, n: tally.n, c: tally.c, skipped: tally.skipped, mastered: tally.mastered, elapsed: tally.elapsed(), level, levels: data.levels }
    return (
      <TaskEnd finish={finish} result={result}
        title={tally.n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={tally.mastered ? '낱말 고르기를 숙달했어요. 다음 단계가 열렸어요.' : null}
        stats={tally.n ? [{ label: '정답률', value: pct(tally.c, tally.n), note: `${tally.n}문제 중 ${tally.c}문제`, main: true },
          leveled ? { label: '지금 수준', value: `${level} / ${data.levels}` } : null, { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }].filter(Boolean) : []}
        notes={[skippedNote(tally.skipped)]} />
    )
  }
  const answerIdx = res ? it.options.indexOf(res.target) : null
  const meta = metaLabel
    ? `${metaLabel} · 보기 ${it.options.length}개`
    : [leveled && `수준 ${level} / ${data.levels}`, `보기 ${it.options.length}개`, it.review && '다시 듣는 낱말'].filter(Boolean).join(' · ')
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="들은 낱말을 골라요" meta={meta} sub={k === 0 && !res ? data.guide : null} />
      {target.state === 'missing' ? missingCard(target, skip) : (
        <>
          <SoundCard player={player} onPlay={() => play()} clipState={target.state} label={res ? '낱말 다시 듣기' : '낱말 듣기'} plays={plays} />
          <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
            {it.options.map((o, i) => (
              <Option key={o} index={i} label={o} big state={optionState(i, { picked, result: res, answer: answerIdx })}
                disabled={!canAnswer} waiting={!plays && !res} onClick={() => setPicked(i)} />
            ))}
          </div>
          {res && !res.correct && (
            <Card className="flex flex-col gap-3">
              <p className="break-keep text-[14px] leading-[1.6] text-ink">{contrastText(res.contrast)}</p>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={() => play(target.clip)} disabled={player.busy} aria-label={`정답 ${res.target} 듣기`}
                  className="btn-secondary flex flex-col items-center gap-0.5 px-2 py-2.5 text-track-dark">
                  <span className="text-[12px] font-bold opacity-80">정답 듣기</span><span className="break-keep text-[16px]">{res.target}</span>
                </button>
                <button type="button" onClick={() => play(heard.clip)} disabled={player.busy || heard.state !== 'ready'} aria-label={`고른 말 ${pickedWord} 듣기`}
                  className="btn-secondary flex flex-col items-center gap-0.5 px-2 py-2.5">
                  <span className="text-[12px] font-bold opacity-80">고른 말 듣기</span><span className="break-keep text-[16px]">{pickedWord}</span>
                </button>
              </div>
            </Card>
          )}
          <BottomBar active={active} tone={res ? (res.correct ? 'good' : 'bad') : null}
            title={res ? (res.correct ? '정답이에요!' : '아쉬워요') : null}
            sub={res ? [`정답은 「${res.target}」예요`, change].filter(Boolean).join(' · ') : null}
            hint={!plays ? '먼저 낱말을 들어요' : picked == null ? `보기를 골라요 · 1~${it.options.length} 키` : 'Enter로 확인해요'}
            alert={err}
            primary={res ? { label: '계속하기', onClick: next } : { label: sending ? '보내는 중' : '확인', onClick: confirm, disabled: !canAnswer || picked == null }} />
        </>
      )}
    </div>
  )
}
