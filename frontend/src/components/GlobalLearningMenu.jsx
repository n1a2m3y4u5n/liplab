import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useLocation, useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'

const CONVERSATION_UNLOCK_HINT = '3단계 문장 독화를 완료하면 대화 실전이 해금됩니다.'

const MENU_GROUPS = [
  {
    title: '독화 학습',
    tone: 'sky',
    items: [
      { label: '입모양 기초', description: '자음·모음 입모양 익히기', icon: '👄', to: '/learn/viseme' },
      { label: '음절·단어', description: '비슷한 입모양 구별하기', icon: '🔤', to: '/learn/word' },
      { label: '문장 테스트', description: '상황별 독화 실력 확인', icon: '💬', to: '/dashboard#reading-test' },
      { label: '대화 실전', description: '상황을 고르고 AI와 대화', icon: '🗣️', to: '/dashboard#reading-test', unlockStage: 4 },
      { label: '문맥 추론', description: '앞뒤 맥락으로 뜻 찾기', icon: '🧩', to: '/learn/closure' },
      { label: '내 문장 발음', description: '아무 글이나 입력해 입모양 보기', icon: '✍️', to: '/pronounce' },
    ],
  },
  {
    title: '연습과 복습',
    tone: 'rose',
    items: [
      { label: '말하기 연습', description: '내 발음을 눈으로 다듬기', icon: '🎤', to: '/speak' },
      { label: '오늘의 복습', description: '예정 항목과 모은 문장', icon: '🔁', to: '/dashboard#daily-review' },
      { label: '북마크', description: '저장한 문장 모아보기', icon: '★', to: '/bookmarks' },
    ],
  },
  {
    title: '학습 도구',
    tone: 'violet',
    items: [
      { label: '수어 학습', description: '문장을 수어로 확인', icon: '🤟', to: '/sign' },
      { label: '촉각 학습', description: '얼굴 모형을 손으로 느껴 이해(타도마)', icon: '🖐️', to: '/tactile' },
      { label: '학습 분석', description: '강점과 취약점 확인', icon: '📊', to: '/analysis' },
      { label: '사용법', description: 'LIPLAB 활용 안내', icon: '?', to: '/guide' },
    ],
  },
]

const TONES = {
  sky: 'bg-sky-50 text-sky-700 group-hover:bg-sky-100',
  rose: 'bg-rose-50 text-rose-700 group-hover:bg-rose-100',
  violet: 'bg-violet-50 text-violet-700 group-hover:bg-violet-100',
}

