import Logo from '../Logo'
import { DOKA_ASSETS } from '../DokaNode'

const USER = { initial: '게', name: '게스트', streak: 12, xp: '1,240', level: 4 }

const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // DOKA SVG 그림자 여백(DokaNode와 같음)
const ARROW_OVERFLOW = { top: -4, left: -7, width: 'calc(100% + 14px)', height: 'calc(100% + 14px)' }
const area = (key) => ({ 'data-area': key })

// 장면 전환 애니메이션. 담담하게 아래에서 살짝 올라오며 나타난다(300ms).
const KEYFRAMES = '@keyframes gm-rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}'
  + '@keyframes gm-fade{from{opacity:0}to{opacity:1}}'
const RISE = 'animate-[gm-rise_300ms_ease-out_both]'
const FADE = 'animate-[gm-fade_300ms_ease-out_both]'

function MaskIcon({ src, className = '' }) {
  return <span className={`mask-icon ${className}`} style={{ '--icon': `url(${src})` }} />
}

function Avatar({ className = '' }) {
  return (
    <span className={`flex shrink-0 items-center justify-center rounded-full border-2 border-primary-200 bg-primary-100 font-black text-primary-600 ${className}`}>
      {USER.initial}
    </span>
  )
}

// 스탯 한 칸(AppShell Stat과 같은 모양)
function Stat({ icon, box, w = box, h = box, value, className }) {
  return (
    <span className={`inline-flex shrink-0 items-center font-bold leading-figma ${className}`}>
      <span className="flex shrink-0 items-start justify-center" style={{ width: box, height: box }}>
        <img src={icon} alt="" className="max-w-none" style={{ width: w, height: h }} />
      </span>
      {value}
    </span>
  )
}

// ── 3D 아바타 자리: 어두운 무대 + 아래 얼굴 일러스트 ───────────────────────
// 입모양 3가지를 겹쳐 두고 투명도로 바꾼다. '바다' = 닫힘(ㅂ) → 벌림(ㅏ) → 반쯤(ㄷ) → 벌림(ㅏ).
const LIPS = {
  closed: (
    <>
      <path d="M121 101C133 93 148 89 160 94C172 89 187 93 199 101C186 103 173 104 160 104C147 104 134 103 121 101Z" fill="#b65d62" />
      <path d="M121 101C134 104 147 105 160 105C173 105 186 104 199 101C191 115 177 122 160 122C143 122 129 115 121 101Z" fill="#c86f71" />
      <path d="M122 101.5C135 104.5 147 105.5 160 105.5C173 105.5 185 104.5 198 101.5" stroke="#7a3238" strokeWidth="1.6" strokeLinecap="round" fill="none" />
      <ellipse cx="160" cy="114" rx="13" ry="2.4" fill="#fff" opacity="0.22" />
    </>
  ),
  mid: (
    <>
      <path d="M124 98C140 101 180 101 196 98C190 108 176 113 160 113C144 113 130 108 124 98Z" fill="#3a1117" />
      <path d="M132 99.5C146 102 174 102 188 99.5L186.5 104.5C174 106.5 146 106.5 133.5 104.5Z" fill="#f3eee8" />
      <path d="M120 98C132 89 148 85 160 90C172 85 188 89 200 98C188 100 174 101 160 101C146 101 132 100 120 98Z" fill="#b65d62" />
      <path d="M122 99C130 110 144 116 160 116C176 116 190 110 198 99C192 116 178 126 160 126C142 126 128 116 122 99Z" fill="#c86f71" />
      <ellipse cx="160" cy="121.5" rx="12" ry="2.2" fill="#fff" opacity="0.22" />
    </>
  ),
  open: (
    <>
      <path d="M123 96C140 100 180 100 197 96C192 114 177 125 160 125C143 125 128 114 123 96Z" fill="#3a1117" />
      <path d="M131 98.5C146 101.5 174 101.5 189 98.5L187.5 105C174 107.5 146 107.5 132.5 105Z" fill="#f3eee8" />
      <ellipse cx="160" cy="120" rx="21" ry="6.5" fill="#c05e68" />
      <path d="M119 96C131 87 148 83 160 88C172 83 189 87 201 96C188 99 174 100 160 100C146 100 132 99 119 96Z" fill="#b65d62" />
      <path d="M121 97C129 116 144 126 160 126C176 126 191 116 199 97C193 120 178 134 160 134C142 134 127 120 121 97Z" fill="#c86f71" />
      <ellipse cx="160" cy="129.5" rx="12" ry="2.2" fill="#fff" opacity="0.22" />
    </>
  ),
}
const MOUTH_CYCLE = ['closed', 'open', 'mid', 'open']

