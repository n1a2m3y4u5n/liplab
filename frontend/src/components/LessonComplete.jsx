import WatermarkCard from './WatermarkCard'

/**
 * 레슨 완료(Figma "Lesson / 4. 완료" 93:12) — DOKA + 워터마크 스탯 3칸(정답률·획득 XP·걸린 시간) + 버튼 2개.
 * 문맥 추론 레슨에서 쓴다. (단어·입모양·문장 레슨에는 같은 모양의 사본이 각 페이지에 있다.)
 * 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
 */
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-18 border-2 border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
// 완료 버튼 — 데스크톱 75:23(btn-lg), lg 미만은 모바일 버튼 규격(r14·b5, py16, 16px)
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'
const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`

export default function LessonComplete({ accuracy, xp, elapsedSec, onNext, onHome, homeLabel = '커리큘럼으로 돌아가기' }) {
  return (
    <div className="flex min-h-[100dvh] w-full flex-col items-center justify-center gap-[26px] bg-page px-[18px] py-12">
      <span className="relative size-[140px] shrink-0">
        <img src="/ui/lp-93-12-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
      </span>
      <h1 className="text-center text-[38px] font-bold leading-figma tracking-[-0.95px] text-ink">레슨 완료!</h1>

      <div className="flex w-full max-w-[640px] gap-3.5 py-2">
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-percent.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>정답률</p>
          <p className={`${STAT_VALUE} text-primary-700`}>{accuracy == null ? '-' : `${accuracy}%`}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-xp.svg', size: 157.945, top: -76, right: -71.44 }}>
          <p className={STAT_LABEL}>획득 XP</p>
          <p className={`${STAT_VALUE} text-warn-text`}>+{xp}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-clock.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>걸린 시간</p>
          <p className={`${STAT_VALUE} text-stat-level`}>{fmtDuration(elapsedSec)}</p>
        </WatermarkCard>
      </div>

      <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
        <button type="button" onClick={onNext} className={`btn-primary btn-lg ${DONE_BTN}`}>다음 레슨으로</button>
        <button type="button" onClick={onHome} className={`btn-secondary btn-lg text-track ${DONE_BTN}`}>{homeLabel}</button>
      </div>
    </div>
  )
}
