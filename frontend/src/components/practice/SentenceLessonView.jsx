import LessonA11yButton from '../LessonA11yButton'
import { HintDisplay, BAR_BTN, OPTION_CLASS } from '../../components/practice/SentencePresentation'
import { Progress } from '../../components/UI'
import { motion, AnimatePresence } from 'framer-motion'
import { MotionPanel } from '../../components/UI'
import MouthAvatar from '../../components/MouthAvatar'
import QuizForm from '../../components/QuizForm'
import SignPanel from '../../components/SignPanel'
import BookmarkButton from '../../components/BookmarkButton'
import SubmitRetry from '../../components/SubmitRetry'
import { ModalClose } from '../../components/Modal'
import CueBadges, { CueLegend } from '../../components/CueBadges'
import ConsonantFeedback from '../../components/ConsonantFeedback'
import SoundReplayBar from '../../components/SoundReplayBar'

export default function SentenceLessonView({ multiple, handleFinish, answered, total, currentSentenceIndex, currentScenario, questionTitle, isBookmarked, toggleBookmark, visemeError, fetchVisemes, submitFail, resendAnswer, skipFailedAnswer, shownVisemes, result, currentSentence, lesson, replay, choices, submitting, setSelectedChoice, selectedChoice, optionState, sound, effectiveMode, player, setSignOpen, handleNext, isLastSentence, handleSubtitleFrame, subtitleRestartKey, hintLevel, showNextHint, retry, revealedTextIndex, revealedAnswer, draft, setDraft, handleSubmitAnswer, handleRetry, revealAfterRetry, mcCorrect, signOpen, signRef }) {
return (
    <div className="min-h-[100dvh] bg-page">
      <div className={`mx-auto flex w-full max-w-[676px] flex-col px-[18px] pt-[18px] lg:pt-7 ${multiple ? 'lesson-content pb-[200px] lg:pb-[150px]' : 'pb-12'}`}>
        {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + n / 전체 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={handleFinish} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <Progress value={(answered / total) * 100} label="레슨 진행률" animated className="lg:h-[14px]" />
          <LessonA11yButton />
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{currentSentenceIndex + 1} / {total}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          {/* 질문 + 북마크(91:19 · 328:40 / 모바일 235:42 · 328:64) — 북마크는 기존대로 서버에 저장 */}
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">{currentScenario.situation}</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">{questionTitle}</h1>
            <BookmarkButton active={isBookmarked} onToggle={toggleBookmark}
              label={isBookmarked ? '이 문장 북마크 해제' : '이 문장 북마크하기'}
              className="absolute right-0 top-[14px] lg:top-[21px]" />
          </div>

          {/* 입모양을 받지 못했을 때: 이전 문장 입모양은 비운 채 다시 받기를 둔다(문항 상태는 그대로) */}
          {visemeError && (
            <div role="alert" className="flex items-center justify-between gap-3 rounded-14 border border-bad-line bg-bad-tint px-4 py-2.5 text-[13.5px] font-bold text-bad-text">
              입모양을 가져오지 못했어요.
              <button type="button" onClick={fetchVisemes} className="shrink-0 underline">다시 가져오기</button>
            </div>
          )}

          {submitFail && <SubmitRetry onResend={resendAnswer} onSkip={skipFailedAnswer} busy={submitting} />}

          {multiple ? (
            <>
              {/* 입모양 카드(91:22 / 모바일 235:45) — 아바타만, 무한 반복(다시 보기·속도·프레임 조작 없음) */}
              <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
                {/* 시각증강 기호(축 J-3)는 답을 확인한 뒤에만 — 문제 중에 보이면 보기끼리 다른 자질이 기호로 드러나 답이 된다.
                    그 뒤에는 약한 표적 입모양 음절에만 입꼬리 옆에 겹쳐 '왜 헷갈렸는지'를 보여 준다(숙달되면 흐려짐). */}
                <MouthAvatar frames={shownVisemes} height={null} className="h-full" cueText={result ? currentSentence : null} cueFocus
                  talker={lesson.talker} talkerSeed={lesson.seed} override={replay.frame} />
              </div>

              {/* 4지선다(91:28 / 모바일 235:51) — 선택 → 확인 */}
              <div className="flex flex-col gap-2.5 lg:gap-3">
                {choices.map((c, i) => (
                  <button key={c} type="button" disabled={!!result || submitting} onClick={() => setSelectedChoice(c)}
                    aria-pressed={!result ? selectedChoice === c : undefined} className={OPTION_CLASS[optionState(c)]}>
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                    <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{c}</span>
                  </button>
                ))}
              </div>

              {result && <SoundReplayBar sound={sound} replay={replay} />}
              {/* 결과 뒤 음절 기호(시각증강) — 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
              {result && (
                <MotionPanel
                  className="overflow-x-auto rounded-16 border border-line bg-white p-3">
                  <CueBadges text={currentSentence} showControls />
                  <div className="mt-1.5"><CueLegend /></div>
                </MotionPanel>
              )}
            </>
          ) : effectiveMode === 'study' ? (
            <>
              {player({ loop: true })}
              <div className="card flex flex-col gap-4">
                <div className="rounded-14 border border-good-line bg-good-tint p-4">
                  <p className="text-2xl font-bold leading-relaxed tracking-wide text-good-text">{currentSentence}</p>
                </div>
                <button type="button" onClick={() => setSignOpen(true)} className="btn-secondary w-full py-2.5 text-[14px] text-track">
                  이 문장 수어로 보기
                </button>
                <div className="space-y-1 rounded-lg bg-surface-muted p-3 text-sm text-ink-muted">
                  <p className="font-bold text-ink">학습 방법</p>
                  <p>1. 위 문장을 읽으면서 입모양 애니메이션을 반복해서 보세요.</p>
                  <p>2. 각 음절이 어떤 입모양인지 연결해보세요.</p>
                  <p>3. 충분히 익혔으면 다음 문장으로 넘어가세요.</p>
                </div>
                <button type="button" onClick={handleNext} className="btn-primary w-full">
                  {isLastSentence ? '학습 마치기' : '익혔어요, 다음 문장 →'}
                </button>
              </div>
            </>
          ) : (
            /* 주관식 / 서술형 */
            <>
              {player({ onFrameChange: handleSubtitleFrame, loop: !result, restartKey: subtitleRestartKey })}
              <div className="card">
                {!result && hintLevel < 3 && (
                  <button type="button" onClick={showNextHint}
                    className="mb-2 rounded-full bg-warn-tint px-3 py-1.5 text-xs font-bold text-warn-text transition-colors hover:brightness-95">
                    힌트 보기 {hintLevel > 0 ? `(${hintLevel}/3)` : ''}
                  </button>
                )}

                {retry && !result && (
                  <div className="mb-3">
                    <ConsonantFeedback feedback={retry.feedback} />
                  </div>
                )}

                <AnimatePresence>
                  {hintLevel > 0 && (
                    <motion.div key={hintLevel} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                      <HintDisplay sentence={currentSentence} hintLevel={hintLevel} revealedTextIndex={revealedTextIndex} />
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="mt-4">
                  <QuizForm
                    key={`${currentSentenceIndex}-${retry ? 'retry' : revealedAnswer != null ? 'reveal' : 'first'}`}
                    initialAnswer={revealedAnswer || draft}
                    onAnswerChange={setDraft}
                    onSubmit={handleSubmitAnswer}
                    onRetry={handleRetry}
                    loading={submitting}
                    result={result}
                    correctAnswer={currentSentence}
                    label={retry ? '단서를 보고 문장을 한 번 더 입력하세요'
                      : effectiveMode === 'essay'
                        ? '입모양을 보고 문장 전체를 서술해서 입력하세요'
                        : '입모양을 보고 문장을 입력하세요'}
                    placeholder={effectiveMode === 'essay'
                      ? '읽은 내용을 문장으로 자세히 적어보세요...'
                      : '여기에 읽은 문장을 입력하세요...'}
                  />
                </div>

                {retry && !result && (
                  <button type="button" onClick={revealAfterRetry}
                    className="mt-2 w-full rounded-14 py-2 text-[13.5px] font-bold text-ink-muted underline">
                    모르겠어요, 정답 보기
                  </button>
                )}

                {result && (
                  <MotionPanel className="mt-4">
                    <div className="mb-3"><SoundReplayBar sound={sound} replay={replay} /></div>
                    {result.streak_count > 1 && (
                      <p className="mb-2 text-center text-sm font-bold text-stat-streak">
                        {result.streak_count}일째 연속 학습 중! 경험치를 {Math.round((result.streak_multiplier - 1) * 100)}% 더 받아요
                      </p>
                    )}
                    <button type="button" onClick={handleNext} className="btn-primary w-full">
                      {isLastSentence ? '마치기' : '계속하기'}
                    </button>
                  </MotionPanel>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 4지선다 하단 고정 바 — 문제(130:17) · 정답(94:133) · 오답(94:175). lg 미만(235:68 · 235:105)은
          힌트 없이 메시지 위·전체 폭 버튼 아래로 쌓는다(§4-12). */}
      {multiple && (
        <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : mcCorrect ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
          <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
            {result ? (
              <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${mcCorrect ? 'text-good-text' : 'text-bad-text'}`}>
                <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{mcCorrect ? '정답이에요!' : '아쉬워요'}</p>
                <p className="line-clamp-2 text-[13px] font-bold opacity-80 lg:text-[14px]">정답은 「{currentSentence}」예요</p>
              </div>
            ) : (
              <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">{selectedChoice == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}</span>
            )}
            {result ? (
              <button type="button" onClick={handleNext} className={`${mcCorrect ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
            ) : (
              <button type="button" onClick={() => handleSubmitAnswer(selectedChoice)} disabled={selectedChoice == null || submitting}
                className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
            )}
          </div>
        </div>
      )}

      {/* 수어 보기 — 학습 화면을 벗어나지 않는 슬라이드오버 모달 */}
      <AnimatePresence>
        {signOpen && (
          <motion.div
            className="fixed inset-0 z-50 flex justify-end bg-overlay/50"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSignOpen(false)}
          >
            <motion.div
              ref={signRef}
              role="dialog"
              aria-modal="true"
              aria-label={`${currentSentence} 수어 번역`}
              tabIndex={-1}
              className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-modal outline-none"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="sticky top-0 z-10 flex items-center justify-between border-b-1.5 border-line bg-white px-5 py-3">
                <div>
                  <p className="text-xs text-ink-faint">이 문장을 수어로</p>
                  <p className="font-bold text-ink">{currentSentence}</p>
                </div>
                <ModalClose onClose={() => setSignOpen(false)} />
              </div>
              <div className="p-5">
                {signOpen && <SignPanel text={currentSentence} />}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
