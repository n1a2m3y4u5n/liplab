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
 *
 * @param {boolean} active - 모달이 열려 있는지
 * @param {() => void} onEscape - Esc 또는 닫기 시 호출
 */
export default function useFocusTrap(active, onEscape) {
  const ref = useRef(null)
  const prevFocus = useRef(null)

  useEffect(() => {
    if (!active) return undefined
    const node = ref.current
    prevFocus.current = document.activeElement
    const list = () => Array.from(node ? node.querySelectorAll(FOCUSABLE) : [])
    // 첫 포커스를 모달 안으로
    ;(list()[0] || node)?.focus?.()

    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onEscape?.()
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
  }, [active, onEscape])

  return ref
}
