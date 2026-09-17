import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import useStore from '../../store/useStore'
import { learningAPI, reviewAPI, speakAPI } from '../../api'
import { buildQTypes } from './buildQTypes'

// ── 오늘의 복습 — 두 기둥(독화·말하기) 모두 예정(SRS)·틀림·북마크 3분할 ──────
export default function ReviewSection() {
  const navigate = useNavigate()
  const setScenario = useStore((s) => s.setScenario)
  const [data, setData] = useState(null)          // { read, speak } 각 {due, wrong, bookmark}
  const [wrongSentences, setWrongSentences] = useState([])  // 독화 문장 복습(오답)용

  useEffect(() => {
    Promise.all([
      reviewAPI.getDue().catch(() => ({ items: [] })),
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks('read').catch(() => []),
      speakAPI.getReview().catch(() => ({ buckets: { due: 0, wrong: 0, bookmark: 0 } })),
    ]).then(([due, wrong, bm, speak]) => {
      setWrongSentences(wrong || [])
      setData({
        read: { due: (due.items || []).length, wrong: (wrong || []).length, bookmark: (bm || []).length },
        speak: speak.buckets || { due: 0, wrong: 0, bookmark: 0 },
      })
    })
  }, [])

  // 독화 문장 복습(오답 문장) → /practice. 예정(SRS 입모양·단어)이 있으면 /review 우선.
  const startReadReview = () => {
    if (data?.read.due > 0) { navigate('/review/scheduled'); return }
    const sents = wrongSentences.map((w) => w.sentence)
    if (sents.length) {
      setScenario({ situation: '복습', level: 1, sentences: sents, qTypes: buildQTypes(sents.length), scenario_id: `review_${Date.now()}` }, 'test')
      navigate('/practice', { state: { review: true } })
      return
    }
    if (data?.read.bookmark > 0) { navigate('/review/saved'); return }   // 북마크만 있으면 저장한 문장으로
    navigate('/review/scheduled')   // 전부 비어도 안전 랜딩(빈 상태 안내)
  }

  const pillars = data ? [
    { key: 'read', icon: '👁️', label: '독화', b: data.read, onStart: startReadReview,
      theme: { bg: 'bg-sky-50/40', border: 'border-sky-100', badge: 'bg-sky-100 text-sky-700', btn: 'bg-sky-600 hover:bg-sky-700' } },
    { key: 'speak', icon: '🗣️', label: '말하기', b: data.speak, onStart: () => navigate('/review/speaking'),
      theme: { bg: 'bg-rose-50/40', border: 'border-rose-100', badge: 'bg-rose-100 text-rose-700', btn: 'bg-rose-600 hover:bg-rose-700' } },
  ] : []

  return (
    <motion.div id="daily-review" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card !p-4 scroll-mt-52">
      <div className="mb-0.5 flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-gray-900">오늘의 복습</h2>
        <span className="text-xs text-gray-400">두 기둥 · 예정·틀림·북마크</span>
      </div>
      <p className="mb-3 text-xs text-gray-500">
        독화·말하기를 각각 <b>예정(간격반복)</b> · <b>틀린 문제</b> · <b>북마크</b>로 복습해요.
      </p>

      {!data ? (
        <div className="py-4 text-center text-xs text-gray-400">불러오는 중...</div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
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
