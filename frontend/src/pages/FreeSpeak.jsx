import { useState } from 'react'
import { motion } from 'framer-motion'
import { learningAPI, articulationAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import Audio2FaceAvatar from '../components/Audio2FaceAvatar'
import AppShell from '../components/AppShell'

/**
 * 자유 발화 (Figma 225:30 / 225:73) — 자유 입력 → 3D 입모양
 * ------------------------------------------------------------------
 * 사용자가 아무 글자·문장이나 입력하면 백엔드 /api/viseme로 입모양 프레임을 받아
 * 3D 얼굴(LipSyncPlayer3D)이 그대로 '발음'하는 모습을 보여준다(반복 재생).
 * 인증이 필요 없는 열린 도구 — 커리큘럼 잠금과 무관하게 누구나 쓸 수 있다.
 * Figma대로 한 줄 입력(Enter로 보기) + 빠른 예시 칩, 입모양 카드, 소리 내는 법 카드를 한 열로 쌓는다.
 * 음성구동 아바타(A4) 카드는 Figma에 없지만 출시된 기능이라 맨 아래에 둔다(서버에 모델·예시가 없으면 스스로 숨김).
 */
const EXAMPLES = ['안녕하세요', '오늘 날씨 좋네요', '커피 한 잔 주세요', '고맙습니다']

// 카드 틀(225:140) — 2px 테두리, r18, p22, 머리-본문 16
const CARD = 'flex w-full flex-col gap-4 rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]'

export default function FreeSpeak() {
  const [text, setText] = useState('')
  const [visemes, setVisemes] = useState([])
  const [playedText, setPlayedText] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
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
    if (!loading) speak()
  }

  const useExample = (ex) => {
    setText(ex)
    speak(ex)
  }

  return (
    <AppShell active="practice" title="자유 발화" description="내가 쓴 문장을 소리 내어 확인해요">
      {/* 무엇을 발음해 볼까요? (225:140) */}
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className={CARD}>
        <p className="text-[17px] font-bold leading-figma text-ink">무엇을 발음해 볼까요?</p>
        <form onSubmit={onSubmit}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={100}
            enterKeyHint="go"
            aria-busy={loading}
            aria-label="발음해 볼 글자나 문장"
            placeholder="예: 안녕하세요, 오늘 날씨 좋네요"
            className="h-[58px] w-full rounded-14 border-2 border-line bg-white px-4 text-[16px] text-ink placeholder:text-placeholder focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200"
          />
        </form>
        {error && <p role="alert" className="-mt-1 text-sm text-bad">{error}</p>}
        <p className="text-[13px] font-bold leading-figma text-ink-muted">빠른 예시</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => useExample(ex)}
              disabled={loading}
              className="rounded-full bg-surface-sunken px-4 py-[9px] text-[13.5px] font-bold leading-figma text-ink-muted transition hover:bg-surface-hover disabled:opacity-50"
            >
              {ex}
            </button>
          ))}
        </div>
      </motion.section>

      {/* 입모양 애니메이션 (225:155) — 무대(225:159) 안에 아바타와 '지금 발음 중'(225:162) */}
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className={CARD}>
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">입모양 애니메이션</p>
          <span className="text-[13px] text-ink-muted">3D 아바타</span>
        </div>
        <div className="flex flex-col gap-4 rounded-16 bg-surface-muted p-3">
          <LipSyncPlayer3D
            visemes={visemes}
            isPlaying={isPlaying}
            onComplete={() => setIsPlaying(false)}
            loop
            cueText={playedText}
          />
          {playedText && (
            <div role="status" className="flex flex-col items-center gap-1 pb-2 leading-figma">
              <p className="text-[12px] text-primary-500">지금 발음 중</p>
              <p className="text-center text-[22px] font-bold tracking-[1.32px] text-primary-700">{playedText}</p>
            </div>
          )}
        </div>
      </motion.section>

      {/* 축 E: 소리 내는 법 (225:165) — 밖에서 안 보이는 혀·조음(자모 타일: 자모 + 안내 한 줄) */}
      {guide && guide.syllables?.length > 0 && (
        <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className={CARD}>
          <div className="flex items-center justify-between font-bold leading-figma">
            <p className="text-[17px] text-ink">소리 내는 법</p>
            <span className="text-[13px] text-ink-muted">밖에서 안 보이는 혀·조음</span>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {guide.syllables.flatMap((s, si) =>
              s.jamo.map((j, ji) => (
                <div key={`${si}-${ji}`} className="flex min-w-[120px] flex-1 flex-col items-center gap-2 rounded-14 bg-primary-100 px-2.5 py-3.5 text-center text-primary-700">
                  <div className="text-[24px] font-bold leading-figma">{j.jamo}</div>
                  <p className="text-[12px] leading-[1.5] opacity-80">{j.guide}</p>
                </div>
              ))
            )}
          </div>
        </motion.section>
      )}

      {/* 음성구동 아바타(A4) — 서버에 모델이 있을 때만 표시(없으면 컴포넌트가 스스로 숨김) */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full">
        <Audio2FaceAvatar />
      </motion.div>
    </AppShell>
  )
}
