// 보기 앞 번호 칩. 채점 뒤에는 정답에 ✓, 고른 오답에 ✕를 그려 색만으로 맞고 틀림을 알리지 않게 한다(11/03).
// state: idle | selected | correct(고른 정답) | target(못 고른 정답) | wrong(고른 오답)
const SR = { correct: '정답, 고른 답', target: '정답', wrong: '고른 답, 틀린 답' }
const TONE = { correct: 'bg-good text-white', target: 'bg-good text-white', wrong: 'bg-bad text-white' }

export default function OptionKey({ n, state = 'idle', className = '' }) {
  const mark = state === 'wrong' ? 'x' : state === 'correct' || state === 'target' ? 'check' : null
  return (
    <span className={`flex size-6 shrink-0 items-center justify-center rounded-[7px] text-[12px] font-bold leading-figma lg:size-7 lg:rounded-lg lg:text-[13px] ${TONE[state] || 'bg-fill text-ink-muted'} ${className}`}>
      {mark ? (
        <>
          <svg viewBox="0 0 16 16" aria-hidden className="size-3.5 lg:size-4" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            {mark === 'check' ? <path d="M3.5 8.5l3 3 6-7" /> : <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />}
          </svg>
          <span className="sr-only">{SR[state]}</span>
        </>
      ) : n}
    </span>
  )
}
