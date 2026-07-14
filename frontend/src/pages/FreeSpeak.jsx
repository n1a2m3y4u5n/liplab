import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { learningAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'

/**
 * 내 문장 발음 보기 (자유 입력 → 3D 입모양)
 * ------------------------------------------------------------------
 * 사용자가 아무 글자·문장이나 입력하면 백엔드 /api/viseme로 입모양 프레임을 받아
 * 3D 얼굴(LipSyncPlayer3D)이 그대로 '발음'하는 모습을 보여준다.
 * 인증이 필요 없는 열린 도구 — 커리큘럼 잠금과 무관하게 누구나 쓸 수 있다.
 */
const EXAMPLES = ['안녕하세요', '감사합니다', '반갑습니다', '맛있어요', '괜찮아요', '사랑해요']

export default function FreeSpeak() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [visemes, setVisemes] = useState([])
  const [playedText, setPlayedText] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [loop, setLoop] = useState(true)

  const speak = async (raw) => {
    const value = (raw ?? text).trim()
    if (!value) {
      setError('발음할 글자나 문장을 입력해주세요.')
      return
    }
    setError('')
    setLoading(true)
    setIsPlaying(false)
    try {
      const data = await learningAPI.getVisemes(value)
      if (!data || data.length === 0) {
        setVisemes([])
        setPlayedText('')
        setError('입모양으로 바꿀 한글이 없어요. 한글을 입력해주세요. (예: 안녕하세요)')
        return
      }
      setVisemes(data)
      setPlayedText(value)
      setIsPlaying(true)
    } catch (e) {
      console.error('Failed to load visemes:', e)
      setError('입모양 생성에 실패했어요. 잠시 후 다시 시도해주세요.')
    } finally {
      setLoading(false)
    }
  }

  const onSubmit = (e) => {
    e.preventDefault()
    speak()
  }

  const useExample = (ex) => {
    setText(ex)
    speak(ex)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">내 문장 발음 보기</h1>
            <p className="text-sm text-gray-600">아무 글자나 문장을 입력하면 3D 얼굴이 그대로 발음해요.</p>
          </div>
          <button
            onClick={() => navigate('/pillar/reading')}
            className="shrink-0 text-gray-500 hover:text-gray-800 text-sm"
          >
            ✕ 나가기
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 입력 */}
        <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="card">
          <h3 className="text-lg font-semibold mb-4 text-gray-900">무엇을 발음해 볼까요?</h3>

          <form onSubmit={onSubmit}>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  speak()
                }
              }}
              rows={3}
              maxLength={100}
              placeholder="예: 안녕하세요, 오늘 날씨 좋네요"
              className="input-field resize-none text-lg"
            />
            <div className="mt-1 text-right text-xs text-gray-400">{text.length}/100</div>
            <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
              {loading ? '입모양 생성 중…' : '👄 발음 보기'}
            </button>
          </form>

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

          {/* 빠른 예시 */}
          <div className="mt-5">
            <p className="text-xs font-medium text-gray-500 mb-2">빠른 예시</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => useExample(ex)}
                  disabled={loading}
                  className="px-3 py-1.5 rounded-full border border-gray-200 text-sm text-gray-700 hover:border-primary-400 hover:bg-primary-50 transition-colors disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* 반복 재생 토글 */}
          <label className="mt-5 flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={loop}
              onChange={(e) => setLoop(e.target.checked)}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            반복 재생 (완료 후 자동으로 다시)
          </label>

          <div className="mt-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-500 space-y-1">
            <p className="font-medium text-gray-700">tip</p>
            <p>· 한 글자(예: 마)만 입력해도 돼요.</p>
            <p>· 재생 속도를 0.5x로 낮추면 입·혀 움직임이 잘 보여요.</p>
            <p>· 아바타를 마우스로 살짝 돌려 옆모습도 볼 수 있어요.</p>
          </div>
        </motion.div>

        {/* 재생 */}
        <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="card">
          <h3 className="text-lg font-semibold mb-4 text-gray-900">입모양 애니메이션</h3>
          <LipSyncPlayer3D
            visemes={visemes}
            isPlaying={isPlaying}
            onComplete={() => setIsPlaying(false)}
            loop={loop}
          />
          {playedText && (
            <div className="mt-4 p-3 bg-primary-50 border border-primary-100 rounded-xl text-center">
              <p className="text-xs text-primary-500 mb-0.5">지금 발음 중</p>
              <p className="text-xl font-bold text-primary-900 tracking-wide">{playedText}</p>
            </div>
          )}
        </motion.div>
      </main>
    </div>
  )
}
