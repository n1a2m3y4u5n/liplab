import { useEffect, useState } from 'react'

export const SIGN_INTRO_CLOSED = 'liplab:sign-intro-closed'

export default function useSignIntroPending() {
  const [pending, setPending] = useState(() => {
    try { return !localStorage.getItem('liplab_sign_intro_seen') } catch { return true }
  })
  useEffect(() => {
    const closed = () => setPending(false)
    window.addEventListener(SIGN_INTRO_CLOSED, closed)
    // 첫 안내를 닫은 이벤트가 이 effect보다 먼저 올 수 있다(지연 로딩).
    try { if (localStorage.getItem('liplab_sign_intro_seen')) closed() } catch {}
    return () => window.removeEventListener(SIGN_INTRO_CLOSED, closed)
  }, [])
  return pending
}
