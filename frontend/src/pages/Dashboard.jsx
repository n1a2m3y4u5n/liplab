import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI } from '../api'

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

// ── GitHub 스타일 활동 캘린더 ─────────────────────────────────────────────────
function ActivityCalendar({ data }) {
  const today = new Date()
  // 오늘 포함 90일
  const days = useMemo(() => {
    const arr = []
    for (let i = 89; i >= 0; i--) {
      const d = new Date(today)
      d.setDate(today.getDate() - i)
      const key = d.toISOString().slice(0, 10)
      arr.push({ key, count: data[key] || 0 })
    }
    return arr
  }, [data])

  const getColor = (count) => {
    if (count === 0) return 'bg-gray-100'
    if (count <= 2)  return 'bg-green-200'
    if (count <= 5)  return 'bg-green-400'
    return 'bg-green-600'
  }

  // 7행 열 배열로 변환 (일요일 시작)
  const startPad = new Date(days[0].key).getDay() // 0=Sun
  const cells = [...Array(startPad).fill(null), ...days]

  return (
    <div>
      <div className="flex gap-0.5 flex-wrap">
        {cells.map((cell, i) =>
          cell === null ? (
            <div key={`pad-${i}`} className="w-3.5 h-3.5" />
          ) : (
            <div
              key={cell.key}
              title={`${cell.key}: ${cell.count}문장`}
              className={`w-3.5 h-3.5 rounded-sm ${getColor(cell.count)} transition-colors cursor-default`}
            />
          )
        )}
      </div>
      <div className="flex items-center gap-1 mt-2 text-xs text-gray-400">
        <span>적음</span>
        {['bg-gray-100','bg-green-200','bg-green-400','bg-green-600'].map(c => (
          <div key={c} className={`w-3 h-3 rounded-sm ${c}`} />
        ))}
        <span>많음</span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  const user = useStore((state) => state.user)
  const logout = useStore((state) => state.logout)
  const setScenario = useStore((state) => state.setScenario)
  const statistics = useStore((state) => state.statistics)
  const setStatistics = useStore((state) => state.setStatistics)

  const [selectedSituation, setSelectedSituation] = useState('카페')
  const [customSituation, setCustomSituation] = useState('')
  const [selectedLevel, setSelectedLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [loading, setLoading] = useState(false)
  const [statsLoading, setStatsLoading] = useState(true)
  const [calendarData, setCalendarData] = useState({})
  const [mode, setMode] = useState('test')

  useEffect(() => {
    loadStatistics()
    loadCalendar()
  }, [])

  const loadStatistics = async () => {
    try {
      const stats = await learningAPI.getStatistics()
      setStatistics(stats)
    } catch (error) {
      console.error('Failed to load statistics:', error)
    } finally {
      setStatsLoading(false)
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

  const startPractice = async () => {
    // 복습 모드: 틀린 문장 가져오기
    if (mode === 'review') {
      setLoading(true)
      try {
        const sentences = await learningAPI.getReviewSentences()
        if (sentences.length === 0) {
          alert('복습할 문장이 없어요! 먼저 테스트를 진행해보세요.')
          return
        }
        const scenario = {
          situation: '복습',
          level: 1,
          sentences: sentences.map(s => s.sentence),
          scenario_id: `review_${Date.now()}`,
        }
        setScenario(scenario, 'test')
        navigate('/practice')
      } catch (e) {
        alert('복습 문장을 불러오지 못했습니다.')
      } finally {
        setLoading(false)
      }
      return
    }

    if (!effectiveSituation.trim()) {
      alert('상황을 입력해주세요.')
      return
    }
    setLoading(true)
    try {
      const scenario = await learningAPI.getScenario(effectiveSituation, selectedLevel)
      setScenario(scenario, mode)
      if (mode === 'conversation') {
        navigate('/conversation')
      } else {
        navigate('/practice')
      }
    } catch (error) {
      alert('시나리오 생성에 실패했습니다. 다시 시도해주세요.')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const MODES = [
    { id: 'study',         label: '학습 모드',  desc: '문장 보며 입모양 익히기' },
    { id: 'test',          label: '주관식',     desc: '직접 타이핑해서 맞추기' },
    { id: 'test-multiple', label: '4지선다',    desc: '4개 보기 중 정답 선택' },
    { id: 'review',        label: '복습',       desc: '틀린 문장만 다시 풀기' },
    { id: 'conversation',  label: '대화 연습',  desc: 'AI와 실전 대화' },
  ]

  const startLabel = {
    study: '학습 시작',
    test: '테스트 시작',
    'test-multiple': '4지선다 시작',
    review: '복습 시작',
    conversation: '대화 연습 시작',
  }[mode]

  const showSituationPicker = mode !== 'review' && mode !== 'conversation' || mode === 'conversation'
  const hideSituationForReview = mode === 'review'

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <h1 className="text-3xl font-bold text-primary-600">LIPLAB</h1>
            <div className="flex items-center gap-2">
              <button
                onClick={() => navigate('/bookmarks')}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors border border-gray-200 rounded-lg"
              >
                ★ 북마크
              </button>
              <button
                onClick={() => navigate('/guide')}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors border border-gray-200 rounded-lg"
              >
                사용법
              </button>
              <button
                onClick={() => navigate('/analysis')}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors border border-gray-200 rounded-lg"
              >
                분석
              </button>
              <div className="text-right hidden sm:block">
                <p className="text-xs text-gray-500">안녕하세요,</p>
                <p className="font-semibold text-gray-900 text-sm">{user?.username}님</p>
              </div>
              <button
                onClick={handleLogout}
                className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors border border-gray-200 rounded-lg"
              >
                로그아웃
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* 스트릭 배너 */}
        <AnimatePresence>
          {(user?.streak_count || 0) > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 flex items-center gap-3 px-5 py-3 bg-gradient-to-r from-orange-400 to-amber-400 rounded-2xl text-white shadow"
            >
              <span className="text-2xl">🔥</span>
              <div>
                <p className="font-bold text-lg">{user.streak_count}일째 연속 학습 중!</p>
                <p className="text-xs text-orange-100">
                  {user.streak_count >= 10
                    ? `대단해요! 스트릭 보너스 XP ${Math.min(Math.round(user.streak_count * 10), 200)}% 적용 중`
                    : '꾸준히 연습하면 스트릭 보너스 XP를 받아요!'}
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Stats Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="card"
          >
            <h3 className="text-sm font-semibold text-gray-500 mb-3">학습 레벨</h3>
            <div className="flex items-end gap-3">
              <div className="text-5xl font-bold text-primary-600">
                {user?.current_level || 1}
              </div>
              <div className="mb-1">
                <p className="text-xs text-gray-500">{user?.total_xp || 0} XP</p>
                <div className="w-24 bg-gray-200 rounded-full h-2 mt-1">
                  <div
                    className="bg-primary-500 h-full rounded-full transition-all duration-500"
                    style={{ width: `${((user?.total_xp || 0) % 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="card"
          >
            <h3 className="text-sm font-semibold text-gray-500 mb-3">학습 통계</h3>
            {statsLoading ? (
              <div className="flex justify-center py-4">
                <div className="w-7 h-7 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">총 연습 횟수</span>
                  <span className="font-semibold">{statistics?.total_sessions || 0}회</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">평균 점수</span>
                  <span className="font-semibold text-primary-600">
                    {statistics?.average_score || 0}점
                  </span>
                </div>
              </div>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card"
          >
            <h3 className="text-sm font-semibold text-gray-500 mb-3">취약 입모양</h3>
            {!statsLoading && statistics?.weak_visemes?.length > 0 ? (
              <ul className="space-y-1.5">
                {statistics.weak_visemes.slice(0, 3).map((wv, idx) => (
                  <li key={idx} className="flex justify-between items-center text-sm">
                    <span className="text-gray-600 capitalize">{wv.feature}</span>
                    <span className="text-red-500 font-medium">{wv.error_rate}% 오답</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400">아직 데이터가 없습니다.</p>
            )}
          </motion.div>
        </div>

        {/* 활동 캘린더 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="card mb-8"
        >
          <h3 className="text-sm font-semibold text-gray-500 mb-4">최근 90일 학습 현황</h3>
          <ActivityCalendar data={calendarData} />
        </motion.div>

        {/* Practice Setup */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card max-w-3xl mx-auto"
        >
          {/* Mode toggle */}
          <div className="flex gap-1 mb-6 p-1 bg-gray-100 rounded-xl overflow-x-auto">
            {MODES.map((m) => (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className={`flex-1 min-w-0 py-2 px-1 rounded-lg text-xs font-medium transition-all leading-tight whitespace-nowrap ${
                  mode === m.id
                    ? 'bg-white text-primary-600 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <div>{m.label}</div>
                <div className={`text-xs font-normal mt-0.5 hidden sm:block ${mode === m.id ? 'text-primary-400' : 'text-gray-400'}`}>
                  {m.desc}
                </div>
              </button>
            ))}
          </div>

          <h2 className="text-xl font-bold mb-5 text-gray-900">
            {startLabel}
          </h2>

          {/* Mode hints */}
          {mode === 'study' && (
            <div className="mb-5 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
              문장을 보면서 입모양을 익힙니다. 채점 없이 반복 학습할 수 있어요.
            </div>
          )}
          {mode === 'test-multiple' && (
            <div className="mb-5 p-3 bg-purple-50 border border-purple-200 rounded-lg text-sm text-purple-700">
              4개 보기 중 입모양에 맞는 문장을 선택하세요. 타이핑 없이 빠르게 연습할 수 있어요.
            </div>
          )}
          {mode === 'review' && (
            <div className="mb-5 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
              이전 테스트에서 틀린 문장들만 모아서 다시 연습합니다.
            </div>
          )}
          {mode === 'conversation' && (
            <div className="mb-5 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
              AI와 자연스러운 대화를 나누며 독화를 연습합니다. AI의 말을 읽고 답변해보세요.
            </div>
          )}

          <div className="space-y-5">
            {/* Situation Selection — 복습 모드는 숨김 */}
            {!hideSituationForReview && (
              <div>
                <label className="label">상황 선택</label>
                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                  {PRESET_SITUATIONS.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedSituation(s.id)}
                      className={`p-3 rounded-lg border-2 transition-all text-center ${
                        selectedSituation === s.id
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300 bg-white'
                      }`}
                    >
                      <div className="text-2xl mb-1">{s.icon}</div>
                      <div className="text-xs font-medium leading-tight">{s.label}</div>
                    </button>
                  ))}
                </div>

                <AnimatePresence>
                  {selectedSituation === '직접 입력' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3"
                    >
                      <input
                        type="text"
                        value={customSituation}
                        onChange={(e) => setCustomSituation(e.target.value)}
                        className="input-field"
                        placeholder="상황을 직접 입력하세요 (예: 헬스장에서 트레이너와 대화, 면접 준비...)"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        어떤 상황이든 AI가 맞춤형 문제를 만들어줍니다
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            {/* Level Selection — 복습 모드는 숨김 */}
            {!hideSituationForReview && (
              <div>
                <label className="label">난이도</label>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map((level) => (
                    <button
                      key={level}
                      onClick={() => setSelectedLevel(level)}
                      className={`flex-1 py-2.5 rounded-lg border-2 font-medium transition-all text-sm ${
                        selectedLevel === level
                          ? 'border-primary-500 bg-primary-500 text-white'
                          : 'border-gray-200 hover:border-gray-300 text-gray-700'
                      }`}
                    >
                      {level}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-1.5">추천 레벨: {Math.min(user?.current_level || 1, 5)}</p>
              </div>
            )}

            {/* Start Button */}
            <button
              onClick={startPractice}
              disabled={
                loading ||
                (mode !== 'review' && selectedSituation === '직접 입력' && !customSituation.trim())
              }
              className="btn-primary w-full py-3.5 text-base disabled:opacity-60"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  {mode === 'review' ? '복습 문장 불러오는 중...' : 'AI가 시나리오를 만드는 중...'}
                </span>
              ) : startLabel}
            </button>
          </div>
        </motion.div>
      </main>
    </div>
  )
}
