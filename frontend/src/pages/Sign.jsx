import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { learningAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'

/**
 * 한국어 → 한국수어(KSL) 학습 보조 페이지
 * ------------------------------------------------------------------
 * 문장을 입력하면 Claude가 KSL 문법으로 gloss 번역(조사 제거·어순 재배열)하고,
 * 각 단어를 국립국어원 한국수어사전에서 조회해 실제 수어 영상(딥링크) + 수형설명을,
 * 사전에 없는 단어는 지문자(지화)로 보여준다. 각 단어의 입모양(mouthing)은
 * LIPLAB viseme 아바타로 함께 재생 — "수어 + 입모양"을 한 화면에.
 *
 * 학습·이해 보조용(베타)이며 공식 통역이 아니다.
 */
const EXAMPLES = ['학교에 갔어요', '병원이 어디예요?', '만나서 반가워요', '천천히 말해 주세요']

function CoverageBadge({ method, coverage }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className={`px-2 py-0.5 rounded-full font-medium ${method === 'llm' ? 'bg-indigo-100 text-indigo-700' : 'bg-amber-100 text-amber-700'}`}>
        {method === 'llm' ? 'AI 번역(Claude)' : '규칙 근사(오프라인)'}
      </span>
      <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700">
        수어 {coverage.matched}
      </span>
      {coverage.fingerspelled > 0 && (
        <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
          지문자 {coverage.fingerspelled}
        </span>
      )}
    </div>
  )
}

function TokenCard({ token, active, onClick }) {
  const isSign = token.type === 'sign'
  return (
    <button
      onClick={onClick}
      className={`text-left w-full rounded-xl border p-3 transition-all ${
        active ? 'border-primary-500 ring-2 ring-primary-200 bg-primary-50' : 'border-gray-200 bg-white hover:border-gray-300'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold text-gray-900">
          {token.word}
          {token.negate && <span className="ml-1 text-xs text-red-500 align-middle">(부정)</span>}
        </span>
        {isSign ? (
          <span className="text-[10px] shrink-0 px-1.5 py-0.5 rounded bg-green-100 text-green-700">수어</span>
        ) : (
          <span className="text-[10px] shrink-0 px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">지문자</span>
        )}
      </div>

      {isSign ? (
        <>
          {token.description && (
            <p className="mt-1 text-xs text-gray-500 line-clamp-2">{token.description}</p>
          )}
          {token.dict_url && (
            <a
              href={token.dict_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="mt-2 inline-block text-xs text-primary-600 hover:underline"
            >
              국립국어원 영상 ↗
            </a>
          )}
          {token.alt_count > 1 && (
            <span className="ml-2 text-[10px] text-gray-400">다른 수어 {token.alt_count - 1}개</span>
          )}
        </>
      ) : (
        <div className="mt-2 flex flex-wrap gap-1">
          {token.jamo.map((group, gi) => (
            <span key={gi} className="px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200 text-sm tracking-wide">
              {group.join('')}
            </span>
          ))}
        </div>
      )}
    </button>
  )
}

export default function Sign() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [current, setCurrent] = useState(0)
  const [playing, setPlaying] = useState(false)

  const translate = useCallback(async (value) => {
    const q = (value ?? text).trim()
    if (!q) return
    setLoading(true); setError(''); setResult(null); setPlaying(false); setCurrent(0)
    try {
      const data = await learningAPI.translateSign(q)
      setResult(data)
    } catch (e) {
      setError(e?.response?.data?.detail || '번역 중 오류가 발생했습니다. 로그인 상태를 확인해 주세요.')
    } finally {
      setLoading(false)
    }
  }, [text])

  const tokens = result?.tokens || []
  const currentToken = tokens[current] || null

  // 한 토큰의 입모양이 끝나면 다음 토큰으로 자동 진행(전체 재생)
  const handleComplete = useCallback(() => {
    setCurrent((i) => {
      if (i < tokens.length - 1) return i + 1
      setPlaying(false)
      return i
    })
  }, [tokens.length])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-primary-600">LIPLAB · 수어</h1>
          <button
            onClick={() => navigate('/dashboard')}
            className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 border border-gray-200 rounded-lg"
          >
            ← 대시보드
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* 정직성 배너 */}
        <div className="mb-4 text-xs text-gray-500 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
          <b>AI 수어 번역 (베타)</b> · 한국어를 한국수어 문법으로 옮겨 <b>학습·이해를 돕는</b> 도구입니다.
          공식 수어 통역이 아니며, 실제 수어 영상은 <b>국립국어원 한국수어사전</b>을 출처로 합니다.
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
                onClick={() => { setText(ex); translate(ex) }}
                className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200"
              >
                {ex}
              </button>
            ))}
            <button
              onClick={() => translate()}
              disabled={loading || !text.trim()}
              className="ml-auto px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 disabled:opacity-40 text-white text-sm font-medium"
            >
              {loading ? '번역 중…' : '수어로 보기'}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>
        )}

        {result && tokens.length > 0 && (
          <div className="mt-6 grid md:grid-cols-2 gap-6">
            {/* 입모양 아바타 (mouthing) */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-gray-700">입모양 (현재: {currentToken?.word})</h2>
                <button
                  onClick={() => { setCurrent(0); setPlaying(true) }}
                  className="text-xs px-3 py-1 rounded-lg bg-primary-500 text-white hover:bg-primary-600"
                >
                  ▶ 전체 재생
                </button>
              </div>
              <LipSyncPlayer3D
                visemes={currentToken?.visemes || []}
                isPlaying={playing}
                onComplete={handleComplete}
              />
            </div>

            {/* 수어 시퀀스 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-gray-700">수어 순서 (KSL)</h2>
                <CoverageBadge method={result.method} coverage={result.coverage} />
              </div>

              {result.notes && (
                <p className="mb-2 text-xs text-gray-500">💬 {result.notes}</p>
              )}
              {result.annotations?.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {result.annotations.map((a, i) => (
                    <span key={i} className="text-[11px] px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-100">
                      {a.marker}: {a.note}
                    </span>
                  ))}
                </div>
              )}

              <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                {tokens.map((t, i) => (
                  <TokenCard
                    key={i}
                    token={t}
                    active={i === current}
                    onClick={() => { setCurrent(i); setPlaying(true) }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {result && tokens.length === 0 && !loading && (
          <div className="mt-6 text-sm text-gray-500">변환할 단어가 없습니다.</div>
        )}
      </main>
    </div>
  )
}
