import { useId } from 'react'
import { soundStatusText } from '../../lib/listenView'
import { ProgressLine, SpeakerIcon } from './ui'

/**
 * 소리 카드: 화면의 중심(듣기 버튼 + 상태). 버튼 왼쪽·글 오른쪽으로 낮게 둬서 1366×768 같은 낮은 화면에서도 보기까지 한 화면에 들어온다.
 * clipState: 'loading' | 'ready' | 'missing'. maxPlays를 주면 그만큼만 듣는다(검사). statusText로 상태 문구를 바꿀 수 있다(Ling 무음 시행).
 * 접근성(청각장애 학습자): 소리 상태(준비 중·나오는 중·끝남)를 글과 막대로 늘 보인다. 막대는 시간만 보이고 소리 모양(파형)은 그리지 않는다
 * (파형은 길이·같다·다르다를 눈으로 풀게 해 듣기 훈련이 아니게 된다).
 */
export default function SoundCard({ player, onPlay, clipState = 'ready', label, plays = 0, maxPlays = null, disabled = false, statusText = null, children }) {
  const statusId = useId()
  const limit = maxPlays != null && plays >= maxPlays
  const phase = clipState !== 'ready' ? clipState : limit && !player.busy ? 'limit' : player.phase
  const text = statusText || soundStatusText(phase, { part: player.part, parts: player.parts })
  // 재생 중에는 버튼을 회색으로 끄지 않고 눌린 모양(트랙색)으로 둔다. 회색은 '지금 들을 수 없음'일 때만
  const off = disabled || clipState !== 'ready' || limit
  const left = maxPlays != null && !limit ? ` · ${maxPlays - plays}번 더 들을 수 있어요` : ''
  return (
    <div className="rounded-18 border-2 border-line bg-white px-4 py-4 lg:rounded-22 lg:px-6 lg:py-5">
      <div className="flex items-center gap-4 lg:gap-5">
        <button type="button" onClick={player.busy ? undefined : onPlay} disabled={off && !player.busy} aria-disabled={player.busy || off}
          aria-describedby={statusId} aria-label={player.busy ? '소리가 나오고 있어요' : `${label}, 스페이스 키`}
          className={`flex size-[72px] shrink-0 items-center justify-center rounded-full border-2 text-white transition-all duration-100 disabled:cursor-not-allowed disabled:border-inactive-line disabled:bg-inactive disabled:text-inactive-text lg:size-[80px] ${
            player.busy ? 'translate-y-[2px] cursor-default border-b-2 border-track-dark bg-track-dark' : 'border-b-5 border-track-dark bg-track hover:bg-track-hover active:translate-y-[2px] active:border-b-2'}`}>
          <SpeakerIcon playing={player.busy} />
        </button>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="text-[16px] font-bold leading-figma text-ink lg:text-[17px]">{label}</p>
          <ProgressLine phase={clipState === 'ready' ? player.phase : 'idle'} run={player.run} totalMs={player.totalMs} />
          <p id={statusId} role="status" aria-live="polite" className={`text-[13px] font-bold leading-snug ${player.busy ? 'text-track-dark' : 'text-ink-muted'}`}>
            {text}
          </p>
          <p className="text-[12px] leading-snug text-ink-faint">
            {plays > 0 ? `${plays}번 들었어요${left} · ` : left ? `${left.slice(3)} · ` : ''}기계 목소리(합성)<span className="hidden lg:inline"> · 스페이스 키로 듣기</span>
          </p>
        </div>
      </div>
      {children}
    </div>
  )
}
