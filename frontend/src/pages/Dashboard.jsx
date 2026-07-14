import { useState, useEffect, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI, curriculumAPI, reviewAPI, speakAPI, tactileAPI } from '../api'

const PRESET_SITUATIONS = [
  { id: '카페', label: '카페' },
  { id: '병원', label: '병원' },
  { id: '식당', label: '식당' },
  { id: '은행', label: '은행' },
  { id: '쇼핑', label: '쇼핑' },
  { id: '대중교통', label: '대중교통' },
  { id: '직장', label: '직장' },
  { id: '학교', label: '학교' },
  { id: '직접 입력', label: '직접 입력' },
]

// 테스트 탭 문제 유형: 주관식 · 4지선다 · 서술형을 골고루 섞는다.
const TEST_QTYPES = ['test', 'test-multiple', 'essay']
const CONVERSATION_UNLOCK_HINT = '문장 독화(4단계)를 완료하면 대화 실전(5단계)이 해금돼요.'
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

// ── 단계형 커리큘럼 경로 ──────────────────────────────────────────────────────
const TRACKS = [
  { id: 'perception', title: '독화 지각 트랙', desc: '한국어를 이미 아는 분. 입모양 읽기 능력에 집중.' },
  { id: 'language', title: '언어+독화 트랙', desc: '수어가 더 편한 분. 뜻(수어)부터 익히고 입모양으로.' },
]

const STAGE_STATUS = {
  mastered:    { label: '완료',     cls: 'bg-green-100 text-green-700' },
  in_progress: { label: '진행 중',  cls: 'bg-blue-100 text-blue-700' },
  unlocked:    { label: '시작 가능', cls: 'bg-primary-100 text-primary-700' },
  available:   { label: '연습',     cls: 'bg-gray-100 text-gray-600' },
  locked:      { label: '잠김',     cls: 'bg-gray-100 text-gray-400' },
  coming_soon: { label: '준비 중',  cls: 'bg-gray-100 text-gray-400' },
}

// 세 커리큘럼(독화·말하기·타도마)이 동일한 카드 구조를 쓰도록 하는 공통 단계 칩.
// 기둥별 강조색만 theme으로 바꾼다. — 단계번호/상태뱃지/제목/설명/숙련도바/잠금오버레이 레이아웃 통일
const LADDER_ACCENT = {
  sky:    { hover: 'hover:border-primary-400 hover:bg-primary-50', bar: 'bg-primary-500' },
  rose:   { hover: 'hover:border-rose-400 hover:bg-rose-50',       bar: 'bg-rose-500' },
  purple: { hover: 'hover:border-purple-400 hover:bg-purple-50',   bar: 'bg-purple-500' },
}

// 단계 번호는 사용자에게 항상 1부터 보인다(내부 stage는 0부터). n은 호출부에서 stage+1로 넘긴다.
function StageChip({ n, title, desc, status = 'unlocked', mastery = null, unlockHint, theme = 'sky', onClick, disabled }) {
  const st = STAGE_STATUS[status] || STAGE_STATUS.locked
  const accent = LADDER_ACCENT[theme] || LADDER_ACCENT.sky
  const isLocked = status === 'locked'
  const openable = !isLocked && status !== 'coming_soon'
  // 진행 기록이 아직 없는 단계는 0%, '완료'인데 기록이 없는 단계(예: 입문·배치)는 100%로 본다.
  const pct = mastery != null ? mastery : (status === 'mastered' ? 100 : 0)
  return (
    <button onClick={onClick} disabled={disabled}
      aria-label={isLocked && unlockHint ? `${title}, 잠김. ${unlockHint}` : title}
      title={isLocked && unlockHint ? unlockHint : undefined}
      className={`group relative overflow-hidden text-left p-2 rounded-xl border-2 transition-all ${openable ? `border-gray-200 bg-white ${accent.hover} cursor-pointer` : isLocked ? 'border-dashed border-gray-300 bg-gray-100/80 cursor-help hover:border-amber-400' : 'border-gray-100 bg-gray-50 cursor-default'}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-gray-400">{n}단계</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${st.cls}`}>{st.label}</span>
      </div>
      <div className={`text-[13px] font-bold mt-0.5 ${openable ? 'text-gray-800' : 'text-gray-400'}`}>{title}</div>
      <div className="mt-0.5 truncate text-[10px] leading-tight text-gray-400">{desc}</div>
      {openable && (
        <div className="mt-1 flex items-center gap-1.5">
          <div className="flex-1 bg-gray-200 rounded-full h-1 overflow-hidden">
            <div className={`${accent.bar} h-full`} style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <span className="shrink-0 text-[9px] tabular-nums text-gray-400">{Math.round(pct)}%</span>
        </div>
      )}
      {isLocked && unlockHint && (
        <span className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-slate-900/95 px-2 text-center opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100">
          <span className="text-xs font-bold text-amber-300">해금 방법</span>
          <span className="mt-1 text-[10px] leading-tight text-white">{unlockHint}</span>
        </span>
      )}
    </button>
  )
}

