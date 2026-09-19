import { useState, useEffect, useMemo, useCallback, lazy, Suspense } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI } from '../api'
import LearnHeader from '../components/LearnHeader'
import AvatarVRM from '../components/AvatarVRM'
import VocalTract from '../components/VocalTract'
import VocalTractSimulator from '../components/VocalTractSimulator'
import CueBadges, { CueLegend } from '../components/CueBadges'

// MediaPipe 번들이 커서 펼칠 때만 로드(초기 번들 보호)
const WebcamMouthCheck = lazy(() => import('../components/WebcamMouthCheck'))

/**
 * 1단계 · 입모양 인지 (Viseme Literacy)
 * ------------------------------------------------------------------
 * 지금까지 앱은 입모양 15종을 '아바타 애니메이션'에만 썼다. 이 페이지는 그 입모양을
 * 실제로 '가르치는' 기초 단계다. 학습(10그룹 훑기) + 인지퀴즈(어느 그룹인지 맞히기).
 * 핵심 교육: 어떤 소리는 잘 보이고(모음·양순), 어떤 소리는 똑같이 보인다(동구형이음).
 *
 * 퀴즈는 LipSyncPlayer3D를 쓰지 않는다 — 그 컴포넌트는 하단에 'Viseme N'을 노출해
 * 정답이 새기 때문. 대신 AvatarVRM을 직접 써서 오버레이 없이 입모양만 보여준다.
 */

const VIS_BADGE = {
  high:   { label: '잘 보임',      cls: 'bg-green-100 text-green-700 border-green-300' },
  medium: { label: '보통',        cls: 'bg-amber-100 text-amber-700 border-amber-300' },
  low:    { label: '거의 안 보임', cls: 'bg-gray-200 text-gray-500 border-gray-300' },
}

const lessonLabel = (lesson) => {
  const phonemes = lesson?.phonemes?.join(', ')
  return phonemes ? `${lesson.name}(${phonemes})` : lesson?.name || ''
}

// neutral(15) ↔ target 반복 → 입모양이 '만들어지는' 움직임을 보여준다.
// 정적보다 인지가 쉽고, 정답 숫자를 노출하지 않는다.
function VisemeAvatar({ visemeId, height = 300 }) {
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
    <div>
      <div className="relative w-full rounded-2xl overflow-hidden shadow-xl bg-gradient-to-b from-slate-800 to-slate-900"
           style={{ height }}>
        <AvatarVRM visemeId={vid} xray={xray} />
        {showTract && (
          <div className="absolute bottom-2 right-2 w-28 bg-slate-900/85 border border-slate-700 rounded-xl p-1 backdrop-blur-sm">
            <VocalTract visemeId={vid} />
          </div>
        )}
      </div>
      {/* 안 보이는 조음(혀·치아) 시각화 토글 — 독화 교육 핵심 */}
      <div className="mt-2 flex gap-2">
        <button onClick={() => setXray((v) => !v)}
          className={`flex-1 py-1.5 text-xs rounded-lg font-medium transition-colors ${xray ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          title="피부를 반투명하게 해 안 보이는 혀·치아를 드러냄">🫥 투명 두상</button>
        <button onClick={() => setShowTract((v) => !v)}
          className={`flex-1 py-1.5 text-xs rounded-lg font-medium transition-colors ${showTract ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          title="측면 성도 단면으로 혀·입술·턱 조음 보기">🗣️ 성도 단면</button>
      </div>
    </div>
  )
}

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

function Splash({ text }) {
  return <div className="min-h-screen flex items-center justify-center text-gray-500">{text}</div>
}

export default function VisemeLiteracy() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('learn')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    curriculumAPI.getVisemeLessons()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Splash text="불러오는 중…" />
  if (!data) return <Splash text="콘텐츠를 불러오지 못했어요." />

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="reading"
        title="입모양 학습"
        description="10개 입모양 그룹을 익히고, 무엇이 보이고 무엇이 안 보이는지 배웁니다"
        onExit={() => navigate('/dashboard')}
      />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <div className="flex gap-1 mb-6 p-1 bg-gray-100 rounded-xl max-w-sm">
          {[['learn', '학습'], ['quiz', '인지 퀴즈']].map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${tab === id ? 'bg-white text-primary-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              {label}
            </button>
          ))}
        </div>

        {tab === 'learn' ? <LearnPanel data={data} /> : <QuizPanel data={data} />}
      </main>
    </div>
  )
}

