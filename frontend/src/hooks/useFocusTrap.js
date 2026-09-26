import { useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
  'input:not([disabled])', 'select:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(', ')

/**
 * 모달 접근성 훅 — 열린 동안 포커스를 모달 안에 가두고(Tab 순환), Esc로 닫고,
 * 닫히면 직전에 포커스였던 요소로 되돌린다. 반환한 ref를 모달 '패널' 요소에 붙인다.
 *
 * 기존 모달 마크업을 바꾸지 않고 접근성만 더하기 위한 최소 구현. keydown을 캡처 단계로
 * 잡아 Esc가 모달을 먼저 닫도록 한다.
 * onEscape는 ref로 들고 있어 부모가 렌더마다 새 함수(onClose={() => ...})를 넘겨도 효과가 다시 돌지 않는다
 * (다시 돌면 포커스가 모달 밖으로 복원됐다가 첫 요소로 튀어, 입력 중인 칸에서 포커스가 빠진다).
 * 화면에 그려지지 않은 요소(반응형으로 display:none인 데스크톱·모바일 사본)는 순환 대상에서 뺀다.
 *
 * @param {boolean} active - 모달이 열려 있는지
 * @param {() => void} onEscape - Esc 또는 닫기 시 호출
 */
export default function useFocusTrap(active, onEscape) {
  const ref = useRef(null)
  const prevFocus = useRef(null)
  const escRef = useRef(onEscape)

  useEffect(() => { escRef.current = onEscape }, [onEscape])

  useEffect(() => {
    if (!active) return undefined
    const node = ref.current
    prevFocus.current = document.activeElement
    const list = () => Array.from(node ? node.querySelectorAll(FOCUSABLE) : [])
      .filter((el) => el.getClientRects().length > 0)
    // 첫 포커스를 모달 안으로
    ;(list()[0] || node)?.focus?.()

    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        escRef.current?.()
        return
      }
      if (e.key !== 'Tab') return
      const f = list()
      if (f.length === 0) { e.preventDefault(); node?.focus?.(); return }
      const first = f[0]
      const last = f[f.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('keydown', onKey, true)
      prevFocus.current?.focus?.()   // 포커스 복원
    }
  }, [active])

  return ref
}
