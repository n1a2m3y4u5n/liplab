import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI } from '../api'
import AvatarVRM from '../components/AvatarVRM'
import VocalTract from '../components/VocalTract'
import VocalTractSimulator from '../components/VocalTractSimulator'
import BookmarkButton from '../components/BookmarkButton'
import useBookmark from '../lib/useBookmark'
import WatermarkCard from '../components/WatermarkCard'
import LoadingScreen from '../components/LoadingScreen'
import CueBadges, { CueLegend } from '../components/CueBadges'
import useChoiceKeys from '../lib/useChoiceKeys'

// MediaPipe 번들이 커서 펼칠 때만 로드(초기 번들 보호)
const WebcamMouthCheck = lazy(() => import('../components/WebcamMouthCheck'))

/**
 * 1단계 · 입모양 인지 (Viseme Literacy)
 * ------------------------------------------------------------------
 * 지금까지 앱은 입모양 15종을 '아바타 애니메이션'에만 썼다. 이 페이지는 그 입모양을
 * 실제로 '가르치는' 기초 단계다. 인지퀴즈(어느 그룹인지 맞히기) + 학습 자료(10그룹 훑기).
 * 핵심 교육: 어떤 소리는 잘 보이고(모음·양순), 어떤 소리는 똑같이 보인다(동구형이음).
 *
 * /learn/viseme 는 독화 레슨 공통 템플릿(핸드오프 §4-03 — 91:12 · 94:98 · 94:140 · 93:12, 모바일 235:34 · 235:71)
 * 으로 인지퀴즈를 바로 연다. 예전 상단 헤더·학습/퀴즈 탭은 Figma에 없어 뺐다.
 * 학습 자료(LearnPanel: 10그룹·웹캠·성도 실험실·동구형이음)는 Figma 프레임이 없어 지우지 않고
 * /learn/viseme?tab=learn (또는 ?v=그룹번호)로 연다 — 연습 탭의 '입모양 교실' 카드가 이리로 온다.
 *
 * 퀴즈는 LipSyncPlayer3D를 쓰지 않는다 — 그 컴포넌트는 하단에 'Viseme N'을 노출해
 * 정답이 새기 때문. 대신 AvatarVRM을 직접 써서 오버레이 없이 입모양만 보여준다.
 */

// 보임 정도 배지 — 의미색 토큰(잘 보임=good · 보통=warn · 거의 안 보임=회색)
const VIS_BADGE = {
  high:   { label: '잘 보임',      cls: 'bg-good-tint text-good-text border-good-line' },
  medium: { label: '보통',        cls: 'bg-warn-tint text-warn-text border-warn/40' },
  low:    { label: '거의 안 보임', cls: 'bg-surface-sunken text-ink-muted border-line' },
}

// 최소대립쌍은 승인 콘텐츠 병합으로 100쌍 넘게 불어난다. 학습 화면에서는 전부 나열하는 대신
// '같아 보임(●) 3 + 다르게 보임(○) 2'로 맛보기만 보여준다 — 개념 체감이 목적이고,
// 실제 드릴은 2단계(단어)에서 전량을 쓴다.
const PAIR_PREVIEW_SAME = 3
const PAIR_PREVIEW_DIFF = 2

const pickPairPreview = (pairs = []) => [
  ...pairs.filter((m) => m.same_looking).slice(0, PAIR_PREVIEW_SAME),
  ...pairs.filter((m) => !m.same_looking).slice(0, PAIR_PREVIEW_DIFF),
]

const lessonLabel = (lesson) => {
  const phonemes = lesson?.phonemes?.join(', ')
  return phonemes ? `${lesson.name}(${phonemes})` : lesson?.name || ''
}

