import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI, curriculumAPI, reviewAPI, speakAPI } from '../api'

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

// 테스트 탭 문제 유형: 주관식 · 4지선다 · 서술형을 골고루 섞는다.
const TEST_QTYPES = ['test', 'test-multiple', 'essay']
function buildQTypes(n) {
  const arr = Array.from({ length: n }, (_, i) => TEST_QTYPES[i % TEST_QTYPES.length])
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

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

function CurriculumPath() {
  const navigate = useNavigate()
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [due, setDue] = useState(0)

  const load = () => curriculumAPI.getStages().then(setState).catch(() => setState(null)).finally(() => setLoading(false))
  useEffect(() => {
    load()
    reviewAPI.getDue().then((d) => setDue(d.count || 0)).catch(() => {})
  }, [])

  const pickTrack = async (track) => {
    setSaving(true)
    try { await curriculumAPI.setTrack(track); await load() } finally { setSaving(false) }
  }

  const resetTrack = async () => {
    setSaving(true)
    try { await curriculumAPI.resetTrack(); await load() } finally { setSaving(false) }
  }

  const go = (s) => {
    if (s.status === 'coming_soon') return   // 준비 중 — 안내할 이전 단계가 없음
    if (s.status === 'locked') {
      const prev = state?.stages?.find((x) => x.stage === s.stage - 1)
      const prevName = prev ? `${prev.stage}단계(${prev.title})` : '이전 단계'
      alert(`아직 잠긴 단계예요. ${prevName} 학습을 먼저 완료해주세요.`)
      return
    }
    if (!s.route) return
    navigate(s.route)
  }

  if (loading || !state) return null

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card mb-8">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-bold text-gray-900">학습</h2>
        {state.placed ? (
          <button onClick={resetTrack} disabled={saving}
            className="text-xs text-gray-400 hover:text-primary-600 transition-colors disabled:opacity-50">
            ← 트랙 다시 선택
          </button>
        ) : (
          <span className="text-xs text-gray-400">기초부터 단계별로</span>
        )}
      </div>

      {!state.placed ? (
        <div>
          <p className="text-sm text-gray-500 mb-3">시작 전에 나에게 맞는 트랙을 골라주세요.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {TRACKS.map((t) => (
              <button key={t.id} disabled={saving} onClick={() => pickTrack(t.id)}
                className="text-left p-4 rounded-xl border-2 border-gray-200 hover:border-primary-400 hover:bg-primary-50 transition-all disabled:opacity-60">
                <div className="text-2xl mb-1">{t.icon}</div>
                <div className="font-bold text-gray-800">{t.title}</div>
                <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3">
          {state.stages.map((s) => {
            const st = STAGE_STATUS[s.status] || STAGE_STATUS.locked
            const isLocked = s.status === 'locked'
            const openable = !isLocked && s.status !== 'coming_soon' && !!s.route
            // 잠긴 단계는 흐리게(잠김) 보이되, 눌러서 '이전 단계 완료' 안내를 받을 수 있게 클릭은 허용
            return (
              <button key={s.stage} onClick={() => go(s)} disabled={s.status === 'coming_soon'}
                className={`text-left p-3 rounded-xl border-2 transition-all ${openable ? 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 cursor-pointer' : isLocked ? 'border-gray-100 bg-gray-50 cursor-pointer hover:border-gray-200' : 'border-gray-100 bg-gray-50 cursor-default'}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">{s.stage}단계</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${st.cls}`}>{st.label}</span>
                </div>
                <div className={`text-sm font-bold mt-1 ${openable ? 'text-gray-800' : 'text-gray-400'}`}>{s.title}</div>
                <div className="text-[11px] text-gray-400 mt-0.5 leading-tight">{s.desc}</div>
                {s.stage === 1 && s.mastery_score != null && (
                  <div className="mt-1.5 bg-gray-200 rounded-full h-1 overflow-hidden">
                    <div className="bg-primary-500 h-full" style={{ width: `${Math.min(s.mastery_score, 100)}%` }} />
                  </div>
                )}
              </button>
            )
          })}
        </div>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button onClick={() => navigate('/review')}
            className={`py-2.5 rounded-xl text-sm font-semibold transition-all ${due > 0 ? 'bg-amber-100 text-amber-800 hover:bg-amber-200' : 'bg-gray-100 text-gray-400'}`}>
            🔁 오늘의 복습 {due > 0 ? `${due}개` : '(없음)'}
          </button>
          <button onClick={() => navigate('/learn/closure')}
            className="py-2.5 rounded-xl text-sm font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-all">
            🧩 문맥 추론 훈련
          </button>
        </div>
        </>
      )}
    </motion.div>
  )
}

// ── 발화(말하기) 커리큘럼 경로 — Ling 기반 6단계 사다리 ───────────────────────
function SpeakCurriculumPath() {
  const navigate = useNavigate()
  const [stages, setStages] = useState(null)
  const [reviewDue, setReviewDue] = useState(0)

  useEffect(() => {
    speakAPI.getCurriculum().then((d) => setStages(d.stages)).catch(() => setStages(null))
    speakAPI.getReview().then((d) => setReviewDue(d.count || 0)).catch(() => {})
  }, [])

  const go = (s) => {
    if (s.status === 'locked') {
      alert(`아직 잠긴 단계예요. ${s.stage - 1}단계를 먼저 숙달해주세요.`)
      return
    }
    navigate(`/speak?stage=${s.stage}`)
  }

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28 }} className="card mb-8">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-bold text-gray-900">말하기 연습</h2>
        <span className="text-xs text-gray-400">읽기의 짝 · 발음을 눈으로 다듬기</span>
      </div>
      <p className="text-sm text-gray-500 mb-3">
        소리 내기부터 문장 억양까지 — 단계별로 내 발음을 곡선으로 보고 AI 코칭을 받아요.
      </p>
      {!stages ? (
        <div className="py-6 text-center text-sm text-gray-400">불러오는 중…</div>
      ) : (
        <>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {stages.map((s) => {
            const st = STAGE_STATUS[s.status] || STAGE_STATUS.locked
            const openable = s.status !== 'locked'
            return (
              <button key={s.stage} onClick={() => go(s)}
                className={`text-left p-3 rounded-xl border-2 transition-all ${openable ? 'border-gray-200 bg-white hover:border-rose-400 hover:bg-rose-50 cursor-pointer' : 'border-gray-100 bg-gray-50 cursor-pointer hover:border-gray-200'}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">{s.stage}단계</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${st.cls}`}>{st.label}</span>
                </div>
                <div className={`text-sm font-bold mt-1 flex items-center gap-1 ${openable ? 'text-gray-800' : 'text-gray-400'}`}>
                  <span>{s.icon}</span><span className="truncate">{s.title}</span>
                </div>
                <div className="text-[11px] text-gray-400 mt-0.5 leading-tight">{s.desc}</div>
                {s.mastery_score != null && (
                  <div className="mt-1.5 bg-gray-200 rounded-full h-1 overflow-hidden">
                    <div className="bg-rose-500 h-full" style={{ width: `${Math.min(s.mastery_score, 100)}%` }} />
                  </div>
                )}
              </button>
            )
          })}
        </div>
        <button onClick={() => reviewDue > 0 && navigate('/speak?review=1')} disabled={reviewDue === 0}
          className={`mt-3 w-full py-2.5 rounded-xl text-sm font-semibold transition-all ${reviewDue > 0 ? 'bg-rose-100 text-rose-700 hover:bg-rose-200' : 'bg-gray-100 text-gray-400 cursor-default'}`}>
          🔁 발음 복습 {reviewDue > 0 ? `${reviewDue}개` : '(없음)'}
        </button>
        </>
      )}
    </motion.div>
  )
}

