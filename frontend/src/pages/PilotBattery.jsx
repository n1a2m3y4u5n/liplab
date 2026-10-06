import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { batteryAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import LoadingScreen from '../components/LoadingScreen'
import { resetRenderTiming } from '../lib/frameClock'
import {
  LAYER_LABEL, MISSING_LABEL, addVideoQuality, buildRenderLog, hasWebGL, noiseGain, rmsDbfs, nonsensePreview, playState,
  reactionTimes, queueOf,
} from '../lib/pilotBattery'

/**
 * 청인 예비 파일럿(P3) 검사 묶음 — /pilot/battery. 파일럿 참여자만 쓴다(서버가 403으로 막고, 프로필의 파일럿 메뉴에서만 들어온다).
 * 연구진이 옆에서 회차(A1·A2·B·R)와 층을 골라 진행한다. 층: 무의미 낱말 자음(아바타), 실제 얼굴 낱말(영상), 개방형 문장
 * (영상 또는 아바타), SNR 맞추기와 소음 속 문장(영상 + 잡담 잡음, A1에서 SNR을 정한다). docs/pilot/battery.md
 * 검사이므로 정답은 알려 주지 않는다. 영상이 아직 없는 문항은 '영상 준비 전'으로만 알리고 내지도 세지도 않는다.
 * 문항마다 재생 횟수(최대 목록의 max_plays), 첫 재생 끝부터와 시작부터 답까지의 시간(ms)을 남기고, 층 끝에 기기·렌더링 요약을 보낸다.
 */
const STATE_TEXT = { done: '마침', in_progress: '진행 중', todo: '시작 전' }
const STATE_TONE = { done: 'bg-good-tint text-good-text', in_progress: 'bg-warn-tint text-warn-text', todo: 'bg-fill text-ink-muted' }

function missingText(missing) {
  const parts = Object.entries(missing || {}).filter(([, n]) => n > 0).map(([k, n]) => `${MISSING_LABEL[k] || k} ${n}`)
  return parts.join(' · ')
}

export default function PilotBattery() {
  const navigate = useNavigate()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [run, setRun] = useState(null)          // 진행 중인 층(서버 start 응답)
  const [checks, setChecks] = useState({ headphone: false, volume: false })
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try { setStatus(await batteryAPI.status()) } catch (e) {
      setError(e?.response?.data?.detail || '검사 상태를 불러오지 못했어요.')
    }
  }, [])
  useEffect(() => { load() }, [load])

  const start = async (label, layer) => {
    setBusy(true); setError(null)
    try { setRun(await batteryAPI.start(label, layer)) } catch (e) {
      setError(e?.response?.data?.detail || '검사를 시작하지 못했어요.')
    } finally { setBusy(false) }
  }

  if (run) {
    return <LayerRunner run={run} checks={checks} onExit={() => { setRun(null); load() }} />
  }
  if (!status && !error) return <LoadingScreen />

  return (
    <div className="min-h-[100dvh] bg-page">
      <div className="mx-auto flex max-w-[720px] flex-col gap-5 px-[18px] py-8">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-[24px] font-bold tracking-[-0.5px] text-ink">파일럿 검사</h1>
          <button type="button" onClick={() => navigate('/profile')} className="btn-secondary px-4 py-2 text-[14px]">나가기</button>
        </div>
        {error && <p role="alert" className="rounded-13 bg-bad-tint px-4 py-3 text-[14px] font-bold text-bad-text">{error}</p>}
        {status && (
          <>
            <section className="flex flex-col gap-1.5 rounded-16 border-2 border-line bg-white px-5 py-4 text-[14px] text-ink">
              <p><b>참여 순번</b> {status.seq} · <b>폼 순서</b> {status.order.split('').join(' → ')}</p>
              <p className="text-ink-muted">목록 {status.manifest.version}{status.manifest.status === 'draft' ? ' (초안)' : ''}
                {status.snr_calibrated_db != null && ` · 개인 SNR ${status.snr_calibrated_db} dB`}</p>
              {status.manifest.status === 'draft' && (
                <p className="text-[13px] text-warn-text">초안 목록이에요. 문장·낱말을 동결하고 촬영하기 전에는 팀 리허설에만 써요.</p>
              )}
              {status.manifest.n_errors > 0 && (
                <p className="text-[13px] font-bold text-bad-text">목록 점검 문제 {status.manifest.n_errors}개: {status.manifest.errors.slice(0, 3).join(' / ')}</p>
              )}
            </section>

            <section className="flex flex-col gap-2 rounded-16 border-2 border-line bg-white px-5 py-4 text-[14px] text-ink">
              <p className="font-bold">소음 속 검사 전에 확인</p>
              <label className="flex items-center gap-2"><input type="checkbox" checked={checks.headphone}
                onChange={(e) => setChecks((c) => ({ ...c, headphone: e.target.checked }))} />헤드폰을 썼어요</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={checks.volume}
                onChange={(e) => setChecks((c) => ({ ...c, volume: e.target.checked }))} />기기 볼륨을 정한 값으로 고정했어요</label>
            </section>

            {status.labels.map((L) => (
              <section key={L.label} className={`flex flex-col gap-3 rounded-16 border-2 bg-white px-5 py-4 ${status.next_label === L.label ? 'border-track' : 'border-line'}`}>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[17px] font-bold text-ink">{L.label} <span className="text-[14px] font-bold text-ink-muted">· 폼 {L.form}</span></p>
                  <span className="text-[13px] font-bold text-ink-muted">{L.done ? '회차 마침' : L.available ? '진행할 수 있어요' : '앞 회차를 먼저 마쳐요'}</span>
                </div>
                {L.layers.map((x) => {
                  const audioLayer = x.layer === 'av' || x.layer === 'snr'
                  const blocked = !L.available || x.state === 'done' || x.n_ready === 0 || (audioLayer && !(checks.headphone && checks.volume))
                  return (
                    <div key={x.layer} className="flex flex-col gap-2 border-t border-line pt-3 sm:flex-row sm:items-center">
                      <div className="flex min-w-0 flex-1 items-center gap-2">
                        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[12px] font-bold ${STATE_TONE[x.state]}`}>{STATE_TEXT[x.state]}</span>
                        <span className="min-w-0 text-[15px] font-bold text-ink">{x.title || LAYER_LABEL[x.layer]}</span>
                      </div>
                      <div className="flex items-center justify-between gap-2 sm:justify-end">
                        <span className="text-[12px] text-ink-muted">준비 {x.n_ready}/{x.n_items}{missingText(x.missing) ? ` · ${missingText(x.missing)}` : ''}</span>
                        <button type="button" disabled={busy || blocked} onClick={() => start(L.label, x.layer)}
                          className="btn-primary shrink-0 px-4 py-2 text-[14px] disabled:cursor-not-allowed disabled:opacity-50">
                          {x.state === 'in_progress' ? '이어서' : '시작'}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </section>
            ))}
          </>
        )}
      </div>
    </div>
  )
}

// ── 층 하나 진행 ───────────────────────────────────────
function LayerRunner({ run, checks, onExit }) {
  const maxPlays = run.playback?.max_plays || 2
  const [items, setItems] = useState(run.items)
  const q = useMemo(() => queueOf(items), [items])
  const item = q.todo[0] || null
  const [stair, setStair] = useState(run.staircase || null)
  const [summary, setSummary] = useState(null)
  const [err, setErr] = useState(null)
  const videoQ = useRef({ total: 0, dropped: 0 })
  const usedVideo = run.items.some((it) => it.media)
  const usedAvatar = run.items.some((it) => it.frames)
  const webgl = useMemo(() => hasWebGL(), [])
  const audio = useAudioMixer(run)

  useEffect(() => { resetRenderTiming() }, [])   // 이 층의 재생 지연만 센다

  const finished = !item || (run.layer === 'snr' && stair?.done)
  const finish = useCallback(async () => {
    setErr(null)
    const renderMode = usedVideo && usedAvatar ? 'mixed' : usedVideo ? 'video' : (webgl ? 'avatar3d' : 'avatar2d_fallback')
    try {
      setSummary(await batteryAPI.finish({
        session_id: run.session_id,
        render_log: buildRenderLog({ video: videoQ.current, renderMode, webgl }),
        ...(run.layer === 'av' || run.layer === 'snr' ? { headphone_check: checks.headphone, volume_fixed: checks.volume } : {}),
      }))
    } catch (e) { setErr(e?.response?.data?.detail || '마침을 저장하지 못했어요. 다시 눌러 주세요.') }
  }, [run, checks, usedVideo, usedAvatar, webgl])

  const submit = async (body) => {
    setErr(null)
    try {
      const r = await batteryAPI.answer({ session_id: run.session_id, item_id: item.id, ...body })
      if (r.staircase) setStair(r.staircase)
      setItems((xs) => xs.map((x) => (x.id === item.id ? { ...x, answered: true } : x)))
      return true
    } catch (e) {
      setErr(e?.response?.data?.detail || '답을 보내지 못했어요. 다시 눌러 주세요.')
      return false
    }
  }

  const snrNow = run.layer === 'snr' ? stair?.next_db : run.snr_db
  return (
    <div className="min-h-[100dvh] bg-page">
      <div className="mx-auto flex max-w-[720px] flex-col gap-4 px-[18px] py-6">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[15px] font-bold text-ink">{run.label} · {run.title || LAYER_LABEL[run.layer]} · 폼 {run.form}</p>
          <button type="button" onClick={onExit} className="btn-secondary px-4 py-2 text-[14px]">나가기</button>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-fill-strong">
          <div className="h-full rounded-full bg-track transition-all" style={{ width: `${q.nReady ? (q.nDone / q.nReady) * 100 : 100}%` }} />
        </div>
        <p className="text-[13px] text-ink-muted">
          {q.nDone} / {q.nReady}문항{run.layer === 'snr' && stair ? ` · 시행 ${stair.n_trials}` : ''}
          {q.missing.length > 0 && ` · ${missingText(run.missing)} 문항은 내지 않고 세지 않아요`}
        </p>
        {err && <p role="alert" className="rounded-13 bg-bad-tint px-4 py-3 text-[14px] font-bold text-bad-text">{err}</p>}

        {finished ? (
          <section className="flex flex-col items-center gap-3 rounded-16 border-2 border-line bg-white px-5 py-8 text-center">
            {summary ? (
              <>
                <p className="text-[19px] font-bold text-ink">이 검사를 마쳤어요</p>
                <p className="text-[14px] text-ink-muted">답한 문항 {summary.n_answered} / 준비된 문항 {summary.n_ready}
                  {summary.snr_calibrated_db != null && ` · 개인 SNR ${summary.snr_calibrated_db} dB`}</p>
                <button type="button" onClick={onExit} className="btn-primary px-6 py-3 text-[15px]">목록으로</button>
              </>
            ) : (
              <>
                <p className="text-[17px] font-bold text-ink">{q.nReady === 0 ? '준비된 문항이 없어요' : '모든 문항에 답했어요'}</p>
                <button type="button" onClick={finish} className="btn-primary px-6 py-3 text-[15px]">마침 저장</button>
              </>
            )}
          </section>
        ) : audio.enabled && audio.status !== 'ready' ? (
          <section role="status" className="rounded-16 border-2 border-line bg-white px-5 py-8 text-center text-[15px] font-bold text-ink-muted">
            {audio.status === 'loading' ? '잡음 소리를 준비하고 있어요…'
              : '잡음 소리를 불러오지 못해 이 검사를 진행할 수 없어요. 연구진에게 알려 주세요.'}
          </section>
        ) : (
          <ItemView run={run} item={item} maxPlays={maxPlays} audio={audio} snrDb={snrNow}
            onVideoQuality={(vq) => { videoQ.current = addVideoQuality(videoQ.current, vq) }} onSubmit={submit} />
        )}
      </div>
    </div>
  )
}

// ── 문항 하나: 자극 재생 + 응답 ───────────────────────────
// 문항이 바뀌어도 아바타(3D 캔버스)를 다시 만들지 않도록 이 구성 요소는 key로 다시 마운트하지 않고, 문항 id가 바뀌면 상태만 처음으로 돌린다
// (다시 마운트하면 문항마다 WebGL 컨텍스트를 새로 만들어 첫 그리기까지 0.1~1초가 걸린다, MouthAvatar 머리말). 영상과 답 칸은 문항마다 새로 만든다.
function ItemView({ run, item, maxPlays, audio, snrDb, onVideoQuality, onSubmit }) {
  const [plays, setPlays] = useState(0)
  const [playing, setPlaying] = useState(false)
  const t = useRef({ firstOnsetAt: null, firstEndedAt: null })
  const [ended, setEnded] = useState(false)
  const [sending, setSending] = useState(false)
  const [cur, setCur] = useState(item.id)
  if (cur !== item.id) {
    setCur(item.id); setPlays(0); setPlaying(false); setEnded(false); setSending(false)
    t.current = { firstOnsetAt: null, firstEndedAt: null }
  }
  const ps = playState({ plays, playing, firstEndedAt: ended ? 1 : null, maxPlays })

  const onStart = () => {
    if (t.current.firstOnsetAt == null) t.current.firstOnsetAt = performance.now()
  }
  const onEnd = () => {
    setPlaying(false)
    if (t.current.firstEndedAt == null) { t.current.firstEndedAt = performance.now(); setEnded(true) }
  }
  const play = () => {
    if (!ps.canPlay) return
    setPlays((n) => n + 1)
    setPlaying(true)
  }

  const send = async (body) => {
    if (sending || !ps.canAnswer) return
    setSending(true)
    const rt = reactionTimes({ ...t.current, answeredAt: performance.now() })
    const ok = await onSubmit({ ...body, ...rt, plays })
    if (!ok) setSending(false)
  }

  const hidden = item.modality === 'A' || run.layer === 'snr'   // 청각만: 영상은 가리고 소리만
  return (
    <section className="flex flex-col gap-4 rounded-16 border-2 border-line bg-white px-4 py-4 lg:px-6">
      <div className="relative overflow-hidden rounded-14 bg-[#1a1a2e]" style={{ height: 300 }}>
        {item.frames ? (
          <LipSyncPlayer3D visemes={item.frames} isPlaying={playing} onComplete={onEnd} showControls={false} stageHeight={300}
            onFrameChange={(f) => { if (f.index === 0 && !f.completed) onStart() }} />
        ) : (
          <VideoStim key={item.id} item={item} playing={playing} hidden={hidden} audio={audio} snrDb={snrDb}
            onStart={onStart} onEnd={onEnd} onQuality={onVideoQuality} />
        )}
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] text-ink-muted">
          {hidden ? '소리만 들어요' : item.modality === 'AV' ? '보면서 들어요' : '소리 없이 봐요'} · 남은 재생 {ps.left}번
        </span>
        <button type="button" onClick={play} disabled={!ps.canPlay}
          className="btn-secondary px-5 py-2.5 text-[15px] disabled:cursor-not-allowed disabled:opacity-50">
          {plays === 0 ? '재생' : '한 번 더'}
        </button>
      </div>
      {run.response === 'choice4' && <ChoiceAnswer key={item.id} options={item.options} disabled={!ps.canAnswer || sending} onSend={(c) => send({ chosen: c })} />}
      {run.response === 'typed' && <TypedAnswer key={item.id} disabled={!ps.canAnswer || sending} onSend={(txt) => send({ answer_text: txt })} />}
      {run.response === 'consonant3' && <ConsonantAnswer key={item.id} sets={run.consonant_sets} vowels={item.vowels} disabled={!ps.canAnswer || sending}
        onSend={(cs) => send({ chosen_consonants: cs })} />}
      {!ps.canAnswer && <p className="text-center text-[13px] text-ink-faint">끝까지 한 번 재생한 뒤에 답할 수 있어요</p>}
    </section>
  )
}

function ChoiceAnswer({ options = [], disabled, onSend }) {
  const [sel, setSel] = useState(null)
  return (
    <div className="flex flex-col gap-2.5">
      <div className="grid grid-cols-2 gap-2.5">
        {options.map((o, i) => (
          <button key={o} type="button" disabled={disabled} onClick={() => setSel(o)} aria-pressed={sel === o}
            className={`flex items-center gap-3 rounded-14 border-2 border-b-5 px-4 py-3.5 text-left disabled:opacity-60 ${sel === o ? 'border-track bg-track-tint' : 'border-line bg-white'}`}>
            <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold text-ink-muted">{i + 1}</span>
            <span className="text-[18px] font-bold text-ink">{o}</span>
          </button>
        ))}
      </div>
      <button type="button" disabled={disabled || !sel} onClick={() => onSend(sel)} className="btn-primary py-3.5 text-[16px] disabled:opacity-50">다음</button>
    </div>
  )
}

function TypedAnswer({ disabled, onSend }) {
  const [text, setText] = useState('')
  return (
    <form className="flex flex-col gap-2.5" onSubmit={(e) => { e.preventDefault(); if (!disabled) onSend(text) }}>
      <input value={text} onChange={(e) => setText(e.target.value)} disabled={disabled} maxLength={200} autoComplete="off"
        autoCorrect="off" autoCapitalize="off" spellCheck={false} placeholder="본 문장을 써 주세요(일부만 알아도 써요)"
        className="w-full rounded-13 border-2 border-line px-4 py-3 text-[17px] outline-none focus:border-primary-400 disabled:opacity-60" />
      <div className="flex gap-2.5">
        <button type="button" disabled={disabled} onClick={() => onSend('')} className="btn-secondary flex-1 py-3.5 text-[15px] disabled:opacity-50">모르겠어요</button>
        <button type="submit" disabled={disabled || !text.trim()} className="btn-primary flex-[2] py-3.5 text-[16px] disabled:opacity-50">다음</button>
      </div>
    </form>
  )
}

const POS_LABEL = { C1: '첫 자음', C2: '가운데 자음', C3: '받침' }

function ConsonantAnswer({ sets = {}, vowels = [], disabled, onSend }) {
  const [ch, setCh] = useState([null, null, null])
  const pick = (i, c) => setCh((xs) => xs.map((x, j) => (j === i ? c : x)))
  return (
    <div className="flex flex-col gap-3">
      <p className="text-center text-[28px] font-bold tracking-[2px] text-ink">{nonsensePreview(vowels, ch)}</p>
      {['C1', 'C2', 'C3'].map((pos, i) => (
        <div key={pos} className="flex flex-col gap-1.5">
          <p className="text-[12px] font-bold text-ink-muted">{POS_LABEL[pos]}</p>
          <div className="flex flex-wrap gap-1.5">
            {(sets[pos] || []).map((c) => (
              <button key={c} type="button" disabled={disabled} onClick={() => pick(i, c)} aria-pressed={ch[i] === c}
                className={`size-11 rounded-10 border-2 text-[18px] font-bold disabled:opacity-60 ${ch[i] === c ? 'border-track bg-track-tint text-ink' : 'border-line bg-white text-ink'}`}>
                {c}
              </button>
            ))}
          </div>
        </div>
      ))}
      <button type="button" disabled={disabled || ch.some((x) => !x)} onClick={() => onSend(ch)} className="btn-primary py-3.5 text-[16px] disabled:opacity-50">다음</button>
    </div>
  )
}

// ── 영상 자극 ─────────────────────────────────────────
// 영상은 로그인 머리글이 필요해 blob으로 받아 주소를 만든다. 소리가 필요한 층(av·snr)은 영상 소리를 Web Audio로 보내고, 잡담 잡음을
// 개인 SNR에 맞춘 크기로 함께 튼다(말소리 크기는 목록의 speech_rms_dbfs, 잡음 크기는 받은 파일에서 잰다). 소리가 필요 없는 층은 음소거.
function VideoStim({ item, playing, hidden, audio, snrDb, onStart, onEnd, onQuality }) {
  const ref = useRef(null)
  const [url, setUrl] = useState(null)
  const [failed, setFailed] = useState(false)
  const [noNoise, setNoNoise] = useState(false)   // 잡음을 틀지 못해 재생하지 않음(이 시행은 내지 않는다)
  const needsAudio = audio.enabled

  useEffect(() => {
    let on = true
    let made = null
    batteryAPI.blob(item.media).then((b) => { if (on) { made = URL.createObjectURL(b); setUrl(made) } }).catch(() => on && setFailed(true))
    return () => { on = false; if (made) URL.revokeObjectURL(made) }
  }, [item.media])

  useEffect(() => {
    const v = ref.current
    if (!v || !url) return
    v.muted = !needsAudio   // React의 muted 속성은 처음 그릴 때만 반영되는 경우가 있어 직접 맞춘다
    if (playing) {
      v.currentTime = 0
      const go = async () => {
        if (needsAudio && !(await audio.startNoise(v, item.speech_rms_dbfs, snrDb))) { setNoNoise(true); return }
        try { await v.play() } catch { if (needsAudio) audio.stopNoise(); onEnd() }
      }
      go()
    }
  }, [playing, url])   // eslint-disable-line react-hooks/exhaustive-deps

  const ended = () => {
    try { const qv = ref.current?.getVideoPlaybackQuality?.(); if (qv) onQuality(qv) } catch { /* 지원하지 않는 브라우저 */ }
    if (needsAudio) audio.stopNoise()
    onEnd()
  }

  if (failed) return <p className="flex h-full items-center justify-center text-[14px] font-bold text-white/80">영상 준비 전</p>
  if (!url) return <p className="flex h-full items-center justify-center text-[14px] text-white/60">영상을 받는 중</p>
  return (
    <>
      <video ref={ref} src={url} playsInline preload="auto" muted={!needsAudio} onPlaying={onStart} onEnded={ended}
        className="h-full w-full object-contain" />
      {hidden && <div className="absolute inset-0 flex items-center justify-center bg-[#1a1a2e] text-[15px] font-bold text-white/80">소리만 들어요</div>}
      {noNoise && <div role="alert" className="absolute inset-0 flex items-center justify-center bg-[#1a1a2e] px-4 text-center text-[14px] font-bold text-white">잡음을 틀지 못해 재생하지 않았어요. 연구진에게 알려 주세요.</div>}
    </>
  )
}

// 소음 층의 오디오 그래프: 영상 소리(MediaElementSource) + 반복 재생 잡음(AudioBuffer). 잡음은 말보다 0.3초 먼저 시작하고 0.3초 뒤에 멈춘다.
function useAudioMixer(run) {
  const enabled = run.layer === 'av' || run.layer === 'snr'
  const st = useRef({ ctx: null, noise: null, noiseDb: null, src: null, wired: new WeakSet() })
  // 잡음 준비 상태: 'off'(소리 층 아님) | 'loading' | 'ready' | 'failed'. 준비 전·실패 때는 시행을 내지 않는다
  // (깨끗한 소리로 들은 답이 그 SNR로 기록되면 계단과 개인 SNR이 틀어진다)
  const [status, setStatus] = useState(enabled ? (run.noise ? 'loading' : 'failed') : 'off')
  useEffect(() => {
    if (!enabled) { setStatus('off'); return undefined }
    if (!run.noise) { setStatus('failed'); return undefined }
    let on = true
    setStatus('loading')
    batteryAPI.blob(run.noise).then((b) => b.arrayBuffer()).then(async (buf) => {
      if (!on) return
      const Ctx = window.AudioContext || window.webkitAudioContext
      const ctx = st.current.ctx || new Ctx()
      st.current.ctx = ctx
      const decoded = await ctx.decodeAudioData(buf)
      st.current.noise = decoded
      st.current.noiseDb = rmsDbfs(decoded.getChannelData(0))
      if (on) setStatus(Number.isFinite(st.current.noiseDb) ? 'ready' : 'failed')
    }).catch(() => { if (on) setStatus('failed') })
    return () => { on = false; try { st.current.src?.stop() } catch { /* 이미 멈춤 */ } st.current.ctx?.close?.() }
  }, [enabled, run.noise])

  // 잡음을 틀었으면 true. 준비가 안 됐거나 크기 정보가 없으면 false(호출부는 재생하지 않는다)
  const startNoise = async (video, speechDb, snrDb) => {
    const s = st.current
    if (!s.ctx) return false
    if (s.ctx.state === 'suspended') await s.ctx.resume()
    if (!s.wired.has(video)) { s.ctx.createMediaElementSource(video).connect(s.ctx.destination); s.wired.add(video) }
    if (!s.noise || !Number.isFinite(s.noiseDb) || !Number.isFinite(speechDb) || !Number.isFinite(snrDb)) return false
    const src = s.ctx.createBufferSource()
    src.buffer = s.noise
    src.loop = true
    const g = s.ctx.createGain()
    g.gain.value = noiseGain(speechDb, s.noiseDb, snrDb)
    src.connect(g).connect(s.ctx.destination)
    src.start()
    s.src = src
    await new Promise((r) => setTimeout(r, 300))
    return true
  }
  const stopNoise = () => {
    const src = st.current.src
    st.current.src = null
    if (src) setTimeout(() => { try { src.stop() } catch { /* 이미 멈춤 */ } }, 300)
  }
  return { enabled, status, startNoise, stopNoise }
}
