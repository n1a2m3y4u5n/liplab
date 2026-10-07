import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listenAPI, learningAPI } from '../api'
import LoadingScreen from '../components/LoadingScreen'
import ConsonantFeedback from '../components/ConsonantFeedback'
import MouthAvatar from '../components/MouthAvatar'
import { loadClip, loadVoices, loadNoise, playClip, playPair, lingClip, silence, stopAll, ensureAudio, outputLatencyMs, avOffsetMs, setSimMode } from '../lib/listenAudio'
import { readSettings, writeSettings, clampGainDb, voiceRoles, voiceFor, fitFramesToAudio, snrLabel, contrastText,
  DEVICES, ROUTES, GAIN_MIN_DB, GAIN_MAX_DB } from '../lib/listenMix'

/**
 * 소리 듣기(청능훈련) 레슨 — /learn/listening?stage=N (backend listen_curriculum, docs/auditory-training-design.md).
 * 루트에 data-track="listen"을 달아 트랙색(버튼·진행바)이 청록이 된다. 레슨 틀은 말하기 레슨과 같다(X · 진행바 · n / 전체).
 *
 * 처음에는 소리 크기 맞추기(편안한 크기·기기·듣는 길)를 거친다. 설정은 이 기기에만 저장한다(학습자 정보 원칙, C6).
 * 소리는 서버가 미리 합성한 음성이고(lib/listenAudio), 아직 합성되지 않은 글은 '소리 준비 전'으로 건너뛴다(세지 않음).
 * 단계마다 과제가 다르다: 0 Ling 점검, 1 같다·다르다, 2 낱말 고르기, 3 조용한 문장 받아쓰기, 4 소음 속 문장(+검사), 5 대화 듣기.
 */

const IC = { close: '/ui/lp-91-12-close.svg' }
const NOTICE = '청력을 진단하거나 치료하지 않아요. 보청기·인공와우 조절은 청능사나 병원에서 해요. 귀가 아프거나 울리면 바로 멈추세요.'

function useListenSettings() {
  const [s, setS] = useState(() => readSettings())
  const save = (v) => { const next = { ...v, gainDb: clampGainDb(v.gainDb), at: new Date().toISOString() }; writeSettings(next); setS(next) }
  return [s, save]
}

/** 글 하나의 소리를 미리 받는다. state: 'loading' | 'ready' | 'missing' */
function useClip(text, voice) {
  const [st, setSt] = useState({ clip: null, state: 'loading' })
  useEffect(() => {
    let on = true
    if (!text) { setSt({ clip: null, state: 'missing' }); return undefined }
    setSt({ clip: null, state: 'loading' })
    loadClip(text, voice).then((c) => { if (on) setSt({ clip: c, state: c ? 'ready' : 'missing' }) })
    return () => { on = false }
  }, [text, voice])
  return st
}

function useNoise(enabled, name = 'babble') {
  const [st, setSt] = useState({ noise: null, state: enabled ? 'loading' : 'off' })
  useEffect(() => {
    let on = true
    if (!enabled) { setSt({ noise: null, state: 'off' }); return undefined }
    setSt({ noise: null, state: 'loading' })
    loadNoise(name).then((n) => { if (on) setSt({ noise: n, state: n ? 'ready' : 'missing' }) })
    return () => { on = false }
  }, [enabled, name])
  return st
}

// ── 공통 조각 ─────────────────────────────────────────────────

function Card({ children, className = '' }) {
  return <div className={`rounded-18 border-2 border-line bg-white p-5 lg:rounded-22 lg:p-6 ${className}`}>{children}</div>
}

function PlayButton({ onClick, busy, disabled, label = '듣기', plays }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled || busy}
      className="btn-primary flex w-full items-center justify-center gap-2 py-4 text-[17px] disabled:opacity-50">
      <span aria-hidden className="text-[20px]">{busy ? '🔊' : '▶'}</span>
      {busy ? '듣는 중…' : label}
      {plays > 0 && !busy && <span className="text-[13px] font-normal opacity-80">· {plays}번 들음</span>}
    </button>
  )
}

function Missing({ onSkip }) {
  return (
    <Card className="text-center">
      <p className="text-[16px] font-bold text-ink">이 소리는 아직 준비되지 않았어요</p>
      <p className="mt-1 text-[13px] text-ink-muted">서버에서 소리를 만드는 중이에요. 이 문항은 세지 않고 넘어가요.</p>
      <button type="button" onClick={onSkip} className="btn-secondary mt-4 px-6 py-2.5 text-[14px]">다음 문항</button>
    </Card>
  )
}

function ResultBar({ correct, children, onNext, nextLabel = '다음' }) {
  return (
    <div className={`flex flex-col gap-3 rounded-16 border-2 p-4 ${correct ? 'border-good/40 bg-good-tint' : 'border-bad/30 bg-bad-tint'}`}
      role="status" aria-live="polite">
      <p className={`text-[16px] font-bold ${correct ? 'text-good-text' : 'text-bad-text'}`}>{correct ? '맞았어요' : '아쉬워요'}</p>
      {children}
      {onNext && <button type="button" onClick={onNext} className="btn-primary py-3 text-[15px]">{nextLabel}</button>}
    </div>
  )
}

function Done({ title, lines = [], onMore, onExit, moreLabel = '계속하기' }) {
  return (
    <Card className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-[20px] font-bold text-ink">{title}</p>
      {lines.filter(Boolean).map((l, i) => <p key={i} className="text-[14px] text-ink-muted">{l}</p>)}
      <div className="mt-2 flex w-full max-w-[360px] flex-col gap-2">
        {onMore && <button type="button" onClick={onMore} className="btn-primary py-3 text-[15px]">{moreLabel}</button>}
        <button type="button" onClick={onExit} className="btn-secondary py-3 text-[15px]">학습 경로로</button>
      </div>
    </Card>
  )
}

