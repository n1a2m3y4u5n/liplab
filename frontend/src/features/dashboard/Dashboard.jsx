import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../../store/useStore'
import { learningAPI, curriculumAPI } from '../../api'
import DashboardPet from '../../components/DashboardPet'
import NextUpCard from './NextUpCard'
import LearnerProfileCard from './LearnerProfileCard'
import { buildQTypes } from './buildQTypes'

const PRESET_SITUATIONS = [
  { id: '카페', label: '카페', icon: '☕' },
  { id: '병원', label: '병원', icon: '🏥' },
  { id: '식당', label: '식당', icon: '🍽️' },
  { id: '은행', label: '은행', icon: '🏦' },
  { id: '쇼핑', label: '쇼핑', icon: '🛍️' },
  { id: '대중교통', label: '대중교통', icon: '🚌' },
  { id: '직장', label: '직장', icon: '💼' },
  { id: '학교', label: '학교', icon: '📚' },
  { id: '직접 입력', label: '직접 입력', icon: '✏️' },
]

const HERO_SLIDES = [
  {
    id: 'reading',
    tab: '독화',
    eyebrow: '01',
    title: ['독화 학습', '입모양으로 들어요'],
    description: '자음·모음 입모양부터 상황별 문장·대화까지 단계로 익혀요.',
    to: '/pillar/reading',
    navMenuId: 'reading',
    cta: '독화 학습 보기',
    background: 'from-[#fffede] via-[#fffbb6] to-[#fff58d]',
    badge: 'bg-white/75 text-sky-700',
    visual: { shape: 'from-sky-300 via-sky-400 to-sky-600', shadow: 'shadow-[0_30px_60px_rgba(2,132,199,0.28)]', first: '입', second: '문장', third: '독화', chip: 'bg-sky-100 text-sky-700' },
  },
  {
    id: 'speaking',
    tab: '말하기',
    eyebrow: '02',
    title: ['말하기 학습', '발음을 다듬어요'],
    description: '소리와 억양을 보며 또박또박 말해요.',
    to: '/pillar/speaking',
    navMenuId: 'speaking',
    cta: '말하기 학습 보기',
    background: 'from-[#fff6f7] via-[#ffe7eb] to-[#ffd5dc]',
    badge: 'bg-white/80 text-rose-700',
    visual: { shape: 'from-rose-300 via-rose-400 to-pink-500', shadow: 'shadow-[0_30px_60px_rgba(244,63,94,0.22)]', first: '소리', second: '억양', third: '발음', chip: 'bg-rose-100 text-rose-700' },
  },
]

const CONVERSATION_UNLOCK_HINT = '3단계 문장 독화를 완료하면 대화 실전이 해금됩니다.'

// ── 단계형 커리큘럼 경로 (재설계 Phase 1) ────────────────────────────────────
const TRACKS = [
  { id: 'perception', title: '독화 지각 트랙', desc: '한국어를 이미 아는 분. 입모양 읽기 능력에 집중.', icon: '👂' },
  { id: 'language', title: '언어+독화 트랙', desc: '수어가 더 편한 분. 뜻(수어)부터 익히고 입모양으로.', icon: '🤟' },
]

const STAGE_STATUS = {
  mastered:    { label: '완료',     cls: 'bg-green-100 text-green-700' },
  in_progress: { label: '진행 중',  cls: 'bg-blue-100 text-blue-700' },
  unlocked:    { label: '시작 가능', cls: 'bg-primary-100 text-primary-700' },
  available:   { label: '연습',     cls: 'bg-gray-100 text-gray-600' },
  locked:      { label: '잠김',     cls: 'bg-gray-100 text-gray-400' },
  coming_soon: { label: '준비 중',  cls: 'bg-gray-100 text-gray-400' },
}

