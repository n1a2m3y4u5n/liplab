import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'

/**
 * 온보딩 트랙 선택 (Figma 리디자인 "온보딩 / 1. 설문 안내" 골격 적용).
 * 두 트랙(독화=perception / 발화=language) 중 하나를 고르고 학습을 시작한다.
 * 정확한 시작점을 원하면 자가진단(배치검사)으로 이동. 표시 여부는 localStorage로 1회 제어.
 */
const TRACKS = [
  { key: 'perception', label: '독화', sub: '입모양을 보고 말을 읽어요', icon: '👁', route: '/learn/path' },
  { key: 'language', label: '발화', sub: '소리 내어 또렷하게 말해요', icon: '🔊', route: '/learn/speaking' },
]

export default function Onboarding() {
  const navigate = useNavigate()
  const [sel, setSel] = useState('perception')
  const [busy, setBusy] = useState(false)
  const mark = () => { try { localStorage.setItem('liplab_onboarded', '1') } catch { /* 무시 */ } }

  const start = async () => {
    setBusy(true)
    const t = TRACKS.find((x) => x.key === sel)
    try { await curriculumAPI.setTrack(sel) } catch { /* 실패해도 이동 */ }
    mark()
    navigate(t.route)
  }
  const goPlacement = () => { mark(); navigate('/learn/placement') }
  const goDemo = () => { mark(); navigate('/learn/path') }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[#f3f3f3] px-4 py-8">
      <div className="flex w-full max-w-[420px] flex-col items-center gap-7">
        {/* 마스코트 + 타이틀 (Figma 설문 안내) */}
        <img src="/ui/mascot.svg" alt="" className="h-[120px] w-[120px]" />
        <div className="flex flex-col items-center gap-3 text-center">
          <h1 className="text-[30px] font-bold leading-tight tracking-[-0.95px] text-ink sm:text-[34px]">어떻게 시작해볼까요?</h1>
          <p className="text-[17px] leading-[1.85] text-ink-muted">무엇부터 시작할지 골라주세요.</p>
        </div>

        {/* 트랙 선택 (Figma 자기진단 옵션 카드 스타일) */}
        <div className="flex w-full flex-col gap-3">
          {TRACKS.map((t) => {
            const on = sel === t.key
            return (
              <button key={t.key} type="button" onClick={() => setSel(t.key)}
                className={`flex items-center gap-4 rounded-[16px] p-5 text-left transition ${on
                  ? 'border-[2.5px] border-primary-500 bg-primary-100'
                  : 'border-2 border-b-[5px] border-line bg-white hover:border-gray-300'}`}>
                <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-[22px] ${on ? 'bg-white' : 'bg-gray-100'}`}>{t.icon}</span>
                <span className="flex flex-1 flex-col gap-1">
                  <span className={`text-[18px] font-bold ${on ? 'text-primary-700' : 'text-ink'}`}>{t.label}</span>
                  <span className="text-[14px] text-ink-muted">{t.sub}</span>
                </span>
              </button>
            )
          })}
        </div>

        {/* 자가진단 안내 (Figma 노트 카드) */}
        <button type="button" onClick={goPlacement}
          className="flex w-full items-center gap-2.5 rounded-[12px] bg-[#fff3d6] px-4 py-3.5 text-left text-[14px] text-[#92400e] transition hover:brightness-95">
          <span aria-hidden>💡</span>
          <span className="flex-1">입모양·발음 자가진단으로 딱 맞는 시작점을 추천받을 수 있어요.</span>
        </button>

        {/* 하단 버튼 (공용 3D 버튼) */}
        <div className="flex w-full flex-col gap-3">
          <button type="button" onClick={start} disabled={busy}
            className="btn-primary w-full !py-4 text-[18px]">
            {busy ? '…' : '학습 시작하기'}
          </button>
          <button type="button" onClick={goDemo}
            className="btn-secondary w-full !py-3.5 text-[15px]">
            빠른 데모 시작
          </button>
        </div>
      </div>
    </div>
  )
}
