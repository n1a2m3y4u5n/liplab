import { useId } from 'react'

/**
 * 팀원 마스코트 아바타(9/28 사용자 요청: 개발자 프로필을 마스코트로, 색·표정·모션을 사람마다 다르게).
 * 몸 모양은 DOKA(Figma 372:98 가이드 마스코트)와 같은 경로를 쓰고, 색은 랜딩 마스코트 팔레트(lp-19-* sky·rose·purple·amber·emerald)를
 * 따른다. 표정(face)과 모션(motion)은 index.css의 mascot-* 애니메이션. 눈을 뜬 표정은 서로 다른 박자로 깜빡이고, 마우스를 올리면
 * 폴짝 뛴다(group-hover). '동작 최소화' 설정이면 index.css의 prefers-reduced-motion 규칙이 모션을 멈춘다.
 */
export const PALETTES = {
  purple: ['#C4B5FD', '#A78BFA', '#7D53DE'],
  rose: ['#FDA4AF', '#FB7185', '#EC4899'],
  sky: ['#7DD3FC', '#38BDF8', '#0284C7'],
  emerald: ['#6EE7B7', '#34D399', '#10B981'],
  amber: ['#FDE68A', '#FBBF24', '#F59E0B'],
  cyan: ['#67E8F9', '#22D3EE', '#3B82F6'],
}
const TINT = { purple: '#EFE9FC', rose: '#FFE4E9', sky: '#E0F2FE', emerald: '#D1FAE5', amber: '#FEF3C7', cyan: '#CFFAFE' }

const BODY = 'M5.04 23.1C5.04 11.9659 14.0659 2.94 25.2 2.94H28.56C38.7662 2.94 47.04 11.2138 47.04 21.42V23.94C47.04 35.538 37.638 44.94 26.04 44.94H24.36C13.6899 44.94 5.04 36.2901 5.04 25.62V23.1Z'
const INK = '#0F172A'

function OpenEye({ cx, cy, r = 3.3, look = 0, blink }) {
  return (
    <g className="mascot-eye" style={{ transformOrigin: `${cx}px ${cy}px`, animationDelay: blink }}>
      <circle cx={cx} cy={cy} r={r} fill={INK} />
      <circle cx={cx + look - r * 0.35} cy={cy - r * 0.4} r={r * 0.36} fill="white" />
    </g>
  )
}

function ArcEye({ cx, cy, w = 3.4, up = true }) {
  // 웃는 눈(^) 또는 감은 눈
  const d = up ? `M${cx - w} ${cy + 1.2}Q${cx} ${cy - 3} ${cx + w} ${cy + 1.2}` : `M${cx - w} ${cy - 0.8}Q${cx} ${cy + 2.6} ${cx + w} ${cy - 0.8}`
  return <path d={d} stroke={INK} strokeWidth="2.3" strokeLinecap="round" fill="none" />
}

