import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { authAPI, seedAPI } from '../api'

/**
 * 로그인 · 회원가입 (Figma 리디자인 00) — 좌: 보라 그라데이션 브랜드 패널, 우: 폼.
 * 로그인/회원가입 전환 + '둘러보기(데모)' 즉시 입장. 미인증 진입점.
 */
export default function Login() {
  const navigate = useNavigate()
  const setAuth = useStore((s) => s.setAuth)
  const [mode, setMode] = useState('login')  // login | signup
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const enter = async (data) => {
    setAuth(data.user, data.access_token)
    try { await seedAPI.seedDemo() } catch { /* 무시 */ }
    navigate('/')
  }
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const data = mode === 'login'
        ? await authAPI.login(email, password)
        : await authAPI.register(email, username || email.split('@')[0], password)
      await enter(data)
    } catch (e2) {
      setErr(e2?.response?.data?.detail || (mode === 'login' ? '이메일·비밀번호를 확인해 주세요.' : '가입에 실패했어요.'))
    } finally { setBusy(false) }
  }
  const demo = async () => {
    setBusy(true); setErr('')
    try { await enter(await authAPI.demoLogin()) }
    catch { setErr('데모 입장에 실패했어요.') } finally { setBusy(false) }
  }

  return (
    <div className="flex min-h-[100dvh] bg-white">
      {/* 좌: 브랜드 패널 */}
      <div className="relative hidden w-1/2 max-w-[560px] shrink-0 overflow-hidden lg:block"
        style={{ backgroundImage: 'linear-gradient(160deg, #a78bfa 0%, #7d53de 72%)' }}>
        <div className="absolute -left-16 top-24 h-64 w-64 rounded-full bg-white/10" />
        <div className="absolute -right-10 bottom-16 h-72 w-72 rounded-full bg-white/10" />
        <div className="relative flex h-full flex-col items-center justify-center gap-6 px-10 text-center">
          <span className="flex h-28 w-28 items-center justify-center rounded-[32px] bg-white/25 shadow-xl">
            <img src="/ui/mascot.svg" alt="" className="h-16 w-16" />
          </span>
          <p className="text-[26px] font-bold leading-snug tracking-[-0.5px] text-white">입모양이 보이기<br />시작하는 순간까지</p>
        </div>
      </div>

      {/* 우: 폼 */}
      <div className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="w-full max-w-[380px]">
          {/* 모바일: 중앙 마스코트 + 로고 (좌측 패널이 숨겨질 때) */}
          <div className="mb-6 flex flex-col items-center gap-2.5 lg:hidden">
            <span className="flex h-[76px] w-[76px] items-center justify-center rounded-[26px] bg-primary-100">
              <img src="/ui/mascot.svg" alt="" className="h-11 w-11" />
            </span>
            <span className="font-display text-[26px] leading-none tracking-[-1px] text-primary-500">LIPLAB</span>
          </div>
          {/* 데스크톱: 좌상단 로고 */}
          <div className="mb-8 hidden items-center gap-2 lg:flex">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100">
              <img src="/ui/mascot.svg" alt="" className="h-6 w-6" />
            </span>
            <span className="font-display text-[26px] leading-none tracking-[-1px] text-primary-500">LIPLAB</span>
          </div>
          <h1 className="text-center text-[24px] font-bold tracking-[-0.5px] text-ink lg:text-left">
            {mode === 'login' ? '다시 만나서 반가워요' : '지금 시작해볼까요?'}
          </h1>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-[13px] font-bold text-ink-muted">이메일</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" placeholder="you@example.com" />
            </label>
            {mode === 'signup' && (
              <label className="block">
                <span className="mb-1.5 block text-[13px] font-bold text-ink-muted">이름</span>
                <input value={username} onChange={(e) => setUsername(e.target.value)} className="input-field" placeholder="이름 (선택)" />
              </label>
            )}
            <label className="block">
              <span className="mb-1.5 block text-[13px] font-bold text-ink-muted">비밀번호</span>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="input-field" placeholder="••••••••" />
            </label>
            {err && <p className="text-[13px] font-bold text-rose-500">{err}</p>}
            <button type="submit" disabled={busy} className="btn-primary w-full !py-3.5 text-[17px]">
              {busy ? '…' : mode === 'login' ? '로그인' : '회원가입'}
            </button>
          </form>

          <button type="button" onClick={demo} disabled={busy} className="btn-secondary mt-2 w-full !py-3.5 text-[16px]">
            둘러보기 (데모)
          </button>

          <p className="mt-5 text-center text-[13px] text-ink-muted">
            {mode === 'login' ? '아직 계정이 없으신가요? ' : '이미 계정이 있으신가요? '}
            <button type="button" onClick={() => { setErr(''); setMode(mode === 'login' ? 'signup' : 'login') }}
              className="font-bold text-primary-500 hover:underline">
              {mode === 'login' ? '회원가입' : '로그인'}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
