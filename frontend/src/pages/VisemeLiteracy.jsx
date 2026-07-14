import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI } from '../api'
import AvatarVRM from '../components/AvatarVRM'

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

// neutral(15) ↔ target 반복 → 입모양이 '만들어지는' 움직임을 보여준다.
// 정적보다 인지가 쉽고, 정답 숫자를 노출하지 않는다.
function VisemeAvatar({ visemeId, height = 300 }) {
  const [vid, setVid] = useState(15)
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
    <div className="w-full rounded-2xl overflow-hidden shadow-xl bg-gradient-to-b from-slate-800 to-slate-900"
         style={{ height }}>
      <AvatarVRM visemeId={vid} />
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
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">입모양 인지</h1>
            <p className="text-sm text-gray-500">10개 입모양 그룹을 익히고, 무엇이 보이고 무엇이 안 보이는지 배웁니다</p>
          </div>
          <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-800 text-sm">✕ 나가기</button>
        </div>
      </header>

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
  const [sel, setSel] = useState(lessons[0])
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
              <div className="text-sm font-bold text-gray-800">{l.name}</div>
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
          <div>
            <p className="text-xs text-gray-400 mb-1">예시 단어</p>
            <div className="flex flex-wrap gap-2">
              {sel.example_words.map((w) => (
                <span key={w} className="px-2.5 py-1 rounded-lg bg-white border border-gray-200 text-sm font-medium text-gray-700">{w}</span>
              ))}
            </div>
          </div>
        </div>
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
    // 선지는 언어학 용어(양순음 등)가 아니라 실제 자모(ㅁㅂㅃㅍ)로 보여준다 — 학습자가 실제로 볼 글자와 바로 연결되도록.
    const choices = shuffle([target, ...others]).map((l) => ({ viseme_id: l.viseme_id, phonemes: l.phonemes.join('') }))
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
    <div className="space-y-5">
      {/* 숙달도 */}
      <div className="card">
        <div className="flex justify-between text-sm mb-1.5">
          <span className="text-gray-600">숙달도 (정확도)</span>
          <span className="font-semibold text-primary-600">{stat.mastery}% · {stat.attempts}회</span>
        </div>
        <div className="bg-gray-200 rounded-full h-2 overflow-hidden">
          <div className="bg-primary-500 h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(stat.mastery, 100)}%` }} />
        </div>
        {stat.mastered && <p className="mt-2 text-sm font-semibold text-green-600">🎉 1단계 숙달! 입모양 인지에 익숙해졌어요.</p>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <p className="text-sm text-gray-500 mb-3">이 입모양은 어느 그룹일까요?</p>
          <VisemeAvatar visemeId={q.target.viseme_id} />
        </div>

        <div className="card">
          <div className="space-y-3">
            {q.choices.map((c) => {
              const isTarget = c.viseme_id === q.target.viseme_id
              const isChosen = result?.chosenId === c.viseme_id
              let cls = 'w-full text-left px-4 py-3 rounded-xl border-2 font-medium text-sm transition-all '
              if (!result) cls += 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 text-gray-800'
              else if (isTarget) cls += 'border-green-500 bg-green-50 text-green-800'
              else if (isChosen) cls += 'border-red-400 bg-red-50 text-red-700'
              else cls += 'border-gray-200 bg-gray-50 text-gray-400'
              return (
                <button key={c.viseme_id} disabled={!!result || submitting} onClick={() => choose(c.viseme_id)} className={cls}>
                  {c.phonemes}
                  {result && isTarget && <span className="float-right text-green-600">✓</span>}
                  {result && isChosen && !isTarget && <span className="float-right text-red-500">✗</span>}
                </button>
              )
            })}
          </div>

          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2">
                <div className={`p-3 rounded-lg text-sm ${result.correct ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                  {result.correct ? '정답! 🎉' : `오답 — 정답은 "${q.target.phonemes.join('')}"`}
                  {!result.correct && result.same_cluster && (
                    <p className="mt-1 text-gray-600">헷갈릴 만해요! 이 둘은 <b>같아 보이는 무리</b>라 입모양만으론 구별이 어렵습니다. 실제로는 문맥으로 판단해요.</p>
                  )}
                </div>
                <div className="p-3 bg-gray-50 rounded-lg text-xs text-gray-600">{result.target.teach}</div>
                <button onClick={newQ} className="btn-primary w-full py-2 text-sm">다음 문제 →</button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
