import { useEffect } from 'react'

/** 모달 닫기 — Figma Close(36px 원 + X, 210:194·222:170·338:237 공통 에셋). 다른 모달에서도 쓴다. */
export function ModalClose({ onClose, className = '' }) {
  return (
    <button type="button" onClick={onClose} aria-label="닫기"
      className={`size-9 shrink-0 rounded-full transition hover:brightness-95 ${className}`}>
      <img src="/ui/lp-210-189-modal-close.svg" alt="" className="size-9" />
    </button>
  )
}

/**
 * 모달 (핸드오프 §3.5, Figma 210:189 · 222:165 등 상세 모달 공통) — 딤 오버레이 + 중앙 흰 카드 + 오른쪽 위 원형 X.
 * ESC·배경 클릭으로 닫힘. 본문은 children.
 * Figma 스펙: 오버레이 bg-overlay/50, 카드 rounded-22 / pt-26 pb-28 px-28,
 * 그림자 shadow-modal, 제목 21px tracking-[-.42px], 닫기 = Figma Close 에셋(36px, 210:194).
 * 선택 props: subtitle(제목 아래 보조문구 — Figma 모달 제목부에는 없으니 넣지 않는 것이 기본),
 * tone('default'|'danger' 붉은 제목+분홍 테두리, 222:168), gap(헤더-본문 간격), cardClass(카드 추가 클래스).
 * 폭은 maxW로: 전체 통계 max-w-[880px](210:189), 학습 초기화·상세 분석 max-w-[600px](222:165·182:68).
 * 스크롤: 카드는 overflow-hidden, 헤더는 고정, 본문만 스크롤(.modal-scroll)한다. 카드 여백은
 * 헤더(pt-26·px-28)와 본문(px-28·pb-28)이 나눠 갖고, gap은 헤더-본문 사이와 본문 항목 사이에 똑같이 들어간다.
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/50 p-4" onClick={onClose}>
      {/* 카드는 overflow-hidden으로 모서리를 지키고, 스크롤은 본문 영역만 — 스크롤바가 둥근 모서리 밖으로 튀어나오지 않는다 */}
      <div
        role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}
        className={`flex w-full flex-col ${gap} ${maxW} max-h-[86vh] overflow-hidden rounded-22 bg-white shadow-modal ${danger ? 'border-2 border-bad-line' : ''} ${cardClass}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex w-full shrink-0 items-start justify-between px-[28px] pt-[26px]">
          <div className="flex min-h-9 flex-col justify-center gap-[4px]">
            <h2 className={`text-[21px] font-bold leading-figma tracking-[-0.42px] ${danger ? 'text-bad-text' : 'text-ink'}`}>{title}</h2>
            {subtitle && <p className="text-[13px] text-ink-muted">{subtitle}</p>}
          </div>
          <ModalClose onClose={onClose} />
        </div>
        {/* 본문 — 스크롤 영역은 블록으로 두고 안쪽 래퍼가 항목 사이 gap을 준다(항목이 높이에 눌려 줄지 않고 스크롤된다) */}
        <div className="modal-scroll min-h-0 flex-1 overflow-y-auto px-[28px] pb-[28px]">
          <div className={`flex flex-col ${gap}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
