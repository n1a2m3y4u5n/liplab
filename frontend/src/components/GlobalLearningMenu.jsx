import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useLocation, useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'

const PILLAR_NAV = [
  {
    id: 'reading',
    label: '독화',
    to: '/pillar/reading',
    bg: 'from-[#fffede] via-[#fffbb6] to-[#fff58d]',
    petGrad: 'from-sky-300 via-sky-400 to-sky-600',
    intro: '입모양을 보고 말을 이해하는 독화예요. 무엇부터 배워볼까요? 👀',
    theme: { text: 'text-sky-700', line: 'bg-sky-500' },
    items: [
      { label: '입모양 익히기', description: '자음·모음의 입모양 익히기', icon: '👄', to: '/learn/viseme' },
      { label: '단어 익히기', description: '비슷한 입모양 구별하기', icon: '🔤', to: '/learn/word' },
      { label: '문장 익히기', description: '상황별 독화와 AI 대화', icon: '💬', to: '/learn/scenario' },
      { label: '문맥 추론', description: '앞뒤 맥락으로 뜻 찾기', icon: '🧩', to: '/learn/closure' },
      { label: '내 문장 발음 보기', description: '원하는 문장의 입모양 확인하기', icon: '✍️', to: '/pronounce' },
      { label: '독화 복습', description: '틀린 문장과 예정 항목 다시 풀기', icon: '🔁', to: '/review/mistakes' },
    ],
  },
  {
    id: 'speaking',
    label: '말하기',
    to: '/pillar/speaking',
    bg: 'from-[#fff6f7] via-[#ffe7eb] to-[#ffd5dc]',
    petGrad: 'from-rose-300 via-rose-400 to-pink-500',
    intro: '내 발음을 눈으로 보며 또박또박 다듬어요! 🎤',
    theme: { text: 'text-rose-700', line: 'bg-rose-500' },
    items: [
      { label: '말하기 연습', description: '발성부터 문장 억양까지 연습하기', icon: '🎤', to: '/learn/speaking' },
      { label: '말하기 복습', description: '부족했던 발음 다시 연습하기', icon: '🔁', to: '/review/speaking' },
    ],
  },
  {
    id: 'tactile',
    label: '촉각(타도마)',
    to: '/pillar/tactile',
    bg: 'from-[#faf8ff] via-[#eee9ff] to-[#ddd6fe]',
    petGrad: 'from-violet-300 via-violet-400 to-purple-600',
    intro: '얼굴 모형을 손끝으로 느껴 말을 이해하는 촉각 학습이에요. ✋',
    theme: { text: 'text-violet-700', line: 'bg-violet-500' },
    items: [
      { label: '촉각 학습', description: '5단계 커리큘럼과 자유 체험', icon: '🖐️', to: '/learn/tactile' },
      { label: '촉각 복습', description: '취약 항목 다시 풀기', icon: '🔁', to: '/review/tactile' },
    ],
  },
  {
    id: 'etc',
    label: '기타',
    to: null,
    bg: 'from-[#f8fafc] via-[#eef2f7] to-[#dbe3ec]',
    petGrad: 'from-slate-300 via-slate-400 to-slate-600',
    intro: '수어·분석·사용법도 준비했어요. 골라보세요! ✨',
    theme: { text: 'text-slate-800', line: 'bg-slate-500' },
    items: [
      { label: '수어 학습', description: '문장을 수어로 함께 확인하기', icon: '🤟', to: '/learn/sign' },
      { label: '학습 분석', description: '강점과 취약점, 학습 흐름 보기', icon: '📊', to: '/analysis/overview' },
      { label: '사용법', description: 'LIPLAB 활용 안내', icon: '❔', to: '/guide' },
    ],
  },
]

