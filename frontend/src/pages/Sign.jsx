import { useState, useEffect } from 'react'
import SignPanel from '../components/SignPanel'
import AppShell from '../components/AppShell'
import { markSignExplored } from '../lib/badges'

/**
 * 수어 함께 보기 (Figma 226:32 / 226:75) — 한국어 → 한국수어(KSL) 학습 보조
 * 문장을 입력하면 Claude가 KSL 문법으로 번역하고, 각 단어의 **실제 국립국어원 수어
 * 영상을 화면 안에서 재생**한다(사전에 없는 단어는 지문자). 입모양 아바타를 옆 칸에 나란히 둔다.
 * Figma대로 한 줄 입력(Enter로 보기) + 예시 칩. '공식 통역이 아님' 안내는 결과 아래 출처 표기에 있다.
 */
const EXAMPLES = ['학교에 갔어요', '밥 먹었어요', '고맙습니다', '내일 만나요']

// 카드 틀(226:142) — 2px 테두리, r18, p22, 머리-본문 16
const CARD = 'flex w-full flex-col gap-4 rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]'

export default function Sign() {
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')   // SignPanel에 넘길 확정 문장

  // '수어 탐험' 배지는 서버 기록이 없어 이 화면 진입을 브라우저에 표시해 판정한다(lib/badges.js).
  useEffect(() => { markSignExplored() }, [])

  // Practice 등에서 /sign?text=문장 으로 넘어오면 자동 번역
  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get('text')
    if (raw) {
      const q = raw.slice(0, 200)
      setText(q)
      setQuery(q)
    }
  }, [])

  const onSubmit = (e) => {
    e.preventDefault()
    const q = text.trim()
    if (q) setQuery(q)
  }

  return (
    <AppShell active="practice" title="수어 함께 보기" description="문장을 수어 영상으로도 확인해요">
      {/* 어떤 문장을 볼까요? (226:142) */}
      <section className={CARD}>
        <p className="text-[17px] font-bold leading-figma text-ink">어떤 문장을 볼까요?</p>
        <form onSubmit={onSubmit}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={200}
            enterKeyHint="go"
            aria-label="수어로 볼 한국어 문장"
            placeholder="수어로 볼 한국어 문장을 입력하세요 (예: 학교에 갔어요)"
            className="h-[58px] w-full rounded-14 border-2 border-line bg-white px-4 text-[15.5px] text-ink placeholder:text-[#c9c9d6] focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200"
          />
        </form>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => { setText(ex); setQuery(ex) }}
              className="rounded-full bg-surface-sunken px-4 py-[9px] text-[13px] font-bold leading-figma text-ink-muted transition hover:bg-surface-hover"
            >
              {ex}
            </button>
          ))}
        </div>
      </section>

      {/* 수어와 입모양 (226:156) — 나란히 보기 */}
      <section className={CARD}>
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">수어와 입모양</p>
          <span className="text-[13px] text-ink-muted">나란히 보기</span>
        </div>
        <SignPanel text={query} variant="split" />
      </section>
    </AppShell>
  )
}
