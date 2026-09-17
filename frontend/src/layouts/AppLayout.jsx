import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import TopBar from './TopBar'
import NavShell from './NavShell'

// 모든 화면을 감싸는 최상위 레이아웃(리디자인 스펙 6.1).
// TopBar + NavShell을 한 번만 렌더링하고, 화면 본문은 <Outlet/>으로 위임한다.
// - 기존 GlobalLearningMenu·SignSelectionOverlay는 App.jsx에서 이 레이아웃 바깥(원래 자리)에 그대로 둔다.
// - 본문을 <main>으로 감싸지 않는다 — 기존 페이지들이 각자 <main>을 갖고 있어 중첩되기 때문.
// - 레이아웃 안에도 지연로딩 경계를 둬, 페이지 청크를 받는 동안 TopBar·NavShell이 사라지지 않게 한다.
export default function AppLayout() {
  return (
    <div className="app-shell">
      <TopBar />
      <NavShell />
      <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>불러오는 중…</div>}>
        <Outlet />
      </Suspense>
    </div>
  )
}
