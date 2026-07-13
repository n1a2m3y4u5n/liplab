import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { learningAPI, speakAPI } from '../api'

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

function Spinner({ label = '분석 중...' }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3">
      <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
      <p className="text-gray-500">{label}</p>
    </div>
  )
}

// ── 말하기(발화) 분석 — 독화 분석과 분리 ──────────────────────────────────────
function SpeakAnalysis({ loading, d, onRefresh, refreshing }) {
  if (loading) return <Spinner label="말하기 분석 중..." />
  if (!d) return <div className="card text-center py-12 text-gray-500">데이터를 불러오지 못했습니다.</div>
  if (!d.total) {
    return (
      <div className="card text-center py-12 text-gray-400">
        아직 말하기 기록이 없어요.<br />대시보드의 <b className="text-rose-500">말하기 연습</b>에서 단계를 진행하면 여기에 분석이 쌓여요.
      </div>
    )
  }
  const maxConf = d.weak_sounds?.[0]?.count || 1
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: '총 발화', value: `${d.total}회` },
          { label: '평균 점수', value: `${d.avg_score}점` },
          { label: '평균 크기', value: `${d.avg_loudness}/100` },
        ].map((s) => (
          <div key={s.label} className="card text-center">
            <p className="text-3xl font-bold text-rose-500">{s.value}</p>
            <p className="text-sm text-gray-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* 자주 틀리는 소리 */}
      <div className="card">
        <h2 className="text-lg font-bold text-gray-900 mb-2">자주 틀리는 소리</h2>
        <p className="text-xs text-gray-400 mb-4">내 발음이 다르게 인식된 소리예요. 그 입모양·조음을 집중해서 연습해보세요.</p>
        {d.weak_sounds?.length > 0 ? (
          <div className="space-y-2">
            {d.weak_sounds.map((c, i) => (
              <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <span className="text-2xl font-bold text-rose-500 w-8 text-center">{c.correct}</span>
                <span className="text-gray-400">→</span>
                <span className="text-2xl font-bold text-blue-500 w-8 text-center">{c.confused_as}</span>
                <div className="flex-1">
                  <p className="text-sm text-gray-700 font-medium">
                    <span className="text-rose-500">{c.correct}</span>를{' '}
                    <span className="text-blue-500">{c.confused_as}</span>로 발음한 경우
                  </p>
                  <p className="text-xs text-gray-400">{c.count}회 발생</p>
                </div>
                <div className="w-16 bg-gray-200 rounded-full h-2">
                  <div className="bg-rose-400 h-full rounded-full" style={{ width: `${Math.min((c.count / maxConf) * 100, 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400 py-4 text-center">아직 뚜렷한 발음 오류 패턴이 없어요. 좋아요!</p>
        )}
      </div>

      {/* 억양·크기 */}
      <div className="card">
        <h2 className="text-lg font-bold text-gray-900 mb-2">억양·크기</h2>
        <p className="text-xs text-gray-400 mb-4">스스로 듣기 어려운 부분이에요. 최근 발화의 목소리 크기와 억양 폭이에요.</p>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="p-3 rounded-xl bg-rose-50 text-center">
            <p className="text-2xl font-bold text-rose-500">{d.avg_loudness}<span className="text-sm text-gray-400">/100</span></p>
            <p className="text-xs text-gray-500 mt-0.5">평균 목소리 크기 {d.avg_loudness < 40 ? '· 작은 편' : '· 적당'}</p>
          </div>
          <div className="p-3 rounded-xl bg-indigo-50 text-center">
            <p className="text-2xl font-bold text-indigo-500">{d.avg_pitch_range}<span className="text-sm text-gray-400">Hz</span></p>
            <p className="text-xs text-gray-500 mt-0.5">평균 억양 폭 {d.avg_pitch_range < 25 ? '· 평평한 편' : '· 살아있음'}</p>
          </div>
        </div>
        {d.trend?.length > 1 && (
          <div>
            <p className="text-xs text-gray-400 mb-1">최근 발화 점수 추세</p>
            <div className="flex items-end gap-1 h-16">
              {d.trend.map((t, i) => (
                <div key={i} className="flex-1 bg-rose-400/70 rounded-t" style={{ height: `${Math.max(4, Math.min(t.score, 100))}%` }} title={`${t.score}점`} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 단계별 숙달 */}
      <div className="card">
        <h2 className="text-lg font-bold text-gray-900 mb-3">단계별 숙달</h2>
        <div className="space-y-3">
          {d.stages?.map((s) => (
            <div key={s.stage}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-700 font-medium">{s.icon} {s.stage}단계 · {s.title}</span>
                <span className="text-gray-500">{s.mastery_score}% <span className="text-xs text-gray-400">({s.attempts}회)</span>{s.status === 'mastered' && ' ✓'}</span>
              </div>
              <div className="bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div className={`h-full rounded-full ${s.status === 'mastered' ? 'bg-green-500' : 'bg-rose-400'}`} style={{ width: `${Math.min(s.mastery_score, 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 팁 */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-gray-900">맞춤 발음 팁</h2>
          <button onClick={onRefresh} disabled={refreshing}
            className="text-xs px-3 py-1.5 rounded-full bg-rose-50 text-rose-500 hover:bg-rose-100 transition-colors disabled:opacity-50">
            {refreshing ? '분석 중...' : '↻ 새로 분석'}
          </button>
        </div>
        <ul className="space-y-2">
          {d.tips?.map((t, i) => (
            <li key={i} className="p-3 bg-rose-50 rounded-lg text-sm text-rose-900">🗣️ {t}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function Analysis() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('read')      // 'read'(독화) | 'speak'(말하기)
  const [data, setData] = useState(null)       // 독화
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [speak, setSpeak] = useState(null)     // 말하기
  const [speakLoading, setSpeakLoading] = useState(true)
  const [speakRefreshing, setSpeakRefreshing] = useState(false)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      setData(await learningAPI.getAnalysis())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const loadSpeak = async (isRefresh = false) => {
    if (isRefresh) setSpeakRefreshing(true)
    else setSpeakLoading(true)
    try {
      setSpeak(await speakAPI.getAnalysis())
    } catch (e) {
      console.error(e)
    } finally {
      setSpeakLoading(false)
      setSpeakRefreshing(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm('독화 연습 기록을 초기화하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return
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

  useEffect(() => { load(); loadSpeak() }, [])

  const hasVariance = data?.viseme_stats?.length > 0 && data.viseme_stats.some((v) => v.accuracy > 0)

  const TabBtn = ({ id, children }) => (
    <button onClick={() => setTab(id)}
      className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${tab === id ? (id === 'read' ? 'bg-primary-500 text-white' : 'bg-rose-500 text-white') : 'bg-white text-gray-500 border border-gray-200 hover:bg-gray-50'}`}>
      {children}
    </button>
  )

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">학습 분석</h1>
            <p className="text-sm text-gray-500">독화(입 읽기)와 말하기(발음)를 나눠서 봅니다</p>
          </div>
          <div className="flex items-center gap-2">
            {tab === 'read' && (
              <button onClick={handleReset} disabled={resetting || loading}
                className="text-xs px-3 py-1.5 rounded-lg border border-red-200 text-red-500 hover:bg-red-50 transition-colors disabled:opacity-40">
                {resetting ? '초기화 중...' : '독화 기록 초기화'}
              </button>
            )}
            <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-800 text-sm">← 대시보드</button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* 탭: 독화 | 말하기 */}
        <div className="flex gap-2">
          <TabBtn id="read">👂 독화 분석</TabBtn>
          <TabBtn id="speak">🎤 말하기 분석</TabBtn>
        </div>

        {tab === 'speak' ? (
          <SpeakAnalysis loading={speakLoading} d={speak} onRefresh={() => loadSpeak(true)} refreshing={speakRefreshing} />
        ) : loading ? (
          <Spinner />
        ) : !data ? (
          <div className="card text-center py-12"><p className="text-gray-500">데이터를 불러오지 못했습니다.</p></div>
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
                        <div className="bg-red-400 h-full rounded-full"
                          style={{ width: `${Math.min((c.count / (data.confusions[0]?.count || 1)) * 100, 100)}%` }} />
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
                <h2 className="text-lg font-bold text-gray-900">AI 맞춤 독화 조언</h2>
                <button onClick={() => load(true)} disabled={refreshing}
                  className="text-xs px-3 py-1.5 rounded-full bg-primary-50 text-primary-600 hover:bg-primary-100 transition-colors disabled:opacity-50">
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
