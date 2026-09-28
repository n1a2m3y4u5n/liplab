import { Fragment, useCallback, useLayoutEffect, useRef, useState } from 'react'
import Logo from '../Logo'
import { DOKA_ASSETS } from '../DokaNode'
import { WatermarkDeco } from '../WatermarkCard'
import { scoreTone } from '../../lib/scoreTone'

/**
 * 사용법 가이드 화면 목업(9/28). 스크린샷 대신 실제 앱 화면을 단순화해 코드로 그린다.
 * 색·반경·글자 크기는 앱과 같은 토큰을 쓰고, 값은 정적 예시(이름 '게스트', 단어 '바다' 등)다.
 * 각 목업은 고정 설계 크기(design)로 그린 뒤 transform scale로 가이드의 사진 상자(w×h)에 맞춰 줄인다.
 * 앱 컴포넌트의 lg: 반응형 클래스는 뷰포트 기준이라 가이드 안에서는 크기가 어긋나므로, 모바일 화면은 모바일 값을 직접 쓴다.
 * 3D 아바타 칸은 WebGL을 띄우지 않고 어두운 무대 위 얼굴 일러스트(FaceStage)로 그린다.
 *
 * 동적 요소
 *  - 영역: 목업 안 요소에 data-area를 달고, 가이드 주석(GROUPS annots의 셋째 값)과 같은 키로 잇는다.
 *    강조 중인 영역은 링을 두르고 나머지는 흰 막으로 살짝 흐린다. 번호 배지는 목업이 가진 영역(MOCKS areas)에만 단다.
 *  - 시연: scene(장면)과 tick(틱 수)을 받아 그린다. 장면 순서는 DEMOS, 재생은 GuideDemo의 useDemo가 맡는다.
 * 안쪽은 장식(aria-hidden, 포인터 막음)이고 스크린리더에는 sr-only 설명을 읽힌다. 안쪽에는 버튼 대신 span·div만 쓴다.
 */

// 예시 값. 레벨 4 = XP 900~1,600 구간(lib/level.js), 1,240이면 340 / 700.
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
    <div className={`relative overflow-hidden rounded-2xl bg-gradient-to-b from-slate-800 to-slate-900 shadow-xl ${className}`}>
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
  { key: 'learn', label: '학습', icon: '/ui/nav-learn.svg' },
  { key: 'practice', label: '연습', icon: '/ui/nav-practice.svg' },
  { key: 'task', label: '과제', icon: '/ui/nav-task.svg' },
  { key: 'review', label: '복습', icon: '/ui/nav-review.svg' },
  { key: 'analysis', label: '분석', icon: '/ui/nav-analytics.svg' },
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
const SIDE = [
  { key: 'learn', label: '학습', icon: '/ui/nav-learn.svg' },
  { key: 'practice', label: '연습', icon: '/ui/nav-practice.svg' },
  { key: 'task', label: '과제', icon: '/ui/nav-task.svg' },
  { key: 'review', label: '복습', icon: '/ui/nav-review.svg' },
  { key: 'analysis', label: '분석', icon: '/ui/nav-analytics.svg' },
  { key: 'profile', label: '프로필', icon: '/ui/nav-profile.svg' },
]

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

