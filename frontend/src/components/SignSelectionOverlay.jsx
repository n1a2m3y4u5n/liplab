import { useState, useEffect, useCallback, lazy, Suspense } from 'react'

// SignPanel(→수어 영상, 무거움)은 모달을 열 때만 로드 → 초기 번들에 안 실림.
const SignPanel = lazy(() => import('./SignPanel'))

const hasKorean = (s) => /[가-힣]/.test(s)

/**
 * 전역 텍스트 선택 → 수어 번역.
 * 앱 어느 화면에서든 한국어 문장을 드래그하면 근처에 "수어로 보기" 버튼이 뜨고,
 * 누르면 그 자리에서 슬라이드오버로 수어를 보여준다(수어 탭으로 이동 불필요).
 * App 루트에 1회 마운트. 리스너/버튼은 가볍고, 무거운 SignPanel은 지연로딩.
 */
export default function SignSelectionOverlay() {
  const [hint, setHint] = useState(null)     // {text, x, y} 플로팅 버튼
  const [modalText, setModalText] = useState(null)

  useEffect(() => {
    function onMouseUp(e) {
      if (modalText) return                   // 모달 열려있으면 무시
      if (e.target?.closest?.('[data-sign-trigger]')) return  // 버튼 클릭은 제외
      const selection = window.getSelection()
      const text = selection ? selection.toString().trim() : ''
      if (text && text.length >= 2 && text.length <= 200 && hasKorean(text)) {
        try {
          const rect = selection.getRangeAt(0).getBoundingClientRect()
          setHint({ text, x: rect.left + rect.width / 2, y: rect.top })
          return
        } catch { /* fallthrough */ }
      }
      setHint(null)
    }
    document.addEventListener('mouseup', onMouseUp)
    return () => document.removeEventListener('mouseup', onMouseUp)
  }, [modalText])

  const openModal = useCallback(() => {
    if (hint) { setModalText(hint.text); setHint(null) }
  }, [hint])

  return (
    <>
      {hint && (
        <button
          data-sign-trigger
          onMouseDown={(e) => e.preventDefault()}   // 선택 유지
          onClick={openModal}
          style={{ position: 'fixed', left: hint.x, top: Math.max(8, hint.y - 46), transform: 'translateX(-50%)', zIndex: 60 }}
          className="px-3 py-1.5 rounded-full bg-primary-600 text-white text-sm font-semibold shadow-lg hover:bg-primary-700 whitespace-nowrap"
        >
          🤟 수어로 보기
        </button>
      )}

      {modalText && (
        <div className="fixed inset-0 z-50 bg-black/40 flex justify-end" onClick={() => setModalText(null)}>
          <div
            className="w-full max-w-2xl h-full bg-white shadow-2xl overflow-y-auto animate-[slideIn_.2s_ease]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b border-gray-200 px-5 py-3 flex items-center justify-between">
              <div className="min-w-0">
                <p className="text-xs text-gray-400">이 문장을 수어로</p>
                <p className="font-bold text-gray-900 truncate">{modalText}</p>
              </div>
              <button
                onClick={() => setModalText(null)}
                className="ml-3 shrink-0 px-3 py-1.5 text-sm text-gray-500 hover:text-gray-900 border border-gray-200 rounded-lg"
              >
                닫기 ✕
              </button>
            </div>
            <div className="p-5">
              <Suspense fallback={<div className="py-14 text-center text-gray-500 text-sm">불러오는 중…</div>}>
                <SignPanel text={modalText} />
              </Suspense>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