export default function GlobalLearningMenu() {
  const [open, setOpen] = useState(false)
  const [conversationLocked, setConversationLocked] = useState(false)
  const [unlockMessage, setUnlockMessage] = useState(null)
  const location = useLocation()
  const navigate = useNavigate()
  const triggerRef = useRef(null)
  const panelRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    setOpen(false)
    setUnlockMessage(null)
  }, [location.pathname, location.search, location.hash])

  useEffect(() => {
    let cancelled = false
    curriculumAPI.getStages()
      .then((data) => {
        const stage = (data?.stages || []).find((item) => item.stage === 4)
        if (!cancelled) setConversationLocked(!!stage && (stage.status === 'locked' || stage.status === 'coming_soon'))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!open) return undefined

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
      if (event.key !== 'Tab') return

      const focusable = panelRef.current?.querySelectorAll(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
      triggerRef.current?.focus()
    }
  }, [open])

  const go = (to) => {
    setOpen(false)
    navigate(to)
  }

  const chooseItem = (item) => {
    if (item.unlockStage === 4 && conversationLocked) {
      setUnlockMessage(CONVERSATION_UNLOCK_HINT)
      return
    }
    go(item.to)
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label="전체 학습 메뉴 열기"
        aria-expanded={open}
        aria-controls="global-learning-menu"
        className="fixed right-3 top-3 z-[70] inline-flex h-11 items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-3 text-sm font-bold text-slate-800 shadow-lg shadow-slate-900/10 backdrop-blur transition hover:-translate-y-0.5 hover:border-primary-300 hover:text-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 sm:right-5 sm:px-4"
      >
        <span aria-hidden="true" className="flex w-4 flex-col gap-1">
          <span className="h-0.5 w-4 rounded-full bg-current" />
          <span className="h-0.5 w-4 rounded-full bg-current" />
          <span className="h-0.5 w-4 rounded-full bg-current" />
        </span>
        <span className="hidden sm:inline">학습 메뉴</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-[80] bg-slate-950/35 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setOpen(false)
            }}
          >
            <motion.aside
              ref={panelRef}
              id="global-learning-menu"
              role="dialog"
              aria-modal="true"
              aria-label="전체 학습 메뉴"
              className="ml-auto flex h-full w-full max-w-sm flex-col bg-white shadow-2xl"
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.24, ease: 'easeOut' }}
            >
              <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                <button type="button" onClick={() => go('/dashboard')} className="text-left">
                  <span className="block text-xl font-black tracking-tight text-primary-600">LIPLAB</span>
                  <span className="block text-xs text-slate-500">원하는 학습으로 바로 이동하세요</span>
                </button>
                <button
                  ref={closeRef}
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="전체 학습 메뉴 닫기"
                  className="grid h-10 w-10 place-items-center rounded-full bg-slate-100 text-xl text-slate-600 transition hover:bg-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  ×
                </button>
              </div>

              <nav className="flex-1 overflow-y-auto px-4 py-4" aria-label="학습 콘텐츠 바로가기">
                <button
                  type="button"
                  onClick={() => go('/dashboard')}
                  className={`mb-4 flex w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left transition ${
                    location.pathname === '/dashboard' && !location.hash
                      ? 'border-primary-200 bg-primary-50 text-primary-800'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-primary-200 hover:bg-primary-50/60'
                  }`}
                >
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-white text-xl shadow-sm">⌂</span>
                  <span>
                    <span className="block text-sm font-bold">메인 학습 허브</span>
                    <span className="block text-xs text-slate-500">전체 콘텐츠 한눈에 보기</span>
                  </span>
                </button>

                <AnimatePresence>
                  {unlockMessage && (
                    <motion.div role="alert" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                      className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-relaxed text-amber-900">
                      <div className="flex items-start gap-2">
                        <span aria-hidden="true">🔒</span>
                        <span><b>대화 실전은 아직 잠겨 있어요.</b><br />{unlockMessage}</span>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="space-y-5">
                  {MENU_GROUPS.map((group) => (
                    <section key={group.title} aria-labelledby={`menu-${group.tone}`}>
                      <h2 id={`menu-${group.tone}`} className="mb-2 px-1 text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                        {group.title}
                      </h2>
                      <div className="space-y-1.5">
                        {group.items.map((item) => {
                          const current = location.pathname === item.to.split('#')[0]
                            && (!item.to.includes('#') || location.hash === `#${item.to.split('#')[1]}`)
                          const locked = item.unlockStage === 4 && conversationLocked
                          return (
                            <button
                              key={`${item.label}-${item.to}`}
                              type="button"
                              onClick={() => chooseItem(item)}
                              aria-current={current ? 'page' : undefined}
                              aria-label={locked ? `${item.label}, 잠김. ${CONVERSATION_UNLOCK_HINT}` : item.label}
                              title={locked ? CONVERSATION_UNLOCK_HINT : undefined}
                              className={`group flex w-full items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition ${
                                locked
                                  ? 'border border-dashed border-amber-300 bg-slate-50 hover:bg-amber-50'
                                  : current ? 'bg-slate-100' : 'hover:bg-slate-50'
                              }`}
                            >
                              <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl text-lg transition ${
                                locked ? 'bg-gray-200 text-gray-500 group-hover:bg-amber-100 group-hover:text-amber-700' : TONES[group.tone]
                              }`}>
                                {locked ? '🔒' : item.icon}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className={`block text-sm font-bold ${locked ? 'text-gray-500' : 'text-slate-800'}`}>{item.label}</span>
                                <span className={`block truncate text-xs ${locked ? 'text-amber-700' : 'text-slate-500'}`}>
                                  {locked ? '3단계 문장 독화 완료 후 해금' : item.description}
                                </span>
                              </span>
                              <span aria-hidden="true" className={`text-xs font-bold ${locked ? 'text-amber-600' : 'text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500'}`}>
                                {locked ? '잠김' : '→'}
                              </span>
                            </button>
                          )
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </nav>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
