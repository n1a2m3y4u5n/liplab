/**
 * 워터마크 카드 (핸드오프 §3.6) — 숫자 카드의 아이콘을 오른쪽 위에 크게 걸쳐 잘리게 둔다.
 * 회전은 Figma +20°(반시계) = CSS -20deg가 기본. 투명도(0.17~0.28)는 내보낸 SVG 안에 이미 있으므로
 * 여기서 opacity를 더하지 않는다. 카드는 relative isolate overflow-hidden이라 아이콘이 잘리고,
 * 아이콘은 z -1로 배경 위·글자 아래에 깔린다(글자에 relative를 줄 필요 없음).
 *
 * deco 좌표는 Figma get_design_context 값을 그대로 넣는다:
 *   size  = 회전 전 아이콘(Deco 프레임) 크기          예) 93:22 정답률 115.2
 *   top   = 회전 후 외접 상자의 top (카드 테두리 안쪽 기준)  예) -45.83
 *   right = 회전 후 외접 상자의 오른쪽 넘침 = 카드 안쪽 폭 − (left + 외접 크기), 음수면 밖으로 걸침
 *   rotate(deg, 기본 -20) · inset(마스코트처럼 이미지가 슬롯보다 큰 경우 [top,right,bottom,left] %)
 *   lg: { size, top, right } — lg(1024px) 이상에서 바꿀 값. hideBelowLg: lg 미만에서 숨김.
 */
function place(size, top, right, rotate) {
  const a = Math.abs((rotate * Math.PI) / 180)
  const pad = (size * (Math.abs(Math.cos(a)) + Math.abs(Math.sin(a))) - size) / 2   // 외접 상자 → 회전 전 상자
  const r2 = (v) => `${Math.round(v * 100) / 100}px`
  return { s: r2(size), t: r2(top + pad), r: r2(right + pad) }
}

export function WatermarkDeco({ src, size, top, right, rotate = -20, inset, lg, hideBelowLg = false }) {
  const b = place(size, top, right, rotate)
  const style = { '--wm-s': b.s, '--wm-t': b.t, '--wm-r': b.r, '--wm-rot': `${rotate}deg` }
  if (lg) {
    const p = place(lg.size ?? size, lg.top ?? top, lg.right ?? right, rotate)
    Object.assign(style, { '--wm-s-lg': p.s, '--wm-t-lg': p.t, '--wm-r-lg': p.r })
  }
  const imgStyle = inset
    ? { top: `${inset[0]}%`, left: `${inset[3]}%`, width: `${100 - inset[1] - inset[3]}%`, height: `${100 - inset[0] - inset[2]}%` }
    : { top: 0, left: 0, width: '100%', height: '100%' }
  return (
    <span aria-hidden className={`wm-deco ${hideBelowLg ? 'hidden lg:block' : ''}`} style={style}>
      <img src={src} alt="" className="absolute max-w-none" style={imgStyle} />
    </span>
  )
}

/**
 * 기본 모양 = Figma 스탯 카드(93:22·104:135): 흰 바탕, 2px 라인 테두리, r18, p20, 세로 간격 8,
 * 가로 줄에서 똑같이 나눠 갖는 flex-1. className을 넘기면 기본 모양 대신 그 클래스를 쓴다(히어로·모바일 카드 등).
 */
export default function WatermarkCard({ as: Tag = 'div', deco, className = 'flex min-w-0 flex-1 flex-col gap-2 rounded-18 border-2 border-line bg-white p-5', children, ...rest }) {
  return (
    <Tag className={`relative isolate overflow-hidden ${className}`} {...rest}>
      {deco && <WatermarkDeco {...deco} />}
      {children}
    </Tag>
  )
}
