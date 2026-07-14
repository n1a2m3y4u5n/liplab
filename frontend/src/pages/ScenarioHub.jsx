import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import useStore from '../store/useStore'
import LearnHeader from '../components/LearnHeader'

const SITUATIONS = ['카페', '병원', '식당', '은행', '쇼핑', '대중교통', '직장', '학교', '직접 입력']
const QUESTION_TYPES = ['test', 'test-multiple', 'essay']

function shuffledTypes(length) {
  return Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length])
    .sort(() => Math.random() - 0.5)
}

export default function ScenarioHub() {
  const navigate = useNavigate()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const [situation, setSituation] = useState('카페')
  const [customSituation, setCustomSituation] = useState('')
  const [level, setLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [recommended, setRecommended] = useState(null)
  const [locks, setLocks] = useState({ practice: false, conversation: false })
  const [loadingMode, setLoadingMode] = useState(null)

  useEffect(() => {
    curriculumAPI.getRecommendedLevel()
      .then((result) => {
        setRecommended(result.recommended_level)
        setLevel(result.recommended_level)
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
      alert(mode === 'practice' ? '단어 학습을 완료하면 문장 학습이 열려요.' : '문장 학습을 완료하면 대화 실전이 열려요.')
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
      alert('실전 문장을 준비하지 못했어요. 다시 시도해주세요.')
    } finally {
      setLoadingMode(null)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="reading"
        title="문장 학습"
        description="연습할 상황과 난이도를 고르면 AI가 독화 문장과 대화를 준비합니다"
        onExit={() => navigate('/dashboard')}
      />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <section className="card">
            <h2 className="text-lg font-bold text-gray-900">어디에서 대화하나요?</h2>
            <p className="mt-1 text-sm text-gray-500">실제로 자주 마주치는 상황을 선택하세요.</p>
            <div className="mt-5 flex flex-wrap gap-2">
              {SITUATIONS.map((item) => (
                <button key={item} type="button" onClick={() => setSituation(item)} aria-pressed={situation === item}
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition-all ${situation === item ? 'border-primary-500 bg-primary-500 text-white' : 'border-gray-200 text-gray-600 hover:border-primary-300 hover:bg-primary-50'}`}>
                  {item}
                </button>
              ))}
            </div>
            {situation === '직접 입력' && (
              <label className="mt-4 block">
                <span className="label">직접 입력할 상황</span>
                <input value={customSituation} onChange={(event) => setCustomSituation(event.target.value)} className="input-field" placeholder="예: 면접에서 질문에 답하기" />
              </label>
            )}

            <div className="mt-7 border-t border-gray-100 pt-6">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-gray-900">난이도</h2>
                <span className="text-xs font-semibold text-primary-600">추천 {recommended || level}단계</span>
              </div>
              <div className="mt-3 grid grid-cols-5 gap-2">
                {[1, 2, 3, 4, 5].map((item) => (
                  <button key={item} type="button" onClick={() => setLevel(item)} aria-pressed={level === item}
                    className={`rounded-xl border-2 py-3 text-sm font-bold transition-all ${level === item ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <aside className="space-y-3">
            <button type="button" onClick={() => start('practice')} disabled={loadingMode || locks.practice || !effectiveSituation}
              className="card w-full text-left transition-all hover:border-primary-300 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50">
              <span className="text-xs font-semibold text-primary-600">문장 테스트</span>
              <span className="mt-2 block text-xl font-bold text-gray-900">입모양을 읽고 답하기</span>
              <span className="mt-2 block text-sm text-gray-500">주관식·선택형·서술형 문제</span>
              <span className="mt-5 block text-sm font-bold text-primary-600">{loadingMode === 'practice' ? '준비 중…' : locks.practice ? '🔒 잠김' : '시작하기 →'}</span>
            </button>
            <button type="button" onClick={() => start('conversation')} disabled={loadingMode || locks.conversation || !effectiveSituation}
              className="card w-full text-left transition-all hover:border-purple-300 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50">
              <span className="text-xs font-semibold text-purple-600">AI 대화</span>
              <span className="mt-2 block text-xl font-bold text-gray-900">대화를 이어가며 독화하기</span>
              <span className="mt-2 block text-sm text-gray-500">상황에 맞는 실시간 대화</span>
              <span className="mt-5 block text-sm font-bold text-purple-600">{loadingMode === 'conversation' ? '준비 중…' : locks.conversation ? '🔒 잠김' : '시작하기 →'}</span>
            </button>
          </aside>
        </div>
      </main>
    </div>
  )
}