// ── 소리 크기 맞추기 ───────────────────────────────────────────

const CALIBRATION_TEXT = '안녕하세요. 이 정도 크기가 편안한가요?'

// 인공와우 모의(청인 예비 파일럿): 연구진이 주소에 ?sim=ci를 붙여 열었거나 이미 켠 기기에서만 고를 수 있다. 학습자 화면에는 보이지 않는다
function simAllowed(initial) {
  try { return initial?.sim === 'ci' || new URLSearchParams(window.location.search).get('sim') === 'ci' } catch { return false }
}

function ListenSetup({ initial, onSave, onCancel }) {
  const [gainDb, setGainDb] = useState(initial?.gainDb ?? -15)
  const [sim, setSim] = useState(initial?.sim === 'ci' || (simAllowed(initial) && !initial))
  const showSim = simAllowed(initial)
  const [device, setDevice] = useState(initial?.device || 'unknown')
  const [route, setRoute] = useState(initial?.route || 'speaker')
  const [busy, setBusy] = useState(false)
  const { clip, state } = useClip(CALIBRATION_TEXT, '')
  const test = async () => {
    setBusy(true)
    const c = clip || await lingClip('a')
    await playClip(c, { gainDb, sim: sim ? 'ci' : null })
    setBusy(false)
  }
  useEffect(() => () => stopAll(), [])
  return (
    <Card className="flex flex-col gap-5">
      <div>
        <p className="text-[19px] font-bold text-ink">소리 크기 맞추기</p>
        <p className="mt-1 text-[14px] text-ink-muted">평소처럼 기기를 켜고, 예시 소리를 들으며 편안한 크기를 골라요. 연습 중에는 이 크기를 넘지 않아요.</p>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-[14px] font-bold text-ink">
          <span>크기</span><span className="text-track">{gainDb} dB</span>
        </div>
        <input type="range" min={GAIN_MIN_DB} max={GAIN_MAX_DB} step={1} value={gainDb} onChange={(e) => setGainDb(Number(e.target.value))}
          aria-label="소리 크기" className="w-full accent-[var(--track)]" />
        <button type="button" onClick={test} disabled={busy} className="btn-secondary py-3 text-[15px]">
          {busy ? '듣는 중…' : state === 'ready' ? '예시 소리 듣기' : '예시 소리 듣기(합성 모음)'}
        </button>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[14px] font-bold text-ink">쓰는 기기</legend>
        <div className="grid grid-cols-2 gap-2">
          {DEVICES.map((d) => (
            <button key={d.key} type="button" aria-pressed={device === d.key} onClick={() => setDevice(d.key)}
              className={`rounded-13 border-2 px-3 py-2.5 text-[14px] font-bold ${device === d.key ? 'border-track bg-track-tint text-track-dark' : 'border-line bg-white text-ink'}`}>
              {d.label}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[14px] font-bold text-ink">듣는 방법</legend>
        <div className="flex flex-col gap-2">
          {ROUTES.map((r) => (
            <button key={r.key} type="button" aria-pressed={route === r.key} onClick={() => setRoute(r.key)}
              className={`rounded-13 border-2 px-3 py-2.5 text-left text-[14px] font-bold ${route === r.key ? 'border-track bg-track-tint text-track-dark' : 'border-line bg-white text-ink'}`}>
              {r.label}
            </button>
          ))}
        </div>
      </fieldset>
      {showSim && (
        <label className="flex items-start gap-3 rounded-13 border-2 border-warn/40 bg-warn-tint px-4 py-3">
          <input type="checkbox" checked={sim} onChange={(e) => setSim(e.target.checked)} className="mt-1" />
          <span className="text-[13px] leading-[1.6] text-ink">
            <b>인공와우 모의(연구용)</b> · 청인 참여자가 인공와우를 흉내 낸 소리(8채널 보코더)로 들어요. 예비 파일럿에서만 켜요.
          </span>
        </label>
      )}
      <p className="text-[12px] leading-[1.6] text-ink-faint">{NOTICE} 기기 정보는 이 기기에만 저장돼요.</p>
      <div className="flex gap-2">
        {onCancel && <button type="button" onClick={onCancel} className="btn-secondary flex-1 py-3 text-[15px]">취소</button>}
        <button type="button" onClick={() => { stopAll(); onSave({ gainDb, device, route, ...(sim && showSim ? { sim: 'ci' } : {}) }) }} className="btn-primary flex-1 py-3 text-[15px]">이 크기로 시작</button>
      </div>
    </Card>
  )
}

// ── 0단계: Ling 6소리 ──────────────────────────────────────────

const LING_LABEL = { m: '음', u: '우', a: '아', i: '이', sh: '쉬', s: '스' }

function LingCheck({ data, settings, onProgress, onExit }) {
  const seq = data.sequence || []
  const [k, setK] = useState(0)
  const [phase, setPhase] = useState('ready')   // ready | playing | answer
  const res = useRef({ results: {}, fa: 0 })
  const [summary, setSummary] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { onProgress(Math.min(k, seq.length), seq.length) }, [k, seq.length, onProgress])
  const cur = seq[k]
  const play = async () => {
    setPhase('playing')
    if (cur === 'silent') await silence(1400)
    else await playClip(await lingClip(cur), { gainDb: settings.gainDb })
    setPhase('answer')
  }
  const answer = async (heard) => {
    if (cur === 'silent') { if (heard) res.current.fa += 1 } else res.current.results[cur] = heard
    if (k + 1 < seq.length) { setK(k + 1); setPhase('ready'); return }
    setK(seq.length)
    try {
      const r = await listenAPI.ling({ results: res.current.results, false_alarms: res.current.fa, route: settings.route })
      setSummary(r.summary)
    } catch { setErr('결과를 저장하지 못했어요. 다시 해 주세요.') }
  }
  if (summary) {
    return (
      <Card className="flex flex-col gap-4">
        <p className="text-[19px] font-bold text-ink">오늘의 소리 확인</p>
        <div className="grid grid-cols-3 gap-2">
          {(data.sounds || []).map((s) => {
            const ok = summary.heard.includes(s.key)
            return (
              <div key={s.key} className={`flex flex-col items-center gap-0.5 rounded-14 border-2 py-3 ${ok ? 'border-good/40 bg-good-tint' : 'border-bad/30 bg-bad-tint'}`}>
                <span className="text-[20px] font-bold text-ink">{s.label}</span>
                <span className="text-[11px] text-ink-muted">{s.band}</span>
                <span className={`text-[12px] font-bold ${ok ? 'text-good-text' : 'text-bad-text'}`}>{ok ? '들림' : '안 들림'}</span>
              </div>
            )
          })}
        </div>
        {summary.dropped.length > 0 && (
          <p className="rounded-13 bg-warn-tint px-4 py-3 text-[14px] font-bold text-warn-text">
            지난번에 들리던 {summary.dropped.map((x) => LING_LABEL[x]).join('·')} 소리가 오늘은 안 들렸어요. 배터리와 기기 상태를 확인해 보세요. 계속 안 들리면 청능사나 병원에 알려요.
          </p>
        )}
        {!summary.reliable && (
          <p className="text-[13px] text-ink-muted">소리가 없을 때도 '들렸어요'를 {summary.false_alarms}번 눌렀어요. 다음에는 확실히 들릴 때만 눌러 보세요.</p>
        )}
        {summary.missed.length > 0 && summary.dropped.length === 0 && (
          <p className="text-[13px] text-ink-muted">안 들린 소리가 있어도 괜찮아요. 남은 청력에 맞춰 다음 단계에서 연습해요.</p>
        )}
        <div className="flex flex-col gap-2">
          <button type="button" onClick={onExit} className="btn-primary py-3 text-[15px]">학습 경로로</button>
        </div>
      </Card>
    )
  }
  return (
    <Card className="flex flex-col items-center gap-5 py-8 text-center">
      <p className="text-[14px] font-bold text-track">소리 {Math.min(k + 1, seq.length)} / {seq.length}</p>
      <p className="text-[18px] font-bold text-ink">{phase === 'answer' ? '소리가 들렸나요?' : '버튼을 누르면 소리가 나요. 아무 소리가 없을 때도 있어요.'}</p>
      {err && <p role="alert" className="text-[14px] font-bold text-bad-text">{err}</p>}
      {phase !== 'answer' ? (
        <div className="w-full max-w-[360px]"><PlayButton onClick={play} busy={phase === 'playing'} label="소리 내기" /></div>
      ) : (
        <div className="grid w-full max-w-[360px] grid-cols-2 gap-2">
          <button type="button" onClick={() => answer(true)} className="btn-primary py-4 text-[16px]">들렸어요</button>
          <button type="button" onClick={() => answer(false)} className="btn-secondary py-4 text-[16px]">안 들렸어요</button>
        </div>
      )}
    </Card>
  )
}

// ── 1단계: 같다·다르다 ─────────────────────────────────────────

function AxDrill({ data, settings, voices, onProgress, onExit, reload }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [plays, setPlays] = useState(0)
  const [score, setScore] = useState({ n: 0, c: 0, level: data.level, up: null })
  const t0 = useRef(Date.now())
  const it = items[k]
  const v1 = voiceFor(voices.train, k, it?.voice_pair?.[0] || 0, data.voice_mode, data.voice_block)
  const v2 = voiceFor(voices.train, k, it?.voice_pair?.[1] || 0, data.voice_mode, data.voice_block)
  const a = useClip(it?.first, v1)
  const b = useClip(it?.second, v2)
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setPlays(0); t0.current = Date.now() }, [k])
  if (!it) {
    return <Done title="이번 묶음을 마쳤어요" lines={[`${score.n}문항 중 ${score.c}문항 맞음`, `지금 수준 ${score.level} / ${data.levels}`]}
      onMore={reload} onExit={onExit} />
  }
  if (a.state === 'missing' || b.state === 'missing') return <Missing onSkip={() => setK(k + 1)} />
  const ready = a.state === 'ready' && b.state === 'ready'
  const play = async () => { setBusy(true); await playPair(a.clip, b.clip, { gainDb: settings.gainDb }); setBusy(false); setPlays((p) => p + 1) }
  const answer = async (same) => {
    try {
      const r = await listenAPI.answer({ stage: 1, item_key: it.key, same, plays, rt_ms: Date.now() - t0.current, voice: v1, route: settings.route,
        pick: it.pick })
      setRes(r)
      setScore((s) => ({ n: s.n + 1, c: s.c + (r.correct ? 1 : 0), level: r.level ?? s.level, up: r.level_changed ? r.level : null }))
    } catch { setRes({ error: true }) }
  }
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="flex items-center justify-between text-[13px] font-bold">
          <span className="text-track">수준 {score.level} / {data.levels}</span>
          <span className="text-ink-muted">{it.kind_label}</span>
        </div>
        <p className="text-[18px] font-bold text-ink">두 소리가 같나요, 다른가요?</p>
        {it.voice_pair?.[1] !== it.voice_pair?.[0] && voices.train.length > 1 && (
          <p className="text-[13px] text-ink-muted">두 소리는 다른 목소리예요. 목소리가 아니라 말소리가 같은지 들어 보세요.</p>
        )}
        <PlayButton onClick={play} busy={busy} disabled={!ready || !!res} label={ready ? '두 소리 듣기' : '소리 받는 중…'} plays={plays} />
        {!res && (
          <div className="grid grid-cols-2 gap-2">
            <button type="button" disabled={!plays} onClick={() => answer(true)} className="btn-secondary py-4 text-[16px] disabled:opacity-40">같아요</button>
            <button type="button" disabled={!plays} onClick={() => answer(false)} className="btn-secondary py-4 text-[16px] disabled:opacity-40">달라요</button>
          </div>
        )}
      </Card>
      {res && !res.error && (
        <ResultBar correct={res.correct} onNext={() => setK(k + 1)}>
          <p className="text-[14px] text-ink">{res.same ? '같은 소리였어요' : `다른 소리였어요: ${it.first} / ${it.second}`} · {res.kind_label}</p>
          {score.up && <p className="text-[14px] font-bold text-track-dark">수준 {score.up}로 바뀌었어요</p>}
          <button type="button" onClick={play} disabled={busy} className="btn-secondary py-2.5 text-[14px]">다시 들어 보기</button>
        </ResultBar>
      )}
      {res?.error && <p role="alert" className="text-[14px] font-bold text-bad-text">답을 보내지 못했어요. 다시 눌러 주세요.</p>}
    </div>
  )
}

