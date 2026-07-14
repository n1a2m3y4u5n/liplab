import { useLayoutEffect, useRef, useState } from 'react'

// 학습 화면 상단 헤더 — 기둥(독화·말하기·촉각)별 단색 배경을 입히고,
// '나가기'에 마우스를 올리면 그 글자 위치에서 붉은 물감이 퍼지듯 헤더를 덮는다.
const HEADER_ACCENTS = {
  reading: '#fef3c7',   // 독화 (연한 노랑)
  speaking: '#ffe4e6',  // 말하기 (연한 로즈)
  tactile: '#ede9fe',   // 촉각 (연한 바이올렛)
}

// 나가기 호버 시 덮이는 붉은 물감 — 연한 단색 레드
const RED_COLOR = '#fca5a5'

export default function LearnHeader({ title, description, accent = 'reading', onExit, maxWidth = 'max-w-5xl' }) {
  const [exitHover, setExitHover] = useState(false)
  const [origin, setOrigin] = useState({ x: 92, y: 50 })
  const headerRef = useRef(null)
  const btnRef = useRef(null)
  const bgColor = HEADER_ACCENTS[accent] || HEADER_ACCENTS.reading

  // 붉은 물감이 '나가기' 글자에서 퍼지도록, 버튼 중심을 헤더 기준 %좌표로 계산.
  // 호버 순간이 아니라 마운트·리사이즈 때 미리 측정해 둔다 — 그래야 첫 호버에서도
  // 중심점이 바뀌지 않고(=옆으로 미끄러지지 않고) 반경만 커진다.
  const measure = () => {
    const h = headerRef.current
    const b = btnRef.current
    if (!h || !b) return
    const hr = h.getBoundingClientRect()
    const br = b.getBoundingClientRect()
    setOrigin({
      x: ((br.left + br.width / 2 - hr.left) / hr.width) * 100,
      y: ((br.top + br.height / 2 - hr.top) / hr.height) * 100,
    })
  }

  useLayoutEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  return (
    <header ref={headerRef} className="relative overflow-hidden border-b border-slate-200" style={{ backgroundColor: bgColor }}>
      {/* 나가기 호버 시 그 글자 위치에서 붉은 물감이 퍼진다 */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 transition-[clip-path] duration-[600ms] ease-out"
        style={{
          backgroundColor: RED_COLOR,
          clipPath: `circle(${exitHover ? 80 : 0}px at ${origin.x}% ${origin.y}%)`,
        }}
      />
      <div className={`relative ${maxWidth} mx-auto flex items-center justify-between gap-4 px-4 py-4 sm:px-6`}>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          <p className="text-sm text-slate-700">{description}</p>
        </div>
        <button
          ref={btnRef}
          type="button"
          onClick={onExit}
          onMouseEnter={() => setExitHover(true)}
          onMouseLeave={() => setExitHover(false)}
          className={`shrink-0 text-sm font-bold transition-colors ${exitHover ? 'text-red-900' : 'text-slate-600 hover:text-slate-900'}`}
        >
          ✕ 나가기
        </button>
      </div>
    </header>
  )
}
