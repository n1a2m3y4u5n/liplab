import { useEffect, useRef } from 'react'

/**
 * 성도(측면 단면) 도식 — 계획서 E '성도 시뮬레이터' lite.
 * viseme(1~15)를 조음 파라미터(혀끝·혀뒤·원순·개구·폐쇄)로 바꿔, 겉으로 안 보이는
 * 혀·입술·턱의 움직임을 측면 단면으로 실시간 표시한다(독화 교육). GPU 불필요, 순수 SVG.
 */
// viseme → 조음 파라미터 {tip: 혀끝 들림, back: 혀뒤 들림, round: 원순, jaw: 개구, close: 양순폐쇄}
const VIS_ART = {
  1: { close: 1.0, jaw: 0.05 }, 11: { close: 0.92, jaw: 0.05 },     // 양순 ㅂㅍㅁ
  2: { jaw: 0.92 }, 5: { jaw: 0.44 }, 8: { jaw: 0.30 },             // 개방/중설/성문
  3: { jaw: 0.16 },                                                  // 전설 ㅣㅔ (혀 앞·평평)
  4: { jaw: 0.20, round: 0.9 }, 9: { jaw: 0.34, round: 0.55 },       // 원순/이중
  6: { jaw: 0.24, tip: 0.95 }, 12: { jaw: 0.22, tip: 0.7 },          // 치경 ㄷㄴㄹㅅ
  7: { jaw: 0.24, back: 0.85 }, 13: { jaw: 0.20, back: 0.55 },       // 연구개 ㄱㅋㅇ
  10: { jaw: 0.16, tip: 0.4 },                                       // 경구개 ㅈㅊ
  14: { jaw: 0.04 }, 15: { jaw: 0.02 },                              // 휴지/중립
}
const KO = { 1: '양순 폐쇄', 11: '양순 폐쇄', 4: '원순', 9: '원순', 6: '혀끝(치경)', 12: '혀끝(치경)', 7: '혀뒤(연구개)', 13: '혀뒤(연구개)', 10: '경구개', 2: '개방', 5: '중설', 8: '성문', 3: '전설' }
const clamp = (v) => (v < 0 ? 0 : v > 1 ? 1 : v)

export default function VocalTract({ visemeId = 15 }) {
  const tongueRef = useRef(null)
  const jawRef = useRef(null)
  const lipLRef = useRef(null)
  const lblRef = useRef(null)
  const curRef = useRef({ tip: 0, back: 0, round: 0, jaw: 0.02, close: 0 })
  const targetRef = useRef({ tip: 0, back: 0, round: 0, jaw: 0.02, close: 0 })

  // 목표 갱신(viseme 바뀔 때)
  useEffect(() => {
    const a = VIS_ART[visemeId] || VIS_ART[15]
    targetRef.current = { tip: a.tip || 0, back: a.back || 0, round: a.round || 0, jaw: a.jaw || 0, close: a.close || 0 }
    if (lblRef.current) lblRef.current.textContent = KO[visemeId] || ''
  }, [visemeId])

  // rAF 부드러운 보간 + 도형 갱신
  useEffect(() => {
    let raf
    const tick = () => {
      const c = curRef.current, t = targetRef.current
      for (const k in c) c[k] += (t[k] - c[k]) * 0.25
      const tipX = 62, tipY = 120 - clamp(c.tip) * 34
      const dorX = 120, dorY = 116 - clamp(c.back) * 36
      if (tongueRef.current) tongueRef.current.setAttribute('d',
        `M44,124 Q${tipX},${tipY.toFixed(1)} ${dorX},${dorY.toFixed(1)} Q168,${(dorY + 6).toFixed(1)} 186,126 L186,140 Q110,150 44,140 Z`)
      if (jawRef.current) jawRef.current.setAttribute('transform', `translate(0,${(clamp(c.jaw) * 20 - clamp(c.close) * 6).toFixed(1)})`)
      if (lipLRef.current) { lipLRef.current.setAttribute('x', (41 - clamp(c.round) * 6).toFixed(1)); lipLRef.current.setAttribute('width', (7 - clamp(c.round) * 2).toFixed(1)) }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <svg viewBox="0 0 240 190" className="w-full h-full" role="img" aria-label="성도 단면">
      <path d="M40,20 Q150,8 205,55 Q220,95 200,130 Q205,150 190,165 L120,178 Q60,180 40,150 Z" fill="#0f1622" stroke="#2a3444" strokeWidth="1.5" />
      <path d="M46,86 Q95,66 150,70 Q178,74 190,96" fill="none" stroke="#7f8ea3" strokeWidth="3" strokeLinecap="round" />
      <rect x="41" y="84" width="7" height="10" rx="2" fill="#c98b7a" />
      <rect x="49" y="88" width="4" height="8" rx="1" fill="#eef2f7" />
      <path ref={tongueRef} d="M44,124 Q62,120 120,116 Q168,122 186,126 L186,140 Q110,150 44,140 Z" fill="#d96a6a" stroke="#a94b4b" strokeWidth="1.5" />
      <g ref={jawRef}>
        <rect ref={lipLRef} x="41" y="104" width="7" height="11" rx="2" fill="#c98b7a" />
        <rect x="49" y="104" width="4" height="8" rx="1" fill="#eef2f7" />
        <path d="M40,116 Q70,150 120,150" fill="none" stroke="#7f8ea3" strokeWidth="3" strokeLinecap="round" />
      </g>
      <text ref={lblRef} x="120" y="184" textAnchor="middle" fontSize="12" fill="#9fb0c3"></text>
    </svg>
  )
}
