import { useEffect, useRef } from 'react'

export default function ListenNotice({ onClose }) {
  const dialog = useRef(null)
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close() }, [])
  return <dialog ref={dialog} onCancel={(e) => { e.preventDefault(); onClose() }} aria-labelledby="listen-notice-title"
    className="listen-notice m-auto w-[calc(100%-36px)] max-w-[480px] rounded-24 border-0 bg-white p-6 text-ink shadow-modal backdrop:bg-black/40" data-track="listen">
    <div className="flex items-center justify-between gap-4"><h2 id="listen-notice-title" className="text-[23px] font-bold">소리 듣기 안내</h2><button onClick={onClose} aria-label="안내 닫기" className="size-11 text-2xl">×</button></div>
    <div className="my-5 flex flex-col divide-y divide-line text-[15px] leading-relaxed">
      <p className="py-4"><strong className="mb-2 block text-track-dark">소리 크기</strong>편안한 크기로 시작하세요. 귀가 아프거나 불편하면 멈추세요.</p>
      <p className="py-4"><strong className="mb-2 block text-track-dark">연습용</strong>의료기기가 아니며, 청력을 진단하거나 치료하지 않아요.</p>
      <p className="py-4"><strong className="mb-2 block text-track-dark">기계 목소리(합성)</strong>미리 합성한 음성을 사용해요. Supertonic 3.</p>
    </div>
    <button onClick={onClose} className="btn-primary btn-lg w-full">확인</button>
  </dialog>
}
