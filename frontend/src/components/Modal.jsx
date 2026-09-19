import { useEffect } from 'react'

/**
 * 모달 (Figma 리디자인 06/07 상세 모달 공통) — 반투명 오버레이 + 중앙 카드 + 나가기 X.
 * ESC·배경 클릭으로 닫힘. 본문은 children.
 * Figma 스펙: 오버레이 rgba(15,10,31,.5), 카드 rounded-22 / pt-26 pb-28 px-28,
 * 그림자 0 18 44 -6 rgba(13,5,31,.32), 제목 21px tracking-[-.42px].
 * 선택 props: subtitle(제목 아래 보조문구), tone('default'|'danger' 붉은 제목+분홍 테두리),
 * gap(헤더-본문 간격), cardClass(카드 추가 클래스). 기존 호출부는 그대로 동작한다.
 */
export default function Modal({ open, onClose, title, subtitle, children, maxW = 'max-w-lg', tone = 'default', gap = 'gap-[22px]', cardClass = '' }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  const danger = tone === 'danger'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0f0a1f]/50 p-4" onClick={onClose}>
      <div
        className={`flex w-full flex-col ${gap} ${maxW} max-h-[86vh] overflow-y-auto rounded-[22px] bg-white pb-[28px] pt-[26px] px-[28px] shadow-[0px_18px_44px_-6px_rgba(13,5,31,0.32)] ${danger ? 'border-2 border-[#f3c8c8]' : ''} ${cardClass}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex w-full items-start justify-between">
          <div className="flex flex-col gap-[4px]">
            <h2 className={`text-[21px] font-bold tracking-[-0.42px] ${danger ? 'text-[#b91c1c]' : 'text-ink'}`}>{title}</h2>
            {subtitle && <p className="text-[13px] text-ink-muted">{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="닫기"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#f3f3f7] text-ink-muted transition-colors hover:bg-[#e9e9f0] hover:text-ink">
            <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
