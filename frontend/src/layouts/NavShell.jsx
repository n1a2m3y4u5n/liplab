import { Link, useLocation } from 'react-router-dom'

// 전역 내비게이션(리디자인 스펙 2.2) — 홈/학습/복습/분석/설정 5개 항목 고정.
// 레이아웃 형태(사이드바·상단 탭·하단 탭바)는 Figma에서 정한다. 지금은 섹션 진입 링크만 연결.
// 각 섹션의 첫 화면은 App.jsx 라우팅이 정한다(/learn → 독화 트랙 등).
// match: 이 경로(또는 그 하위)에 있으면 해당 항목을 현재 위치로 표시한다.
const NAV_ITEMS = [
  { label: '홈', to: '/dashboard', match: ['/dashboard'] },
  { label: '학습', to: '/learn', match: ['/learn', '/pronounce'] },
  { label: '복습', to: '/review', match: ['/review'] },
  { label: '분석', to: '/analysis', match: ['/analysis'] },
  { label: '설정', to: '/account', match: ['/account'] },
]

const isUnder = (pathname, base) => pathname === base || pathname.startsWith(`${base}/`)

export default function NavShell() {
  const { pathname } = useLocation()

  return (
    <nav aria-label="주요 메뉴" className="border-b border-slate-200 bg-white">
      <ul className="mx-auto flex max-w-[1440px] gap-1 overflow-x-auto px-2 sm:px-6">
        {NAV_ITEMS.map((item) => {
          const current = item.match.some((base) => isUnder(pathname, base))
          return (
            <li key={item.to} className="shrink-0">
              <Link
                to={item.to}
                aria-current={current ? 'page' : undefined}
                className={`block border-b-2 px-4 py-2 text-sm font-bold ${current ? 'border-sky-600 text-sky-700' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
              >
                {item.label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
