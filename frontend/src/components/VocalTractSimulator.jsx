import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * 성도 시뮬레이터 (계획서 E '인터랙티브 조음 교구').
 * 혀 위치(전후=F2, 고저=F1)와 입술 원순을 조작하면 성도 공명(포먼트)이 바뀌어 소리가
 * 실시간으로 변한다. 보이지 않는 조음(혀·성도 모양)과 소리의 관계를 귀로 직접 잇게 한다.
 *
 * 구현: 브라우저 WebAudio 포먼트 합성(source-filter). VocalTractLab(데스크톱)을 웹으로
 * 옮기는 대신, 성도를 3개 공명(F1~F3)으로 근사한다. 성문원(성대 진동)을 톱니 오실레이터로,
 * 성도 공명을 병렬 대역통과 필터 3개로 모델링한다. GPU·서버 불필요.
 *
 * 정직: 이는 성도의 '포먼트 근사'이지 완전한 파동관 모델(Kelly-Lochbaum)이 아니다. 모음의
 * 혀 위치↔소리 관계를 가르치는 데 적합하며, 자음의 순간 폐쇄·마찰은 다루지 않는다.
 */

// F1(혀 높이): 위(고모음)=낮은 F1 ~ 아래(저모음)=높은 F1
const F1_LO = 250, F1_HI = 850
// F2(혀 전후): 왼쪽(전설)=높은 F2 ~ 오른쪽(후설)=낮은 F2
const F2_HI = 2500, F2_LO = 750
const F3_BASE = 2650

// 한국어 단모음 목표 — (F1, F2) 대략치(성인 남성 기준, Hz). round=원순 필요.
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

  const ctxRef = useRef(null)
  const nodesRef = useRef(null)                 // {osc, formants:[{bp,g}], master}
  const draggingRef = useRef(false)
  const padRef = useRef(null)

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

  // 볼륨 변경 → 즉시 반영(발성 중이면 마스터 게인 조정)
  useEffect(() => {
    volRef.current = vol
    const n = nodesRef.current, ctx = ctxRef.current
    if (on && n && ctx) n.master.gain.setTargetAtTime(vol, ctx.currentTime, 0.02)
  }, [vol, on])

  useEffect(() => () => { try { ctxRef.current?.close?.() } catch (_) {} }, [])

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

  // 키보드 조작(접근성) — 화살표=혀 위치, [ ]=입술 원순, 스페이스/엔터=발성 토글
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

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-bold text-gray-800">성도 실험실 <span className="font-normal text-gray-500">— 혀를 움직여 소리를 만들어 보세요</span></div>
        <button onClick={on ? stop : start}
          className={`px-3 py-1 rounded-lg text-sm font-semibold ${on ? 'bg-rose-500 text-white' : 'bg-sky-600 text-white'}`}>
          {on ? '■ 멈춤' : '▶ 발성'}
        </button>
      </div>

      {/* 모음 사각도(vowel chart): 위=고모음, 왼쪽=전설 */}
      <div ref={padRef} onPointerDown={onDown} onKeyDown={onKey}
        tabIndex={0} role="application"
        aria-label={`성도 조음 조작판. 화살표키로 혀 위치, 대괄호로 입술 원순, 스페이스로 발성. 지금 소리 ${nearest ? nearest.ko : '모음 사이'}, F1 ${Math.round(f1)} F2 ${Math.round(f2)} 헤르츠.`}
        className="relative w-full rounded-lg bg-gradient-to-br from-sky-50 to-indigo-50 border border-sky-100 cursor-crosshair select-none touch-none focus:outline-none focus:ring-2 focus:ring-sky-500"
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
          return (
            <div key={v.ko}
              className={`absolute -translate-x-1/2 -translate-y-1/2 flex items-center justify-center rounded-full text-xs font-bold transition-all ${hit ? 'bg-emerald-500 text-white scale-125 shadow' : 'bg-white/80 text-gray-600 border border-gray-300'}`}
              style={{ left: `${x}%`, top: `${y}%`, width: 26, height: 26 }}>
              {v.ko}{v.round ? '°' : ''}
            </div>
          )
        })}
        {/* 현재 혀 위치 */}
        <div className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-500 border-2 border-white shadow-lg pointer-events-none"
          style={{ left: `${pos.x * 100}%`, top: `${pos.y * 100}%`, width: 18, height: 18, opacity: on ? 1 : 0.6 }} />
      </div>

      {/* 입술 원순 */}
      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-gray-500 w-16">입술 원순</span>
        <input type="range" min="0" max="1" step="0.01" value={round}
          onChange={(e) => setRound(parseFloat(e.target.value))} className="flex-1 accent-sky-600" />
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
            ? <span className="text-emerald-600 font-semibold">지금 소리: “{nearest.ko}”{nearest.round ? ' (원순)' : ''}</span>
            : <span className="text-gray-400">모음 사이 소리</span>}
        </div>
      </div>
      <p className="mt-1.5 text-[11px] leading-snug text-gray-400">
        ㅗ·ㅜ는 입술 원순을 함께 올려야 제 소리가 납니다. 성도를 공명(F1·F2)으로 근사한 합성이라 모음 조음↔소리 관계 학습용입니다.
      </p>
    </div>
  )
}
