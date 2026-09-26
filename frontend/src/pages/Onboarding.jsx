import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'

/**
 * 온보딩 — 자가진단 안내 (Figma 84:7 / 모바일 243:65, lg 미만 반응형).
 * 트랙 선택 화면 대신, 자가진단(배치검사)으로 바로 갈지 나중에 할지만 고르는 화면.
 * - 시작하기: 배치검사로 이동. 결과에서 '학습하러 가기'를 누르면 추천 시작 단계로 배치된다(Placement).
 * - 나중에 할게요: 기본 트랙(독화=perception)으로 배치(setTrack)한 뒤 학습 경로로 간다.
 *   배치(placed) 전에는 /api/curriculum/stages가 1단계를 잠김으로 돌려준다.
 * 온보딩을 마쳤는지는 서버의 배치 여부(placed)로 판단한다(App.jsx HomeRedirect). 예전에는 브라우저 전체에 하나인
 * localStorage 표시를 남겨, 공용 기기의 다음 사람이 온보딩을 건너뛰었다. 발화 경로는 학습 탭의 트랙 전환(?track=speak)으로 연다.
 */
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
// 버튼 — 데스크톱 75:23(btn-lg), lg 미만 243:77(r14·b5, py16, 16px)
const BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

export default function Onboarding() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const goPlacement = () => navigate('/learn/placement')
  const startLater = async () => {
    setBusy(true)
    try { await curriculumAPI.setTrack('perception') } catch { /* 실패해도 이동 */ }
    navigate('/learn/path')
  }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-page px-[34px] py-8 lg:px-4">
      <div className="flex w-full max-w-[420px] flex-col items-center gap-[22px] lg:gap-[28px]">
        {/* 마스코트 132 / lg 150 (84:8 · 243:67) */}
        <span className="relative size-[132px] shrink-0 lg:size-[150px]">
          <img src="/ui/lp-84-7-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
        </span>

        {/* 제목 (부제 없음) */}
        <h1 className="text-center text-[26px] font-bold leading-figma tracking-[-0.65px] text-ink lg:text-[38px] lg:tracking-[-0.95px]">
          어디서부터 시작할까요?
        </h1>

        {/* 액션 버튼 */}
        <div className="flex w-full flex-col gap-2.5 lg:gap-3">
          <button type="button" onClick={goPlacement} disabled={busy} className={`btn-primary btn-lg ${BTN}`}>
            시작하기
          </button>
          <button type="button" onClick={startLater} disabled={busy} className={`btn-secondary btn-lg text-track ${BTN}`}>
            나중에 할게요
          </button>
        </div>
      </div>
    </div>
  )
}