// 하위 카드는 같은 폴더의 파일로 분리했다(NextUpCard·LearnerProfileCard).
// ActivityCalendar·ReviewSection은 기존에도 렌더링되지 않던 컴포넌트라 여기서 쓰지 않고 파일로만 보존한다.

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const statistics = useStore((state) => state.statistics)
  const setStatistics = useStore((state) => state.setStatistics)
  const requestNavMenu = useStore((state) => state.requestNavMenu)

  const [heroSlide, setHeroSlide] = useState(0)
  const [heroDirection, setHeroDirection] = useState(1)
  const [selectedSituation, setSelectedSituation] = useState('카페')
  const [customSituation, setCustomSituation] = useState('')
  const [selectedLevel, setSelectedLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [loading, setLoading] = useState(false)
  const [calendarData, setCalendarData] = useState({})
  const [recLevel, setRecLevel] = useState(null)
  const [testLocked, setTestLocked] = useState(false)   // 3단계(문장 테스트) 잠김 여부
  const [conversationLocked, setConversationLocked] = useState(false)
  const [unlockNotice, setUnlockNotice] = useState(null)

  useEffect(() => {
    loadStatistics()
    loadCalendar()
    // 적응형 난이도 — 최근 정확도로 추천 레벨을 받아 기본값으로
    curriculumAPI.getRecommendedLevel()
      .then((r) => { setRecLevel(r); setSelectedLevel(r.recommended_level) })
      .catch(() => {})
    // 테스트(3단계)는 2단계 숙달 전엔 잠긴다 → 시나리오 생성 전에 미리 막는다
    curriculumAPI.getStages()
      .then((data) => {
        const s3 = (data?.stages || []).find((x) => x.stage === 3)
        const s4 = (data?.stages || []).find((x) => x.stage === 4)
        setTestLocked(!!s3 && (s3.status === 'locked' || s3.status === 'coming_soon'))
        setConversationLocked(!!s4 && (s4.status === 'locked' || s4.status === 'coming_soon'))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!location.hash) return undefined
    const timer = window.setTimeout(() => {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [location.hash])

  useEffect(() => {
    if (!unlockNotice) return undefined
    const timer = window.setTimeout(() => setUnlockNotice(null), 5000)
    return () => window.clearTimeout(timer)
  }, [unlockNotice])

  const loadStatistics = async () => {
    try {
      const stats = await learningAPI.getStatistics()
      setStatistics(stats)
    } catch (error) {
      console.error('Failed to load statistics:', error)
    }
  }

  const loadCalendar = async () => {
    try {
      const data = await learningAPI.getCalendar()
      setCalendarData(data)
    } catch (e) {
      console.error('Failed to load calendar:', e)
    }
  }

  const effectiveSituation =
    selectedSituation === '직접 입력' ? customSituation : selectedSituation

  const explainConversationUnlock = () => {
    setUnlockNotice(CONVERSATION_UNLOCK_HINT)
  }

  const startScenario = async (mode) => {
    const isConversation = mode === 'conversation'
    if ((!isConversation && testLocked) || (isConversation && conversationLocked)) {
      if (isConversation) explainConversationUnlock()
      else setUnlockNotice('아직 잠긴 단계예요. 학습에서 2단계(음절·단어)를 먼저 완료해주세요.')
      return
    }
    if (!effectiveSituation.trim()) {
      setUnlockNotice('상황을 입력해주세요.')
      return
    }
    setLoading(true)
    try {
      const scenario = await learningAPI.getScenario(effectiveSituation, selectedLevel)
      if (!isConversation) {
        // 테스트는 문장마다 주관식·4지선다·서술형을 섞어서 출제한다.
        scenario.qTypes = buildQTypes(scenario.sentences.length)
      }
      setScenario(scenario, 'test')
      navigate(isConversation ? '/conversation' : '/practice')
    } catch (error) {
      setUnlockNotice('시나리오 생성에 실패했습니다. 다시 시도해주세요.')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const startPractice = () => startScenario('practice')
  const startConversation = () => startScenario('conversation')

  const goToSection = (id) => {
    const element = document.getElementById(id)
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const moveHeroSlide = (step) => {
    setHeroDirection(step > 0 ? 1 : -1)
    setHeroSlide((current) => (current + step + HERO_SLIDES.length) % HERO_SLIDES.length)
  }

  const selectHeroSlide = (index) => {
    if (index === heroSlide) return
    setHeroDirection(index > heroSlide ? 1 : -1)
    setHeroSlide(index)
  }

  const finishHeroDrag = (_, info) => {
    if (info.offset.x < -55 || info.velocity.x < -500) moveHeroSlide(1)
    else if (info.offset.x > 55 || info.velocity.x > 500) moveHeroSlide(-1)
  }

  const currentHero = HERO_SLIDES[heroSlide]

  return (
    <div className="min-h-0 bg-white lg:h-full lg:overflow-hidden">

      <AnimatePresence>
        {unlockNotice && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            className="fixed right-4 top-44 z-[60] flex max-w-sm items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-950 shadow-xl sm:right-6"
          >
            <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-amber-200 text-lg">🔒</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-black">대화 실전은 아직 잠겨 있어요</p>
              <p className="mt-0.5 text-xs leading-relaxed text-amber-800">{unlockNotice}</p>
            </div>
            <button type="button" onClick={() => setUnlockNotice(null)} aria-label="해금 안내 닫기"
              className="text-lg leading-none text-amber-600 hover:text-amber-900">×</button>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="mx-auto max-w-[1440px] px-4 py-4 sm:px-6 sm:py-5 lg:h-full">

        <NextUpCard />

        <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid items-stretch gap-4 lg:h-full lg:grid-cols-[290px_minmax(0,1fr)]">
          <LearnerProfileCard user={user} statistics={statistics} calendarData={calendarData} />

          <div
            role="region"
            aria-roledescription="carousel"
            aria-label="LIPLAB 맞춤 학습"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') { event.preventDefault(); moveHeroSlide(-1) }
              if (event.key === 'ArrowRight') { event.preventDefault(); moveHeroSlide(1) }
            }}
            className="relative min-h-[500px] overflow-hidden rounded-[24px] outline-none ring-sky-400 transition focus-visible:ring-2 focus-visible:ring-offset-2 lg:h-full lg:min-h-0"
          >
            <AnimatePresence initial={false} mode="wait">
              <motion.article
                key={currentHero.id}
                initial={{ opacity: 0, x: heroDirection > 0 ? 90 : -90 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: heroDirection > 0 ? -90 : 90 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={0.16}
                dragMomentum={false}
                onDragEnd={finishHeroDrag}
                aria-live="polite"
                aria-label={`${heroSlide + 1} / ${HERO_SLIDES.length}: ${currentHero.tab}`}
                className={`absolute inset-0 cursor-grab overflow-hidden bg-gradient-to-r ${currentHero.background} px-7 pb-20 pt-6 active:cursor-grabbing sm:px-10 lg:px-12`}
                style={{ touchAction: 'pan-y' }}
              >
                {/* 배경 깊이감 — 부드러운 오브(빛망울)로 밋밋한 단색 배경을 채운다 */}
                <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
                  <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-white/40 blur-3xl" />
                  <div className="absolute left-[46%] -top-16 h-64 w-64 rounded-full bg-white/30 blur-3xl" />
                  <div className="absolute left-[36%] top-1/3 h-72 w-72 rounded-full bg-amber-200/30 blur-3xl animate-pulse-slow" />
                  <div className="absolute -bottom-10 left-[30%] h-56 w-56 rounded-full bg-white/25 blur-2xl" />
                </div>

                {/* 중앙 빈 공간을 채우는 떠다니는 장식 — 프로스티드 카드·점·링·반짝임 (텍스트 뒤) */}
                <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-[1] hidden lg:block">
                  <div className={`absolute left-[45%] top-[24%] grid h-16 w-16 -rotate-6 place-items-center rounded-2xl text-lg font-black shadow-lg backdrop-blur-sm ${currentHero.visual.chip}`}>{currentHero.visual.first}</div>
                  <div className="absolute left-[63%] top-[15%] h-12 w-12 rotate-12 rounded-xl bg-white/60 shadow-md backdrop-blur-sm" />
                  <div className="absolute left-[38%] top-[60%] h-10 w-10 rotate-6 rounded-xl bg-white/50 shadow-md backdrop-blur-sm" />
                  <span className="absolute left-[57%] top-[58%] h-11 w-11 rounded-full border-2 border-white/60" />
                  <span className="absolute left-[43%] top-[13%] h-8 w-8 rounded-full border-2 border-amber-300/60" />
                  <span className="absolute left-[41%] top-[50%] h-3.5 w-3.5 rounded-full bg-white/75" />
                  <span className="absolute left-[54%] top-[40%] h-2.5 w-2.5 rounded-full bg-amber-400/70" />
                  <span className="absolute left-[69%] top-[50%] h-3 w-3 rounded-full bg-white/65" />
                  <span className="absolute left-[50%] top-[70%] h-2 w-2 rounded-full bg-slate-900/10" />
                  <span className="absolute left-[52%] top-[30%] text-2xl text-amber-400/80">✦</span>
                  <span className="absolute left-[67%] top-[33%] text-base text-amber-500/70">✦</span>
                  <span className="absolute left-[47%] top-[43%] text-sm text-white/90 animate-pulse">✦</span>
                </div>

                <div className="relative z-10 flex h-full items-center">
                  <div className="ml-9 max-w-xl pb-6 sm:ml-12 md:pr-[210px] lg:ml-16 lg:pr-[250px]">
                    {/* data-hero-copy: 펫이 넘어오지 못하는 '학습 섹션' 장애물 영역 (실제 글자 폭에만 맞춤) */}
                    <div data-hero-copy className="w-fit">
                      <span className={`inline-flex rounded-full px-3 py-1.5 text-[11px] font-black shadow-sm ${currentHero.badge}`}>LIPLAB · {currentHero.eyebrow}</span>
                      <h1 className="mt-4 text-3xl font-black leading-[1.13] tracking-[-0.045em] text-slate-950 sm:text-4xl lg:text-[36px] xl:text-[40px]">
                        {currentHero.title[0]}<br />{currentHero.title[1]}
                      </h1>
                      <p className="mt-3 max-w-md text-sm font-semibold leading-relaxed text-slate-600">{currentHero.description}</p>
                      <button
                        type="button"
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={() => requestNavMenu(currentHero.navMenuId)}
                        className="mt-5 rounded-full bg-slate-950 px-6 py-3 text-sm font-black text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
                      >
                        {currentHero.cta}
                      </button>
                    </div>
                  </div>
                </div>

                <div aria-hidden="true" className="pointer-events-none absolute -bottom-10 -right-10 hidden h-[330px] w-[360px] md:block">
                  <div className={`absolute bottom-12 right-12 h-52 w-52 rotate-[-5deg] rounded-[48%_44%_50%_46%] bg-gradient-to-br ${currentHero.visual.shape} ${currentHero.visual.shadow}`}>
                    <span className="absolute left-[75px] top-[64px] h-5 w-5 rounded-full bg-slate-800" />
                    <span className="absolute left-[113px] top-[61px] h-5 w-5 rounded-full bg-slate-800" />
                    <span className="absolute left-[58px] top-[100px] h-10 w-[92px] rounded-b-full rounded-t-[42%] border-b-[12px] border-white/90" />
                    <span className="absolute left-[40px] top-[78px] h-4 w-4 rounded-full bg-white/40" />
                    <span className="absolute right-[40px] top-[78px] h-4 w-4 rounded-full bg-white/40" />
                    <span className="absolute -right-7 top-20 h-20 w-14 rotate-12 rounded-[55%_45%_55%_45%] bg-slate-900/20" />
                  </div>
                  <div className="absolute right-20 top-2 grid h-16 min-w-16 rotate-12 place-items-center rounded-2xl bg-white px-2 text-sm font-black text-slate-800 shadow-xl">{currentHero.visual.first}</div>
                  <div className={`absolute right-3 top-24 grid h-14 min-w-14 -rotate-6 place-items-center rounded-2xl px-2 text-xs font-black shadow-xl ${currentHero.visual.chip}`}>{currentHero.visual.second}</div>
                  <div className="absolute left-8 top-16 grid h-14 min-w-14 rotate-[-12deg] place-items-center rounded-full bg-white/90 px-2 text-xs font-black text-slate-700 shadow-xl">{currentHero.visual.third}</div>
                  <span className="absolute left-8 top-2 text-3xl text-amber-400">✦</span>
                  <span className="absolute right-8 top-3 text-xl text-amber-500">✦</span>
                </div>
              </motion.article>
            </AnimatePresence>

            {/* 대시보드 마스코트 펫 — 슬라이드 위에서 빈 공간을 돌아다닌다(슬라이드 전환에도 유지) */}
            <DashboardPet slideId={currentHero.id} />

            <button
              type="button"
              onClick={() => moveHeroSlide(-1)}
              aria-label="이전 맞춤 학습"
              className="absolute left-3 top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-slate-950/70 text-white shadow-lg backdrop-blur transition hover:scale-105 hover:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-white sm:left-4"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <button
              type="button"
              onClick={() => moveHeroSlide(1)}
              aria-label="다음 맞춤 학습"
              className="absolute right-3 top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-slate-950/70 text-white shadow-lg backdrop-blur transition hover:scale-105 hover:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-white sm:right-4"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
            </button>

            <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full bg-white/75 p-1.5 shadow-lg backdrop-blur-md" role="tablist" aria-label="맞춤 학습 슬라이드">
              {HERO_SLIDES.map((slide, index) => (
                <button
                  key={slide.id}
                  type="button"
                  role="tab"
                  aria-selected={heroSlide === index}
                  aria-label={`${slide.tab} 슬라이드`}
                  onClick={() => selectHeroSlide(index)}
                  className={`rounded-full px-3 py-2 text-[11px] font-black transition sm:px-4 ${heroSlide === index ? 'bg-slate-950 text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-slate-900'}`}
                >
                  {slide.tab}
                </button>
              ))}
            </div>
          </div>
        </motion.section>
      </main>
    </div>
  )
}
