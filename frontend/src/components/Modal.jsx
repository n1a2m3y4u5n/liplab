import { useEffect } from 'react'

/**
 * 모달 (Figma 리디자인 06/07 상세 모달 공통) — 반투명 오버레이 + 중앙 카드 + 나가기 X.
 * ESC·배경 클릭으로 닫힘. 본문은 children.
 */
export default function Modal({ open, onClose, title, children, maxW = 'max-w-lg' }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      {/* 카드는 overflow-hidden으로 모서리를 지키고, 스크롤은 본문 영역만 — 스크롤바가 둥근 모서리 밖으로 튀어나오지 않는다 */}
      <div className={`flex w-full ${maxW} max-h-[86vh] flex-col overflow-hidden rounded-[22px] border border-line bg-white shadow-2xl`}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex shrink-0 items-center justify-between px-6 pb-4 pt-6">
          <h2 className="text-[20px] font-bold tracking-[-0.4px] text-ink">{title}</h2>
          <button type="button" onClick={onClose} aria-label="닫기" className="text-ink-muted hover:text-ink">
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <div className="modal-scroll min-h-0 flex-1 overflow-y-auto px-6 pb-6">
          {children}
        </div>
      </div>
    </div>
  )
}