// neutral(15) ↔ target 반복 → 입모양이 '만들어지는' 움직임을 보여준다.
// 정적보다 인지가 쉽고, 정답 숫자를 노출하지 않는다.
// height=null이면 부모 카드 높이를 채운다(className="h-full") — 레슨 입모양 카드(모바일 214 / lg 370).
function VisemeAvatar({ visemeId, height = 300, variant = 'learn', className = '' }) {
  const isQuiz = variant === 'quiz'
  const [vid, setVid] = useState(15)
  const [xray, setXray] = useState(false)        // 투명 두상: 피부 반투명 → 혀·치아 노출(계획서 F)
  const [showTract, setShowTract] = useState(false)  // 성도 단면(측면) 도식(계획서 E)
  useEffect(() => {
    let on = true
    let t
    const cycle = (toTarget) => {
      if (!on) return
      setVid(toTarget ? visemeId : 15)
      t = setTimeout(() => cycle(!toTarget), toTarget ? 850 : 450)
    }
    setVid(15)
    t = setTimeout(() => cycle(true), 250)
    return () => { on = false; clearTimeout(t) }
  }, [visemeId])
  return (
    <div className={className}>
      <div className={`relative w-full overflow-hidden ${height == null ? 'h-full' : ''} ${isQuiz ? 'rounded-2xl bg-gradient-to-b from-slate-800 to-slate-900' : 'rounded-2xl shadow-xl bg-gradient-to-b from-slate-800 to-slate-900'}`}
           style={height != null ? { height } : undefined}>
        <AvatarVRM visemeId={vid} xray={xray} />
        {showTract && (
          <div className="absolute bottom-2 right-2 w-28 bg-slate-900/85 border border-slate-700 rounded-xl p-1 backdrop-blur-sm">
            <VocalTract visemeId={vid} />
          </div>
        )}
      </div>
      {/* 안 보이는 조음(혀·치아) 시각화 토글 — 독화 교육 핵심 (학습 자료에서만) */}
      {!isQuiz && (
        <div className="mt-2 flex gap-2">
          <button onClick={() => setXray((v) => !v)}
            className={`flex-1 py-1.5 text-xs rounded-lg font-bold transition-colors ${xray ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}
            title="피부를 반투명하게 해 안 보이는 혀·치아를 드러냄">투명 두상</button>
          <button onClick={() => setShowTract((v) => !v)}
            className={`flex-1 py-1.5 text-xs rounded-lg font-bold transition-colors ${showTract ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}
            title="측면 성도 단면으로 혀·입술·턱 조음 보기">성도 단면</button>
        </div>
      )}
    </div>
  )
}

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)
// 레슨 시작 전 트랙 로딩(§4-10 223:30)을 최소 이만큼은 보인다 — 데이터가 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000

export default function VisemeLiteracy() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // 학습 자료는 ?tab=learn 또는 ?v=그룹(약점 입모양 바로가기)일 때만 — 기본은 레슨(인지퀴즈)
  const learnMode = params.get('tab') === 'learn' || params.get('v') != null
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [introDone, setIntroDone] = useState(false)

  useEffect(() => {
    curriculumAPI.getVisemeLessons()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [])

  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81). 학습 자료는 레슨이 아니라 기본 로딩(256:34).
  if (loading) return learnMode ? <LoadingScreen /> : <LoadingScreen variant="brand" track="perception" />
  if (!learnMode && !introDone) return <LoadingScreen variant="brand" track="perception" />
  if (!data) return <div className="flex min-h-[100dvh] items-center justify-center bg-page text-[15px] text-ink-muted">콘텐츠를 불러오지 못했어요.</div>

  if (learnMode) {
    return (
      <div className="min-h-[100dvh] bg-page">
        <main className="mx-auto max-w-5xl px-[18px] pb-12 pt-[18px] lg:px-6 lg:pt-7">
          <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="mb-5 block">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <LearnPanel data={data} />
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-[100dvh] bg-page">
      <QuizPanel data={data} />
    </div>
  )
}

