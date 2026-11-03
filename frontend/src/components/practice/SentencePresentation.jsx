import { motion } from 'framer-motion'
import WatermarkCard from '../WatermarkCard'
import EffortCheck from '../EffortCheck'
import { sentenceSkeleton } from '../../lib/consonantSkeleton'

function HintDisplay({ sentence, hintLevel, revealedTextIndex = -1 }) {
  if (!sentence) return null

  const chars = sentence.replace(/ /g, '')
  const words = sentence.split(' ')

  if (hintLevel === 0) return null

  if (hintLevel === 1) {
    // 음절 수만 표시
    return (
      <div className="mt-3 p-3 bg-warn-tint border border-warn/40 rounded-lg">
        <p className="text-xs text-warn-text font-medium mb-1">힌트 1 — 글자 수</p>
        <div className="flex flex-wrap gap-2">
          {words.map((word, wi) => (
            <div key={wi} className="flex gap-1">
              {word.split('').map((_, ci) => (
                <span key={ci} className="w-7 h-7 rounded-full bg-warn-tint flex items-center justify-center text-warn-text font-bold text-sm">
                  ●
                </span>
              ))}
            </div>
          ))}
        </div>
        <p className="text-xs text-warn-text mt-1">{chars.length}글자</p>
      </div>
    )
  }

  if (hintLevel === 2) {
    // 자음 골격: 음절마다 첫 자음만, 모음·받침은 입모양으로 읽는다
    return (
      <div className="mt-3 p-3 bg-bookmark-tint border border-bookmark-line rounded-lg">
        <p className="text-xs text-bookmark-dark font-medium mb-1">힌트 2 — 첫 자음</p>
        <div className="flex flex-wrap gap-2">
          {sentenceSkeleton(sentence).map((word, wi) => (
            <div key={wi} className="flex gap-1">
              {word.map((ch, ci) => (
                <span key={ci} className="w-7 h-7 rounded border flex items-center justify-center text-sm font-bold bg-bookmark-tint border-bookmark text-bookmark-dark">
                  {ch}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (hintLevel >= 3) {
    // 입모양 프레임의 원문 위치에 맞춰 음절별로 공개
    const sentenceChars = Array.from(sentence)

    return (
      <div className="mt-3 p-3 bg-good-tint border border-good-line rounded-lg">
        <p className="text-xs text-good-dark font-medium mb-1">힌트 3 — 발음 자막</p>
        <p className="sr-only">{sentence}</p>
        <p aria-hidden="true" className="text-lg font-bold text-good-dark tracking-wide">
          {sentenceChars.map((char, index) => (
            <motion.span
              key={`${index}-${char}`}
              className="inline-block whitespace-pre"
              initial={false}
              animate={index <= revealedTextIndex
                ? { opacity: 1, y: 0, filter: 'blur(0px)' }
                : { opacity: 0, y: 4, filter: 'blur(3px)' }}
              transition={{ duration: 0.28, ease: 'easeOut' }}
            >
              {char}
            </motion.span>
          ))}
        </p>
        <p className="text-xs text-good-text/80 mt-1.5">
          입모양 재생에 맞춰 자막이 나타납니다.
        </p>
      </div>
    )
  }

  return null
}

// 4지선다 정답 판정(94:98/94:140) — 고른 문장이 정답 문장과 같으면 정답. 주관식·서술형은 기존 화면의 '정답' 기준(80점).
const CORRECT_SCORE = 80
// 레슨 시작 전 트랙 로딩(§4-10 223:30)을 최소 이만큼은 보인다 — 첫 문장 입모양이 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`

// 레슨 완료 스탯 카드(93:22) — 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-16 border border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:py-4 max-lg:text-[16px]'

// Figma "Lesson / 4. 완료"(93:12) — 마지막 문장 뒤 레슨 컴포넌트의 마지막 상태.
function LessonComplete({ accuracy, xp, elapsedSec, onNext, onHome, effort }) {
  return (
    <div className="flex min-h-[100dvh] w-full flex-col items-center justify-center gap-[26px] bg-page px-[18px] py-12">
      <span className="relative size-[140px] shrink-0">
        <img src="/ui/lp-93-12-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
      </span>
      <h1 className="text-center text-[38px] font-bold leading-figma tracking-[-0.95px] text-ink">레슨을 마쳤어요!</h1>

      <div className="flex w-full max-w-[640px] gap-3.5 py-2">
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-percent.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>정답률</p>
          <p className={`${STAT_VALUE} text-primary-700`}>{accuracy == null ? '-' : `${accuracy}%`}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-xp.svg', size: 157.945, top: -76, right: -71.44 }}>
          <p className={STAT_LABEL}>받은 경험치</p>
          <p className={`${STAT_VALUE} text-warn-text`}>+{xp}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-clock.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>걸린 시간</p>
          <p className={`${STAT_VALUE} text-stat-level`}>{fmtDuration(elapsedSec)}</p>
        </WatermarkCard>
      </div>

      {/* 레슨별 정신적 노력 한 문항(계획 C14, 건너뛸 수 있음, 기록만) */}
      {effort && <EffortCheck {...effort} />}

      <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
        <button type="button" onClick={onNext} className={`btn-primary btn-lg ${DONE_BTN}`}>다음 레슨으로</button>
        <button type="button" onClick={onHome} className={`btn-secondary btn-lg text-track ${DONE_BTN}`}>학습 화면으로 돌아가기</button>
      </div>
    </div>
  )
}

// 하단 바 버튼 — 데스크톱 .btn-bar(40/15, 17px) 오른쪽, lg 미만 전체 폭 py16·16px(235:69 · 235:109)
const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'
// 보기 한 줄(91:29 / 모바일 235:52) — 1px 테두리. 정답·오답 공개(94:119 · 94:161 · 94:169)는 같은 색 안쪽 링을 더한다.
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
// 11/03: 고름·정답·오답은 1px 테두리 안쪽에 1px 링을 더해 2px처럼 보이게 한다(box-shadow라 보기 높이가 바뀌지 않는다).
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border border-track ring-1 ring-inset ring-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} border border-good ring-1 ring-inset ring-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} border border-good ring-1 ring-inset ring-good bg-white text-ink`,
  wrong: `${OPTION_BASE} border border-bad ring-1 ring-inset ring-bad bg-bad-tint text-bad-text`,
}

/**
 * 3단계 · 문장 (상황별) — 레슨 집중 모드(핸드오프 §3.4): AppShell 없이 전체 화면, 상단 X + 진행률 + n / 전체.
 * 문장마다 유형이 다르다(주관식 · 4지선다 · 서술형, 학습 모드는 문장 보기). 4지선다는 독화 레슨 공통 템플릿
 * (§4-03 — 91:12 · 94:98 · 94:140, 모바일 235:34 · 235:71)으로 그리고, 마지막 문장 뒤에 레슨 완료(93:12)를 띄운다.
 * 채점(submitProgress)·힌트·수어·북마크 저장 로직은 그대로다.
 */

export { HintDisplay, CORRECT_SCORE, INTRO_MS, OVERFLOW, fmtDuration, STAT_CARD, STAT_LABEL, STAT_VALUE, DONE_BTN, LessonComplete, BAR_BTN, OPTION_BASE, OPTION_CLASS }