// ── 2단계: 낱말 고르기 ─────────────────────────────────────────

function WordId({ data, settings, voices, onProgress, onExit, reload }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [res, setRes] = useState(null)
  const [picked, setPicked] = useState(null)
  const [busy, setBusy] = useState(false)
  const [plays, setPlays] = useState(0)
  const [score, setScore] = useState({ n: 0, c: 0, level: data.level })
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const target = useClip(it?.target, voice)
  const heard = useClip(res && !res.correct ? picked : null, voice)
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setPicked(null); setPlays(0); t0.current = Date.now() }, [k])
  if (!it) {
    return <Done title="이번 묶음을 마쳤어요" lines={[`${score.n}문항 중 ${score.c}문항 맞음`, `지금 수준 ${score.level} / ${data.levels}`]}
      onMore={reload} onExit={onExit} />
  }
  if (target.state === 'missing') return <Missing onSkip={() => setK(k + 1)} />
  const play = async (clip = target.clip) => { setBusy(true); await playClip(clip, { gainDb: settings.gainDb }); setBusy(false); if (clip === target.clip) setPlays((p) => p + 1) }
  const answer = async (w) => {
    setPicked(w)
    try {
      const r = await listenAPI.answer({ stage: 2, item_key: it.key, answer: w, level: it.level, plays, rt_ms: Date.now() - t0.current,
        voice, route: settings.route, pick: it.pick })
      setRes(r)
      setScore((s) => ({ n: s.n + 1, c: s.c + (r.correct ? 1 : 0), level: r.level ?? s.level }))
    } catch { setRes({ error: true }) }
  }
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <p className="text-[13px] font-bold text-track">수준 {score.level} / {data.levels} · 보기 {it.options.length}개{it.review ? ' · 다시 보는 낱말' : ''}</p>
        <p className="text-[18px] font-bold text-ink">들은 낱말을 골라요</p>
        <PlayButton onClick={() => play()} busy={busy} disabled={target.state !== 'ready'} label={target.state === 'ready' ? '낱말 듣기' : '소리 받는 중…'} plays={plays} />
        <div className={`grid gap-2 ${it.options.length > 2 ? 'grid-cols-2' : 'grid-cols-2'}`}>
          {it.options.map((o) => {
            const show = res && !res.error
            const isT = show && o === res.target
            const isP = show && o === picked && !res.correct
            return (
              <button key={o} type="button" disabled={!plays || show} onClick={() => answer(o)}
                className={`rounded-14 border-2 py-4 text-[20px] font-bold transition disabled:cursor-default ${
                  isT ? 'border-good bg-good-tint text-good-text' : isP ? 'border-bad bg-bad-tint text-bad-text' : 'border-line bg-white text-ink'} ${!plays && !show ? 'opacity-40' : ''}`}>
                {o}
              </button>
            )
          })}
        </div>
      </Card>
      {res && !res.error && (
        <ResultBar correct={res.correct} onNext={() => setK(k + 1)}>
          {!res.correct && <p className="text-[14px] text-ink">{contrastText(res.contrast)}</p>}
          {!res.correct && (
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => play(target.clip)} disabled={busy} className="btn-secondary py-2.5 text-[14px]">정답 {res.target} 듣기</button>
              <button type="button" onClick={() => play(heard.clip)} disabled={busy || heard.state !== 'ready'} className="btn-secondary py-2.5 text-[14px]">고른 말 {picked} 듣기</button>
            </div>
          )}
        </ResultBar>
      )}
      {res?.error && <p role="alert" className="text-[14px] font-bold text-bad-text">답을 보내지 못했어요. 다시 눌러 주세요.</p>}
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

