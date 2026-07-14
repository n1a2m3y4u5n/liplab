import { useState, useEffect, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI, curriculumAPI, reviewAPI, speakAPI, tactileAPI } from '../api'
import DashboardPet from '../components/DashboardPet'

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

const HERO_SLIDES = [
  {
    id: 'reading',
    tab: '독화',
    eyebrow: '01',
    title: ['독화 · 입모양 읽기', '입모양부터 대화까지'],
    description: '자음·모음 입모양부터 상황별 문장·대화까지 단계로 익혀요.',
    to: '/pillar/reading',
    cta: '독화 학습 보기',
    background: 'from-[#fffede] via-[#fffbb6] to-[#fff58d]',
    badge: 'bg-white/75 text-sky-700',
    visual: { shape: 'from-sky-300 via-sky-400 to-sky-600', shadow: 'shadow-[0_30px_60px_rgba(2,132,199,0.28)]', first: '입', second: '문장', third: '독화', chip: 'bg-sky-100 text-sky-700' },
  },
  {
    id: 'speaking',
    tab: '말하기',
    eyebrow: '02',
    title: ['말하기 연습', '발음을 다듬어요'],
    description: '소리와 억양을 보며 또박또박 말해요.',
    to: '/pillar/speaking',
    cta: '말하기 보기',
    background: 'from-[#fff6f7] via-[#ffe7eb] to-[#ffd5dc]',
    badge: 'bg-white/80 text-rose-700',
    visual: { shape: 'from-rose-300 via-rose-400 to-pink-500', shadow: 'shadow-[0_30px_60px_rgba(244,63,94,0.22)]', first: '소리', second: '억양', third: '발음', chip: 'bg-rose-100 text-rose-700' },
  },
  {
    id: 'tactile',
    tab: '촉각(타도마)',
    eyebrow: '03',
    title: ['촉각 학습', '손끝으로 느껴요'],
    description: '입의 움직임과 진동을 촉각으로 익혀요.',
    to: '/pillar/tactile',
    cta: '촉각 학습 보기',
    background: 'from-[#faf8ff] via-[#eee9ff] to-[#ddd6fe]',
    badge: 'bg-white/80 text-violet-700',
    visual: { shape: 'from-violet-300 via-violet-400 to-purple-600', shadow: 'shadow-[0_30px_60px_rgba(124,58,237,0.22)]', first: '진동', second: '바람', third: '촉각', chip: 'bg-violet-100 text-violet-700' },
  },
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

// 세 커리큘럼(독화·말하기·타도마)이 동일한 카드 구조를 쓰도록 하는 공통 단계 칩.
// 기둥별 강조색만 theme으로 바꾼다. — 단계번호/상태뱃지/제목/설명/숙련도바/잠금오버레이 레이아웃 통일
const LADDER_ACCENT = {
  sky:    { hover: 'hover:border-primary-400 hover:bg-primary-50', bar: 'bg-primary-500' },
  rose:   { hover: 'hover:border-rose-400 hover:bg-rose-50',       bar: 'bg-rose-500' },
  purple: { hover: 'hover:border-purple-400 hover:bg-purple-50',   bar: 'bg-purple-500' },
}

function StageChip({ n, title, desc, status = 'unlocked', mastery = null, unlockHint, theme = 'sky', onClick, disabled }) {
  const st = STAGE_STATUS[status] || STAGE_STATUS.locked
  const accent = LADDER_ACCENT[theme] || LADDER_ACCENT.sky
  const isLocked = status === 'locked'
  const openable = !isLocked && status !== 'coming_soon'
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
      {mastery != null && (
        <div className="mt-1 bg-gray-200 rounded-full h-1 overflow-hidden">
          <div className={`${accent.bar} h-full`} style={{ width: `${Math.min(mastery, 100)}%` }} />
        </div>
      )}
      {isLocked && unlockHint && (
        <span className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-slate-900/95 px-2 text-center opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100">
          <span className="text-xs font-bold text-amber-300">🔒 해금 방법</span>
          <span className="mt-1 text-[10px] leading-tight text-white">{unlockHint}</span>
        </span>
      )}
    </button>
  )
}

