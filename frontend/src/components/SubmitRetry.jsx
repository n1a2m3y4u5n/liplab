/** 답을 서버에 보내지 못했을 때의 공용 안내. 조용히 다음 문항으로 넘어가 기록이 빠지지 않게, 다시 보내거나 건너뛰기를 고르게 한다. */
export default function SubmitRetry({ onResend, onSkip, busy = false, className = '' }) {
  return (
    <div role="alert" className={`flex flex-wrap items-center justify-between gap-3 rounded-14 border-2 border-bad-line bg-bad-tint px-4 py-2.5 text-[13.5px] font-bold text-bad-text ${className}`}>
      기록을 보내지 못했어요
      <span className="flex shrink-0 gap-4">
        <button type="button" onClick={onResend} disabled={busy} className="underline disabled:opacity-50">다시 보내기</button>
        <button type="button" onClick={onSkip} disabled={busy} className="underline disabled:opacity-50">건너뛰기</button>
      </span>
    </div>
  )
}
