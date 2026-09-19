import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SignPanel from '../components/SignPanel'
import AppShell from '../components/AppShell'

/**
 * 한국어 → 한국수어(KSL) 학습 보조 페이지
 * 문장을 입력하면 Claude가 KSL 문법으로 번역하고, 각 단어의 **실제 국립국어원 수어
 * 영상을 화면 안에서 재생**한다(사전에 없는 단어는 지문자). 학습·이해 보조용(베타).
 */
const EXAMPLES = ['학교에 갔어요', '밥 먹었어요', '고맙습니다', '내일 만나요']

export default function Sign() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')   // SignPanel에 넘길 확정 문장

  // Practice 등에서 /sign?text=문장 으로 넘어오면 자동 번역
  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get('text')
    if (raw) {
      const q = raw.slice(0, 200)
      setText(q)
      setQuery(q)
    }
  }, [])

  return (
    <AppShell active="practice" title="수어 함께 보기" description="문장을 수어 영상으로도 확인해요">
      <div className="w-full">
        {/* 베타 안내 — 공식 수어 통역이 아님을 명확히(학습·이해 보조) */}
        <div className="mb-4 rounded-[14px] border-2 border-primary-100 bg-primary-50 px-4 py-2.5 text-[13px] text-ink-muted">
          <b className="text-primary-700">AI 수어 번역 (베타)</b> · 한국어를 한국수어 문법으로 옮겨 실제 수어 영상으로 보여주는
          <b className="text-primary-700"> 학습·이해 보조</b> 도구입니다. 공식 수어 통역이 아닙니다.
        </div>

        {/* 어떤 문장을 볼까요? — 입력 카드(Figma) */}
        <section className="card">
          <p className="text-[17px] font-bold text-ink">어떤 문장을 볼까요?</p>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="수어로 볼 한국어 문장을 입력하세요 (예: 학교에 갔어요)"
            rows={2}
            maxLength={200}
            className="input-field mt-4 resize-none text-[15.5px]"
          />
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => { setText(ex); setQuery(ex) }}
                className="rounded-full bg-[#f3f3f7] px-4 py-[9px] text-[13px] font-bold text-ink-muted transition hover:bg-gray-200"
              >
                {ex}
              </button>
            ))}
            <button
              onClick={() => setQuery(text.trim())}
              disabled={!text.trim()}
              className="ml-auto rounded-[14px] border-2 border-b-[5px] border-primary-700 bg-primary-500 px-5 py-2.5 text-[15px] font-bold text-white transition-all hover:bg-primary-600 active:translate-y-[2px] active:border-b-2 disabled:opacity-40"
            >
              수어로 보기
            </button>
          </div>
        </section>

        {/* 수어와 입모양 — 결과(실제 KSL 영상: SignPanel) */}
        <section className="card mt-5">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-[17px] font-bold text-ink">수어와 입모양</p>
            <span className="text-[13px] text-ink-muted">나란히 보기</span>
          </div>
          <SignPanel text={query} />
        </section>
      </div>
    </AppShell>
  )
}