function SentenceTask({ data, settings, voices, onProgress, onExit, reload, noisy }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [answer, setAnswer] = useState('')
  const [first, setFirst] = useState(null)       // 첫 답 채점(세는 답)
  const [retry, setRetry] = useState(null)       // 자음 단서를 본 뒤 다시 쓴 답(세지 않음)
  const [busy, setBusy] = useState(false)
  const [plays, setPlays] = useState(0)
  // 이번 문항의 조건·SNR은 문항이 바뀔 때만 정한다(답 뒤에 계단이 움직여도 다시 듣기는 같은 조건으로)
  const [stair, setStair] = useState(data.stair || null)
  const [nextCond, setNextCond] = useState(data.next_condition || 'ao')
  const [cond, setCond] = useState(data.next_condition || 'ao')
  const [snrNow, setSnrNow] = useState(data.stair?.[data.next_condition || 'ao']?.next_db ?? 10)
  const [stats, setStats] = useState({ n: 0, c: 0 })
  const [playFrames, setPlayFrames] = useState(null)
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const { clip, state } = useClip(it?.text, voice)
  const nz = useNoise(noisy)
  const av = noisy && cond === 'av'
  const frames = useAvFrames(it?.text, clip, av)
  const snr = noisy ? snrNow : null
  const goNext = () => {
    setCond(nextCond)
    setSnrNow(stair?.[nextCond]?.next_db ?? 10)
    setK(k + 1)
  }
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setAnswer(''); setFirst(null); setRetry(null); setPlays(0); setPlayFrames(null); t0.current = Date.now() }, [k])
  // 정답 글을 보인 뒤 같은 소리(소음 속이면 같은 소음·SNR)를 한 번 다시 들려준다. 글 먼저, 그다음 같은 왜곡된 소리가 가장 근거 있는
  // 순서다(Davis 2005, Loebach 2010). 첫 답이 다 맞았으면 자동으로 틀지 않는다. 훅은 아래 조기 반환보다 위에 둔다
  const playRef = useRef(null)
  const autoRef = useRef(null)
  const avOffsetRef = useRef(null)
  const firstAllRight = !!(first?.word_feedback && first.word_feedback.correct_words === first.word_feedback.total_words)
  const done = !!(first && !first.error && (firstAllRight || retry))
  useEffect(() => {
    if (!done || firstAllRight || autoRef.current === k) return undefined
    autoRef.current = k
    const t = setTimeout(() => { playRef.current?.() }, 700)
    return () => clearTimeout(t)
  }, [done, firstAllRight, k])
  if (!it) {
    const lines = [`${stats.n}문장 중 ${stats.c}문장 통과`]
    if (noisy && stair?.ao?.srt_db != null) lines.push(`소리만 역치 추정 ${stair.ao.srt_db > 0 ? '+' : ''}${stair.ao.srt_db} dB`)
    return <Done title="이번 묶음을 마쳤어요" lines={lines} onMore={reload} onExit={onExit} />
  }
  if (state === 'missing') return <Missing onSkip={goNext} />
  if (noisy && nz.state === 'missing') {
    return <Card className="text-center text-[15px] font-bold text-ink-muted">잡음 소리를 아직 받지 못해 이 단계를 진행할 수 없어요. 잠시 뒤 다시 열어 주세요.</Card>
  }
  const ready = state === 'ready' && (!noisy || nz.state === 'ready') && (!av || frames)
  const play = async (opts = {}) => {
    setBusy(true)
    if (av && frames?.length) {
      // 블루투스 등 출력 지연만큼 입모양을 늦춘다(avOffsetMs, 덜 보정). 새 배열이라 아바타가 처음부터 한 번 재생한다
      await ensureAudio()
      const offset = avOffsetMs()
      avOffsetRef.current = offset
      const fresh = frames.map((f) => ({ ...f }))
      setTimeout(() => setPlayFrames(fresh), offset)
      await playClip(clip, { gainDb: settings.gainDb, snrDb: snr, noise: nz.noise, leadMs: 300, ...opts })
    } else {
      await playClip(clip, { gainDb: settings.gainDb, snrDb: noisy ? snr : null, noise: noisy ? nz.noise : null, ...opts })
    }
    setBusy(false)
    setPlays((p) => p + 1)
  }
  const submit = async () => {
    const body = { stage: noisy ? 4 : 3, item_key: it.key, answer, plays, rt_ms: Date.now() - t0.current, voice, route: settings.route,
      output_latency_ms: outputLatencyMs() }
    if (noisy) Object.assign(body, { snr_db: snr, condition: cond })
    if (av && avOffsetRef.current != null) body.av_offset_ms = avOffsetRef.current
    try {
      if (!first) {
        const r = await listenAPI.answer(body)
        setFirst(r)
        setStats((s) => ({ n: s.n + 1, c: s.c + (r.passed ? 1 : 0) }))
        if (r.stair) setStair(r.stair)
        if (r.next_condition) setNextCond(r.next_condition)
      } else {
        setRetry(await listenAPI.answer({ ...body, practice: true }))
      }
    } catch { setFirst((f) => f || { error: true }) }
  }
  const allRight = first && first.word_feedback && first.word_feedback.correct_words === first.word_feedback.total_words
  const finished = first && (allRight || retry)
  playRef.current = play
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        {noisy && (
          <div className="flex items-center justify-between text-[13px] font-bold">
            <span className="text-track">{cond === 'av' ? '소리 + 입모양' : '소리만'}</span>
            <span className="text-ink-muted">{snrLabel(snr)}</span>
          </div>
        )}
        <p className="text-[18px] font-bold text-ink">문장을 듣고 들은 대로 써요</p>
        {it.review && <p className="-mt-2 text-[12px] font-bold text-track">며칠 전에 놓친 문장을 다시 들어요</p>}
        {av && (
          <div className="overflow-hidden rounded-16 border-2 border-line">
            <MouthAvatar frames={playFrames} once height={null} className="h-[160px] lg:h-[220px]" showTalker={false} />
          </div>
        )}
        {av && settings.route === 'stream' && (
          <p className="text-[12px] leading-[1.6] text-ink-faint">블루투스로 바로 들으면 소리가 입모양보다 늦게 들릴 수 있어요. 어긋나 보이면 스피커나 유선 이어폰으로 들어 보세요.</p>
        )}
        <PlayButton onClick={() => play()} busy={busy} disabled={!ready || !!finished} label={ready ? '문장 듣기' : '소리 받는 중…'} plays={plays} />
        {!finished && (
          <form onSubmit={(e) => { e.preventDefault(); if (answer.trim() && plays) submit() }} className="flex flex-col gap-2">
            <input value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!plays} placeholder={plays ? '들은 말을 써요' : '먼저 문장을 들어요'}
              aria-label="들은 문장" className="w-full rounded-14 border-2 border-line bg-white px-4 py-3 text-[17px] text-ink outline-none focus:border-track disabled:bg-surface-muted" />
            <button type="submit" disabled={!answer.trim() || !plays} className="btn-primary py-3 text-[15px] disabled:opacity-40">
              {first ? '다시 쓴 답 확인' : '확인'}
            </button>
            {first && !retry && <p className="text-[12px] text-ink-faint">다시 쓴 답은 점수에 넣지 않아요. 단서를 보고 한 번 더 들어 보는 연습이에요.</p>}
          </form>
        )}
      </Card>
      {first && !first.error && !allRight && !retry && (
        <ConsonantFeedback feedback={first.word_feedback} hint="맞힌 낱말은 그대로, 틀린 낱말은 글자마다 첫 자음만 보여요. 문장을 다시 듣고 한 번 더 써 보세요." />
      )}
      {finished && (
        <ResultBar correct={!!first.passed} onNext={goNext}>
          <p className="text-[18px] font-bold text-ink">{(retry || first).target}</p>
          <p className="text-[13px] text-ink-muted">첫 답 {Math.round((first.score || 0) * 100)}% 낱말 맞음{retry ? ` · 다시 쓴 답 ${Math.round((retry.score || 0) * 100)}%` : ''}</p>
          <button type="button" onClick={() => play()} disabled={busy} className="btn-secondary py-2.5 text-[14px]">글을 보며 다시 듣기</button>
        </ResultBar>
      )}
      {first?.error && <p role="alert" className="text-[14px] font-bold text-bad-text">답을 보내지 못했어요. 다시 눌러 주세요.</p>}
    </div>
  )
}

