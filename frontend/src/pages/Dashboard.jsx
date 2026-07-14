import { useState, useEffect, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
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
const CONVERSATION_UNLOCK_HINT = '3단계 문장 독화를 완료하면 대화 실전이 해금됩니다.'
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

  const load = () => curriculumAPI.getStages().then(setState).catch(() => setState(null)).finally(() => setLoading(false))
  useEffect(() => {
    load()
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
    if (s.stage === 3 || s.stage === 4) {
      navigate('/dashboard#reading-test')
      return
    }
    navigate(s.route)
  }

  if (loading || !state) return null

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card !p-4">
      <div className="flex items-center justify-between mb-0.5">
        <h2 className="text-base font-bold text-gray-900">독화 학습</h2>
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
          <p className="text-xs text-gray-500 mb-2">시작 전에 나에게 맞는 트랙을 골라주세요.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {TRACKS.map((t) => (
              <button key={t.id} disabled={saving} onClick={() => pickTrack(t.id)}
                className="text-left p-3 rounded-xl border-2 border-gray-200 hover:border-primary-400 hover:bg-primary-50 transition-all disabled:opacity-60">
                <div className="text-xl mb-0.5">{t.icon}</div>
                <div className="font-bold text-gray-800">{t.title}</div>
                <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 mt-2">
          {state.stages.map((s) => {
            const st = STAGE_STATUS[s.status] || STAGE_STATUS.locked
            const isLocked = s.status === 'locked'
            const openable = !isLocked && s.status !== 'coming_soon' && !!s.route
            const prev = isLocked ? state.stages.find((item) => item.stage === s.stage - 1) : null
            const unlockHint = prev
              ? `${prev.stage}단계 ${prev.title} 학습을 완료하면 열려요.`
              : '이전 단계를 완료하면 열려요.'
            // 잠긴 단계는 흐리게(잠김) 보이되, 눌러서 '이전 단계 완료' 안내를 받을 수 있게 클릭은 허용
            return (
              <button key={s.stage} onClick={() => go(s)} disabled={s.status === 'coming_soon'}
                aria-label={isLocked ? `${s.title}, 잠김. ${unlockHint}` : s.title}
                title={isLocked ? unlockHint : undefined}
                className={`group relative overflow-hidden text-left p-2 rounded-xl border-2 transition-all ${openable ? 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 cursor-pointer' : isLocked ? 'border-dashed border-gray-300 bg-gray-100/80 cursor-help hover:border-amber-400' : 'border-gray-100 bg-gray-50 cursor-default'}`}>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-gray-400">{s.stage}단계</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${st.cls}`}>{st.label}</span>
                </div>
                <div className={`text-[13px] font-bold mt-0.5 ${openable ? 'text-gray-800' : 'text-gray-400'}`}>{s.title}</div>
                <div className="mt-0.5 truncate text-[10px] leading-tight text-gray-400">{s.desc}</div>
                {s.stage === 1 && s.mastery_score != null && (
                  <div className="mt-1 bg-gray-200 rounded-full h-1 overflow-hidden">
                    <div className="bg-primary-500 h-full" style={{ width: `${Math.min(s.mastery_score, 100)}%` }} />
                  </div>
                )}
                {isLocked && (
                  <span className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-slate-900/95 px-2 text-center opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100">
                    <span className="text-xs font-bold text-amber-300">🔒 해금 방법</span>
                    <span className="mt-1 text-[10px] leading-tight text-white">{unlockHint}</span>
                  </span>
                )}
              </button>
            )
          })}
        </div>
        <div className="mt-2">
          <button onClick={() => navigate('/learn/closure')}
            className="w-full py-2 rounded-xl text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-all">
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
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} className="card !p-4">
      <div className="flex items-center justify-between mb-0.5">
        <h2 className="text-base font-bold text-gray-900">말하기 연습</h2>
        <span className="text-xs text-gray-400">읽기의 짝 · 발음을 눈으로 다듬기</span>
      </div>
      <p className="mb-2 line-clamp-2 text-xs text-gray-500">
        소리 내기부터 문장 억양까지 — 단계별로 내 발음을 곡선으로 보고 AI 코칭을 받아요.
      </p>
      {!stages ? (
        <div className="py-4 text-center text-xs text-gray-400">불러오는 중…</div>
      ) : (
        <>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
          {stages.map((s) => {
            const st = STAGE_STATUS[s.status] || STAGE_STATUS.locked
            const openable = s.status !== 'locked'
            return (
              <button key={s.stage} onClick={() => go(s)}
                className={`text-left p-2 rounded-xl border-2 transition-all ${openable ? 'border-gray-200 bg-white hover:border-rose-400 hover:bg-rose-50 cursor-pointer' : 'border-gray-100 bg-gray-50 cursor-pointer hover:border-gray-200'}`}>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-gray-400">{s.stage}단계</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${st.cls}`}>{st.label}</span>
                </div>
                <div className={`mt-0.5 truncate text-[13px] font-bold ${openable ? 'text-gray-800' : 'text-gray-400'}`}>
                  {s.title}
                </div>
                <div className="mt-0.5 truncate text-[10px] leading-tight text-gray-400">{s.desc}</div>
                {s.mastery_score != null && (
                  <div className="mt-1 bg-gray-200 rounded-full h-1 overflow-hidden">
                    <div className="bg-rose-500 h-full" style={{ width: `${Math.min(s.mastery_score, 100)}%` }} />
                  </div>
                )}
              </button>
            )
          })}
        </div>
        <button onClick={() => reviewDue > 0 && navigate('/speak?review=1')} disabled={reviewDue === 0}
          className={`mt-2 w-full py-2 rounded-xl text-xs font-semibold transition-all ${reviewDue > 0 ? 'bg-rose-100 text-rose-700 hover:bg-rose-200' : 'bg-gray-100 text-gray-400 cursor-default'}`}>
          발음 복습 {reviewDue > 0 ? `${reviewDue}개` : '(없음)'}
        </button>
        </>
      )}
    </motion.div>
  )
}

// ── 오늘의 복습 ──────────────────────────────────────────────────────────────
// 예정된 SRS 항목과 오답·북마크 문장을 한곳에서 확인하고 각 학습 흐름으로 진입한다.
function ReviewSection() {
  const navigate = useNavigate()
  const setScenario = useStore((state) => state.setScenario)
  const [items, setItems] = useState(null)   // 합쳐진 복습 문장 목록
  const [dueItems, setDueItems] = useState([])
  const [showAll, setShowAll] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = () => {
    Promise.all([
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks().catch(() => []),
      reviewAPI.getDue().catch(() => ({ items: [] })),
    ]).then(([wrong, bookmarks, due]) => {
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
      setDueItems(due.items || [])
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
    // 복습은 단계 잠금과 무관하게 허용 — App.jsx StageGate가 이 state로 예외 처리(duadnwls)
    navigate('/practice', { state: { review: true } })
  }

  const wrongCount = items ? items.filter((i) => i.source !== 'bookmark').length : 0
  const bookmarkCount = items ? items.filter((i) => i.source !== 'wrong').length : 0
  const total = items ? items.length : 0
  const dueCount = dueItems.length
  const visibleItems = showAll ? (items || []) : (items || []).slice(0, 3)
  const sourceLabel = {
    wrong: { label: '오답', cls: 'bg-red-100 text-red-700' },
    bookmark: { label: '북마크', cls: 'bg-amber-100 text-amber-700' },
    both: { label: '오답+북마크', cls: 'bg-violet-100 text-violet-700' },
  }

  return (
    <motion.div
      id="daily-review"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="card !p-4 scroll-mt-20"
    >
      <div className="flex items-center justify-between gap-3 mb-0.5">
        <h2 className="text-base font-bold text-gray-900">오늘의 복습</h2>
        <span className="text-xs text-gray-400">예정 항목 + 모아둔 문장</span>
      </div>
      <p className="mb-2 text-xs text-gray-500">
        오늘 다시 볼 입모양·단어와 오답·북마크 문장을 한곳에서 확인하세요.
      </p>

      {items === null ? (
        <div className="py-4 text-center text-xs text-gray-400">불러오는 중...</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-1.5 mb-3">
            <div className="bg-sky-50 rounded-xl p-2 text-center">
              <div className="text-xl font-bold text-sky-700">{dueCount}</div>
              <div className="text-xs text-gray-500">오늘 예정</div>
            </div>
            <div className="bg-red-50 rounded-xl p-2 text-center">
              <div className="text-xl font-bold text-red-600">{wrongCount}</div>
              <div className="text-xs text-gray-500">틀린 문제</div>
            </div>
            <div className="bg-yellow-50 rounded-xl p-2 text-center">
              <div className="text-xl font-bold text-yellow-600">{bookmarkCount}</div>
              <div className="text-xs text-gray-500">북마크</div>
            </div>
          </div>

          {dueCount > 0 && (
            <div className="mb-3 rounded-xl border border-sky-100 bg-sky-50/70 p-2">
              <p className="mb-2 text-xs font-bold text-sky-800">오늘 예정된 기초 복습</p>
              <div className="flex flex-wrap gap-1.5">
                {dueItems.slice(0, 4).map((item) => (
                  <span key={`${item.kind}-${item.ref}`} className="rounded-full bg-white px-2.5 py-1 text-xs text-sky-700 shadow-sm">
                    {item.kind === 'viseme' ? '입모양' : '단어'} · {item.name || item.ref}
                  </span>
                ))}
                {dueCount > 4 && <span className="px-1 py-1 text-xs text-sky-600">외 {dueCount - 4}개</span>}
              </div>
            </div>
          )}

          {total > 0 ? (
            <div className="mb-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-bold text-gray-700">모아둔 문장 {total}개</p>
                {total > 3 && (
                  <button type="button" onClick={() => setShowAll((value) => !value)}
                    className="text-xs font-medium text-primary-600 hover:text-primary-700">
                    {showAll ? '접기' : '전체 보기'}
                  </button>
                )}
              </div>
              <ul className="max-h-52 space-y-1.5 overflow-y-auto pr-1">
                {visibleItems.map((item) => {
                  const source = sourceLabel[item.source]
                  return (
                    <li key={item.sentence} className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
                      <div className="mb-1 flex items-center gap-1.5">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${source.cls}`}>{source.label}</span>
                        <span className="truncate text-[10px] text-gray-400">{item.situation}</span>
                      </div>
                      <p className="text-sm font-medium leading-snug text-gray-800">{item.sentence}</p>
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : dueCount === 0 ? (
            <div className="mb-3 rounded-xl bg-gray-50 px-3 py-4 text-center text-xs text-gray-400">
              오늘 복습할 항목이 없어요. 틀린 문장이나 북마크는 이곳에 자동으로 모입니다.
            </div>
          ) : (
            <p className="mb-3 rounded-xl bg-gray-50 px-3 py-2 text-center text-xs text-gray-400">
              모아둔 문장은 아직 없지만 오늘 예정된 기초 복습이 있어요.
            </p>
          )}

          <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
            <button type="button" onClick={() => navigate('/review')} disabled={dueCount === 0}
              className="w-full rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400">
              {dueCount > 0 ? `기초 복습 시작 (${dueCount})` : '오늘 예정된 기초 복습 없음'}
            </button>
            <button type="button" onClick={start} disabled={loading || total === 0}
              className="btn-primary w-full px-4 py-2.5 text-sm disabled:opacity-60">
              {loading ? '불러오는 중...' : total > 0 ? `모은 문장 복습 (${total})` : '모아둔 문장 없음'}
            </button>
          </div>
        </>
      )}
    </motion.div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
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

  const explainConversationUnlock = () => {
    setUnlockNotice(CONVERSATION_UNLOCK_HINT)
  }

  const startScenario = async (mode) => {
    const isConversation = mode === 'conversation'
    if ((!isConversation && testLocked) || (isConversation && conversationLocked)) {
      if (isConversation) explainConversationUnlock()
      else alert('아직 잠긴 단계예요. 학습에서 2단계(음절·단어)를 먼저 완료해주세요.')
      return
    }
    if (!effectiveSituation.trim()) {
      alert('상황을 입력해주세요.')
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
      alert('시나리오 생성에 실패했습니다. 다시 시도해주세요.')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const startPractice = () => startScenario('practice')
  const startConversation = () => startScenario('conversation')


  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/95 shadow-sm backdrop-blur-xl">
        <div className="mx-auto max-w-[1440px] px-4 sm:px-6">
          <div className="flex items-center justify-between py-2.5">
            <button type="button" onClick={() => navigate('/dashboard')} className="text-left">
              <span className="block text-xl font-black tracking-tight text-primary-600">LIPLAB</span>
              <span className="hidden text-[11px] font-medium text-slate-500 sm:block">눈으로 듣고, 보며 말하는 학습</span>
            </button>
            <div className="mr-1 hidden text-right sm:block">
              <p className="text-[11px] text-slate-400">오늘도 반가워요</p>
              <p className="text-sm font-bold text-slate-800">{user?.username}님</p>
            </div>
          </div>

        </div>
      </header>

      <AnimatePresence>
        {unlockNotice && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            className="fixed right-4 top-20 z-[60] flex max-w-sm items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-950 shadow-xl sm:right-6"
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

      <main className="mx-auto max-w-[1440px] px-4 py-3 sm:px-6 sm:py-4">

        <motion.section
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-slate-950 via-sky-950 to-sky-800 p-4 text-white shadow-xl shadow-sky-950/10 sm:p-5"
        >
          <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-sky-300">Learning hub</p>
              <h1 className="mt-0.5 text-xl font-black tracking-tight sm:text-2xl">오늘은 어떤 훈련을 할까요?</h1>
              <p className="mt-0.5 text-xs text-sky-100/75">필요한 콘텐츠를 고르면 바로 학습을 시작할 수 있어요.</p>
            </div>
            <dl className="grid grid-cols-4 gap-1.5 text-center lg:min-w-[340px]">
              {[
                ['레벨', user?.current_level || 1],
                ['연속 학습', `${user?.streak_count || 0}일`],
                ['평균 점수', statsLoading ? '—' : `${statistics?.average_score || 0}점`],
                ['누적 XP', user?.total_xp || 0],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-white/10 bg-white/10 px-2 py-1.5 backdrop-blur-sm">
                  <dt className="text-[10px] text-sky-100/65">{label}</dt>
                  <dd className="mt-0.5 text-[13px] font-black text-white">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

        </motion.section>

        <section className="mt-3 grid items-start gap-3 lg:grid-cols-2">
          <div id="reading-learning" className="scroll-mt-20">
            <CurriculumPath />
          </div>
          <div id="speaking-learning" className="scroll-mt-20">
            <SpeakCurriculumPath />
          </div>
        </section>

        {/* 촉각 학습(타도마) — 하드웨어/시뮬레이터 */}
        <section className="mt-3">
          <button onClick={() => navigate('/tactile')}
            className="w-full card text-left border-2 border-transparent hover:border-purple-300 transition-colors flex items-center gap-4">
            <span className="text-4xl">🖐️</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-gray-900">촉각 학습 (타도마)</h2>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">NEW · 하드웨어</span>
              </div>
              <p className="text-sm text-gray-500 mt-0.5">얼굴 모형의 턱·입술·진동·바람을 손으로 느끼며 말을 이해해요 · 하드웨어 없이 시뮬레이터로도 체험</p>
            </div>
            <span className="text-gray-300 text-xl">→</span>
          </button>
        </section>

        {/* Practice Setup */}
        <section className="mt-3 grid items-start gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(280px,0.7fr)]">
        <motion.div
          id="reading-test"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12 }}
          className="card !p-4 scroll-mt-20"
        >
          <h2 className="mb-2 flex items-center gap-2 text-lg font-bold text-gray-900">
            문장·대화 실전
            {testLocked && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-400">🔒 잠김</span>
            )}
            {conversationLocked && !testLocked && (
              <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700">🔒 대화 잠김</span>
            )}
          </h2>

          {testLocked ? (
            <div className="mb-2 rounded-lg border border-gray-200 bg-gray-50 p-2 text-xs text-gray-500">
              학습에서 2단계(음절·단어)를 완료하면 테스트가 열려요.
            </div>
          ) : (
            <div className="mb-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-xs text-blue-700">
              그동안 학습한 내용을 검증합니다. 주관식·4지선다·서술형 문제가 섞여서 출제돼요.
            </div>
          )}

          {conversationLocked && !testLocked && (
            <button type="button" onClick={explainConversationUnlock}
              className="mb-2 flex w-full items-center gap-2 rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-1.5 text-left text-xs text-amber-800 transition hover:border-amber-400 hover:bg-amber-100 focus:outline-none focus:ring-2 focus:ring-amber-400">
              <span aria-hidden="true">🔒</span>
              <span><b>대화 실전 잠김</b> · {CONVERSATION_UNLOCK_HINT}</span>
            </button>
          )}

          <div className="space-y-3">
            {/* Situation Selection */}
            <div>
                <label className="label !mb-1 !text-xs">상황 선택</label>
                <div className="grid grid-cols-3 gap-1 sm:grid-cols-5 lg:grid-cols-9">
                  {PRESET_SITUATIONS.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedSituation(s.id)}
                      className={`rounded-lg border-2 p-1.5 text-center transition-all ${
                        selectedSituation === s.id
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300 bg-white'
                      }`}
                    >
                      <div className="text-base">{s.icon}</div>
                      <div className="text-[11px] font-medium leading-tight">{s.label}</div>
                    </button>
                  ))}
                </div>

                <AnimatePresence>
                  {selectedSituation === '직접 입력' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-2"
                    >
                      <input
                        type="text"
                        value={customSituation}
                        onChange={(e) => setCustomSituation(e.target.value)}
                        className="input-field !px-3 !py-2 text-sm"
                        placeholder="상황을 직접 입력하세요 (예: 헬스장에서 트레이너와 대화, 면접 준비...)"
                      />
                      <p className="mt-1 text-[11px] text-gray-500">
                        어떤 상황이든 AI가 맞춤형 문제를 만들어줍니다
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
            </div>

            {/* Level Selection */}
            <div>
                <label className="label !mb-1 !text-xs">난이도</label>
                <div className="flex gap-1.5">
                  {[1, 2, 3, 4, 5].map((level) => (
                    <button
                      key={level}
                      onClick={() => setSelectedLevel(level)}
                      className={`flex-1 rounded-lg border-2 py-2 text-xs font-medium transition-all ${
                        selectedLevel === level
                          ? 'border-primary-500 bg-primary-500 text-white'
                          : 'border-gray-200 hover:border-gray-300 text-gray-700'
                      }`}
                    >
                      {level}
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-[11px] text-gray-400">
                  추천 레벨: {recLevel?.recommended_level ?? Math.min(user?.current_level || 1, 5)}
                  {recLevel?.reason ? ` · ${recLevel.reason}` : ''}
                </p>
            </div>

            <div className="grid gap-1.5 sm:grid-cols-2">
              <button
                onClick={startPractice}
                disabled={
                  loading ||
                  testLocked ||
                  (selectedSituation === '직접 입력' && !customSituation.trim())
                }
                className="btn-primary w-full py-2.5 text-sm disabled:opacity-60"
              >
                {loading ? 'AI 시나리오 준비 중…' : testLocked ? '🔒 문장 테스트 잠김' : '💬 문장 테스트 시작'}
              </button>
              <div className="group relative">
                <button
                  onClick={startConversation}
                  aria-describedby={conversationLocked ? 'conversation-unlock-tooltip' : undefined}
                  disabled={
                    loading ||
                    (!conversationLocked && selectedSituation === '직접 입력' && !customSituation.trim())
                  }
                  className={`w-full rounded-lg px-5 py-2.5 text-sm font-bold transition focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
                    conversationLocked
                      ? 'cursor-help border-2 border-dashed border-amber-300 bg-gray-100 text-gray-500 hover:border-amber-400 hover:bg-amber-50 focus:ring-amber-400'
                      : 'bg-violet-600 text-white hover:bg-violet-700 focus:ring-violet-500'
                  }`}
                >
                  {loading ? 'AI 시나리오 준비 중…' : conversationLocked ? '🔒 대화 실전 · 잠김' : '🗣️ AI 대화 시작'}
                </button>
                {conversationLocked && (
                  <div id="conversation-unlock-tooltip" role="tooltip"
                    className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-20 w-64 -translate-x-1/2 rounded-xl bg-slate-900 px-3 py-2 text-center text-xs leading-relaxed text-white opacity-0 shadow-xl transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                    <b className="text-amber-300">해금 방법</b><br />{CONVERSATION_UNLOCK_HINT}
                    <span className="absolute left-1/2 top-full -translate-x-1/2 border-8 border-transparent border-t-slate-900" />
                  </div>
                )}
              </div>
            </div>
          </div>
        </motion.div>

        <ReviewSection />
        </section>

        <details className="group mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <summary className="flex cursor-pointer list-none flex-col justify-between gap-2 px-4 py-3 marker:hidden sm:flex-row sm:items-center">
            <div>
              <h2 className="font-bold text-slate-900">학습 기록과 분석</h2>
              <p className="text-xs text-slate-500">상세 기록은 필요할 때 펼쳐보세요.</p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">총 {statistics?.total_sessions || 0}회</span>
              <span className="rounded-full bg-primary-50 px-2.5 py-1 font-bold text-primary-700">평균 {statistics?.average_score || 0}점</span>
              <span aria-hidden="true" className="grid h-7 w-7 place-items-center rounded-full bg-slate-100 text-slate-500 transition group-open:rotate-180">⌄</span>
            </div>
          </summary>
          <div className="grid gap-4 border-t border-slate-100 px-4 py-4 lg:grid-cols-2">
            <section aria-labelledby="activity-title">
              <h3 id="activity-title" className="mb-2 text-sm font-bold text-slate-700">최근 90일 학습 현황</h3>
              <ActivityCalendar data={calendarData} />
            </section>
            <section aria-labelledby="weak-viseme-title">
              <h3 id="weak-viseme-title" className="mb-3 text-sm font-bold text-slate-700">취약 입모양</h3>
              {!statsLoading && statistics?.weak_visemes?.length > 0 ? (
                <ul className="grid gap-1.5 sm:grid-cols-3 lg:grid-cols-1">
                  {statistics.weak_visemes.slice(0, 3).map((wv, idx) => (
                    <li key={idx} className="flex items-center justify-between rounded-xl bg-red-50 px-3 py-1.5 text-sm">
                      <span className="capitalize text-slate-700">{wv.feature}</span>
                      <span className="font-bold text-red-600">{wv.error_rate}% 오답</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-xl bg-slate-50 px-3 py-4 text-center text-sm text-slate-400">아직 분석할 데이터가 없습니다.</p>
              )}
            </section>
          </div>
        </details>
      </main>
    </div>
  )
}
