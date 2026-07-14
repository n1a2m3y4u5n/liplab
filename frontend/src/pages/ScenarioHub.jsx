import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import DomainPageShell from '../components/DomainPageShell'
import useStore from '../store/useStore'

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
      alert(mode === 'practice' ? '음절·단어 학습을 완료하면 문장 실전이 열려요.' : '문장 독화를 완료하면 대화 실전이 열려요.')
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
    <DomainPageShell domain="learn" title="문장·대화 실전" description="연습할 상황과 난이도를 고르면 AI가 독화 문장과 대화를 준비합니다.">
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <section className="rounded-[24px] border border-slate-200 bg-white p-5 sm:p-7">
          <h2 className="text-lg font-black">어디에서 대화하나요?</h2>
          <p className="mt-1 text-sm text-slate-500">실제로 자주 마주치는 상황을 선택하세요.</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {SITUATIONS.map((item) => (
              <button key={item} type="button" onClick={() => setSituation(item)} aria-pressed={situation === item}
                className={`rounded-full border px-4 py-2 text-sm font-bold transition ${situation === item ? 'border-sky-600 bg-sky-600 text-white' : 'border-slate-200 text-slate-600 hover:border-sky-300 hover:bg-sky-50'}`}>
                {item}
              </button>
            ))}
          </div>
          {situation === '직접 입력' && (
            <label className="mt-4 block">
              <span className="mb-2 block text-sm font-bold text-slate-700">직접 입력할 상황</span>
              <input value={customSituation} onChange={(event) => setCustomSituation(event.target.value)} className="input-field" placeholder="예: 면접에서 질문에 답하기" />
            </label>
          )}

          <div className="mt-7 border-t border-slate-100 pt-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-black">난이도</h2>
              <span className="text-xs font-bold text-sky-700">추천 {recommended || level}단계</span>
            </div>
            <div className="mt-3 grid grid-cols-5 gap-2">
              {[1, 2, 3, 4, 5].map((item) => (
                <button key={item} type="button" onClick={() => setLevel(item)} aria-pressed={level === item}
                  className={`rounded-xl border py-3 text-sm font-black transition ${level === item ? 'border-slate-950 bg-slate-950 text-white' : 'border-slate-200 text-slate-600 hover:border-slate-400'}`}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        </section>

        <aside className="space-y-3">
          <button type="button" onClick={() => start('practice')} disabled={loadingMode || locks.practice || !effectiveSituation}
            className="w-full rounded-[22px] bg-sky-600 p-5 text-left text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500">
            <span className="text-xs font-bold text-sky-100">문장 테스트</span>
            <span className="mt-2 block text-xl font-black">입모양을 읽고 답하기</span>
            <span className="mt-2 block text-sm text-sky-100">주관식·선택형·서술형 문제</span>
            <span className="mt-5 block text-sm font-black">{loadingMode === 'practice' ? '준비 중…' : locks.practice ? '잠김' : '시작하기 →'}</span>
          </button>
          <button type="button" onClick={() => start('conversation')} disabled={loadingMode || locks.conversation || !effectiveSituation}
            className="w-full rounded-[22px] bg-violet-600 p-5 text-left text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500">
            <span className="text-xs font-bold text-violet-100">AI 대화</span>
            <span className="mt-2 block text-xl font-black">대화를 이어가며 독화하기</span>
            <span className="mt-2 block text-sm text-violet-100">상황에 맞는 실시간 대화</span>
            <span className="mt-5 block text-sm font-black">{loadingMode === 'conversation' ? '준비 중…' : locks.conversation ? '잠김' : '시작하기 →'}</span>
          </button>
        </aside>
      </div>
    </DomainPageShell>
  )
}
