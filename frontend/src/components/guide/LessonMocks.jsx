import { area, RISE, FADE, FaceStage, mouthAt } from './MockPrimitives'
import { scoreTone } from '../../lib/scoreTone'

function LessonShell({ track = 'read', done = 0, children, bar }) {
  return (
    <div data-track={track} className="relative flex h-full flex-col overflow-hidden bg-page text-ink">
      <div className="flex items-center gap-3 px-[18px] pt-[18px]">
        <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 shrink-0" />
        <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong">
          <div className="h-full rounded-full bg-track transition-[width] duration-500 ease-out" style={{ width: `${(done / 12) * 100}%` }} />
        </div>
        <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted">1 / 12</span>
      </div>
      <div className="flex flex-col gap-4 px-[18px] pt-6">{children}</div>
      <div className="absolute inset-x-0 bottom-0 z-10">{bar}</div>
    </div>
  )
}

function Question({ label, title }) {
  return (
    <div className="relative flex flex-col gap-1.5 pr-12 leading-figma">
      <p className="text-[12px] font-bold text-track">{label}</p>
      <p className="text-[21px] font-bold tracking-[-0.525px] text-ink">{title}</p>
      <span {...area('bookmark')} className="absolute right-0 top-[14px] flex size-[38px] items-center justify-center rounded-full border border-line bg-white">
        <img src="/ui/lp-328-8-bookmark-default.svg" alt="" className="size-[16.29px]" />
      </span>
    </div>
  )
}

