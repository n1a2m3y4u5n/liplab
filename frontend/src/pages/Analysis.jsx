import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { learningAPI } from '../api'

function AccuracyBar({ name, accuracy, attempts }) {
  const color =
    accuracy >= 80 ? 'bg-green-500' :
    accuracy >= 60 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-700 font-medium">{name}</span>
        <span className="text-gray-500">{accuracy}점 <span className="text-xs text-gray-400">({attempts}회)</span></span>
      </div>
      <div className="bg-gray-100 rounded-full h-3 overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(accuracy, 100)}%` }}
          transition={{ duration: 0.6, delay: 0.1 }}
        />
      </div>
    </div>
  )
}

export default function Analysis() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [resetting, setResetting] = useState(false)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      const result = await learningAPI.getAnalysis()
      setData(result)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm('모든 연습 기록을 초기화하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return
    setResetting(true)
    try {
      await learningAPI.resetAnalysis()
      await load()
    } catch (e) {
      console.error(e)
      alert('초기화에 실패했습니다.')
    } finally {
      setResetting(false)
    }
  }

  useEffect(() => { load() }, [])

  // Check if we have meaningful variance in the data
  const hasVariance = data?.viseme_stats?.length > 0 &&
    data.viseme_stats.some(v => v.accuracy > 0)

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">학습 분석</h1>
            <p className="text-sm text-gray-500">내 독화 능력 분석 및 맞춤 학습 조언</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              disabled={resetting || loading}
              className="text-xs px-3 py-1.5 rounded-lg border border-red-200 text-red-500 hover:bg-red-50 transition-colors disabled:opacity-40"
            >
              {resetting ? '초기화 중...' : '기록 초기화'}
            </button>
            <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-800 text-sm">
              ← 대시보드
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3">
            <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
            <p className="text-gray-500">분석 중...</p>
          </div>
        ) : !data ? (
          <div className="card text-center py-12">
            <p className="text-gray-500">데이터를 불러오지 못했습니다.</p>
          </div>
        ) : (
          <>
            {/* Overview */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-3 gap-4">
              {[
                { label: '총 연습', value: `${data.total_sessions}회` },
                { label: '평균 점수', value: `${data.average_score}점` },
                { label: '분석 항목', value: `${data.viseme_stats?.length ?? 0}개` },
              ].map((s) => (
                <div key={s.label} className="card text-center">
                  <p className="text-3xl font-bold text-primary-600">{s.value}</p>
                  <p className="text-sm text-gray-500 mt-1">{s.label}</p>
                </div>
              ))}
            </motion.div>

            {/* Accuracy by viseme type */}
            {data.viseme_stats?.length > 0 ? (
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card">
                <h2 className="text-lg font-bold text-gray-900 mb-2">입모양 유형별 평균 점수</h2>
                <p className="text-xs text-gray-400 mb-5">
                  각 입모양 유형이 포함된 문장에서의 평균 테스트 점수입니다. 점수가 낮을수록 해당 유형이 어려운 것입니다.
                </p>
                {!hasVariance && (
                  <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
                    아직 모든 항목의 점수가 낮습니다. 더 연습해서 점수가 오르면 강점과 약점을 파악할 수 있어요.
                  </div>
                )}
                <div className="space-y-4">
                  {[...data.viseme_stats].sort((a, b) => b.accuracy - a.accuracy).map((v) => (
                    <AccuracyBar key={v.viseme_id} name={v.name} accuracy={v.accuracy} attempts={v.attempts} />
                  ))}
                </div>
              </motion.div>
            ) : (
              <div className="card text-center py-8 text-gray-400">
                테스트를 완료하면 입모양 유형별 점수가 표시됩니다.
              </div>
            )}

            {/* Strengths & Weaknesses */}
            {hasVariance && (data.strengths?.length > 0 || data.weaknesses?.length > 0) && (
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="card border-l-4 border-green-400">
                  <h3 className="font-semibold text-green-700 mb-3">잘하는 입모양</h3>
                  {data.strengths?.length > 0 ? (
                    <ul className="space-y-2">
                      {data.strengths.map((s) => (
                        <li key={s.viseme_id} className="flex justify-between text-sm">
                          <span className="text-gray-700">{s.name}</span>
                          <span className="font-semibold text-green-600">{s.accuracy}점</span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="text-sm text-gray-400">데이터 부족</p>}
                </div>
                <div className="card border-l-4 border-red-400">
                  <h3 className="font-semibold text-red-700 mb-3">취약한 입모양</h3>
                  {data.weaknesses?.length > 0 ? (
                    <ul className="space-y-2">
                      {data.weaknesses.map((w) => (
                        <li key={w.viseme_id} className="flex justify-between text-sm">
                          <span className="text-gray-700">{w.name}</span>
                          <span className="font-semibold text-red-500">{w.accuracy}점</span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="text-sm text-gray-400">데이터 부족</p>}
                </div>
              </motion.div>
            )}

            {/* Phoneme Confusion Analysis */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="card">
              <h2 className="text-lg font-bold text-gray-900 mb-2">음소 혼동 분석</h2>
              <p className="text-xs text-gray-400 mb-4">자주 헷갈리는 입모양 조합입니다. 해당 음소에 집중해서 연습해보세요.</p>
              {data.confusions?.length > 0 ? (
                <div className="space-y-2">
                  {data.confusions.map((c, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                      <span className="text-2xl font-bold text-red-500 w-8 text-center">{c.correct}</span>
                      <span className="text-gray-400">→</span>
                      <span className="text-2xl font-bold text-blue-500 w-8 text-center">{c.confused_as}</span>
                      <div className="flex-1">
                        <p className="text-sm text-gray-700 font-medium">
                          <span className="text-red-500">{c.correct}</span>를{' '}
                          <span className="text-blue-500">{c.confused_as}</span>로 읽은 경우
                        </p>
                        <p className="text-xs text-gray-400">{c.count}회 발생</p>
                      </div>
                      <div className="w-16 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-red-400 h-full rounded-full"
                          style={{ width: `${Math.min((c.count / (data.confusions[0]?.count || 1)) * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 py-4 text-center">
                  아직 분석할 혼동 패턴이 없습니다. 더 많은 테스트 후 확인해보세요.
                </p>
              )}
            </motion.div>

            {/* AI Recommendation */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-gray-900">AI 맞춤 학습 조언</h2>
                <button
                  onClick={() => load(true)}
                  disabled={refreshing}
                  className="text-xs px-3 py-1.5 rounded-full bg-primary-50 text-primary-600 hover:bg-primary-100 transition-colors disabled:opacity-50"
                >
                  {refreshing ? '분석 중...' : '↻ 새로 분석'}
                </button>
              </div>
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl">
                <p className="text-sm text-blue-900 leading-relaxed whitespace-pre-line">
                  {data.recommendation || '분석 데이터가 부족합니다.'}
                </p>
              </div>
            </motion.div>
          </>
        )}
      </main>
    </div>
  )
}
