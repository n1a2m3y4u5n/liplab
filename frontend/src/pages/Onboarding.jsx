import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'

/**
 * 온보딩 트랙 선택 (Figma 리디자인 01 / 10.모바일 "어떻게 시작해볼까요?").
 * 두 트랙(독화=perception / 발화=language) 중 하나를 고르고 학습을 시작한다.
 * 정확한 시작점을 원하면 자가진단(배치검사)으로 이동. 표시 여부는 localStorage로 1회 제어.
 */
const TRACKS = [
  { key: 'perception', label: '독화', sub: '입모양 읽기', icon: '👁', route: '/learn/path',
    tint: 'bg-primary-100', border: 'border-primary-500', ring: 'ring-primary-200', text: 'text-primary-700' },
  { key: 'language', label: '발화', sub: '소리 내어 말하기', icon: '🔊', route: '/learn/path?track=speak',
    tint: 'bg-[#ffe4e9]', border: 'border-[#ec4899]', ring: 'ring-[#fbcfe8]', text: 'text-[#be185d]' },
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
    <div className="flex min-h-[100dvh] items-center justify-center bg-gray-50 px-4 py-8">
      <div className="w-full max-w-[420px]">
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="flex h-[76px] w-[76px] items-center justify-center rounded-[26px] bg-primary-100 shadow-sm">
            <img src="/ui/mascot.svg" alt="" className="h-11 w-11" />
          </span>
          <h1 className="text-[26px] font-bold tracking-[-0.5px] text-ink">어떻게 시작해볼까요?</h1>
        </div>

        <div className="mt-6 rounded-[24px] border border-line bg-white p-5">
          <p className="mb-3 text-[13px] font-bold text-ink-muted">무엇부터 시작할까요</p>
          <div className="grid grid-cols-2 gap-3">
            {TRACKS.map((t) => {
              const on = sel === t.key
              return (
                <button key={t.key} type="button" onClick={() => setSel(t.key)}
                  className={`flex flex-col items-center gap-2 rounded-[18px] border-2 px-3 py-5 transition ${on ? `${t.border} ${t.tint} ring-4 ${t.ring}` : 'border-line bg-white hover:border-gray-300'}`}>
                  <span className={`flex h-12 w-12 items-center justify-center rounded-full text-[22px] ${t.tint}`}>{t.icon}</span>
                  <span className="text-[16px] font-bold text-ink">{t.label}</span>
                  <span className={`text-[12px] font-medium ${on ? t.text : 'text-ink-muted'}`}>{t.sub}</span>
                </button>
              )
            })}
          </div>
          <button type="button" onClick={goPlacement}
            className="mt-4 flex w-full items-center gap-2 rounded-[14px] border border-amber-200 bg-amber-50 px-4 py-3 text-left text-[13px] font-medium text-amber-800 transition hover:bg-amber-100">
            <span aria-hidden>💡</span>
            <span className="flex-1">입모양·발음 자가진단으로 딱 맞는 시작점을 추천받을 수 있어요.</span>
          </button>
        </div>

        <button type="button" onClick={start} disabled={busy}
          className="btn-primary mt-4 w-full !py-4 text-[18px]">
          {busy ? '…' : '학습 시작하기'}
        </button>
        <button type="button" onClick={goDemo}
          className="btn-secondary mt-2 w-full !py-3.5 text-[15px]">
          빠른 데모 시작
        </button>
      </div>
    </div>
  )
}
