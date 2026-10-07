import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import ConsonantFeedback from '../ConsonantFeedback'
import MouthAvatar from '../MouthAvatar'
import { ensureAudio, outputLatencyMs, avOffsetMs } from '../../lib/listenAudio'
import { voiceFor, snrLabel } from '../../lib/listenMix'
import { normalizeStair, skippedNote } from '../../lib/listenFlow'
import { fmtDb, fmtDuration } from '../../lib/listenView'
import BottomBar from './BottomBar'
import { TaskEnd } from './ListenComplete'
import SoundCard from './SoundCard'
import { missingCard, noiseMissingCard } from './StateCard'
import StairTrace from './StairTrace'
import { useAvFrames, useClip, useNoise, usePrefetch } from './useClip'
import { useListenKeys, usePlayer, useStageTally } from './usePlayer'
import { Card, Heading, inputClass, isDesktop } from './ui'

/**
 * 문장 받아쓰기(3단계 조용함 · 4단계 소음 속). 문장을 듣고 들은 대로 쓴다. 첫 답만 세고, 틀린 낱말은 첫 자음 단서를 보고 다시 쓴다.
 * 끝나면 정답 문장을 보인 뒤 같은 소리를 한 번 더 들려준다. 단계 레슨, 받아쓰기·소음 속 듣기·듣기 조건 연습, 오늘의 듣기, 복습에서 쓴다.
 *  - noisy: 소음 속(4단계 계단, 네 번에 한 번 소리+입모양). data.stair·next_condition을 쓴다.
 *  - condition: 계단 없이 정한 조건으로 듣는다(듣기 조건 연습). {kind: 'phone'|'room'|'noise', label, noise?, rt60?, snrDb?}
 *  - showStair: 소음 계단 흐름을 작게 보인다(소음 속 듣기 연습. 연습 계단이라 검사·숙달에 들어가지 않는다).
 */
const SENTENCE_HINT = '맞힌 낱말은 그대로, 틀린 낱말은 글자마다 첫 자음만 보여요. 문장을 다시 듣고 한 번 더 써 보세요. 다시 쓴 답은 점수에 넣지 않아요.'

