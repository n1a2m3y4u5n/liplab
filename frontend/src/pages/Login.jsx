import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { authAPI, seedAPI } from '../api'
import Logo from '../components/Logo'

/**
 * 로그인 · 회원가입 (Figma 227:35 / 227:74, 모바일 243:34 / 244:34 — lg 미만 반응형).
 * 데스크톱: 좌 보라 그라데이션 브랜드 패널 + 우 폼. 모바일: 폼만(로그인은 위에 Halo+마스코트).
 * 로그인/회원가입 전환 + '둘러보기(데모)' 즉시 입장. 미인증 진입점(App.jsx AuthGate가 라우트 없이 렌더).
 * 회원가입의 약관·처리방침 링크와 만 14세 확인 줄은 법적 요건(§4.9)으로 Figma보다 한 줄 많다.
 */
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)

// 입력칸(227:59 54px·15.5px / 모바일 243:52 50px·15px) — 전역 .input-field 위에 이 화면 값만 덮는다.
const INPUT = 'input-field h-[50px] rounded-13 bg-white px-[14px] py-0 text-[15px] placeholder:text-placeholder lg:h-[54px] lg:px-[15px] lg:text-[15.5px]'
const LABEL = 'text-[12.5px] font-bold leading-figma text-ink-muted lg:text-[13px]'
// 주 버튼(227:67 r15·py17·17px / 모바일 243:58 r14·py16·16px)
const BTN = 'w-full py-4 text-[16px] lg:rounded-15 lg:py-[17px] lg:text-[17px]'

// 서버 오류 → 한국어 안내. FastAPI 422는 detail이 배열({loc, msg})이라 그대로 렌더하면 React가 깨진다.
const AUTH_ERR = {
  'Incorrect email or password': '이메일·비밀번호를 확인해 주세요.',
  'Email already registered': '이미 가입된 이메일이에요.',
  'Username already taken': '이미 쓰고 있는 사용자명이에요.',
}
function authErrorMessage(detail, mode) {
  if (typeof detail === 'string') return AUTH_ERR[detail] || detail
  if (Array.isArray(detail)) {
    const field = detail.map((d) => (Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null)).find(Boolean)
    if (field === 'password') return '비밀번호는 6자 이상 입력해주세요.'
    if (field === 'username') return '사용자명은 2~50자로 입력해주세요.'
    if (field === 'email') return '이메일 형식을 확인해 주세요.'
  }
  return mode === 'login' ? '이메일·비밀번호를 확인해 주세요.' : '가입에 실패했어요.'
}

// lg(1024px) 이상인지 — 비밀번호 placeholder가 데스크톱(227:107)과 모바일(244:52)에서 다르다.
function useIsDesktop() {
  const query = '(min-width: 1024px)'
  const [ok, setOk] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const sync = () => setOk(m.matches)
    sync()
    m.addEventListener('change', sync)
    return () => m.removeEventListener('change', sync)
  }, [])
  return ok
}

