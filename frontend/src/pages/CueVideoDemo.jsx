import { useEffect, useMemo, useRef, useState } from 'react'
import { CueGlyph, CUE_META, useCuesEnabled } from '../components/CueBadges'
import {
  parsePack, syllableWindows, activeIndex, nearestSample, cueAnchor, nasalPolyline,
} from '../lib/cueVideo'

/**
 * 실제 영상 위 기호(연구용, 계획서 J-9·K-4): /lab/cue-video
 * ------------------------------------------------------------------
 * 촬영된 화자 영상에 강제정렬로 얻은 음절 시각을 맞춰 J 기호(기식·긴장·울림)를 입 옆에 띄운다.
 * 투명 두상(F)은 우리 아바타에서만 되지만, 규칙 기호는 어떤 촬영 영상에도 얹을 수 있다는 점을 보인다.
 * 아래 그래프는 같은 화자 영상에서 K가 낸 비음 확률이다(K-4). 묶음(pack.json + 영상)은
 * liplab-lab/tools/cue_video.py pack이 만들고, 영상은 서버로 보내지 않고 브라우저에서만 재생한다.
 * 열기: 파일 고르기(pack.json과 영상을 함께) 또는 ?pack=<pack.json 주소>.
 */
const CHART_W = 1000
const CHART_H = 110
const RATES = [0.5, 0.75, 1]

function fmtSigned(x) {
  if (x == null) return '-'
  return `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(2)}`
}

