import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'

/**
 * 온보딩 — 자가진단 안내 (Figma 84:7).
 * 트랙 선택 화면 대신, 자가진단(배치검사)으로 바로 갈지 나중에 할지만 고르는 화면.
 * - 시작하기: 배치검사로 이동. 결과에서 '학습하러 가기'를 누르면 추천 시작 단계로 배치된다(Placement).
 * - 나중에 할게요: 기본 트랙(독화=perception)으로 배치(setTrack)한 뒤 학습 경로로 간다.
 *   배치(placed) 전에는 /api/curriculum/stages가 1단계를 잠김으로 돌려준다.
 * 두 버튼 모두 온보딩 완료(localStorage)를 마킹한다. 발화 경로는 학습 탭의 트랙 전환(?track=speak)으로 연다.
 */
export default function Onboarding() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const mark = () => { try { localStorage.setItem('liplab_onboarded', '1') } catch { /* 무시 */ } }
  const goPlacement = () => { mark(); navigate('/learn/placement') }
  const startLater = async () => {
    setBusy(true)
    try { await curriculumAPI.setTrack('perception') } catch { /* 실패해도 이동 */ }
    mark()
    navigate('/learn/path')
  }

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
          <button type="button" onClick={goPlacement} disabled={busy}
            className="w-full rounded-[16px] border-2 border-b-[6px] border-[#5f3ab8] bg-[#7d53de] px-8 py-[18px] text-[20px] font-bold tracking-[-0.2px] text-white">
            시작하기
          </button>
          <button type="button" onClick={startLater} disabled={busy}
            className="w-full rounded-[16px] border-2 border-b-[6px] border-[#e2e2e8] bg-white px-8 py-[18px] text-[20px] font-bold text-[#7d53de]">
            나중에 할게요
          </button>
        </div>
      </div>
    </div>
  )
}
