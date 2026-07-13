import { useState, useEffect, useCallback, lazy, Suspense } from 'react'

// SignPanel(→수어 영상, 무거움)은 모달을 열 때만 로드 → 초기 번들에 안 실림.
const SignPanel = lazy(() => import('./SignPanel'))

const hasKorean = (s) => /[가-힣]/.test(s)
const INTRO_KEY = 'liplab_sign_intro_seen'   // 첫 접속 사용법 팝업 1회 표시용

/**
 * 전역 텍스트 선택 → 수어 번역.
 * 앱 어느 화면에서든 한국어 문장을 드래그하면 근처에 "수어로 보기" 버튼이 뜨고,
 * 누르면 그 자리에서 슬라이드오버로 수어를 보여준다(수어 탭으로 이동 불필요).
 * App 루트에 1회 마운트. 리스너/버튼은 가볍고, 무거운 SignPanel은 지연로딩.
 */
export default function SignSelectionOverlay() {
  const [hint, setHint] = useState(null)     // {text, x, y} 플로팅 버튼
  const [modalText, setModalText] = useState(null)
  const [showIntro, setShowIntro] = useState(false)   // 첫 접속 사용법 팝업

  useEffect(() => {
    try { if (!localStorage.getItem(INTRO_KEY)) setShowIntro(true) } catch { /* noop */ }
  }, [])

  const dismissIntro = () => {
    setShowIntro(false)
    try { localStorage.setItem(INTRO_KEY, '1') } catch { /* noop */ }
  }

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

      {/* 첫 접속 — 수어 번역 사용법 안내(드래그 제스처가 숨어 있어 처음엔 모름) */}
      {showIntro && (
        <div className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4" onClick={dismissIntro}>
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="text-center mb-4">
              <div className="text-4xl mb-2">🤟</div>
              <h3 className="text-lg font-bold text-gray-900">수어 번역, 이렇게 써요</h3>
              <p className="text-sm text-gray-500 mt-1">어느 화면에서든 문장을 수어로 바꿔볼 수 있어요.</p>
            </div>

            {/* 미니 시연 */}
            <div className="relative bg-gray-50 border border-gray-100 rounded-xl px-4 pt-5 pb-4 mb-4">
              <p className="text-sm text-gray-700 leading-relaxed">
                오늘 날씨가 <span className="bg-primary-200/80 rounded px-0.5">참 좋네요</span>
              </p>
              <span className="absolute right-4 top-1 px-2.5 py-1 rounded-full bg-primary-600 text-white text-xs font-semibold shadow">🤟 수어로 보기</span>
            </div>

            <ol className="space-y-2.5 mb-5">
              {[
                ['1', '한국어 문장을 마우스로 드래그해 선택 (터치 기기는 길게 눌러 선택)'],
                ['2', '위에 뜨는 "🤟 수어로 보기" 버튼을 누르기'],
                ['3', '그 자리에서 바로 수어 영상으로 확인'],
              ].map(([n, t]) => (
                <li key={n} className="flex gap-2.5 items-start">
                  <span className="shrink-0 w-5 h-5 rounded-full bg-primary-100 text-primary-700 text-xs font-bold flex items-center justify-center mt-0.5">{n}</span>
                  <span className="text-sm text-gray-600">{t}</span>
                </li>
              ))}
            </ol>

            <button onClick={dismissIntro}
              className="w-full py-2.5 rounded-xl bg-primary-600 text-white font-semibold hover:bg-primary-700 transition-colors">
              알겠어요
            </button>
          </div>
        </div>
      )}
    </>
  )
}
