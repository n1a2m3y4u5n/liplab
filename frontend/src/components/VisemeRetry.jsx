/** 입모양을 받지 못했을 때의 공용 안내(Practice의 visemeError와 같은 모양). 문항 상태는 건드리지 않고 입모양만 다시 받는다. */
export default function VisemeRetry({ onRetry, className = '' }) {
  return (
    <div role="alert" className={`flex items-center justify-between gap-3 rounded-14 border border-bad-line bg-bad-tint px-4 py-2.5 text-[13.5px] font-bold text-bad-text ${className}`}>
      입모양을 불러오지 못했어요
      <button type="button" onClick={onRetry} className="shrink-0 underline">다시 받기</button>
    </div>
  )
}