// ── 4단계 검사: 소음 속 문장 인식 역치(20문장) ─────────────────────

function NoiseTest({ settings, voices, onDone, onCancel }) {
  const [run, setRun] = useState(null)
  const [k, setK] = useState(0)
  const [snr, setSnr] = useState(10)
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [plays, setPlays] = useState(0)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const it = run?.items?.[k]
  const { clip, state } = useClip(it?.text, voices.test)
  const nz = useNoise(true)
  useEffect(() => {
    listenAPI.testStart({ route: settings.route }).then((r) => { setRun(r); setSnr(r.start_db) }).catch(() => setErr('검사를 시작하지 못했어요.'))
  }, [settings.route])
  useEffect(() => { setAnswer(''); setPlays(0) }, [k])
  if (err) return <Card className="text-center text-[15px] font-bold text-bad-text">{err}</Card>
  if (!run || (state === 'loading' && !result) || nz.state === 'loading') return <LoadingScreen variant="section" />
  if (result) {
    return (
      <Done title="검사를 마쳤어요" lines={[`소음 속 문장 인식 역치 ${result.srt_db > 0 ? '+' : ''}${result.srt_db} dB`,
        result.srt_db >= 24 ? '소음을 가장 작게 해도 낱말 절반을 넘기 어려웠어요. 3단계 문장 알아듣기를 더 연습하고 다시 검사해 보세요.'
          : '말이 소음보다 이만큼 클 때 낱말을 열에 넷쯤 알아들었다는 뜻이에요. 낮을수록 시끄러운 곳에서 잘 알아들어요.']}
        onMore={onDone} moreLabel="훈련 시작하기" onExit={onCancel} />
    )
  }
  if (state === 'missing' || nz.state === 'missing') {
    return <Card className="text-center text-[15px] font-bold text-ink-muted">검사 소리가 아직 준비되지 않았어요. 잠시 뒤 다시 해 주세요.</Card>
  }
  const play = async () => { setBusy(true); await playClip(clip, { gainDb: settings.gainDb, snrDb: snr, noise: nz.noise }); setBusy(false); setPlays((p) => p + 1) }
  const submit = async () => {
    try {
      const r = await listenAPI.testAnswer({ session: run.session, item_key: it.key, answer, voice: voices.test, plays, route: settings.route })
      if (r.done) { setResult(r); return }
      setSnr(r.next_db)
      setK(k + 1)
    } catch { setErr('답을 보내지 못했어요. 검사를 처음부터 다시 해 주세요.') }
  }
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between text-[13px] font-bold">
        <span className="text-track">검사 {k + 1} / {run.items.length}</span>
        <span className="text-ink-muted">정답은 알려 주지 않아요</span>
      </div>
      <p className="text-[18px] font-bold text-ink">문장을 듣고 들은 대로 써요</p>
      <PlayButton onClick={play} busy={busy} disabled={state !== 'ready' || plays >= 1} label={plays >= 1 ? '한 번만 들어요' : '문장 듣기'} />
      <form onSubmit={(e) => { e.preventDefault(); if (plays) submit() }} className="flex flex-col gap-2">
        <input value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!plays} aria-label="들은 문장"
          placeholder={plays ? '들은 말을 써요(모르면 비워 두고 다음)' : '먼저 문장을 들어요'}
          className="w-full rounded-14 border-2 border-line bg-white px-4 py-3 text-[17px] text-ink outline-none focus:border-track disabled:bg-surface-muted" />
        <button type="submit" disabled={!plays} className="btn-primary py-3 text-[15px] disabled:opacity-40">다음</button>
      </form>
    </Card>
  )
}

