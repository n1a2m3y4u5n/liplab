import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { reviewAPI, learningAPI } from '../api'

/**
 * 복습 탭 (Figma 리디자인 05) — 오답·북마크 복습 진입 + 복습 항목 리스트.
 * 실데이터: reviewAPI.getDue(예정), learningAPI.getReviewSentences(오답), getBookmarks(북마크).
 * 각 항목은 트랙 배지(독화=보라 / 발화=핑크) + 단어 + 사유. 클릭 시 해당 복습 흐름으로 이동.
 */
function GradientCta({ count, title, sub, btn, from, to, border, btnColor, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className="relative flex-1 overflow-hidden rounded-[20px] border-2 border-b-[5px] p-6 text-left"
      style={{ backgroundImage: `linear-gradient(155deg, ${from} 0%, ${to} 71%)`, borderColor: border }}>
      <div className="flex flex-col gap-4">
        <div className="text-white">
          <p className="text-[22px] font-bold tracking-[-0.44px]">{title} {count}개</p>
          <p className="mt-1 text-[13.5px] opacity-85">{sub}</p>
        </div>
        <span className="inline-flex w-fit items-center rounded-[13px] border-2 border-b-4 border-white/60 bg-white px-6 py-3 text-[15px] font-bold" style={{ color: btnColor }}>{btn}</span>
      </div>
    </button>
  )
}

function ReviewItem({ track, word, meta, onClick, first }) {
  const isSpeak = track === '발화'
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full items-center gap-3.5 py-3.5 text-left ${first ? '' : 'border-t-[1.5px] border-line'}`}>
      <span className={`flex w-[54px] shrink-0 items-center justify-center rounded-lg py-[5px] text-[11.5px] font-bold ${isSpeak ? 'bg-[#ffe4e9] text-[#be185d]' : 'bg-primary-100 text-primary-700'}`}>{track}</span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-[16px] font-bold text-ink">{word}</span>
        <span className="text-[12.5px] text-ink-muted">{meta}</span>
      </span>
      <img src="/ui/review-arrow.svg" alt="" className="h-3 w-1.5" />
    </button>
  )
}

export default function ReviewTab() {
  const navigate = useNavigate()
  const [due, setDue] = useState(0)
  const [wrong, setWrong] = useState(0)
  const [marks, setMarks] = useState(0)
  const [items, setItems] = useState([])
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    let on = true
    Promise.all([
      reviewAPI.getDue().catch(() => ({ items: [] })),
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks('read').catch(() => []),
    ]).then(([dueRes, wrongRes, bmRes]) => {
      if (!on) return
      const dueItems = dueRes.items || []
      const wrongArr = Array.isArray(wrongRes) ? wrongRes : (wrongRes.items || [])
      const bmArr = Array.isArray(bmRes) ? bmRes : (bmRes.items || [])
      setDue(dueItems.length)
      setWrong(wrongArr.length)
      setMarks(bmArr.length)
      const norm = (arr, kind) => arr.slice(0, 8).map((x, i) => ({
        id: `${kind}-${i}`,
        track: (x.domain === 'speak' || x.track === 'speak') ? '발화' : '독화',
        word: x.word || x.sentence || x.text || x.target || '복습 항목',
        meta: kind === 'bookmark' ? '북마크를 했어요' : (x.wrong_count ? `${x.wrong_count}회 틀렸어요` : '다시 볼 항목'),
        kind,
      }))
      setItems([...norm(wrongArr, 'wrong'), ...norm(dueItems, 'due'), ...norm(bmArr, 'bookmark')])
    })
    return () => { on = false }
  }, [])

  const shown = items.filter((it) => filter === 'all' || (filter === 'wrong' ? it.kind !== 'bookmark' : it.kind === 'bookmark')).slice(0, 8)
  const chips = [
    { key: 'all', label: '전체', n: items.length },
    { key: 'wrong', label: '오답', n: wrong + due },
    { key: 'bookmark', label: '북마크', n: marks },
  ]

  return (
    <AppShell active="review" title="복습" description="잊어버릴 때쯤 다시 나와요. 오늘 것만 가볍게 확인해보세요.">
      <div className="flex w-full flex-col gap-3.5 sm:flex-row">
        <GradientCta count={wrong + due} title="복습할 오답" sub="오답 다시보기" btn="오답 복습하기"
          from="#a78bfa" to="#7d53de" border="#5f3ab8" btnColor="#5f3ab8" onClick={() => navigate('/review/mistakes')} />
        <GradientCta count={marks} title="복습할 북마크" sub="북마크 다시보기" btn="북마크 복습하기"
          from="#60a5fa" to="#2563eb" border="#1d4ed8" btnColor="#1d4ed8" onClick={() => navigate('/review/saved')} />
      </div>

      <section className="card-flat w-full">
        <div className="flex gap-2">
          {chips.map((c) => (
            <button key={c.key} type="button" onClick={() => setFilter(c.key)}
              className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-[13.5px] font-bold ${filter === c.key ? 'bg-primary-500 text-white' : 'bg-gray-100 text-ink-muted'}`}>
              {c.label}<span className={filter === c.key ? 'text-white/75' : 'text-gray-400'}>{c.n}</span>
            </button>
          ))}
        </div>
        <div className="mt-2">
          {shown.length === 0 ? (
            <p className="py-10 text-center text-sm text-ink-muted">복습할 항목이 없어요. 잘하고 있어요!</p>
          ) : shown.map((it, i) => (
            <ReviewItem key={it.id} {...it} first={i === 0}
              onClick={() => navigate(it.kind === 'bookmark' ? '/review/saved' : '/review/mistakes')} />
          ))}
        </div>
      </section>
    </AppShell>
  )
}