function LearnPanel({ data }) {
  const { lessons, homophene_clusters, minimal_pairs } = data
  const [params] = useSearchParams()
  const _tv = parseInt(params.get('v'), 10)
  const [sel, setSel] = useState(lessons.find((l) => l.viseme_id === _tv) || lessons[0])
  const pairPreview = useMemo(() => pickPairPreview(minimal_pairs), [minimal_pairs])
  const [showCam, setShowCam] = useState(false)
  const badge = VIS_BADGE[sel.visibility] || VIS_BADGE.medium

  return (
    <div className="space-y-6">
      {/* 10그룹 칩 */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {lessons.map((l) => {
          const b = VIS_BADGE[l.visibility] || VIS_BADGE.medium
          const active = sel.viseme_id === l.viseme_id
          return (
            <button key={l.viseme_id} onClick={() => setSel(l)}
              className={`p-3 rounded-14 border-2 text-center transition-all ${active ? 'border-primary-500 bg-primary-50' : 'border-line bg-white hover:border-primary-300'}`}>
              <div className="text-xs font-bold leading-snug text-ink sm:text-sm">{lessonLabel(l)}</div>
              <div className={`mt-1 inline-block text-[10px] px-1.5 py-0.5 rounded-full border ${b.cls}`}>{b.label}</div>
            </button>
          )
        })}
      </div>

      {/* 상세 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <VisemeAvatar visemeId={sel.viseme_id} />
        </div>
        <div className="card flex flex-col gap-3">
          <div className="flex items-center flex-wrap gap-2">
            <h3 className="text-xl font-bold text-ink">{sel.name}</h3>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${badge.cls}`}>{badge.label}</span>
            {data.anchors?.includes(sel.viseme_id) && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700">닻(뚜렷)</span>
            )}
          </div>
          <p className="text-sm text-ink-muted">{sel.phonemes.join('  ·  ')}</p>
          <div className="p-3 bg-surface-muted rounded-lg text-sm text-ink"><b>입모양</b> — {sel.look}</div>
          <div className="p-3 bg-warn-tint border border-warn/30 rounded-lg text-sm text-warn-text"><b>독화 포인트</b> — {sel.teach}</div>
          {sel.articulation && (
            <div className="p-3 bg-sky-50 border border-sky-100 rounded-lg text-sm text-sky-900">
              <div className="flex items-center gap-1.5 mb-0.5">
                <b>소리 내는 법</b>
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">{sel.articulation.place}</span>
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">{sel.articulation.manner}</span>
                {sel.articulation.nasal && <span className="text-[11px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">비음</span>}
              </div>
              <span className="text-sky-800">밖에서 안 보이는 혀·조음 — {sel.articulation.guide}</span>
            </div>
          )}
          <div>
            <p className="text-xs text-ink-faint mb-1">예시 단어 · 안 보이는 소리를 기호로</p>
            <div className="flex flex-wrap items-end gap-2">
              {sel.example_words.map((w) => (
                <CueBadges key={w} text={w} />
              ))}
            </div>
            <div className="mt-2"><CueLegend /></div>
          </div>
        </div>
      </div>

      {/* 웹캠으로 따라하기 (축 D) — 펼칠 때만 MediaPipe 로드 */}
      {showCam ? (
        <Suspense fallback={<div className="card text-sm text-ink-muted">카메라 모듈 불러오는 중…</div>}>
          <WebcamMouthCheck visemeId={sel.viseme_id} visemeName={sel.name} articulationGuide={sel.articulation?.guide} />
        </Suspense>
      ) : (
        <button type="button" onClick={() => setShowCam(true)}
          className="w-full rounded-14 border-2 border-dashed border-line py-3 text-sm font-bold text-ink-muted transition hover:border-primary-300 hover:bg-white">
          웹캠으로 내 입모양 확인하기
        </button>
      )}

      {/* 성도 실험실 (축 E) — 혀 위치↔소리를 귀로 잇는 인터랙티브 조음 교구 */}
      <div className="card">
        <h3 className="text-base font-bold text-ink mb-1">성도 실험실 — 조음과 소리 잇기</h3>
        <p className="text-sm text-ink-muted mb-3">밖에서 안 보이는 <b>혀 위치</b>를 직접 움직이면 소리가 어떻게 바뀌는지 들어봅니다. 모음마다 혀가 어디에 있어야 하는지 귀로 익힙니다.</p>
        <VocalTractSimulator />
      </div>

      {/* 동구형이음 교육 */}
      <div className="card">
        <h3 className="text-base font-bold text-ink mb-1">같아 보이는 입모양 (동구형이음)</h3>
        <p className="text-sm text-ink-muted mb-3">독화의 핵심 — 어떤 소리들은 입모양이 똑같아서 <b>문맥으로 판단</b>해야 합니다.</p>
        <div className="space-y-2">
          {homophene_clusters.map((c) => (
            <div key={c.id} className="p-3 bg-surface-muted rounded-lg text-sm">
              <b className="text-ink">{c.name}</b>
              <span className="text-ink-muted ml-1">
                ({c.viseme_ids.map((id) => lessons.find((l) => l.viseme_id === id)?.name).filter(Boolean).join(', ')})
              </span>
              <p className="text-ink-muted mt-1">{c.note}</p>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <p className="text-xs text-ink-faint mb-1.5">최소대립쌍 예시 — 같아 보이는(●) / 다르게 보이는(○) 쌍</p>
          <div className="flex flex-wrap gap-2">
            {pairPreview.map((m, i) => (
              <span key={i} title={m.note}
                className={`px-2.5 py-1 rounded-lg text-sm border ${m.same_looking ? 'bg-bad-tint border-bad-line text-bad-text' : 'bg-good-tint border-good-line text-good-text'}`}>
                {m.same_looking ? '●' : '○'} {m.a} / {m.b}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

const QUIZ_LEN = 12  // 레슨 1회 문항 수(진행바 분모) — 숙달 판정과 별개

const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)

// 레슨 완료 스탯 카드(93:22) — 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-18 border-2 border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

// Figma "Lesson / 4. 완료"(93:12) — 레슨 컴포넌트의 마지막 상태. DOKA + 워터마크 스탯 3칸 + 버튼 2개.
function LessonComplete({ accuracy, xp, elapsedSec, onNext, onHome }) {
  return (
    <div className="flex min-h-[100dvh] w-full flex-col items-center justify-center gap-[26px] bg-page px-[18px] py-12">
      <span className="relative size-[140px] shrink-0">
        <img src="/ui/lp-93-12-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
      </span>
      <h1 className="text-center text-[38px] font-bold leading-figma tracking-[-0.95px] text-ink">레슨 완료!</h1>

      <div className="flex w-full max-w-[640px] gap-3.5 py-2">
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-percent.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>정답률</p>
          <p className={`${STAT_VALUE} text-primary-700`}>{accuracy}%</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-xp.svg', size: 157.945, top: -76, right: -71.44 }}>
          <p className={STAT_LABEL}>획득 XP</p>
          <p className={`${STAT_VALUE} text-warn-text`}>+{xp}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-clock.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>걸린 시간</p>
          <p className={`${STAT_VALUE} text-stat-level`}>{fmtDuration(elapsedSec)}</p>
        </WatermarkCard>
      </div>

      <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
        <button type="button" onClick={onNext} className={`btn-primary btn-lg ${DONE_BTN}`}>다음 레슨으로</button>
        <button type="button" onClick={onHome} className={`btn-secondary btn-lg text-track ${DONE_BTN}`}>커리큘럼으로 돌아가기</button>
      </div>
    </div>
  )
}

function QuizPanel({ data }) {
  const navigate = useNavigate()
  const { lessons } = data
  const quizzable = useMemo(() => lessons.filter((l) => l.quizzable), [lessons])
  const [q, setQ] = useState(null)
  const [selected, setSelected] = useState(null)   // 확인 전 선택(선택→확인 2단계)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState({ attempts: 0, mastery: 0, mastered: false })
  const [qNum, setQNum] = useState(1)              // 레슨 내 문항 번호(진행바)
  const [tally, setTally] = useState({ n: 0, correct: 0 })   // 이번 레슨에서 푼 문항·정답 수 → 완료 뷰 정답률
  const [done, setDone] = useState(false)          // 12문항을 마치면 완료 뷰(93:12)
  const [xpEarned, setXpEarned] = useState(0)      // 레슨 동안 서버가 준 XP 합(응답 xp_gained) → 완료 뷰
  // 문항 북마크 — 입모양 그룹의 대표 음절(없으면 이름)을 저장한다. 저장한 문장 화면에서 그 음절 입모양을 다시 본다.
  const [saved, toggleSaved] = useBookmark(q ? (q.target.demo_syllable || lessonLabel(q.target)) : null,
    { situation: q ? `입모양 · ${q.target.name}` : '' })
  const startRef = useRef(Date.now())              // 레슨 시작 시각 → 걸린 시간
  const [elapsedSec, setElapsedSec] = useState(0)

  const newQ = useCallback(() => {
    const target = quizzable[Math.floor(Math.random() * quizzable.length)]
    const others = shuffle(lessons.filter((l) => l.viseme_id !== target.viseme_id)).slice(0, 3)
    const choices = shuffle([target, ...others]).map((l) => ({ viseme_id: l.viseme_id, name: lessonLabel(l) }))
    setQ({ target, choices })
    setSelected(null)
    setResult(null)
  }, [lessons, quizzable])

  useEffect(() => { newQ() }, [newQ])

  // 보기 숫자 키 1~4(§4-03) — 채점 중·결과 표시 중에는 받지 않는다.
  useChoiceKeys(q?.choices, (c) => setSelected(c.viseme_id), !!q && !result && !submitting && !done)

  const confirm = async () => {
    if (result || submitting || selected == null) return
    setSubmitting(true)
    try {
      const r = await curriculumAPI.submitRecognition(q.target.viseme_id, selected)
      setResult({ ...r, chosenId: selected })
      setStat({ attempts: r.attempts, mastery: r.mastery_score, mastered: r.mastered })
      setXpEarned((x) => x + (r.xp_gained || 0))
      setTally((t) => ({ n: t.n + 1, correct: t.correct + (r.correct ? 1 : 0) }))
    } catch {
      /* 네트워크 실패는 조용히 무시 — 다시 시도 가능 */
    } finally {
      setSubmitting(false)
    }
  }
  // 계속하기 — 12번째 문항 뒤에는 완료 뷰로(걸린 시간은 이 순간으로 고정).
  const next = () => {
    if (qNum >= QUIZ_LEN) {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
      setDone(true)
      return
    }
    setQNum((n) => n + 1)
    newQ()
  }
  // 새 레슨(12문항) — 단계를 아직 숙달하지 못했을 때 '다음 레슨으로'가 같은 단계의 다음 세트를 연다.
  const restart = () => {
    setDone(false); setQNum(1); setTally({ n: 0, correct: 0 }); setXpEarned(0)
    startRef.current = Date.now()
    newQ()
  }

  if (!q) return null

  if (done) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : 0
    return (
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => (stat.mastered ? navigate('/learn/word') : restart())}
        onHome={() => navigate('/learn/path')} />
    )
  }

  const answered = qNum - 1 + (result ? 1 : 0)
  const pct = Math.round((answered / QUIZ_LEN) * 100)

  const optionState = (c) => {
    if (!result) return selected === c.viseme_id ? 'selected' : 'idle'
    if (c.viseme_id === q.target.viseme_id) return result.chosenId === c.viseme_id ? 'correct' : 'target'
    return result.chosenId === c.viseme_id ? 'wrong' : 'idle'
  }

  return (
    <>
      <div className="mx-auto flex w-full max-w-[676px] flex-col px-[18px] pb-[200px] pt-[18px] lg:pb-[150px] lg:pt-7">
        {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + n / 12 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{qNum} / {QUIZ_LEN}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          {/* 질문 + 북마크(91:19 · 328:40 / 모바일 235:42 · 328:64) */}
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">입모양 인지</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">이 입모양은 어느 그룹일까요?</h1>
            <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-[21px]" />
          </div>

          {/* 입모양 카드(91:22 560×370 / 모바일 235:45 전체 폭×214) — 아바타만, 무한 반복(다시 보기 없음) */}
          <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
            <VisemeAvatar visemeId={q.target.viseme_id} variant="quiz" height={null} className="h-full" />
          </div>

          {/* 4지선다(91:28 / 모바일 235:51) — 선택 → 확인 */}
          <div className="flex flex-col gap-2.5 lg:gap-3">
            {q.choices.map((c, i) => (
              <button key={c.viseme_id} type="button" disabled={!!result || submitting} onClick={() => setSelected(c.viseme_id)}
                aria-pressed={!result ? selected === c.viseme_id : undefined} className={OPTION_CLASS[optionState(c)]}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{c.name}</span>
              </button>
            ))}
          </div>

          {/* 결과 상세(문맥 힌트 · 독화 포인트) — 핵심 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                {!result.correct && result.same_cluster && (
                  <div className="rounded-16 border-2 border-warn/40 bg-warn-tint px-4 py-3 text-[13px] text-warn-text">
                    헷갈릴 만해요! 이 둘은 <b>같아 보이는 무리</b>라 입모양만으론 구별이 어렵습니다. 실제로는 문맥으로 판단해요.
                  </div>
                )}
                <div className="rounded-16 border-2 border-line bg-white p-3 text-[13px] text-ink-muted">{result.target.teach}</div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 하단 고정 바 — 문제(130:17) · 정답(94:133) · 오답(94:175). lg 미만(235:68 · 235:105)은 힌트 없이
          메시지 위·전체 폭 버튼 아래로 쌓는다(§4-12 "모바일 레슨의 하단 버튼은 전체 폭"). */}
      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            // 정오 피드백은 스크린리더에 알린다(role=status·aria-live) — 잔존청력·저시력 사용자 대상(c92fdc3, 병합 복원)
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{result.correct ? '정답이에요!' : '아쉬워요'}</p>
              <p className="line-clamp-2 text-[13px] font-bold opacity-80 lg:text-[14px]">{result.correct ? result.target.teach : `정답은 「${lessonLabel(q.target)}」예요`}</p>
            </div>
          ) : (
            <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">{selected == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}</span>
          )}
          {result ? (
            <button type="button" onClick={next} className={`${result.correct ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
          ) : (
            <button type="button" onClick={confirm} disabled={selected == null || submitting} className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
          )}
        </div>
      </div>
    </>
  )
}

// 하단 바 버튼 — 데스크톱 .btn-bar(40/15, 17px) 오른쪽, lg 미만 전체 폭 py16·16px(235:69 · 235:109)
const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'

// 보기 한 줄(91:29 / 모바일 235:52) — 기본 3D 하단테두리. 정답·오답 공개(94:119 · 94:161 · 94:169)는 2.5px 테두리.
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} border-[2.5px] border-good bg-good-tint text-good-text`,   // 고른 답이 정답
  target: `${OPTION_BASE} border-[2.5px] border-good bg-white text-ink`,              // 오답일 때 정답 표시
  wrong: `${OPTION_BASE} border-[2.5px] border-bad bg-bad-tint text-bad-text`,        // 고른 오답
}