const OPT = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] transition-colors duration-300 ease-out'
const OPT_CLASS = {
  idle: `${OPT} py-3 border border-line bg-white text-ink`,
  selected: `${OPT} py-3 border border-track bg-track-tint text-ink`,
  correct: `${OPT} pb-3 pt-[14px] border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPT} pb-3 pt-[14px] border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPT} pb-3 pt-[14px] border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}

function Option({ n, word, state = 'idle' }) {
  return (
    <div className={OPT_CLASS[state]}>
      <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted">{n}</span>
      <span className="flex-1 text-[18px] font-bold leading-figma">{word}</span>
    </div>
  )
}

// 단어 독화 문항(두 보기와 결과 바가 한 화면에 들어오게 입모양 칸·보기·하단 바를 앱보다 조금 줄였다). 시연 장면: play(입모양 재생) → select(보기 고름) → confirm(확인 누름) → result(결과 바).
// wrong이면 1번 '나비'를 골라 틀리고, 아니면 2번 '바다'를 골라 맞힌다. 장면이 없으면 정지 화면(골라 둔 상태 또는 오답 결과).
function ReadMock({ wrong = false, scene, tick, running }) {
  const s = scene || (wrong ? 'result' : 'select')
  const pick = wrong ? 1 : 2
  const shown = s === 'result'
  const optState = (n) => {
    if (s === 'play') return 'idle'
    if (!shown) return n === pick ? 'selected' : 'idle'
    if (n === 2) return pick === 2 ? 'correct' : 'target'
    return n === pick ? 'wrong' : 'idle'
  }
  const correct = !wrong
  const bar = shown ? (
    <div key="result" className={`flex flex-col gap-2.5 border-t-2 px-[18px] pb-4 pt-3 ${correct ? 'border-good bg-good-tint' : 'border-bad bg-bad-tint'}`}>
      <div className={`flex flex-col gap-[3px] leading-figma ${RISE} ${correct ? 'text-good-text' : 'text-bad-text'}`}>
        <p className="text-[19px] font-bold tracking-[-0.38px]">{correct ? '정답이에요!' : '아쉬워요'}</p>
        <p className="text-[13px] font-bold opacity-80">정답은 「바다」예요</p>
      </div>
      <span className={`${correct ? 'btn-good' : 'btn-bad'} btn-bar w-full py-3 text-center text-[16px]`}>계속하기</span>
    </div>
  ) : (
    <div key="ask" className="border-t-2 border-line bg-white px-[18px] pb-4 pt-3">
      <span className={`btn-primary btn-bar block w-full py-3 text-center text-[16px] ${
        s === 'play' ? '!border-inactive-line !bg-inactive !text-inactive-text' : s === 'confirm' ? '' : ''}`}>확인</span>
    </div>
  )
  return (
    <LessonShell done={shown ? 1 : 0} bar={<div {...area('resultBar')}>{bar}</div>}>
      <Question label="단어 독화" title="이 입모양은 어떤 단어일까요?" />
      <div {...area('stage')} className="h-[158px] w-full rounded-18 border border-line bg-white p-4">
        <FaceStage mouth={mouthAt(tick, running)} className="h-full" talker="사람 2" />
      </div>
      <div {...area('options')} className="flex flex-col gap-2.5">
        <Option n={1} word="나비" state={optState(1)} />
        <Option n={2} word="바다" state={optState(2)} />
      </div>
    </LessonShell>
  )
}

// 녹음 중 파형. 틱마다 막대 높이를 바꾸고 높이 전환(300ms)으로 이어 붙인다.
function Wave({ tick }) {
  return (
    <div className="flex h-[26px] items-center justify-center gap-[3px]">
      {Array.from({ length: 30 }, (_, i) => {
        const v = Math.abs(Math.sin(i * 1.7 + tick * 2.3)) * (0.45 + 0.55 * Math.abs(Math.sin(i * 0.37 + tick * 0.9)))
        return <span key={i} className="w-[3px] rounded-full bg-track transition-[height] duration-300 ease-out" style={{ height: 4 + v * 22 }} />
      })}
    </div>
  )
}

const PHONES = [['ㅂ', 88], ['ㅏ', 92], ['ㄷ', 58], ['ㅏ', 90]]

// 발화 문항(결과 카드와 결과 바가 겹치지 않게 여백을 앱보다 조금 줄였다). before = 녹음 전·중(idle → rec), result = 결과(idle·rec 동안은 분석 중, result에서 점수·칩이 나온다).
function SpeakMock({ result = false, scene, tick, running }) {
  const s = scene || (result ? 'result' : 'idle')
  let body
  let bar
  if (result) {
    const ready = s === 'result'
    const good = PHONES.filter(([, v]) => scoreTone(v).level === 'good').length
    body = (
      <div className="flex w-full flex-col items-center gap-3 rounded-18 border border-line bg-white px-4 py-4">
        <div {...area('score')} className="flex flex-col items-center gap-0.5 font-bold leading-figma">
          {ready
            ? <p key="score" className={`text-[44px] tracking-[-1.32px] ${FADE} ${scoreTone(84).text}`}>84%</p>
            : <p key="wait" className="text-[44px] tracking-[-1.32px] text-ink-ghost">…</p>}
          <p className="text-[13px] text-ink-faint">발음 점수</p>
        </div>
        <div {...area('chips')} className="flex justify-center gap-2">
          {PHONES.map(([p, v], i) => (
            ready ? (
              <span key={`r${i}`} className={`flex size-12 items-center justify-center rounded-13 border ${RISE} ${scoreTone(v).chip}`}
                style={{ animationDelay: `${120 + i * 90}ms` }}>
                <span className="text-[20px] font-bold leading-figma">{p}</span>
              </span>
            ) : <span key={`w${i}`} className="size-12 rounded-13 border border-dashed border-line bg-surface-muted" />
          ))}
        </div>
        <span {...area('detail')} className={`btn-secondary rounded-[12px] px-[26px] py-3 text-[14px] transition-opacity duration-300 ${ready ? '' : 'opacity-50'}`}>자세히 보기</span>
      </div>
    )
    bar = ready ? (
      <div key="done" className="flex flex-col gap-2.5 border-t-2 border-good/35 bg-good-tint px-[18px] pb-4 pt-3">
        <div className={`flex flex-col gap-[3px] font-bold leading-figma text-good-text ${RISE}`}>
          <p className="text-[19px] tracking-[-0.38px]">잘했어요!</p>
          <p className="text-[13px] opacity-80">{PHONES.length}개 중 {good}개 소리를 정확히 냈어요</p>
        </div>
        <div className="flex gap-2.5">
          <span className="btn-secondary btn-bar flex-1 rounded-13 border-good-line px-0 py-3 text-center text-[15px] text-good-text">다시 말하기</span>
          <span className="btn-good btn-bar flex-1 rounded-13 px-0 py-3 text-center text-[15px]">계속하기</span>
        </div>
      </div>
    ) : (
      <div key="wait" className="flex flex-col gap-[3px] border-t-2 border-line bg-white px-[18px] pb-[26px] pt-4 font-bold leading-figma text-ink-muted">
        <p className="text-[19px] tracking-[-0.38px]">분석 중…</p>
        <p className="text-[13px] opacity-80">발음을 분석하고 있어요</p>
      </div>
    )
  } else {
    const rec = s === 'rec'
    body = (
      <div {...area('stage')} className="w-full overflow-hidden rounded-18 border border-line bg-white">
        <div className="px-4 pt-4"><FaceStage mouth={mouthAt(tick, running)} className="h-[120px]" /></div>
        <div className="flex h-[46px] items-center justify-center">
          {rec
            ? <div key="wave" className={FADE}><Wave tick={tick} /></div>
            : <p key="cap" className={`text-center text-[13px] font-bold leading-figma text-ink-faint ${scene ? FADE : ''}`}>입모양을 따라 해보세요</p>}
        </div>
      </div>
    )
    bar = (
      <div className="flex flex-col items-center gap-2.5 border-t-2 border-line bg-white px-[18px] pb-[26px] pt-[18px]">
        <span {...area('mic')} className="relative block size-[72px]">
          {rec ? (
            <img key="rec" src="/ui/speak-recording.svg" alt="" className="absolute max-w-none animate-pulse"
              style={{ top: '-16.67%', left: '-16.67%', width: '133.33%', height: '133.33%' }} />
          ) : (
            <span key="mic" className="flex size-[72px] items-center justify-center rounded-full border border-track-dark bg-track">
              <img src="/ui/speak-mic.svg" alt="" className="size-8" />
            </span>
          )}
        </span>
        <p className={`text-[14px] font-bold leading-figma ${rec ? 'text-track-dark' : 'text-ink-faint'}`}>{rec ? '듣고 있어요' : '눌러서 말하기'}</p>
      </div>
    )
  }
  return (
    <LessonShell track="speak" done={result && s === 'result' ? 1 : 0} bar={bar}>
      <Question label="음절·단어" title="이 단어를 소리 내어 말해보세요" />
      <div className="flex items-center justify-center rounded-16 bg-track-tint py-[18px] pl-[22px] pr-4">
        <p className="text-center text-[32px] font-bold leading-figma tracking-[-0.64px] text-track-dark">바다</p>
      </div>
      {body}
    </LessonShell>
  )
}

// ── 06 연습 ──────────────────────────────────────────────────────────────────

export { ReadMock, SpeakMock }
