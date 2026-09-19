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
      <div className={`w-full ${maxW} max-h-[86vh] overflow-y-auto rounded-[22px] border-2 border-b-[5px] border-line bg-white p-6 shadow-2xl`}
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-[20px] font-bold tracking-[-0.4px] text-ink">{title}</h2>
          <button type="button" onClick={onClose} aria-label="닫기" className="text-ink-muted hover:text-ink">
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
