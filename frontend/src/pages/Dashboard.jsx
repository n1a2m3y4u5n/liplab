import { useState, useEffect, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI, curriculumAPI, reviewAPI, speakAPI, tactileAPI } from '../api'

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

const SEARCH_ITEMS = [
  { keywords: ['입모양', '독화', '기초', '비지움'], to: '/learn/viseme' },
  { keywords: ['단어', '음절'], to: '/learn/word' },
  { keywords: ['문장', '테스트', '대화', '실전'], to: '/learn/scenario' },
  { keywords: ['말하기', '발음', '억양'], to: '/learn/speaking' },
  { keywords: ['촉각', '타도마', '하드웨어'], to: '/learn/tactile' },
  { keywords: ['수어', '손말'], to: '/learn/sign' },
  { keywords: ['복습', '오답'], to: '/review/today' },
  { keywords: ['북마크', '저장'], to: '/review/saved' },
  { keywords: ['분석', '기록', '통계'], to: '/analysis/overview' },
  { keywords: ['사용법', '가이드', '도움말'], to: '/guide' },
]

const TOPIC_MENUS = [
  {
    id: 'learn',
    label: '학습',
    title: '새로운 내용을 익혀요',
    description: '보고, 말하고, 느끼는 방식 중 나에게 맞는 학습을 선택하세요.',
    theme: {
      active: 'bg-sky-50 text-sky-700',
      line: 'bg-sky-500',
      badge: 'bg-sky-100 text-sky-700',
      hover: 'hover:border-sky-200 hover:bg-sky-50/70',
    },
    items: [
      { label: '입모양 기초', description: '자음·모음의 입모양 익히기', to: '/learn/viseme' },
      { label: '음절·단어', description: '비슷한 입모양 구별하기', to: '/learn/word' },
      { label: '문장·대화 실전', description: '상황별 독화 능력 확인하기', to: '/learn/scenario' },
      { label: '말하기 연습', description: '내 발음과 억양 다듬기', to: '/learn/speaking' },
      { label: '촉각 학습', description: '움직임과 진동을 손으로 익히기', to: '/learn/tactile' },
      { label: '수어 학습', description: '문장을 수어로 함께 확인하기', to: '/learn/sign' },
    ],
  },
  {
    id: 'review',
    label: '복습',
    title: '기억이 오래가도록 반복해요',
    description: '예정된 항목, 틀린 문제, 저장한 문장을 다시 확인하세요.',
    theme: {
      active: 'bg-amber-50 text-amber-800',
      line: 'bg-amber-500',
      badge: 'bg-amber-100 text-amber-800',
      hover: 'hover:border-amber-200 hover:bg-amber-50/70',
    },
    items: [
      { label: '오늘의 복습', description: '지금 복습할 항목 한눈에 보기', to: '/review/today' },
      { label: '입모양·단어 복습', description: '간격 반복 일정에 맞춰 복습하기', to: '/review/scheduled' },
      { label: '틀린 문장 다시 풀기', description: '독화 오답을 문장으로 재연습하기', to: '/review/mistakes' },
      { label: '말하기 복습', description: '부족했던 발음 다시 연습하기', to: '/review/speaking' },
      { label: '촉각 복습', description: '촉각 단계의 취약 항목 확인하기', to: '/review/tactile' },
      { label: '저장한 문장', description: '북마크한 문장 모아보기', to: '/review/saved' },
    ],
  },
  {
    id: 'analysis',
    label: '분석',
    title: '학습 흐름과 취약점을 확인해요',
    description: '최근 기록을 바탕으로 강점과 다음 학습 방향을 살펴보세요.',
    theme: {
      active: 'bg-violet-50 text-violet-700',
      line: 'bg-violet-500',
      badge: 'bg-violet-100 text-violet-700',
      hover: 'hover:border-violet-200 hover:bg-violet-50/70',
    },
    items: [
      { label: '종합 학습 분석', description: '독화·말하기 결과 함께 보기', to: '/analysis/overview' },
      { label: '학습 활동', description: '최근 90일 학습 흐름 확인하기', to: '/analysis/activity' },
      { label: '취약 입모양', description: '자주 틀리는 발음 특징 찾아보기', to: '/analysis/visemes' },
      { label: '평균 점수', description: '학습별 점수 변화 살펴보기', to: '/analysis/scores' },
      { label: '학습 기록', description: '완료한 세션과 누적 성과 보기', to: '/analysis/history' },
      { label: '학습 가이드', description: '분석 결과 활용 방법 알아보기', to: '/analysis/guide' },
    ],
  },
]

