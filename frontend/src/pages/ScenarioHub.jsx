import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'

/**
 * 상황별 시나리오 (Figma 225:183 / 225:226) — 셸 안의 피커.
 * 상황·난이도를 고르고 모드(문장 테스트 / AI 대화)를 선택하면 기존 학습 흐름으로 진입한다.
 * 상황은 Figma 6칸(225:296: 카페·병원·학교 / 식당·회사·직접 입력). 목록에 없는 상황으로 들어오면
 * (회차 히스토리의 ?situation=은행 등) '직접 입력'에 그 상황을 채워 이어서 연습할 수 있게 한다.
 * 모드 카드는 제목·부제만(225:330) — 잠김은 비활성(흐림), 준비 중에는 부제를 '준비 중…'으로 바꾼다.
 */
const SITUATIONS = ['카페', '병원', '학교', '식당', '회사', '직접 입력']
const CUSTOM = '직접 입력'
const QUESTION_TYPES = ['test', 'test-multiple', 'essay']
// 카드 틀(225:293) — 2px 테두리, r18, p22, 머리-본문 16
const CARD = 'flex w-full flex-col gap-4 rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]'
const LOCK_HINT = { practice: '단어 학습을 완료하면 문장 학습이 열려요.', conversation: '문장 학습을 완료하면 대화 실전이 열려요.' }

function shuffledTypes(length) {
  return Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length])
    .sort(() => Math.random() - 0.5)
}

export default function ScenarioHub() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  // 회차 히스토리 등에서 ?situation=병원 으로 들어오면 그 상황을 미리 고른다(목록에 없으면 직접 입력으로).
  const preset = (searchParams.get('situation') || '').trim()
  const presetListed = preset && SITUATIONS.includes(preset) && preset !== CUSTOM
  const [situation, setSituation] = useState(presetListed ? preset : preset ? CUSTOM : '카페')
  const [customSituation, setCustomSituation] = useState(presetListed ? '' : preset)
  const [level, setLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [recommended, setRecommended] = useState(null)
  const [locks, setLocks] = useState({ practice: false, conversation: false })
  const [loadingMode, setLoadingMode] = useState(null)
  const [notice, setNotice] = useState('')   // 브라우저 alert 대신 쓰는 인앱 안내(맥락 유지)

  const levelTouched = useRef(false)   // 유저가 난이도를 직접 고르면 추천값이 덮어쓰지 않게

  useEffect(() => {
    if (!notice) return undefined
    const t = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  useEffect(() => {
    curriculumAPI.getRecommendedLevel()
      .then((result) => {
        setRecommended(result.recommended_level)
        if (!levelTouched.current) setLevel(result.recommended_level)
      })
      .catch(() => {})
    curriculumAPI.getStages()
      .then((data) => {
        const stages = data?.stages || []
        const locked = (number) => {
          const stage = stages.find((item) => item.stage === number)
          return !!stage && ['locked', 'coming_soon'].includes(stage.status)
        }
        setLocks({ practice: locked(3), conversation: locked(4) })
      })
      .catch(() => {})
  }, [])

  const effectiveSituation = situation === CUSTOM ? customSituation.trim() : situation

  const start = async (mode) => {
    if (locks[mode]) {
      setNotice(LOCK_HINT[mode])
      return
    }
    if (!effectiveSituation) return
    setLoadingMode(mode)
    try {
      const scenario = await learningAPI.getScenario(effectiveSituation, level)
      if (mode === 'practice') scenario.qTypes = shuffledTypes(scenario.sentences.length)
      setScenario(scenario, 'test')
      navigate(mode === 'practice' ? '/practice' : '/conversation')
    } catch (error) {
      console.error(error)
      setNotice('실전 문장을 준비하지 못했어요. 다시 시도해주세요.')
    } finally {
      setLoadingMode(null)
    }
  }

  return (
    <AppShell active="practice" title="상황별 시나리오" description="상황을 고르면 그에 맞는 문장이 나와요">
      {notice && (
        <div role="status" aria-live="polite"
          className="fixed left-1/2 top-4 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 shadow-lg">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice('')} aria-label="안내 닫기" className="text-amber-500 hover:text-amber-700">✕</button>
        </div>
      )}
      {/* 어디에서 대화하나요? (225:293) */}
      <section className={CARD}>
        <p className="text-[17px] font-bold leading-figma text-ink">어디에서 대화하나요?</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SITUATIONS.map((item) => {
            const active = situation === item
            return (
              <button key={item} type="button" onClick={() => setSituation(item)} aria-pressed={active}
                className={active
                  ? 'rounded-14 border-[2.5px] border-primary-500 bg-primary-100 py-[18px] text-[16px] font-bold leading-figma text-primary-700'
                  : 'rounded-14 border-2 border-b-5 border-line bg-white py-[18px] text-[16px] font-bold leading-figma text-ink transition-all hover:border-primary-300 active:translate-y-[1px] active:border-b-2'}>{/* Figma: 비활성=3D 하단테두리 */}
                {item}
              </button>
            )
          })}
        </div>
        {situation === CUSTOM && (
          <input value={customSituation} onChange={(e) => setCustomSituation(e.target.value)}
            className="input-field" placeholder="예: 면접에서 질문에 답하기" />
        )}
      </section>

      {/* 난이도 (225:311) */}
      <section className={CARD}>
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">난이도</p>
          <span className="text-[13px] text-ink-muted">추천 {recommended || level}단계</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5].map((item) => (
            <button key={item} type="button" onClick={() => { levelTouched.current = true; setLevel(item) }} aria-pressed={level === item}
              className={`rounded-full px-4 py-[9px] text-[13.5px] font-bold leading-figma transition ${level === item ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}>
              {item}단계
            </button>
          ))}
        </div>
      </section>

      {/* 어떻게 연습할까요? (225:326) — 모드 카드는 제목·부제만(225:330 / 225:333) */}
      <section className={CARD}>
        <p className="text-[17px] font-bold leading-figma text-ink">어떻게 연습할까요?</p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <button type="button" onClick={() => start('practice')} disabled={loadingMode || locks.practice || !effectiveSituation}
            aria-busy={loadingMode === 'practice'} title={locks.practice ? LOCK_HINT.practice : undefined}
            className="flex flex-1 flex-col gap-1.5 rounded-16 bg-primary-100 p-5 text-left leading-figma text-primary-700 transition hover:brightness-95 disabled:opacity-50">
            <span className="text-[17px] font-bold">문장 테스트</span>
            <span className="text-[13px] opacity-80">{loadingMode === 'practice' ? '준비 중…' : '정해진 문장을 읽어요'}</span>
          </button>
          <button type="button" onClick={() => start('conversation')} disabled={loadingMode || locks.conversation || !effectiveSituation}
            aria-busy={loadingMode === 'conversation'} title={locks.conversation ? LOCK_HINT.conversation : undefined}
            className="flex flex-1 flex-col gap-1.5 rounded-16 bg-indigo-100 p-5 text-left leading-figma text-indigo-600 transition hover:brightness-95 disabled:opacity-50">
            <span className="text-[17px] font-bold">AI 대화</span>
            <span className="text-[13px] opacity-80">{loadingMode === 'conversation' ? '준비 중…' : '상황에 맞춰 대화해요'}</span>
          </button>
        </div>
      </section>
    </AppShell>
  )
}