export default function SentenceTask({ data, settings, voices, onProgress, onExit, finish, noisy, active, exitLabel = '학습 경로로',
  answerExtra = null, onAnswered = null, condition = null, showStair = false, metaLabel = null }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [answer, setAnswer] = useState('')
  const [first, setFirst] = useState(null)       // 첫 답 채점(세는 답)
  const [retry, setRetry] = useState(null)       // 자음 단서를 본 뒤 다시 쓴 답(세지 않음). {skipped:true}는 다시 쓰지 않고 정답을 본 것
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [plays, setPlays] = useState(0)
  // 이번 문항의 조건·SNR은 문항이 바뀔 때만 정한다(답 뒤에 계단이 움직여도 다시 듣기는 같은 조건으로)
  const stair0 = normalizeStair(data.stair)
  const [stair, setStair] = useState(stair0)
  const [nextCond, setNextCond] = useState(data.next_condition || 'ao')
  const [cond, setCond] = useState(data.next_condition || 'ao')
  const [snrNow, setSnrNow] = useState(stair0?.[data.next_condition || 'ao']?.next_db ?? 10)
  const [trace, setTrace] = useState(() => (Array.isArray(data.trace) ? data.trace : []))
  const [scores, setScores] = useState([])
  const [playFrames, setPlayFrames] = useState(null)
  const tally = useStageTally(data.status, onAnswered)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const inputRef = useRef(null)
  const frameTimer = useRef(null)
  const avOffsetRef = useRef(null)
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const clip = useClip(it?.text, voice)
  const fixedNoise = !noisy && condition?.kind === 'noise'
  const nz = useNoise(noisy || fixedNoise, fixedNoise ? condition.noise || 'babble' : 'babble')
  usePrefetch(items[k + 1] ? [[items[k + 1].text, voiceFor(voices.train, k + 1, 0, data.voice_mode, data.voice_block)]] : [])
  const av = noisy && cond === 'av'
  const frames = useAvFrames(it?.text, clip.clip, av)
  const snr = noisy ? snrNow : fixedNoise ? (condition.snrDb ?? 5) : null
  const needNoise = noisy || fixedNoise
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => {
    setAnswer(''); setFirst(null); setRetry(null); setErr(null); setPlays(0); setPlayFrames(null)
    clearTimeout(frameTimer.current); player.reset(); t0.current = Date.now()
  }, [k, player.reset])
  useEffect(() => () => clearTimeout(frameTimer.current), [])
  const firstAllRight = !!(first?.word_feedback && first.word_feedback.correct_words === first.word_feedback.total_words)
  const finished = !!(first && (firstAllRight || retry))
  const ready = clip.state === 'ready' && (!needNoise || nz.state === 'ready') && (!av || frames)
  const play = async () => {
    if (!ready || player.busy) return
    let opts
    if (av && frames?.length) {
      // 블루투스 등 출력 지연만큼 입모양을 늦춘다(avOffsetMs, 덜 보정). 새 배열이라 아바타가 처음부터 한 번 재생한다
      await ensureAudio()
      const offset = avOffsetMs()
      avOffsetRef.current = offset
      const fresh = frames.map((f) => ({ ...f }))
      clearTimeout(frameTimer.current)
      // 말소리가 실제로 나오는 순간에 맞춘다. 보코더·전화·방 판을 만드는 시간이 있으므로 재생이 알려 준 지연(delayMs)을 기준으로,
      // 아바타의 처음 300 ms 중립을 빼고 출력 지연 보정(offset)을 더한다(listenAudio.playClip onStart)
      const onStart = (delayMs) => {
        clearTimeout(frameTimer.current)
        frameTimer.current = setTimeout(() => setPlayFrames(fresh), Math.max(0, delayMs - 300 + offset))
      }
      opts = { gainDb: settings.gainDb, snrDb: snr, noise: nz.noise, leadMs: 300, onStart }
    } else if (condition && !noisy) {
      opts = { gainDb: settings.gainDb, phone: condition.kind === 'phone', room: condition.kind === 'room' ? (condition.rt60 ?? 0.5) : null,
        snrDb: fixedNoise ? snr : null, noise: fixedNoise ? nz.noise : null }
    } else {
      opts = { gainDb: settings.gainDb, snrDb: noisy ? snr : null, noise: noisy ? nz.noise : null }
    }
    const ok = await player.play([{ clip: clip.clip, opts }])
    if (ok && !first) {
      setPlays((p) => p + 1)
      if (isDesktop()) inputRef.current?.focus()
    }
  }
  // 정답 글을 보인 뒤 같은 소리(소음 속이면 같은 소음·SNR)를 한 번 다시 들려준다. 글 먼저, 그다음 같은 왜곡된 소리가 가장 근거 있는
  // 순서다(Davis 2005, Loebach 2010). 첫 답이 다 맞았으면 자동으로 틀지 않는다
  const playRef = useRef(null)
  const autoRef = useRef(null)
  playRef.current = play
  useEffect(() => {
    if (!finished || firstAllRight || autoRef.current === k || !active) return undefined
    autoRef.current = k
    const t = setTimeout(() => { playRef.current?.() }, 700)
    return () => clearTimeout(t)
  }, [finished, firstAllRight, k, active])
  const goNext = () => {
    player.stop()
    setCond(nextCond)
    setSnrNow(stair?.[nextCond]?.next_db ?? 10)
    setK(k + 1)
  }
  const skipItem = () => { tally.skip(); goNext() }
  const canSubmit = !!answer.trim() && plays > 0 && !sending && !finished
  const submit = async () => {
    if (!canSubmit) return
    player.stop()
    setSending(true)
    setErr(null)
    const body = { stage: noisy ? 4 : 3, item_key: it.key, answer, plays, rt_ms: Date.now() - t0.current, voice, route: settings.route,
      output_latency_ms: outputLatencyMs(), ...(answerExtra || {}) }
    if (noisy) Object.assign(body, { snr_db: snr, condition: cond })
    else if (condition) Object.assign(body, { condition: condition.kind, ...(fixedNoise ? { snr_db: snr, noise: condition.noise || 'babble' } : {}) })
    if (av && avOffsetRef.current != null) body.av_offset_ms = avOffsetRef.current
    try {
      if (!first) {
        const r = await listenAPI.answer(body)
        setFirst(r)
        tally.add(r.passed, r.status)
        setScores((s) => [...s, r.score || 0])
        if (r.stair) setStair(normalizeStair(r.stair))
        if (r.next_condition) setNextCond(r.next_condition)
        if (noisy) setTrace((t) => [...t, { snr, correct: !!r.passed, cond }].slice(-24))
      } else {
        setRetry(await listenAPI.answer({ ...body, practice: true }))
      }
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  useListenKeys({ active: active && !!it, onPlay: play, canPlay: ready && !player.busy,
    onEnter: finished ? goNext : clip.state === 'missing' ? skipItem : submit, canEnter: finished || clip.state === 'missing' || canSubmit })

  if (!it) {
    const avgWords = scores.length ? `${Math.round((scores.reduce((x, y) => x + y, 0) / scores.length) * 100)}%` : '–'
    const result = { stage: noisy ? 4 : 3, n: tally.n, c: tally.c, skipped: tally.skipped, mastered: tally.mastered, elapsed: tally.elapsed(),
      stair, trace, avgWords }
    return (
      <TaskEnd finish={finish} result={result}
        title={tally.n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'}
        sub={tally.mastered ? `${noisy ? '소음 속 듣기' : '문장 알아듣기'}를 숙달했어요. 다음 단계가 열렸어요.` : null}
        stats={tally.n ? [
          { label: '통과한 문장', value: `${tally.c} / ${tally.n}`, main: true },
          noisy ? { label: '소리만 역치', value: fmtDb(stair?.ao?.srt_db), note: '낮을수록 시끄러운 곳에서 잘 들어요' } : { label: '낱말 정확도', value: avgWords, note: '첫 답 평균' },
          { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }] : []}
        notes={[skippedNote(tally.skipped)]} />
    )
  }
  const shownTarget = (retry && !retry.skipped && retry.target) || first?.target || it.text
  const barTone = finished ? (first.passed ? 'good' : 'bad') : null
  const needRetry = first && !firstAllRight && !retry
  const meta = [
    metaLabel,
    noisy && (cond === 'av' ? '소리 + 입모양' : '소리만'), noisy && snrLabel(snr),
    !noisy && condition?.label, fixedNoise && snrLabel(snr),
    it.review && '며칠 전에 놓친 문장',
  ].filter(Boolean).join(' · ') || null
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="문장을 듣고 들은 대로 써요" meta={meta} sub={k === 0 && !first ? data.guide : null} />
      {showStair && noisy && <StairTrace trace={trace} now={snr} />}
      {clip.state === 'missing' ? missingCard(clip, skipItem) : needNoise && nz.state === 'missing' ? noiseMissingCard(nz, onExit, exitLabel) : (
        <>
          {av && (
            <div className="overflow-hidden rounded-18 border-2 border-line bg-white lg:rounded-22">
              <MouthAvatar frames={playFrames} once height={null} className="h-[150px] lg:h-[220px]" showTalker={false} />
            </div>
          )}
          {av && settings.route === 'stream' && (
            <p className="break-keep text-[12px] leading-[1.6] text-ink-faint">블루투스로 바로 들으면 소리가 입모양보다 늦게 들릴 수 있어요. 어긋나 보이면 스피커나 유선 이어폰으로 들어 보세요.</p>
          )}
          <SoundCard player={player} onPlay={play} clipState={ready ? 'ready' : 'loading'} label={finished ? '글을 보며 다시 듣기' : first ? '문장 다시 듣기' : '문장 듣기'} plays={plays} />
          {!finished && (
            <form onSubmit={(e) => { e.preventDefault(); submit() }}>
              <label htmlFor="listen-answer" className="sr-only">들은 문장</label>
              <input id="listen-answer" ref={inputRef} value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!plays || sending}
                autoComplete="off" enterKeyHint="done" placeholder={plays ? (first ? '단서를 보고 다시 써요' : '들은 말을 써요') : '먼저 문장을 들어요'} className={inputClass} />
            </form>
          )}
          {needRetry && (
            <ConsonantFeedback feedback={first.word_feedback} tone="neutral" hint={SENTENCE_HINT}
              title={first.word_feedback?.correct_words > 0 ? null : '조금 더 들어 볼까요?'} />
          )}
          {finished && (
            <Card className="flex flex-col gap-1.5">
              <p className="text-[13px] font-bold text-ink-muted">정답 문장</p>
              <p className="break-keep text-[19px] font-bold leading-snug text-ink lg:text-[21px]">{shownTarget}</p>
              {!firstAllRight && <p className="text-[12px] text-ink-faint">글을 보면서 같은 소리를 한 번 더 들려줘요.</p>}
            </Card>
          )}
          <BottomBar active={active} tone={barTone}
            title={finished ? (first.passed ? '통과했어요' : '아쉬워요') : null}
            sub={finished ? `첫 답 낱말 ${Math.round((first.score || 0) * 100)}% 맞음${retry && !retry.skipped ? ` · 다시 쓴 답 ${Math.round((retry.score || 0) * 100)}%` : ''}` : null}
            hint={!plays ? '먼저 문장을 들어요' : needRetry ? '다시 쓴 답은 점수에 넣지 않아요' : '들은 대로 쓰고 Enter'}
            alert={err}
            primary={finished ? { label: '계속하기', onClick: goNext }
              : { label: sending ? '보내는 중' : needRetry ? '다시 쓴 답 확인' : '확인', onClick: submit, disabled: !canSubmit }}
            secondary={needRetry ? { label: '정답 보기', onClick: () => { player.stop(); setRetry({ skipped: true }) } } : null} />
        </>
      )}
    </div>
  )
}
