import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { authAPI, seedAPI } from '../api'

/**
 * 로그인 · 회원가입 (Figma "Auth" 리디자인 227:35 / 227:74) — 좌: 보라 그라데이션
 * 브랜드 패널, 우: 폼. 로그인/회원가입 전환 + '둘러보기(데모)' 즉시 입장. 미인증 진입점.
 */
export default function Login() {
  const navigate = useNavigate()
  const setAuth = useStore((s) => s.setAuth)
  const [mode, setMode] = useState('login')  // login | signup
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [agree, setAgree] = useState(false)
  const [guardianOk, setGuardianOk] = useState(false)  // 만 14세 미만 보호자 동의(§4.9 미성년 보호)
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
        : await authAPI.register(email, username || email.split('@')[0], password,
            { agree_terms: agree, age_confirmed: guardianOk })
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
  const toggle = () => {
    setErr(''); setAgree(false)
    setMode(mode === 'login' ? 'signup' : 'login')
  }

  return (
    <div className="flex min-h-[100dvh] bg-white">
      {/* 좌: 브랜드 패널 (Figma "Brand panel" 560px, 126deg 그라데이션) */}
      <div className="relative hidden w-1/2 max-w-[560px] shrink-0 overflow-hidden lg:block"
        style={{ backgroundImage: 'linear-gradient(126deg, #a78bfa 0%, #6d3fc4 71.4%)' }}>
        {/* Blob 1 / Blob 2 — 흰 반투명 원 */}
        <div className="absolute -left-[130px] -top-[110px] h-[420px] w-[420px] rounded-full bg-white/10" />
        <div className="absolute left-[420px] top-[780px] h-[320px] w-[320px] rounded-full bg-white/[0.08]" />
        <div className="relative flex h-full flex-col items-center justify-center gap-[26px] px-10 text-center">
          {/* Halo 176px + Mascot 126px */}
          <span className="flex h-[176px] w-[176px] items-center justify-center rounded-full bg-white/[0.16]">
            <img src="/ui/mascot.svg" alt="" className="h-[126px] w-[126px]" />
          </span>
          <p className="text-[30px] font-bold leading-[1.5] tracking-[-0.6px] text-white">
            입모양이 보이기<br />시작하는 순간까지
          </p>
        </div>
      </div>

      {/* 우: 폼 (Figma "Form" 420px, gap 18px) */}
      <div className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="flex w-full max-w-[420px] flex-col gap-[18px]">
          {/* 모바일: 중앙 마스코트 + 로고 (좌측 패널이 숨겨질 때) */}
          <div className="flex flex-col items-center gap-2.5 lg:hidden">
            <span className="flex h-[76px] w-[76px] items-center justify-center rounded-[26px] bg-primary-100">
              <img src="/ui/mascot.svg" alt="" className="h-11 w-11" />
            </span>
            <span className="font-display text-[28px] leading-none tracking-[-1.4px] text-primary-500">LIPLAB</span>
          </div>
          {/* 데스크톱: 좌상단 로고 (Figma "Logo" — 보라 원 아이콘 + Rowdies LIPLAB) */}
          <div className="hidden items-center gap-2 lg:flex">
            <img src="/ui/logo.png" alt="" className="h-[28px] w-[28px] object-contain" />
            <span className="font-display text-[28px] leading-none tracking-[-1.4px] text-primary-500">LIPLAB</span>
          </div>

          <h1 className="text-center text-[30px] font-bold tracking-[-0.75px] text-ink lg:text-left">
            {mode === 'login' ? '오늘도 학습을 시작해볼까요?' : '학습할 준비 되셨나요?'}
          </h1>

          <form onSubmit={submit} className="flex flex-col gap-[18px]">
            <label className="flex flex-col gap-[7px]">
              <span className="text-[13px] font-bold text-ink-muted">이메일</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" placeholder="you@example.com" />
            </label>

            {mode === 'signup' && (
              <label className="flex flex-col gap-[7px]">
                <span className="text-[13px] font-bold text-ink-muted">사용자명</span>
                <input value={username} onChange={(e) => setUsername(e.target.value)} className="input-field" placeholder="2~50자로 입력해주세요" />
              </label>
            )}

            <label className="flex flex-col gap-[7px]">
              <span className="text-[13px] font-bold text-ink-muted">비밀번호</span>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="input-field" placeholder="••••••••" />
              {mode === 'signup' && (
                <span className="text-[12px] text-[#a8a8b8]">6자 이상 입력해주세요</span>
              )}
            </label>

            {mode === 'login' && (
              <div className="flex justify-end">
                <span className="text-[13px] font-bold text-primary-500">비밀번호를 잊으셨나요?</span>
              </div>
            )}

            {mode === 'signup' && (
              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-2.5">
                  <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)}
                    className="h-5 w-5 shrink-0 rounded-[6px] border-2 border-line accent-primary-500" />
                  <span className="text-[13.5px] text-ink-muted">
                    <a href="/terms" target="_blank" rel="noreferrer" className="font-bold text-primary-500 hover:underline">이용약관</a>
                    {' 및 '}
                    <a href="/privacy" target="_blank" rel="noreferrer" className="font-bold text-primary-500 hover:underline">개인정보 처리방침</a>
                    에 동의해요
                  </span>
                </label>
                <label className="flex items-center gap-2.5">
                  <input type="checkbox" checked={guardianOk} onChange={(e) => setGuardianOk(e.target.checked)}
                    className="h-5 w-5 shrink-0 rounded-[6px] border-2 border-line accent-primary-500" />
                  <span className="text-[13.5px] text-ink-muted">만 14세 이상이거나 보호자 동의를 받았어요</span>
                </label>
              </div>
            )}

            {err && <p className="text-[13px] font-bold text-rose-500">{err}</p>}

            <button type="submit" disabled={busy || (mode === 'signup' && (!agree || !guardianOk))} className="btn-primary w-full !py-[17px] text-[17px]">
              {busy ? '…' : mode === 'login' ? '로그인' : '회원가입'}
            </button>
          </form>

          {mode === 'login' && (
            <button type="button" onClick={demo} disabled={busy} className="btn-secondary w-full !py-[17px] text-[17px]">
              둘러보기 (데모)
            </button>
          )}

          <p className="flex justify-center gap-1.5 text-[14px] text-ink-muted">
            {mode === 'login' ? '아직 계정이 없으신가요?' : '이미 계정이 있으신가요?'}
            <button type="button" onClick={toggle} className="font-bold text-primary-500 hover:underline">
              {mode === 'login' ? '회원가입' : '로그인'}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
