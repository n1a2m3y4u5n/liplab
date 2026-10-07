import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import { voiceFor } from '../../lib/listenMix'
import { pct, skippedNote } from '../../lib/listenFlow'
import { fmtDuration, levelChangeText } from '../../lib/listenView'
import BottomBar from './BottomBar'
import { TaskEnd } from './ListenComplete'
import SoundCard from './SoundCard'
import { missingCard } from './StateCard'
import { useClip, usePrefetch } from './useClip'
import { useListenKeys, usePlayer, useStageTally } from './usePlayer'
import { Heading, Option, optionState } from './ui'

/**
 * 소리 구별(1단계 같다·다르다). 두 소리를 차례로 듣고 같은지 다른지 고른다. 단계 레슨, 소리 짝 집중 연습, 오늘의 듣기에서 쓴다.
 * data: {items:[{key, first, second, voice_pair, kind_label, pick}], level?, levels?, voice_mode, voice_block, guide, status}
 * answerExtra는 답에 그대로 붙는다(연습이면 {practice_mode}). 끝 처리는 finish(ListenComplete.TaskEnd).
 */
export default function AxDrill({ data, settings, voices, onProgress, finish, active, answerExtra = null, onAnswered = null }) {
  const items = data.items || []
  const leveled = data.levels != null
  const [k, setK] = useState(0)
  const [picked, setPicked] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [plays, setPlays] = useState(0)
  const [level, setLevel] = useState(data.level)
  const [change, setChange] = useState(null)
  const tally = useStageTally(data.status, onAnswered)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const it = items[k]
  const v1 = voiceFor(voices.train, k, it?.voice_pair?.[0] || 0, data.voice_mode, data.voice_block)
  const v2 = voiceFor(voices.train, k, it?.voice_pair?.[1] || 0, data.voice_mode, data.voice_block)
  const a = useClip(it?.first, v1)
  const b = useClip(it?.second, v2)
  const nx = items[k + 1]
  usePrefetch(nx ? [[nx.first, voiceFor(voices.train, k + 1, nx.voice_pair?.[0] || 0, data.voice_mode, data.voice_block)],
    [nx.second, voiceFor(voices.train, k + 1, nx.voice_pair?.[1] || 0, data.voice_mode, data.voice_block)]] : [])
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setPicked(null); setErr(null); setPlays(0); setChange(null); player.reset(); t0.current = Date.now() }, [k, player.reset])
  const ready = a.state === 'ready' && b.state === 'ready'
  const clipState = a.state === 'missing' || b.state === 'missing' ? 'missing' : ready ? 'ready' : 'loading'
  const play = async () => {
    if (!ready || player.busy) return
    const opts = { gainDb: settings.gainDb }
    const ok = await player.play([{ clip: a.clip, opts }, { clip: b.clip, opts }])
    if (ok && !res) setPlays((p) => p + 1)
  }
  const canAnswer = plays > 0 && !res && !sending
  const confirm = async () => {
    if (!canAnswer || picked == null) return
    player.stop()
    setSending(true)
    setErr(null)
    try {
      const r = await listenAPI.answer({ stage: 1, item_key: it.key, same: picked === 0, plays, rt_ms: Date.now() - t0.current, voice: v1, route: settings.route,
        pick: it.pick, ...(answerExtra || {}) })
      setRes(r)
      tally.add(r.correct, r.status)
      if (r.level != null && leveled) { setChange(levelChangeText(level, r.level, data.levels)); setLevel(r.level) }
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  const next = () => { player.stop(); setK(k + 1) }
  const skip = () => { tally.skip(); next() }
  useListenKeys({ active: active && !!it, onPlay: play, canPlay: ready && !player.busy, optionCount: 2, canPick: canAnswer, onPick: setPicked,
    onEnter: res ? next : clipState === 'missing' ? skip : confirm, canEnter: res ? true : clipState === 'missing' || (canAnswer && picked != null) })

  if (!it) {
    const result = { stage: 1, n: tally.n, c: tally.c, skipped: tally.skipped, mastered: tally.mastered, elapsed: tally.elapsed(), level, levels: data.levels }
    return (
      <TaskEnd finish={finish} result={result}
        title={tally.n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={tally.mastered ? '소리 구별을 숙달했어요. 다음 단계가 열렸어요.' : null}
        stats={tally.n ? [{ label: '정답률', value: pct(tally.c, tally.n), note: `${tally.n}문항 중 ${tally.c}문항`, main: true },
          leveled ? { label: '지금 수준', value: `${level} / ${data.levels}` } : null, { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }].filter(Boolean) : []}
        notes={[skippedNote(tally.skipped)]} />
    )
  }
  const sameVoice = it.voice_pair?.[1] === it.voice_pair?.[0] || voices.train.length < 2
  const answerIdx = res ? (res.same ? 0 : 1) : null
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="두 소리가 같나요, 다른가요?" meta={[leveled && `수준 ${level} / ${data.levels}`, it.kind_label].filter(Boolean).join(' · ') || null}
        sub={!sameVoice ? '두 소리는 다른 목소리예요. 목소리가 아니라 말소리가 같은지 들어 보세요.' : k === 0 ? data.guide : null} />
      {clipState === 'missing' ? missingCard(a.state === 'missing' ? a : b, skip) : (
        <>
          <SoundCard player={player} onPlay={play} clipState={clipState} label={res ? '두 소리 다시 듣기' : '두 소리 듣기'} plays={plays} />
          <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
            {['같아요', '달라요'].map((l, i) => (
              <Option key={l} index={i} label={l} big state={optionState(i, { picked, result: res, answer: answerIdx })}
                disabled={!canAnswer} waiting={!plays && !res} onClick={() => setPicked(i)} />
            ))}
          </div>
        </>
      )}
      {clipState !== 'missing' && (
        <BottomBar active={active} tone={res ? (res.correct ? 'good' : 'bad') : null}
          title={res ? (res.correct ? '정답이에요!' : '아쉬워요') : null}
          sub={res ? [res.same ? '같은 소리였어요' : `다른 소리였어요 · ${it.first} / ${it.second}`, change].filter(Boolean).join(' · ') : null}
          hint={!plays ? '먼저 두 소리를 들어요' : picked == null ? '같은지 다른지 골라요 · 1·2 키' : 'Enter로 확인해요'}
          alert={err}
          primary={res ? { label: '계속하기', onClick: next } : { label: sending ? '보내는 중' : '확인', onClick: confirm, disabled: !canAnswer || picked == null }} />
      )}
    </div>
  )
}
