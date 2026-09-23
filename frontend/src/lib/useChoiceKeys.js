import { useEffect, useRef } from 'react'

/**
 * 보기 숫자 키 선택 — 독화 레슨 공통 템플릿(§4-03 "보기는 클릭 또는 숫자 키 1~4").
 * 1~n 키를 누르면 onPick(options[k-1], k-1)을 부른다. enabled=false(채점 중·결과 표시 중)면 무시.
 * 입력칸에 타이핑 중이거나 조합키(⌘·Ctrl·Alt)를 누른 경우는 건드리지 않는다.
 */
export default function useChoiceKeys(options, onPick, enabled = true) {
  const pickRef = useRef(onPick)
  useEffect(() => { pickRef.current = onPick })   // 매 렌더 최신 콜백(리스너는 다시 달지 않는다)
  const count = options?.length || 0

  useEffect(() => {
    if (!enabled || !count) return undefined
    const onKey = (e) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return
      const t = e.target
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return
      const k = Number(e.key)
      if (!Number.isInteger(k) || k < 1 || k > count) return
      e.preventDefault()
      pickRef.current?.(options[k - 1], k - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [options, count, enabled])
}
