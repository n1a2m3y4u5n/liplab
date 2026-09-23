import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'

/**
 * 상황별 시나리오 (Figma 리디자인 09 연습기능) — 셸 안의 피커.
 * 상황·난이도를 고르고 모드(문장 테스트 / AI 대화)를 선택하면 기존 학습 흐름으로 진입한다.
 */
const SITUATIONS = ['카페', '병원', '식당', '은행', '쇼핑', '대중교통', '직장', '학교', '직접 입력']
const QUESTION_TYPES = ['test', 'test-multiple', 'essay']

function shuffledTypes(length) {
  return Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length])
    .sort(() => Math.random() - 0.5)
}

export default function ScenarioHub() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  // 회차 히스토리 등에서 ?situation=병원 으로 들어오면 그 상황을 미리 고른다(목록에 있을 때만).
  const preset = searchParams.get('situation')
  const [situation, setSituation] = useState(preset && SITUATIONS.includes(preset) ? preset : '카페')
  const [customSituation, setCustomSituation] = useState('')
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

  const effectiveSituation = situation === '직접 입력' ? customSituation.trim() : situation

  const start = async (mode) => {
    if (locks[mode]) {
      setNotice(mode === 'practice' ? '단어 학습을 완료하면 문장 학습이 열려요.' : '문장 학습을 완료하면 대화 실전이 열려요.')
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
      {/* 어디에서 대화하나요? */}
      <section className="card-flat w-full">
        <p className="text-[17px] font-bold text-ink">어디에서 대화하나요?</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SITUATIONS.map((item) => {
            const active = situation === item
            return (
              <button key={item} type="button" onClick={() => setSituation(item)} aria-pressed={active}
                className={active
                  ? 'rounded-[14px] border-[2.5px] border-primary-500 bg-primary-100 py-[18px] text-[16px] font-bold text-primary-700'
                  : 'rounded-[14px] border-2 border-b-[5px] border-line bg-white py-[18px] text-[16px] font-bold text-ink transition-all hover:border-primary-300 active:translate-y-[1px] active:border-b-2'}>{/* Figma: 비활성=3D 하단테두리 */}
                {item}
              </button>
            )
          })}
        </div>
        {situation === '직접 입력' && (
          <input value={customSituation} onChange={(e) => setCustomSituation(e.target.value)}
            className="input-field mt-3" placeholder="예: 면접에서 질문에 답하기" />
        )}
      </section>

      {/* 난이도 */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">난이도</p>
          <span className="text-[13px] text-ink-muted">추천 {recommended || level}단계</span>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5].map((item) => (
            <button key={item} type="button" onClick={() => { levelTouched.current = true; setLevel(item) }} aria-pressed={level === item}
              className={`rounded-full px-4 py-2 text-[13.5px] font-bold transition ${level === item ? 'bg-primary-500 text-white' : 'bg-gray-100 text-ink-muted hover:bg-gray-200'}`}>
              {item}단계
            </button>
          ))}
        </div>
      </section>

      {/* 어떻게 연습할까요? */}
      <section className="card-flat w-full">
        <p className="text-[17px] font-bold text-ink">어떻게 연습할까요?</p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <button type="button" onClick={() => start('practice')} disabled={loadingMode || locks.practice || !effectiveSituation}
            className="flex-1 rounded-2xl bg-primary-100 p-5 text-left text-primary-700 transition hover:brightness-95 disabled:opacity-50">
            <p className="text-[17px] font-bold">문장 테스트</p>
            <p className="mt-1 text-[13px] opacity-80">정해진 문장을 읽어요</p>
            <p className="mt-3 text-[13px] font-bold">{loadingMode === 'practice' ? '준비 중…' : locks.practice ? '🔒 잠김' : '시작하기 →'}</p>
          </button>
          <button type="button" onClick={() => start('conversation')} disabled={loadingMode || locks.conversation || !effectiveSituation}
            className="flex-1 rounded-2xl bg-indigo-100 p-5 text-left text-indigo-600 transition hover:brightness-95 disabled:opacity-50">
            <p className="text-[17px] font-bold">AI 대화</p>
            <p className="mt-1 text-[13px] opacity-80">상황에 맞춰 대화해요</p>
            <p className="mt-3 text-[13px] font-bold">{loadingMode === 'conversation' ? '준비 중…' : locks.conversation ? '🔒 잠김' : '시작하기 →'}</p>
          </button>
        </div>
      </section>
    </AppShell>
  )
}