function LearnPanel({ data }) {
  const { lessons, homophene_clusters, minimal_pairs } = data
  const [params] = useSearchParams()
  const _tv = parseInt(params.get('v'), 10)
  const [sel, setSel] = useState(lessons.find((l) => l.viseme_id === _tv) || lessons[0])
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
              className={`p-3 rounded-xl border-2 text-center transition-all ${active ? 'border-primary-500 bg-primary-50' : 'border-gray-200 bg-white hover:border-gray-300'}`}>
              <div className="text-xs font-bold leading-snug text-gray-800 sm:text-sm">{lessonLabel(l)}</div>
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
            <h3 className="text-xl font-bold text-gray-900">{sel.name}</h3>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${badge.cls}`}>{badge.label}</span>
            {data.anchors?.includes(sel.viseme_id) && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700">닻(뚜렷)</span>
            )}
          </div>
          <p className="text-sm text-gray-500">{sel.phonemes.join('  ·  ')}</p>
          <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-700"><b>입모양</b> — {sel.look}</div>
          <div className="p-3 bg-amber-50 border border-amber-100 rounded-lg text-sm text-amber-800"><b>독화 포인트</b> — {sel.teach}</div>
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
            <p className="text-xs text-gray-400 mb-1">예시 단어 · 안 보이는 소리를 기호로</p>
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
        <Suspense fallback={<div className="card text-sm text-gray-500">카메라 모듈 불러오는 중…</div>}>
          <WebcamMouthCheck visemeId={sel.viseme_id} visemeName={sel.name} articulationGuide={sel.articulation?.guide} />
        </Suspense>
      ) : (
        <button type="button" onClick={() => setShowCam(true)}
          className="w-full rounded-xl border-2 border-dashed border-gray-300 py-3 text-sm font-bold text-gray-600 transition hover:border-gray-400 hover:bg-gray-50">
          📷 웹캠으로 내 입모양 확인하기
        </button>
      )}

      {/* 성도 실험실 (축 E) — 혀 위치↔소리를 귀로 잇는 인터랙티브 조음 교구 */}
      <div className="card">
        <h3 className="text-base font-bold text-gray-900 mb-1">🔊 성도 실험실 — 조음과 소리 잇기</h3>
        <p className="text-sm text-gray-500 mb-3">밖에서 안 보이는 <b>혀 위치</b>를 직접 움직이면 소리가 어떻게 바뀌는지 들어봅니다. 모음마다 혀가 어디에 있어야 하는지 귀로 익힙니다.</p>
        <VocalTractSimulator />
      </div>

      {/* 동구형이음 교육 */}
      <div className="card">
        <h3 className="text-base font-bold text-gray-900 mb-1">👀 같아 보이는 입모양 (동구형이음)</h3>
        <p className="text-sm text-gray-500 mb-3">독화의 핵심 — 어떤 소리들은 입모양이 똑같아서 <b>문맥으로 판단</b>해야 합니다.</p>
        <div className="space-y-2">
          {homophene_clusters.map((c) => (
            <div key={c.id} className="p-3 bg-gray-50 rounded-lg text-sm">
              <b className="text-gray-800">{c.name}</b>
              <span className="text-gray-500 ml-1">
                ({c.viseme_ids.map((id) => lessons.find((l) => l.viseme_id === id)?.name).filter(Boolean).join(', ')})
              </span>
              <p className="text-gray-600 mt-1">{c.note}</p>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <p className="text-xs text-gray-400 mb-1.5">최소대립쌍 — 같아 보이는(●) / 다르게 보이는(○) 쌍</p>
          <div className="flex flex-wrap gap-2">
            {minimal_pairs.map((m, i) => (
              <span key={i} title={m.note}
                className={`px-2.5 py-1 rounded-lg text-sm border ${m.same_looking ? 'bg-red-50 border-red-200 text-red-700' : 'bg-green-50 border-green-200 text-green-700'}`}>
                {m.same_looking ? '●' : '○'} {m.a} / {m.b}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function QuizPanel({ data }) {
  const { lessons } = data
  const quizzable = useMemo(() => lessons.filter((l) => l.quizzable), [lessons])
  const [q, setQ] = useState(null)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState({ attempts: 0, mastery: 0, mastered: false })

  const newQ = useCallback(() => {
    const target = quizzable[Math.floor(Math.random() * quizzable.length)]
    const others = shuffle(lessons.filter((l) => l.viseme_id !== target.viseme_id)).slice(0, 3)
    const choices = shuffle([target, ...others]).map((l) => ({ viseme_id: l.viseme_id, name: lessonLabel(l) }))
    setQ({ target, choices })
    setResult(null)
  }, [lessons, quizzable])

  useEffect(() => { newQ() }, [newQ])

  const choose = async (chosenId) => {
    if (result || submitting) return
    setSubmitting(true)
    try {
      const r = await curriculumAPI.submitRecognition(q.target.viseme_id, chosenId)
      setResult({ ...r, chosenId })
      setStat({ attempts: r.attempts, mastery: r.mastery_score, mastered: r.mastered })
    } catch {
      /* 네트워크 실패는 조용히 무시 — 다시 시도 가능 */
    } finally {
      setSubmitting(false)
    }
  }

  if (!q) return null

  return (
    <div className="mx-auto flex max-w-[680px] flex-col">
      {/* 진행바 + 숙달도 */}
      <div className="flex items-center gap-4">
        <div className="h-3.5 flex-1 overflow-hidden rounded-full bg-line">
          <div className="h-full rounded-full bg-primary-500 transition-all duration-500" style={{ width: `${Math.min(stat.mastery, 100)}%` }} />
        </div>
        <span className="shrink-0 text-[15px] font-bold text-ink-muted">{stat.mastery}%</span>
      </div>

      <div className="mt-6">
        <p className="text-[13px] font-bold text-primary-500">입모양 인지 · {stat.attempts}회</p>
        <p className="mt-2 text-[26px] font-bold tracking-[-0.75px] text-ink sm:text-[30px]">이 입모양은 어느 그룹일까요?</p>
        {stat.mastered && <p className="mt-1 text-sm font-semibold text-emerald-600">🎉 1단계 숙달! 입모양 학습을 완료했어요.</p>}
      </div>

      {/* 입모양(3D) */}
      <div className="mt-6 rounded-[22px] border-2 border-line bg-white p-4">
        <VisemeAvatar visemeId={q.target.viseme_id} />
      </div>

      {/* 4지선다 */}
      <div className="mt-6 flex flex-col gap-3">
        {q.choices.map((c, i) => {
          const isTarget = c.viseme_id === q.target.viseme_id
          const isChosen = result?.chosenId === c.viseme_id
          let cls = 'flex items-center gap-4 rounded-2xl border-2 border-b-[5px] px-5 py-4 text-left font-bold text-[17px] transition-all '
          let chip = 'bg-gray-100 text-ink-muted'
          if (!result) cls += 'border-line bg-white text-ink hover:border-primary-400 hover:bg-primary-50 active:translate-y-[3px] active:border-b-2'
          else if (isTarget) { cls += 'border-emerald-500 bg-emerald-50 text-emerald-800'; chip = 'bg-emerald-500 text-white' }
          else if (isChosen) { cls += 'border-rose-400 bg-rose-50 text-rose-700'; chip = 'bg-rose-400 text-white' }
          else cls += 'border-line bg-gray-50 text-gray-400'
          return (
            <button key={c.viseme_id} disabled={!!result || submitting} onClick={() => choose(c.viseme_id)} className={cls}>
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[13px] ${chip}`}>{i + 1}</span>
              <span className="flex-1">{c.name}</span>
              {result && isTarget && <span className="text-emerald-600">✓</span>}
              {result && isChosen && !isTarget && <span className="text-rose-500">✕</span>}
            </button>
          )
        })}
      </div>

      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-5 space-y-3">
            <div className={`rounded-2xl px-4 py-3 text-[15px] font-bold ${result.correct ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
              {result.correct ? '정답이에요! 🎉' : `오답 — 정답은 "${lessonLabel(q.target)}"`}
              {!result.correct && result.same_cluster && (
                <p className="mt-1 text-[13px] font-normal text-ink-muted">헷갈릴 만해요! 이 둘은 <b>같아 보이는 무리</b>라 입모양만으론 구별이 어렵습니다. 실제로는 문맥으로 판단해요.</p>
              )}
            </div>
            <div className="rounded-2xl border-2 border-line bg-white p-3 text-[13px] text-ink-muted">{result.target.teach}</div>
            <button onClick={newQ} className="btn-primary w-full !py-3.5 text-[18px]">다음 문제 →</button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
