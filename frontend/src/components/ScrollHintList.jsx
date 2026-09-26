import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

/**
 * 세로 스크롤 목록 + 바닥 스크롤 안내(변경 내역 §0-1, 복습 항목 192:21·320:36·320:39, 회차 상세 213:27).
 *  - 목록은 최대 높이(maxHeightClass) 안에서 세로로 스크롤된다. 항목은 잘리지 않고 이어진다.
 *  - 안내는 목록 바닥에 겹치는 흰 그라데이션 페이드(투명 → 55% 지점부터 흰색)와 가운데 화살표 원이다. 목록 흐름을
 *    밀어내지 않도록 absolute로 겹치고, 버튼이 아니라서 누를 수도 포커스할 수도 없다(pointer-events none, aria-hidden).
 *  - 스크롤이 맨 아래에 닿으면 150ms로 사라지고, 목록이 틀보다 짧아 스크롤이 필요 없으면 처음부터 보이지 않는다.
 *  - "더 보기" 같은 문구는 넣지 않는다(Figma에 없음).
 * props
 *   maxHeightClass  목록 최대 높이(예: 'max-h-[241px] lg:max-h-[419px]')
 *   hintHeight      페이드 높이(복습 52 · 회차 상세 56)
 *   iconSize·iconTop 화살표 원 지름과 페이드 위쪽 여백(복습 38·8 · 회차 상세 36·12)
 *   onOverflowChange 스크롤이 필요한지(목록이 틀보다 긴지) 바뀔 때 알린다: 카드 아래 여백을 Figma대로 맞출 때 쓴다.
 *                   목록이 빠질 때(빈 상태 등)는 false를 알려 줄어든 여백이 남지 않게 한다.
 *   resetKey        바뀌면 맨 위로 되돌린다(예: 필터). 같은 스크롤 틀에 새 목록이 들어오므로 이전 위치에서 열리지 않게 한다.
 *   label           스크롤이 생기면 틀이 키보드 초점을 받아 화살표로 내릴 수 있다. 그때 읽어 줄 이름(aria-label).
 * 초점을 받은 항목이 페이드에 가리지 않도록 스크롤할 때 아래쪽에 페이드 높이만큼 여유(scroll-padding)를 둔다.
 */
const ICON = '/ui/lp-318-33-scroll-more.svg'  // 38px 원 + 그림자(에셋 52×52, 원 기준 -10.53% · -18.42% 인셋)

export default function ScrollHintList({
  children, maxHeightClass = '', className = '', hintHeight = 52, iconSize = 38, iconTop = 8, onOverflowChange, resetKey, label,
}) {
  const ref = useRef(null)
  const [overflow, setOverflow] = useState(false)   // 스크롤이 필요한가
  const [atEnd, setAtEnd] = useState(true)          // 맨 아래에 닿았나

  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    const over = el.scrollHeight - el.clientHeight > 1
    setOverflow(over)
    setAtEnd(!over || el.scrollHeight - el.clientHeight - el.scrollTop <= 1)
  }, [])

  // 필터가 바뀌면 맨 위에서 다시 연다(재기 전에 해야 맨 아래 여부가 새 위치로 잡힌다).
  useLayoutEffect(() => { if (ref.current) ref.current.scrollTop = 0 }, [resetKey])
  // 항목이 바뀔 때마다(필터·삭제·데이터 도착) 다시 잰다.
  useLayoutEffect(() => { measure() })
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [measure])
  useEffect(() => { onOverflowChange?.(overflow) }, [overflow, onOverflowChange])
  const overflowCb = useRef(onOverflowChange)
  overflowCb.current = onOverflowChange
  useEffect(() => () => overflowCb.current?.(false), [])   // 목록이 빠지면 부모의 '넘침'도 되돌린다

  const show = overflow && !atEnd
  return (
    <div className="relative w-full">
      <div ref={ref} onScroll={measure}
        tabIndex={overflow ? 0 : undefined} role={overflow && label ? 'region' : undefined} aria-label={overflow ? label : undefined}
        style={overflow ? { scrollPaddingBottom: hintHeight } : undefined}
        className={`scroll-hint-list w-full overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 ${maxHeightClass} ${className}`}>
        {children}
      </div>
      {overflow && (
        <div aria-hidden
          className={`pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-b from-white/0 to-white to-55% transition-opacity duration-150 ${show ? 'opacity-100' : 'opacity-0'}`}
          style={{ height: hintHeight }}>
          <span className="absolute left-1/2 -translate-x-1/2" style={{ top: iconTop, width: iconSize, height: iconSize }}>
            <img src={ICON} alt="" className="absolute max-w-none"
              style={{ top: '-10.53%', left: '-18.42%', width: '136.84%', height: '136.85%' }} />
          </span>
        </div>
      )}
    </div>
  )
}