function CurriculumPath({ onOpenTest, children }) {
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
      const prevName = prev ? `${prev.stage + 1}단계(${prev.title})` : '이전 단계'
      alert(`아직 잠긴 단계예요. ${prevName} 학습을 먼저 완료해주세요.`)
      return
    }
    // 4단계(문장)·5단계(대화)는 클릭하면 아래에 시작 설정 패널이 펼쳐진다.
    if (s.stage === 3 || s.stage === 4) {
      onOpenTest?.(s.stage === 3 ? 'sentence' : 'conversation')
      return
    }
    if (!s.route) return
    navigate(s.route)
  }

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card !p-4">
      {(loading || !state) ? (
        <div className="py-6 text-center text-xs text-gray-400">불러오는 중…</div>
      ) : (
      <>
      <div className="flex items-center justify-between mb-0.5">
        <h2 className="text-base font-bold text-gray-900">독화 학습</h2>
        {state.placed ? (
          <button onClick={resetTrack} disabled={saving}
            className="text-xs text-gray-400 hover:text-primary-600 transition-colors disabled:opacity-50">
            트랙 다시 선택
          </button>
        ) : (
          <span className="text-xs text-gray-400">기초부터 단계별로</span>
        )}
      </div>
      <p className="mb-2 line-clamp-2 text-xs text-gray-500">
        입모양 읽기(독화)를 기초 입모양 → 단어 → 문장 → 대화까지 단계별로 익혀요.
      </p>

      {!state.placed ? (
        <div>
          <p className="text-xs text-gray-500 mb-2">시작 전에 나에게 맞는 트랙을 골라주세요.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {TRACKS.map((t) => (
              <button key={t.id} disabled={saving} onClick={() => pickTrack(t.id)}
                className="text-left p-3 rounded-xl border-2 border-gray-200 hover:border-primary-400 hover:bg-primary-50 transition-all disabled:opacity-60">
                <div className="font-bold text-gray-800">{t.title}</div>
                <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
        {/* 5단계 전체를 한 줄에 나열 — 한눈에 보이도록 */}
        <div className="grid grid-cols-5 gap-1 sm:gap-1.5 mt-2">
          {state.stages.map((s) => {
            const isLocked = s.status === 'locked'
            const prev = isLocked ? state.stages.find((item) => item.stage === s.stage - 1) : null
            const unlockHint = prev
              ? `${prev.stage + 1}단계 ${prev.title} 학습을 완료하면 열려요.`
              : '이전 단계를 완료하면 열려요.'
            return (
              <StageChip key={s.stage} n={s.stage + 1} title={s.title} desc={s.desc}
                status={s.status} mastery={s.mastery_score} theme="sky"
                unlockHint={isLocked ? unlockHint : undefined}
                disabled={s.status === 'coming_soon'} onClick={() => go(s)} />
            )
          })}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button onClick={() => navigate('/learn/closure')}
            className="py-2 rounded-xl text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-all">
            문맥 추론 훈련
          </button>
          <button onClick={() => navigate('/pronounce')}
            className="py-2 rounded-xl text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-all">
            내 문장 발음 보기
          </button>
        </div>
        </>
      )}
      </>
      )}
      {children && (
        <div className="mt-4 border-t border-gray-100 pt-4">
          {children}
        </div>
      )}
    </motion.div>
  )
}

// ── 발화(말하기) 커리큘럼 경로 — Ling 기반 6단계 사다리 ───────────────────────
function SpeakCurriculumPath() {
  const navigate = useNavigate()
  const [stages, setStages] = useState(null)

  useEffect(() => {
    speakAPI.getCurriculum().then((d) => setStages(d.stages)).catch(() => setStages(null))
  }, [])

  const go = (s) => {
    if (s.status === 'locked') {
      alert(`아직 잠긴 단계예요. ${s.stage}단계를 먼저 숙달해주세요.`)
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
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-1 sm:gap-1.5">
          {stages.map((s) => (
            <StageChip key={s.stage} n={s.stage + 1} title={s.title} desc={s.desc}
              status={s.status} mastery={s.mastery_score} theme="rose" onClick={() => go(s)} />
          ))}
        </div>
      )}
    </motion.div>
  )
}

