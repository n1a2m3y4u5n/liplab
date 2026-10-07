import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listenAPI, learningAPI } from '../api'
import ConsonantFeedback from '../components/ConsonantFeedback'
import MouthAvatar from '../components/MouthAvatar'
import { loadClip, loadVoices, loadNoise, playClip, lingClip, silence, stopAll, ensureAudio, outputLatencyMs, avOffsetMs, setSimMode } from '../lib/listenAudio'
import { readSettings, writeSettings, clampGainDb, voiceRoles, voiceFor, fitFramesToAudio, snrLabel, contrastText,
  DEVICES, ROUTES, GAIN_MIN_DB, GAIN_MAX_DB } from '../lib/listenMix'
import { listenKeyAction, sequenceMs, soundStatusText, fmtDb, fmtDuration, levelChangeText, testStep } from '../lib/listenView'

/**
 * 소리 듣기(청능훈련) 레슨: /learn/listening?stage=N (backend listen_curriculum, docs/auditory-training-design.md).
 * 루트에 data-track="listen"을 달아 트랙색(버튼·진행바)이 청록이 된다. 레슨 틀은 독화·말하기 레슨과 같다:
 * 위에 X · 진행바 · n / 전체, 가운데에 소리 카드(듣기 버튼 + 재생 상태) 하나, 아래 고정 바에 확인 → 정답·오답 → 계속하기.
 *
 * 처음에는 소리 크기 맞추기(편안한 크기·기기·듣는 길)를 거친다. 설정은 이 기기에만 저장한다(학습자 정보 원칙, C6).
 * 레슨 중에 크기를 바꿔도 묶음은 그대로 이어진다(레슨을 숨겨 두고 설정만 위에 연다).
 * 소리는 서버가 미리 합성한 음성이고(lib/listenAudio), 받지 못한 글은 '아직 들을 수 없음'으로 알리고 세지 않고 넘긴다.
 * 단계마다 과제가 다르다: 0 Ling 점검, 1 같다·다르다, 2 낱말 고르기, 3 조용한 문장 받아쓰기, 4 소음 속 문장(+검사), 5 대화 듣기.
 *
 * 접근성(청각장애 학습자): 소리 상태(준비 중·나오는 중·끝남)를 글과 막대로 늘 보인다. 막대는 시간만 보이고 소리 모양(파형)은 그리지 않는다
 * (파형은 길이·같다·다르다를 눈으로 풀게 해 듣기 훈련이 아니게 된다). 키보드: 스페이스 = 듣기, 숫자 = 보기, Enter = 확인·계속하기(lib/listenView).
 */

const IC = { close: '/ui/lp-91-12-close.svg' }
const NOTICE = '청력을 진단하거나 치료하지 않아요. 보청기·인공와우 조절은 청능사나 병원에서 해요. 귀가 아프거나 울리면 바로 멈추세요.'
const SYNTH = '소리는 기계로 미리 만든 합성 음성이에요.'
const SENTENCE_HINT = '맞힌 낱말은 그대로, 틀린 낱말은 글자마다 첫 자음만 보여요. 문장을 다시 듣고 한 번 더 써 보세요. 다시 쓴 답은 점수에 넣지 않아요.'
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // DOKA SVG 그림자 여백(Figma inset)
// 마우스·터치로 누른 버튼은 초점을 내려놓는다. 그래야 다음 Enter·스페이스가 그 버튼을 다시 누르지 않고 '확인'·'듣기'가 된다.
// 키보드로 누른 것(detail 0)은 초점을 그대로 둬 Tab 이동이 끊기지 않는다.
const releaseClickFocus = (e) => {
  if (e.detail > 0) e.target.closest?.('button')?.blur()
}
const isDesktop = () => { try { return window.matchMedia('(min-width: 1024px)').matches } catch { return false } }

function useListenSettings() {
  const [s, setS] = useState(() => readSettings())
  const save = (v) => { const next = { ...v, gainDb: clampGainDb(v.gainDb), at: new Date().toISOString() }; writeSettings(next); setS(next) }
  return [s, save]
}

/** 글 하나의 소리를 미리 받는다. state: 'loading' | 'ready' | 'missing'. retry를 부르면 다시 받는다(실패는 캐시하지 않는다). */
function useClip(text, voice) {
  const [st, setSt] = useState({ clip: null, state: 'loading' })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let on = true
    if (!text) { setSt({ clip: null, state: 'missing' }); return undefined }
    setSt({ clip: null, state: 'loading' })
    loadClip(text, voice).then((c) => { if (on) setSt({ clip: c, state: c ? 'ready' : 'missing' }) })
    return () => { on = false }
  }, [text, voice, nonce])
  const retry = useCallback(() => setNonce((n) => n + 1), [])
  return { ...st, retry }
}

function useNoise(enabled, name = 'babble') {
  const [st, setSt] = useState({ noise: null, state: enabled ? 'loading' : 'off' })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let on = true
    if (!enabled) { setSt({ noise: null, state: 'off' }); return undefined }
    setSt({ noise: null, state: 'loading' })
    loadNoise(name).then((n) => { if (on) setSt({ noise: n, state: n ? 'ready' : 'missing' }) })
    return () => { on = false }
  }, [enabled, name, nonce])
  const retry = useCallback(() => setNonce((n) => n + 1), [])
  return { ...st, retry }
}

/** 다음 문항 소리를 미리 받아 둔다(넘길 때 '준비 중'이 덜 보이게). loadClip이 캐시한다. */
function usePrefetch(pairs) {
  const key = pairs.map(([t, v]) => `${v}\n${t}`).join('|')
  useEffect(() => {
    const t = setTimeout(() => { for (const [text, voice] of pairs) if (text) loadClip(text, voice) }, 400)
    return () => clearTimeout(t)
  }, [key])   // eslint-disable-line react-hooks/exhaustive-deps
}

/**
 * 재생기. play(steps)는 소리를 차례로 튼다(steps: [{clip, opts}] 또는 [{silenceMs}]). 재생 중 다시 누르면 무시하고,
 * stop·reset(문항이 바뀔 때)은 소리를 멈추고 늦게 끝난 재생이 화면을 건드리지 못하게 한다(토큰).
 * phase: idle | playing | done. everDone은 이 문항에서 한 번이라도 끝까지 들었는가.
 */
const PLAYER0 = { phase: 'idle', part: 1, parts: 1, totalMs: 0, run: 0, everDone: false }
function usePlayer() {
  const [st, setSt] = useState(PLAYER0)
  const tok = useRef(0)
  const busyRef = useRef(false)
  const reset = useCallback(() => { tok.current += 1; busyRef.current = false; stopAll(); setSt(PLAYER0) }, [])
  const stop = useCallback(() => {
    tok.current += 1
    busyRef.current = false
    stopAll()
    setSt((s) => (s.phase === 'playing' ? { ...s, phase: s.everDone ? 'done' : 'idle' } : s))
  }, [])
  const play = useCallback(async (steps, gapMs = 600) => {
    if (busyRef.current || !steps?.length) return false
    busyRef.current = true
    const id = ++tok.current
    setSt((s) => ({ ...s, phase: 'playing', part: 1, parts: steps.length, totalMs: sequenceMs(steps, gapMs), run: s.run + 1 }))
    let ok = true
    try {
      for (let i = 0; i < steps.length; i += 1) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, gapMs))
          if (tok.current !== id) return false
          setSt((s) => ({ ...s, part: i + 1 }))
        }
        const step = steps[i]
        const r = step.silenceMs != null ? await silence(step.silenceMs) : await playClip(step.clip, step.opts || {})
        if (tok.current !== id) return false
        if (!r) { ok = false; break }
      }
    } catch { ok = false }
    if (tok.current !== id) return false
    busyRef.current = false
    setSt((s) => ({ ...s, phase: ok || s.everDone ? 'done' : 'idle', everDone: s.everDone || ok }))
    return ok
  }, [])
  useEffect(() => () => { tok.current += 1; stopAll() }, [])
  return { ...st, busy: st.phase === 'playing', play, stop, reset }
}