// 동의 체크(227:109 20px / 모바일 244:55 19px) — 네이티브 체크박스는 화면에서 숨기고(키보드·낭독기용으로 유지)
// 그 옆에 Figma 모양을 그린다. 켜짐은 Figma 'Checkbox / on'(318:33) 에셋.
function AgreeCheck({ checked, onChange, children }) {
  return (
    <label className="flex cursor-pointer items-center gap-[9px] lg:gap-2.5">
      <input type="checkbox" checked={checked} onChange={onChange} className="peer sr-only" />
      <span aria-hidden className="flex size-[19px] shrink-0 rounded-md peer-focus-visible:ring-2 peer-focus-visible:ring-primary-300 peer-focus-visible:ring-offset-1 lg:size-5">
        {checked
          ? <img src="/ui/lp-318-33-checkbox-on.svg" alt="" className="size-full" />
          : <span className="size-full rounded-md border-2 border-line bg-white" />}
      </span>
      <span className="text-[12.5px] leading-figma text-ink-muted lg:text-[13.5px]">{children}</span>
    </label>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const setAuth = useStore((s) => s.setAuth)
  const isDesktop = useIsDesktop()
  const [mode, setMode] = useState('login')  // login | signup
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [agree, setAgree] = useState(false)
  const [guardianOk, setGuardianOk] = useState(false)  // 만 14세 미만 보호자 동의(§4.9 미성년 보호)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const signup = mode === 'signup'

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
      setErr(authErrorMessage(e2?.response?.data?.detail, mode))
    } finally { setBusy(false) }
  }
  const demo = async () => {
    setBusy(true); setErr('')
    try { await enter(await authAPI.demoLogin()) }
    catch { setErr('데모 입장에 실패했어요.') } finally { setBusy(false) }
  }
  const toggle = () => {
    setErr(''); setAgree(false); setGuardianOk(false)
    setMode(mode === 'login' ? 'signup' : 'login')
  }

  return (
    <div className="flex min-h-[100dvh] bg-white">
      {/* 좌: 브랜드 패널 (Figma "Brand panel" 560px, 126deg 그라데이션) */}
      <div className="relative hidden w-1/2 max-w-[560px] shrink-0 overflow-hidden lg:block"
        style={{ backgroundImage: 'linear-gradient(126deg, var(--brand-light) 0%, var(--brand-hover) 71.4%)' }}>
        {/* Blob 1 / Blob 2 — 흰 반투명 원(227:37 · 227:38) */}
        <div className="absolute -left-[130px] -top-[110px] h-[420px] w-[420px] rounded-full bg-white/10" />
        <div className="absolute left-[420px] top-[780px] h-[320px] w-[320px] rounded-full bg-white/[0.08]" />
        <div className="relative flex h-full flex-col items-center justify-center gap-[26px] px-10 text-center">
          {/* Halo 176 + Mascot 126(227:40 · 227:41 — 슬롯 126, 그림자 여백만큼 넘친다) */}
          <span className="relative size-[176px] shrink-0 rounded-full bg-white/[0.16]">
            <span className="absolute left-[25px] top-[25px] size-[126px]">
              <img src="/ui/lp-227-35-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
            </span>
          </span>
          <p className="text-[30px] font-bold leading-[1.5] tracking-[-0.6px] text-white">
            입모양이 보이기<br />시작하는 순간까지
          </p>
        </div>
      </div>

      {/* 우: 폼 (Figma "Form" 420px, gap 18 / 모바일 322px, gap 16·15) */}
      <div className="flex flex-1 items-center justify-center px-[34px] py-10 lg:px-6">
        <div className={`flex w-full max-w-[420px] flex-col items-center lg:items-stretch lg:gap-[18px] ${signup ? 'gap-[15px]' : 'gap-4'}`}>
          {/* 모바일 로그인: Halo 108 + 마스코트 80(243:36). 회원가입(244:34)에는 없다. */}
          {!signup && (
            <span className="relative size-[108px] shrink-0 rounded-full bg-primary-100 lg:hidden">
              <span className="absolute left-[14px] top-[14px] size-20">
                <img src="/ui/lp-84-7-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
              </span>
            </span>
          )}
          {/* 로고(모바일 243:44 24px / 데스크톱 227:51 28px) */}
          <Logo size={24} className="lg:hidden" />
          <Logo size={28} className="hidden lg:inline-block" />

          <h1 className="text-center text-[24px] font-bold leading-figma tracking-[-0.6px] text-ink lg:text-left lg:text-[30px] lg:tracking-[-0.75px]">
            {signup ? '학습할 준비 되셨나요?' : (
              <>
                <span className="lg:hidden">다시 만나서 반가워요</span>
                <span className="hidden lg:inline">오늘도 학습을 시작해볼까요?</span>
              </>
            )}
          </h1>

          <form onSubmit={submit} className={`flex w-full flex-col lg:gap-[18px] ${signup ? 'gap-[15px]' : 'gap-4'}`}>
            <label className="flex flex-col gap-1.5 lg:gap-[7px]">
              <span className={LABEL}>이메일</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} placeholder="you@example.com" />
            </label>

            {signup && (
              <label className="flex flex-col gap-1.5 lg:gap-[7px]">
                <span className={LABEL}>사용자명</span>
                <input value={username} onChange={(e) => setUsername(e.target.value)} minLength={2} maxLength={50} className={INPUT} placeholder="2~50자로 입력해주세요" />
              </label>
            )}

            <label className="flex flex-col gap-1.5 lg:gap-[7px]">
              <span className={LABEL}>비밀번호</span>
              <input type="password" required minLength={signup ? 6 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} className={INPUT}
                placeholder={signup && isDesktop ? '6자 이상 입력해주세요.' : '••••••••'} />
              {/* 모바일 회원가입만 아래 도움말(244:54) — 데스크톱은 placeholder로 안내(227:107) */}
              {signup && (
                <span className="text-[11.5px] leading-figma text-ink-ghost lg:hidden">6자 이상 입력해주세요</span>
              )}
            </label>

            {/* 비밀번호 찾기(227:65) — 데스크톱에만 있다(모바일 243:34에는 없음). 재설정 화면·API는 아직 없다. */}
            {!signup && (
              <div className="hidden justify-end lg:flex">
                <span className="text-[13px] font-bold leading-figma text-primary-500">비밀번호를 잊으셨나요?</span>
              </div>
            )}

            {signup && (
              <div className="flex flex-col gap-2">
                <AgreeCheck checked={agree} onChange={(e) => setAgree(e.target.checked)}>
                  <a href="/terms" target="_blank" rel="noreferrer" className="font-bold text-primary-500 hover:underline">이용약관</a>
                  {' 및 '}
                  <a href="/privacy" target="_blank" rel="noreferrer" className="font-bold text-primary-500 hover:underline">개인정보 처리방침</a>
                  에 동의해요
                </AgreeCheck>
                <AgreeCheck checked={guardianOk} onChange={(e) => setGuardianOk(e.target.checked)}>
                  만 14세 이상이거나 보호자 동의를 받았어요
                </AgreeCheck>
              </div>
            )}

            {err && <p role="alert" className="text-[13px] font-bold text-bad-text">{err}</p>}

            <button type="submit" disabled={busy || (signup && (!agree || !guardianOk))} className={`btn-primary ${BTN}`}>
              {busy ? '…' : signup ? '회원가입' : '로그인'}
            </button>
          </form>

          {!signup && (
            <button type="button" onClick={demo} disabled={busy} className={`btn-secondary text-track ${BTN}`}>
              둘러보기 (데모)
            </button>
          )}

          <p className="flex justify-center gap-[5px] text-[13px] leading-figma text-ink-muted lg:gap-1.5 lg:text-[14px]">
            {signup ? '이미 계정이 있으신가요?' : '아직 계정이 없으신가요?'}
            <button type="button" onClick={toggle} className="font-bold text-primary-500 hover:underline">
              {signup ? '로그인' : '회원가입'}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
