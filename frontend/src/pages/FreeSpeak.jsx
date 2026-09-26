import { useState } from 'react'
import { motion } from 'framer-motion'
import { learningAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import VocalTractVTL from '../components/VocalTractVTL'
import Audio2FaceAvatar from '../components/Audio2FaceAvatar'
import AppShell from '../components/AppShell'
import { VISEME_TO_VTL } from '../lib/vtlShapes'

/**
 * 자유 발화 (Figma 225:30 / 225:73): 자유 입력 → 3D 입모양 + 성도 단면
 * ------------------------------------------------------------------
 * 사용자가 아무 글자·문장이나 입력하면 백엔드 /api/viseme로 입모양 프레임을 받아
 * 3D 얼굴(LipSyncPlayer3D)이 그대로 '발음'하는 모습을 보여준다(반복 재생).
 * 인증이 필요 없는 열린 도구 — 커리큘럼 잠금과 무관하게 누구나 쓸 수 있다.
 * 9/26 Figma(변경 내역 §4-4): 입력·입모양·성도 단면을 카드 하나(445:82)에 넣고 구분선으로 나눈다. 입모양(445:88)과
 * 성도 단면(445:98)은 좌우 2단이고, '지금 발음 중'(445:95)은 두 그림 아래 가운데. 빠른 예시 칩과 소리 내는 법 목록은 빠졌다.
 * 성도 단면은 재생 중인 입모양 프레임을 따라 VocalTractLab 윤곽(E-6)을 바꾼다.
 * 음성구동 아바타(A4) 카드는 Figma에 없지만 출시된 기능이라 맨 아래에 둔다(서버에 모델·예시가 없으면 스스로 숨김).
 */
const PANE = 'h-[240px] w-full overflow-hidden rounded-14 bg-surface-muted'

export default function FreeSpeak() {
  const [text, setText] = useState('')
  const [visemes, setVisemes] = useState([])
  const [playedText, setPlayedText] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [visemeId, setVisemeId] = useState(15)   // 성도 단면이 따라가는 현재 입모양(15 = 쉼)

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
        setVisemeId(15)   // 입모양 칸이 자리 그림으로 돌아가니 성도 단면도 쉼으로
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
    if (!loading) speak()
  }

  return (
    <AppShell active="practice" title="자유 발화" closeTo="/practice/hub">
      {/* Card / 자유 발화 (445:82): 입력 · 구분선 · 입모양|성도 단면 · 구분선 · 지금 발음 중 */}
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="flex w-full flex-col gap-[18px] rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]">
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
        {error && <p role="alert" className="-mt-2 text-sm text-bad">{error}</p>}

        <div className="h-[1.5px] w-full shrink-0 bg-line" />

        {/* Row / 입모양 · 성도 (445:87): 좌우 2단(좁은 화면은 위아래) */}
        <div className="flex w-full flex-col gap-4 sm:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            <p className="text-[14.5px] font-bold leading-figma text-ink">입모양</p>
            <div className={PANE}>
              {visemes.length > 0 ? (
                <LipSyncPlayer3D
                  visemes={visemes}
                  isPlaying={isPlaying}
                  onComplete={() => setIsPlaying(false)}
                  onFrameChange={({ frame }) => setVisemeId(frame?.viseme ?? 15)}
                  loop
                  cueText={playedText}
                  showControls={false}
                  stageHeight={240}
                />
              ) : (
                /* 입력 전 자리 그림(445:92, 입 150×80 + 안쪽 102×40) */
                <div aria-hidden className="relative h-full w-full">
                  <img src="/ui/lp-445-93-mouth.svg" alt="" className="absolute left-1/2 top-16 h-20 w-[150px] -translate-x-1/2" />
                  <img src="/ui/lp-445-94-mouth-inner.svg" alt="" className="absolute left-1/2 top-[84px] h-10 w-[102px] -translate-x-1/2" />
                </div>
              )}
            </div>
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            <p className="text-[14.5px] font-bold leading-figma text-ink">성도 단면</p>
            <div className={`${PANE} grid place-items-center p-3`}>
              <VocalTractVTL phoneme={VISEME_TO_VTL[visemeId] || 'rest'} labels={false}
                className="flex h-full w-full justify-center [&_svg]:h-full [&_svg]:w-auto" />
            </div>
          </div>
        </div>

        <div className="h-[1.5px] w-full shrink-0 bg-line" />

        {/* Now playing (445:95): 두 그림 아래 가운데 */}
        <div role="status" className="flex min-h-[42px] flex-col items-center justify-center gap-1 leading-figma">
          {playedText ? (
            <>
              <p className="text-[11.5px] text-primary-500">지금 발음 중</p>
              <p className="text-center text-[20px] font-bold tracking-[1.2px] text-primary-700">{playedText}</p>
            </>
          ) : null}
        </div>
      </motion.section>

      {/* 음성구동 아바타(A4) — 서버에 모델이 있을 때만 표시(없으면 컴포넌트가 스스로 숨김) */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full">
        <Audio2FaceAvatar />
      </motion.div>
    </AppShell>
  )
}
