import { useState, useEffect } from 'react'
import SignPanel from '../components/SignPanel'
import AppShell from '../components/AppShell'
import { markSignExplored } from '../lib/badges'

/**
 * 수어 보기 (Figma 226:32 / 226:75): 한국어 → 한국수어(KSL) 학습 보조
 * 문장을 입력하면 Claude가 KSL 문법으로 번역하고, 각 단어의 **실제 국립국어원 수어
 * 영상을 화면 안에서 재생**한다(사전에 없는 단어는 지문자).
 * 9/26 Figma: 제목이 '수어 보기'로 바뀌고 예시 칩·입모양 아바타 칸이 빠졌다(한 줄 입력 + '수어' 영상 칸 하나).
 * 제목 줄 오른쪽 X는 연습 탭으로(변경 내역 §4-4). '공식 통역이 아님' 안내는 결과 아래 출처 표기에 있다.
 */

// 카드 틀(226:142) — 2px 테두리, r18, p22, 머리-본문 16
const CARD = 'flex w-full flex-col gap-4 rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]'

export default function Sign() {
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')   // SignPanel에 넘길 확정 문장
  const [attempt, setAttempt] = useState(0)   // 같은 문장을 다시 보낸 횟수(SignPanel key)

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
    if (!q) return
    // SignPanel은 문장이 바뀔 때만 다시 번역한다. 번역이 실패한 뒤 같은 문장을 다시 보내면 아무 일도 없어
    // 다시 시도할 길이 없었다 → 같은 문장이면 key를 바꿔 패널을 새로 띄워 다시 번역한다.
    if (q === query) setAttempt((n) => n + 1)
    else setQuery(q)
  }

  return (
    <AppShell active="practice" title="수어 보기" closeTo="/practice/hub">
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
            className="h-[58px] w-full rounded-14 border-2 border-line bg-white px-4 text-[15.5px] text-ink placeholder:text-placeholder focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200"
          />
        </form>
      </section>

      {/* 수어 (226:156): 머리글 + 영상 칸 하나 */}
      <section className={CARD}>
        <p className="text-[17px] font-bold leading-figma text-ink">수어</p>
        <SignPanel key={attempt} text={query} variant="single" />
      </section>
    </AppShell>
  )
}
