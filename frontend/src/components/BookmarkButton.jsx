/**
 * 북마크 버튼 (Figma 컴포넌트 328:8 — Default 328:2 / Active 328:5, 모바일 인스턴스 328:64).
 * 레슨 질문 제목 오른쪽 끝에 둔다(§3.4). 기본은 흰 바탕+라인 테두리, 누르면 브랜드 틴트로 채운다.
 * 발화 레슨(328:49)에서도 트랙 분홍이 아니라 이 브랜드색 그대로다.
 * 크기: lg 미만 38px·아이콘 16.29px(328:64) / lg 이상 42px·아이콘 18px(328:2).
 * 저장은 호출부가 한다 — active(현재 상태)와 onToggle만 받는다.
 */
export default function BookmarkButton({ active = false, onToggle, disabled = false, label = '북마크', className = '' }) {
  return (
    <button type="button" onClick={onToggle} disabled={disabled} aria-label={label} aria-pressed={active}
      className={`flex size-[38px] shrink-0 items-center justify-center rounded-full border-2 transition-colors disabled:cursor-not-allowed disabled:opacity-50 lg:size-[42px] ${
        active ? 'border-primary-500 bg-primary-100' : 'border-line bg-white'} ${className}`}>
      <img src={active ? '/ui/lp-328-8-bookmark-active.svg' : '/ui/lp-328-8-bookmark-default.svg'} alt=""
        className="size-[16.29px] lg:size-[18px]" />
    </button>
  )
}