// ── 촉각 학습(타도마) — 독화·말하기 카드와 완전 동급(백엔드 진행도 + 동일 구조) ──
function TactileCard() {
  const navigate = useNavigate()
  const [stages, setStages] = useState(null)

  useEffect(() => {
    tactileAPI.getCurriculum().then((d) => setStages(d.stages)).catch(() => setStages(null))
  }, [])

  const go = (s) => {
    if (s.status === 'locked') {
      alert(`아직 잠긴 단계예요. ${s.stage}단계를 먼저 숙달해주세요.`)
      return
    }
    navigate(`/tactile?level=${s.stage}`)
  }

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card !p-4">
      <div className="flex items-center justify-between mb-0.5">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-bold text-gray-900">촉각 학습 (타도마)</h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">하드웨어</span>
        </div>
        <span className="text-xs text-gray-400">손으로 느끼는 발화 이해</span>
      </div>
      <p className="mb-2 line-clamp-2 text-xs text-gray-500">
        얼굴 모형의 턱·입술·진동·바람을 손으로 느끼며 말을 이해해요 — 하드웨어 없이 시뮬레이터로도 체험할 수 있어요.
      </p>
      {!stages ? (
        <div className="py-4 text-center text-xs text-gray-400">불러오는 중…</div>
      ) : (
        <div className="grid grid-cols-5 gap-1 sm:gap-1.5">
          {stages.map((s) => (
            <StageChip key={s.stage} n={s.stage + 1} title={s.title} desc={s.desc}
              status={s.status} mastery={s.mastery_score} theme="purple" onClick={() => go(s)} />
          ))}
        </div>
      )}
    </motion.div>
  )
}

