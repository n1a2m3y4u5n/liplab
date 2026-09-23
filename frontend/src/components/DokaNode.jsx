/**
 * 학습 경로의 DOKA 노드 (핸드오프 §3.7 · §8-1 공통 컴포넌트).
 * Figma: 데스크톱 58:11 / 발화 171:38 (노드 76px·현재 87.4px·링 109px·체크 배지 24px@55,54)
 *        모바일 232:35 (노드 56px·현재 64.4px·링 80px·체크 배지 19px@40,39) — lg에서 바뀐다.
 *
 * status: 'mastered'(완료 — 트랙색 DOKA 55% + 체크 배지) | 'current'(1.15배 + 링)
 *         | 'skip'(건너뛰기 가능 — 연한 DOKA, 눈 뜸) | 'locked'(회색, 잠듦)
 * track:  'read'(보라, 기본) | 'speak'(분홍)
 *
 * 자리(layout)는 상태와 무관하게 늘 56px(lg 76px)이다. 현재 노드의 큰 몸통·링은 자리 가운데에
 * 겹쳐 넘치므로, 노드와 DokaConnector를 세로로 쌓기만 하면 Figma 간격(74px / 118px)이 나온다.
 * SVG는 그림자까지 담아 슬롯보다 크다(124%, 위 -7%·왼쪽 -12%). 픽셀 값은 a11y 글자 키우기에도
 * 어긋나지 않게 px로 둔다.
 */
export const DOKA_ASSETS = {
  read: {
    done: '/ui/node-done.svg', current: '/ui/node-current.svg', ring: '/ui/node-ring.svg',
    badge: '/ui/node-check-badge.svg', badgeMobile: '/ui/lp-232-35-node-check-badge.svg',
    skip: '/ui/lp-78-8-node-skip.svg',
  },
  speak: {
    done: '/ui/lp-171-38-node-done.svg', current: '/ui/lp-171-38-node-current.svg', ring: '/ui/lp-171-38-node-ring.svg',
    badge: '/ui/lp-171-38-node-check-badge.svg', badgeMobile: null,   // Figma에 발화 모바일 배지 없음 → 데스크톱 배지를 줄여 쓴다
    skip: '/ui/lp-78-8-node-skip.svg',                                // Figma에 분홍 건너뛰기 DOKA 없음 → 독화 것을 쓴다
  },
  locked: '/ui/node-locked.svg',
}

const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // Figma inset -7% -12% -17% -12%

export default function DokaNode({ status = 'locked', track = 'read', className = '' }) {
  const a = DOKA_ASSETS[track] || DOKA_ASSETS.read
  const body = status === 'mastered' ? a.done : status === 'skip' ? a.skip : DOKA_ASSETS.locked
  return (
    <span className={`relative z-[1] block size-[56px] shrink-0 lg:size-[76px] ${className}`}>
      {status === 'current' ? (
        <>
          <img src={a.ring} alt="" aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 size-[80px] max-w-none -translate-x-1/2 -translate-y-1/2 lg:size-[109px]" />
          <span className="absolute left-1/2 top-1/2 size-[64.4px] -translate-x-1/2 -translate-y-1/2 lg:size-[87.4px]">
            <img src={a.current} alt="" aria-hidden className="absolute max-w-none" style={OVERFLOW} />
          </span>
        </>
      ) : (
        <img src={body} alt="" aria-hidden className="absolute max-w-none" style={OVERFLOW} />
      )}
      {status === 'mastered' && (
        // 배지 SVG는 그림자 여백(좌우 3·위 2·아래 4px)을 포함한다 → 슬롯보다 6px 크게, (-3, -2)에 둔다.
        <span className="absolute left-[40px] top-[39px] size-[19px] lg:left-[55px] lg:top-[54px] lg:size-[24px]">
          <picture>
            {a.badgeMobile && <source media="(min-width: 1024px)" srcSet={a.badge} />}
            <img src={a.badgeMobile || a.badge} alt="" aria-hidden
              className="absolute left-[-3px] top-[-2px] h-[calc(100%+6px)] w-[calc(100%+6px)] max-w-none" />
          </picture>
        </span>
      )}
    </span>
  )
}

/** 노드 사이 연결선 — 모바일 5×28(233:46) / lg 6×58(171:102). 위아래 노드에 5px(lg 8px)씩 겹친다.
 *  done이면 트랙색(bg-track), 아니면 bg-fill-strong. */
export function DokaConnector({ done = false, className = '' }) {
  return (
    <span aria-hidden
      className={`relative z-0 my-[-5px] block h-[28px] w-[5px] shrink-0 rounded-[3px] lg:my-[-8px] lg:h-[58px] lg:w-[6px] ${done ? 'bg-track' : 'bg-fill-strong'} ${className}`} />
  )
}
