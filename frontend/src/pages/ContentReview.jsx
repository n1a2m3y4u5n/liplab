import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { contentReviewAPI } from '../api'
import LearnHeader from '../components/LearnHeader'
import LoadingScreen from '../components/LoadingScreen'

/**
 * 콘텐츠 사람검수(축 G '이중 게이트'의 사람 단계) — 운영자용.
 * LLM이 생성하고 규칙 게이트를 통과한 후보를, 운영자가 승인/반려한다. 승인분만 커리큘럼에 반영.
 * 서버가 LIPLAB_REVIEW=1일 때만 열린다(운영자 전용, 기본 비활성).
 */
const KIND_LABEL = { words: '단어', pairs: '헷갈리는 쌍', closures: '문맥 추론 문항' }

function ItemCard({ kind, item, onDecide, busy }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="min-w-0 flex-1 text-sm text-slate-800">
        {kind === 'words' && (
          <span><b>{item.word}</b> <span className="text-xs text-slate-400">난이도 {item.tier ?? '-'}</span></span>
        )}
        {kind === 'pairs' && (
          <span><b>{item.a}</b> ↔ <b>{item.b}</b>{' '}
            <span className="text-xs text-slate-400">{item.relation === 'homophene' ? '동구형이음' : '최소대립'}</span>
            {item.note && <span className="ml-1 block truncate text-[11px] text-slate-400">{item.note}</span>}
          </span>
        )}
        {kind === 'closures' && (
          <span><b>{item.display}</b> <span className="text-xs text-slate-500">정답 {item.answer}</span>
            {item.hint && <span className="ml-1 block truncate text-[11px] text-slate-400">힌트: {item.hint}</span>}
          </span>
        )}
      </div>
      <div className="flex shrink-0 gap-1.5">
        <button type="button" disabled={busy} onClick={() => onDecide('approve')}
          className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-40">승인</button>
        <button type="button" disabled={busy} onClick={() => onDecide('reject')}
          className="rounded-md border border-rose-300 px-2.5 py-1 text-xs font-bold text-rose-600 hover:bg-rose-50 disabled:opacity-40">반려</button>
      </div>
    </div>
  )
}

export default function ContentReview() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [denied, setDenied] = useState('')   // 403 사유(서버 문구). 기능이 꺼진 것과 운영자가 아닌 것을 구분해 보인다
  const [busyKey, setBusyKey] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await contentReviewAPI.candidates())
      setDenied('')
    } catch (e) {
      if (e?.response?.status === 403) setDenied(e.response.data?.detail || '운영자 계정만 콘텐츠를 검수할 수 있습니다.')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const decide = async (kind, item, idx, decision) => {
    const key = `${kind}:${idx}`
    setBusyKey(key)
    try {
      await contentReviewAPI.review(kind, item, decision)
      setData((d) => {
        const next = { ...d, pending: { ...d.pending, [kind]: d.pending[kind].filter((_, i) => i !== idx) } }
        const c = { ...next.counts[kind] }
        c.pending -= 1; c[decision === 'approve' ? 'approved' : 'rejected'] += 1
        next.counts = { ...next.counts, [kind]: c }
        return next
      })
    } catch { /* 무시 */ } finally { setBusyKey(null) }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader accent="etc" title="콘텐츠 검수" description="AI가 생성하고 규칙을 통과한 후보를 사람이 최종 승인합니다 (운영자용)."
        maxWidth="max-w-3xl" onExit={() => navigate('/dashboard')} />
      <main className="mx-auto max-w-3xl px-4 py-8 space-y-5">
        {loading ? (
          <LoadingScreen variant="inline" />
        ) : denied ? (
          <div className="rounded-2xl border border-slate-200 bg-white px-6 py-16 text-center text-sm text-slate-500">
            {denied}
            {/비활성/.test(denied) && (
              <> 서버에 <code className="rounded bg-slate-100 px-1">LIPLAB_REVIEW=1</code>을 설정하면 운영자 검수가 열립니다.</>
            )}
          </div>
        ) : !data ? (
          <div className="rounded-2xl border border-slate-200 bg-white py-16 text-center text-sm text-slate-500">불러오지 못했습니다.</div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3">
              {['words', 'pairs', 'closures'].map((k) => (
                <div key={k} className="rounded-2xl border border-slate-200 bg-white p-4 text-center">
                  <p className="text-xs font-bold text-slate-400">{KIND_LABEL[k]}</p>
                  <p className="mt-1 text-2xl font-black text-slate-800">{data.counts[k].pending}<span className="ml-1 text-sm font-bold text-slate-400">대기</span></p>
                  <p className="mt-0.5 text-[11px] text-slate-400">승인 {data.counts[k].approved} · 반려 {data.counts[k].rejected}</p>
                </div>
              ))}
            </div>
            {['words', 'pairs', 'closures'].map((kind) => (
              data.pending[kind].length > 0 && (
                <section key={kind}>
                  <h2 className="mb-2 text-sm font-bold text-slate-700">{KIND_LABEL[kind]} <span className="text-slate-400">({data.pending[kind].length})</span></h2>
                  <div className="space-y-1.5">
                    {data.pending[kind].slice(0, 50).map((item, i) => (
                      <ItemCard key={i} kind={kind} item={item} busy={busyKey === `${kind}:${i}`}
                        onDecide={(dec) => decide(kind, item, i, dec)} />
                    ))}
                  </div>
                </section>
              )
            ))}
            {['words', 'pairs', 'closures'].every((k) => data.pending[k].length === 0) && (
              <div className="rounded-2xl border border-slate-200 bg-white px-6 py-14 text-center text-sm text-slate-500">
                검수할 후보가 없습니다. 모두 처리됐어요. 새 콘텐츠는 <code className="rounded bg-slate-100 px-1">scripts/gen_content.py</code>로 생성합니다.
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