function MegaMenuPet({ petGrad, speech }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.6, x: -60 }}
      animate={{ opacity: 1, scale: 1, x: 0 }}
      exit={{ opacity: 0, scale: 0.7, x: -30 }}
      transition={{ type: 'spring', stiffness: 200, damping: 18 }}
      className="pointer-events-none flex select-none flex-col items-center gap-5"
    >
      <div className="relative min-h-[64px] w-[280px]">
        <AnimatePresence mode="wait">
          <motion.div
            key={speech}
            initial={{ opacity: 0, y: 10, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="relative rounded-[26px] bg-white px-6 py-4 text-center text-[15px] font-bold leading-relaxed text-slate-800 shadow-[0_16px_40px_rgba(15,23,42,0.16)]"
          >
            {speech}
            <span className="absolute -bottom-2 left-1/2 h-5 w-5 -translate-x-1/2 rotate-45 rounded-sm bg-white" />
          </motion.div>
        </AnimatePresence>
      </div>
      <motion.div
        animate={{ y: [0, -10, 0], rotate: [-2, 2, -2] }}
        transition={{ duration: 3.4, repeat: Infinity, ease: 'easeInOut' }}
        className={`relative h-36 w-36 rounded-[48%_44%_50%_46%] bg-gradient-to-br ${petGrad} shadow-[0_28px_60px_rgba(15,23,42,0.28)]`}
      >
        <span className="absolute left-[42px] top-[56px] h-4 w-4 rounded-full bg-slate-900" />
        <span className="absolute left-[78px] top-[56px] h-4 w-4 rounded-full bg-slate-900" />
        <span className="absolute left-[46px] top-[80px] h-6 w-[44px] rounded-b-full border-b-[8px] border-white/90" />
        <span className="absolute left-[26px] top-[64px] h-3 w-3 rounded-full bg-white/40" />
        <span className="absolute right-[26px] top-[64px] h-3 w-3 rounded-full bg-white/40" />
      </motion.div>
    </motion.div>
  )
}

