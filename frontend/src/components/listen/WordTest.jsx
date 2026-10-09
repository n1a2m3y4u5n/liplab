import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import BottomBar from './BottomBar'
import ListenComplete from './ListenComplete'
import SoundCard from './SoundCard'
import StateCard from './StateCard'
import { useClip, usePrefetch } from './useClip'
import { useListenKeys, usePlayer } from './usePlayer'
import { Heading, Option, Skeleton } from './ui'

/**
 * 낱말 일반화 검사(청인 파일럿, /learn/listening?stage=2&wordtest=1). 훈련에 나오지 않은 낱말을 검사 목소리로 듣고 고른다.
 * 낱말마다 두 번까지 듣고, 정답은 알려 주지 않는다.
 */
export default function WordTest({ settings, voices, onProgress, onExit, active }) {
  const [run, setRun] = useState(null)
  const [nonce, setNonce] = useState(0)
  const [k, setK] = useState(0)
  const [picked, setPicked] = useState(null)
  const [plays, setPlays] = useState(0)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)
  const [fatal, setFatal] = useState(null)
  const [err, setErr] = useState(null)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const it = run?.items?.[k]
  const clip = useClip(it?.target, voices.test)
  usePrefetch(run?.items?.[k + 1] ? [[run.items[k + 1].target, voices.test]] : [])
  useEffect(() => {
    setFatal(null)
    listenAPI.wordTestStart().then((r) => { setRun(r); setK(0) }).catch(() => setFatal('검사를 시작하지 못했어요. 인터넷 연결을 확인하고 다시 해 주세요.'))
  }, [nonce])
  useEffect(() => { if (run) onProgress(k, run.items.length) }, [k, run, onProgress])
  useEffect(() => { setPlays(0); setPicked(null); setErr(null); player.reset(); t0.current = Date.now() }, [k, player.reset])
  const play = async () => {
    if (clip.state !== 'ready' || player.busy || plays >= 2) return
    const ok = await player.play([{ clip: clip.clip, opts: { gainDb: settings.gainDb } }])
    if (ok) setPlays((p) => p + 1)
  }
  const canAnswer = plays > 0 && !sending
  const confirm = async () => {
    if (!canAnswer || picked == null) return
    player.stop()
    setSending(true)
    setErr(null)
    try {
      const r = await listenAPI.wordTestAnswer({ session: run.session, item_key: it.key, answer: it.options[picked], voice: voices.test, plays,
        rt_ms: Date.now() - t0.current, route: settings.route })
      if (r.done) setResult(r)
      else setK(k + 1)
    } catch (e) {
      // 응답 없이 끊겼으면 같은 답을 다시 보내면 서버가 그때 결과를 그대로 돌려준다(멱등). 버튼을 다시 누르면 이어서 한다
      if (e?.response && e.response.status !== 409) setFatal('답을 기록하지 못했어요. 검사를 처음부터 다시 해 주세요.')
      else if (e?.response?.status === 409) setFatal('이미 다른 답이 기록된 문장이에요. 검사를 처음부터 다시 해 주세요.')
      else setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 같은 답으로 다시 눌러 주세요. 검사는 이어서 할 수 있어요.')
    }
    setSending(false)
  }
  useListenKeys({ active: active && !!it && !result && !fatal, onPlay: play, canPlay: clip.state === 'ready' && !player.busy && plays < 2,
    optionCount: it?.options?.length || 0, canPick: canAnswer, onPick: setPicked, onEnter: confirm, canEnter: canAnswer && picked != null })

  if (fatal) return <StateCard title={fatal} actions={[{ label: '검사 다시 시작', onClick: () => { setRun(null); setNonce((n) => n + 1) } }, { label: '학습 화면으로', onClick: onExit }]} />
  if (!run) return <Skeleton />
  if (result) {
    return <ListenComplete title="낱말 검사를 마쳤어요" stats={[{ label: '맞힌 낱말', value: `${Math.round(result.accuracy * run.items.length)} / ${run.items.length}`, main: true }]}
      sub="훈련에 나오지 않은 낱말로 측정했어요. 정답은 따로 알려 주지 않아요." primary={{ label: '학습 화면으로', onClick: onExit }} />
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="들은 낱말을 골라요" meta={`낱말 검사 ${k + 1} / ${run.items.length} · 정답은 알려 주지 않아요`}
        sub={k === 0 ? '낱말마다 두 번까지 들을 수 있어요.' : null} />
      {clip.state === 'missing' && clip.reason === 'not_prepared' ? (
        <StateCard title="검사 소리가 아직 준비되지 않았어요" body="검사 낱말 소리를 아직 만드는 중이라 지금은 검사를 할 수 없어요. 나중에 다시 해 주세요."
          actions={[{ label: '학습 화면으로', onClick: onExit }]} />
      ) : clip.state === 'missing' ? (
        <StateCard title="검사 소리를 받지 못했어요" body="인터넷 연결을 확인하고 다시 받아 주세요." actions={[{ label: '다시 받기', onClick: clip.retry }, { label: '학습 화면으로', onClick: onExit }]} />
      ) : (
        <>
          <SoundCard player={player} onPlay={play} clipState={clip.state} label="낱말 듣기" plays={plays} maxPlays={2} />
          <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
            {it.options.map((o, i) => (
              <Option key={o} index={i} label={o} big state={picked === i ? 'selected' : 'idle'} disabled={!canAnswer} waiting={!plays} onClick={() => setPicked(i)} />
            ))}
          </div>
          <BottomBar active={active} hint={!plays ? '먼저 낱말을 들어요' : picked == null ? '보기를 골라요' : 'Enter로 다음 낱말로 가요'} alert={err}
            primary={{ label: sending ? '보내는 중' : '다음', onClick: confirm, disabled: !canAnswer || picked == null }} />
        </>
      )}
    </div>
  )
}
