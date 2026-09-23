import { useEffect, useRef, useState, useCallback } from 'react'
import VocalTract from './VocalTract'
import VocalTractVTL from './VocalTractVTL'
import { VOWEL_IDS, vtlWavUrl } from '../lib/vtlShapes'

/**
 * 성도 시뮬레이터 (계획서 E '인터랙티브 조음 교구', E-5·E-6).
 * 혀 위치(전후=F2, 고저=F1)와 입술 원순을 조작하면 성도 공명(포먼트)이 바뀌어 소리가
 * 실시간으로 변한다. 보이지 않는 조음(혀·성도 모양)과 소리의 관계를 귀로 직접 잇게 한다.
 *
 * 소리(발성 버튼): 브라우저 WebAudio 포먼트 합성(source-filter). 성문원(성대 진동)을 톱니
 * 오실레이터로, 성도 공명을 병렬 대역통과 필터 3개(F1~F3)로 근사한다. 끌 때마다 바로 반응해야
 * 해서 이 부분은 포먼트 근사로 둔다. 파동관 모델이 아니며 GPU·서버가 필요 없다.
 *
 * 성도 단면(E-6): VocalTractLab(VTL)을 파라미터 인터페이스로 오프라인 실행해 만든 자산
 * (scripts/vtl_build_assets.py → public/vtl/)을 읽는다. 지금 F1·F2와 원순에서 가장 가까운 VTL 격자
 * 상태를 추정 조음으로 그리고(lib/vtlShapes.js), 목표 모음의 VTL 형상을 점선으로 겹친다. '합성음
 * 듣기'는 VTL이 그 형상으로 합성한 모음이다. 앱은 VTL(GPL-3.0)을 번들하거나 호출하지 않고 결과
 * 파일만 받는다. 자산을 못 받으면 예전 도식(VocalTract)으로 그린다.
 *
 * 한계: 포먼트에서 성도 모양은 여러 가지가 가능해(다대일) 추정 단면은 그럴듯한 한 가지 예시이고
 * 진단이 아니다. 자음의 순간 폐쇄·마찰은 이 화면에서 다루지 않는다(자음 단면은 VocalTract의 vtl 모드).
 */

// F1(혀 높이): 위(고모음)=낮은 F1 ~ 아래(저모음)=높은 F1
const F1_LO = 250, F1_HI = 850
// F2(혀 전후): 왼쪽(전설)=높은 F2 ~ 오른쪽(후설)=낮은 F2
const F2_HI = 2500, F2_LO = 750
const F3_BASE = 2650

// 한국어 단모음 목표: (F1, F2) 대략치(성인 남성 기준, Hz). round=원순 필요.
// backend/formants.py VOWEL_TARGETS와 같은 값이고, scripts/vtl_build_assets.py가 두 곳이 같은지 확인한다.
const VOWELS = [
  { ko: 'ㅣ', f1: 300, f2: 2300, round: 0 },
  { ko: 'ㅔ', f1: 450, f2: 2000, round: 0 },
  { ko: 'ㅐ', f1: 620, f2: 1760, round: 0 },
  { ko: 'ㅏ', f1: 780, f2: 1300, round: 0 },
  { ko: 'ㅓ', f1: 600, f2: 1150, round: 0 },
  { ko: 'ㅗ', f1: 460, f2: 880, round: 1 },
  { ko: 'ㅜ', f1: 330, f2: 830, round: 1 },
  { ko: 'ㅡ', f1: 350, f2: 1500, round: 0 },
]

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v)
// 정규화 좌표(0~1) → 포먼트
const toF1 = (yn) => F1_LO + clamp(yn, 0, 1) * (F1_HI - F1_LO)
const toF2 = (xn) => F2_HI - clamp(xn, 0, 1) * (F2_HI - F2_LO)
// 포먼트 → 정규화 좌표(목표 마커 배치용)
const f1ToY = (f1) => (f1 - F1_LO) / (F1_HI - F1_LO)
const f2ToX = (f2) => (F2_HI - f2) / (F2_HI - F2_LO)

