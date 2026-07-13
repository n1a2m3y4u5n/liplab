import { Component, lazy, Suspense, useState, useEffect } from 'react'
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
import { authAPI } from './api'
import SignSelectionOverlay from './components/SignSelectionOverlay'
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
 * AuthGate — 로그인 화면 없이 데모 계정으로 자동 입장.
 * 부팅 시 미인증이면 /api/auth/demo로 자동 로그인하고, 완료까지 스플래시를 보인다.
 * 인증 체계 자체는 유지되므로 진행도·북마크 등은 정상 동작한다.
 */
function AuthGate({ children }) {
  const isAuthenticated = useStore((s) => s.isAuthenticated)
  const setAuth = useStore((s) => s.setAuth)
  const [status, setStatus] = useState(isAuthenticated ? 'ready' : 'loading')

  useEffect(() => {
    if (isAuthenticated) { setStatus('ready'); return }
    let cancelled = false
    authAPI.demoLogin()
      .then((data) => { if (!cancelled) { setAuth(data.user, data.access_token); setStatus('ready') } })
      .catch(() => { if (!cancelled) setStatus('error') })
    return () => { cancelled = true }
  }, [isAuthenticated, setAuth])

  if (status === 'ready') return children
  if (status === 'error') return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, textAlign: 'center' }}>
      <div>
        <p style={{ fontSize: 40, margin: 0 }}>🔌</p>
        <p style={{ color: '#64748b', margin: '8px 0 16px' }}>서버에 연결하지 못했어요.</p>
        <button onClick={() => window.location.reload()}
          style={{ padding: '10px 20px', borderRadius: 10, background: '#4f46e5', color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer' }}>
          다시 시도
        </button>
      </div>
    </div>
  )
  return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>불러오는 중…</div>
}

/**
 * Main App component with routing
 */
function App() {
  return (
    <ErrorBoundary>
    <Router>
      <AuthGate>
      <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>불러오는 중…</div>}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/practice" element={<Practice />} />
        <Route path="/conversation" element={<Conversation />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/sign" element={<Sign />} />
        <Route path="/bookmarks" element={<Bookmarks />} />
        <Route path="/guide" element={<Guide />} />
        <Route path="/dev-viseme" element={<DevViseme />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      </Suspense>
      {/* 앱 어디서나 문장 선택 → 수어 번역 (수어 탭 이동 불필요) */}
      <SignSelectionOverlay />
      </AuthGate>
    </Router>
    </ErrorBoundary>
  )
}

export default App
