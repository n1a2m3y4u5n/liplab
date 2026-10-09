import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import ConsonantFeedback from '../ConsonantFeedback'
import { stopAll } from '../../lib/listenAudio'
import { fmtDb, testStep } from '../../lib/listenView'
import BottomBar from './BottomBar'
import ListenComplete from './ListenComplete'
import SentenceTask from './SentenceTask'
import SoundCard from './SoundCard'
import StateCard, { noiseMissingCard } from './StateCard'
import { useClip, useNoise, usePrefetch } from './useClip'
import { useListenKeys, usePlayer } from './usePlayer'
import { Card, Heading, Skeleton, inputClass, isDesktop } from './ui'

/** 4단계 검사: 소음 속 문장 인식 역치(연습 5문장 + 검사 20문장). 문장마다 한 번만 듣고, 검사 문장의 정답은 마칠 때까지 알려 주지 않는다. */
export function NoiseTest({ settings, voices, onProgress, onDone, onCancel, active, noise: noiseName = 'babble' }) {
  const [run, setRun] = useState(null)
  const [nonce, setNonce] = useState(0)
  const [k, setK] = useState(0)
  const [snr, setSnr] = useState(10)
  const [answer, setAnswer] = useState('')
  const [plays, setPlays] = useState(0)
  const [sending, setSending] = useState(false)
  const [prac, setPrac] = useState(null)        // 연습 문장 답(정답 문장과 자음 단서를 보인다)
  const [result, setResult] = useState(null)
  const [fatal, setFatal] = useState(null)
  const [err, setErr] = useState(null)
  const player = usePlayer()
  const inputRef = useRef(null)
  const it = run?.items?.[k]
  const step = testStep(run?.items, k)
  const clip = useClip(it?.text, voices.test)
  const nz = useNoise(true, run?.noise || noiseName)
  usePrefetch(run?.items?.[k + 1] ? [[run.items[k + 1].text, voices.test]] : [])
  useEffect(() => {
    setFatal(null)
    listenAPI.testStart({ route: settings.route, noise: noiseName }).then((r) => { setRun(r); setSnr(r.start_db); setK(0); setPrac(null) })
      .catch(() => setFatal('검사를 시작하지 못했어요. 인터넷 연결을 확인하고 다시 해 주세요.'))
  }, [settings.route, noiseName, nonce])
  // 진행 표시는 검사 문장 기준(n / 20). 연습 동안은 막대를 비워 두고 '연습 n / 5'로 적는다
  useEffect(() => {
    if (!run) return
    if (step.practice) onProgress(0, run.items.length - step.nPractice, `연습 ${step.no} / ${step.total}`)
    else onProgress(step.no - 1, step.total)
  }, [run, k, step.practice, step.no, step.total, onProgress])
  useEffect(() => { setAnswer(''); setPlays(0); setErr(null); setPrac(null); player.reset() }, [k, player.reset])
  const ready = clip.state === 'ready' && nz.state === 'ready'
  const play = async () => {
    if (!ready || player.busy || (plays >= 1 && !prac)) return
    const ok = await player.play([{ clip: clip.clip, opts: { gainDb: settings.gainDb, snrDb: snr, noise: nz.noise } }])
    if (ok && !prac) {
      setPlays((p) => p + 1)
      if (isDesktop()) inputRef.current?.focus()
    }
  }
  const canSubmit = plays > 0 && !sending && !prac
  const advance = (r) => {
    setSnr(r.next_db)
    setK((x) => x + 1)
  }
  const submit = async () => {
    if (!canSubmit) return
    player.stop()
    setSending(true)
    setErr(null)
    try {
      const r = await listenAPI.testAnswer({ session: run.session, item_key: it.key, answer, voice: voices.test, plays, route: settings.route,
        noise: run.noise })
      if (r.done) setResult(r)
      else if (r.practice) setPrac(r)
      else advance(r)
    } catch (e) {
      if (e?.response) setFatal('답을 기록하지 못했어요. 검사를 처음부터 다시 해 주세요.')
      else setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.')
    }
    setSending(false)
  }
  const nextPractice = () => { player.stop(); advance(prac) }
  useListenKeys({ active: active && !!it && !result && !fatal, onPlay: play, canPlay: ready && !player.busy && (plays < 1 || !!prac),
    onEnter: prac ? nextPractice : submit, canEnter: prac ? true : canSubmit })

  if (fatal) {
    return <StateCard title={fatal} actions={[{ label: '검사 다시 시작', onClick: () => { setRun(null); setNonce((n) => n + 1) } }, { label: '학습 화면으로', onClick: onCancel }]} />
  }
  if (!run) return <Skeleton />
  if (result) {
    return (
      <ListenComplete title="검사를 마쳤어요" stats={[{ label: '소음 속 문장 인식 역치', value: fmtDb(result.srt_db), main: true }]}
        sub={result.srt_db >= 24 ? '소음을 가장 작게 해도 낱말 절반을 넘기 어려웠어요. 문장 알아듣기를 더 연습하고 다시 검사해 보세요.'
          : `말이 소음보다 이만큼 클 때 ${(run.session || '').startsWith('test:v2-') ? '낱말을 절반쯤' : '낱말을 열에 넷쯤'} 알아들었다는 뜻이에요. 낮을수록 시끄러운 곳에서 잘 알아들어요.`}
        primary={{ label: '훈련 시작하기', onClick: onDone }} secondary={{ label: '학습 화면으로', onClick: onCancel }} />
    )
  }
  const firstTest = !step.practice && step.no === 1 && step.nPractice > 0
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      {firstTest && (
        <p role="status" className="rounded-14 bg-track-tint px-4 py-3 text-[14px] font-bold text-track-dark">연습을 마쳤어요. 이제 검사를 시작해요.</p>
      )}
      <Heading title="문장을 듣고 들은 대로 써요"
        meta={step.practice ? `연습 ${step.no} / ${step.total} · 점수에 안 들어가요` : `검사 ${step.no} / ${step.total} · 정답은 마칠 때까지 알려 주지 않아요`}
        sub={k === 0 ? '문장마다 한 번만 들어요. 모르면 비워 두고 넘어가도 돼요. 먼저 연습 문장으로 익혀요.' : null} />
      {clip.state === 'missing' && clip.reason === 'not_prepared' && step.practice ? (
        // 연습 문장 소리가 아직 합성되지 않았으면 그 연습만 건너뛴다(연습은 역치에 들어가지 않는다)
        <StateCard title="이 연습 문장은 소리가 아직 준비되지 않았어요" body="이 연습은 건너뛰고 다음으로 가요."
          actions={[{ label: '다음으로', onClick: () => setK((x) => x + 1) }]} />
      ) : clip.state === 'missing' && clip.reason === 'not_prepared' ? (
        <StateCard title="검사 소리가 아직 준비되지 않았어요" body="검사 문장 소리를 아직 만드는 중이라 지금은 검사를 할 수 없어요. 나중에 다시 해 주세요."
          actions={[{ label: '학습 화면으로', onClick: onCancel }]} />
      ) : clip.state === 'missing' ? (
        <StateCard title="검사 소리를 받지 못했어요" body="인터넷 연결을 확인하고 다시 받아 주세요." actions={[{ label: '다시 받기', onClick: clip.retry }, { label: '학습 화면으로', onClick: onCancel }]} />
      ) : nz.state === 'missing' ? noiseMissingCard(nz, onCancel) : (
        <>
          <SoundCard player={player} onPlay={play} clipState={ready ? 'ready' : 'loading'} label={prac ? '글을 보며 다시 듣기' : '문장 듣기'}
            plays={plays} maxPlays={prac ? null : 1} />
          {!prac ? (
            <form onSubmit={(e) => { e.preventDefault(); submit() }}>
              <label htmlFor="listen-test-answer" className="sr-only">들은 문장</label>
              <input id="listen-test-answer" ref={inputRef} value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!plays || sending}
                autoComplete="off" enterKeyHint="next" placeholder={plays ? '들은 말을 써요(모르면 비워 두고 다음)' : '먼저 문장을 들어요'} className={inputClass} />
            </form>
          ) : (
            <>
              <Card className="flex flex-col gap-1.5">
                <p className="text-[13px] font-bold text-ink-muted">연습 문장 정답</p>
                <p className="break-keep text-[19px] font-bold leading-snug text-ink lg:text-[21px]">{prac.target}</p>
              </Card>
              {prac.word_feedback && prac.word_feedback.correct_words < prac.word_feedback.total_words && (
                <ConsonantFeedback feedback={prac.word_feedback} tone="neutral" title={`${prac.word_feedback.total_words}낱말 중 ${prac.word_feedback.correct_words}낱말을 맞혔어요`}
                  hint="맞힌 낱말은 그대로, 틀린 낱말은 글자마다 첫 자음만 보여요. 검사에서는 이런 단서가 나오지 않아요." />
              )}
            </>
          )}
          <BottomBar active={active}
            title={prac ? `연습 ${step.no} / ${step.total}` : null}
            sub={prac ? `낱말 ${Math.round((prac.score || 0) * 100)}% 맞음 · 점수에 안 들어가요` : null}
            hint={!plays ? '먼저 문장을 들어요' : '들은 대로 쓰고 Enter'}
            alert={err}
            primary={prac ? { label: step.no >= step.total ? '검사 시작' : '다음 연습', onClick: nextPractice }
              : { label: sending ? '보내는 중' : '다음', onClick: submit, disabled: !canSubmit }} />
        </>
      )}
    </div>
  )
}

