import { Component, lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(e) { return { error: e } }
  render() {
    const err = this.state.error
    if (!err) return this.props.children
    // 코드분할(lazy) 청크 로드 실패(불안정 통신망)도 여기로 전파된다 → 원본 스택 대신
    // 사용자 친화 메시지 + 새로고침. 개발 모드에서만 상세 스택을 보여준다.
    const isChunk = /chunk|dynamically imported|Failed to fetch|Importing a module/i.test(err?.message || '')
    return (
      <div style={{minHeight:'100vh',display:'flex',alignItems:'center',justifyContent:'center',padding:24,textAlign:'center'}}>
        <div style={{maxWidth:420}}>
          <p style={{fontSize:44,margin:0}}>😵</p>
          <h1 style={{fontSize:18,fontWeight:700,margin:'8px 0',color:'#0f172a'}}>
            {isChunk ? '페이지를 불러오지 못했어요' : '문제가 발생했어요'}
          </h1>
          <p style={{color:'#64748b',fontSize:14,marginBottom:16}}>
            {isChunk ? '네트워크가 불안정할 수 있어요. 새로고침 해주세요.' : '잠시 후 다시 시도해 주세요.'}
          </p>
          <button onClick={() => window.location.reload()}
            style={{padding:'10px 20px',borderRadius:10,background:'#4f46e5',color:'#fff',border:'none',fontWeight:600,cursor:'pointer'}}>
            새로고침
          </button>
          {import.meta.env?.DEV && (
            <pre style={{marginTop:16,textAlign:'left',fontSize:11,color:'#ef4444',whiteSpace:'pre-wrap',overflow:'auto',maxHeight:200}}>
              {err?.message}{'\n'}{err?.stack}
            </pre>
          )}
        </div>
      </div>
    )
  }
}
import useStore from './store/useStore'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Analysis from './pages/Analysis'
import Bookmarks from './pages/Bookmarks'
import Guide from './pages/Guide'

// 3D(Three.js) 아바타를 쓰는 페이지는 지연로딩한다. 이 페이지들만 three-vendor
// 청크(~320KB gzip)를 끌어오므로, 동적 import 경계를 두면 로그인/대시보드 초기
// 진입에서 three가 빠져 첫 로딩이 가벼워진다(저사양·불안정 통신망 타겟 배려).
// Conversation도 LipSyncPlayer3D→three를 쓰므로 반드시 포함.
const Practice = lazy(() => import('./pages/Practice'))
const Conversation = lazy(() => import('./pages/Conversation'))
const DevViseme = lazy(() => import('./pages/DevViseme'))
const Sign = lazy(() => import('./pages/Sign'))

/**
 * Protected Route wrapper
 */
function ProtectedRoute({ children }) {
  const isAuthenticated = useStore((state) => state.isAuthenticated)

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

/**
 * Main App component with routing
 */
function App() {
  return (
    <ErrorBoundary>
    <Router>
      <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>불러오는 중…</div>}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/practice"
          element={
            <ProtectedRoute>
              <Practice />
            </ProtectedRoute>
          }
        />
        <Route
          path="/conversation"
          element={
            <ProtectedRoute>
              <Conversation />
            </ProtectedRoute>
          }
        />
        <Route path="/analysis" element={<ProtectedRoute><Analysis /></ProtectedRoute>} />
        <Route path="/sign" element={<ProtectedRoute><Sign /></ProtectedRoute>} />
        <Route path="/bookmarks" element={<ProtectedRoute><Bookmarks /></ProtectedRoute>} />
        <Route path="/guide" element={<Guide />} />
        <Route path="/dev-viseme" element={<DevViseme />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      </Suspense>
    </Router>
    </ErrorBoundary>
  )
}

export default App