export default function GlobalLearningMenu() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useStore((state) => state.user)
  const [activeNavMenu, setActiveNavMenu] = useState(null)
  const [navTop, setNavTop] = useState(0)
  const [hoveredItem, setHoveredItem] = useState(null)
  const navRef = useRef(null)
  const activeTopic = PILLAR_NAV.find((topic) => topic.id === activeNavMenu)

  useEffect(() => {
    setActiveNavMenu(null)
    setHoveredItem(null)
  }, [location.pathname])

  const openNav = (id) => {
    if (navRef.current) setNavTop(navRef.current.getBoundingClientRect().top)
    setHoveredItem(null)
    setActiveNavMenu(id)
  }

  const closeNav = () => {
    setActiveNavMenu(null)
    setHoveredItem(null)
  }

  const go = (to) => {
    closeNav()
    navigate(to)
  }

  const chooseTab = (tab) => {
    if (tab.to) go(tab.to)
    else if (activeNavMenu === tab.id) closeNav()
    else openNav(tab.id)
  }

  return (
    <header className="sticky top-0 z-50 shrink-0 border-b border-slate-200 bg-white/95 backdrop-blur-xl">
      <div className="border-b border-slate-100 bg-slate-50/90">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-2 text-[11px] text-slate-500 sm:px-6">
          <button type="button" onClick={() => go('/dashboard')} className="inline-flex items-center gap-1.5 font-bold text-slate-700 hover:text-sky-700">
            <span aria-hidden="true">⌂</span>
            메인 바로가기
          </button>
          <p className="hidden sm:block"><b className="text-slate-700">{user?.username}님</b>, 오늘도 나에게 맞는 방식으로 학습해 보세요.</p>
        </div>
      </div>

      <div className="mx-auto max-w-[1440px] px-4 sm:px-6">
        <div className="flex min-h-[74px] items-center gap-4 py-3">
          <button type="button" onClick={() => go('/dashboard')} className="flex shrink-0 items-center gap-2 text-left">
            <span aria-hidden="true" className="relative grid h-10 w-10 place-items-center rounded-2xl bg-sky-50">
              <span className="absolute h-4 w-7 rounded-full border-[3px] border-sky-400" />
              <span className="absolute h-7 w-4 rounded-full border-[3px] border-sky-400" />
            </span>
            <span>
              <span className="block text-2xl font-black tracking-[-0.05em] text-slate-950">LIPLAB</span>
              <span className="hidden text-[10px] font-medium text-slate-400 sm:block">Visual Language Lab</span>
            </span>
          </button>

          <div className="ml-auto flex items-center gap-1">
            {[
              ['복습', '/review/today', '↻'],
              ['사용법', '/guide', '?'],
            ].map(([label, to, icon]) => (
              <button key={label} type="button" onClick={() => go(to)} className="flex w-16 flex-col items-center gap-1 rounded-xl py-1.5 text-[11px] font-bold text-slate-600 transition hover:bg-sky-50 hover:text-sky-700">
                <span aria-hidden="true" className="grid h-6 w-7 place-items-center text-lg">{icon}</span>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <nav
        ref={navRef}
        aria-label="학습 카테고리"
        onMouseLeave={closeNav}
        onKeyDown={(event) => {
          if (event.key === 'Escape') closeNav()
        }}
        className="relative border-t border-slate-100"
      >
        <AnimatePresence>
          {activeTopic && (
            <motion.div
              key={activeTopic.id}
              initial={{ clipPath: 'circle(0% at 12% 0%)' }}
              animate={{ clipPath: 'circle(150% at 12% 0%)' }}
              exit={{ clipPath: 'circle(0% at 12% 0%)', transition: { duration: 0.28, ease: 'easeIn' } }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              style={{ height: `calc(100dvh - ${navTop}px)` }}
              className={`absolute inset-x-0 top-0 z-0 overflow-hidden bg-gradient-to-br ${activeTopic.bg}`}
            >
              <div className="mx-auto grid h-full max-w-[1440px] grid-cols-1 gap-6 px-5 pb-10 pt-[76px] sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <div className="flex min-h-0 flex-col justify-center overflow-y-auto py-4">
                  <p className={`mb-2 text-sm font-black uppercase tracking-[0.14em] ${activeTopic.theme.text}`}>{activeTopic.label}</p>
                  {activeTopic.items.map((item) => (
                    <button
                      key={item.to}
                      type="button"
                      onMouseEnter={() => setHoveredItem(item)}
                      onFocus={() => setHoveredItem(item)}
                      onClick={() => go(item.to)}
                      className="group flex items-center gap-4 border-b border-slate-900/10 py-3.5 text-left transition hover:pl-2 sm:py-4"
                    >
                      <span aria-hidden="true" className="text-3xl transition group-hover:scale-110 sm:text-4xl">{item.icon}</span>
                      <span className="min-w-0 flex-1 text-2xl font-black tracking-tight text-slate-900 sm:text-[28px]">{item.label}</span>
                      <span aria-hidden="true" className="text-2xl font-black text-slate-900/25 transition group-hover:translate-x-1 group-hover:text-slate-900/60">→</span>
                    </button>
                  ))}
                </div>

                <div onMouseEnter={closeNav} className="hidden items-center justify-center lg:flex">
                  <MegaMenuPet petGrad={activeTopic.petGrad} speech={hoveredItem?.description || activeTopic.intro} />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="relative z-10 mx-auto max-w-[1440px] px-2 sm:px-6">
          <ul className="flex items-stretch overflow-x-auto">
            {PILLAR_NAV.map((tab) => {
              const active = activeNavMenu === tab.id
              return (
                <li key={tab.id} onMouseEnter={() => openNav(tab.id)} className="shrink-0">
                  <button
                    type="button"
                    onFocus={() => openNav(tab.id)}
                    onClick={() => chooseTab(tab)}
                    aria-haspopup="menu"
                    aria-expanded={active}
                    className={`relative flex items-center gap-2 px-4 py-3 text-base font-black tracking-tight transition sm:px-8 sm:text-lg ${active ? tab.theme.text : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`}
                  >
                    {tab.label}
                    <span aria-hidden="true" className={`text-[10px] transition-transform ${active ? 'rotate-180' : ''}`}>▼</span>
                    <span aria-hidden="true" className={`absolute inset-x-3 bottom-0 h-1 rounded-full transition ${active ? tab.theme.line : 'bg-transparent'}`} />
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </nav>
    </header>
  )
}