const HERO_SLIDES = [
  {
    id: 'viseme',
    tab: '입모양 기초',
    eyebrow: '맞춤 학습 01',
    title: ['입모양 기초부터', '차근차근 시작해요.'],
    description: '자음과 모음의 핵심 입모양을 보고 구별하는 첫 단계입니다.',
    to: '/learn/viseme',
    cta: '입모양 학습 시작',
    background: 'from-[#fffede] via-[#fffbb6] to-[#fff58d]',
    badge: 'bg-white/75 text-sky-700',
    visual: { shape: 'from-sky-300 via-sky-400 to-sky-600', shadow: 'shadow-[0_30px_60px_rgba(2,132,199,0.28)]', first: '가', second: 'ㅁ', third: '입', chip: 'bg-sky-100 text-sky-700' },
  },
  {
    id: 'scenario',
    tab: '문장 실전',
    eyebrow: '맞춤 학습 02',
    title: ['일상 속 문장을', '상황으로 익혀요.'],
    description: '카페, 병원, 학교처럼 자주 마주치는 장면으로 독화를 연습합니다.',
    to: '/learn/scenario',
    cta: '상황별 실전 열기',
    background: 'from-[#effcff] via-[#dff7ff] to-[#ccefff]',
    badge: 'bg-white/80 text-cyan-700',
    visual: { shape: 'from-cyan-300 via-cyan-400 to-blue-500', shadow: 'shadow-[0_30px_60px_rgba(6,182,212,0.25)]', first: '카페', second: '병원', third: '대화', chip: 'bg-cyan-100 text-cyan-700' },
  },
  {
    id: 'speaking',
    tab: '말하기',
    eyebrow: '맞춤 학습 03',
    title: ['내 목소리를 보며', '발음을 다듬어요.'],
    description: '소리의 크기와 억양을 시각적으로 확인하며 또박또박 말해봅니다.',
    to: '/learn/speaking',
    cta: '말하기 연습 시작',
    background: 'from-[#fff6f7] via-[#ffe7eb] to-[#ffd5dc]',
    badge: 'bg-white/80 text-rose-700',
    visual: { shape: 'from-rose-300 via-rose-400 to-pink-500', shadow: 'shadow-[0_30px_60px_rgba(244,63,94,0.22)]', first: '소리', second: '억양', third: '발음', chip: 'bg-rose-100 text-rose-700' },
  },
  {
    id: 'tactile',
    tab: '촉각',
    eyebrow: '맞춤 학습 04',
    title: ['말의 움직임을', '손끝으로 느껴요.'],
    description: '턱과 입술의 움직임, 진동과 바람을 촉각으로 익히는 학습입니다.',
    to: '/learn/tactile',
    cta: '촉각 학습 시작',
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

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const statistics = useStore((state) => state.statistics)
  const setStatistics = useStore((state) => state.setStatistics)

  const [searchTerm, setSearchTerm] = useState('')
  const [activeNavMenu, setActiveNavMenu] = useState(null)
  const [heroSlide, setHeroSlide] = useState(0)
  const [heroDirection, setHeroDirection] = useState(1)
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

  const goToSection = (id) => {
    const element = document.getElementById(id)
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const submitSearch = (event) => {
    event.preventDefault()
    const query = searchTerm.trim().toLowerCase().replace(/\s/g, '')
    if (!query) return
    const result = SEARCH_ITEMS.find((item) => item.keywords.some((keyword) => {
      const normalized = keyword.toLowerCase().replace(/\s/g, '')
      return normalized.includes(query) || query.includes(normalized)
    }))
    if (result) navigate(result.to)
    else alert('찾는 학습을 발견하지 못했어요. 학습 메뉴에서 전체 콘텐츠를 확인해주세요.')
  }

  const activeTopic = TOPIC_MENUS.find((topic) => topic.id === activeNavMenu)

  const chooseTopicItem = (to) => {
    setActiveNavMenu(null)
    navigate(to)
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
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-xl">
        <div className="border-b border-slate-100 bg-slate-50/90">
          <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-2 text-[11px] text-slate-500 sm:px-6">
            <button type="button" onClick={() => navigate('/dashboard')} className="inline-flex items-center gap-1.5 font-bold text-slate-700 hover:text-primary-700">
              <span aria-hidden="true">⌂</span>
              메인 바로가기
            </button>
            <p className="hidden sm:block"><b className="text-slate-700">{user?.username}님</b>, 오늘도 나에게 맞는 방식으로 학습해 보세요.</p>
          </div>
        </div>

        <div className="mx-auto max-w-[1440px] px-4 sm:px-6">
          <div className="flex min-h-[86px] items-center gap-4 py-4 sm:gap-7">
            <button type="button" onClick={() => navigate('/dashboard')} className="flex shrink-0 items-center gap-2 text-left">
              <span aria-hidden="true" className="relative grid h-10 w-10 place-items-center rounded-2xl bg-sky-50">
                <span className="absolute h-4 w-7 rounded-full border-[3px] border-sky-400" />
                <span className="absolute h-7 w-4 rounded-full border-[3px] border-sky-400" />
              </span>
              <span>
                <span className="block text-2xl font-black tracking-[-0.05em] text-slate-950">LIPLAB</span>
                <span className="hidden text-[10px] font-medium text-slate-400 sm:block">Visual Language Lab</span>
              </span>
            </button>

            <form onSubmit={submitSearch} className="hidden max-w-2xl flex-1 md:block" role="search">
              <label htmlFor="learning-search" className="sr-only">학습 콘텐츠 검색</label>
              <div className="flex h-12 items-center overflow-hidden rounded-full border-2 border-sky-300 bg-white pl-5 pr-2 transition focus-within:border-sky-500 focus-within:ring-4 focus-within:ring-sky-100">
                <input
                  id="learning-search"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
                  placeholder="배우고 싶은 입모양, 단어, 학습을 검색해 보세요."
                />
                <button type="submit" aria-label="검색" className="grid h-9 w-9 place-items-center rounded-full text-xl text-slate-800 hover:bg-sky-50">⌕</button>
              </div>
            </form>

            <div className="ml-auto hidden items-center gap-1 xl:flex">
              {[
                ['복습', '/review/today', '↻'],
                ['북마크', '/review/saved', '★'],
                ['사용법', '/guide', '?'],
              ].map(([label, to, icon]) => (
                <button key={label} type="button" onClick={() => navigate(to)} className="group flex w-16 flex-col items-center gap-1 rounded-xl py-2 text-[11px] font-bold text-slate-600 transition hover:bg-sky-50 hover:text-sky-700">
                  <span aria-hidden="true" className="grid h-7 w-7 place-items-center text-lg">{icon}</span>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={submitSearch} className="pb-4 md:hidden" role="search">
            <label htmlFor="learning-search-mobile" className="sr-only">학습 콘텐츠 검색</label>
            <div className="flex h-11 items-center rounded-full border-2 border-sky-300 px-4 focus-within:border-sky-500">
              <input id="learning-search-mobile" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder="학습 콘텐츠 검색" />
              <button type="submit" aria-label="검색" className="text-lg">⌕</button>
            </div>
          </form>
        </div>

        <nav
          className="relative border-t border-slate-100"
          aria-label="학습 콘텐츠"
          onMouseLeave={() => setActiveNavMenu(null)}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setActiveNavMenu(null)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setActiveNavMenu(null)
              event.currentTarget.querySelector(`[data-topic="${activeNavMenu}"]`)?.focus()
            }
          }}
        >
          <div className="mx-auto flex max-w-[1440px] items-center overflow-x-auto px-4 py-1 sm:px-6">
            <div className="mr-3 inline-flex shrink-0 items-center gap-2 px-2 py-3 text-sm font-black text-sky-600 sm:mr-7">
              <span aria-hidden="true" className="text-lg">☰</span>
              학습 콘텐츠
            </div>
            <div className="flex items-stretch gap-1" role="menubar" aria-label="학습 콘텐츠 주제">
              {TOPIC_MENUS.map((topic) => {
                const active = activeNavMenu === topic.id
                return (
                  <button
                    key={topic.id}
                    type="button"
                    role="menuitem"
                    data-topic={topic.id}
                    aria-haspopup="true"
                    aria-expanded={active}
                    aria-controls={`topic-menu-${topic.id}`}
                    onMouseEnter={() => setActiveNavMenu(topic.id)}
                    onFocus={() => setActiveNavMenu(topic.id)}
                    onClick={() => setActiveNavMenu(active ? null : topic.id)}
                    className={`group relative min-w-[84px] shrink-0 rounded-xl px-5 py-3 text-sm font-black transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-inset sm:min-w-[104px] sm:text-base ${
                      active ? `${topic.theme.active} -translate-y-0.5 shadow-sm` : 'text-slate-800 hover:-translate-y-0.5 hover:bg-slate-50 hover:text-sky-700'
                    }`}
                  >
                    <span className="inline-flex items-center gap-2">
                      {topic.label}
                      <span aria-hidden="true" className={`text-[10px] transition-transform duration-200 ${active ? 'rotate-180' : ''}`}>⌄</span>
                    </span>
                    <span aria-hidden="true" className={`absolute inset-x-5 bottom-0 h-0.5 origin-center rounded-full transition-transform duration-200 ${topic.theme.line} ${active ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-75'}`} />
                  </button>
                )
              })}
            </div>
            <p className="ml-auto hidden shrink-0 text-xs font-medium text-slate-400 lg:block">
              주제를 선택하면 관련 메뉴를 한 번에 볼 수 있어요
            </p>
          </div>

          <AnimatePresence initial={false}>
            {activeTopic && (
              <motion.div
                id={`topic-menu-${activeTopic.id}`}
                role="menu"
                aria-label={`${activeTopic.label} 메뉴`}
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16, ease: 'easeOut' }}
                className="absolute inset-x-0 top-full z-50 max-h-[65vh] overflow-y-auto border-y border-slate-200 bg-white shadow-[0_24px_50px_rgba(15,23,42,0.14)]"
              >
                <div className="mx-auto grid max-w-[1440px] gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[250px_1fr] lg:gap-8 lg:py-7">
                  <div className="border-b border-slate-100 pb-4 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-8">
                    <span className={`inline-flex rounded-full px-3 py-1 text-[11px] font-black ${activeTopic.theme.badge}`}>{activeTopic.label}</span>
                    <h2 className="mt-3 text-xl font-black tracking-tight text-slate-950">{activeTopic.title}</h2>
                    <p className="mt-2 text-sm leading-relaxed text-slate-500">{activeTopic.description}</p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {activeTopic.items.map((item, index) => (
                      <button
                        key={`${activeTopic.id}-${item.label}`}
                        type="button"
                        role="menuitem"
                        onClick={() => chooseTopicItem(item.to)}
                        className={`group flex items-start gap-3 rounded-2xl border border-transparent p-3.5 text-left transition focus:outline-none focus:ring-2 focus:ring-sky-400 ${activeTopic.theme.hover}`}
                      >
                        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl text-[11px] font-black ${activeTopic.theme.badge}`}>
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <span className="min-w-0 pt-0.5">
                          <span className="block text-sm font-black text-slate-900 transition group-hover:text-slate-950">{item.label}</span>
                          <span className="mt-1 block text-xs leading-relaxed text-slate-500">{item.description}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </nav>
      </header>

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

      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 sm:py-7">

        <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4 lg:grid-cols-[250px_minmax(0,1fr)]">
          <aside className="overflow-hidden rounded-[24px] bg-[#f6f7fb] p-4 sm:p-5" aria-labelledby="category-heading">
            <div className="flex items-center justify-between lg:block">
              <h2 id="category-heading" className="text-base font-black text-sky-600">전체 학습 보기</h2>
              <span className="text-[11px] font-medium text-slate-400 lg:mt-1 lg:block">원하는 방식으로 바로 이동</span>
            </div>
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1.5 lg:overflow-visible">
              {[
                ['입모양 기초', '01', () => navigate('/learn/viseme')],
                ['음절·단어', '02', () => navigate('/learn/word')],
                ['문장·대화', '03', () => navigate('/learn/scenario')],
                ['말하기 연습', '04', () => navigate('/learn/speaking')],
                ['촉각 학습', '05', () => navigate('/learn/tactile')],
                ['오늘의 복습', '06', () => navigate('/review/today')],
                ['학습 분석', '07', () => navigate('/analysis/overview')],
              ].map(([label, number, onClick]) => (
                <button key={label} type="button" onClick={onClick} className="group flex shrink-0 items-center gap-3 rounded-xl bg-white px-3 py-2.5 text-left text-sm font-bold text-slate-700 transition hover:bg-sky-50 hover:text-sky-700 lg:w-full lg:bg-transparent">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white text-[10px] font-black text-sky-500 shadow-sm group-hover:bg-sky-100">{number}</span>
                  {label}
                </button>
              ))}
            </div>
          </aside>

          <div
            role="region"
            aria-roledescription="carousel"
            aria-label="LIPLAB 맞춤 학습"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') { event.preventDefault(); moveHeroSlide(-1) }
              if (event.key === 'ArrowRight') { event.preventDefault(); moveHeroSlide(1) }
            }}
            className="relative min-h-[560px] overflow-hidden rounded-[24px] outline-none ring-sky-400 transition focus-visible:ring-2 focus-visible:ring-offset-2 sm:min-h-[500px] lg:min-h-[420px]"
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
                className={`absolute inset-0 cursor-grab overflow-hidden bg-gradient-to-r ${currentHero.background} px-7 pb-24 pt-8 active:cursor-grabbing sm:px-12 sm:pt-10 lg:px-14 lg:pt-11`}
                style={{ touchAction: 'pan-y' }}
              >
                <div className="relative z-10 max-w-2xl md:pr-[230px] lg:pr-[310px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`inline-flex rounded-full px-3 py-1.5 text-xs font-black shadow-sm ${currentHero.badge}`}>LIPLAB {currentHero.eyebrow}</span>
                    <span className="hidden text-[11px] font-bold text-slate-500 sm:inline">좌우로 드래그해 보세요</span>
                  </div>
                  <h1 className="mt-5 text-3xl font-black leading-[1.2] tracking-[-0.045em] text-slate-950 sm:text-4xl xl:text-[44px]">
                    {currentHero.title[0]}<br />{currentHero.title[1]}
                  </h1>
                  <p className="mt-4 max-w-lg text-sm font-medium leading-relaxed text-slate-600 sm:text-base">{currentHero.description}</p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={() => navigate(currentHero.to)}
                      className="rounded-full bg-slate-950 px-5 py-3 text-sm font-black text-white transition hover:-translate-y-0.5 hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
                    >
                      {currentHero.cta}
                    </button>
                    <button
                      type="button"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={() => navigate('/guide')}
                      className="rounded-full border border-slate-900/15 bg-white/70 px-5 py-3 text-sm font-black text-slate-800 transition hover:bg-white"
                    >
                      사용법 보기
                    </button>
                  </div>
                  <dl className="mt-7 flex max-w-lg divide-x divide-slate-900/10 overflow-hidden rounded-2xl bg-white/65 backdrop-blur-sm">
                    {[
                      ['레벨', user?.current_level || 1],
                      ['연속 학습', `${user?.streak_count || 0}일`],
                      ['평균 점수', statsLoading ? '—' : `${statistics?.average_score || 0}점`],
                    ].map(([label, value]) => (
                      <div key={label} className="min-w-0 flex-1 px-3 py-3 text-center">
                        <dt className="truncate text-[10px] font-bold text-slate-500">{label}</dt>
                        <dd className="mt-0.5 text-sm font-black text-slate-900">{value}</dd>
                      </div>
                    ))}
                  </dl>
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

        <div className="mt-9 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-black tracking-[0.12em] text-sky-600">TODAY'S LEARNING</p>
            <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">오늘의 추천 학습</h2>
          </div>
          <button type="button" onClick={() => navigate('/guide')} className="hidden text-sm font-bold text-slate-500 hover:text-sky-700 sm:block">학습 방법 알아보기 →</button>
        </div>

        {/* 독화 학습 — 단계 사다리 + 문장·대화 실전을 한 카드로 통합 */}
        <section id="reading-learning" className="mt-4 scroll-mt-52">
          <CurriculumPath>
          <div id="reading-test" className="scroll-mt-52">
          <h2 className="mb-1 flex flex-wrap items-center gap-2 text-base font-bold text-gray-900">
            🎯 문장·대화 실전
            <span className="text-[11px] font-medium text-gray-400">3·4단계</span>
            {testLocked && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-400">🔒 잠김</span>
            )}
            {conversationLocked && !testLocked && (
              <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700">🔒 대화 잠김</span>
            )}
          </h2>
          <p className="mb-2 text-xs text-gray-500">
            AI의 <b className="text-gray-700">입모양을 눈으로 읽고</b> 무슨 말인지 알아맞히는 연습이에요. (말하기·발음이 아닙니다)
          </p>

          {testLocked ? (
            <div className="mb-2 rounded-lg border border-gray-200 bg-gray-50 p-2 text-xs text-gray-500">
              학습에서 2단계(음절·단어)를 완료하면 테스트가 열려요.
            </div>
          ) : (
            <div className="mb-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-xs text-blue-700">
              그동안 학습한 <b>독화(입모양 읽기)</b> 실력을 검증합니다. 주관식·4지선다·서술형 문제가 섞여서 출제돼요.
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
                  {loading ? 'AI 시나리오 준비 중…' : conversationLocked ? '🔒 대화 실전 · 잠김' : '👁️ AI 대화 독화'}
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
          </div>
          </CurriculumPath>
        </section>

        {/* 말하기 · 촉각 학습 */}
        <section className="mt-3 grid items-start gap-3 lg:grid-cols-2">
          <div id="speaking-learning" className="scroll-mt-52">
            <SpeakCurriculumPath />
          </div>
          <TactileCard />
        </section>

        <section className="mt-3">
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
          <div className="border-t border-slate-100 px-4 py-3">
            <button onClick={() => navigate('/analysis/overview')}
              className="text-sm font-semibold text-primary-600 hover:text-primary-700">
              📊 독화·말하기 상세 분석 보기 →
            </button>
          </div>
        </details>
      </main>
    </div>
  )
}
