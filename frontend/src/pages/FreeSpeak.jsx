import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { learningAPI, articulationAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import Audio2FaceAvatar from '../components/Audio2FaceAvatar'
import AppShell from '../components/AppShell'

/**
 * 내 문장 발음 보기 (자유 입력 → 3D 입모양)
 * ------------------------------------------------------------------
 * 사용자가 아무 글자·문장이나 입력하면 백엔드 /api/viseme로 입모양 프레임을 받아
 * 3D 얼굴(LipSyncPlayer3D)이 그대로 '발음'하는 모습을 보여준다.
 * 인증이 필요 없는 열린 도구 — 커리큘럼 잠금과 무관하게 누구나 쓸 수 있다.
 */
const EXAMPLES = ['안녕하세요', '오늘 날씨 좋네요', '커피 한 잔 주세요', '고맙습니다']

export default function FreeSpeak() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [visemes, setVisemes] = useState([])
  const [playedText, setPlayedText] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [loop, setLoop] = useState(true)
  const [guide, setGuide] = useState(null)  // 축 E: 음소별 '보이지 않는 조음' 가이드

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
      // 축 E: 음소별 '보이지 않는 조음'(혀·조음 위치) 가이드도 함께 — 실패해도 립싱크는 진행
      articulationAPI.guide(value).then(setGuide).catch(() => setGuide(null))
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
    <AppShell active="practice" title="자유 발화" description="내가 쓴 문장을 소리 내어 확인해요">
      <div className="grid w-full grid-cols-1 gap-5 lg:grid-cols-2">
        {/* 입력 — 무엇을 발음해 볼까요? */}
        <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="card">
          <p className="mb-4 text-[17px] font-bold text-ink">무엇을 발음해 볼까요?</p>

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
              className="input-field resize-none text-[16px]"
            />
            <div className="mt-1 text-right text-xs text-gray-400">{text.length}/100</div>
            <button type="submit" disabled={loading} className="btn-primary mt-2 w-full">
              {loading ? '입모양 생성 중…' : '👄 발음 보기'}
            </button>
          </form>

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

          {/* 빠른 예시 — Figma 필드 칩 */}
          <div className="mt-5">
            <p className="mb-2 text-[13px] font-bold text-ink-muted">빠른 예시</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => useExample(ex)}
                  disabled={loading}
                  className="rounded-full bg-[#f3f3f7] px-4 py-[9px] text-[13.5px] font-bold text-ink-muted transition hover:bg-gray-200 disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* 반복 재생 토글 */}
          <label className="mt-5 flex cursor-pointer select-none items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={loop}
              onChange={(e) => setLoop(e.target.checked)}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            반복 재생 (완료 후 자동으로 다시)
          </label>

          <div className="mt-4 space-y-1 rounded-[14px] bg-gray-50 p-3 text-xs text-gray-500">
            <p className="font-medium text-gray-700">tip</p>
            <p>· 한 글자(예: 마)만 입력해도 돼요.</p>
            <p>· 재생 속도를 0.5x로 낮추면 입·혀 움직임이 잘 보여요.</p>
            <p>· 아바타를 마우스로 살짝 돌려 옆모습도 볼 수 있어요.</p>
          </div>
        </motion.div>

        {/* 재생 — 입모양 애니메이션 */}
        <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="card">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-[17px] font-bold text-ink">입모양 애니메이션</p>
            <span className="text-[13px] text-ink-muted">3D 아바타</span>
          </div>
          <div className="rounded-[16px] bg-[#fafafc] p-3">
            <LipSyncPlayer3D
              visemes={visemes}
              isPlaying={isPlaying}
              onComplete={() => setIsPlaying(false)}
              loop={loop}
              cueText={playedText}
            />
          </div>
          {playedText && (
            <div className="mt-4 rounded-[14px] border border-primary-100 bg-primary-50 py-3 text-center">
              <p className="mb-0.5 text-xs text-primary-500">지금 발음 중</p>
              <p className="text-[22px] font-bold tracking-[1.32px] text-primary-700">{playedText}</p>
            </div>
          )}
        </motion.div>

        {/* 축 E: 소리 내는 법 — 밖에서 안 보이는 혀·조음(Figma 자모 타일) */}
        {guide && guide.syllables?.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="card lg:col-span-2">
            <div className="mb-1 flex items-center justify-between">
              <p className="text-[17px] font-bold text-ink">소리 내는 법</p>
              <span className="text-[13px] text-ink-muted">밖에서 안 보이는 혀·조음</span>
            </div>
            <p className="mb-3 text-xs text-gray-500">독화·웹캠은 입모양만 보여줘요. 소리를 가르는 혀 위치·조음 방식은 입 안에 있어 보이지 않으니, 음절마다 함께 익혀요.</p>
            <div className="flex flex-wrap gap-2.5">
              {guide.syllables.flatMap((s, si) =>
                s.jamo.map((j, ji) => (
                  <div key={`${si}-${ji}`} className="flex min-w-[120px] flex-1 flex-col items-center gap-2 rounded-[14px] bg-primary-100 px-2.5 py-3.5 text-center">
                    <div className="text-[24px] font-bold text-primary-700">{j.jamo}</div>
                    <p className="text-[12px] leading-[1.5] text-primary-700/80">{j.guide}</p>
                    <div className="flex flex-wrap items-center justify-center gap-1">
                      <span className="rounded bg-white/70 px-1 text-[10px] text-primary-600">{j.place}</span>
                      {j.nasal && <span className="rounded bg-indigo-100 px-1 text-[10px] text-indigo-600">비음</span>}
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}

        {/* 음성구동 아바타(A4) — 서버에 모델이 있을 때만 표시(없으면 컴포넌트가 스스로 숨김) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="lg:col-span-2"
        >
          <Audio2FaceAvatar />
        </motion.div>
      </div>
    </AppShell>
  )
}
