import { useEffect, useMemo, useRef, useState } from 'react'
import {
  loadVtlShapes, loadVtlGrid, phonemeById, estimateOutline, part, segment, tonguePolygon, centroid,
  velicPort, toPoints,
} from '../lib/vtlShapes'

/**
 * VocalTractLab 정중시상 단면 (계획서 E-6).
 * scripts/vtl_build_assets.py가 VTL로 미리 계산한 윤곽(public/vtl/)을 SVG로 그린다. 앱은 VTL을
 * 호출하지 않는다. 두 가지를 그릴 수 있다.
 *   phoneme   음소 하나의 목표 형상(shapes.json). estimate가 있으면 점선으로 겹친다.
 *   estimate  {f1, f2, round}: 학습자 포먼트에서 고른 격자 상태(추정 조음). 혀를 색칠해 그린다.
 * 색은 세 가지 뜻만 쓴다: 회색 = 움직이지 않는 틀(입천장·인두벽), 트랙색 = 지금 그리는 조음(혀·입술·
 * 연구개), 초록 점선 = 목표. 자산은 이 컴포넌트가 처음 보일 때만 받는다(lib/vtlShapes 지연 로더).
 * variant="dark"는 VocalTract.jsx 도식과 같은 색으로 어두운 작은 패널에 넣을 때 쓴다(글자 없음).
 */

// 보이는 범위(좌표 단위 0.01 cm). 입천장 위 글자 자리부터 후두덮개까지. 아래 후두는 잘린다.
const VIEW = { x: 20, y: 0, w: 1220, h: 930 }

const LIGHT = {
  frame: 'var(--ink-faint)',
  main: 'var(--track)',
  mainFill: 'var(--track-tint)',
  target: 'var(--good)',
  label: 'var(--ink-muted)',
}
// VocalTract.jsx 도식의 색(어두운 패널)
const DARK = {
  frame: '#7f8ea3',
  main: '#c98b7a',
  mainFill: '#d96a6a',
  tongueStroke: '#a94b4b',
  target: '#9fb0c3',
  label: '#9fb0c3',
}

