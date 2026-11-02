import { useState } from 'react'
import { mergeBadges } from '../../lib/badges'
import useFocusTrap from '../../hooks/useFocusTrap'
const GREY_ONLY = new Set(['sign', 'streak30', 'dawn', 'complete', 'level5'])

/**
 * 배지 아이콘 그래픽(그리드·모달 공용). size는 Tailwind 크기 클래스.
 *  - icon: Figma 메달 에셋(medal-*.svg, 원 배경 포함)
 *  - shape 'check'(정확도 90%, 313:148): 연녹 원 + 45° 회전한 초록 마름모(22/56)
 *  - shape 'lock'(레벨 5, 313:181): 연회색 원(85%) + 회색 둥근 사각(25/56)
 * markOnly: 모달의 정확도 90% 마크(313:224) — 원 없이 큰 마름모만(92/130).
 */
function BadgeMedal({ b, size, markOnly = false }) {
  if (b.icon) return <img src={b.icon} alt="" className={`max-w-none ${size}`} />
  if (b.shape === 'check') {
    if (markOnly) {
      return (
        <span className={`flex items-center justify-center drop-shadow-[0_10px_12px_rgba(5,77,51,0.35)] ${size}`}>
          <span className="size-[70.77%] rotate-45 rounded-[17.4%] bg-good" />
        </span>
      )
    }
    return (
      <span className={`flex items-center justify-center rounded-full bg-pastel-mint ${size}`}>
        <span className="size-[39.3%] rotate-45 rounded-[18%] bg-good" />
      </span>
    )
  }
  return (
    <span className={`flex items-center justify-center rounded-full bg-inactive-bg ${size}`}>
      <span className="size-[44.6%] rounded-[20%] bg-inactive-glyph" />
    </span>
  )
}

/** 배지 한 칸(313:135) — 메달 56 + 9 + 이름 11.5px. 미획득은 이름을 흐리게(55%), 색 메달은 회색조로. */
function Badge({ b, onSelect }) {
  const dim = !b.earned && !GREY_ONLY.has(b.key)
  return (
    <button type="button" onClick={() => onSelect(b)}
      className="flex min-w-0 flex-col items-center gap-[9px] rounded-2xl outline-none transition-transform hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-primary-400">
      <span className={dim ? 'opacity-50 grayscale' : ''}><BadgeMedal b={b} size="size-14" /></span>
      <span className={`text-center text-[11.5px] font-bold leading-figma ${b.earned ? 'text-ink' : 'text-ink-muted'}`}>{b.key === 'free' ? '내 문장 입모양 보기' : b.label}</span>
    </button>
  )
}

/**
 * 배지 상세 모달 (Figma 313:33) — §3.5 예외: 흰 카드 없이 배경 블러 위에 배지를 크게 띄운다.
 * 공용 Modal.jsx(흰 카드+X) 재사용 금지. 전용 오버레이 + 중앙 세로 스택.
 * 글로우 420(313:215) 가운데 배지 마크 130(313:224), 문구 묶음(313:225)은 글로우 아래쪽에 40px 겹친다.
 * 모바일 프레임이 없어 lg 미만은 같은 비율로 줄인다(글로우 260 · 마크 80 · 겹침 25).
 * 정확도 90%(획득)는 Figma가 글로우와 마크를 한 에셋으로 내보낸 lp-313-33-glow.svg를 그대로 쓴다.
 * 배경 클릭·ESC로 닫힘. 열린 동안 포커스를 모달 안에 가두고, 닫히면 누른 배지로 포커스를 돌려준다(hooks/useFocusTrap).
 */
function BadgeDetailModal({ badge, onClose }) {
  const dialogRef = useFocusTrap(!!badge, onClose)
  if (!badge) return null
  const figmaMark = badge.shape === 'check' && badge.earned
  return (
    <div ref={dialogRef} className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-overlay-deep/80 p-6 backdrop-blur-[9px]"
      onClick={onClose} role="dialog" aria-modal="true" aria-label={badge.label}>
      <div className="flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
        {/* 글로우(링 3개·부드러운 빛·반짝이) 뒤 + 배지 마크 가운데 */}
        <div className="relative flex size-[260px] items-center justify-center lg:size-[420px]">
          <img src={figmaMark ? '/ui/lp-313-33-glow.svg' : '/ui/lp-313-33-glow-ring.svg'} alt="" aria-hidden="true"
            className="pointer-events-none absolute inset-0 size-full" />
          {!figmaMark && (
            <div className={`relative ${badge.earned || GREY_ONLY.has(badge.key) ? '' : 'opacity-60'}`}>
              <BadgeMedal b={badge} size="size-20 lg:size-[130px]" markOnly />
            </div>
          )}
        </div>

        {/* 제목·설명·희귀도 칩 */}
        <div className="relative -mt-[25px] flex flex-col items-center gap-2.5 lg:-mt-10">
          <h2 className="text-center text-[32px] font-bold leading-figma tracking-[-0.64px] text-white">{badge.label}</h2>
          <p className="max-w-[320px] text-center text-[15px] leading-figma text-white opacity-70">{badge.desc}</p>
          {/* 희귀도 칩: 계산 API가 없으면 숨긴다(핸드오프 §7-3). */}
          {badge.percent != null && (
            <span className="rounded-full border-[1.5px] border-white/[0.22] bg-white/[0.12] px-[18px] py-[9px] leading-figma">
              <span className="text-[15px] text-white">전체 사용자 중 </span>
              <span className="text-[18px] font-bold text-chart-onDark">{badge.percent}%</span>
              <span className="text-[15px] text-white">가 받았어요</span>
            </span>
          )}
        </div>

        {/* 닫기(313:230) */}
        <button type="button" onClick={onClose}
          className="mt-8 w-[220px] rounded-14 border-2 border-b-5 border-line-strong bg-white py-[15px] text-[17px] font-bold leading-figma text-ink transition-all active:translate-y-[1px] active:border-b-2">
          닫기
        </button>
      </div>
    </div>
  )
}


export default function Badges({ data }) {
  const [selected, setSelected] = useState(null)
  const badges = mergeBadges(data)
  return <section className="card-flat"><h2 className="mb-4 font-bold">학습 상</h2><div className="grid grid-cols-4 gap-4 sm:grid-cols-6">{badges.map((b) => <Badge key={b.key} b={b} onSelect={setSelected} />)}</div><BadgeDetailModal badge={selected} onClose={() => setSelected(null)} /></section>
}