// ── 복습 탭 ──────────────────────────────────────────────────────────────────
// 학습·테스트를 진행하며 틀린 문장과 북마크한 문장을 모아 다시 볼 수 있게 한다.
function ReviewSection() {
  const navigate = useNavigate()
  const setScenario = useStore((state) => state.setScenario)
  const [items, setItems] = useState(null)   // 합쳐진 복습 문장 목록
  const [loading, setLoading] = useState(false)

  const load = () => {
    Promise.all([
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks().catch(() => []),
    ]).then(([wrong, bookmarks]) => {
      const map = new Map()
      wrong.forEach((w) => map.set(w.sentence, {
        sentence: w.sentence,
        situation: w.situation || '복습',
        level: w.difficulty_level || 1,
        source: 'wrong',
      }))
      bookmarks.forEach((b) => {
        if (!map.has(b.sentence)) {
          map.set(b.sentence, { sentence: b.sentence, situation: b.situation || '복습', level: b.level || 1, source: 'bookmark' })
        } else {
          map.get(b.sentence).source = 'both'
        }
      })
      setItems([...map.values()])
    })
  }
  useEffect(load, [])

  const start = () => {
    if (!items || items.length === 0) return
    setLoading(true)
    const sentences = items.map((i) => i.sentence)
    const scenario = {
      situation: '복습',
      level: 1,
      sentences,
      qTypes: buildQTypes(sentences.length),
      scenario_id: `review_${Date.now()}`,
    }
    setScenario(scenario, 'test')
    navigate('/practice')
  }

  const wrongCount = items ? items.filter((i) => i.source !== 'bookmark').length : 0
  const bookmarkCount = items ? items.filter((i) => i.source !== 'wrong').length : 0
  const total = items ? items.length : 0

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card mt-8">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-bold text-gray-900">복습</h2>
        <span className="text-xs text-gray-400">틀린 문제 + 북마크 모아보기</span>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        학습·테스트에서 틀렸거나 북마크해 둔 문장을 모아서 다시 풀어봅니다.
      </p>

      {items === null ? (
        <div className="py-6 text-center text-sm text-gray-400">불러오는 중...</div>
      ) : total === 0 ? (
        <div className="py-6 text-center text-sm text-gray-400">
          아직 복습할 문장이 없어요. 테스트에서 틀리거나 문장을 북마크하면 여기에 모여요.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className="bg-gray-50 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-gray-900">{total}</div>
              <div className="text-xs text-gray-500">전체</div>
            </div>
            <div className="bg-red-50 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-red-600">{wrongCount}</div>
              <div className="text-xs text-gray-500">틀린 문제</div>
            </div>
            <div className="bg-yellow-50 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-yellow-600">{bookmarkCount}</div>
              <div className="text-xs text-gray-500">북마크</div>
            </div>
          </div>
          <button onClick={start} disabled={loading}
            className="btn-primary w-full py-3 text-base disabled:opacity-60">
            {loading ? '불러오는 중...' : `복습 시작 (${total}문장)`}
          </button>
        </>
      )}
    </motion.div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

// 두 스킬 기둥(독화 / 말하기) 구분용 구역 헤더
function ZoneHeader({ icon, title, sub, divider }) {
  return (
    <div className={`flex items-baseline gap-2 mb-4 ${divider ? 'mt-12 pt-8 border-t border-gray-200' : 'mt-2'}`}>
      <span className="text-2xl">{icon}</span>
      <h2 className="text-xl font-bold text-gray-900">{title}</h2>
      <span className="hidden sm:inline text-xs text-gray-400">{sub}</span>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const statistics = useStore((state) => state.statistics)
  const setStatistics = useStore((state) => state.setStatistics)

  const [selectedSituation, setSelectedSituation] = useState('카페')
  const [customSituation, setCustomSituation] = useState('')
  const [selectedLevel, setSelectedLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [loading, setLoading] = useState(false)
  const [statsLoading, setStatsLoading] = useState(true)
  const [calendarData, setCalendarData] = useState({})
  const [recLevel, setRecLevel] = useState(null)
  const [testLocked, setTestLocked] = useState(false)   // 3단계(문장 테스트) 잠김 여부

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
        setTestLocked(!!s3 && (s3.status === 'locked' || s3.status === 'coming_soon'))
      })
      .catch(() => {})
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
    if (testLocked) {
      alert('아직 잠긴 단계예요. 학습에서 2단계(음절·단어)를 먼저 완료해주세요.')
      return
    }
    if (!effectiveSituation.trim()) {
      alert('상황을 입력해주세요.')
      return
    }
    setLoading(true)
    try {
      const scenario = await learningAPI.getScenario(effectiveSituation, selectedLevel)
      // 테스트는 문장마다 주관식·4지선다·서술형을 섞어서 출제한다.
      scenario.qTypes = buildQTypes(scenario.sentences.length)
      setScenario(scenario, 'test')
      navigate('/practice')
    } catch (error) {
      alert('시나리오 생성에 실패했습니다. 다시 시도해주세요.')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }


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
              <button
                onClick={() => navigate('/sign')}
                className="px-3 py-1.5 text-sm text-white bg-primary-500 hover:bg-primary-600 transition-colors rounded-lg"
              >
                수어
              </button>
              <div className="text-right hidden sm:block">
                <p className="text-xs text-gray-500">안녕하세요,</p>
                <p className="font-semibold text-gray-900 text-sm">{user?.username}님</p>
              </div>
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
            <h3 className="text-sm font-semibold text-gray-500 mb-3">취약 입모양 <span className="text-[10px] text-gray-400">(독화)</span></h3>
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

        {/* ── 독화(입 읽기) 기둥: 학습 · 테스트 · 복습 ── */}
        <ZoneHeader icon="👂" title="독화 — 입 읽기" sub="남의 말을 입모양으로 읽는 훈련" />

        {/* 단계형 커리큘럼 경로 (오늘의 학습) */}
        <CurriculumPath />

        {/* Practice Setup */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card"
        >
          <h2 className="text-xl font-bold mb-5 text-gray-900 flex items-center gap-2">
            테스트
            {testLocked && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-400">🔒 잠김</span>
            )}
          </h2>

          {testLocked ? (
            <div className="mb-5 p-3 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-500">
              학습에서 2단계(음절·단어)를 완료하면 테스트가 열려요.
            </div>
          ) : (
            <div className="mb-5 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
              그동안 학습한 내용을 검증합니다. 주관식·4지선다·서술형 문제가 섞여서 출제돼요.
            </div>
          )}

          <div className="space-y-5">
            {/* Situation Selection */}
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

            {/* Level Selection */}
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
                <p className="text-xs text-gray-400 mt-1.5">
                  추천 레벨: {recLevel?.recommended_level ?? Math.min(user?.current_level || 1, 5)}
                  {recLevel?.reason ? ` · ${recLevel.reason}` : ''}
                </p>
            </div>

            {/* Start Button */}
            <button
              onClick={startPractice}
              disabled={
                loading ||
                testLocked ||
                (selectedSituation === '직접 입력' && !customSituation.trim())
              }
              className="btn-primary w-full py-3.5 text-base disabled:opacity-60"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  AI가 시나리오를 만드는 중...
                </span>
              ) : testLocked ? '🔒 2단계 완료 후 열려요' : '테스트 시작'}
            </button>
          </div>
        </motion.div>

        <ReviewSection />

        {/* ── 말하기(발음) 기둥: 발화 6단계 ── */}
        <ZoneHeader icon="🎤" title="말하기 — 발음" sub="내 발음을 눈으로 보며 다듬는 훈련" divider />
        <SpeakCurriculumPath />
      </main>
    </div>
  )
}