function OverviewMock({ motion }) {
  const path = ['mastered', 'mastered', 'current', 'skip']
  return (
    <div className="flex h-full bg-white text-ink">
      {/* 사이드바 */}
      <div className="flex w-[256px] shrink-0 flex-col gap-2 border-r border-line bg-white px-4 pb-6 pt-7">
        <span {...area('logo')} className="self-start"><Logo size={30} /></span>
        <div className="h-5" />
        {SIDE.map((n) => (
          <span key={n.key} className={`side-item ${n.key === 'learn' ? 'side-item-active' : ''}`}>
            <MaskIcon src={n.icon} className="size-6" />
            {n.label}
          </span>
        ))}
      </div>

      {/* 본문: 학습 경로 */}
      <div className="flex min-w-0 flex-1 flex-col px-8 pt-8">
        <div className="mx-auto flex w-full max-w-[752px] flex-col items-center gap-6">
          <div className="flex gap-1 rounded-14 bg-surface-sunken p-1">
            <span className="rounded-10 bg-white px-[26px] py-2.5 text-[15px] font-bold leading-figma text-track shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]">독화</span>
            <span className="rounded-10 px-[26px] py-2.5 text-[15px] font-bold leading-figma text-ink-faint">발화</span>
          </div>
          <div className="flex w-full items-center gap-3.5 rounded-18 border-b-5 border-track-dark bg-track py-5 pl-[26px] pr-5 text-white">
            <div className="flex min-w-0 flex-1 flex-col gap-1 font-bold leading-figma">
              <span className="text-[13px] opacity-[0.85]">독화 · 3단계</span>
              <span className="text-[24px] tracking-[-0.48px]">문장 (상황별)</span>
            </div>
            <span className="shrink-0 rounded-[12px] border-2 border-white/40 bg-white/[0.18] px-[18px] py-3 text-[14px] font-bold leading-figma">가이드</span>
          </div>

          <div className="relative w-full py-2">
            <StageArrow src="/ui/stage-arrow-prev.svg" className="left-[27px] top-1/2 size-11 -translate-y-1/2" />
            <StageArrow src="/ui/stage-arrow-next.svg" className="right-[52px] top-1/2 size-11 -translate-y-1/2" />
            <div className="ml-[130px] flex w-[76px] flex-col items-center">
              {path.map((st, i) => (
                <Fragment key={i}>
                  {i > 0 && <Connector size="d" done={path[i - 1] === 'mastered'} />}
                  <div className="relative">
                    <Node status={st} size="d" glow={motion} />
                    {st === 'current' && (
                      <div className="absolute left-full z-10 ml-[34px] flex w-[360px] flex-col gap-3.5 rounded-20 border-2 border-line bg-white px-6 py-[22px] shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)]"
                        style={{ bottom: 'calc(50% - 37.5px)' }}>
                        <TailLeft className="bottom-[24.5px] left-[-15px]" />
                        <p className="text-[22px] font-bold leading-figma tracking-[-0.44px] text-ink">문장 (상황별)</p>
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center justify-between text-[13px] font-bold leading-figma">
                            <span className="text-ink-muted">진행률</span>
                            <span className="text-track">3 / 5</span>
                          </div>
                          <div className="h-[10px] overflow-hidden rounded-full bg-fill">
                            <div className="h-full w-[60%] rounded-full bg-track" />
                          </div>
                        </div>
                        <span className="btn-primary btn-lg w-full text-center">이어서 학습하기</span>
                      </div>
                    )}
                    {st === 'skip' && (
                      <span className="absolute left-full top-1/2 z-10 ml-[34px] -translate-y-1/2 whitespace-nowrap rounded-14 border-2 border-line bg-white px-5 py-3 text-[15px] font-bold leading-figma text-track-dark shadow-[0px_6px_16px_-2px_rgba(26,13,64,0.1)]">
                        여기로 건너뛸까요?
                        <TailLeft className="left-[-15px] top-1/2 -translate-y-1/2" />
                      </span>
                    )}
                  </div>
                </Fragment>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 오른쪽 패널 */}
      <div className="flex w-[368px] shrink-0 flex-col gap-4 bg-white p-6">
        <div {...area('stats')} className="flex items-center justify-center gap-[18px] pb-2">
          <Avatar className="size-[34px] text-[14px]" />
          <span className="h-[22px] w-[1.5px] shrink-0 bg-line" />
          <Stat icon="/ui/stat-streak.svg" box={21} value={USER.streak} className="gap-1.5 text-[15px] text-stat-streak" />
          <Stat icon="/ui/stat-xp.svg" box={18} w={17.12} h={16.28} value={USER.xp} className="gap-1.5 text-[15px] text-stat-xp" />
          <Stat icon="/ui/stat-level.svg" box={18} w={15.59} h={18} value={`Lv.${USER.level}`} className="gap-1.5 text-[15px] text-stat-level" />
        </div>
        <div {...area('rail')} className="flex flex-col gap-4">
          <div className="card-flat flex flex-col gap-4">
            <div className="flex items-center justify-between font-bold leading-figma">
              <p className="text-[17px] text-ink">오늘의 과제</p>
              <span className="text-[14px] text-track">모두 보기</span>
            </div>
            <RailTask label="오늘의 복습 정리" cur={0} total={1} />
            <RailTask label="독화 학습 1회" cur={1} total={1} />
            <RailTask label="학습 2회 채우기" cur={1} total={2} />
          </div>
          <div className="card-flat flex flex-col items-center gap-3.5">
            <div className="flex items-baseline gap-3 font-bold leading-figma">
              <p className="text-[17px] text-ink">오답 <span className="text-[22px] text-primary-500">5</span><span className="text-primary-500">개</span></p>
              <span className="h-[18px] w-[1.5px] shrink-0 rounded-[1px] bg-line" />
              <p className="text-[17px] text-ink">북마크 <span className="text-[22px] text-bookmark">3</span><span className="text-bookmark">개</span></p>
            </div>
            <span className="btn-primary btn-md w-full text-center">복습하기</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 02 학습 탭(모바일 학습 경로) ─────────────────────────────────────────────
function LearnMock({ motion }) {
  const path = ['mastered', 'current', 'skip', 'locked']
  const cur = 1
  const sheet = (
    <div {...area('sheet')} className="absolute inset-x-0 bottom-[78px] z-20 flex flex-col gap-[11px] rounded-t-22 border-t-2 border-line bg-white px-[18px] pb-5 pt-[18px] shadow-sheet">
      <div className="flex items-center justify-between gap-3 font-bold leading-figma">
        <p className="min-w-0 truncate text-[17px] text-ink">음절·단어</p>
        <span className="shrink-0 text-[13px] text-track">4 / 6</span>
      </div>
      <div className="h-[9px] overflow-hidden rounded-full bg-fill">
        <div className="h-full w-[66%] rounded-full bg-track" />
      </div>
      <span className="btn-primary w-full py-4 text-center text-[16px]">이어서 학습하기</span>
    </div>
  )
  return (
    <MobileShell active="learn" overlay={sheet}>
      <div {...area('switch')} className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1">
        <span className="flex-1 rounded-10 bg-white py-[9px] text-center text-[14px] font-bold leading-figma text-track shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]">독화</span>
        <span className="flex-1 rounded-10 py-[9px] text-center text-[14px] font-bold leading-figma text-ink-faint">발화</span>
      </div>
      <div className="flex w-full items-center gap-3.5 rounded-16 border-b-4 border-track-dark bg-track py-[15px] pl-[17px] pr-[13px] text-white">
        <div className="flex min-w-0 flex-1 flex-col gap-[3px] font-bold leading-figma">
          <span className="text-[11px] opacity-[0.85]">독화 · 2단계</span>
          <span className="text-[18px] tracking-[-0.36px]">음절·단어</span>
        </div>
        <span {...area('guideBtn')} className="shrink-0 rounded-10 border-1.5 border-white/35 bg-white/[0.18] px-3 py-[7px] text-[12px] font-bold leading-figma">가이드</span>
      </div>
      <div className="relative w-full py-2">
        <StageArrow src="/ui/lp-232-35-stage-arrow-prev.svg" className="left-0.5 size-[38px]" style={{ top: 8 + cur * 74 + 9 }} />
        <StageArrow src="/ui/lp-232-35-stage-arrow-next.svg" className="right-0.5 size-[38px]" style={{ top: 8 + cur * 74 + 9 }} />
        <div {...area('nodes')} className="mx-auto flex w-[56px] flex-col items-center">
          {path.map((st, i) => (
            <Fragment key={i}>
              {i > 0 && <Connector done={path[i - 1] === 'mastered'} />}
              <div className="relative">
                <Node status={st} glow={motion} />
                {st === 'skip' && (
                  <span className="absolute left-full top-1/2 z-10 ml-4 -translate-y-1/2 whitespace-nowrap rounded-13 border-2 border-line bg-white px-2.5 py-2 text-[12px] font-bold leading-figma text-track-dark shadow-[0px_6px_16px_-2px_rgba(26,13,64,0.1)]">
                    여기로 건너뛸까요?
                    <TailLeft className="left-[-15px] top-1/2 -translate-y-1/2" />
                  </span>
                )}
              </div>
            </Fragment>
          ))}
        </div>
      </div>
    </MobileShell>
  )
}

// ── 03·04 레슨 화면(모바일) ─────────────────────────────────────────────────
function LessonShell({ track = 'read', done = 0, children, bar }) {
  return (
    <div data-track={track} className="relative flex h-full flex-col overflow-hidden bg-page text-ink">
      <div className="flex items-center gap-3 px-[18px] pt-[18px]">
        <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 shrink-0" />
        <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong">
          <div className="h-full rounded-full bg-track transition-[width] duration-500 ease-out" style={{ width: `${(done / 12) * 100}%` }} />
        </div>
        <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted">1 / 12</span>
      </div>
      <div className="flex flex-col gap-4 px-[18px] pt-6">{children}</div>
      <div className="absolute inset-x-0 bottom-0 z-10">{bar}</div>
    </div>
  )
}

function Question({ label, title }) {
  return (
    <div className="relative flex flex-col gap-1.5 pr-12 leading-figma">
      <p className="text-[12px] font-bold text-track">{label}</p>
      <p className="text-[21px] font-bold tracking-[-0.525px] text-ink">{title}</p>
      <span {...area('bookmark')} className="absolute right-0 top-[14px] flex size-[38px] items-center justify-center rounded-full border-2 border-line bg-white">
        <img src="/ui/lp-328-8-bookmark-default.svg" alt="" className="size-[16.29px]" />
      </span>
    </div>
  )
}

const OPT = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] transition-colors duration-300 ease-out'
const OPT_CLASS = {
  idle: `${OPT} py-3 border-2 border-b-5 border-line bg-white text-ink`,
  selected: `${OPT} py-3 border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPT} pb-3 pt-[14px] border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPT} pb-3 pt-[14px] border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPT} pb-3 pt-[14px] border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}

function Option({ n, word, state = 'idle' }) {
  return (
    <div className={OPT_CLASS[state]}>
      <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted">{n}</span>
      <span className="flex-1 text-[18px] font-bold leading-figma">{word}</span>
    </div>
  )
}

// 단어 독화 문항(두 보기와 결과 바가 한 화면에 들어오게 입모양 칸·보기·하단 바를 앱보다 조금 줄였다). 시연 장면: play(입모양 재생) → select(보기 고름) → confirm(확인 누름) → result(결과 바).
// wrong이면 1번 '나비'를 골라 틀리고, 아니면 2번 '바다'를 골라 맞힌다. 장면이 없으면 정지 화면(골라 둔 상태 또는 오답 결과).
function ReadMock({ wrong = false, scene, tick, running }) {
  const s = scene || (wrong ? 'result' : 'select')
  const pick = wrong ? 1 : 2
  const shown = s === 'result'
  const optState = (n) => {
    if (s === 'play') return 'idle'
    if (!shown) return n === pick ? 'selected' : 'idle'
    if (n === 2) return pick === 2 ? 'correct' : 'target'
    return n === pick ? 'wrong' : 'idle'
  }
  const correct = !wrong
  const bar = shown ? (
    <div key="result" className={`flex flex-col gap-2.5 border-t-2 px-[18px] pb-4 pt-3 ${correct ? 'border-good bg-good-tint' : 'border-bad bg-bad-tint'}`}>
      <div className={`flex flex-col gap-[3px] leading-figma ${RISE} ${correct ? 'text-good-text' : 'text-bad-text'}`}>
        <p className="text-[19px] font-bold tracking-[-0.38px]">{correct ? '정답이에요!' : '아쉬워요'}</p>
        <p className="text-[13px] font-bold opacity-80">정답은 「바다」예요</p>
      </div>
      <span className={`${correct ? 'btn-good' : 'btn-bad'} btn-bar w-full py-3 text-center text-[16px]`}>계속하기</span>
    </div>
  ) : (
    <div key="ask" className="border-t-2 border-line bg-white px-[18px] pb-4 pt-3">
      <span className={`btn-primary btn-bar block w-full py-3 text-center text-[16px] ${
        s === 'play' ? '!border-inactive-line !bg-inactive !text-inactive-text' : s === 'confirm' ? 'translate-y-[2px] !border-b-2' : ''}`}>확인</span>
    </div>
  )
  return (
    <LessonShell done={shown ? 1 : 0} bar={<div {...area('resultBar')}>{bar}</div>}>
      <Question label="단어 독화" title="이 입모양은 어떤 단어일까요?" />
      <div {...area('stage')} className="h-[158px] w-full rounded-18 border-2 border-line bg-white p-4">
        <FaceStage mouth={mouthAt(tick, running)} className="h-full" talker="화자 2" />
      </div>
      <div {...area('options')} className="flex flex-col gap-2.5">
        <Option n={1} word="나비" state={optState(1)} />
        <Option n={2} word="바다" state={optState(2)} />
      </div>
    </LessonShell>
  )
}

// 녹음 중 파형. 틱마다 막대 높이를 바꾸고 높이 전환(300ms)으로 이어 붙인다.
function Wave({ tick }) {
  return (
    <div className="flex h-[26px] items-center justify-center gap-[3px]">
      {Array.from({ length: 30 }, (_, i) => {
        const v = Math.abs(Math.sin(i * 1.7 + tick * 2.3)) * (0.45 + 0.55 * Math.abs(Math.sin(i * 0.37 + tick * 0.9)))
        return <span key={i} className="w-[3px] rounded-full bg-track transition-[height] duration-300 ease-out" style={{ height: 4 + v * 22 }} />
      })}
    </div>
  )
}

const PHONES = [['ㅂ', 88], ['ㅏ', 92], ['ㄷ', 58], ['ㅏ', 90]]

// 발화 문항(결과 카드와 결과 바가 겹치지 않게 여백을 앱보다 조금 줄였다). before = 녹음 전·중(idle → rec), result = 결과(idle·rec 동안은 분석 중, result에서 점수·칩이 나온다).
function SpeakMock({ result = false, scene, tick, running }) {
  const s = scene || (result ? 'result' : 'idle')
  let body
  let bar
  if (result) {
    const ready = s === 'result'
    const good = PHONES.filter(([, v]) => scoreTone(v).level === 'good').length
    body = (
      <div className="flex w-full flex-col items-center gap-3 rounded-18 border-2 border-line bg-white px-4 py-4">
        <div {...area('score')} className="flex flex-col items-center gap-0.5 font-bold leading-figma">
          {ready
            ? <p key="score" className={`text-[44px] tracking-[-1.32px] ${FADE} ${scoreTone(84).text}`}>84%</p>
            : <p key="wait" className="text-[44px] tracking-[-1.32px] text-ink-ghost">…</p>}
          <p className="text-[13px] text-ink-faint">발음 정확도</p>
        </div>
        <div {...area('chips')} className="flex justify-center gap-2">
          {PHONES.map(([p, v], i) => (
            ready ? (
              <span key={`r${i}`} className={`flex size-12 items-center justify-center rounded-13 border-2 ${RISE} ${scoreTone(v).chip}`}
                style={{ animationDelay: `${120 + i * 90}ms` }}>
                <span className="text-[20px] font-bold leading-figma">{p}</span>
              </span>
            ) : <span key={`w${i}`} className="size-12 rounded-13 border-2 border-dashed border-line bg-surface-muted" />
          ))}
        </div>
        <span {...area('detail')} className={`btn-secondary rounded-[12px] border-b-4 px-[26px] py-3 text-[14px] transition-opacity duration-300 ${ready ? '' : 'opacity-50'}`}>자세히 보기</span>
      </div>
    )
    bar = ready ? (
      <div key="done" className="flex flex-col gap-2.5 border-t-2 border-good/35 bg-good-tint px-[18px] pb-4 pt-3">
        <div className={`flex flex-col gap-[3px] font-bold leading-figma text-good-text ${RISE}`}>
          <p className="text-[19px] tracking-[-0.38px]">잘했어요!</p>
          <p className="text-[13px] opacity-80">{PHONES.length}개 중 {good}개 소리를 정확히 냈어요</p>
        </div>
        <div className="flex gap-2.5">
          <span className="btn-secondary btn-bar flex-1 rounded-13 border-good-line px-0 py-3 text-center text-[15px] text-good-text">다시 말하기</span>
          <span className="btn-good btn-bar flex-1 rounded-13 px-0 py-3 text-center text-[15px]">계속하기</span>
        </div>
      </div>
    ) : (
      <div key="wait" className="flex flex-col gap-[3px] border-t-2 border-line bg-white px-[18px] pb-[26px] pt-4 font-bold leading-figma text-ink-muted">
        <p className="text-[19px] tracking-[-0.38px]">분석 중…</p>
        <p className="text-[13px] opacity-80">발음을 분석하고 있어요</p>
      </div>
    )
  } else {
    const rec = s === 'rec'
    body = (
      <div {...area('stage')} className="w-full overflow-hidden rounded-18 border-2 border-line bg-white">
        <div className="px-4 pt-4"><FaceStage mouth={mouthAt(tick, running)} className="h-[120px]" /></div>
        <div className="flex h-[46px] items-center justify-center">
          {rec
            ? <div key="wave" className={FADE}><Wave tick={tick} /></div>
            : <p key="cap" className={`text-center text-[13px] font-bold leading-figma text-ink-faint ${scene ? FADE : ''}`}>입모양을 따라 해보세요</p>}
        </div>
      </div>
    )
    bar = (
      <div className="flex flex-col items-center gap-2.5 border-t-2 border-line bg-white px-[18px] pb-[26px] pt-[18px]">
        <span {...area('mic')} className="relative block size-[72px]">
          {rec ? (
            <img key="rec" src="/ui/speak-recording.svg" alt="" className="absolute max-w-none animate-pulse"
              style={{ top: '-16.67%', left: '-16.67%', width: '133.33%', height: '133.33%' }} />
          ) : (
            <span key="mic" className="flex size-[72px] items-center justify-center rounded-full border-2 border-b-6 border-track-dark bg-track">
              <img src="/ui/speak-mic.svg" alt="" className="size-8" />
            </span>
          )}
        </span>
        <p className={`text-[14px] font-bold leading-figma ${rec ? 'text-track-dark' : 'text-ink-faint'}`}>{rec ? '듣고 있어요' : '눌러서 말하기'}</p>
      </div>
    )
  }
  return (
    <LessonShell track="speak" done={result && s === 'result' ? 1 : 0} bar={bar}>
      <Question label="음절·단어" title="이 단어를 소리 내어 말해보세요" />
      <div className="flex items-center justify-center rounded-16 bg-track-tint py-[18px] pl-[22px] pr-4">
        <p className="text-center text-[32px] font-bold leading-figma tracking-[-0.64px] text-track-dark">바다</p>
      </div>
      {body}
    </LessonShell>
  )
}

// ── 06 연습 ──────────────────────────────────────────────────────────────────
const PRACTICE = [
  ['free', '자유 발화', '내가 쓴 문장을 소리 내어 확인해요', '/ui/card-free.svg', 'bg-pastel-pink'],
  ['scenario', '상황별 시나리오', '카페·병원 등 상황을 골라 연습해요', '/ui/card-scenario.svg', 'bg-pastel-amber'],
  ['sign', '수어 보기', '문장을 수어로도 확인할 수 있어요', '/ui/card-sign.svg', 'bg-pastel-mint'],
  ['endless', '엔드리스 학습', '틀렸던 유형이 계속 나와요', '/ui/tab-card-endless.svg', 'bg-pastel-indigo'],
  ['mouth', '입모양 교실', '웹캠으로 따라 하고 안 보이는 혀 위치도 확인해요', '/ui/nav-learn.svg', 'bg-pastel-violet'],
]

function PracticeMock() {
  return (
    <MobileShell active="practice" title="연습">
      <div className="flex flex-col gap-2.5">
        {PRACTICE.map(([key, t, d, icon, chip]) => (
          <div key={key} {...area(key)} className="flex items-center gap-3.5 rounded-16 border-2 border-b-5 border-line bg-white p-4">
            <span className={`icon-chip-sm ${chip}`}><img src={icon} alt="" className="size-[22px]" /></span>
            <span className="flex min-w-0 flex-1 flex-col gap-[3px] leading-figma">
              <span className="text-[16px] font-bold text-ink">{t}</span>
              <span className="truncate text-[12.5px] text-ink-muted">{d}</span>
            </span>
            <span className="relative h-3 w-1.5 shrink-0">
              <img src="/ui/review-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
            </span>
          </div>
        ))}
      </div>
    </MobileShell>
  )
}

// ── 07 과제(데스크톱 본문 열) ────────────────────────────────────────────────
function TaskRow({ label, cur, total, xp }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3.5">
      {done
        ? <img src="/ui/task-done.svg" alt="" className="size-[26px] shrink-0" />
        : <span className="size-[26px] shrink-0 rounded-full border-2 border-line" />}
      <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <span className="text-[15px] text-ink">{label}</span>
          <span className="text-[13px] text-primary-500">{cur} / {total}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-fill">
          <div className="h-full rounded-full bg-primary-500" style={{ width: `${(cur / total) * 100}%` }} />
        </div>
      </div>
      <span className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold leading-figma ${done ? 'bg-primary-100 text-primary-700' : 'bg-surface-sunken text-ink-faint'}`}>+{xp} XP</span>
    </div>
  )
}

const BADGES = [
  ['첫 걸음', '/ui/medal-0.svg', true], ['7일 연속', '/ui/medal-1.svg', true], ['입모양 마스터', '/ui/medal-2.svg', false],
  ['정확도 90%', null, true], ['100문제 돌파', '/ui/medal-3.svg', true], ['복습왕', '/ui/medal-4.svg', false],
]

function TaskMock() {
  return (
    <div className="flex h-full flex-col gap-4 overflow-hidden bg-white px-8 pt-5 text-ink">
      <section {...area('today')} className="flex flex-col gap-[18px] rounded-18 border-2 border-line bg-white p-[22px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">오늘의 과제</p>
          <span className="text-[13px] text-ink-muted">오늘 남은 시간 6시간</span>
        </div>
        <TaskRow label="오늘의 복습 정리" cur={0} total={1} xp={10} />
        <TaskRow label="독화 학습 1회" cur={1} total={1} xp={15} />
        <TaskRow label="학습 2회 채우기" cur={1} total={2} xp={20} />
      </section>
      <section {...area('special')} className="relative isolate h-[158px] shrink-0 overflow-hidden rounded-20 border-2 border-b-5 border-primary-600 bg-[linear-gradient(167.63deg,var(--brand-light)_0%,var(--brand)_70.92%)] pl-[26px] pt-[26px]">
        <WatermarkDeco src="/ui/lp-137-17-deco-doka.svg" size={198} top={-73.06} right={-73.06} inset={[-7, -12, -17, -12]} />
        <div className="flex w-[462px] flex-col gap-2.5 font-bold leading-figma text-white">
          <p className="text-[13px] tracking-[0.26px] opacity-80">특별 과제</p>
          <p className="text-[23px] tracking-[-0.46px]">이번 주 5일 학습하기</p>
          <div className="flex justify-between text-[14px]">
            <span className="opacity-90">3 / 5일</span>
            <span className="opacity-90">+100 XP</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-white/30">
            <div className="h-full w-[60%] rounded-full bg-white" />
          </div>
        </div>
      </section>
      <section {...area('badges')} className="flex flex-col gap-[18px] rounded-18 border-2 border-line bg-white p-[22px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">배지</p>
          <span className="text-[13px] text-ink-muted">4 / 12개 획득</span>
        </div>
        <div className="grid grid-cols-6 gap-x-3">
          {BADGES.map(([label, icon, earned]) => (
            <div key={label} className="flex min-w-0 flex-col items-center gap-[9px]">
              <span className={earned ? '' : 'opacity-50 grayscale'}>
                {icon ? <img src={icon} alt="" className="size-14 max-w-none" /> : (
                  <span className="flex size-14 items-center justify-center rounded-full bg-pastel-mint">
                    <span className="size-[39.3%] rotate-45 rounded-[18%] bg-emerald-500" />
                  </span>
                )}
              </span>
              <span className={`text-center text-[11.5px] font-bold leading-figma ${earned ? 'text-ink' : 'text-ink-muted opacity-55'}`}>{label}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

// ── 08 복습 ──────────────────────────────────────────────────────────────────
function ReviewCta({ id, title, sub, btn, card, btnCls }) {
  return (
    <div {...area(id)} className={`h-[150px] min-w-0 flex-1 rounded-18 border-2 border-b-5 px-3.5 pt-[27px] ${card}`}>
      <span className="flex flex-col gap-3">
        <span className="flex flex-col gap-3 leading-figma text-white">
          <span className="text-[17px] font-bold tracking-[-0.34px]">{title}</span>
          <span className="text-[12px] opacity-85">{sub}</span>
        </span>
        <span className={`flex w-full items-center justify-center rounded-[11px] bg-white py-2.5 text-[12.5px] font-bold leading-figma ${btnCls}`}>{btn}</span>
      </span>
    </div>
  )
}

const REVIEW_ITEMS = [
  ['독화', '바다', '오늘 · 2회 틀렸어요'],
  ['독화', '커피 주세요', '어제 · 1회 틀렸어요'],
  ['발화', '나비', '3일 전 · 북마크를 했어요'],
]

function ReviewMock() {
  return (
    <MobileShell active="review" title="복습">
      <div className="flex w-full gap-2.5">
        <ReviewCta id="ctaWrong" title="복습할 오답 5개" sub="약 3분이면 끝나요" btn="오답 복습하기" btnCls="text-primary-700"
          card="border-primary-700 bg-[linear-gradient(137.7deg,var(--brand-light)_0%,var(--brand)_70.92%)]" />
        <ReviewCta id="ctaMark" title="복습할 북마크 3개" sub="저장해둔 문장이에요" btn="북마크 복습하기" btnCls="text-bookmark-dark"
          card="border-bookmark-dark bg-[linear-gradient(137.7deg,var(--bookmark-light)_0%,var(--bookmark)_70.92%)]" />
      </div>
      <section className="flex w-full flex-col gap-3 rounded-16 border-2 border-line bg-white px-[18px] pb-[18px] pt-[18px]">
        <div className="flex items-center justify-between">
          <p className="text-[16px] font-bold leading-figma text-ink">복습할 항목</p>
          <span {...area('erase')} className="flex items-center gap-1.5 rounded-full border-1.5 border-line py-[7px] pl-3 pr-3.5 text-[12.5px] font-bold leading-figma text-ink-muted">
            <img src="/ui/lp-100-15-trash.svg" alt="" className="size-3.5" />
            지우기
          </span>
        </div>
        <div className="flex gap-[7px]">
          {[['전체', 8, true], ['오답', 5], ['북마크', 3]].map(([l, n, on]) => (
            <span key={l} className={`flex items-center gap-[5px] rounded-full px-[13px] py-2 font-bold leading-figma ${on ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted'}`}>
              <span className="text-[12.5px]">{l}</span>
              <span className={`text-[11px] ${on ? 'text-white/75' : 'text-ink-ghost'}`}>{n}</span>
            </span>
          ))}
        </div>
        <div {...area('items')} className="flex flex-col">
          {REVIEW_ITEMS.map(([track, word, meta], i) => (
            <div key={word} className={`flex items-center gap-[11px] py-3 ${i ? 'border-t-1.5 border-line' : ''}`}>
              <span className={`flex w-[46px] shrink-0 items-center justify-center rounded-[7px] py-1 text-[11px] font-bold leading-figma ${track === '발화' ? 'bg-speak-tint text-speak-dark' : 'bg-primary-100 text-primary-700'}`}>{track}</span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma">
                <span className="truncate text-[15px] font-bold text-ink">{word}</span>
                <span className="text-[11.5px] text-ink-muted">{meta}</span>
              </span>
              <span className="relative h-2.5 w-[5px] shrink-0">
                <img src="/ui/lp-239-34-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
              </span>
            </div>
          ))}
        </div>
      </section>
    </MobileShell>
  )
}

// ── 09 분석(데스크톱 본문 열, 상세 링크까지 보이게) ─────────────────────────────
const STAT_DECO = {
  clock: { src: '/ui/lp-104-15-deco-clock.svg', size: 124, top: -49.47, right: -47.47 },
  percent: { src: '/ui/lp-104-15-deco-percent.svg', size: 124, top: -49.47, right: -47.47 },
  flame: { src: '/ui/lp-104-15-deco-flame.svg', size: 167, top: -77.02, right: -75.03 },
}
const WEEK_MIN = [40, 25, 55, 35, 60, 45, 72]
const WEEK_ACC = [68, 71, 70, 75, 74, 79, 82]

function ChartCard({ id, title, children }) {
  return (
    <section {...area(id)} className="flex w-full flex-col gap-[18px] rounded-18 border-2 border-line bg-white p-[22px]">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[17px] text-ink">{title}</p>
        <span className="text-[13px] text-ink-muted">최근 7주</span>
      </div>
      {children}
    </section>
  )
}

function GridLines() {
  return [38, 75, 113].map((t) => <div key={t} className="absolute left-0 right-[-4px] h-px bg-fill" style={{ top: t }} />)
}

function AnalysisMock() {
  const max = Math.max(...WEEK_MIN)
  const lo = 65, hi = 85
  const y = (v) => 123 - ((v - lo) / (hi - lo)) * 93
  const n = WEEK_ACC.length - 1
  const x = (i) => `calc(10px + ${i} * (100% - 16px) / ${n})`
  return (
    <div className="flex h-full flex-col gap-5 overflow-hidden bg-white px-8 pt-6 text-ink">
      <p className="text-[30px] font-bold leading-figma tracking-[-0.75px] text-ink">분석</p>
      <div {...area('stats')} className="flex w-full gap-3.5">
        {[['clock', '총 학습', '3시간 40분', '지난주보다 +25분', 'text-stat-xp'], ['percent', '평균 정확도', '82%', '지난주 +3%p', 'text-stat-accuracy'],
          ['flame', '연속 학습', `${USER.streak}일`, '최고 기록 15일', 'text-stat-streak']].map(([deco, label, value, delta, color]) => (
          <div key={deco} className="relative isolate flex min-w-0 flex-1 flex-col gap-[7px] overflow-hidden rounded-18 border-2 border-line bg-white p-5 leading-figma">
            <WatermarkDeco {...STAT_DECO[deco]} />
            <span className="text-[13px] font-bold text-ink-soft">{label}</span>
            <span className={`whitespace-nowrap text-[27px] font-bold tracking-[-0.675px] ${color}`}>{value}</span>
            <span className="text-[12px] font-bold text-ink-faint">{delta}</span>
          </div>
        ))}
      </div>
      <ChartCard id="bars" title="학습시간 추이">
        <div className="relative h-[150px] w-full">
          <GridLines />
          <div className="absolute inset-x-0 bottom-[22px] top-0 flex items-end">
            {WEEK_MIN.map((m, i) => (
              <div key={i} className="flex flex-1 justify-center">
                <div className={`w-[46px] rounded-b-[2px] rounded-t-[8px] ${i === n ? 'bg-primary-500' : 'bg-primary-300'}`} style={{ height: (m / max) * 114 }} />
              </div>
            ))}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex h-[18px] items-start">
            {WEEK_MIN.map((m, i) => (
              <span key={i} className={`flex-1 text-center font-bold leading-figma ${i === n ? 'text-[11.5px] text-primary-700' : 'text-[10.5px] text-ink-ghost'}`}>
                {Math.floor(m / 60)}h {m % 60}m
              </span>
            ))}
          </div>
        </div>
      </ChartCard>
      <ChartCard id="line" title="정확도 추이">
        <div className="relative h-[150px] w-full">
          <GridLines />
          <svg viewBox={`0 0 ${n} 150`} preserveAspectRatio="none" className="absolute left-2.5 top-0 h-[150px] w-[calc(100%-16px)] overflow-visible">
            <path d={WEEK_ACC.map((v, i) => `${i ? 'L' : 'M'}${i} ${y(v).toFixed(1)}`).join(' ')} fill="none" className="stroke-chart-accuracy"
              strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          </svg>
          {WEEK_ACC.map((v, i) => (
            <Fragment key={i}>
              <span className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-chart-accuracy ${i === n ? 'size-4' : 'size-[11px]'}`}
                style={{ left: x(i), top: y(v) }} />
              <span className={`absolute -translate-x-1/2 font-bold leading-figma ${i === n ? 'text-[13px] text-stat-accuracy' : 'text-[11.5px] text-chart-label'}`}
                style={{ left: x(i), top: y(v) - (i === n ? 31.2 : 26.67) }}>{v}</span>
            </Fragment>
          ))}
        </div>
      </ChartCard>
      <div className="flex w-full gap-3">
        {[['calendar', '활동 캘린더'], ['history', '회차 히스토리'], ['fullStats', '전체 통계']].map(([k, label]) => (
          <span key={k} {...area(k)} className="flex flex-1 items-center justify-between rounded-16 border-2 border-b-5 border-line bg-white py-[18px] pl-5 pr-[18px] text-[15px] font-bold leading-figma text-ink">
            {label}
            <span className="relative h-3.5 w-[7px] shrink-0">
              <img src="/ui/menu-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── 10 프로필 ────────────────────────────────────────────────────────────────
function MenuRow({ id, title, sub, danger, first }) {
  return (
    <div {...area(id)} className={`flex items-center justify-between py-[15px] pl-[18px] pr-4 leading-figma ${first ? '' : 'border-t-1.5 border-line'}`}>
      <span className="flex flex-col gap-[3px]">
        <span className={`text-[15px] font-bold ${danger ? 'text-bad-text' : 'text-ink'}`}>{title}</span>
        <span className="text-[12px] text-ink-muted">{sub}</span>
      </span>
      <span className="relative h-3 w-1.5 shrink-0">
        <img src="/ui/lp-240-34-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
      </span>
    </div>
  )
}

function ProfileMock() {
  // 접근성 설정 Aa 버튼(A11ySettings). 휴대폰에서는 탭 바 위 왼쪽에 떠 있다
  const aa = (
    <span {...area('a11y')} className="absolute bottom-[94px] left-4 z-40 grid size-11 place-items-center rounded-full bg-slate-900 text-[15px] font-bold tracking-tight text-white shadow-lg">Aa</span>
  )
  return (
    <MobileShell title="프로필" overlay={aa}>
      <section className="flex h-[150px] w-full items-start gap-3.5 overflow-hidden rounded-18 border-2 border-b-5 border-primary-600 bg-[linear-gradient(156.15deg,#a78bfa_0%,#7d53de_70.92%)] pl-[18px] pr-4 pt-[22px]">
        <div className="flex size-16 shrink-0 items-center justify-center rounded-full border-[3px] border-white/90 bg-white/20 text-2xl font-black text-white">{USER.initial}</div>
        <div className="mt-[19px] flex min-w-0 flex-1 flex-col gap-2 font-bold leading-figma text-white">
          <div className="flex items-center gap-2">
            <span className="truncate text-[20px] tracking-[-0.4px]">{USER.name}</span>
            <span className="shrink-0 rounded-full bg-white/[0.24] px-2.5 py-1 text-[11.5px]">Lv.{USER.level}</span>
          </div>
          <div className="flex justify-between text-[11.5px]">
            <span className="opacity-85">다음 레벨까지</span>
            <span>340 / 700 XP</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/[0.28]">
            <div className="h-full w-[49%] rounded-full bg-white" />
          </div>
        </div>
      </section>
      <section className="w-full overflow-hidden rounded-16 border-2 border-line bg-white">
        <MenuRow first id="placement" title="자가진단 다시 하기" sub="지금 수준으로 단계 재추천" />
        <MenuRow id="account" title="계정 설정" sub="이름 · 이메일 · 비밀번호 · 로그아웃" />
        <MenuRow id="reset" danger title="학습 초기화" sub="기록을 모두 지우고 처음부터" />
      </section>
    </MobileShell>
  )
}

// 목업 목록. design = 설계 크기(px, 가이드 사진 상자와 같은 비율). areas = 이 목업에 번호 배지를 다는 영역.
export const MOCKS = {
  overview: { design: [1440, 760], C: OverviewMock, areas: ['stats', 'rail', 'logo'],
    alt: '데스크톱 학습 화면 예시. 왼쪽 메뉴, 가운데 학습 경로와 레슨 카드, 오른쪽 오늘의 과제와 복습 카드.' },
  learn: { design: [520, 653], C: LearnMock, areas: ['switch', 'guideBtn', 'nodes', 'arrows', 'sheet'],
    alt: '휴대폰 학습 탭 예시. 독화·발화 전환, 단계 이름과 가이드 버튼, DOKA 단계 노드와 아래 레슨 카드.' },
  readQuestion: { design: [375, 564], C: (p) => <ReadMock {...p} />, areas: ['bookmark', 'stage', 'options'],
    alt: '단어 독화 문항 예시. 왼쪽 위에 화자 이름이 붙은 입모양 영상을 보고 보기를 고른 뒤 확인을 누르면 초록 결과 바에 정답이에요가 나온다.' },
  readWrong: { design: [375, 564], C: (p) => <ReadMock wrong {...p} />, areas: ['resultBar'],
    alt: '단어 독화 오답 예시. 고른 보기는 빨강, 정답 보기는 초록 테두리, 아래 빨간 결과 바에 정답이 나온다.' },
  speakBefore: { design: [375, 564], C: (p) => <SpeakMock {...p} />, areas: ['stage', 'mic'],
    alt: '발화 문항 예시. 말할 단어와 아바타 입모양, 아래 마이크 버튼. 녹음 중에는 파형이 움직인다.' },
  speakResult: { design: [375, 564], C: (p) => <SpeakMock result {...p} />, areas: ['score', 'chips', 'detail'],
    alt: '발화 결과 예시. 발음 정확도 84%, 소리별 칩 네 개 중 ㄷ은 주황, 아래 초록 결과 바 잘했어요.' },
  practice: { design: [520, 653], C: PracticeMock, areas: ['free', 'scenario', 'sign', 'endless', 'mouth'],
    alt: '연습 탭 예시. 자유 발화, 상황별 시나리오, 수어 보기, 엔드리스 학습, 입모양 교실 카드.' },
  task: { design: [700, 606], C: TaskMock, areas: ['today', 'special', 'badges'],
    alt: '과제 탭 예시. 오늘의 과제 세 줄, 특별 과제 카드, 배지 목록.' },
  review: { design: [520, 653], C: ReviewMock, areas: ['ctaWrong', 'ctaMark', 'items', 'erase'],
    alt: '복습 탭 예시. 오답·북마크 복습 카드와 복습할 항목 목록, 지우기 버튼.' },
  analysis: { design: [640, 804], C: AnalysisMock, areas: ['stats', 'bars', 'line', 'calendar', 'history', 'fullStats'],
    alt: '분석 탭 예시. 총 학습·평균 정확도·연속 학습 세 칸, 학습시간·정확도 추이 그래프, 활동 캘린더·회차 히스토리·전체 통계 링크.' },
  profile: { design: [520, 653], C: ProfileMock, areas: ['placement', 'account', 'reset', 'a11y'],
    alt: '프로필 탭 예시. 이름과 레벨 카드, 자가진단 다시 하기·계정 설정·학습 초기화 메뉴, 왼쪽 아래 접근성 설정 Aa 버튼.' },
}

/**
 * 시연 루프. tick(ms)마다 한 칸씩 steps를 돈다([장면, 칸 수]). final = 동작 최소화일 때 보일 정지 장면.
 * areaScene = 그 영역을 강조할 때 붙잡아 둘 장면(결과 바를 가리키면 결과 장면에서 멈춘다).
 */
export const DEMOS = {
  reading: {
    tick: 350, steps: [['play', 6], ['select', 3], ['confirm', 2], ['result', 8]], final: 'result',
    areaScene: { bookmark: 'play', stage: 'play', options: 'select', resultBar: 'result' },
  },
  speaking: {
    tick: 350, steps: [['idle', 5], ['rec', 8], ['result', 9]], final: 'result',
    areaScene: { stage: 'idle', mic: 'rec', score: 'result', chips: 'result', detail: 'result' },
  },
}

const HOLE_PAD = 4
function roundRect(x, y, w, h, r) {
  return `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}`
    + `H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`
}
const sameRects = (a, b) => JSON.stringify(a) === JSON.stringify(b)

/**
 * 가이드 사진 상자. 폭은 w(좁으면 칸 폭), 높이는 w×h 비율을 따른다. 안쪽 목업은 설계 크기로 그리고
 * 상자 폭 / 설계 폭만큼 줄인다(ResizeObserver). 강조·번호 배지는 줄이지 않은 겉 층에 그린다(배지 크기가 일정하게).
 *
 * scene·tick·running: 시연 상태(GuideDemo useDemo). motion: 동작 최소화가 아니면 true(현재 단계 링 깜빡임).
 * active: 강조 중인 영역 키. numbers·labels: 영역 → 주석 번호·제목. onPick·onHover: 배지를 누름·가리킴.
 */
export default function GuideMock({ name, w, h, scene = null, tick = 0, running = false, motion = false, active = null, numbers = {}, labels = {}, onPick, onHover }) {
  const m = MOCKS[name]
  const outerRef = useRef(null)
  const innerRef = useRef(null)
  const [dw, dh] = m ? m.design : [w, h]
  const [scale, setScale] = useState(w / dw)
  const [box, setBox] = useState({ w, h })
  const [rects, setRects] = useState({})

  // 상자 폭이 바뀌면 배율을 다시 잰다
  useLayoutEffect(() => {
    const el = outerRef.current
    if (!el) return undefined
    const fit = () => {
      if (!el.clientWidth) return
      setScale(el.clientWidth / dw)
      setBox({ w: el.clientWidth, h: el.clientHeight })
    }
    fit()
    if (typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [dw])

  // 영역 위치(겉 층 좌표). 배율·장면이 바뀌면 다시 재고, 전환(300ms)이 끝난 뒤 한 번 더 잰다.
  const own = m?.areas
  const measure = useCallback(() => {
    const outer = outerRef.current
    const inner = innerRef.current
    if (!outer || !inner || !own) return
    const base = outer.getBoundingClientRect()
    const next = {}
    inner.querySelectorAll('[data-area]').forEach((el) => {
      const k = el.getAttribute('data-area')
      if (!own.includes(k)) return
      const r = el.getBoundingClientRect()
      if (!r.width || !r.height) return
      ;(next[k] ||= []).push({ x: Math.round(r.left - base.left), y: Math.round(r.top - base.top), w: Math.round(r.width), h: Math.round(r.height) })
    })
    setRects((prev) => (sameRects(prev, next) ? prev : next))
  }, [own])
  useLayoutEffect(() => {
    measure()
    const t = setTimeout(measure, 380)
    return () => clearTimeout(t)
  }, [measure, scale, scene])
  useLayoutEffect(() => {
    document.fonts?.ready?.then(measure).catch(() => {})
  }, [measure])

  if (!m) return null
  const { C } = m
  const hit = active ? rects[active] : null
  const holes = (hit || []).map((r) => roundRect(r.x - HOLE_PAD, r.y - HOLE_PAD, r.w + HOLE_PAD * 2, r.h + HOLE_PAD * 2, 10)).join(' ')
  const clampX = (v) => Math.max(3, Math.min(box.w - 23, v))
  const clampY = (v) => Math.max(3, Math.min(box.h - 23, v))
  const placed = []
  return (
    <div ref={outerRef} className="relative shrink-0 overflow-hidden rounded-14 bg-page" style={{ width: w, maxWidth: '100%', aspectRatio: `${w} / ${h}` }}>
      <style>{KEYFRAMES}</style>
      <span className="sr-only">{m.alt}</span>
      <div ref={innerRef} aria-hidden="true" className="pointer-events-none absolute left-0 top-0 origin-top-left select-none"
        style={{ width: dw, height: dh, transform: `scale(${scale})` }}>
        <C scene={scene} tick={tick} running={running} motion={motion} />
      </div>

      {/* 강조: 영역 밖을 흰 막으로 흐리고 영역에 링을 두른다. 다른 사진의 영역이면 이 사진 전체를 흐린다. */}
      <svg aria-hidden="true" width={box.w} height={box.h}
        className={`pointer-events-none absolute inset-0 transition-opacity duration-300 ease-out ${active ? 'opacity-100' : 'opacity-0'}`}>
        <path fillRule="evenodd" fill="rgba(255,255,255,0.6)" d={`M0 0H${box.w}V${box.h}H0Z ${holes}`} />
      </svg>
      {(hit || []).map((r, i) => (
        <span key={`${active}-${i}`} aria-hidden="true"
          className="pointer-events-none absolute animate-[gm-fade_250ms_ease-out_both] rounded-[10px] border-2 border-primary-500 shadow-[0_0_0_4px_rgba(125,83,222,0.16)]"
          style={{ left: r.x - HOLE_PAD, top: r.y - HOLE_PAD, width: r.w + HOLE_PAD * 2, height: r.h + HOLE_PAD * 2 }} />
      ))}

      {/* 번호 배지: 누르거나 가리키면 옆 주석이 함께 강조된다 */}
      {onPick && own?.map((k) => {
        const r = rects[k]?.[0]
        const n = numbers[k]
        if (!r || !n) return null
        const on = active === k
        // 영역 왼쪽에 자리가 있으면 영역 밖 왼쪽에(글자를 가리지 않게), 없으면 왼쪽 위 모서리에 걸친다.
        // 작게 줄인 사진에서 배지가 겹치면 앞 배지 오른쪽으로 비켜 놓는다.
        const outside = r.x - 26 >= 3
        let left = clampX(outside ? r.x - 26 : r.x - 8)
        const top = clampY(outside ? r.y + Math.min(4, r.h / 2 - 10) : r.y - 8)
        while (placed.some((p) => Math.abs(p[0] - left) < 22 && Math.abs(p[1] - top) < 22)) left = clampX(left + 24)
        placed.push([left, top])
        return (
          <button key={k} type="button" aria-label={`${n}번 ${labels[k] || ''} 위치`} aria-pressed={on}
            onClick={() => onPick(k)} onMouseEnter={() => onHover?.(k)} onMouseLeave={() => onHover?.(null)}
            onFocus={() => onHover?.(k)} onBlur={() => onHover?.(null)}
            className={`absolute flex size-5 items-center justify-center rounded-full text-[11px] font-bold leading-none text-white shadow-[0_2px_6px_rgba(26,13,64,0.28)] ring-2 ring-white transition-[transform,background-color,opacity] duration-200 ease-out focus:outline-none focus-visible:ring-primary-300 ${
              on ? 'scale-110 bg-primary-700' : 'bg-primary-500 hover:bg-primary-600'} ${active && !on ? 'opacity-50' : ''}`}
            style={{ left, top }}>
            {n}
          </button>
        )
      })}

      {/* 테두리는 위에 덮어 그린다(상자 크기를 바꾸지 않게) */}
      <span aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-14 border-1.5 border-line" />
    </div>
  )
}
