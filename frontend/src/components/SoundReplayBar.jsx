import { shouldSuggest } from '../lib/soundSync'

/**
 * 답한 뒤의 '소리와 함께 다시 보기'(C17) 줄. 레슨의 결과 영역에 둔다(답 전에는 그리지 않는다).
 *  - 소리 조건이 켜져 있으면 버튼. 누르면 소리와 함께 한 번, 소리 없이 한 번 더 보인다(useSoundReplay).
 *  - 꺼져 있고 보청기·인공와우를 답한 학습자면 한 번 권한다(켜기 / 괜찮아요). 그 밖에는 아무것도 그리지 않는다.
 * sound: useSoundCondition(), replay: useSoundReplay()
 */
const LABEL = {
  idle: '소리와 함께 다시 보기',
  loading: '소리 가져오는 중',
  sound: '소리와 함께 보는 중',
  silent: '소리 없이 한 번 더',
  unavailable: '소리 준비 중이에요',
}

export default function SoundReplayBar({ sound, replay }) {
  if (!sound) return null
  if (!sound.enabled) {
    if (!shouldSuggest(sound)) return null
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-16 border-2 border-line bg-white p-3 text-[13px] leading-snug text-ink-muted">
        <p className="min-w-0 flex-1">보청기나 인공와우를 쓰신다면, 답한 뒤 소리와 함께 한 번 더 볼 수 있어요. 답은 늘 소리 없이 해요.</p>
        <button type="button" onClick={() => sound.setEnabled(true)} className="btn-secondary px-3 py-2 text-[13px] text-track">켜기</button>
        <button type="button" onClick={sound.dismiss} className="px-2 py-2 text-[13px] text-ink-faint hover:text-ink">괜찮아요</button>
      </div>
    )
  }
  const busy = replay.phase !== 'idle' && replay.phase !== 'unavailable'
  return (
    <div className="flex items-center gap-2">
      <button type="button" onClick={busy ? replay.stop : replay.start} aria-live="polite" title="소리는 미리 만든 합성 음성이에요"
        className={`btn-secondary flex flex-1 items-center justify-center gap-2 py-2.5 text-[14px] ${replay.phase === 'unavailable' ? 'text-ink-faint' : 'text-track'}`}>
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M11 5 6 9H3v6h3l5 4V5z" />
          {replay.phase === 'silent' ? <path d="m16 9 5 6m0-6-5 6" /> : <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />}
        </svg>
        {LABEL[replay.phase] || LABEL.idle}
      </button>
      {busy && <span className="sr-only">누르면 멈춰요</span>}
    </div>
  )
}