// ── 복습 탭 — 독화·말하기·촉각에서 틀린 모든 문제를 한곳에 모은다 ─────────────
function ReviewTab() {
  const navigate = useNavigate()
  const setScenario = useStore((s) => s.setScenario)
  const [loading, setLoading] = useState(true)
  const [readDue, setReadDue] = useState([])
  const [wrongSentences, setWrongSentences] = useState([])
  const [readBookmarks, setReadBookmarks] = useState([])
  const [speak, setSpeak] = useState(null)
  const [tactile, setTactile] = useState(null)

  useEffect(() => {
    Promise.all([
      reviewAPI.getDue().catch(() => ({ items: [] })),
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks('read').catch(() => []),
      speakAPI.getReview().catch(() => null),
      tactileAPI.getReview().catch(() => null),
    ]).then(([due, wrong, bm, sp, tc]) => {
      setReadDue(due.items || [])
      setWrongSentences(wrong || [])
      setReadBookmarks(bm || [])
      setSpeak(sp)
      setTactile(tc)
      setLoading(false)
    })
  }, [])

  const startReadReview = () => {
    if (!wrongSentences.length) { navigate('/review'); return }
    const sents = wrongSentences.map((w) => w.sentence)
    setScenario({ situation: '복습', level: 1, sentences: sents, qTypes: buildQTypes(sents.length), scenario_id: `review_${Date.now()}` }, 'test')
    navigate('/practice', { state: { review: true } })
  }

  const retrySentence = (s) => {
    setScenario({ situation: '복습', level: s.difficulty_level || 1, sentences: [s.sentence], qTypes: buildQTypes(1), scenario_id: `review_${Date.now()}` }, 'test')
    navigate('/practice', { state: { review: true } })
  }

  if (loading) {
    return <div className="card !p-4 py-10 text-center text-xs text-gray-400">불러오는 중…</div>
  }

  const speakTotal = speak ? speak.buckets.due + speak.buckets.wrong : 0
  const tactileTotal = tactile ? tactile.buckets.due + tactile.buckets.wrong : 0

  return (
    <div className="space-y-3">
      {/* 독화 */}
      <section className="card !p-4 border-l-4 border-sky-400">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900">독화 복습</h2>
          <span className="text-xs text-gray-400">틀린 문제 {readDue.length + wrongSentences.length}개</span>
        </div>

        {readDue.length > 0 && (
          <div className="mb-2 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
            <span className="text-xs text-gray-600">입모양·단어 복습 예정 {readDue.length}개</span>
            <button onClick={() => navigate('/review')} className="text-xs font-semibold text-primary-600 hover:text-primary-700">
              복습 퀴즈 풀기 →
            </button>
          </div>
        )}

        {wrongSentences.length > 0 ? (
          <div className="space-y-1.5">
            {wrongSentences.map((s, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-xl bg-gray-50 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm text-gray-800">{s.sentence}</p>
                  <p className="text-[11px] text-gray-400">{s.situation} · {s.difficulty_level}단계 · {s.score}점</p>
                </div>
                <button onClick={() => retrySentence(s)} className="shrink-0 text-xs font-semibold text-primary-600 hover:text-primary-700">
                  다시 풀기
                </button>
              </div>
            ))}
          </div>
        ) : readDue.length === 0 && (
          <p className="py-4 text-center text-xs text-gray-400">틀린 문제가 없어요.</p>
        )}

        {wrongSentences.length > 0 && (
          <button onClick={startReadReview}
            className="mt-2 w-full rounded-lg bg-sky-600 py-2 text-xs font-bold text-white hover:bg-sky-700">
            틀린 문장 전체 다시 풀기 ({wrongSentences.length})
          </button>
        )}
        {readBookmarks.length > 0 && (
          <button onClick={() => navigate('/bookmarks')}
            className="mt-1.5 w-full rounded-lg border border-gray-200 py-1.5 text-xs text-gray-500 hover:bg-gray-50">
            북마크 {readBookmarks.length}개 보기
          </button>
        )}
      </section>

      {/* 말하기 */}
      <section className="card !p-4 border-l-4 border-rose-400">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900">말하기 복습</h2>
          <span className="text-xs text-gray-400">틀린 문제 {speak?.wrong?.length || 0}개</span>
        </div>
        {speak?.wrong?.length > 0 ? (
          <div className="space-y-1.5">
            {speak.wrong.map((w, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-xl bg-gray-50 px-3 py-2">
                <span className="truncate text-sm text-gray-800">{w.target}</span>
                <span className="shrink-0 text-[11px] text-gray-400">{w.last_score}점</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-4 text-center text-xs text-gray-400">틀린 문제가 없어요.</p>
        )}
        <button onClick={() => navigate('/speak?review=1')} disabled={speakTotal === 0}
          className="mt-2 w-full rounded-lg bg-rose-600 py-2 text-xs font-bold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400">
          말하기 복습 시작{speakTotal ? ` (${speakTotal})` : ''}
        </button>
      </section>

      {/* 촉각 */}
      <section className="card !p-4 border-l-4 border-purple-400">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900">촉각 복습</h2>
          <span className="text-xs text-gray-400">틀린 문제 {tactile?.wrong?.length || 0}개</span>
        </div>
        {tactile?.wrong?.length > 0 ? (
          <div className="space-y-1.5">
            {tactile.wrong.map((w, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-xl bg-gray-50 px-3 py-2">
                <span className="truncate text-sm text-gray-800">{w.target}</span>
                <span className="shrink-0 text-[11px] text-gray-400">{w.stage + 1}단계</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-4 text-center text-xs text-gray-400">틀린 문제가 없어요.</p>
        )}
        <button onClick={() => navigate('/tactile?review=1')} disabled={tactileTotal === 0}
          className="mt-2 w-full rounded-lg bg-purple-600 py-2 text-xs font-bold text-white hover:bg-purple-700 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400">
          촉각 복습 시작{tactileTotal ? ` (${tactileTotal})` : ''}
        </button>
      </section>
    </div>
  )
}

// ── 분석 탭 — 최근 활동 + 취약점 요약, 상세 분석은 /analysis로 연결 ────────────
function AnalysisTab({ statistics, statsLoading, calendarData, navigate }) {
  return (
    <section className="card !p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-bold text-gray-900">학습 기록과 분석</h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">총 {statistics?.total_sessions || 0}회</span>
          <span className="rounded-full bg-primary-50 px-2.5 py-1 font-bold text-primary-700">평균 {statistics?.average_score || 0}점</span>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
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
      <div className="mt-4 border-t border-slate-100 pt-3">
        <button onClick={() => navigate('/analysis')}
          className="text-sm font-semibold text-primary-600 hover:text-primary-700">
          독화·말하기·촉각 상세 분석 보기 →
        </button>
      </div>
    </section>
  )
}

const TABS = [
  { id: 'learn', label: '학습', desc: '독화·말하기·촉각 단계별 학습을 시작해요.' },
  { id: 'review', label: '복습', desc: '틀렸던 문제를 모아서 다시 풀어요.' },
  { id: 'analysis', label: '분석', desc: '학습 기록과 취약점을 확인해요.' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const statistics = useStore((state) => state.statistics)
  const setStatistics = useStore((state) => state.setStatistics)

  const [activeTab, setActiveTab] = useState(null)   // 처음엔 아무 탭도 선택 안 된 상태 — 골라야 뜬다
  const [testMode, setTestMode] = useState('sentence')   // 'sentence'(4단계) | 'conversation'(5단계)
  const [showTestPanel, setShowTestPanel] = useState(false)  // 4·5단계 칩을 눌러야 패널이 펼쳐진다
  const [selectedSituation, setSelectedSituation] = useState('카페')
  const [customSituation, setCustomSituation] = useState('')
  const [selectedLevel, setSelectedLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [loading, setLoading] = useState(false)
  const [statsLoading, setStatsLoading] = useState(true)
  const [calendarData, setCalendarData] = useState({})
  const [recLevel, setRecLevel] = useState(null)
  const [testLocked, setTestLocked] = useState(false)   // 4단계(문장 테스트) 잠김 여부
  const [conversationLocked, setConversationLocked] = useState(false)
  const [unlockNotice, setUnlockNotice] = useState(null)

  useEffect(() => {
    loadStatistics()
    loadCalendar()
    // 적응형 난이도 — 최근 정확도로 추천 레벨을 받아 기본값으로
    curriculumAPI.getRecommendedLevel()
      .then((r) => { setRecLevel(r); setSelectedLevel(r.recommended_level) })
      .catch(() => {})
    // 테스트(4단계)는 3단계 숙달 전엔 잠긴다 → 시나리오 생성 전에 미리 막는다
    curriculumAPI.getStages()
      .then((data) => {
        const s3 = (data?.stages || []).find((x) => x.stage === 3)
        const s4 = (data?.stages || []).find((x) => x.stage === 4)
        setTestLocked(!!s3 && (s3.status === 'locked' || s3.status === 'coming_soon'))
        setConversationLocked(!!s4 && (s4.status === 'locked' || s4.status === 'coming_soon'))
      })
      .catch(() => {})
  }, [])

  // 학습 메뉴 바(전체 학습 메뉴)의 해시 링크로 들어오면 해당 탭·패널을 열어준다.
  useEffect(() => {
    if (location.hash === '#daily-review') setActiveTab('review')
    else if (location.hash === '#test-sentence') { setActiveTab('learn'); openTestPanel('sentence') }
    else if (location.hash === '#test-conversation') { setActiveTab('learn'); openTestPanel('conversation') }
  }, [location.hash])

  useEffect(() => {
    if (!unlockNotice) return undefined
    const timer = window.setTimeout(() => setUnlockNotice(null), 5000)
    return () => window.clearTimeout(timer)
  }, [unlockNotice])

  // 4·5단계 칩을 누르면 패널을 펼치고 그 위치로 스크롤한다.
  const openTestPanel = (mode) => {
    setTestMode(mode)
    setShowTestPanel(true)
  }

  useEffect(() => {
    if (showTestPanel) {
      document.getElementById('reading-test-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [showTestPanel, testMode])

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
      else alert('아직 잠긴 단계예요. 학습에서 3단계(음절·단어)를 먼저 완료해주세요.')
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

        {/* 탭: 학습 / 복습 / 분석 — 고른 뒤에만 아래 전환용으로 노출 */}
        {activeTab && (
          <div className="mt-3 flex gap-1.5">
            <button onClick={() => setActiveTab(null)}
              className="rounded-2xl border border-gray-200 bg-white px-4 text-sm font-bold text-gray-500 transition-all hover:bg-gray-50">
              처음으로
            </button>
            <div className="flex flex-1 gap-1 rounded-2xl border border-gray-200 bg-white p-1">
              {TABS.map((t) => (
                <button key={t.id} onClick={() => setActiveTab(t.id)}
                  className={`flex-1 rounded-xl py-2 text-sm font-bold transition-all ${
                    activeTab === t.id ? 'bg-primary-600 text-white shadow' : 'text-gray-500 hover:bg-gray-50'
                  }`}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {!activeTab && (
          <section className="mt-3">
            <div className="flex min-h-[65vh] flex-col gap-3 sm:flex-row">
              {TABS.map((t) => (
                <button key={t.id} onClick={() => setActiveTab(t.id)}
                  className="flex flex-1 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-gray-200 bg-white p-6 text-center transition-all hover:border-primary-400 hover:bg-primary-50">
                  <div className="text-2xl font-black text-gray-800">{t.label}</div>
                  <div className="max-w-[220px] text-sm leading-relaxed text-gray-500">{t.desc}</div>
                </button>
              ))}
            </div>
          </section>
        )}

        {activeTab === 'learn' && (
          <>
            {/* 독화 학습 — 단계 사다리 + 문장·대화 실전을 한 카드로 통합 */}
            <section id="reading-learning" className="mt-3">
              <CurriculumPath onOpenTest={openTestPanel}>
              {showTestPanel && (
              <div id="reading-test-panel">
              <h2 className="mb-1 flex flex-wrap items-center gap-2 text-base font-bold text-gray-900">
                {testMode === 'conversation' ? '대화 실전' : '문장 테스트'}
                <span className="text-[11px] font-medium text-gray-400">{testMode === 'conversation' ? '5단계' : '4단계'}</span>
                {testMode === 'sentence' && testLocked && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-400">잠김</span>
                )}
                {testMode === 'conversation' && conversationLocked && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700">잠김</span>
                )}
              </h2>
              <p className="mb-2 text-xs text-gray-500">
                {testMode === 'conversation'
                  ? 'AI와 대화하며 상대의 입모양을 눈으로 읽고 이해도를 확인해요.'
                  : <>AI의 <b className="text-gray-700">입모양을 눈으로 읽고</b> 무슨 말인지 알아맞히는 연습이에요. (말하기·발음이 아닙니다)</>}
              </p>

              {testMode === 'sentence' && (
                testLocked ? (
                  <div className="mb-2 rounded-lg border border-gray-200 bg-gray-50 p-2 text-xs text-gray-500">
                    학습에서 3단계(음절·단어)를 완료하면 테스트가 열려요.
                  </div>
                ) : (
                  <div className="mb-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-xs text-blue-700">
                    그동안 학습한 <b>독화(입모양 읽기)</b> 실력을 검증합니다. 주관식·4지선다·서술형 문제가 섞여서 출제돼요.
                  </div>
                )
              )}

              {testMode === 'conversation' && conversationLocked && (
                <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
                  {CONVERSATION_UNLOCK_HINT}
                </div>
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
                          className={`rounded-lg border-2 px-1.5 py-2 text-center transition-all ${
                            selectedSituation === s.id
                              ? 'border-primary-500 bg-primary-50'
                              : 'border-gray-200 hover:border-gray-300 bg-white'
                          }`}
                        >
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

                {testMode === 'conversation' ? (
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
                      {loading ? 'AI 시나리오 준비 중…' : conversationLocked ? '대화 실전 · 잠김' : 'AI 대화 독화 시작'}
                    </button>
                    {conversationLocked && (
                      <div id="conversation-unlock-tooltip" role="tooltip"
                        className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-20 w-64 -translate-x-1/2 rounded-xl bg-slate-900 px-3 py-2 text-center text-xs leading-relaxed text-white opacity-0 shadow-xl transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                        <b className="text-amber-300">해금 방법</b><br />{CONVERSATION_UNLOCK_HINT}
                        <span className="absolute left-1/2 top-full -translate-x-1/2 border-8 border-transparent border-t-slate-900" />
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    onClick={startPractice}
                    disabled={
                      loading ||
                      testLocked ||
                      (selectedSituation === '직접 입력' && !customSituation.trim())
                    }
                    className="btn-primary w-full py-2.5 text-sm disabled:opacity-60"
                  >
                    {loading ? 'AI 시나리오 준비 중…' : testLocked ? '문장 테스트 잠김' : '문장 테스트 시작'}
                  </button>
                )}
              </div>
              </div>
              )}
              </CurriculumPath>
            </section>

            {/* 말하기 · 촉각 학습 */}
            <section className="mt-3 grid items-start gap-3 lg:grid-cols-2">
              <div id="speaking-learning">
                <SpeakCurriculumPath />
              </div>
              <TactileCard />
            </section>
          </>
        )}

        {activeTab === 'review' && (
          <section className="mt-3">
            <ReviewTab />
          </section>
        )}

        {activeTab === 'analysis' && (
          <section className="mt-3">
            <AnalysisTab statistics={statistics} statsLoading={statsLoading} calendarData={calendarData} navigate={navigate} />
          </section>
        )}
      </main>
    </div>
  )
}
