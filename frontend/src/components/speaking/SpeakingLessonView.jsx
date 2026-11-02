import { Progress } from '../UI'
import { Suspense } from 'react'
import { MotionPanel } from '../UI'
import MouthAvatar from '../MouthAvatar'
import BookmarkButton from '../BookmarkButton'
import Modal from '../Modal'
import { scoreTone } from '../../lib/scoreTone'
import { VOWEL_IDS } from '../../lib/vtlShapes'
import { toneDirection, toneMissed } from '../../lib/speakTone'
import { SOFT_BAND, loudnessRms, volumeCurveNote } from '../../lib/speakFeedback'
import { phoneTone, phoneValue } from '../../lib/phoneChips'
import { VocalTractVTL, IC, OVERFLOW, RESULT_BTN } from './speakingSupport'
export default function SpeakingLessonView({ exit, barPct, total, cur, exitError, err, setRetry, teardown, navigate, reviewEmpty, category, heading, saved, toggleSaved, target, summary, frames, metricMode, toggleMirror, mirrorOn, mirrorBusy, attachVideo, recording, canvasRef, volLabel, vol, pitch, progress, probeLine, scoreNum, assessing, scoreLabel, phones, chipView, setShowDetail, barTone, good, hold, fbTitle, fbSub, nextItem, resetAttempt, reviewMode, stageNo, start, starting, stop, showDetail, closeDetail, assessment, fusion, mouthRes, fusionAudio, vowelFb, rateCue, mode, drill, loadCoaching, attemptRef }) {
return (
    <div data-track="speak" className="flex min-h-[100dvh] flex-col bg-page">
      {/* 진행 헤더(175:22 / 모바일 236:35) — X + 트랙(분홍) 진행바 + n / 전체 */}
      <div className="mx-auto w-full max-w-[676px] px-[18px] pt-[18px] lg:pt-7 lg:[@media(max-height:860px)]:pt-5">
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={exit} aria-label="나가기" className="shrink-0">
            <img src={IC.close} alt="" className="size-8 lg:size-9" />
          </button>
          <Progress value={barPct} label="레슨 진행률" animated className="lg:h-[14px]" />
          {total && <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{cur} / {total}</span>}
        </div>
      </div>

      <main className="mx-auto w-full max-w-[676px] flex-1 px-[18px] pb-8 pt-6 lg:pt-5 lg:[@media(max-height:860px)]:pb-4 lg:[@media(max-height:860px)]:pt-3.5">
          {exitError ? (
            <div className="flex flex-col items-center gap-2 rounded-22 border-2 border-line bg-white px-6 py-16 text-center">
              <p className="text-lg font-bold text-ink">단계를 가져오지 못했어요</p>
              <p className="mb-3 text-sm text-ink-faint">{err} 네트워크를 확인하고 다시 시도해 주세요.</p>
              <div className="flex justify-center gap-2">
                <button type="button" onClick={() => setRetry((n) => n + 1)} className="btn-primary px-6 py-2.5 text-sm">다시 가져오기</button>
                <button type="button" onClick={() => { teardown(); navigate('/learn/path?track=speak') }} className="btn-secondary px-6 py-2.5 text-sm">발화 학습 화면으로</button>
              </div>
            </div>
          ) : reviewEmpty ? (
            <div className="flex flex-col items-center gap-2 rounded-22 border-2 border-line bg-white px-6 py-16 text-center">
              <p className="text-lg font-bold text-ink">복습할 발음이 없어요</p>
              <p className="mb-3 text-sm text-ink-faint">최근 발음이 다 좋았어요. 단계 연습을 이어가 볼까요?</p>
              <button type="button" onClick={() => { teardown(); navigate('/review/speaking') }} className="btn-primary px-6 py-2.5 text-sm">목록으로</button>
            </div>
          ) : (
          <div className="flex flex-col gap-4 lg:gap-5 lg:[@media(max-height:860px)]:gap-3.5">
            {/* 질문 + 북마크(175:28 · 328:49 / 모바일 236:71 · 328:70) — 북마크는 트랙과 무관한 브랜드색 */}
            <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
              <p className="text-[12px] font-bold text-track lg:text-[13px]">{category}</p>
              <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[28px] lg:tracking-[-0.7px]">{heading}</h1>
              <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-5" />
            </div>

            {/* 말할 단어(175:31 / 모바일 236:74) — 가운데 정렬 분홍 카드. 들어보기 버튼 없음(§3.4 청각장애 대상) */}
            <div className="flex items-center justify-center rounded-16 bg-track-tint py-[18px] pl-[22px] pr-4 lg:rounded-18 lg:py-5 lg:pl-7 lg:pr-5">
              <p className="text-center text-[32px] font-bold leading-figma tracking-[-0.64px] text-track-dark lg:text-[38px] lg:tracking-[-0.76px]">{target || '…'}</p>
            </div>

            {err && !exitError && (
              <div className="rounded-14 border border-bad-line bg-bad-tint p-3 text-sm text-bad-text">{err}</div>
            )}

            {!summary ? (
              <>
                {/* 입모양(175:36 560×300 / 모바일 236:79 전체 폭×200): 3D 아바타 + 안내.
                    세로 860px 이하 데스크톱은 위 여백·간격을 줄여 웹캠 버튼까지 하단 바 위에 보이게 한다. */}
                <div className="mx-auto w-full max-w-[560px] overflow-hidden rounded-18 border-2 border-line bg-white lg:rounded-22">
                  <div className="px-4 pt-4 lg:pt-6 lg:[@media(max-height:860px)]:pt-4">
                    <MouthAvatar loadingHint frames={frames} height={null} className="h-[134px] lg:h-[209px]" />
                  </div>
                  <p className="pb-5 pt-2.5 text-center text-[13px] font-bold leading-figma text-ink-faint lg:pb-[34px] lg:pt-3 lg:text-[14px] lg:[@media(max-height:860px)]:pb-4">
                    {metricMode ? '아래 그래프로 목소리 크기·억양을 확인해요' : '입모양을 따라 해보세요'}
                  </p>
                </div>

                {/* 웹캠 미러 — 내 입모양을 거울처럼 띄워 목표 아바타와 비교(따라 말하기). Figma 175:21에는 없지만
                    분석의 입모양 점수(소리와 따로 보임)의 입력이 여기서만 나와 남긴다. */}
                <div className="mx-auto w-full max-w-[560px]">
                  <button type="button" onClick={toggleMirror} aria-pressed={mirrorOn} disabled={mirrorBusy}
                    className={`btn-secondary w-full py-2.5 text-[14px] ${mirrorOn ? 'bg-track-tint text-track-dark' : ''}`}>
                    {mirrorOn ? '웹캠 끄기' : '웹캠으로 내 입모양 보기'}
                  </button>
                  {mirrorOn && (
                    <div className="mt-2 overflow-hidden rounded-14 bg-surface-inverse">
                      <video ref={attachVideo} autoPlay muted playsInline
                        className="w-full" style={{ transform: 'scaleX(-1)', maxHeight: 220, objectFit: 'cover' }} />
                      <p className="py-1 text-center text-[11px] text-white/70">거울처럼 좌우 반전 · 위 아바타 입모양과 내 입을 나란히 비교해보세요</p>
                    </div>
                  )}
                </div>

                {/* 실시간 파형·볼륨·피치(녹음 중) — 귀 대신 눈. 사용법 가이드 '발화 레슨'의 실시간 피드백 */}
                {recording && (
                  <div className="mx-auto w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:rounded-22">
                    <canvas ref={canvasRef} width={480} height={120}
                      className="w-full rounded-14 border border-fill bg-surface-muted" style={{ height: 120 }} />
                    <div className="mt-4">
                      <div className="mb-1 flex justify-between text-xs text-ink-muted"><span>볼륨</span><span>{volLabel}</span></div>
                      <div className="h-3 overflow-hidden rounded-full bg-fill">
                        <div className={`h-full rounded-full transition-[width] duration-75 ${vol < 0.15 ? 'bg-fill-strong' : vol > 0.95 ? 'bg-warn' : 'bg-track'}`}
                          style={{ width: `${Math.round(vol * 100)}%` }} />
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-sm">
                      <span className="text-ink-muted">톤 (피치)</span>
                      <span className="font-bold text-track-dark">{pitch ? `${pitch} Hz` : '…'}</span>
                    </div>
                  </div>
                )}

                {/* 이 단계 숙달 진행 — 레슨 안에서 해금을 알려 주는 유일한 자리라 남긴다(사용자 결정 대기) */}
                {progress && (
                  <div className="mx-auto w-full max-w-[560px]">
                    <div className="mb-1 flex justify-between text-xs text-ink-muted">
                      <span>이 단계 숙달</span><span>{progress.mastery_score}% · {progress.attempts}회</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-fill">
                      <div className="h-full bg-track transition-[width]" style={{ width: `${Math.min(progress.mastery_score, 100)}%` }} />
                    </div>
                    {progress.mastered && <p className="mt-1 text-xs font-bold text-good-text">이 단계를 숙달했어요! 다음 단계가 열렸어요.</p>}
                    {probeLine && <p className="mt-1 text-xs text-ink-muted">{probeLine}</p>}
                  </div>
                )}
              </>
            ) : (
              /* 발음 결과(176:36 560×320 / 모바일 237:50) — 점수 + 음소 칩(§3.2) + 자세히 보기 */
              <MotionPanel
                className="mx-auto flex w-full max-w-[560px] flex-col items-center gap-3.5 rounded-18 border-2 border-line bg-white px-4 py-[18px] lg:gap-0 lg:rounded-22 lg:px-6 lg:py-[30px]">
                <div className="flex flex-col items-center gap-0.5 font-bold leading-figma lg:gap-1">
                  <p className={`text-[44px] tracking-[-1.32px] lg:text-[52px] lg:tracking-[-1.56px] ${scoreTone(scoreNum, 'phone').text}`}>
                    {assessing && scoreNum == null ? '…' : scoreNum != null ? `${scoreNum}%` : '-'}
                  </p>
                  <p className="text-[13px] text-ink-faint lg:text-[14px]">{scoreLabel}</p>
                </div>

                {phones.length > 0 && (
                  <div className="flex flex-wrap justify-center gap-2 lg:mt-[33px] lg:gap-2.5">
                    {phones.map((p, i) => {
                      const v = phoneValue(p)
                      const ref = p.reliable === false
                      return (
                        <div key={i} title={ref ? `점수 ${v} · 참고` : `점수 ${v} · 확실한 정도 ${Math.round((p.confidence ?? 0) * 100)}`}
                          className={`flex size-12 items-center justify-center rounded-13 lg:size-[52px] lg:rounded-14 ${ref ? 'border-1.5' : 'border-2'} ${phoneTone(p).chip}`}>
                          <span className="text-[20px] font-bold leading-figma lg:text-[22px]">{p.label || '·'}</span>
                        </div>
                      )
                    })}
                  </div>
                )}
                {/* 신뢰도 표가 없으면 전체 참고(S14 카파 0.39), 있으면 믿을 만한 소리만 확정(docs/phoneme-feedback-reliability-2026-10.md) */}
                {chipView.note && (
                  <p className="text-center text-[11.5px] leading-relaxed text-ink-faint lg:mt-3">{chipView.note}</p>
                )}

                {assessing && !metricMode && (
                  <div className="flex items-center gap-2 text-sm text-track-dark lg:mt-6">
                    <span className="spinner size-4 rounded-full border-2 border-speak/40 border-t-speak-dark" />
                    발음을 분석하는 중…
                  </div>
                )}

                {/* 자세히 보기(179:21 / 모바일 237:74) — 쉐브론 없음 */}
                <button type="button" onClick={() => setShowDetail(true)}
                  className="btn-secondary rounded-[12px] border-b-4 px-[26px] py-3 text-[14px] lg:mt-[30px] lg:rounded-14 lg:border-b-5 lg:px-[30px] lg:py-[15px] lg:text-[16px]">
                  자세히 보기
                </button>
              </MotionPanel>
            )}
          </div>
          )}
      </main>

      {/* 하단 바 — 말하기 전/녹음 중: 마이크 바(175:40 / 236:83) · 결과: 피드백 바(176:66 · 186:55 / 237:76) */}
      {!exitError && !reviewEmpty && (
        summary ? (
          <div className={`sticky bottom-0 w-full border-t-2 ${barTone}`}>
            <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
              <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] font-bold leading-figma lg:gap-1 ${good == null ? 'text-ink-muted' : hold ? 'text-warn-text' : good ? 'text-good-text' : 'text-bad-text'}`}>
                <p className="text-[19px] tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{assessing && !metricMode ? '분석 중…' : fbTitle}</p>
                <p className="text-[13px] opacity-80 lg:truncate lg:text-[14px]">{assessing && !metricMode ? '발음을 분석하고 있어요' : fbSub}</p>
              </div>
              {/* 버튼: 통과 = 다시 말하기 / 계속하기, 아쉬움 = 넘어가기 / 다시 말하기(§4-04). lg 미만은 반반 폭. */}
              <div className="flex w-full gap-2.5 lg:w-auto lg:shrink-0">
                {hold ? (
                  <>
                    <button type="button" onClick={nextItem} className={`btn-secondary ${RESULT_BTN}`}>{good ? '계속하기' : '넘어가기'}</button>
                    <button type="button" onClick={resetAttempt} className={`btn-primary ${RESULT_BTN}`}>한 번 더 말하기</button>
                  </>
                ) : good ? (
                  <>
                    <button type="button" onClick={resetAttempt} className={`btn-secondary border-good-line text-good-text ${RESULT_BTN}`}>다시 말하기</button>
                    <button type="button" onClick={nextItem} className={`btn-good ${RESULT_BTN}`}>{reviewMode || stageNo != null ? '계속하기' : '다음 단어'}</button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={nextItem} className={`btn-secondary border-bad-line text-bad-text ${RESULT_BTN}`}>넘어가기</button>
                    <button type="button" onClick={resetAttempt} className={`btn-bad ${RESULT_BTN}`}>다시 말하기</button>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="sticky bottom-0 w-full border-t-2 border-line bg-white">
            <div className="mx-auto flex max-w-[676px] flex-col items-center gap-2.5 px-[18px] pb-[calc(26px+env(safe-area-inset-bottom))] pt-[18px] lg:h-[148px] lg:justify-center lg:gap-3 lg:py-0">
              {!recording ? (
                <button type="button" onClick={start} aria-label="눌러서 말하기" disabled={starting}
                  className="flex size-[72px] items-center justify-center rounded-full border-2 border-b-6 border-track-dark bg-track transition-transform hover:scale-105 active:scale-95">
                  <img src={IC.mic} alt="" className="size-8" />
                </button>
              ) : (
                <button type="button" onClick={stop} aria-label="멈추고 결과 보기" className="relative size-[72px] transition-transform hover:scale-105 active:scale-95">
                  <img src={IC.recording} alt="" className="absolute max-w-none animate-pulse"
                    style={{ top: '-16.67%', left: '-16.67%', width: '133.33%', height: '133.33%' }} />
                </button>
              )}
              <p className={`text-[14px] font-bold leading-figma lg:text-[15px] ${recording ? 'text-track-dark' : 'text-ink-faint'}`}>
                {recording ? '듣고 있어요' : '눌러서 말하기'}
              </p>
            </div>
          </div>
        )
      )}

      {/* 자세히 보기(182:21 · 182:68) — 공통 모달(§3.5: 딤 + 흰 카드 + 원형 X, 바깥 클릭·Esc로 닫힘).
          이렇게 들렸어요 · 음소별 정확도 · 소리+입모양 융합 점수 · DOKA의 한마디 */}
      {summary && (
        <Modal open={showDetail} onClose={closeDetail} title="발음 분석" maxW="max-w-[600px]" gap="gap-3.5">
          {((assessment && !assessment.error && assessment.transcript != null) || phones.length > 0 || fusion?.visual_score != null || mouthRes?.score != null) && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {/* 이렇게 들렸어요(182:73) */}
              {assessment && !assessment.error && assessment.transcript != null && (
                <div className="flex min-h-[140px] flex-col items-center justify-center gap-2 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5 sm:min-h-[207px]">
                  <p className="text-[13px] font-bold leading-figma text-ink-muted">이렇게 들렸어요</p>
                  <p className="text-center text-[34px] font-bold leading-figma tracking-[-0.68px] text-ink">"{assessment.transcript || '(잘 안 들렸어요)'}"</p>
                </div>
              )}

              <div className="flex flex-col gap-3">
                {/* 음소별 발음 정확도(182:88) */}
                {phones.length > 0 && (
                  <div className="flex flex-col items-center gap-2.5 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
                    <p className="text-[13px] font-bold leading-figma text-ink-muted">{chipView.title}</p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {phones.map((p, i) => {
                        const v = phoneValue(p)
                        return (
                          <div key={i} className={`flex flex-col items-center gap-0.5 rounded-[11px] border-1.5 px-[15px] py-[9px] font-bold leading-figma ${phoneTone(p).chip}`}>
                            <span className="text-[18px]">{p.label || '·'}</span>
                            <span className="text-[11px] opacity-80">{v}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* 입모양 점수 — 웹캠 미러로 입모양을 잰 시도에만 값이 있다. 발음 점수에는 섞지 않는다 */}
                {mouthRes && mouthRes.score != null && (
                  <div className="flex flex-col items-center gap-1.5 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
                    <p className="text-[13px] font-bold leading-figma text-ink-muted">입모양 점수</p>
                    <span className="text-[19px] font-bold leading-figma text-track-dark">{Math.round(mouthRes.score)}</span>
                    <p className="text-center text-[11px] leading-relaxed text-ink-faint">웹캠으로 본 입모양이에요. 발음 점수에는 섞지 않고 따로 보여 줘요.</p>
                  </div>
                )}

                {/* 소리 + 입모양 융합 점수(182:77) — 서버가 연구용 융합을 켰을 때만 */}
                {fusion && fusion.visual_score != null && (
                  <div className="flex flex-col items-center gap-2.5 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
                    <p className="text-[13px] font-bold leading-figma text-ink-muted">소리 + 입모양 합친 점수</p>
                    <div className="flex items-center gap-[9px] leading-figma">
                      {fusionAudio != null && (
                        <>
                          <span className="text-[15px] text-ink-soft">소리 {Math.round(fusionAudio)}</span>
                          <span className="text-[13px] text-inactive-line">+</span>
                        </>
                      )}
                      <span className="text-[15px] text-ink-soft">입모양 {Math.round(fusion.visual_score)}</span>
                      <span className="text-[13px] text-inactive-line">→</span>
                      <span className="text-[19px] font-bold text-track-dark">{Math.round(fusion.score)}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 혀 위치(축 E-2·E-6) — 모음 단계에서 녹음의 F1·F2로 추정한 혀 모양을 목표 모음(점선) 위에 겹친다.
              포먼트는 화자 크기(speaker_scale)로 나눠 기준 화자 눈금으로 옮긴 뒤 VocalTractLab 격자에서 찾는다. */}
          {vowelFb && VOWEL_IDS[vowelFb.vowel] && (
            <div className="flex flex-col gap-3 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5 sm:flex-row sm:items-center">
              <div className="w-full shrink-0 sm:w-[220px]">
                <Suspense fallback={<div className="aspect-[4/3] w-full animate-pulse rounded-lg bg-white" />}>
                  <VocalTractVTL phoneme={VOWEL_IDS[vowelFb.vowel]} legend targetLabel={vowelFb.vowel}
                    estimate={{ f1: vowelFb.f1 / (vowelFb.speaker_scale || 1), f2: vowelFb.f2 / (vowelFb.speaker_scale || 1) }} />
                </Suspense>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <p className="text-[13px] font-bold leading-figma text-ink-muted">혀 위치 · 목표 {vowelFb.vowel}</p>
                {(vowelFb.messages || []).map((m, i) => (
                  <p key={i} className="text-[14px] leading-[1.6] text-ink">{m}</p>
                ))}
                <p className="text-[11px] leading-relaxed text-ink-faint">
                  목소리 공명(F1 {vowelFb.f1}Hz · F2 {vowelFb.f2}Hz)으로 추정한 한 가지 예시예요. 같은 소리를 내는 혀 모양은 여럿일 수 있어요.
                </p>
              </div>
            </div>
          )}

          {/* 말 빠르기(S7, docs/speak-visual-cues.md). 문장 단계에서 서버가 정렬로 잰 초당 음절 하나만 보인다. 색 띠는 538 정상 화자 문장의
              10~90백분위다. 사람 유창성 평가와의 상관은 아직 재지 않아 '참고'를 붙이고, 느린 쪽일 때만 안내 한 줄을 띄운다. */}
          {rateCue && (
            <div className="flex flex-col gap-2 rounded-14 border-1.5 border-fill bg-surface-muted px-4 py-3.5">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-[13px] font-bold leading-figma text-ink-muted">{rateCue.title}</p>
                <p className={`text-[15px] font-bold leading-figma ${rateCue.slow ? 'text-warn-text' : 'text-ink'}`}>{rateCue.valueText}</p>
              </div>
              <div className="relative h-2.5 w-full rounded-full bg-white" role="img" aria-label={`${rateCue.valueText}, ${rateCue.note}`}>
                <div className="absolute inset-y-0 rounded-full bg-good-line" style={{ left: `${rateCue.bandLeftPct}%`, width: `${rateCue.bandWidthPct}%` }} />
                <div className={`absolute -top-1 h-[18px] w-1 -translate-x-1/2 rounded-full ${rateCue.slow ? 'bg-warn' : 'bg-track-dark'}`}
                  style={{ left: `${rateCue.markerPct}%` }} />
              </div>
              {rateCue.message && <p className="text-[14px] leading-[1.6] text-ink">{rateCue.message}</p>}
              <p className="text-[11px] leading-relaxed text-ink-faint">{rateCue.note}</p>
            </div>
          )}

          {/* 발성·운율(지표 모드)은 Figma 프레임이 없다 — 이 단계의 유일한 결과라 지표와 목소리 곡선을 둔다 */}
          {metricMode && (
            <>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="목소리 크기" value={`${summary.loudness}/100`} />
                <Stat label="억양 폭" value={`${summary.pitchRange}Hz`} />
                <Stat label="이어 낸 길이" value={`${summary.voicedDuration ?? summary.duration}s`} />
              </div>
              {summary.trace && summary.trace.length >= 3 && !summary.micIssue && (
                <div className="rounded-14 border-1.5 border-fill bg-white p-3">
                  <p className="mb-1 text-xs text-ink-muted">내 목소리 그래프</p>
                  <PitchEnergyGraph trace={summary.trace} summary={summary} dir={toneDirection(mode, drill)} drill={drill} />
                </div>
              )}
            </>
          )}

          {/* DOKA의 한마디(182:106 — DOKA 303:32 · 제목 303:39 · 구분선 303:40) */}
          {!assessment?.coaching && assessment?.coaching_pending && (
            <div className="flex items-center gap-2.5 rounded-14 bg-track-tint px-4 py-3.5 opacity-70" aria-live="polite">
              <span className="relative size-[34px] shrink-0">
                <img src={IC.doka} alt="" className="absolute max-w-none" style={OVERFLOW} />
              </span>
              <p className="shrink-0 whitespace-nowrap text-[14px] font-bold leading-figma text-track-dark">DOKA의 한마디</p>
              <span aria-hidden className="h-4 w-[1.5px] shrink-0 rounded-[1px] bg-speak-dark/30" />
              <p className="min-w-0 flex-1 text-[14px] leading-[1.6] text-track-dark">한마디를 쓰고 있어요…</p>
            </div>
          )}
          {assessment?.coaching_error && (
            <div className="flex flex-wrap items-center gap-2.5 rounded-14 bg-track-tint px-4 py-3.5 text-[14px] text-track-dark" aria-live="polite">
              <span className="font-bold">DOKA의 한마디</span>
              <span>{assessment.coaching_error}</span>
              {assessment.coaching_retry && (
                <button type="button" className="font-bold underline" onClick={() => loadCoaching(assessment.coaching_id, attemptRef.current)}>다시 받기</button>
              )}
            </div>
          )}
          {assessment?.coaching && (
            <div className="flex items-center gap-2.5 rounded-14 bg-track-tint px-4 py-3.5">
              <span className="relative size-[34px] shrink-0">
                <img src={IC.doka} alt="" className="absolute max-w-none" style={OVERFLOW} />
              </span>
              <p className="shrink-0 whitespace-nowrap text-[14px] font-bold leading-figma text-track-dark">DOKA의 한마디</p>
              <span aria-hidden className="h-4 w-[1.5px] shrink-0 rounded-[1px] bg-speak-dark/30" />
              <p className="min-w-0 flex-1 text-[14px] leading-[1.6] text-track-dark">{assessment.coaching}</p>
            </div>
          )}

          {assessment?.error && (
            <div className="rounded-14 bg-surface-muted p-3 text-sm text-ink-muted">{assessment.error}</div>
          )}
        </Modal>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-surface-muted p-2 text-center">
      <p className="text-[10px] text-ink-faint">{label}</p>
      <p className="text-sm font-bold text-ink">{value}</p>
    </div>
  )
}

/**
 * 피치·강세 그래프 — 청각장애 학습자가 자기 발음을 '들을' 수 없으니 곡선으로 '본다'.
 *  위 레인: 억양(높낮이). 평균 피치를 중심으로 ±90Hz 매핑 → 기준 목소리 높이와 무관하게
 *           '변화량'만 곡선으로 드러난다(평평하게 말하면 가운데 점선에 붙은 평평한 선).
 *  아래 레인: 목소리 크기(에너지 포락선) + '적정' 기준 점선. 자주 아래로 내려가면 너무 작았다는 뜻.
 *  발화 트랙 토큰(--speak)으로 배색.
 */
function PitchEnergyGraph({ trace, summary, dir, drill }) {
  if (!trace || trace.length < 3) return null
  const W = 480, H = 250
  const padL = 40, padR = 12, padT = 16, padB = 22
  const innerW = W - padL - padR
  const last = trace[trace.length - 1]
  const tMax = Math.max(summary?.duration || 0, last.t || 0.1, 0.1)
  const X = (t) => padL + (t / tMax) * innerW

  // 위: 억양 레인 / 아래: 크기 레인
  const pTop = padT, pBot = padT + 92
  const eTop = pBot + 26, eBot = H - padB

  // 억양: 평균 중심 ±90Hz
  const voiced = trace.filter((s) => s.hz)
  const center = summary?.pitchMean ||
    (voiced.length ? Math.round(voiced.reduce((a, b) => a + b.hz, 0) / voiced.length) : 180)
  const span = 90
  const PY = (hz) => {
    const c = Math.max(center - span, Math.min(center + span, hz))
    return pBot - ((c - (center - span)) / (2 * span)) * (pBot - pTop)
  }
  const segs = []
  let cur = []
  for (const s of trace) {
    if (s.hz) cur.push([X(s.t), PY(s.hz)])
    else { if (cur.length > 1) segs.push(cur); cur = [] }
  }
  if (cur.length > 1) segs.push(cur)

  // 점들을 부드럽게 통과하는 곡선(Catmull-Rom → 3차 베지어)
  const smooth = (pts, t = 0.18) => {
    if (pts.length < 2) return ''
    if (pts.length === 2) return `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)} L${pts[1][0].toFixed(1)} ${pts[1][1].toFixed(1)}`
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2
      const c1x = p1[0] + (p2[0] - p0[0]) * t, c1y = p1[1] + (p2[1] - p0[1]) * t
      const c2x = p2[0] - (p3[0] - p1[0]) * t, c2y = p2[1] - (p3[1] - p1[1]) * t
      d += ` C${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`
    }
    return d
  }

  // 크기: 에너지 포락선(면적) — 이동평균으로 지터 완화 후 부드러운 상단선
  const eMax = 0.14
  const EY = (rms) => eBot - Math.min(1, Math.max(0, rms) / eMax) * (eBot - eTop)
  const yTh = EY(loudnessRms(40))   // 크기 40/100 (적정 기준선, RMS 0.062)
  // '작게' 연습은 적정선 대신 목표 구간(크기 12~45)을 그린다
  const soft = drill === 'soft'
  const yBandTop = EY(loudnessRms(SOFT_BAND[1])), yBandBot = EY(loudnessRms(SOFT_BAND[0]))
  const rmsArr = trace.map((s) => s.rms)
  const topPts = trace.map((s, i) => {
    const a = rmsArr[i - 1] ?? rmsArr[i], b = rmsArr[i], c = rmsArr[i + 1] ?? rmsArr[i]
    return [X(s.t), EY((a + b + c) / 3)]
  })
  const topLine = smooth(topPts)
  const areaFill = topLine + ` L${X(last.t).toFixed(1)} ${eBot} L${X(trace[0].t).toFixed(1)} ${eBot} Z`

  const flat = toneMissed(summary, dir)   // 운율 올리기·내리기에서 끝이 목표 방향으로 움직이지 않음
  const volNote = volumeCurveNote(summary, drill)
  const midY = (pTop + pBot) / 2

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 260 }}
           role="img" aria-label="발음 피치·강세 그래프">
        {/* 레인 배경 */}
        <rect x={padL} y={pTop} width={innerW} height={pBot - pTop} rx="8" style={{ fill: 'var(--speak-tint)' }} />
        <rect x={padL} y={eTop} width={innerW} height={eBot - eTop} rx="8" style={{ fill: 'var(--fill)' }} />

        {/* 억양 기준선(평균=평평의 기준) */}
        <line x1={padL} y1={midY} x2={W - padR} y2={midY} strokeOpacity="0.45" strokeWidth="1" strokeDasharray="4 4" style={{ stroke: 'var(--speak)' }} />
        {/* 억양 곡선 */}
        {segs.map((pts, i) => (
          <path key={i} d={smooth(pts)} fill="none" strokeWidth="2.5"
                strokeLinejoin="round" strokeLinecap="round" style={{ stroke: 'var(--speak)' }} />
        ))}

        {/* 크기 포락선(면적 + 부드러운 상단선) + 적정 기준선 */}
        <path d={areaFill} fillOpacity="0.16" stroke="none" style={{ fill: 'var(--speak)' }} />
        <path d={topLine} fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ stroke: 'var(--speak)' }} />
        {soft ? (
          <>
            <rect x={padL} y={yBandTop} width={innerW} height={yBandBot - yBandTop} fillOpacity="0.12" style={{ fill: 'var(--warn)' }} />
            <line x1={padL} y1={yBandTop} x2={W - padR} y2={yBandTop} strokeWidth="1" strokeDasharray="5 4" style={{ stroke: 'var(--warn)' }} />
            <line x1={padL} y1={yBandBot} x2={W - padR} y2={yBandBot} strokeWidth="1" strokeDasharray="5 4" style={{ stroke: 'var(--warn)' }} />
            <text x={W - padR} y={yBandTop - 3} textAnchor="end" fontSize="9" style={{ fill: 'var(--warn-strong)' }}>목표</text>
          </>
        ) : (
          <>
            <line x1={padL} y1={yTh} x2={W - padR} y2={yTh} strokeWidth="1" strokeDasharray="5 4" style={{ stroke: 'var(--warn)' }} />
            <text x={W - padR} y={yTh - 3} textAnchor="end" fontSize="9" style={{ fill: 'var(--warn-strong)' }}>알맞음</text>
          </>
        )}

        {/* 레인 라벨 */}
        <text x="4" y={midY - 3} fontSize="10" fontWeight="600" style={{ fill: 'var(--speak)' }}>억양</text>
        <text x="4" y={midY + 9} fontSize="8" style={{ fill: 'var(--ink-faint)' }}>높낮이</text>
        <text x="4" y={(eTop + eBot) / 2 + 3} fontSize="10" fontWeight="600" style={{ fill: 'var(--ink-muted)' }}>크기</text>

        {/* 시간축 */}
        <text x={padL} y={H - 5} fontSize="9" style={{ fill: 'var(--ink-faint)' }}>0s</text>
        <text x={W - padR} y={H - 5} textAnchor="end" fontSize="9" style={{ fill: 'var(--ink-faint)' }}>{tMax.toFixed(1)}s</text>
      </svg>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-muted">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-[2px] w-3 bg-speak" /> 억양선</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-3 border border-speak bg-speak-tint" /> 목소리 크기</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 border-t border-dashed border-warn" /> {soft ? `목표 크기 ${SOFT_BAND[0]}~${SOFT_BAND[1]}` : '알맞은 크기'}</span>
      </div>
      <div className="mt-1 space-y-0.5">
        {flat && <p className="text-[11px] text-warn-text">억양선 끝이 시작보다 {dir === 'rise' ? '높아지지' : '낮아지지'} 않았어요 → 끝에서 선을 {dir === 'rise' ? '올려' : '내려'}보세요.</p>}
        {volNote && <p className="text-[11px] text-warn-text">{volNote}</p>}
        {!flat && !volNote && <p className="text-[11px] text-good-text">{dir ? '억양선과 크기 선이 잘 살아있어요.' : '크기 선이 고르게 잘 이어졌어요.'}</p>}
      </div>
    </div>
  )
}
