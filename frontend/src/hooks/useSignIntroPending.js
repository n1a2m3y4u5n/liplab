import { useEffect, useState } from 'react'

export const SIGN_INTRO_CLOSED = 'liplab:sign-intro-closed'

export default function useSignIntroPending() {
  const [pending, setPending] = useState(() => {
    try { return !localStorage.getItem('liplab_sign_intro_seen') } catch { return true }
  })
  useEffect(() => {
    const closed = () => setPending(false)
    window.addEventListener(SIGN_INTRO_CLOSED, closed)
    return () => window.removeEventListener(SIGN_INTRO_CLOSED, closed)
  }, [])
  return pending
}