export default function VocalTractSimulator() {
  const [on, setOn] = useState(false)          // 발성 중
  const [pos, setPos] = useState({ x: 0.5, y: 0.5 })
  const [round, setRound] = useState(0)         // 입술 원순 0~1
  const [vol, setVol] = useState(0.3)           // 출력 볼륨 0~1 (기본 낮게)
  const volRef = useRef(0.3)
  const [nearest, setNearest] = useState(null)
  const [supported, setSupported] = useState(true)
  const [picked, setPicked] = useState(null)    // 학습자가 고른 목표 모음(null이면 가장 가까운 모음)
  const [playing, setPlaying] = useState(false)  // VTL 합성음 재생 중
  const audioRef = useRef(null)

  const ctxRef = useRef(null)
  const nodesRef = useRef(null)                 // {osc, formants:[{bp,g}], master}
  const draggingRef = useRef(false)
  const padRef = useRef(null)
  // 혀 위치·원순을 성도 단면(VocalTract)에 넘겨, 소리를 바꿀 때 입·혀 단면이 함께 변하게 한다(계획서 E).
  const artRef = useRef({ tip: 0, back: 0, round: 0, jaw: 0.02, close: 0 })

  // 현재 좌표+원순 → 포먼트 3개
  const formants = useCallback((p, r) => {
    let f1 = toF1(p.y)
    let f2 = toF2(p.x)
    let f3 = F3_BASE
    f2 -= r * 350        // 입술 원순 → F2·F3 하강
    f3 -= r * 300
    f1 -= r * 20
    return [f1, clamp(f2, 600, 2600), clamp(f3, 2200, 3000)]
  }, [])

  // WebAudio 그래프 구성(사용자 제스처에서 최초 생성)
  const ensureAudio = useCallback(() => {
    if (ctxRef.current) return true
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) { setSupported(false); return false }
    const ctx = new AC()
    const osc = ctx.createOscillator()
    osc.type = 'sawtooth'
    osc.frequency.value = 120                   // 성문 기본주파수(남성 근사)
    const master = ctx.createGain()
    master.gain.value = 0.0001
    const [f1, f2, f3] = formants(pos, round)
    const amps = [1.0, 0.55, 0.28]
    const qs = [8, 11, 13]
    const freqs = [f1, f2, f3]
    const formantNodes = freqs.map((fr, i) => {
      const bp = ctx.createBiquadFilter()
      bp.type = 'bandpass'; bp.frequency.value = fr; bp.Q.value = qs[i]
      const g = ctx.createGain(); g.gain.value = amps[i]
      osc.connect(bp); bp.connect(g); g.connect(master)
      return { bp, g }
    })
    // 로우패스로 톱니 성문원의 거친 고역을 눌러 소리를 부드럽게 한다.
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'; lp.frequency.value = 3800; lp.Q.value = 0.7
    master.connect(lp); lp.connect(ctx.destination)
    osc.start()
    ctxRef.current = ctx
    nodesRef.current = { osc, formants: formantNodes, master }
    return true
  }, [formants, pos, round])

  // 포먼트를 부드럽게 갱신
  const applyFormants = useCallback((p, r) => {
    const n = nodesRef.current, ctx = ctxRef.current
    if (!n || !ctx) return
    const fs = formants(p, r)
    const t = ctx.currentTime
    n.formants.forEach((fn, i) => fn.bp.frequency.setTargetAtTime(fs[i], t, 0.02))
  }, [formants])

  const start = useCallback(() => {
    if (!ensureAudio()) return
    ctxRef.current.resume?.()
    const n = nodesRef.current, ctx = ctxRef.current
    applyFormants(pos, round)
    n.master.gain.cancelScheduledValues(ctx.currentTime)
    n.master.gain.setTargetAtTime(volRef.current, ctx.currentTime, 0.02)  // 페이드 인(볼륨 반영)
    setOn(true)
  }, [ensureAudio, applyFormants, pos, round])

  const stop = useCallback(() => {
    const n = nodesRef.current, ctx = ctxRef.current
    if (n && ctx) n.master.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.03)
    setOn(false)
  }, [])

  // 좌표 갱신 시 포먼트 반영 + 가장 가까운 모음 표시
  useEffect(() => {
    if (on) applyFormants(pos, round)
    let best = null, bd = 1e9
    const [f1, f2] = formants(pos, round)
    for (const v of VOWELS) {
      // 로그 주파수 거리(지각적으로 균형)
      const d = Math.abs(Math.log(f1 / v.f1)) + Math.abs(Math.log(f2 / v.f2)) + Math.abs(v.round - round) * 0.4
      if (d < bd) { bd = d; best = v }
    }
    setNearest(bd < 0.33 ? best : null)
  }, [pos, round, on, applyFormants, formants])

  // 혀 위치(전후=x, 고저=y)·원순 → 성도 단면 파라미터. 전설·고모음=혀끝↑, 후설·고모음=혀뒤↑, 저모음=개구↑.
  useEffect(() => {
    artRef.current = {
      jaw: clamp(pos.y, 0, 1),
      round: clamp(round, 0, 1),
      tip: clamp((1 - pos.x) * (1 - pos.y), 0, 1),
      back: clamp(pos.x * (1 - pos.y), 0, 1),
      close: 0,
    }
  }, [pos, round])

  // 볼륨 변경 → 즉시 반영(발성 중이면 마스터 게인 조정)
  useEffect(() => {
    volRef.current = vol
    const n = nodesRef.current, ctx = ctxRef.current
    if (on && n && ctx) n.master.gain.setTargetAtTime(vol, ctx.currentTime, 0.02)
  }, [vol, on])

  useEffect(() => () => {
    try { ctxRef.current?.close?.() } catch (_) {}
    try { audioRef.current?.pause() } catch (_) {}
  }, [])

  // 목표 모음: 고른 것이 있으면 그것, 없으면 지금 가장 가까운 모음(없으면 목표 없음)
  const targetKo = picked || nearest?.ko || null
  const targetId = targetKo ? VOWEL_IDS[targetKo] : null

  // VTL 합성음 재생. WebAudio 발성과 겹치지 않게 발성 중이면 먼저 멈춘다. 볼륨 조절값을 따른다.
  const playTarget = useCallback(() => {
    if (!targetId) return
    if (on) stop()
    try { audioRef.current?.pause() } catch (_) {}
    const a = new Audio(vtlWavUrl(targetId))
    a.volume = clamp(volRef.current / 0.7, 0, 1)
    a.onended = () => setPlaying(false)
    a.onerror = () => setPlaying(false)
    audioRef.current = a
    setPlaying(true)
    a.play().catch(() => setPlaying(false))
  }, [targetId, on, stop])

  // 포인터 → 정규화 좌표
  const posFromEvent = (e) => {
    const r = padRef.current.getBoundingClientRect()
    const cx = (e.touches ? e.touches[0].clientX : e.clientX) - r.left
    const cy = (e.touches ? e.touches[0].clientY : e.clientY) - r.top
    return { x: clamp(cx / r.width, 0, 1), y: clamp(cy / r.height, 0, 1) }
  }
  const onDown = (e) => { draggingRef.current = true; setPos(posFromEvent(e)); if (!on) start() ; e.preventDefault() }
  const onMove = (e) => { if (draggingRef.current) setPos(posFromEvent(e)) }
  const onUp = () => { draggingRef.current = false }

  // 키보드 조작(접근성): 화살표=혀 위치, [ ]=입술 원순, 스페이스/엔터=발성 토글
  const onKey = (e) => {
    const s = 0.05
    const k = e.key
    if (k === 'ArrowLeft') setPos((p) => ({ ...p, x: clamp(p.x - s, 0, 1) }))
    else if (k === 'ArrowRight') setPos((p) => ({ ...p, x: clamp(p.x + s, 0, 1) }))
    else if (k === 'ArrowUp') setPos((p) => ({ ...p, y: clamp(p.y - s, 0, 1) }))
    else if (k === 'ArrowDown') setPos((p) => ({ ...p, y: clamp(p.y + s, 0, 1) }))
    else if (k === '[') setRound((r) => clamp(r - s, 0, 1))
    else if (k === ']') setRound((r) => clamp(r + s, 0, 1))
    else if (k === ' ' || k === 'Enter') { on ? stop() : start() }
    else return
    e.preventDefault()
  }

  useEffect(() => {
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp) }
  }, [on])

  if (!supported) {
    return <div className="p-3 text-sm text-gray-500 bg-gray-50 rounded-lg">이 브라우저는 오디오 합성을 지원하지 않습니다.</div>
  }

  const [f1, f2] = formants(pos, round)

  // 색의 뜻은 성도 단면과 같다: 트랙색 = 지금 소리(학습자), 초록 = 목표 모음.
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-bold text-gray-800">성도 실험실 <span className="ml-1 font-normal text-gray-500">혀를 움직여 소리를 만들어 보세요</span></div>
        <button onClick={on ? stop : start}
          className={`px-3 py-1 rounded-lg border-2 text-sm font-semibold ${on ? 'border-track bg-white text-track' : 'border-track bg-track text-white hover:bg-track-hover'}`}>
          {on ? '■ 멈춤' : '▶ 발성'}
        </button>
      </div>

      <div className="grid items-start gap-3 md:grid-cols-2">
        {/* 모음 사각도(vowel chart): 위=고모음, 왼쪽=전설 */}
        <div ref={padRef} onPointerDown={onDown} onKeyDown={onKey}
          tabIndex={0} role="application"
          aria-label={`성도 조음 조작판. 화살표키로 혀 위치, 대괄호로 입술 원순, 스페이스로 발성. 지금 소리 ${nearest ? nearest.ko : '모음 사이'}, F1 ${Math.round(f1)} F2 ${Math.round(f2)} 헤르츠.`}
          className="relative w-full rounded-lg border border-line bg-surface-muted cursor-crosshair select-none touch-none focus:outline-none focus:ring-2 focus:ring-primary-300"
          style={{ aspectRatio: '4 / 3' }}>
          {/* 축 라벨 */}
          <span className="absolute left-1 top-1 text-[10px] text-gray-400">혀 앞·높음 (ㅣ)</span>
          <span className="absolute right-1 top-1 text-[10px] text-gray-400">혀 뒤·높음 (ㅜ)</span>
          <span className="absolute left-1 bottom-1 text-[10px] text-gray-400">혀 앞·낮음</span>
          <span className="absolute right-1 bottom-1 text-[10px] text-gray-400">혀 뒤·낮음</span>
          {/* 모음 목표 마커 */}
          {VOWELS.map((v) => {
            const x = f2ToX(v.f2) * 100, y = f1ToY(v.f1) * 100
            const hit = nearest && nearest.ko === v.ko
            const isTarget = targetKo === v.ko
            return (
              <div key={v.ko}
                className={`absolute -translate-x-1/2 -translate-y-1/2 flex items-center justify-center rounded-full text-xs font-bold transition-all ${hit ? 'bg-good text-white scale-125 shadow' : isTarget ? 'bg-white text-good-text border-2 border-good' : 'bg-white/80 text-gray-600 border border-gray-300'}`}
                style={{ left: `${x}%`, top: `${y}%`, width: 26, height: 26 }}>
                {v.ko}{v.round ? '°' : ''}
              </div>
            )
          })}
          {/* 현재 혀 위치 */}
          <div className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-track border-2 border-white shadow-lg pointer-events-none"
            style={{ left: `${pos.x * 100}%`, top: `${pos.y * 100}%`, width: 18, height: 18, opacity: on ? 1 : 0.6 }} />
        </div>

        {/* 성도 단면(E-6): 지금 F1·F2에서 고른 VTL 형상(색칠)과 목표 모음(점선). 자산을 못 받으면 예전 도식 */}
        <div className="rounded-lg border border-line p-2">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-xs font-bold text-ink">성도 단면</p>
            <p className="text-[10px] text-ink-faint">VocalTractLab으로 미리 계산</p>
          </div>
          <VocalTractVTL className="mt-1" phoneme={targetId} estimate={{ f1, f2, round }} legend targetLabel={targetKo || ''}
            fallback={<div className="mt-1 h-24 rounded-lg bg-slate-900/95 p-1"><VocalTract visemeId={15} articulationRef={artRef} /></div>} />
          <div className="mt-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="목표 모음 고르기">
            <span className="mr-0.5 text-[11px] text-ink-muted">목표</span>
            {VOWELS.map((v) => {
              const active = targetKo === v.ko
              return (
                <button key={v.ko} type="button" aria-pressed={picked === v.ko}
                  onClick={() => setPicked((p) => (p === v.ko ? null : v.ko))}
                  className={`h-7 min-w-7 rounded-10 border-2 px-1.5 text-xs font-bold transition-colors ${active ? 'border-good bg-good-tint text-good-text' : 'border-line bg-white text-ink-muted hover:border-primary-300'}`}>
                  {v.ko}
                </button>
              )
            })}
            <button type="button" onClick={playTarget} disabled={!targetId}
              className="ml-auto h-7 rounded-10 border-2 border-line bg-white px-2 text-xs font-bold text-ink-muted transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50">
              {playing ? '재생 중' : `${targetKo ? `${targetKo} ` : ''}합성음 듣기`}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] leading-snug text-ink-faint">
            {picked ? '고른 모음이 목표예요. 한 번 더 누르면 가장 가까운 모음을 따라가요.' : '목표를 고르지 않으면 가장 가까운 모음을 목표로 보여줘요.'}
          </p>
        </div>
      </div>

      {/* 입술 원순 */}
      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-gray-500 w-16">입술 원순</span>
        <input type="range" min="0" max="1" step="0.01" value={round}
          onChange={(e) => setRound(parseFloat(e.target.value))} className="flex-1 accent-primary-500" />
        <span className="text-xs text-gray-400 w-10 text-right">{Math.round(round * 100)}%</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <span className="text-xs text-gray-500 w-16">볼륨</span>
        <input type="range" min="0" max="0.7" step="0.01" value={vol}
          onChange={(e) => setVol(parseFloat(e.target.value))} className="flex-1 accent-gray-400" />
        <span className="text-xs text-gray-400 w-10 text-right">{Math.round(vol * 143)}%</span>
      </div>

      {/* 읽기값 */}
      <div className="mt-2 flex items-center justify-between text-xs">
        <div className="text-gray-500">F1 <b className="text-gray-700">{Math.round(f1)}</b> · F2 <b className="text-gray-700">{Math.round(f2)}</b> Hz</div>
        <div>
          {nearest
            ? <span className="text-good-text font-semibold">지금 소리: “{nearest.ko}”{nearest.round ? ' (원순)' : ''}</span>
            : <span className="text-gray-400">모음 사이 소리</span>}
        </div>
      </div>
      <p className="mt-1.5 text-[11px] leading-snug text-gray-400">
        ㅗ·ㅜ는 입술 원순을 함께 올려야 제 소리가 나요. 발성 소리는 공명(F1·F2)만 흉내 낸 근사 합성이고,
        성도 단면과 합성음은 VocalTractLab으로 미리 계산했어요. 같은 소리를 내는 혀 모양은 여러 가지라 단면의 혀는 한 가지 예시예요.
      </p>
    </div>
  )
}
