import { useNavigate } from 'react-router-dom'

/**
 * 온보딩 — 자가진단 안내 (Figma 84:7).
 * 트랙 선택 없이, 자가진단(배치검사)으로 바로 갈지 나중에 할지만 고르는 정적 화면.
 * 두 버튼 모두 온보딩 완료(localStorage)를 마킹한 뒤 각 목적지로 이동한다.
 */
export default function Onboarding() {
  const navigate = useNavigate()
  const mark = () => { try { localStorage.setItem('liplab_onboarded', '1') } catch { /* 무시 */ } }
  const go = (route) => { mark(); navigate(route) }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[#f3f3f3] px-4 py-8">
      <div className="flex w-full max-w-[420px] flex-col items-center gap-[28px]">
        {/* 마스코트 (Figma 84:7) */}
        <img src="/ui/lp-84-7-mascot.svg" alt="" className="h-[150px] w-[150px]" />

        {/* 제목 (부제 없음) */}
        <h1 className="text-center text-[38px] font-bold leading-tight tracking-[-0.95px] text-[#1a1a2e]">
          어디서부터 시작할까요?
        </h1>

        {/* 액션 버튼 */}
        <div className="flex w-full flex-col gap-3">
          <button type="button" onClick={() => go('/learn/placement')}
            className="w-full rounded-[16px] border-2 border-b-[6px] border-[#5f3ab8] bg-[#7d53de] px-8 py-[18px] text-[20px] font-bold tracking-[-0.2px] text-white">
            시작하기
          </button>
          <button type="button" onClick={() => go('/learn/path')}
            className="w-full rounded-[16px] border-2 border-b-[6px] border-[#e2e2e8] bg-white px-8 py-[18px] text-[20px] font-bold text-[#7d53de]">
            나중에 할게요
          </button>
        </div>
      </div>
    </div>
  )
}