export default function CueVideoDemo() {
  const cuesOn = useCuesEnabled()
  const [pack, setPack] = useState(null)
  const [urls, setUrls] = useState({})
  const [err, setErr] = useState('')
  const [sel, setSel] = useState(0)
  const [t, setT] = useState(0)
  const [dur, setDur] = useState(0)
  const [rate, setRate] = useState(1)
  const videoRef = useRef(null)

  // ?pack=주소 로 열기(연구실 정적 서버). 영상 주소는 pack.json 기준 상대 경로로 푼다.
  useEffect(() => {
    const src = new URLSearchParams(window.location.search).get('pack')
    if (!src) return undefined
    let alive = true
    fetch(src)
      .then((r) => { if (!r.ok) throw new Error(`묶음을 받지 못했어요(${r.status}).`); return r.json() })
      .then((j) => {
        if (!alive) return
        const p = parsePack(j)
        const base = new URL(src, window.location.href)
        setUrls(Object.fromEntries(p.clips.map((c) => [c.video, new URL(c.video, base).href])))
        setPack(p)
        setSel(0)
      })
      .catch((e) => { if (alive) setErr(e.message || '묶음을 읽지 못했어요.') })
    return () => { alive = false }
  }, [])

  // 파일로 연 영상 주소는 바꾸거나 떠날 때 돌려준다.
  useEffect(() => () => {
    Object.values(urls).forEach((u) => { if (u.startsWith('blob:')) URL.revokeObjectURL(u) })
  }, [urls])

  const onFiles = async (e) => {
    const files = [...(e.target.files || [])]
    const js = files.find((f) => f.name.endsWith('.json'))
    if (!js) { setErr('pack.json을 영상과 함께 골라 주세요.'); return }
    try {
      const p = parsePack(JSON.parse(await js.text()))
      const map = {}
      for (const f of files) if (!f.name.endsWith('.json')) map[f.name] = URL.createObjectURL(f)
      const missing = p.clips.filter((c) => !map[c.video]).length
      setUrls(map)
      setPack(p)
      setSel(0)
      setErr(missing ? `영상 ${missing}개를 찾지 못했어요. pack.json과 같은 폴더의 영상을 함께 골라 주세요.` : '')
    } catch (er) {
      setErr(er.message || '묶음을 읽지 못했어요.')
    }
  }

  const clip = pack?.clips[sel] || null
  const windows = useMemo(() => (clip ? syllableWindows(clip.syllables) : []), [clip])
  const byK = useMemo(() => new Map((clip?.syllables || []).map((s, i) => [s.k, i])), [clip])
  const lastT = clip ? Math.max(clip.syllables[clip.syllables.length - 1].t0 + 0.6,
    clip.nasal?.length ? clip.nasal[clip.nasal.length - 1][0] : 0) : 1
  const duration = dur > 0 ? dur : lastT

  // 재생 중에는 프레임마다 시각을 읽는다(timeupdate는 초당 4번 정도라 기호가 늦게 뜬다).
  useEffect(() => {
    const v = videoRef.current
    if (!v) return undefined
    let raf = 0
    const tick = () => { setT(v.currentTime); raf = requestAnimationFrame(tick) }
    const onPlay = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(tick) }
    const onStop = () => { cancelAnimationFrame(raf); setT(v.currentTime) }
    const evs = ['pause', 'seeked', 'ended']
    v.addEventListener('play', onPlay)
    evs.forEach((ev) => v.addEventListener(ev, onStop))
    setT(0)
    setDur(0)
    return () => {
      cancelAnimationFrame(raf)
      v.removeEventListener('play', onPlay)
      evs.forEach((ev) => v.removeEventListener(ev, onStop))
    }
  }, [clip])

  useEffect(() => { if (videoRef.current) videoRef.current.playbackRate = rate }, [rate, clip])

  const ai = activeIndex(windows, t)
  const active = ai >= 0 ? clip.syllables[ai] : null
  const anchor = cueAnchor(nearestSample(clip?.mouth, t))

  const seekTo = (i) => {
    const v = videoRef.current
    if (!v || !windows[i]) return
    v.currentTime = windows[i].start + 0.001
    setT(v.currentTime)
  }

  if (cuesOn === false) {
    return (
      <div className="mx-auto max-w-3xl p-6 text-sm text-gray-600">
        이 계정은 기호 없이 학습하는 연구 집단이라 이 화면을 열지 않아요.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6">
      <header className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">연구용 · J-9 · K-4</p>
        <h1 className="text-xl font-bold text-gray-900">실제 영상 위 기호</h1>
        <p className="text-sm text-gray-600">
          촬영된 화자 영상에 강제정렬 음절 시각을 맞춰, 입모양으로는 안 보이는 자질 기호를 입 옆에 띄웁니다.
          영상은 이 브라우저 안에서만 재생됩니다.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-3 text-sm">
        <label className="inline-flex cursor-pointer items-center rounded-lg border border-gray-300 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50">
          묶음 열기
          <input type="file" multiple accept=".json,video/*" className="sr-only" onChange={onFiles} />
        </label>
        <span className="text-gray-500">pack.json과 영상 파일을 함께 고릅니다. 묶음은 <code className="text-xs">tools/cue_video.py pack</code>으로 만듭니다.</span>
        {err && <span className="w-full text-rose-600">{err}</span>}
      </div>

      {!pack && !err && (
        <p className="text-sm text-gray-500">열린 묶음이 없습니다.</p>
      )}

      {pack && clip && (
        <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
          <div className="space-y-3">
            <div className="relative overflow-hidden rounded-xl bg-black">
              <video
                key={clip.video}
                ref={videoRef}
                src={urls[clip.video]}
                controls
                playsInline
                preload="auto"
                className="block h-auto w-full"
                onLoadedMetadata={(e) => setDur(e.currentTarget.duration || 0)}
              />
              <div className="pointer-events-none absolute inset-0" aria-hidden="true">
                {active && active.cues.length > 0 && (
                  <div
                    className="absolute flex -translate-y-1/2 items-end gap-1"
                    style={{ left: `${anchor.x * 100}%`, top: `${anchor.y * 100}%` }}
                  >
                    {active.cues.map((c, i) => (
                      <div
                        key={`${c.position}-${i}`}
                        className="flex flex-col items-center gap-0.5 rounded-md border bg-white/90 px-1 pb-0.5 pt-1 shadow-sm"
                        style={{ borderColor: CUE_META[c.cue]?.color }}
                      >
                        <CueGlyph cue={c.cue} size={22} />
                        <span className="text-[10px] leading-none text-gray-600">{c.phoneme}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-gray-500">속도</span>
              {RATES.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRate(r)}
                  className={`rounded-md border px-2 py-0.5 ${rate === r ? 'border-gray-800 bg-gray-800 text-white' : 'border-gray-300 text-gray-700 hover:bg-gray-50'}`}
                >
                  {r}×
                </button>
              ))}
              <span className="ml-auto text-xs text-gray-400">{clip.speaker} · {t.toFixed(2)}초</span>
            </div>

            {/* 문장: 지금 음절 강조, 기호가 있는 음절 위에 작은 기호. 누르면 그 음절로 이동 */}
            <p className="rounded-xl border border-gray-200 bg-white p-3 text-lg leading-[2.6rem] text-gray-800">
              {(() => {
                let k = -1
                return [...clip.text].map((ch, ci) => {
                  if (!('가' <= ch && ch <= '힣')) return <span key={ci}>{ch}</span>
                  k += 1
                  const i = byK.get(k)
                  const s = i != null ? clip.syllables[i] : null
                  const on = s && i === ai
                  return (
                    <button
                      key={ci}
                      type="button"
                      disabled={i == null}
                      onClick={() => seekTo(i)}
                      className={`relative inline-block rounded px-0.5 ${on ? 'bg-gray-900 text-white' : 'hover:bg-gray-100'} ${i == null ? 'text-gray-400' : ''}`}
                    >
                      {s?.cues.length > 0 && (
                        <span className="absolute -top-3 left-1/2 flex -translate-x-1/2 gap-px">
                          {s.cues.map((c, j) => <CueGlyph key={j} cue={c.cue} size={10} />)}
                        </span>
                      )}
                      {ch}
                    </button>
                  )
                })
              })()}
            </p>

            {/* K 비음 확률(화자 영상) + 음절 눈금 */}
            <div className="rounded-xl border border-gray-200 bg-white p-3">
              <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
                <span>K 비음 확률(이 화자 영상)</span>
                <span>점선: 발화 중앙값 {clip.k_median?.toFixed(2) ?? '-'}</span>
              </div>
              <svg viewBox={`0 0 ${CHART_W} ${CHART_H + 18}`} className="h-auto w-full" role="img" aria-label="K 비음 확률 그래프">
                {clip.syllables.map((s, i) => {
                  const x = (s.t0 / duration) * CHART_W
                  const tone = s.nasal_expect === 1 ? CUE_META.nasal.color : s.nasal_expect === 0 ? '#9ca3af' : null
                  return (
                    <g key={i}>
                      <line x1={x} x2={x} y1={0} y2={CHART_H} stroke="#e5e7eb" strokeWidth="1" />
                      {tone && <circle cx={x} cy={6} r={3.5} fill={tone} />}
                      <text x={x} y={CHART_H + 14} fontSize="11" textAnchor="middle" fill={i === ai ? '#111827' : '#9ca3af'}>{s.char}</text>
                    </g>
                  )
                })}
                {clip.k_median != null && (
                  <line x1={0} x2={CHART_W} y1={(1 - clip.k_median) * CHART_H} y2={(1 - clip.k_median) * CHART_H}
                    stroke="#9ca3af" strokeDasharray="4 4" strokeWidth="1" />
                )}
                <polyline points={nasalPolyline(clip.nasal, duration, CHART_W, CHART_H)} fill="none"
                  stroke={CUE_META.nasal.color} strokeWidth="1.8" />
                <line x1={(t / duration) * CHART_W} x2={(t / duration) * CHART_W} y1={0} y2={CHART_H} stroke="#111827" strokeWidth="1.5" />
              </svg>
              <p className="mt-1 text-xs text-gray-500">
                위 점: 보라 = 표준발음상 비음 음절, 회색 = 같은 입모양의 파열음 음절.
                지금 음절의 K 값(중앙값 대비) {active ? fmtSigned(active.k_rel) : '-'}.
              </p>
            </div>
          </div>

          <aside className="space-y-3">
            <div className="rounded-xl border border-gray-200 bg-white p-3">
              <p className="mb-2 text-xs font-semibold text-gray-500">클립</p>
              <ul className="space-y-1">
                {pack.clips.map((c, i) => (
                  <li key={c.clip}>
                    <button
                      type="button"
                      onClick={() => setSel(i)}
                      className={`w-full rounded-lg px-2 py-1.5 text-left text-sm ${i === sel ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'}`}
                    >
                      <span className="block text-[11px] opacity-70">{c.speaker}</span>
                      <span className="line-clamp-2">{c.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-1.5 rounded-xl border border-gray-200 bg-white p-3 text-xs text-gray-600">
              <p className="font-semibold text-gray-500">기호</p>
              {Object.entries(CUE_META).map(([k, m]) => (
                <p key={k} className="flex items-center gap-1.5"><CueGlyph cue={k} size={14} /> {m.label}</p>
              ))}
              <p className="text-gray-400">평음은 기준이라 기호가 없습니다. 기호 아래 글자는 해당 자음(표준발음)입니다.</p>
            </div>

            {pack.k4?.auc && (
              <div className="space-y-1.5 rounded-xl border border-gray-200 bg-white p-3 text-xs leading-relaxed text-gray-600">
                <p className="font-semibold text-gray-500">K가 울림 기호를 받쳐 주나(K-4)</p>
                <p>
                  화자 영상 {pack.k4.clips}클립({pack.k4.speakers}명)에서 K 비음 확률은 울림 음절
                  {` ${pack.k4.auc.n_pos}`}개와 같은 입모양 파열음 음절 {pack.k4.auc.n_neg}개를 가르지 못했습니다
                  (AUC {pack.k4.auc.auc.toFixed(2)} [{pack.k4.auc.ci95[0].toFixed(2)}, {pack.k4.auc.ci95[1].toFixed(2)}]).
                </p>
                {pack.k4.controls?.vowel_jawOpen != null && (
                  <p>
                    같은 시각 창으로 입 벌림은 벌린·닫힌 모음을 {pack.k4.controls.vowel_jawOpen.toFixed(2)},
                    입술 닫힘은 양순·치조 초성을 {pack.k4.controls.bilabial_lipClosure?.toFixed(2)}로 갈라 정렬은 맞습니다.
                  </p>
                )}
                <p>그래서 기호는 문장 규칙으로만 켜고, K 값은 참고로만 보여 줍니다.</p>
              </div>
            )}

            <p className="text-[11px] leading-relaxed text-gray-400">{pack.source} 정렬: {pack.alignment}.</p>
          </aside>
        </div>
      )}
    </div>
  )
}