function CurriculumPath({ children }) {
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
      navigate('/learn/scenario')
      return
    }
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
            ← 트랙 다시 선택
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
                <div className="text-xl mb-0.5">{t.icon}</div>
                <div className="font-bold text-gray-800">{t.title}</div>
                <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
        {/* 학습 단계(0~2)만 사다리로. 3·4단계(문장·대화)는 아래 '문장·대화 실전' 구역이 담당 — 역할 중복 제거 */}
        <div className="grid grid-cols-3 gap-1.5 mt-2">
          {state.stages.filter((s) => s.stage <= 2).map((s) => {
            const isLocked = s.status === 'locked'
            const prev = isLocked ? state.stages.find((item) => item.stage === s.stage - 1) : null
            const unlockHint = prev
              ? `${prev.stage}단계 ${prev.title} 학습을 완료하면 열려요.`
              : '이전 단계를 완료하면 열려요.'
            return (
              <StageChip key={s.stage} n={s.stage} title={s.title} desc={s.desc}
                status={s.status} mastery={s.mastery_score} theme="sky"
                unlockHint={isLocked ? unlockHint : undefined}
                disabled={s.status === 'coming_soon'} onClick={() => go(s)} />
            )
          })}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button onClick={() => navigate('/learn/closure')}
            className="py-2 rounded-xl text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-all">
            🧩 문맥 추론 훈련
          </button>
          <button onClick={() => navigate('/pronounce')}
            className="py-2 rounded-xl text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-all">
            ✍️ 내 문장 발음 보기
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
      alert(`아직 잠긴 단계예요. ${s.stage - 1}단계를 먼저 숙달해주세요.`)
      return
    }
    navigate(`/learn/speaking?stage=${s.stage}`)
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
          {stages.map((s) => (
            <StageChip key={s.stage} n={s.stage} title={s.title} desc={s.desc}
              status={s.status} mastery={s.mastery_score} theme="rose" onClick={() => go(s)} />
          ))}
        </div>
        </>
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
        <>
        {(() => {
          const total = stages.length
          const started = stages.filter((s) => s.status === 'mastered' || s.status === 'in_progress').length
          const lastMastered = [...stages].reverse().find((s) => s.status === 'mastered')
          const inProgress = stages.find((s) => s.status === 'in_progress')
          const note = lastMastered ? `${lastMastered.title} 완료`
            : inProgress ? `${inProgress.title} 학습 중` : '아직 시작 전'
          const pct = total ? Math.round(started / total * 100) : 0
          return (
            <div className="rounded-xl bg-gray-50 p-3">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-gray-600">진행</span>
                  <div className="flex gap-1">
                    {stages.map((s) => (
                      <span key={s.stage}
                        title={`${s.stage + 1}. ${s.title} · ${STAGE_STATUS[s.status]?.label || ''}`}
                        className={`h-2.5 w-2.5 rounded-full ${s.status === 'mastered' ? 'bg-purple-600' : s.status === 'in_progress' ? 'bg-purple-300' : 'bg-gray-200'}`} />
                    ))}
                  </div>
                </div>
                <span className="truncate text-xs text-gray-500">{started}/{total}단계 · {note}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-gray-200">
                <div className="h-full bg-purple-500 transition-all" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })()}
        <button onClick={() => navigate('/learn/tactile')}
          className="mt-2 w-full py-2 rounded-xl text-xs font-semibold bg-purple-600 text-white hover:bg-purple-700 transition-all">
          🖐️ 촉각 학습 열기 →
        </button>
        </>
      )}
    </motion.div>
  )
}