function NoiseStage({ data, settings, voices, onProgress, onExit, reload }) {
  const [mode, setMode] = useState(data.needs_pretest ? 'intro' : 'train')
  useEffect(() => { if (mode !== 'train') onProgress(0, 0) }, [mode, onProgress])
  if (mode === 'intro') {
    return (
      <Card className="flex flex-col gap-4">
        <p className="text-[19px] font-bold text-ink">먼저 소음 속 듣기 검사를 해요</p>
        <p className="text-[14px] text-ink-muted">20문장을 소음 속에서 한 번씩 듣고 받아써요(약 5분). 훈련 전의 기준을 측정해 두면 나중에 다시 검사해서 얼마나 늘었는지 비교할 수 있어요.
          검사 문장과 목소리는 훈련에 나오지 않아요.</p>
        <button type="button" onClick={() => setMode('test')} className="btn-primary py-3 text-[15px]">검사 시작</button>
        <button type="button" onClick={() => setMode('train')} className="btn-secondary py-3 text-[15px]">나중에 하고 훈련하기</button>
      </Card>
    )
  }
  if (mode === 'test') return <NoiseTest settings={settings} voices={voices} onDone={() => { setMode('train'); reload() }} onCancel={onExit} />
  return (
    <div className="flex flex-col gap-3">
      <SentenceTask data={data} settings={settings} voices={voices} onProgress={onProgress} onExit={onExit} reload={reload} noisy />
      {!data.needs_pretest && (
        <button type="button" onClick={() => setMode('test')} className="self-center text-[13px] font-bold text-ink-muted underline">
          다시 검사하기{data.tests?.length ? ` · 지난 역치 ${data.tests[data.tests.length - 1].srt_db} dB` : ''}
        </button>
      )}
    </div>
  )
}

