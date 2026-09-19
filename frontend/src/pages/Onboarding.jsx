import { useNavigate } from 'react-router-dom'

/**
 * 온보딩 시작 (Figma 리디자인 01 / 1. 설문 안내) — 첫 방문 환영 화면.
 * 자동 데모 로그인 뒤 처음 들어온 사용자에게 한 번 보이고, 자가진단(배치검사)으로 안내한다.
 * '나중에 하기'는 바로 학습 홈으로. 표시 여부는 localStorage로 1회 제어.
 */
export default function Onboarding() {
  const navigate = useNavigate()
  const done = (to) => {
    try { localStorage.setItem('liplab_onboarded', '1') } catch { /* 무시 */ }
    navigate(to)
  }
  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-[420px] rounded-[24px] border border-line bg-white p-8 text-center">
        <img src="/ui/mascot.svg" alt="" className="mx-auto h-24 w-24" />
        <h1 className="mt-4 text-[26px] font-bold tracking-[-0.5px] text-ink">어디서부터 시작할까요?</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
          몇 가지만 여쭤볼게요. 답해주시면 딱 맞는 단계를 찾아드려요.
        </p>
        <button type="button" onClick={() => done('/learn/placement')}
          className="btn-primary mt-6 w-full !py-4 text-[18px]">
          자가진단 시작하기
        </button>
        <button type="button" onClick={() => done('/learn/path')}
          className="mt-2 w-full rounded-2xl py-3 text-[14px] font-bold text-ink-muted hover:bg-gray-50">
          나중에 하기
        </button>
      </div>
    </div>
  )
}