function Face({ face, blink }) {
  const L = 20.8, R = 31.3, Y = 22.6
  switch (face) {
    case 'wink':
      return (
        <>
          <OpenEye cx={L} cy={Y} blink={blink} />
          <ArcEye cx={R} cy={Y} />
          <path d="M20.4 31.2C22.1 36.3 29.9 36.3 31.7 31.2" stroke="white" strokeOpacity="0.95" strokeWidth="2.56" strokeLinecap="round" fill="none" />
          <path d="M27.4 34.6q1.6 2.4 3.4 0" fill="#FB7185" opacity="0.9" />
        </>
      )
    case 'laugh':
      return (
        <>
          <ArcEye cx={L} cy={Y} />
          <ArcEye cx={R} cy={Y} />
          <path d="M19.6 29.6h12.8c0 5.4-2.9 8.2-6.4 8.2s-6.4-2.8-6.4-8.2Z" fill={INK} />
          <path d="M22.4 35.2q3.6 2.6 7.2 0" fill="#FB7185" />
        </>
      )
    case 'glance':
      return (
        <>
          <OpenEye cx={L} cy={Y} r={3.1} look={1.3} blink={blink} />
          <OpenEye cx={R} cy={Y} r={3.1} look={1.3} blink={blink} />
          <path d="M16.9 17.2q3.4-1.6 6.6-.4M28.4 16.8q3.3-1.2 6.4.6" stroke={INK} strokeWidth="1.7" strokeLinecap="round" fill="none" opacity="0.75" />
          <path d="M22.6 32.1q4.4 2.6 8.4-.6" stroke="white" strokeOpacity="0.95" strokeWidth="2.4" strokeLinecap="round" fill="none" />
        </>
      )
    case 'surprised':
      return (
        <>
          <OpenEye cx={L} cy={Y} r={3.7} blink={blink} />
          <OpenEye cx={R} cy={Y} r={3.7} blink={blink} />
          <path d="M16.6 15.6q3.6-2.4 7.2-.8M28.2 14.8q3.6-1.6 7.2.8" stroke={INK} strokeWidth="1.7" strokeLinecap="round" fill="none" opacity="0.75" />
          <ellipse cx="26" cy="33.2" rx="2.9" ry="3.5" fill={INK} />
        </>
      )
    default:   // grin: 자신 있는 웃음
      return (
        <>
          <OpenEye cx={L} cy={Y} blink={blink} />
          <OpenEye cx={R} cy={Y} blink={blink} />
          <path d="M16.6 16.2q3.6-1.8 7-.6M28.6 15.6q3.4-1.2 7 .6" stroke={INK} strokeWidth="1.7" strokeLinecap="round" fill="none" opacity="0.7" />
          <path d="M19.2 30.2c1.9 6.6 11.8 6.6 13.7 0Z" fill="white" fillOpacity="0.95" />
        </>
      )
  }
}

export default function MascotAvatar({ palette = 'purple', face = 'grin', motion = 'bob', size = 60, delay = 0, className = '', ring = true }) {
  const uid = useId().replace(/:/g, '')
  const [c1, c2, c3] = PALETTES[palette] || PALETTES.purple
  const blink = `${(delay * 1.7) % 4}s`
  return (
    <span aria-hidden className={`group relative inline-block shrink-0 ${className}`} style={{ width: size, height: size }}>
      {ring && <span className="absolute inset-0 rounded-full" style={{ background: TINT[palette] || TINT.purple }} />}
      <svg viewBox="-2 -4 56 60" className="absolute inset-0 size-full overflow-visible">
        <defs>
          <linearGradient id={`g${uid}`} x1="5" y1="3" x2="40" y2="42" gradientUnits="userSpaceOnUse">
            <stop stopColor={c1} /><stop offset="0.5" stopColor={c2} /><stop offset="1" stopColor={c3} />
          </linearGradient>
          <radialGradient id={`s${uid}`} cx="0.35" cy="0.25" r="0.6">
            <stop stopColor="white" stopOpacity="0.55" /><stop offset="1" stopColor="white" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse className={`mascot-shadow mascot-shadow-${motion}`} cx="26" cy="50.5" rx="13" ry="2.2" fill="#0F0A1F" opacity="0.14"
          style={{ transformOrigin: '26px 50.5px', animationDelay: `${delay}s` }} />
        <g className={`mascot-${motion} group-hover:[animation:mascot-hop_0.6s_ease-out]`} style={{ transformOrigin: '26px 44px', animationDelay: `${delay}s` }}>
          <path d={BODY} fill={`url(#g${uid})`} />
          <path d={BODY} fill={`url(#s${uid})`} />
          <circle cx="12.3" cy="26.2" r="2.6" fill="white" fillOpacity="0.4" />
          <circle cx="39.8" cy="26.2" r="2.6" fill="white" fillOpacity="0.4" />
          <Face face={face} blink={blink} />
        </g>
      </svg>
    </span>
  )
}
