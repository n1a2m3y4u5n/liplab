/**
 * LIPLAB 로고 — 보라 블롭(logo.png) + 눈 점 2개 + Rowdies 워드마크 (Figma 58:13).
 * size = 워드마크 글자 크기(px). 나머지 치수는 데스크톱(30px) 기준 비율로 줄인다:
 *   사이드바 30 (58:13) · 로그인 28 (227:51) · 모바일 상단 바 20 (232:37)
 * pink: 발화 트랙(171:40) — 블롭에 분홍 color 블렌드를 얹고(블롭 모양으로 마스킹) 글자도 분홍.
 */
const BASE = 30

export default function Logo({ size = BASE, pink = false, className = '' }) {
  const k = size / BASE
  const px = (v) => `${Math.round(v * k * 100) / 100}px`
  return (
    <span role="img" aria-label="LIPLAB" className={`relative inline-block shrink-0 ${className}`}
      style={{ width: px(155), height: px(38.125) }}>
      {/* 블롭 32.5×28.75, 위 4.38 */}
      <span aria-hidden className="absolute left-0" style={{ top: px(4.38), width: px(32.5), height: px(28.75) }}>
        <img src="/ui/logo.png" alt="" className="absolute inset-0 size-full max-w-none object-cover" />
        {pink && (
          <span className="absolute inset-0 bg-speak mix-blend-color"
            style={{ WebkitMaskImage: 'url(/ui/logo.png)', maskImage: 'url(/ui/logo.png)', WebkitMaskSize: '100% 100%', maskSize: '100% 100%' }} />
        )}
      </span>
      {/* 눈 점 — 58:16(3.75, 4.24 상자 가운데) · 58:17(3.75) */}
      <img src="/ui/lp-58-13-logo-eye.svg" alt="" aria-hidden className="absolute max-w-none"
        style={{ left: px(12.747), top: px(19.627), width: px(3.75), height: px(3.75) }} />
      <img src="/ui/lp-58-13-logo-eye.svg" alt="" aria-hidden className="absolute max-w-none"
        style={{ left: px(18.75), top: px(17.5), width: px(3.75), height: px(3.75) }} />
      <span aria-hidden className={`absolute top-0 whitespace-nowrap font-display ${pink ? 'text-speak' : 'text-primary-500'}`}
        style={{ left: px(31.88), fontSize: px(30), lineHeight: px(38.125), letterSpacing: px(-1.5) }}>
        LIPLAB
      </span>
    </span>
  )
}