// ── 오늘의 복습 — 세 기둥(독화·말하기·타도마) 모두 예정(SRS)·틀림·북마크 3분할 ──────
function ReviewSection() {
  const navigate = useNavigate()
  const setScenario = useStore((s) => s.setScenario)
  const [data, setData] = useState(null)          // { read, speak, tactile } 각 {due, wrong, bookmark}
  const [wrongSentences, setWrongSentences] = useState([])  // 독화 문장 복습(오답)용

  useEffect(() => {
    Promise.all([
      reviewAPI.getDue().catch(() => ({ items: [] })),
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks('read').catch(() => []),
      speakAPI.getReview().catch(() => ({ buckets: { due: 0, wrong: 0, bookmark: 0 } })),
      tactileAPI.getReview().catch(() => ({ buckets: { due: 0, wrong: 0, bookmark: 0 } })),
    ]).then(([due, wrong, bm, speak, tactile]) => {
      setWrongSentences(wrong || [])
      setData({
        read: { due: (due.items || []).length, wrong: (wrong || []).length, bookmark: (bm || []).length },
        speak: speak.buckets || { due: 0, wrong: 0, bookmark: 0 },
        tactile: tactile.buckets || { due: 0, wrong: 0, bookmark: 0 },
      })
    })
  }, [])

  // 독화 문장 복습(오답 문장) → /practice. 예정(SRS 입모양·단어)이 있으면 /review 우선.
  const startReadReview = () => {
    if (data?.read.due > 0) { navigate('/review/scheduled'); return }
    const sents = wrongSentences.map((w) => w.sentence)
    if (!sents.length) { navigate('/review/scheduled'); return }
    setScenario({ situation: '복습', level: 1, sentences: sents, qTypes: buildQTypes(sents.length), scenario_id: `review_${Date.now()}` }, 'test')
    navigate('/practice', { state: { review: true } })
  }

  const pillars = data ? [
    { key: 'read', icon: '👁️', label: '독화', b: data.read, onStart: startReadReview,
      theme: { bg: 'bg-sky-50/40', border: 'border-sky-100', badge: 'bg-sky-100 text-sky-700', btn: 'bg-sky-600 hover:bg-sky-700' } },
    { key: 'speak', icon: '🗣️', label: '말하기', b: data.speak, onStart: () => navigate('/review/speaking'),
      theme: { bg: 'bg-rose-50/40', border: 'border-rose-100', badge: 'bg-rose-100 text-rose-700', btn: 'bg-rose-600 hover:bg-rose-700' } },
    { key: 'tactile', icon: '🖐️', label: '타도마', b: data.tactile, onStart: () => navigate('/review/tactile'),
      theme: { bg: 'bg-purple-50/40', border: 'border-purple-100', badge: 'bg-purple-100 text-purple-700', btn: 'bg-purple-600 hover:bg-purple-700' } },
  ] : []

  return (
    <motion.div id="daily-review" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card !p-4 scroll-mt-52">
      <div className="mb-0.5 flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-gray-900">오늘의 복습</h2>
        <span className="text-xs text-gray-400">세 기둥 · 예정·틀림·북마크</span>
      </div>
      <p className="mb-3 text-xs text-gray-500">
        독화·말하기·타도마를 각각 <b>예정(간격반복)</b> · <b>틀린 문제</b> · <b>북마크</b>로 복습해요.
      </p>

      {!data ? (
        <div className="py-4 text-center text-xs text-gray-400">불러오는 중...</div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-3">
          {pillars.map((p) => {
            const total = p.b.due + p.b.wrong + p.b.bookmark
            return (
              <div key={p.key} className={`rounded-2xl border p-3 ${p.theme.border} ${p.theme.bg}`}>
                <div className="mb-2 flex items-center gap-1.5">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ${p.theme.badge}`}>{p.icon} {p.label}</span>
                </div>
                <div className="mb-2 grid grid-cols-3 gap-1.5">
                  {[['오늘 예정', p.b.due], ['틀린 문제', p.b.wrong], ['북마크', p.b.bookmark]].map(([lbl, n]) => (
                    <div key={lbl} className="rounded-xl bg-white p-2 text-center">
                      <div className="text-lg font-bold text-gray-800">{n}</div>
                      <div className="text-[11px] text-gray-500">{lbl}</div>
                    </div>
                  ))}
                </div>
                <button onClick={p.onStart} disabled={total === 0}
                  className={`w-full rounded-lg px-3 py-2 text-xs font-bold text-white transition disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400 ${p.theme.btn}`}>
                  {total > 0 ? `복습 시작 (${total})` : '복습할 항목 없음'}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </motion.div>
  )
}

function LearnerProfileCard({ user, statistics, calendarData }) {
  const navigate = useNavigate()
  const [dueReviewCount, setDueReviewCount] = useState(null)

  useEffect(() => {
    let active = true
    reviewAPI.getDue()
      .then((data) => {
        if (active) setDueReviewCount((data?.items || []).length)
      })
      .catch(() => {
        if (active) setDueReviewCount(null)
      })
    return () => { active = false }
  }, [])

  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const totalXp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const levelStartXp = 100 * ((level - 1) ** 2)
  const nextLevelXp = 100 * (level ** 2)
  const usesLevelBand = totalXp >= levelStartXp
  const earnedThisLevel = usesLevelBand ? totalXp - levelStartXp : totalXp
  const xpNeededThisLevel = usesLevelBand ? nextLevelXp - levelStartXp : nextLevelXp
  const remainingXp = Math.max(0, xpNeededThisLevel - earnedThisLevel)
  const xpPercent = Math.min(100, Math.max(0, (earnedThisLevel / Math.max(1, xpNeededThisLevel)) * 100))
  const streak = Math.max(0, user?.streak_count || 0)
  const today = new Date()
  const todayKey = [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, '0'),
    String(today.getDate()).padStart(2, '0'),
  ].join('-')
  const todaySessions = Number(calendarData?.[todayKey] || 0)
  const displayName = user?.username || 'LIPLAB 학습자'
  const initial = displayName.trim().slice(0, 1).toUpperCase() || 'L'
  const tasks = [
    {
      id: 'review',
      label: '오늘의 복습 정리',
      detail: dueReviewCount == null ? '복습 항목 확인하기' : dueReviewCount > 0 ? `${dueReviewCount}개가 기다리고 있어요` : '오늘 복습을 모두 정리했어요',
      completed: dueReviewCount === 0,
      to: '/review/today',
    },
    {
      id: 'practice',
      label: '독화 학습 1회',
      detail: todaySessions >= 1 ? '첫 학습을 완료했어요' : '짧게 시작해도 좋아요',
      completed: todaySessions >= 1,
      to: '/learn/viseme',
    },
    {
      id: 'challenge',
      label: '오늘의 학습 2회 채우기',
      detail: `${Math.min(todaySessions, 2)} / 2회 완료`,
      completed: todaySessions >= 2,
      to: '/learn/scenario',
    },
  ]

  return (
    <aside
      className="flex h-full min-h-[460px] flex-col overflow-hidden rounded-[24px] border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-4 shadow-[0_16px_45px_rgba(15,23,42,0.08)] lg:min-h-0"
      aria-labelledby="learner-profile-heading"
    >
      <div className="flex items-center gap-3">
        <div
          className="relative grid h-[102px] w-[102px] shrink-0 place-items-center rounded-full p-[6px] shadow-[0_12px_28px_rgba(101,163,13,0.2)]"
          style={{ background: `conic-gradient(#84cc16 0% ${xpPercent}%, #e2e8f0 ${xpPercent}% 100%)` }}
          role="progressbar"
          aria-label={`레벨 ${level} 경험치`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(xpPercent)}
        >
          <div className="grid h-full w-full place-items-center rounded-full bg-white p-1">
            <div className="grid h-full w-full place-items-center rounded-full bg-gradient-to-br from-sky-100 via-cyan-50 to-lime-100 text-3xl font-black text-sky-700 ring-1 ring-sky-100">
              {initial}
            </div>
          </div>
          <span className="absolute -bottom-1 rounded-full bg-slate-950 px-2.5 py-0.5 text-[9px] font-black text-white shadow-lg">
            {Math.round(xpPercent)}%
          </span>
        </div>

        <div className="min-w-0 flex-1 text-left">
          <p className="text-[9px] font-black tracking-[0.14em] text-lime-700">MY PROFILE</p>
          <h2 id="learner-profile-heading" className="mt-1 truncate text-lg font-black tracking-tight text-slate-950">{displayName}</h2>
          <span className="mt-0.5 block text-sm font-black text-sky-600">Lv {level}</span>
          <p className="mt-1 text-[10px] font-bold leading-tight text-slate-500">다음 레벨까지<br /><b className="text-slate-800">{remainingXp.toLocaleString()} XP</b></p>
          <div className="mt-2 flex items-center justify-between text-[8px] font-bold text-slate-400">
            <span>{earnedThisLevel.toLocaleString()}</span>
            <span>/ {xpNeededThisLevel.toLocaleString()} XP</span>
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-2xl border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 px-2.5 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span aria-hidden="true" className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-orange-500 text-sm shadow-sm">🔥</span>
            <div className="min-w-0 text-left">
              <p className="truncate text-xs font-black text-amber-950">{streak}일 연속 학습</p>
              <p className="text-[9px] font-medium text-amber-700">오늘도 기록을 이어가세요</p>
            </div>
          </div>
          <div className="flex shrink-0 gap-1" aria-label={`최근 연속 학습 ${streak}일`}>
            {Array.from({ length: 7 }, (_, index) => (
              <span
                key={index}
                className={`h-2 w-2 rounded-full ${index < Math.min(streak, 7) ? 'bg-orange-500' : 'bg-amber-200'}`}
                aria-hidden="true"
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex min-h-0 flex-1 flex-col rounded-[18px] bg-slate-50 p-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-black text-slate-900">오늘의 과제</h3>
          <span className="rounded-full bg-lime-100 px-2 py-1 text-[9px] font-black text-lime-700">
            {tasks.filter((task) => task.completed).length}/{tasks.length} 완료
          </span>
        </div>
        <ul className="mt-2 space-y-1">
          {tasks.map((task) => (
            <li key={task.id}>
              <button
                type="button"
                onClick={() => navigate(task.to)}
                className="group flex w-full items-center gap-2 rounded-xl bg-white px-2 py-1.5 text-left ring-1 ring-slate-100 transition hover:-translate-y-0.5 hover:ring-lime-300 focus:outline-none focus:ring-2 focus:ring-lime-400"
              >
                <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-md text-[10px] font-black ${task.completed ? 'bg-lime-500 text-white' : 'border-2 border-slate-300 bg-white text-transparent'}`} aria-hidden="true">
                  ✓
                </span>
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-[11px] font-black ${task.completed ? 'text-slate-500 line-through' : 'text-slate-800'}`}>{task.label}</span>
                  <span className="block truncate text-[9px] font-medium text-slate-400">{task.detail}</span>
                </span>
                <span aria-hidden="true" className="text-xs font-black text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-lime-600">›</span>
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => navigate('/review/today')}
          className="mt-2 w-full rounded-xl border border-lime-200 bg-white py-1.5 text-[10px] font-black text-lime-700 transition hover:border-lime-400 hover:bg-lime-50 focus:outline-none focus:ring-2 focus:ring-lime-400"
        >
          과제 더보기 →
        </button>
      </div>
    </aside>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const statistics = useStore((state) => state.statistics)
  const setStatistics = useStore((state) => state.setStatistics)

  const [heroSlide, setHeroSlide] = useState(0)
  const [heroDirection, setHeroDirection] = useState(1)
  const [selectedSituation, setSelectedSituation] = useState('카페')
  const [customSituation, setCustomSituation] = useState('')
  const [selectedLevel, setSelectedLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [loading, setLoading] = useState(false)
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

  const goToSection = (id) => {
    const element = document.getElementById(id)
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const moveHeroSlide = (step) => {
    setHeroDirection(step > 0 ? 1 : -1)
    setHeroSlide((current) => (current + step + HERO_SLIDES.length) % HERO_SLIDES.length)
  }

  const selectHeroSlide = (index) => {
    if (index === heroSlide) return
    setHeroDirection(index > heroSlide ? 1 : -1)
    setHeroSlide(index)
  }

  const finishHeroDrag = (_, info) => {
    if (info.offset.x < -55 || info.velocity.x < -500) moveHeroSlide(1)
    else if (info.offset.x > 55 || info.velocity.x > 500) moveHeroSlide(-1)
  }

  const currentHero = HERO_SLIDES[heroSlide]

  return (
    <div className="min-h-0 bg-white lg:h-full lg:overflow-hidden">

      <AnimatePresence>
        {unlockNotice && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            className="fixed right-4 top-44 z-[60] flex max-w-sm items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-950 shadow-xl sm:right-6"
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

      <main className="mx-auto max-w-[1440px] px-4 py-4 sm:px-6 sm:py-5 lg:h-full">

        <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid items-stretch gap-4 lg:h-full lg:grid-cols-[290px_minmax(0,1fr)]">
          <LearnerProfileCard user={user} statistics={statistics} calendarData={calendarData} />

          <div
            role="region"
            aria-roledescription="carousel"
            aria-label="LIPLAB 맞춤 학습"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') { event.preventDefault(); moveHeroSlide(-1) }
              if (event.key === 'ArrowRight') { event.preventDefault(); moveHeroSlide(1) }
            }}
            className="relative min-h-[500px] overflow-hidden rounded-[24px] outline-none ring-sky-400 transition focus-visible:ring-2 focus-visible:ring-offset-2 lg:h-full lg:min-h-0"
          >
            <AnimatePresence initial={false} mode="wait">
              <motion.article
                key={currentHero.id}
                initial={{ opacity: 0, x: heroDirection > 0 ? 90 : -90 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: heroDirection > 0 ? -90 : 90 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={0.16}
                dragMomentum={false}
                onDragEnd={finishHeroDrag}
                aria-live="polite"
                aria-label={`${heroSlide + 1} / ${HERO_SLIDES.length}: ${currentHero.tab}`}
                className={`absolute inset-0 cursor-grab overflow-hidden bg-gradient-to-r ${currentHero.background} px-7 pb-20 pt-6 active:cursor-grabbing sm:px-10 lg:px-12`}
                style={{ touchAction: 'pan-y' }}
              >
                {/* 배경 깊이감 — 부드러운 오브(빛망울)로 밋밋한 단색 배경을 채운다 */}
                <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
                  <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-white/40 blur-3xl" />
                  <div className="absolute left-[46%] -top-16 h-64 w-64 rounded-full bg-white/30 blur-3xl" />
                  <div className="absolute left-[36%] top-1/3 h-72 w-72 rounded-full bg-amber-200/30 blur-3xl animate-pulse-slow" />
                  <div className="absolute -bottom-10 left-[30%] h-56 w-56 rounded-full bg-white/25 blur-2xl" />
                </div>

                {/* 중앙 빈 공간을 채우는 떠다니는 장식 — 프로스티드 카드·점·링·반짝임 (텍스트 뒤) */}
                <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-[1] hidden lg:block">
                  <div className={`absolute left-[45%] top-[24%] grid h-16 w-16 -rotate-6 place-items-center rounded-2xl text-lg font-black shadow-lg backdrop-blur-sm ${currentHero.visual.chip}`}>{currentHero.visual.first}</div>
                  <div className="absolute left-[63%] top-[15%] h-12 w-12 rotate-12 rounded-xl bg-white/60 shadow-md backdrop-blur-sm" />
                  <div className="absolute left-[38%] top-[60%] h-10 w-10 rotate-6 rounded-xl bg-white/50 shadow-md backdrop-blur-sm" />
                  <span className="absolute left-[57%] top-[58%] h-11 w-11 rounded-full border-2 border-white/60" />
                  <span className="absolute left-[43%] top-[13%] h-8 w-8 rounded-full border-2 border-amber-300/60" />
                  <span className="absolute left-[41%] top-[50%] h-3.5 w-3.5 rounded-full bg-white/75" />
                  <span className="absolute left-[54%] top-[40%] h-2.5 w-2.5 rounded-full bg-amber-400/70" />
                  <span className="absolute left-[69%] top-[50%] h-3 w-3 rounded-full bg-white/65" />
                  <span className="absolute left-[50%] top-[70%] h-2 w-2 rounded-full bg-slate-900/10" />
                  <span className="absolute left-[52%] top-[30%] text-2xl text-amber-400/80">✦</span>
                  <span className="absolute left-[67%] top-[33%] text-base text-amber-500/70">✦</span>
                  <span className="absolute left-[47%] top-[43%] text-sm text-white/90 animate-pulse">✦</span>
                </div>

                <div className="relative z-10 flex h-full items-center">
                  <div className="ml-9 max-w-xl pb-6 sm:ml-12 md:pr-[210px] lg:ml-16 lg:pr-[250px]">
                    {/* data-hero-copy: 펫이 넘어오지 못하는 '학습 섹션' 장애물 영역 (실제 글자 폭에만 맞춤) */}
                    <div data-hero-copy className="w-fit">
                      <span className={`inline-flex rounded-full px-3 py-1.5 text-[11px] font-black shadow-sm ${currentHero.badge}`}>LIPLAB · {currentHero.eyebrow}</span>
                      <h1 className="mt-4 text-3xl font-black leading-[1.13] tracking-[-0.045em] text-slate-950 sm:text-4xl lg:text-[36px] xl:text-[40px]">
                        {currentHero.title[0]}<br />{currentHero.title[1]}
                      </h1>
                      <p className="mt-3 max-w-md text-sm font-semibold leading-relaxed text-slate-600">{currentHero.description}</p>
                      <button
                        type="button"
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={() => navigate(currentHero.to)}
                        className="mt-5 rounded-full bg-slate-950 px-6 py-3 text-sm font-black text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
                      >
                        {currentHero.cta}
                      </button>
                    </div>
                  </div>
                </div>

                <div aria-hidden="true" className="pointer-events-none absolute -bottom-10 -right-10 hidden h-[330px] w-[360px] md:block">
                  <div className={`absolute bottom-12 right-12 h-52 w-64 rotate-[-5deg] rounded-[48%_44%_50%_46%] bg-gradient-to-br ${currentHero.visual.shape} ${currentHero.visual.shadow}`}>
                    <span className="absolute left-[72px] top-[64px] h-5 w-5 rounded-full bg-slate-800" />
                    <span className="absolute left-[110px] top-[61px] h-5 w-5 rounded-full bg-slate-800" />
                    <span className="absolute left-[68px] top-[100px] h-10 w-[92px] rounded-b-full rounded-t-[42%] border-b-[12px] border-white/90" />
                    <span className="absolute -right-7 top-20 h-20 w-14 rotate-12 rounded-[55%_45%_55%_45%] bg-slate-900/20" />
                  </div>
                  <div className="absolute right-20 top-2 grid h-16 min-w-16 rotate-12 place-items-center rounded-2xl bg-white px-2 text-sm font-black text-slate-800 shadow-xl">{currentHero.visual.first}</div>
                  <div className={`absolute right-3 top-24 grid h-14 min-w-14 -rotate-6 place-items-center rounded-2xl px-2 text-xs font-black shadow-xl ${currentHero.visual.chip}`}>{currentHero.visual.second}</div>
                  <div className="absolute left-8 top-16 grid h-14 min-w-14 rotate-[-12deg] place-items-center rounded-full bg-white/90 px-2 text-xs font-black text-slate-700 shadow-xl">{currentHero.visual.third}</div>
                  <span className="absolute left-8 top-2 text-3xl text-amber-400">✦</span>
                  <span className="absolute right-8 top-3 text-xl text-amber-500">✦</span>
                </div>
              </motion.article>
            </AnimatePresence>

            {/* 대시보드 마스코트 펫 — 슬라이드 위에서 빈 공간을 돌아다닌다(슬라이드 전환에도 유지) */}
            <DashboardPet slideId={currentHero.id} />

            <button
              type="button"
              onClick={() => moveHeroSlide(-1)}
              aria-label="이전 맞춤 학습"
              className="absolute left-3 top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-slate-950/70 text-xl text-white shadow-lg backdrop-blur transition hover:scale-105 hover:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-white sm:left-4"
            >
              ‹
            </button>
            <button
              type="button"
              onClick={() => moveHeroSlide(1)}
              aria-label="다음 맞춤 학습"
              className="absolute right-3 top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-slate-950/70 text-xl text-white shadow-lg backdrop-blur transition hover:scale-105 hover:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-white sm:right-4"
            >
              ›
            </button>

            <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full bg-white/75 p-1.5 shadow-lg backdrop-blur-md" role="tablist" aria-label="맞춤 학습 슬라이드">
              {HERO_SLIDES.map((slide, index) => (
                <button
                  key={slide.id}
                  type="button"
                  role="tab"
                  aria-selected={heroSlide === index}
                  aria-label={`${slide.tab} 슬라이드`}
                  onClick={() => selectHeroSlide(index)}
                  className={`rounded-full px-3 py-2 text-[11px] font-black transition sm:px-4 ${heroSlide === index ? 'bg-slate-950 text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-slate-900'}`}
                >
                  {slide.tab}
                </button>
              ))}
            </div>
          </div>
        </motion.section>
      </main>
    </div>
  )
}