// ── 5단계: 대화 듣기 ─────────────────────────────────────────

const NOISE_LABEL = { babble: '여러 사람 소리', talker1_f: '여자 한 명 말소리', talker1_m: '남자 한 명 말소리', talker2: '두 사람 말소리', ssn: '웅웅 소리' }
const COND_LABEL = { quiet: '조용함', noise: '소음', phone: '전화', room: '울리는 방' }

function ConvoTask({ data, settings, voices, onProgress, onExit, reload }) {
  const items = data.items || []
  const [k, setK] = useState(0)
  const [cond, setCond] = useState('quiet')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [repairs, setRepairs] = useState([])
  const [plays, setPlays] = useState(0)
  const [stats, setStats] = useState({ n: 0, c: 0 })
  const t0 = useRef(Date.now())
  const it = items[k]
  const voice = voiceFor(voices.train, k, 0, data.voice_mode, data.voice_block)
  const line = useClip(it?.line, voice)
  const para = useClip(it?.paraphrase, voice)
  // 소음 조건은 문항마다 잡음 종류를 돌린다(경쟁 화자 1명이 인공와우 사용자에게 가장 어렵고 화자 수 효과는 단조롭지 않아 한 축으로
  // 쓰지 않는다, Chen 2020). talker2는 일반화 확인용으로 훈련에 쓰지 않는다
  const noiseName = (data.noise_types || ['babble'])[k % (data.noise_types?.length || 1)]
  const nz = useNoise(cond === 'noise', noiseName)
  useEffect(() => { onProgress(k, items.length) }, [k, items.length, onProgress])
  useEffect(() => { setRes(null); setRepairs([]); setPlays(0); t0.current = Date.now() }, [k])
  if (!it) return <Done title="이번 대화를 마쳤어요" lines={[`${stats.n}문항 중 ${stats.c}문항 맞음`]} onMore={reload} onExit={onExit} />
  if (line.state === 'missing') return <Missing onSkip={() => setK(k + 1)} />
  // 울리는 방은 문항마다 잔향 시간을 돌린다(여러 방에서 훈련할 때 새 방으로 옮겨 갔다)
  const rt = (data.room_rt60 || [0.5])[k % (data.room_rt60?.length || 1)]
  const opts = { gainDb: settings.gainDb, phone: cond === 'phone', snrDb: cond === 'noise' ? data.noise_snr_db : null, noise: cond === 'noise' ? nz.noise : null,
    room: cond === 'room' ? rt : null }
  const play = async (clip, extra = {}, repair = null) => {
    setBusy(true)
    if (repair) setRepairs((r) => [...r, repair])
    await playClip(clip, { ...opts, ...extra })
    setBusy(false)
    setPlays((p) => p + 1)
  }
  const ready = line.state === 'ready' && (cond !== 'noise' || nz.state === 'ready')
  const choose = async (i) => {
    try {
      const r = await listenAPI.answer({ stage: 5, item_key: it.key, choice: i, condition: cond, snr_db: cond === 'noise' ? data.noise_snr_db : null,
        repairs, plays, rt_ms: Date.now() - t0.current, voice, route: settings.route })
      setRes({ ...r, choice: i })
      setStats((s) => ({ n: s.n + 1, c: s.c + (r.correct ? 1 : 0) }))
    } catch { setRes({ error: true }) }
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 rounded-13 bg-surface-sunken p-1" role="group" aria-label="듣기 조건">
        {(data.conditions || ['quiet']).map((c) => (
          <button key={c} type="button" aria-pressed={cond === c} disabled={plays > 0} onClick={() => setCond(c)}
            className={`flex-1 rounded-10 py-2 text-[14px] font-bold disabled:cursor-not-allowed ${cond === c ? 'bg-white text-track shadow-sm' : 'text-ink-faint'}`}>
            {COND_LABEL[c]}
          </button>
        ))}
      </div>
      <Card className="flex flex-col gap-4">
        <p className="text-[13px] font-bold text-track">{it.place}{cond === 'noise' ? ` · ${NOISE_LABEL[noiseName] || '소음'}` : ''}</p>
        <PlayButton onClick={() => play(line.clip)} busy={busy} disabled={!ready} label={plays ? '처음 말 다시 듣기' : '말 듣기'} plays={plays} />
        {plays > 0 && !res && (
          <div className="grid grid-cols-3 gap-2">
            <button type="button" onClick={() => play(line.clip, {}, 'again')} disabled={busy} className="btn-secondary py-2.5 text-[14px]">다시</button>
            <button type="button" onClick={() => play(line.clip, { rate: 0.8 }, 'slow')} disabled={busy} className="btn-secondary py-2.5 text-[14px]">천천히</button>
            <button type="button" onClick={() => play(para.clip, {}, 'rephrase')} disabled={busy || para.state !== 'ready'} className="btn-secondary py-2.5 text-[14px]">다른 말로</button>
          </div>
        )}
        <p className="text-[18px] font-bold text-ink">{it.question}</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {it.options.map((o, i) => {
            const show = res && !res.error
            const isT = show && i === res.answer
            const isP = show && i === res.choice && !res.correct
            return (
              <button key={o} type="button" disabled={!plays || show} onClick={() => choose(i)}
                className={`rounded-14 border-2 px-3 py-3.5 text-[16px] font-bold ${
                  isT ? 'border-good bg-good-tint text-good-text' : isP ? 'border-bad bg-bad-tint text-bad-text' : 'border-line bg-white text-ink'} ${!plays && !show ? 'opacity-40' : ''}`}>
                {o}
              </button>
            )
          })}
        </div>
      </Card>
      {res && !res.error && (
        <ResultBar correct={res.correct} onNext={() => setK(k + 1)}>
          <p className="text-[16px] font-bold text-ink">“{res.line}”</p>
          <button type="button" onClick={() => play(line.clip)} disabled={busy} className="btn-secondary py-2.5 text-[14px]">글을 보며 다시 듣기</button>
        </ResultBar>
      )}
      {res?.error && <p role="alert" className="text-[14px] font-bold text-bad-text">답을 보내지 못했어요. 다시 눌러 주세요.</p>}
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
  const [prog, setProg] = useState({ cur: 0, total: 0 })
  const voices = useMemo(() => voiceRoles(voiceList || []), [voiceList])

  useEffect(() => { loadVoices().then(setVoiceList) }, [])
  useEffect(() => { setSimMode(settings?.sim) }, [settings?.sim])
  useEffect(() => {
    let on = true
    setData(null)
    setErr(null)
    listenAPI.getStage(stage).then((d) => { if (on) setData(d) }).catch(() => { if (on) setErr('단계를 불러오지 못했어요.') })
    return () => { on = false }
  }, [stage, nonce])
  useEffect(() => () => stopAll(), [])
  const onProgress = useCallback((cur, total) => setProg({ cur, total }), [])
  const exit = () => { stopAll(); navigate('/learn/path?track=listen') }
  const reload = () => setNonce((n) => n + 1)

  const Task = data ? TASK[data.mode] : null
  const pct = prog.total ? (prog.cur / prog.total) * 100 : 0
  return (
    <div data-track="listen" className="flex min-h-[100dvh] flex-col bg-page">
      <div className="mx-auto w-full max-w-[676px] px-[18px] pt-[18px] lg:pt-7">
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={exit} aria-label="나가기" className="shrink-0">
            <img src={IC.close} alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-[width] duration-500" style={{ width: `${pct}%` }} />
          </div>
          {prog.total > 0 && <span className="shrink-0 text-[13px] font-bold text-ink-muted lg:text-[15px]">{Math.min(prog.cur + 1, prog.total)} / {prog.total}</span>}
        </div>
      </div>
      <main className="mx-auto flex w-full max-w-[676px] flex-1 flex-col gap-4 px-[18px] pb-8 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">소리 듣기 · {stage + 1}단계</p>
            <h1 className="text-[21px] font-bold tracking-[-0.5px] text-ink lg:text-[26px]">{data?.title || '…'}</h1>
          </div>
          {settings && !editing && (
            <button type="button" onClick={() => { stopAll(); setEditing(true) }} className="btn-secondary shrink-0 px-3 py-2 text-[13px]">소리 크기</button>
          )}
        </div>
        {err ? (
          <Card className="flex flex-col items-center gap-3 text-center">
            <p className="text-[16px] font-bold text-ink">{err}</p>
            <button type="button" onClick={reload} className="btn-primary px-6 py-2.5 text-[14px]">다시 불러오기</button>
          </Card>
        ) : !settings || editing ? (
          <ListenSetup initial={settings} onSave={(v) => { saveSettings(v); setEditing(false) }} onCancel={settings ? () => setEditing(false) : null} />
        ) : !data || !voiceList ? (
          <LoadingScreen variant="section" />
        ) : data.status === 'locked' ? (
          <Card className="flex flex-col items-center gap-3 text-center">
            <p className="text-[16px] font-bold text-ink">앞 단계를 먼저 숙달해 주세요</p>
            <button type="button" onClick={exit} className="btn-primary px-6 py-2.5 text-[14px]">학습 경로로</button>
          </Card>
        ) : (
          <>
            {stage > 0 && <p className="text-[14px] leading-[1.6] text-ink-muted">{data.guide}</p>}
            <Task key={`${stage}:${nonce}`} data={data} settings={settings} voices={voices} onProgress={onProgress} onExit={exit} reload={reload}
              noisy={data.mode === 'noise'} />
          </>
        )}
        <p className="mt-auto pt-4 text-center text-[11px] leading-[1.6] text-ink-faint">{NOTICE}</p>
      </main>
    </div>
  )
}