/**
 * 4단계 소음 속 듣기(단계 레슨). 처음이면 검사 안내 → 검사 → 훈련, 그 뒤로는 훈련과 '다시 검사하기'.
 * 오늘의 듣기는 검사 안내 없이 훈련(SentenceTask noisy)만 쓴다.
 */
export default function NoiseStage({ data, settings, voices, onProgress, onExit, finish, reload, active }) {
  // 연구용: ?testnoise=talker2면 훈련에 안 쓴 잡음으로 검사만 한다(청인 파일럿 일반화 검사)
  const testNoise = (() => { try { return new URLSearchParams(window.location.search).get('testnoise') } catch { return null } })()
  const [mode, setMode] = useState(testNoise === 'talker2' ? 'test' : data.needs_pretest ? 'intro' : 'train')
  useEffect(() => { if (mode === 'intro') onProgress(0, 0) }, [mode, onProgress])
  useListenKeys({ active: active && mode === 'intro', onEnter: () => setMode('test') })
  if (mode === 'intro') {
    return (
      <div className="flex flex-col gap-4 lg:gap-5">
        <Heading title="먼저 소음 속 듣기 검사를 해요"
          sub="여러 사람이 떠드는 소리 속에서 문장을 한 번씩 듣고 받아써요. 연습 문장 5개 뒤에 검사 문장 20개가 나와요(약 7분). 훈련 전의 기준을 측정해 두면 나중에 다시 검사해서 비교할 수 있어요." />
        <Card>
          <ul className="flex list-disc flex-col gap-2 pl-5 text-[14px] leading-[1.6] text-ink marker:text-ink-faint">
            <li className="break-keep">검사 문장과 목소리는 훈련에 나오지 않아요.</li>
            <li className="break-keep">맞히면 소음이 커지고, 놓치면 작아져요. 전체 크기는 그대로예요.</li>
            <li className="break-keep">검사 문장의 정답은 마칠 때까지 알려 주지 않아요.</li>
          </ul>
        </Card>
        <BottomBar active={active} hint="조용한 곳에서 해요" primary={{ label: '검사 시작', onClick: () => setMode('test') }}
          secondary={{ label: '나중에 하고 훈련하기', onClick: () => setMode('train') }} />
      </div>
    )
  }
  if (mode === 'test') {
    return <NoiseTest settings={settings} voices={voices} onProgress={onProgress} active={active} noise={testNoise === 'talker2' ? 'talker2' : 'babble'}
      onDone={() => { setMode('train'); reload() }} onCancel={onExit} />
  }
  const last = data.tests?.length ? data.tests[data.tests.length - 1] : null
  return (
    <div className="flex flex-col gap-3">
      <SentenceTask data={data} settings={settings} voices={voices} onProgress={onProgress} onExit={onExit} finish={finish} noisy active={active} />
      {!data.needs_pretest && (
        <button type="button" onClick={() => { stopAll(); setMode('test') }}
          className="min-h-[44px] self-center rounded-13 px-4 text-[13px] font-bold text-ink-muted underline-offset-4 hover:underline">
          다시 검사하기{last ? ` · 지난 역치 ${fmtDb(last.srt_db)}` : ''}
        </button>
      )}
    </div>
  )
}