function prefersReducedMotion() {
  if (typeof window === 'undefined') return true
  return document.documentElement.classList.contains('a11y-reduce-motion')
    || !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

const sameShape = (a, b) => a && b && a.length === b.length && a.every((p, k) => p.length === b[k].length)

// 윤곽을 목표 쪽으로 매 프레임 30%씩 옮겨, 격자·음소가 바뀔 때 뚝 끊기지 않게 한다.
function useEasedOutline(target, animate) {
  const [cur, setCur] = useState(target)
  const curRef = useRef(target)
  useEffect(() => {
    if (!target) { curRef.current = null; setCur(null); return undefined }
    if (!animate || !sameShape(curRef.current, target) || prefersReducedMotion()) {
      curRef.current = target
      setCur(target)
      return undefined
    }
    let raf = 0
    const step = () => {
      let maxd = 0
      const next = curRef.current.map((poly, k) => poly.map((v, j) => {
        const t = target[k][j]
        const nv = v + (t - v) * 0.3
        const d = Math.abs(t - nv)
        if (d > maxd) maxd = d
        return nv
      }))
      if (maxd < 0.6) {
        curRef.current = target
        setCur(target)
        return
      }
      curRef.current = next
      setCur(next)
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, animate])
  return cur
}

function useVtlAssets(needGrid) {
  const [state, setState] = useState({ status: 'loading', shapes: null, grid: null })
  useEffect(() => {
    let alive = true
    Promise.all([loadVtlShapes(), needGrid ? loadVtlGrid() : Promise.resolve(null)])
      .then(([shapes, grid]) => { if (alive) setState({ status: 'ready', shapes, grid }) })
      .catch(() => { if (alive) setState({ status: 'error', shapes: null, grid: null }) })
    return () => { alive = false }
  }, [needGrid])
  return state
}

// 그림의 실제 폭(CSS px). 부위 글자를 화면에서 일정한 크기로 두려고 잰다.
function useRenderedWidth(ref) {
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver((entries) => {
      const cw = entries[0]?.contentRect?.width
      if (cw) setW(cw)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}

export default function VocalTractVTL({
  phoneme = null,
  estimate = null,
  variant = 'light',
  labels = true,
  labelPx = 11,
  legend = false,
  caption = false,
  animate = true,
  targetLabel = '',
  className = '',
  fallback = null,
}) {
  const hasEstimate = !!estimate && Number.isFinite(estimate.f1) && Number.isFinite(estimate.f2)
  const { status, shapes, grid } = useVtlAssets(hasEstimate)
  const dark = variant === 'dark'

  const target = useMemo(() => (shapes && phoneme ? phonemeById(shapes, phoneme) : null), [shapes, phoneme])
  const est = useMemo(() => {
    if (!hasEstimate || !grid) return null
    return estimateOutline(grid, estimate.f1, estimate.f2, { round: estimate.round ?? null, k: 3 })
  }, [hasEstimate, grid, estimate?.f1, estimate?.f2, estimate?.round])

  // 주 윤곽: 추정이 있으면 추정, 없으면 음소 자체. 추정이 있을 때만 음소를 점선 목표로 겹친다.
  const mainTarget = hasEstimate ? (est?.outline || null) : (target?.o || null)
  const overlayTarget = hasEstimate && target ? target.o : null
  const main = useEasedOutline(mainTarget, animate)
  const overlay = useEasedOutline(overlayTarget, animate)

  if (status === 'error') {
    return fallback || <div className={`rounded-lg bg-surface-muted p-3 text-xs text-ink-faint ${className}`}>성도 단면을 불러오지 못했어요.</div>
  }
  if (status === 'loading' || !main) {
    return <div className={`w-full animate-pulse rounded-lg ${dark ? 'bg-slate-800/60' : 'bg-surface-muted'} ${className}`}
      style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }} aria-busy="true" />
  }
  return (
    <TractFigure meta={shapes} main={main} overlay={overlay} target={target} hasEstimate={hasEstimate}
      variant={variant} labels={labels} labelPx={labelPx} legend={legend} caption={caption}
      targetLabel={targetLabel} className={className} />
  )
}

/** 그리기만 하는 부분(자산·애니메이션 없음). 윤곽을 직접 받아 SVG를 만든다. */
export function TractFigure({ meta, main, overlay = null, target = null, hasEstimate = false, variant = 'light',
  labels = true, labelPx = 11, legend = false, caption = false, targetLabel = '', className = '' }) {
  const figRef = useRef(null)
  const width = useRenderedWidth(figRef)
  const dark = variant === 'dark'
  const C = dark ? DARK : LIGHT
  const sw = dark ? 2.4 : 1                  // 작은 어두운 패널은 선을 굵게
  // 부위 글자: 화면에서 labelPx(CSS px) 안팎이 되도록 좌표 단위로 바꾼다. 폭을 모르면(첫 그림) 40.
  // 그림이 170 px보다 좁으면 글자가 부위를 가려 빼고, 음소 이름(caption)과 설명에 맡긴다.
  const fs = width ? Math.min(80, Math.max(34, (labelPx * VIEW.w) / width)) : 40
  const showLabels = labels && !dark && (!width || width >= 170)
  const mainVelum = hasEstimate ? 0 : (target?.velum || 0)
  const name = target ? (target.kind === 'vowel' || target.kind === 'consonant' ? target.ko : '') : ''
  const aria = hasEstimate
    ? `성도 단면. 색칠한 혀는 지금 소리에서 추정한 모양이에요.${overlay ? ` 점선은 목표 ${targetLabel || name}의 모양이에요.` : ''}`
    : `성도 단면. ${name ? `${name} 소리를 낼 때` : '쉬는 자세의'} 혀·입술·연구개 모양이에요.`

  return (
    <figure ref={figRef} className={`m-0 ${className}`}>
      <svg viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`} className="block h-auto w-full" role="img" aria-label={aria}>
        <Tract meta={meta} o={main} C={C} sw={sw} dark={dark} velum={mainVelum}
          overlay={overlay ? <TargetOverlay meta={meta} o={overlay} C={C} sw={sw} velum={target?.velum || 0} /> : null} />
        {showLabels && <Labels meta={meta} o={main} C={C} nasal={mainVelum > 0} fs={fs} />}
      </svg>
      {caption && !dark && target && !hasEstimate && (
        <figcaption className="mt-1 text-center text-sm font-bold leading-tight text-ink">
          {target.ko}
          {target.velum > 0 && <span className="ml-1 text-[11px] font-medium text-track">연구개 내림</span>}
        </figcaption>
      )}
      {/* 범례는 추정 그림에만(음소 이름 caption과 함께 나오지 않는다) */}
      {legend && !dark && hasEstimate && (
        <figcaption className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] leading-tight text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-3.5 rounded-sm border-2 border-track bg-track-tint" aria-hidden="true" />
            지금 소리(추정)
          </span>
          {overlay && (
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block w-4 border-t-2 border-dashed border-good" aria-hidden="true" />
              목표 {targetLabel || name}
            </span>
          )}
        </figcaption>
      )}
    </figure>
  )
}

const polyline = (flat, stroke, width, extra = {}) => (
  <polyline points={toPoints(flat)} fill="none" stroke={stroke} strokeWidth={width}
    strokeLinecap="round" strokeLinejoin="round" {...extra} />
)

// 그리는 순서: 혀 면 → 회색 틀 → (목표 점선) → 혀 표면·입술·연구개 실선. 목표가 지금 모양과 겹치는
// 곳은 실선이 덮고, 다른 곳에서만 점선이 보인다.
function Tract({ meta, o, C, sw, dark, velum, overlay = null }) {
  return (
    <g>
      {/* 혀 면: 혀 표면과 구강 바닥 사이. 아랫변은 회색 바닥선이 그린다. */}
      <polygon points={toPoints(tonguePolygon(meta, o))} fill={C.mainFill} fillOpacity={dark ? 0.85 : 1} stroke="none" />
      <g opacity={0.55}>
        {polyline(part(meta, o, 'wall'), C.frame, 5 * sw)}
        {polyline(part(meta, o, 'larynx'), C.frame, 5 * sw)}
        {polyline(part(meta, o, 'epiglottis'), C.frame, 5 * sw)}
      </g>
      {polyline(part(meta, o, 'upper'), C.frame, 6 * sw)}
      {polyline(part(meta, o, 'lower'), C.frame, 6 * sw)}
      {overlay}
      {polyline(part(meta, o, 'tongue'), dark ? C.tongueStroke : C.main, 7 * sw)}
      {polyline(segment(meta, o, 'upperLip'), C.main, 8 * sw)}
      {polyline(segment(meta, o, 'lowerLip'), C.main, 8 * sw)}
      {polyline(segment(meta, o, 'velum'), C.main, 8 * sw)}
      {polyline(part(meta, o, 'uvula'), C.main, 7 * sw)}
      {velum > 0 && <NasalArrow meta={meta} o={o} color={C.main} sw={sw} />}
    </g>
  )
}

function TargetOverlay({ meta, o, C, sw, velum }) {
  const dash = { strokeDasharray: `${18 * sw} ${13 * sw}` }
  const line = (flat) => polyline(flat, C.target, 7 * sw, dash)
  return (
    <g>
      {line(part(meta, o, 'tongue'))}
      {line(segment(meta, o, 'upperLip'))}
      {line(segment(meta, o, 'lowerLip'))}
      {line(segment(meta, o, 'lowerTeeth'))}
      {line(segment(meta, o, 'velum'))}
      {line(part(meta, o, 'uvula'))}
      {velum > 0 && <NasalArrow meta={meta} o={o} color={C.target} sw={sw} dashed />}
    </g>
  )
}

// 연구개가 내려가 코로 공기가 나가는 길(비음). 목젖과 인두벽 사이에서 위로.
function NasalArrow({ meta, o, color, sw, dashed = false }) {
  const [x, y] = velicPort(meta, o)
  const y0 = y + 30
  const y1 = y - 150
  return (
    <g stroke={color} fill="none" strokeWidth={7 * sw} strokeLinecap="round" strokeLinejoin="round"
      strokeDasharray={dashed ? `${18 * sw} ${13 * sw}` : undefined}>
      <line x1={x} y1={y0} x2={x} y2={y1} />
      <polyline points={`${x - 26},${y1 + 34} ${x},${y1} ${x + 26},${y1 + 34}`} />
    </g>
  )
}

function Labels({ meta, o, C, nasal, fs = 40 }) {
  const k = fs / 40                           // 글자 크기에 맞춰 부위와의 간격도 늘린다
  const text = (x, y, s, anchor = 'middle', fill = C.label, weight = 500) => (
    <text x={x} y={y} fontSize={fs} fill={fill} textAnchor={anchor} fontWeight={weight}
      style={{ fontFamily: 'inherit' }}>{s}</text>
  )
  const palate = segment(meta, o, 'palate')
  let px = 0
  let py = Infinity
  for (let i = 0; i < palate.length; i += 2) if (palate[i + 1] < py) { py = palate[i + 1]; px = palate[i] }
  const velum = segment(meta, o, 'velum')
  const vx = velum[6]
  const vy = velum[7]
  const up = segment(meta, o, 'upperLip')
  const lo = segment(meta, o, 'lowerLip')
  const xs = [...up.filter((_, i) => i % 2 === 0), ...lo.filter((_, i) => i % 2 === 0)]
  const loY = Math.max(...lo.filter((_, i) => i % 2 === 1))
  const lipX = (Math.min(...xs) + Math.max(...xs)) / 2
  const [tx, ty] = centroid(tonguePolygon(meta, o))
  const [nx, ny] = velicPort(meta, o)
  // 연구개 글자는 연구개 곡선 위(비강 쪽 빈자리), 코로 글자는 통로 화살표 끝 위에 둔다.
  return (
    <g>
      {text(px, py - 22 * k, '입천장')}
      {text(vx + 40 * k, vy - 50 * k, '연구개')}
      {text(lipX, loY + 58 * k, '입술')}
      {text(tx, ty + 14 * k, '혀', 'middle', C.main, 700)}
      {nasal && text(nx, ny - 150 - 22 * k, '코로', 'middle', C.main, 700)}
    </g>
  )
}
