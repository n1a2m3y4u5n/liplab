import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'
import LearnerInfoForm from '../components/LearnerInfoForm'
import useLearnerInfo from '../hooks/useLearnerInfo'

/**
 * 온보딩 — 자가진단 안내 (Figma 84:7 / 모바일 243:65, lg 미만 반응형).
 * 트랙 선택 화면 대신, 자가진단(배치검사)으로 바로 갈지 나중에 할지만 고르는 화면.
 * - 시작하기: 배치검사로 이동. 결과에서 '학습하러 가기'를 누르면 추천 시작 단계로 배치된다(Placement).
 * - 나중에 할게요: 기본 트랙(독화=perception)으로 배치(setTrack)한 뒤 학습 경로로 간다.
 *   배치(placed) 전에는 /api/curriculum/stages가 1단계를 잠김으로 돌려준다.
 * 온보딩을 마쳤는지는 서버의 배치 여부(placed)로 판단한다(App.jsx HomeRedirect). 예전에는 브라우저 전체에 하나인
 * localStorage 표시를 남겨, 공용 기기의 다음 사람이 온보딩을 건너뛰었다. 발화 경로는 학습 탭의 트랙 전환(?track=speak)으로 연다.
 *
 * 그 앞에 학습자 정보 선택 질문(청력 손실 시기·기기·수어, 계획 2-6)을 한 화면 둔다. 건너뛸 수 있고, 답은 이 기기에만
 * 계정마다 저장해 화면 기본값(짧은 힌트·수어 뜻 펼치기 등, lib/learnerProfile)을 정한다. 서버로 보내지 않는다.
 * 이미 답한 계정이면 바로 시작 화면을 보인다.
 */
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
// 버튼 — 데스크톱 75:23(btn-lg), lg 미만 243:77(r14·b5, py16, 16px)
const BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

export default function Onboarding() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const { answers, save } = useLearnerInfo()
  const [step, setStep] = useState(() => (answers ? 'start' : 'info'))
  const goPlacement = () => navigate('/learn/placement')
  const startLater = async () => {
    setBusy(true)
    try { await curriculumAPI.setTrack('perception') } catch { /* 실패해도 이동 */ }
    navigate('/learn/path')
  }

  if (step === 'info') {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-page px-[22px] py-8 lg:px-4">
        <div className="flex w-full max-w-[460px] flex-col gap-5 rounded-22 border-2 border-line bg-white p-6 lg:p-8">
          <div className="flex flex-col gap-1.5">
            <h1 className="text-[22px] font-bold leading-figma tracking-[-0.44px] text-ink lg:text-[26px]">나에게 맞게 시작해요</h1>
            <p className="text-[14px] leading-[1.6] text-ink-muted">모두 고르지 않아도 돼요. 고른 것에 맞게 화면을 바꿔 둘게요.</p>
          </div>
          <LearnerInfoForm initial={answers} onSave={(a) => { save(a); setStep('start') }} onSkip={() => setStep('start')} />
        </div>
      </div>
    )
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