/** 화면 키보드(lib/listenView.listenKeyAction). cfg는 매 렌더 최신 값을 읽는다. active=false면 듣지 않는다. */
function useListenKeys(cfg) {
  const ref = useRef(cfg)
  useEffect(() => { ref.current = cfg })
  useEffect(() => {
    const onKey = (e) => {
      const c = ref.current
      if (!c || c.active === false || e.defaultPrevented) return
      const t = e.target
      const a = listenKeyAction(
        { key: e.key, code: e.code, repeat: e.repeat, altKey: e.altKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, targetTag: t?.tagName, editable: !!t?.isContentEditable },
        { canPlay: !!c.onPlay && c.canPlay !== false, optionCount: c.optionCount || 0, canPick: !!c.onPick && c.canPick !== false,
          canEnter: !!c.onEnter && c.canEnter !== false })
      if (!a) return
      e.preventDefault()
      if (a.type === 'play') c.onPlay()
      else if (a.type === 'pick') c.onPick(a.index)
      else c.onEnter()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

// ── 공통 조각 ─────────────────────────────────────────────────

function Card({ children, className = '' }) {
  return <div className={`rounded-18 border-2 border-line bg-white p-5 lg:rounded-22 lg:p-6 ${className}`}>{children}</div>
}

/** 문항 질문(독화 레슨 91:19와 같은 크기). meta는 질문 아래 작은 줄(수준·보기 수 등). */
function Heading({ title, meta, sub }) {
  return (
    <div className="flex flex-col gap-1.5 leading-figma lg:gap-2">
      <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[28px] lg:tracking-[-0.7px]">{title}</h1>
      {meta && <p className="text-[13px] font-bold text-track-dark">{meta}</p>}
      {sub && <p className="text-[14px] leading-[1.6] text-ink-muted">{sub}</p>}
    </div>
  )
}

function SpeakerIcon({ playing }) {
  return (
    <svg aria-hidden="true" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {playing ? (
        <>
          <path d="M11 5 6 9H3v6h3l5 4V5z" fill="currentColor" />
          <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
        </>
      ) : <path d="M8 5.5v13l11-6.5z" fill="currentColor" />}
    </svg>
  )
}

/** 재생 진행 막대. 시간만 보인다(소리 모양은 그리지 않는다). 재생이 시작되면 예상 길이 동안 차고, 끝나면 가득 찬 채로 둔다. */
function ProgressLine({ phase, run, totalMs }) {
  const [w, setW] = useState(0)
  useEffect(() => {
    if (phase !== 'playing') { setW(phase === 'done' ? 100 : 0); return undefined }
    setW(0)
    let alive = true
    const id = requestAnimationFrame(() => requestAnimationFrame(() => { if (alive) setW(100) }))
    return () => { alive = false; cancelAnimationFrame(id) }
  }, [phase, run])
  return (
    <div aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-fill">
      <div className={`h-full rounded-full bg-track ${phase === 'done' ? 'opacity-50' : ''}`}
        style={{ width: `${w}%`, transition: phase === 'playing' && w === 100 ? `width ${totalMs}ms linear` : 'none' }} />
    </div>
  )
}

/**
 * 소리 카드: 화면의 중심(듣기 버튼 + 상태). 버튼 왼쪽·글 오른쪽으로 낮게 둬서 1366×768 같은 낮은 화면에서도 보기까지 한 화면에 들어온다.
 * clipState: 'loading' | 'ready' | 'missing'. maxPlays를 주면 그만큼만 듣는다(검사). statusText로 상태 문구를 바꿀 수 있다(Ling 무음 시행).
 */
function SoundCard({ player, onPlay, clipState = 'ready', label, plays = 0, maxPlays = null, disabled = false, statusText = null, children }) {
  const statusId = useId()
  const limit = maxPlays != null && plays >= maxPlays
  const phase = clipState !== 'ready' ? clipState : limit && !player.busy ? 'limit' : player.phase
  const text = statusText || soundStatusText(phase, { part: player.part, parts: player.parts })
  // 재생 중에는 버튼을 회색으로 끄지 않고 눌린 모양(트랙색)으로 둔다. 회색은 '지금 들을 수 없음'일 때만
  const off = disabled || clipState !== 'ready' || limit
  const left = maxPlays != null && !limit ? ` · ${maxPlays - plays}번 더 들을 수 있어요` : ''
  return (
    <div className="rounded-18 border-2 border-line bg-white px-4 py-4 lg:rounded-22 lg:px-6 lg:py-5">
      <div className="flex items-center gap-4 lg:gap-5">
        <button type="button" onClick={player.busy ? undefined : onPlay} disabled={off && !player.busy} aria-disabled={player.busy || off}
          aria-describedby={statusId} aria-label={player.busy ? '소리가 나오고 있어요' : `${label}, 스페이스 키`}
          className={`flex size-[72px] shrink-0 items-center justify-center rounded-full border-2 text-white transition-all duration-100 disabled:cursor-not-allowed disabled:border-inactive-line disabled:bg-inactive disabled:text-inactive-text lg:size-[80px] ${
            player.busy ? 'translate-y-[2px] cursor-default border-b-2 border-track-dark bg-track-dark' : 'border-b-5 border-track-dark bg-track hover:bg-track-hover active:translate-y-[2px] active:border-b-2'}`}>
          <SpeakerIcon playing={player.busy} />
        </button>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="text-[16px] font-bold leading-figma text-ink lg:text-[17px]">{label}</p>
          <ProgressLine phase={clipState === 'ready' ? player.phase : 'idle'} run={player.run} totalMs={player.totalMs} />
          <p id={statusId} role="status" aria-live="polite" className={`text-[13px] font-bold leading-snug ${player.busy ? 'text-track-dark' : 'text-ink-muted'}`}>
            {text}
          </p>
          <p className="text-[12px] leading-snug text-ink-faint">
            {plays > 0 ? `${plays}번 들었어요${left} · ` : left ? `${left.slice(3)} · ` : ''}합성 음성<span className="hidden lg:inline"> · 스페이스 키로 듣기</span>
          </p>
        </div>
      </div>
      {children}
    </div>
  )
}

// 보기(독화 레슨 91:29와 같은 결). 정답·오답 공개는 2.5px 테두리(높이를 맞추려고 위 패딩 2px 더함).
const OPTION_BASE = 'flex min-h-[56px] w-full items-center gap-3.5 rounded-14 px-[18px] py-[13px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-track enabled:active:scale-[0.99] disabled:cursor-not-allowed`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} pt-[15px] lg:pt-[18px] border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} pt-[15px] lg:pt-[18px] border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPTION_BASE} pt-[15px] lg:pt-[18px] border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}
const OPTION_SR = { correct: ', 정답, 고른 답', target: ', 정답', wrong: ', 고른 답, 오답' }

function Option({ index, label, state = 'idle', disabled, waiting, onClick, big = false }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} aria-pressed={state === 'selected' || state === 'idle' ? state === 'selected' : undefined}
      aria-label={`${index + 1}번 ${label}${OPTION_SR[state] || ''}`}
      className={`${OPTION_CLASS[state]} ${waiting ? 'opacity-50' : ''}`}>
      <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{index + 1}</span>
      <span className={`min-w-0 flex-1 break-keep font-bold leading-snug ${big ? 'text-[19px] lg:text-[21px]' : 'text-[16px] lg:text-[17px]'}`}>{label}</span>
    </button>
  )
}

/** 보기 공개 상태: 결과 전에는 고른 것만, 결과 뒤에는 정답·고른 오답. */
function optionState(i, { picked, result, answer }) {
  if (!result) return picked === i ? 'selected' : 'idle'
  if (i === answer) return picked === i ? 'correct' : 'target'
  return picked === i ? 'wrong' : 'idle'
}

/**
 * 하단 고정 바(독화 레슨 130:17 · 94:133 · 94:175와 같은 틀). tone: null(문제) | 'good' | 'bad'.
 * 바 높이를 --listen-bar-h로 알려 페이지가 그만큼 아래 여백을 둔다(글자 크게 설정으로 바가 높아져도 내용·안내문이 바 뒤로 숨지 않는다).
 */
const BAR_TONE = { good: 'border-good bg-good-tint lg:border-good/35', bad: 'border-bad bg-bad-tint lg:border-bad/35' }
const BAR_BTN = 'btn-bar w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'
function BottomBar({ active = true, tone = null, title, sub, hint, alert, primary, secondary }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    const root = document.documentElement
    if (!el) return undefined
    const set = () => root.style.setProperty('--listen-bar-h', `${el.offsetHeight + 12}px`)
    set()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(set) : null
    ro?.observe(el)
    return () => { ro?.disconnect(); root.style.setProperty('--listen-bar-h', '0px') }
  }, [active])
  if (!active) return null
  const textTone = tone === 'good' ? 'text-good-text' : tone === 'bad' ? 'text-bad-text' : 'text-ink'
  const btnTone = tone === 'good' ? 'btn-good' : tone === 'bad' ? 'btn-bad' : 'btn-primary'
  return (
    <>
      <div ref={ref} className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${BAR_TONE[tone] || 'border-line bg-white'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(18px+env(safe-area-inset-bottom))] pt-4 lg:min-h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-4">
          <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${textTone} ${title || alert ? '' : 'max-lg:hidden'}`}>
            {alert ? (
              <p role="alert" className="text-[15px] font-bold leading-snug text-bad-text">{alert}</p>
            ) : title ? (
              <>
                <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{title}</p>
                {sub && <p className="break-keep text-[13px] font-bold leading-snug opacity-80 lg:text-[14px]">{sub}</p>}
              </>
            ) : hint ? <span className="text-[15px] text-ink-faint">{hint}</span> : null}
          </div>
          {(primary || secondary) && (
            <div className="flex gap-2 max-lg:flex-col-reverse lg:shrink-0">
              {secondary && (
                <button type="button" onClick={secondary.onClick} disabled={secondary.disabled} className={`btn-secondary ${BAR_BTN} max-lg:py-3`}>{secondary.label}</button>
              )}
              {primary && (
                <button type="button" onClick={primary.onClick} disabled={primary.disabled} className={`${btnTone} ${BAR_BTN} disabled:cursor-not-allowed disabled:border-inactive-line disabled:bg-inactive disabled:text-inactive-text`}>{primary.label}</button>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/** 상태 안내 카드(준비 전·오류·잠김). 다음 행동은 actions(첫 번째가 주 버튼). */
function StateCard({ title, body, actions = [] }) {
  return (
    <Card className="flex flex-col items-center gap-3 py-8 text-center">
      <p role="status" className="text-[17px] font-bold leading-snug text-ink">{title}</p>
      {body && <p className="max-w-[420px] break-keep text-[14px] leading-[1.6] text-ink-muted">{body}</p>}
      {actions.length > 0 && (
        <div className="mt-2 flex w-full max-w-[360px] flex-col gap-2">
          {actions.map((a, i) => (
            <button key={a.label} type="button" onClick={a.onClick} className={`${i === 0 ? 'btn-primary' : 'btn-secondary'} py-3 text-[15px]`}>{a.label}</button>
          ))}
        </div>
      )}
    </Card>
  )
}

/** 불러오는 중: 화면 모양만 흐리게(질문 · 소리 카드 · 보기). */
function Skeleton() {
  return (
    <div role="status" aria-label="불러오는 중" className="flex animate-pulse-slow flex-col gap-4 lg:gap-5">
      <div className="h-7 w-3/4 rounded-10 bg-fill lg:h-9" />
      <div className="h-[104px] rounded-18 border-2 border-line bg-white lg:h-[124px] lg:rounded-22" />
      <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-[56px] rounded-14 bg-fill lg:h-[60px]" />)}
      </div>
      <span className="sr-only">불러오는 중이에요</span>
    </div>
  )
}

const missingCard = (clip, onSkip) => (
  <StateCard title="이 소리를 아직 들을 수 없어요"
    body="소리가 아직 준비되지 않았거나 인터넷 연결이 끊겼어요. 다시 받아 보거나, 이 문항은 세지 않고 넘어가요."
    actions={[{ label: '다시 받기', onClick: clip.retry }, { label: '이 문항 넘기기', onClick: onSkip }]} />
)

/**
 * 묶음 끝 화면(독화 레슨 완료 93:12와 같은 결): 소리 듣기 DOKA + 스탯 칸 + 버튼 2개. 화면 전체를 덮는다.
 * stats: [{label, value, note, main}], main은 트랙색 값. Enter = 주 버튼.
 */
const GRID = { 1: 'grid-cols-1', 2: 'grid-cols-2', 3: 'grid-cols-3' }
function ListenComplete({ title, sub, stats = [], notes = [], primary, secondary, children }) {
  const h = useRef(null)
  useEffect(() => { h.current?.focus() }, [])
  useListenKeys({ onEnter: primary?.onClick })
  return (
    <div data-track="listen" className="fixed inset-0 z-50 overflow-y-auto bg-page" onClick={releaseClickFocus}>
      <div className="mx-auto flex min-h-full w-full max-w-[640px] flex-col items-center justify-center gap-6 px-[18px] py-12">
        <span className="relative size-[112px] shrink-0 lg:size-[132px]">
          <img src="/ui/listen-node-current.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
        </span>
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 ref={h} tabIndex={-1} className="break-keep text-[28px] font-bold leading-figma tracking-[-0.7px] text-ink outline-none lg:text-[36px] lg:tracking-[-0.9px]">{title}</h1>
          {sub && <p className="break-keep text-[15px] leading-[1.6] text-ink-muted">{sub}</p>}
        </div>
        {stats.length > 0 && (
          <div className={`grid w-full gap-2.5 lg:gap-3.5 ${GRID[stats.length] || 'grid-cols-3'}`}>
            {stats.map((s) => (
              <div key={s.label} className="flex min-w-0 flex-col gap-1.5 rounded-18 border-2 border-line bg-white p-3.5 lg:gap-2 lg:p-5">
                <p className="text-[13px] font-bold leading-figma text-ink-soft">{s.label}</p>
                <p className={`break-keep text-[19px] font-bold leading-figma tracking-[-0.4px] lg:text-[26px] ${s.main ? 'text-track-dark' : 'text-ink'}`}>{s.value}</p>
                {s.note && <p className="break-keep text-[12px] leading-snug text-ink-faint">{s.note}</p>}
              </div>
            ))}
          </div>
        )}
        {children}
        {notes.filter(Boolean).map((n, i) => (
          <p key={i} className="w-full break-keep rounded-14 bg-surface-sunken px-4 py-3 text-[14px] leading-[1.6] text-ink">{n}</p>
        ))}
        <div className="flex w-full flex-col gap-2.5 lg:gap-3">
          {primary && <button type="button" onClick={primary.onClick} className="btn-primary btn-lg w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]">{primary.label}</button>}
          {secondary && <button type="button" onClick={secondary.onClick} className="btn-secondary btn-lg w-full text-track-dark max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]">{secondary.label}</button>}
        </div>
        <p className="break-keep text-center text-[12px] leading-[1.6] text-ink-faint">{NOTICE}</p>
      </div>
    </div>
  )
}

/** 묶음 끝의 버튼: 이번에 숙달했으면 다음 단계로, 아니면 한 묶음 더. */
function completeActions({ stage, mastered, reload, onExit, onStage }) {
  if (mastered && stage < 5) {
    return { primary: { label: '다음 단계로', onClick: () => onStage(stage + 1) }, secondary: { label: '학습 경로로', onClick: onExit } }
  }
  return { primary: { label: '한 묶음 더 하기', onClick: reload }, secondary: { label: '학습 경로로', onClick: onExit } }
}
const pct = (c, n) => (n ? `${Math.round((c / n) * 100)}%` : '–')
const skippedNote = (n) => (n > 0 ? `소리를 받지 못한 ${n}문항은 세지 않고 넘겼어요.` : null)

// ── 소리 크기 맞추기 ───────────────────────────────────────────

const CALIBRATION_TEXT = '안녕하세요. 이 정도 크기가 편안한가요?'

// 인공와우 모의(청인 예비 파일럿): 연구진이 주소에 ?sim=ci를 붙여 열었거나 이미 켠 기기에서만 고를 수 있다. 학습자 화면에는 보이지 않는다
function simAllowed(initial) {
  try { return initial?.sim === 'ci' || new URLSearchParams(window.location.search).get('sim') === 'ci' } catch { return false }
}

function ChoiceGroup({ legend, options, value, onChange, cols }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-[15px] font-bold text-ink">{legend}</legend>
      <div role="radiogroup" aria-label={legend} className={`grid gap-2 ${cols}`}>
        {options.map((o) => {
          const on = value === o.key
          return (
            <button key={o.key} type="button" role="radio" aria-checked={on} onClick={() => onChange(o.key)}
              className={`flex min-h-[48px] items-center gap-2.5 rounded-13 border-2 px-3.5 py-2.5 text-left text-[15px] font-bold leading-snug transition-colors ${on ? 'border-track bg-track-tint text-track-dark' : 'border-line bg-white text-ink hover:border-track'}`}>
              <span aria-hidden className={`flex size-[18px] shrink-0 items-center justify-center rounded-full border-2 ${on ? 'border-track-dark' : 'border-line-strong'}`}>
                {on && <span className="size-2 rounded-full bg-track-dark" />}
              </span>
              <span className="min-w-0 break-keep">{o.label}</span>
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

function ListenSetup({ initial, onSave, onCancel }) {
  const [gainDb, setGainDb] = useState(initial?.gainDb ?? -15)
  const [sim, setSim] = useState(initial?.sim === 'ci' || (simAllowed(initial) && !initial))
  const showSim = simAllowed(initial)
  const [device, setDevice] = useState(initial?.device || 'unknown')
  const [route, setRoute] = useState(initial?.route || 'speaker')
  const player = usePlayer()
  const sample = useClip(CALIBRATION_TEXT, '')
  const test = async () => {
    const c = sample.clip || await lingClip('a')
    await player.play([{ clip: c, opts: { gainDb, sim: sim ? 'ci' : null } }])
  }
  const step = (d) => setGainDb((g) => clampGainDb(g + d))
  const save = () => { player.stop(); onSave({ gainDb, device, route, ...(sim && showSim ? { sim: 'ci' } : {}) }) }
  useListenKeys({ onPlay: test, canPlay: sample.state !== 'loading' && !player.busy, onEnter: save })
  const level = Math.round(((gainDb - GAIN_MIN_DB) / (GAIN_MAX_DB - GAIN_MIN_DB)) * 100)
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="소리 크기 맞추기" sub="평소처럼 보청기나 인공와우를 켜고 예시 소리를 들으며 편안한 크기를 골라요. 연습하는 동안 이 크기를 넘지 않아요." />
      <SoundCard player={player} onPlay={test} clipState={sample.state === 'loading' ? 'loading' : 'ready'}
        label={sample.state === 'ready' ? '예시 문장 듣기' : '예시 소리 듣기(합성 모음)'} />
      <Card className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <p id="listen-gain-label" className="text-[15px] font-bold text-ink">크기</p>
          <p className="text-[15px] font-bold text-track-dark">{level}<span className="text-[12px] font-normal text-ink-faint"> / 100 · {gainDb} dB</span></p>
        </div>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => step(-1)} disabled={gainDb <= GAIN_MIN_DB} aria-label="한 칸 작게"
            className="btn-secondary flex size-11 shrink-0 items-center justify-center p-0 text-[20px]">−</button>
          <input type="range" min={GAIN_MIN_DB} max={GAIN_MAX_DB} step={1} value={gainDb} onChange={(e) => setGainDb(Number(e.target.value))}
            aria-labelledby="listen-gain-label" aria-valuetext={`100 중 ${level}`} className="h-11 min-w-0 flex-1 accent-[var(--track)]" />
          <button type="button" onClick={() => step(1)} disabled={gainDb >= GAIN_MAX_DB} aria-label="한 칸 크게"
            className="btn-secondary flex size-11 shrink-0 items-center justify-center p-0 text-[20px]">+</button>
        </div>
        <div aria-hidden className="flex justify-between px-14 text-[12px] text-ink-faint"><span>작게</span><span>크게</span></div>
      </Card>
      <Card className="flex flex-col gap-5">
        <ChoiceGroup legend="쓰는 기기" options={DEVICES} value={device} onChange={setDevice} cols="grid-cols-1 sm:grid-cols-2" />
        <ChoiceGroup legend="듣는 방법" options={ROUTES} value={route} onChange={setRoute} cols="grid-cols-1" />
        {showSim && (
          <label className="flex min-h-[48px] items-start gap-3 rounded-13 border-2 border-line bg-surface-sunken px-4 py-3">
            <input type="checkbox" checked={sim} onChange={(e) => setSim(e.target.checked)} className="mt-1 size-4 accent-[var(--track)]" />
            <span className="text-[13px] leading-[1.6] text-ink">
              <b>인공와우 모의(연구용)</b> · 청인 참여자가 인공와우를 흉내 낸 소리(8채널 보코더)로 들어요. 예비 파일럿에서만 켜요.
            </span>
          </label>
        )}
      </Card>
      <p className="break-keep text-[12px] leading-[1.6] text-ink-faint">{SYNTH} 기기 정보는 이 기기에만 저장돼요. {NOTICE}</p>
      <BottomBar hint="편안한 크기를 고른 뒤 시작해요"
        primary={{ label: initial ? '이 크기로 저장' : '이 크기로 시작', onClick: save }}
        secondary={onCancel ? { label: '취소', onClick: () => { player.stop(); onCancel() } } : null} />
    </div>
  )
}

// ── 0단계: Ling 6소리 ──────────────────────────────────────────

const LING_LABEL = { m: '음', u: '우', a: '아', i: '이', sh: '쉬', s: '스' }

function LingCheck({ data, settings, onProgress, onExit, onStage, active }) {
  const seq = data.sequence || []
  const [k, setK] = useState(0)
  const res = useRef({ results: {}, fa: 0 })
  const [summary, setSummary] = useState(null)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)
  const player = usePlayer()
  useEffect(() => { onProgress(Math.min(k, seq.length), seq.length) }, [k, seq.length, onProgress])
  useEffect(() => { player.reset() }, [k, player.reset])
  const cur = seq[k]
  const heardOnce = player.everDone
  // Ling 소리는 화면이 합성한다(lingClip). 받는 동안도 '나오는 중'과 구별되지 않게 미리 만들어 둔다
  const [clips, setClips] = useState({})
  useEffect(() => {
    let on = true
    Promise.all(Object.keys(LING_LABEL).map(async (key) => [key, await lingClip(key)]))
      .then((pairs) => { if (on) setClips(Object.fromEntries(pairs)) }).catch(() => {})
    return () => { on = false }
  }, [])
  const ready = cur === 'silent' || !!clips[cur]
  const playNow = () => {
    if (!cur || !ready) return
    player.play([cur === 'silent' ? { silenceMs: 1400 } : { clip: clips[cur], opts: { gainDb: settings.gainDb } }])
  }
  const submit = async () => {
    setSaving(true)
    setErr(null)
    try {
      const r = await listenAPI.ling({ results: res.current.results, false_alarms: res.current.fa, route: settings.route })
      setSummary(r.summary)
    } catch { setErr('결과를 저장하지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSaving(false)
  }
  const answer = (heard) => {
    if (!heardOnce || player.busy || k >= seq.length) return
    if (cur === 'silent') { if (heard) res.current.fa += 1 } else res.current.results[cur] = heard
    if (k + 1 < seq.length) { setK(k + 1); return }
    setK(seq.length)
    submit()
  }
  const done = k >= seq.length
  useListenKeys({ active: active && !done, onPlay: playNow, canPlay: ready && !player.busy, optionCount: 2, canPick: heardOnce && !player.busy,
    onPick: (i) => answer(i === 0) })

  if (summary) {
    return (
      <ListenComplete title="오늘의 소리 확인"
        sub={summary.missed.length === 0 ? '여섯 소리가 모두 들렸어요.' : `여섯 소리 중 ${summary.heard.length}개가 들렸어요.`}
        notes={[
          summary.dropped.length > 0 && `지난번에 들리던 ${summary.dropped.map((x) => LING_LABEL[x]).join('·')} 소리가 오늘은 안 들렸어요. 배터리와 기기 상태를 확인해 보세요. 계속 안 들리면 청능사나 병원에 알려요.`,
          !summary.reliable && `소리가 없을 때도 '들렸어요'를 ${summary.false_alarms}번 눌렀어요. 다음에는 확실히 들릴 때만 눌러 보세요.`,
          summary.missed.length > 0 && summary.dropped.length === 0 && '안 들린 소리가 있어도 괜찮아요. 남은 청력에 맞춰 다음 단계에서 연습해요.',
        ]}
        primary={{ label: '소리 구별 하러 가기', onClick: () => onStage(1) }} secondary={{ label: '학습 경로로', onClick: onExit }}>
        <div className="grid w-full grid-cols-3 gap-2 sm:grid-cols-6">
          {(data.sounds || []).map((s) => {
            const ok = summary.heard.includes(s.key)
            return (
              <div key={s.key} className={`flex flex-col items-center gap-0.5 rounded-14 border-2 py-3 ${ok ? 'border-good/40 bg-good-tint' : 'border-bad/30 bg-bad-tint'}`}>
                <span className="text-[20px] font-bold text-ink">{s.label}</span>
                <span className="text-[12px] text-ink-muted">{s.band}</span>
                <span className={`text-[12px] font-bold ${ok ? 'text-good-text' : 'text-bad-text'}`}>{ok ? '들림' : '안 들림'}</span>
              </div>
            )
          })}
        </div>
      </ListenComplete>
    )
  }
  if (done) {
    return (
      <>
        <StateCard title={saving ? '결과를 저장하고 있어요' : '결과를 저장하지 못했어요'} body={saving ? null : err} />
        <BottomBar active={active} alert={!saving ? err : null} primary={!saving ? { label: '다시 저장하기', onClick: submit } : null}
          secondary={!saving ? { label: '학습 경로로', onClick: onExit } : null} />
      </>
    )
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title={heardOnce ? '소리가 들렸나요?' : '버튼을 눌러 소리를 들어요'}
        meta={`소리 ${k + 1} / ${seq.length}`} sub={k === 0 ? '아무 소리가 나지 않는 차례도 있어요. 들렸을 때만 \'들렸어요\'를 눌러요.' : null} />
      {/* 무음 시행이 드러나지 않게 상태 문구는 소리가 있든 없든 같다 */}
      <SoundCard player={player} onPlay={playNow} clipState={ready ? 'ready' : 'loading'} label="소리 내기"
        statusText={player.busy ? '잘 들어 보세요' : player.phase === 'done' ? '끝났어요. 들렸는지 골라요' : null} />
      <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
        {['들렸어요', '안 들렸어요'].map((l, i) => (
          <Option key={l} index={i} label={l} big disabled={!heardOnce || player.busy} waiting={!heardOnce} onClick={() => answer(i === 0)} />
        ))}
      </div>
      <p className="hidden text-center text-[13px] text-ink-faint lg:block">스페이스 키로 듣고, 1·2 키로 골라요</p>
    </div>
  )
}

// ── 1단계: 같다·다르다 ─────────────────────────────────────────

function useStageTally(initialStatus) {
  const [t, setT] = useState({ n: 0, c: 0, skipped: 0, mastered: false })
  const start = useRef(Date.now())
  const add = (correct, status) => setT((s) => ({ ...s, n: s.n + 1, c: s.c + (correct ? 1 : 0),
    mastered: s.mastered || (status === 'mastered' && initialStatus !== 'mastered') }))
  const skip = () => setT((s) => ({ ...s, skipped: s.skipped + 1 }))
  const elapsed = () => Math.floor((Date.now() - start.current) / 1000)
  return { ...t, add, skip, elapsed }
}

function AxDrill({ data, settings, voices, onProgress, onExit, onStage, reload, active }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [picked, setPicked] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [plays, setPlays] = useState(0)
  const [level, setLevel] = useState(data.level)
  const [change, setChange] = useState(null)
  const tally = useStageTally(data.status)
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
        pick: it.pick })
      setRes(r)
      tally.add(r.correct, r.status)
      if (r.level != null) { setChange(levelChangeText(level, r.level, data.levels)); setLevel(r.level) }
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  const next = () => { player.stop(); setK(k + 1) }
  const skip = () => { tally.skip(); next() }
  useListenKeys({ active: active && !!it, onPlay: play, canPlay: ready && !player.busy, optionCount: 2, canPick: canAnswer, onPick: setPicked,
    onEnter: res ? next : clipState === 'missing' ? skip : confirm, canEnter: res ? true : clipState === 'missing' || (canAnswer && picked != null) })

  if (!it) {
    const acts = completeActions({ stage: 1, mastered: tally.mastered, reload, onExit, onStage })
    return (
      <ListenComplete title={tally.n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={tally.mastered ? '소리 구별을 숙달했어요. 다음 단계가 열렸어요.' : null}
        stats={tally.n ? [{ label: '정답률', value: pct(tally.c, tally.n), note: `${tally.n}문항 중 ${tally.c}문항`, main: true },
          { label: '지금 수준', value: `${level} / ${data.levels}` }, { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }] : []}
        notes={[skippedNote(tally.skipped)]} {...acts} />
    )
  }
  const sameVoice = it.voice_pair?.[1] === it.voice_pair?.[0] || voices.train.length < 2
  const answerIdx = res ? (res.same ? 0 : 1) : null
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="두 소리가 같나요, 다른가요?" meta={`수준 ${level} / ${data.levels} · ${it.kind_label}`}
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

// ── 2단계: 낱말 고르기 ─────────────────────────────────────────

function WordId({ data, settings, voices, onProgress, onExit, onStage, reload, active }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [res, setRes] = useState(null)
  const [picked, setPicked] = useState(null)
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [plays, setPlays] = useState(0)
  const [level, setLevel] = useState(data.level)
  const [change, setChange] = useState(null)
  const tally = useStageTally(data.status)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const target = useClip(it?.target, voice)
  const pickedWord = picked != null ? it?.options?.[picked] : null
  const heard = useClip(res && !res.correct ? pickedWord : null, voice)
  usePrefetch(items[k + 1] ? [[items[k + 1].target, voiceFor(voices.train, k + 1, 0, data.voice_mode, data.voice_block)]] : [])
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
        voice, route: settings.route, pick: it.pick })
      setRes(r)
      tally.add(r.correct, r.status)
      if (r.level != null) { setChange(levelChangeText(level, r.level, data.levels)); setLevel(r.level) }
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  const next = () => { player.stop(); setK(k + 1) }
  const skip = () => { tally.skip(); next() }
  useListenKeys({ active: active && !!it, onPlay: () => play(), canPlay: target.state === 'ready' && !player.busy, optionCount: it?.options?.length || 0,
    canPick: canAnswer, onPick: setPicked,
    onEnter: res ? next : target.state === 'missing' ? skip : confirm, canEnter: res ? true : target.state === 'missing' || (canAnswer && picked != null) })

  if (!it) {
    const acts = completeActions({ stage: 2, mastered: tally.mastered, reload, onExit, onStage })
    return (
      <ListenComplete title={tally.n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={tally.mastered ? '낱말 고르기를 숙달했어요. 다음 단계가 열렸어요.' : null}
        stats={tally.n ? [{ label: '정답률', value: pct(tally.c, tally.n), note: `${tally.n}문항 중 ${tally.c}문항`, main: true },
          { label: '지금 수준', value: `${level} / ${data.levels}` }, { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }] : []}
        notes={[skippedNote(tally.skipped)]} {...acts} />
    )
  }
  const answerIdx = res ? it.options.indexOf(res.target) : null
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="들은 낱말을 골라요" meta={`수준 ${level} / ${data.levels} · 보기 ${it.options.length}개${it.review ? ' · 다시 듣는 낱말' : ''}`}
        sub={k === 0 && !res ? data.guide : null} />
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

// ── 낱말 일반화 검사(청인 파일럿, ?stage=2&wordtest=1) ──────────────────

function WordTest({ settings, voices, onProgress, onExit, active }) {
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
      if (e?.response) setFatal('답을 기록하지 못했어요. 검사를 처음부터 다시 해 주세요.')
      else setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.')
    }
    setSending(false)
  }
  useListenKeys({ active: active && !!it && !result && !fatal, onPlay: play, canPlay: clip.state === 'ready' && !player.busy && plays < 2,
    optionCount: it?.options?.length || 0, canPick: canAnswer, onPick: setPicked, onEnter: confirm, canEnter: canAnswer && picked != null })

  if (fatal) return <StateCard title={fatal} actions={[{ label: '검사 다시 시작', onClick: () => { setRun(null); setNonce((n) => n + 1) } }, { label: '학습 경로로', onClick: onExit }]} />
  if (!run) return <Skeleton />
  if (result) {
    return <ListenComplete title="낱말 검사를 마쳤어요" stats={[{ label: '맞힌 낱말', value: `${Math.round(result.accuracy * run.items.length)} / ${run.items.length}`, main: true }]}
      sub="훈련에 나오지 않은 낱말로 측정했어요. 정답은 따로 알려 주지 않아요." primary={{ label: '학습 경로로', onClick: onExit }} />
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="들은 낱말을 골라요" meta={`낱말 검사 ${k + 1} / ${run.items.length} · 정답은 알려 주지 않아요`}
        sub={k === 0 ? '낱말마다 두 번까지 들을 수 있어요.' : null} />
      {clip.state === 'missing' ? (
        <StateCard title="검사 소리를 받지 못했어요" body="인터넷 연결을 확인하고 다시 받아 주세요." actions={[{ label: '다시 받기', onClick: clip.retry }, { label: '학습 경로로', onClick: onExit }]} />
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

// ── 3·4단계: 문장 받아쓰기(조용함 / 소음 속) ─────────────────────

function useAvFrames(text, clip, on) {
  const [frames, setFrames] = useState(null)
  useEffect(() => {
    let alive = true
    setFrames(null)
    if (!on || !text || !clip) return undefined
    learningAPI.getVisemes(text).then((d) => {
      const fs = Array.isArray(d) ? d : d?.frames || []
      if (alive) setFrames(fitFramesToAudio(fs, clip.duration_ms, clip.syllables))
    }).catch(() => { if (alive) setFrames([]) })
    return () => { alive = false }
  }, [text, clip, on])
  return frames
}

const noiseMissingCard = (nz, onExit) => (
  <StateCard title="잡음 소리를 받지 못했어요" body="이 단계는 잡음이 있어야 연습할 수 있어요. 인터넷 연결을 확인하고 다시 받아 주세요."
    actions={[{ label: '다시 받기', onClick: nz.retry }, { label: '학습 경로로', onClick: onExit }]} />
)

const inputClass = 'w-full rounded-14 border-2 border-line bg-white px-4 py-3.5 text-[17px] text-ink outline-none focus:border-track disabled:bg-surface-sunken disabled:text-ink-faint lg:rounded-16 lg:text-[18px]'

function SentenceTask({ data, settings, voices, onProgress, onExit, onStage, reload, noisy, active }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [answer, setAnswer] = useState('')
  const [first, setFirst] = useState(null)       // 첫 답 채점(세는 답)
  const [retry, setRetry] = useState(null)       // 자음 단서를 본 뒤 다시 쓴 답(세지 않음). {skipped:true}는 다시 쓰지 않고 정답을 본 것
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [plays, setPlays] = useState(0)
  // 이번 문항의 조건·SNR은 문항이 바뀔 때만 정한다(답 뒤에 계단이 움직여도 다시 듣기는 같은 조건으로)
  const [stair, setStair] = useState(data.stair || null)
  const [nextCond, setNextCond] = useState(data.next_condition || 'ao')
  const [cond, setCond] = useState(data.next_condition || 'ao')
  const [snrNow, setSnrNow] = useState(data.stair?.[data.next_condition || 'ao']?.next_db ?? 10)
  const [scores, setScores] = useState([])
  const [playFrames, setPlayFrames] = useState(null)
  const tally = useStageTally(data.status)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const inputRef = useRef(null)
  const frameTimer = useRef(null)
  const avOffsetRef = useRef(null)
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const clip = useClip(it?.text, voice)
  const nz = useNoise(noisy)
  usePrefetch(items[k + 1] ? [[items[k + 1].text, voiceFor(voices.train, k + 1, 0, data.voice_mode, data.voice_block)]] : [])
  const av = noisy && cond === 'av'
  const frames = useAvFrames(it?.text, clip.clip, av)
  const snr = noisy ? snrNow : null
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => {
    setAnswer(''); setFirst(null); setRetry(null); setErr(null); setPlays(0); setPlayFrames(null)
    clearTimeout(frameTimer.current); player.reset(); t0.current = Date.now()
  }, [k, player.reset])
  useEffect(() => () => clearTimeout(frameTimer.current), [])
  const firstAllRight = !!(first?.word_feedback && first.word_feedback.correct_words === first.word_feedback.total_words)
  const finished = !!(first && (firstAllRight || retry))
  const ready = clip.state === 'ready' && (!noisy || nz.state === 'ready') && (!av || frames)
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
      frameTimer.current = setTimeout(() => setPlayFrames(fresh), offset)
      opts = { gainDb: settings.gainDb, snrDb: snr, noise: nz.noise, leadMs: 300 }
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
      output_latency_ms: outputLatencyMs() }
    if (noisy) Object.assign(body, { snr_db: snr, condition: cond })
    if (av && avOffsetRef.current != null) body.av_offset_ms = avOffsetRef.current
    try {
      if (!first) {
        const r = await listenAPI.answer(body)
        setFirst(r)
        tally.add(r.passed, r.status)
        setScores((s) => [...s, r.score || 0])
        if (r.stair) setStair(r.stair)
        if (r.next_condition) setNextCond(r.next_condition)
      } else {
        setRetry(await listenAPI.answer({ ...body, practice: true }))
      }
    } catch { setErr('답을 보내지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSending(false)
  }
  useListenKeys({ active: active && !!it, onPlay: play, canPlay: ready && !player.busy,
    onEnter: finished ? goNext : clip.state === 'missing' ? skipItem : submit, canEnter: finished || clip.state === 'missing' || canSubmit })

  if (!it) {
    const acts = completeActions({ stage: noisy ? 4 : 3, mastered: tally.mastered, reload, onExit, onStage })
    const avgWords = scores.length ? `${Math.round((scores.reduce((x, y) => x + y, 0) / scores.length) * 100)}%` : '–'
    return (
      <ListenComplete title={tally.n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'}
        sub={tally.mastered ? `${noisy ? '소음 속 듣기' : '문장 알아듣기'}를 숙달했어요. 다음 단계가 열렸어요.` : null}
        stats={tally.n ? [
          { label: '통과한 문장', value: `${tally.c} / ${tally.n}`, main: true },
          noisy ? { label: '소리만 역치', value: fmtDb(stair?.ao?.srt_db), note: '낮을수록 시끄러운 곳에서 잘 들어요' } : { label: '낱말 정확도', value: avgWords, note: '첫 답 평균' },
          { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }] : []}
        notes={[skippedNote(tally.skipped)]} {...acts} />
    )
  }
  const shownTarget = (retry && !retry.skipped && retry.target) || first?.target || it.text
  const barTone = finished ? (first.passed ? 'good' : 'bad') : null
  const needRetry = first && !firstAllRight && !retry
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="문장을 듣고 들은 대로 써요"
        meta={[noisy && (cond === 'av' ? '소리 + 입모양' : '소리만'), noisy && snrLabel(snr), it.review && '며칠 전에 놓친 문장'].filter(Boolean).join(' · ') || null}
        sub={k === 0 && !first ? data.guide : null} />
      {clip.state === 'missing' ? missingCard(clip, skipItem) : noisy && nz.state === 'missing' ? noiseMissingCard(nz, onExit) : (
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

// ── 4단계 검사: 소음 속 문장 인식 역치(연습 5문장 + 검사 20문장) ─────────────

function NoiseTest({ settings, voices, onProgress, onDone, onCancel, active, noise: noiseName = 'babble' }) {
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
    return <StateCard title={fatal} actions={[{ label: '검사 다시 시작', onClick: () => { setRun(null); setNonce((n) => n + 1) } }, { label: '학습 경로로', onClick: onCancel }]} />
  }
  if (!run) return <Skeleton />
  if (result) {
    return (
      <ListenComplete title="검사를 마쳤어요" stats={[{ label: '소음 속 문장 인식 역치', value: fmtDb(result.srt_db), main: true }]}
        sub={result.srt_db >= 24 ? '소음을 가장 작게 해도 낱말 절반을 넘기 어려웠어요. 문장 알아듣기를 더 연습하고 다시 검사해 보세요.'
          : '말이 소음보다 이만큼 클 때 낱말을 열에 넷쯤 알아들었다는 뜻이에요. 낮을수록 시끄러운 곳에서 잘 알아들어요.'}
        primary={{ label: '훈련 시작하기', onClick: onDone }} secondary={{ label: '학습 경로로', onClick: onCancel }} />
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
      {clip.state === 'missing' ? (
        <StateCard title="검사 소리를 받지 못했어요" body="인터넷 연결을 확인하고 다시 받아 주세요." actions={[{ label: '다시 받기', onClick: clip.retry }, { label: '학습 경로로', onClick: onCancel }]} />
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

function NoiseStage({ data, settings, voices, onProgress, onExit, onStage, reload, active }) {
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
      <SentenceTask data={data} settings={settings} voices={voices} onProgress={onProgress} onExit={onExit} onStage={onStage} reload={reload} noisy active={active} />
      {!data.needs_pretest && (
        <button type="button" onClick={() => { stopAll(); setMode('test') }}
          className="min-h-[44px] self-center rounded-13 px-4 text-[13px] font-bold text-ink-muted underline-offset-4 hover:underline">
          다시 검사하기{last ? ` · 지난 역치 ${fmtDb(last.srt_db)}` : ''}
        </button>
      )}
    </div>
  )
}

// ── 5단계: 대화 듣기 ─────────────────────────────────────────

const NOISE_LABEL = { babble: '여러 사람 소리', talker1_f: '여자 한 명 말소리', talker1_m: '남자 한 명 말소리', talker2: '두 사람 말소리', ssn: '웅웅 소리' }
const COND_LABEL = { quiet: '조용함', noise: '소음', phone: '전화', room: '울리는 방' }

function ConvoTask({ data, settings, voices, onProgress, onExit, onStage, reload, active }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [cond, setCond] = useState('quiet')
  const [picked, setPicked] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [sending, setSending] = useState(false)
  const [repairs, setRepairs] = useState([])
  const [plays, setPlays] = useState(0)
  const [repairTotal, setRepairTotal] = useState(0)
  const tally = useStageTally(data.status)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const line = useClip(it?.line, voice)
  const para = useClip(it?.paraphrase, voice)
  const nx = items[k + 1]
  usePrefetch(nx ? [[nx.line, voiceFor(voices.train, k + 1, 0, data.voice_mode, data.voice_block)]] : [])
  // 소음 조건은 문항마다 잡음 종류를 돌린다(경쟁 화자 1명이 인공와우 사용자에게 가장 어렵고 화자 수 효과는 단조롭지 않아 한 축으로
  // 쓰지 않는다, Chen 2020). talker2는 일반화 확인용으로 훈련에 쓰지 않는다
  const noiseName = (data.noise_types || ['babble'])[k % (data.noise_types?.length || 1)]
  const nz = useNoise(cond === 'noise', noiseName)
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setPicked(null); setErr(null); setRepairs([]); setPlays(0); player.reset(); t0.current = Date.now() }, [k, player.reset])
  // 울리는 방은 문항마다 잔향 시간을 돌린다(여러 방에서 훈련할 때 새 방으로 옮겨 갔다)
  const rt = (data.room_rt60 || [0.5])[k % (data.room_rt60?.length || 1)]
  const opts = { gainDb: settings.gainDb, phone: cond === 'phone', snrDb: cond === 'noise' ? data.noise_snr_db : null, noise: cond === 'noise' ? nz.noise : null,
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
      const r = await listenAPI.answer({ stage: 5, item_key: it.key, choice: picked, condition: cond, snr_db: cond === 'noise' ? data.noise_snr_db : null,
        repairs, plays, rt_ms: Date.now() - t0.current, voice, route: settings.route })
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
    const acts = completeActions({ stage: 5, mastered: tally.mastered, reload, onExit, onStage })
    return (
      <ListenComplete title={tally.n ? '이번 대화를 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={tally.mastered ? '대화 듣기를 숙달했어요.' : null}
        stats={tally.n ? [{ label: '정답률', value: pct(tally.c, tally.n), note: `${tally.n}문항 중 ${tally.c}문항`, main: true },
          { label: '되물은 횟수', value: `${repairTotal}번`, note: '되묻기는 감점이 없어요' }, { label: '걸린 시간', value: fmtDuration(tally.elapsed()) }] : []}
        notes={[skippedNote(tally.skipped)]} {...acts} />
    )
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <div className="flex gap-1 rounded-13 bg-surface-sunken p-1" role="radiogroup" aria-label="듣기 조건">
        {(data.conditions || ['quiet']).map((c) => (
          <button key={c} type="button" role="radio" aria-checked={cond === c} disabled={plays > 0 && cond !== c} onClick={() => setCond(c)}
            className={`min-h-[44px] flex-1 rounded-10 px-1 text-[14px] font-bold disabled:cursor-not-allowed disabled:opacity-50 ${cond === c ? 'bg-white text-track-dark shadow-seg' : 'text-ink-muted'}`}>
            {COND_LABEL[c]}
          </button>
        ))}
      </div>
      <Heading title={it.question} meta={`${it.place}${cond === 'noise' ? ` · ${NOISE_LABEL[noiseName] || '소음'}` : ''}`}
        sub={k === 0 && !plays ? '듣기 조건은 처음 듣기 전에 골라요. 못 알아들으면 되물어도 돼요.' : null} />
      {line.state === 'missing' ? missingCard(line, skip) : cond === 'noise' && nz.state === 'missing' ? noiseMissingCard(nz, onExit) : (
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

// ── 페이지 ─────────────────────────────────────────────────

const TASK = { ling: LingCheck, ax: AxDrill, word_id: WordId, sentence: SentenceTask, noise: NoiseStage, convo: ConvoTask }

export default function ListeningPractice() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const stage = Math.max(0, Math.min(5, Number(params.get('stage') ?? 0) || 0))
  const [settings, saveSettings] = useListenSettings()
  const [editing, setEditing] = useState(false)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [nonce, setNonce] = useState(0)
  const [voiceList, setVoiceList] = useState(null)
  const [prog, setProg] = useState({ cur: 0, total: 0, label: null })
  const voices = useMemo(() => voiceRoles(voiceList || []), [voiceList])

  useEffect(() => { loadVoices().then(setVoiceList) }, [])
  useEffect(() => { setSimMode(settings?.sim) }, [settings?.sim])
  useEffect(() => {
    let on = true
    setData(null)
    setErr(null)
    setProg({ cur: 0, total: 0, label: null })
    listenAPI.getStage(stage).then((d) => { if (on) setData(d) }).catch(() => { if (on) setErr(true) })
    return () => { on = false }
  }, [stage, nonce])
  useEffect(() => () => stopAll(), [])
  const onProgress = useCallback((cur, total, label = null) => setProg({ cur, total, label }), [])
  const exit = () => { stopAll(); navigate('/learn/path?track=listen') }
  const reload = () => { stopAll(); setNonce((n) => n + 1) }
  const goStage = (n) => { stopAll(); navigate(`/learn/listening?stage=${n}`) }
  const setup = !settings || editing

  const Task = data ? TASK[data.mode] : null
  const barPct = prog.total ? (prog.cur / prog.total) * 100 : 0
  const counter = prog.label || (prog.total > 0 ? `${Math.min(prog.cur + 1, prog.total)} / ${prog.total}` : null)
  const wordTest = stage === 2 && params.get('wordtest') === '1'
  return (
    <div data-track="listen" className="flex min-h-[100dvh] flex-col bg-page" style={{ paddingBottom: 'var(--listen-bar-h, 0px)' }}
      onClick={releaseClickFocus}>
      <div className="mx-auto flex w-full max-w-[676px] flex-1 flex-col px-[18px] pt-[18px] lg:pt-7 lg:[@media(max-height:860px)]:pt-5">
        {/* 진행 헤더(독화 레슨 91:13): 나가기 X + 진행바 + n / 전체 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={exit} aria-label="나가기, 학습 경로로" className="-m-1.5 shrink-0 rounded-full p-1.5">
            <img src={IC.close} alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]" role="progressbar" aria-label="진행"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(barPct)} aria-valuetext={counter || '진행 전'}>
            <div className="h-full rounded-full bg-track transition-[width] duration-500" style={{ width: `${barPct}%` }} />
          </div>
          <span className="min-w-[3.5em] shrink-0 text-right text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{!setup && counter}</span>
        </div>

        <main className="mt-6 flex flex-1 flex-col gap-4 pb-6 lg:mt-5 lg:gap-5 lg:[@media(max-height:860px)]:mt-3.5">
          <div className="flex min-h-[44px] items-center justify-between gap-3">
            <p className="min-w-0 truncate text-[12px] font-bold text-track-dark lg:text-[13px]">소리 듣기 · {stage + 1}단계{data?.title ? ` ${data.title}` : ''}</p>
            {settings && !editing && (
              <button type="button" onClick={() => { stopAll(); setEditing(true) }} className="btn-secondary min-h-[44px] shrink-0 px-3.5 py-2 text-[13px]">소리 크기</button>
            )}
          </div>
          {setup && (
            <ListenSetup initial={settings} onSave={(v) => { saveSettings(v); setEditing(false) }} onCancel={settings ? () => setEditing(false) : null} />
          )}
          {/* 크기를 바꾸는 동안에도 레슨은 숨겨 둘 뿐 그대로 둔다(묶음이 처음부터 다시 시작되지 않게) */}
          <div hidden={setup} className="flex flex-col gap-4 lg:gap-5">
            {err ? (
              <StateCard title="단계를 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러와 주세요."
                actions={[{ label: '다시 불러오기', onClick: reload }, { label: '학습 경로로', onClick: exit }]} />
            ) : !data || !voiceList ? (
              settings ? <Skeleton /> : null
            ) : data.status === 'locked' ? (
              <StateCard title="이 단계는 아직 잠겨 있어요" body="앞 단계를 숙달하면 열려요. 학습 경로에서 바로 앞 단계를 이어 하거나 건너뛸 수 있어요."
                actions={[{ label: '학습 경로로', onClick: exit }]} />
            ) : !Task ? (
              <StateCard title="이 단계를 열 수 없어요" actions={[{ label: '학습 경로로', onClick: exit }]} />
            ) : settings && (
              wordTest ? (
                <WordTest settings={settings} voices={voices} onProgress={onProgress} onExit={exit} active={!setup} />
              ) : (
                <Task key={`${stage}:${nonce}`} data={data} settings={settings} voices={voices} onProgress={onProgress} onExit={exit} onStage={goStage}
                  reload={reload} noisy={data.mode === 'noise'} active={!setup} />
              )
            )}
          </div>
          <p className="mt-auto pt-2 text-center text-[12px] leading-[1.6] text-ink-faint">{NOTICE}</p>
        </main>
      </div>
    </div>
  )
}
