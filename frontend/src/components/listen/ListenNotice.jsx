import { useEffect, useRef } from 'react'

export default function ListenNotice({ onClose }) {
  const dialog = useRef(null)
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close() }, [])
  return <dialog ref={dialog} onCancel={(e) => { e.preventDefault(); onClose() }} aria-labelledby="listen-notice-title"
    className="listen-notice mb-0 mt-auto w-full max-w-[480px] rounded-t-24 border-0 bg-white p-6 text-ink shadow-modal backdrop:bg-black/40 lg:m-auto lg:rounded-24" data-track="listen">
    <div className="flex items-center justify-between gap-4"><h2 id="listen-notice-title" className="text-[23px] font-bold">소리 듣기 안내</h2><button onClick={onClose} aria-label="안내 닫기" className="size-11 text-2xl">×</button></div>
    <div className="my-5 flex flex-col gap-3 text-[15px] leading-relaxed">
      <p className="flex items-center gap-3 rounded-16 border-2 border-warn bg-warn-tint p-3"><span aria-hidden className="text-2xl text-warn-text">△</span><strong>귀가 아프거나 울리면 바로 멈추세요.</strong></p>
      <p className="flex items-center gap-3 rounded-16 bg-surface-sunken p-3"><span aria-hidden className="text-2xl text-ink-muted">⊕</span><span><strong>의료기기가 아니며, 청력을 진단하거나 치료하지 않아요.</strong><span className="mt-1 block text-[14px] text-ink-muted">보청기·인공와우 조절은 청능사나 병원에서 해요.</span></span></p>
      <p className="flex items-center gap-3 rounded-16 bg-surface-sunken p-3"><span aria-hidden className="text-2xl text-ink-muted">≋</span><span><strong>목소리는 기계로 만든 소리예요(합성).</strong><span className="mt-1 block text-[12px] text-ink-muted">Supertonic 3</span></span></p>
    </div>
    <button onClick={onClose} className="btn-primary btn-lg w-full">확인</button>
  </dialog>
}