// talker: 왼쪽 위 가상 화자 이름(앱 TalkerChip과 같은 모양). 독화 레슨에만 붙는다(말하기는 화자를 바꾸지 않는다).
function FaceStage({ mouth = 'open', className = '', talker = null }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl bg-gradient-to-b from-surface-inverse-muted to-surface-inverse shadow-xl ${className}`}>
      <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 size-full">
        <defs>
          <radialGradient id="gm-skin" cx="160" cy="70" r="150" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#f5d2b8" />
            <stop offset="0.55" stopColor="#e8b393" />
            <stop offset="1" stopColor="#c98c6d" />
          </radialGradient>
          <radialGradient id="gm-light" cx="160" cy="60" r="170" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#94a3b8" stopOpacity="0.18" />
            <stop offset="1" stopColor="#94a3b8" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="gm-neck" x1="0" y1="140" x2="0" y2="200" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#b77a5d" />
            <stop offset="1" stopColor="#8f5c46" />
          </linearGradient>
        </defs>
        <rect width="320" height="180" fill="url(#gm-light)" />
        {/* 목 · 얼굴 */}
        <path d="M112 130H208V200H112Z" fill="url(#gm-neck)" />
        <path d="M54 -12C52 58 72 126 118 164C140 181 180 181 202 164C248 126 268 58 266 -12Z" fill="url(#gm-skin)" />
        {/* 턱선 그늘 · 턱 끝 빛 */}
        <path d="M58 30C62 90 84 138 120 164C140 179 180 179 200 164C236 138 258 90 262 30C258 96 236 144 200 168C180 182 140 182 120 168C84 144 62 96 58 30Z" fill="#a8674d" opacity="0.28" />
        <ellipse cx="160" cy="158" rx="22" ry="7" fill="#fff" opacity="0.12" />
        {/* 코 */}
        <path d="M146 -12C146 16 142 34 137 45C134 52 139 59 147 59C151 62 169 62 173 59C181 59 186 52 183 45C178 34 174 16 174 -12Z" fill="#dca283" opacity="0.35" />
        <ellipse cx="160" cy="44" rx="11" ry="8" fill="#f8dcc8" opacity="0.75" />
        <path d="M145 58C149 55 154 55 156 58C153 60 148 60 145 58Z M175 58C171 55 166 55 164 58C167 60 172 60 175 58Z" fill="#8e4f3f" opacity="0.5" />
        {/* 인중 */}
        <path d="M154 62C153 72 152 80 151 86M166 62C167 72 168 80 169 86" stroke="#b97c61" strokeWidth="2.2" strokeLinecap="round" fill="none" opacity="0.35" />
        {Object.entries(LIPS).map(([k, g]) => (
          <g key={k} style={{ opacity: mouth === k ? 1 : 0, transition: 'opacity 140ms ease' }}>{g}</g>
        ))}
        {/* 입꼬리 옆 볼 그늘 */}
        <path d="M108 92C104 108 108 124 116 134M212 92C216 108 212 124 204 134" stroke="#b27456" strokeWidth="3" strokeLinecap="round" fill="none" opacity="0.2" />
      </svg>
      {talker && (
        <span className="absolute left-2 top-2 rounded-full bg-black/45 px-2 py-0.5 text-[11px] font-bold leading-4 text-white/90">{talker}</span>
      )}
    </div>
  )
}

// 재생 중이면 틱마다 입모양을 바꾸고, 멈추면 벌린 입(ㅏ)으로 둔다
const mouthAt = (tick, running) => (running ? MOUTH_CYCLE[tick % MOUTH_CYCLE.length] : 'open')

// ── 학습 경로 노드(DokaNode 에셋, 모바일·데스크톱 크기를 직접 준다) ────────────
const NODE = {
  m: { slot: 56, cur: 64.4, ring: 80, badge: 19, bx: 40, by: 39, badgeSrc: '/ui/lp-232-35-node-check-badge.svg' },
  d: { slot: 76, cur: 87.4, ring: 109, badge: 24, bx: 55, by: 54, badgeSrc: DOKA_ASSETS.read.badge },
}

// glow: 현재 단계 링을 은은하게 깜빡인다(동작 최소화면 index.css 규칙이 멈춘다)
function Node({ status, size = 'm', glow = false }) {
  const z = NODE[size]
  const a = DOKA_ASSETS.read
  const body = status === 'mastered' ? a.done : status === 'skip' ? a.skip : DOKA_ASSETS.locked
  const center = 'absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2'
  return (
    <span className="relative z-[1] block shrink-0" style={{ width: z.slot, height: z.slot }}>
      {status === 'current' ? (
        <>
          <img src={a.ring} alt="" className={`${center} max-w-none ${glow ? 'animate-pulse-slow' : ''}`} style={{ width: z.ring, height: z.ring }} />
          <span className={center} style={{ width: z.cur, height: z.cur }}>
            <img src={a.current} alt="" className="absolute max-w-none" style={OVERFLOW} />
          </span>
        </>
      ) : (
        <img src={body} alt="" className="absolute max-w-none" style={OVERFLOW} />
      )}
      {status === 'mastered' && (
        <span className="absolute" style={{ left: z.bx, top: z.by, width: z.badge, height: z.badge }}>
          <img src={z.badgeSrc} alt="" className="absolute left-[-3px] top-[-2px] h-[calc(100%+6px)] w-[calc(100%+6px)] max-w-none" />
        </span>
      )}
    </span>
  )
}

function Connector({ done, size = 'm' }) {
  const cls = size === 'd' ? 'my-[-8px] h-[58px] w-[6px]' : 'my-[-5px] h-[28px] w-[5px]'
  return <span className={`relative z-0 block shrink-0 rounded-[3px] ${cls} ${done ? 'bg-track' : 'bg-fill-strong'}`} />
}

// 말풍선 꼬리(CurriculumPath TailLeft와 같은 에셋)
function TailLeft({ className = '' }) {
  return (
    <span className={`absolute h-[22px] w-4 ${className}`}>
      <img src="/ui/lp-80-6-tail-face.svg" alt="" className="absolute inset-0 size-full max-w-none" />
      <img src="/ui/lp-80-6-tail-edge.svg" alt="" className="absolute max-w-none" style={{ left: -1, top: -0.825, width: 17.566, height: 23.648 }} />
    </span>
  )
}

function StageArrow({ src, className, style }) {
  return (
    <span {...area('arrows')} className={`absolute ${className}`} style={style}>
      <img src={src} alt="" className="absolute max-w-none" style={ARROW_OVERFLOW} />
    </span>
  )
}

// ── 모바일 셸(AppShell lg 미만): 상단 바 + 본문 + 하단 탭 ─────────────────────
const TABS = [
  { key: 'today', label: '오늘', icon: '/ui/nav-learn.svg' },
  { key: 'learn', label: '학습', icon: '/ui/nav-practice.svg' },
  { key: 'records', label: '기록', icon: '/ui/nav-analytics.svg' },
  { key: 'me', label: '내 정보', icon: '/ui/nav-profile.svg' },
]

function MobileShell({ active, title, children, overlay }) {
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-page text-ink">
      <div className="flex items-center justify-between px-[18px] pb-[14px] pt-4">
        <Logo size={20} />
        <div className="flex items-center gap-3">
          <Stat icon="/ui/stat-flame.svg" box={17} value={USER.streak} className="gap-1 text-[14px] text-stat-streak" />
          <Stat icon="/ui/lp-232-48-star.svg" box={15} w={14.27} h={13.57} value={USER.xp} className="gap-1 text-[14px] text-stat-xp" />
          <Avatar className="size-[30px] text-[13px]" />
        </div>
      </div>
      <div className="flex flex-col gap-3.5 px-[18px] pt-5">
        {title && <p className="text-[25px] font-bold leading-figma tracking-[-0.625px] text-ink">{title}</p>}
        {children}
      </div>
      {overlay}
      <div className="absolute inset-x-0 bottom-0 z-30 flex min-h-[78px] items-center border-t-1.5 border-line bg-white px-2 pt-2.5">
        {TABS.map((t) => (
          <span key={t.key} className={`flex min-w-0 flex-1 flex-col items-center gap-[5px] py-1.5 text-[11px] font-bold leading-figma ${active === t.key ? 'text-track' : 'text-ink-muted'}`}>
            <MaskIcon src={t.icon} className="size-[23px]" />
            {t.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── 01 화면 둘러보기: 데스크톱 전체(사이드바 · 학습 경로 · 오른쪽 패널) ──────────
const SIDE = TABS

function RailTask({ label, cur, total }) {
  return (
    <div className="flex items-center gap-3">
      {cur >= total
        ? <img src="/ui/lp-318-33-checkbox-on.svg" alt="" className="size-[22px] shrink-0" />
        : <span className="size-[22px] shrink-0 rounded-[7px] border-2 border-line" />}
      <span className="min-w-0 flex-1 text-[15px] font-medium leading-figma text-ink-muted">{label}</span>
      <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted">{cur}/{total}</span>
    </div>
  )
}

export { USER, OVERFLOW, ARROW_OVERFLOW, area, KEYFRAMES, RISE, FADE, MaskIcon, Avatar, Stat, LIPS, MOUTH_CYCLE, FaceStage, mouthAt, NODE, Node, Connector, TailLeft, StageArrow, TABS, MobileShell, SIDE, RailTask }
