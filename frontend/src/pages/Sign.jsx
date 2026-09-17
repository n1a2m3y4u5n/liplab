import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SignPanel from '../components/SignPanel'
import LearnHeader from '../components/LearnHeader'

/**
 * 한국어 → 한국수어(KSL) 학습 보조 페이지
 * 문장을 입력하면 Claude가 KSL 문법으로 번역하고, 각 단어의 **실제 국립국어원 수어
 * 영상을 화면 안에서 재생**한다(사전에 없는 단어는 지문자). 학습·이해 보조용(베타).
 */
const EXAMPLES = ['학교에 갔어요', '병원이 어디예요?', '만나서 반가워요', '천천히 말해 주세요']

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
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="etc"
        title="수어 학습"
        description="문장을 입력하면 한국수어(KSL) 영상으로 함께 확인해요"
        onExit={() => navigate('/dashboard')}
      />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-4 text-xs text-gray-500 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
          <b>AI 수어 번역 (베타)</b> · 한국어를 한국수어 문법으로 옮겨 실제 수어 영상으로 보여주는
          <b> 학습·이해 보조</b> 도구입니다. 공식 수어 통역이 아닙니다.
        </div>

        {/* 입력 */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="수어로 볼 한국어 문장을 입력하세요 (예: 학교에 갔어요)"
            rows={2}
            maxLength={200}
            className="w-full resize-none rounded-lg border border-gray-200 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => { setText(ex); setQuery(ex) }}
                className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200"
              >
                {ex}
              </button>
            ))}
            <button
              onClick={() => setQuery(text.trim())}
              disabled={!text.trim()}
              className="ml-auto px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 disabled:opacity-40 text-white text-sm font-medium"
            >
              수어로 보기
            </button>
          </div>
        </div>

        {/* 결과 (실제 수어 영상 메인) */}
        <div className="mt-6">
          <SignPanel text={query} />
        </div>
      </main>
    </div>
  )
}
