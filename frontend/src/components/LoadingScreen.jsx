/**
 * 로딩 (핸드오프 §4-10 · §4-12). lg 미만은 모바일 프레임 값, lg 이상은 데스크톱 프레임 값.
 * variant='plain'(기본) — 페이지 전환·데이터 로딩(256:34 / 모바일 256:48):
 *   흰 배경 + 보라 DOKA(170 / 120) + "로딩 중"(22px / 17px) + 점 3개(11px·간격 9 / 9px·간격 7, 진한→옅은).
 * variant='inline' — 셸(사이드바·탭) 안에서 내용만 불러올 때. 'plain'과 같은 DOKA·문구·점을 그대로 쓰고,
 *   창 전체 대신 내용 영역(최소 60vh)만 채운다(§4-10 256:34를 셸 안에 둔 것).
 * variant='brand' — 레슨 시작 전 트랙별 로딩(223:30 독화 · 223:50 발화 / 모바일 243:81 · 243:101):
 *   트랙 그라데이션 + 블롭 2개 + 헤일로(220 / 158) 안 마스코트(158 / 116) + 흰 점 + 팁 카드.
 *   track='perception'(보라, 기본) | 'language'(분홍).
 * role="status"로 화면 낭독기에 로딩 중임을 알린다.
 */
const TRACK_UI = {
  perception: {
    bg: 'bg-loading-perception',               // index.css — 모바일 121.64° / lg 151.93°
    mascot: '/ui/onb-mascot-light.svg',        // 223:35
    mascotMobile: '/ui/lp-243-81-mascot.svg',  // 243:86 (볼 색이 다름)
    badge: 'TMI',
    tip: ['LIPLAB의 마스코트는', '비교적 오랫동안 디자인 했어요.'],
  },
  language: {
    bg: 'bg-loading-language',
    mascot: '/ui/lp-223-50-mascot.svg',         // 223:55
    mascotMobile: '/ui/lp-243-101-mascot.svg',  // 243:106
    badge: '학습 팁',
    tip: ['발화 학습 때 크게 말해보세요.', '점수뿐만 아니라 자신감도 올라갈 거예요!'],
  },
}

// 마스코트 SVG는 그림자까지 담아 슬롯보다 크다(Figma inset -7% -12% -17% -12%).
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }

// 점 3개(Figma Dots) — 진한 것에서 옅은 것으로(기본 보라 1·.55·.3 / 브랜드 흰색 1·.6·.35), 순차 펄스로 진행을 보인다.
function Dots({ onBrand = false }) {
  const steps = onBrand ? ['opacity-100', 'opacity-60', 'opacity-[0.35]'] : ['opacity-100', 'opacity-[0.55]', 'opacity-30']
  return (
    <div aria-hidden className={`flex ${onBrand ? 'gap-[8px] lg:gap-[10px]' : 'gap-[7px] lg:gap-[9px]'}`}>
      {steps.map((step, i) => (
        <span key={i} className={step}>
          <span className={`block animate-pulse rounded-full ${onBrand ? 'size-[10px] bg-white lg:size-[12px]' : 'size-[9px] bg-primary-500 lg:size-[11px]'}`}
            style={{ animationDelay: `${i * 180}ms` }} />
        </span>
      ))}
    </div>
  )
}

export default function LoadingScreen({ label = '로딩 중', variant = 'plain', track = 'perception' }) {
  if (variant === 'plain' || variant === 'inline') {
    const box = variant === 'inline' ? 'min-h-[60vh] w-full' : 'min-h-[100dvh] bg-white'
    return (
      <div role="status" className={`flex flex-col items-center justify-center gap-[26px] lg:gap-[37px] ${box}`}>
        <span className="relative size-[120px] lg:size-[170px]">
          <img src="/ui/lp-84-7-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
        </span>
        <p className="text-center text-[17px] font-bold leading-figma tracking-[-0.255px] text-ink-muted lg:text-[22px] lg:tracking-[-0.33px]">{label}</p>
        <Dots />
      </div>
    )
  }

  const ui = TRACK_UI[track] || TRACK_UI.perception
  return (
    <div role="status" aria-label={label}
      className={`relative flex min-h-[100dvh] flex-col items-center justify-center overflow-hidden px-[34px] lg:px-6 ${ui.bg}`}>
      {/* 블롭 2개 — 왼쪽 위 300(-110,-90) / 520(-160,-120), 오른쪽 아래 240(-140,-56) / 420(-160,-156) */}
      <img src="/ui/lp-223-30-blob1.svg" alt="" aria-hidden
        className="pointer-events-none absolute left-[-110px] top-[-90px] size-[300px] max-w-none lg:left-[-160px] lg:top-[-120px] lg:size-[520px]" />
      <img src="/ui/lp-223-30-blob2.svg" alt="" aria-hidden
        className="pointer-events-none absolute bottom-[-56px] right-[-140px] size-[240px] max-w-none lg:bottom-[-156px] lg:right-[-160px] lg:size-[420px]" />

      <div className="relative flex w-full flex-col items-center gap-[26px] lg:w-auto lg:gap-[34px]">
        {/* 헤일로 + 밝은 마스코트 */}
        <span className="relative size-[158px] shrink-0 rounded-full bg-white/[0.16] lg:size-[220px]">
          <span className="absolute left-[21px] top-[21px] size-[116px] lg:left-[31px] lg:top-[31px] lg:size-[158px]">
            <picture>
              <source media="(min-width: 1024px)" srcSet={ui.mascot} />
              <img src={ui.mascotMobile} alt="" className="absolute max-w-none" style={OVERFLOW} />
            </picture>
          </span>
        </span>
        <Dots onBrand />
        {/* 팁 카드 — 모바일 전체 폭(390 기준 322) p20 r18 / lg 560 px30 py24 r20 */}
        <div className="flex w-full flex-col items-center gap-2.5 rounded-18 border-2 border-white/30 bg-white/[0.18] p-5 lg:w-[560px] lg:max-w-full lg:gap-3 lg:rounded-20 lg:px-[30px] lg:py-6">
          <span className="rounded-full bg-white/30 px-3 py-[5px] text-[11px] font-bold leading-figma tracking-[0.22px] text-white lg:px-3.5 lg:py-1.5 lg:text-[12px] lg:tracking-[0.24px]">{ui.badge}</span>
          <p className="text-center text-[15px] font-bold leading-[1.7] tracking-[-0.225px] text-white lg:text-[19px] lg:leading-[1.65] lg:tracking-[-0.285px]">
            {ui.tip[0]}<br />{ui.tip[1]}
          </p>
        </div>
      </div>
    </div>
  )
}
