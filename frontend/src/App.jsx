import { Component, lazy, Suspense, useState, useEffect, useLayoutEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom'

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
import { authAPI, curriculumAPI, seedAPI } from './api'
import SignSelectionOverlay from './components/SignSelectionOverlay'
import GlobalLearningMenu from './components/GlobalLearningMenu'
import Dashboard from './pages/Dashboard'
import Bookmarks from './pages/Bookmarks'
import Guide from './pages/Guide'

// 탭·학습 단계 등 라우트가 바뀌면 이전 페이지의 스크롤 위치를 이어받지 않는다.
function ScrollToTop() {
  const location = useLocation()

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [location.key])

  return null
}

// 3D(Three.js) 아바타를 쓰는 페이지는 지연로딩한다. 이 페이지들만 three-vendor
// 청크(~320KB gzip)를 끌어오므로, 동적 import 경계를 두면 로그인/대시보드 초기
// 진입에서 three가 빠져 첫 로딩이 가벼워진다(저사양·불안정 통신망 타겟 배려).
// Conversation도 LipSyncPlayer3D→three를 쓰므로 반드시 포함.
const Practice = lazy(() => import('./pages/Practice'))
const Conversation = lazy(() => import('./pages/Conversation'))
const MultiConversation = lazy(() => import('./pages/MultiConversation'))
const Placement = lazy(() => import('./pages/Placement'))
const DevViseme = lazy(() => import('./pages/DevViseme'))
const Sign = lazy(() => import('./pages/Sign'))
const VisemeLiteracy = lazy(() => import('./pages/VisemeLiteracy'))
const WordStage = lazy(() => import('./pages/WordStage'))
const Review = lazy(() => import('./pages/Review'))
const Closure = lazy(() => import('./pages/Closure'))
const SpeakingPractice = lazy(() => import('./pages/SpeakingPractice'))
const TactilePractice = lazy(() => import('./pages/TactilePractice'))
const FreeSpeak = lazy(() => import('./pages/FreeSpeak'))
const ScenarioHub = lazy(() => import('./pages/ScenarioHub'))
const PillarHub = lazy(() => import('./pages/PillarHub'))
const ReviewLanding = lazy(() => import('./pages/ReviewLanding'))
const SpeakingReviewLanding = lazy(() => import('./pages/SpeakingReviewLanding'))
const AnalysisDetail = lazy(() => import('./pages/AnalysisDetail'))
const HardwareBuild = lazy(() => import('./pages/HardwareBuild'))

/**
 * AuthGate — 로그인 화면 없이 데모 계정으로 자동 입장.
 * 부팅 시 미인증이면 /api/auth/demo로 자동 로그인하고, 완료까지 스플래시를 보인다.
 * 인증 체계 자체는 유지되므로 진행도·북마크 등은 정상 동작한다.
 */
function AuthGate({ children }) {
  const isAuthenticated = useStore((s) => s.isAuthenticated)
  const setAuth = useStore((s) => s.setAuth)
  const updateUser = useStore((s) => s.updateUser)
  const [status, setStatus] = useState(isAuthenticated ? 'ready' : 'loading')

  useEffect(() => {
    if (isAuthenticated) {
      setStatus('ready')
      // 재방문(캐시된 인증)에도 서버 최신값으로 user 동기화 — 스트릭 등 stale 방지
      authAPI.getMe().then((u) => { if (u) updateUser(u) }).catch(() => {})
      return
    }
    let cancelled = false
    authAPI.demoLogin()
      .then(async (data) => {
        if (cancelled) return
        setAuth(data.user, data.access_token)
        try { await seedAPI.seedDemo() } catch { /* 데모 시드 실패는 무시 */ }
        if (!cancelled) setStatus('ready')
      })
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
 * StageGate — 순차 해금 강제. 커리큘럼 카드뿐 아니라 직접 URL/버튼 진입도 막는다.
 * 해당 단계가 잠김(locked/coming_soon)이면 대시보드로 돌려보낸다.
 * 조회 실패 시엔 막지 않는다(네트워크 오류로 학습이 통째로 막히지 않도록 — 가용성 우선).
 */
function StageGate({ stage, children }) {
  const location = useLocation()
  // 복습 세션(틀린 문장·북마크 다시 풀기)은 단계 잠금과 무관하게 항상 허용.
  // 복습은 /practice를 재사용하므로, 복습 진입은 navigate state({review:true})로 표시해 예외 처리한다.
  // (스토어가 아닌 라우터 state를 쓰는 이유: 이 이동에만 붙어 이후 직접 진입엔 남지 않아 우회 누수가 없다.)
  const isReview = location.state?.review === true
  const [state, setState] = useState(isReview ? 'allowed' : 'loading')   // loading | allowed | denied
  useEffect(() => {
    if (isReview) { setState('allowed'); return }
    let cancelled = false
    curriculumAPI.getStages()
      .then((data) => {
        const s = (data?.stages || []).find((x) => x.stage === stage)
        const locked = !s || s.status === 'locked' || s.status === 'coming_soon'
        if (!cancelled) setState(locked ? 'denied' : 'allowed')
      })
      .catch(() => { if (!cancelled) setState('allowed') })
    return () => { cancelled = true }
  }, [stage, isReview])

  if (state === 'loading') return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>불러오는 중…</div>
  if (state === 'denied') return <Navigate to="/dashboard" replace />
  return children
}

/**
 * Main App component with routing
 */
function App() {
  return (
    <ErrorBoundary>
    <Router>
      <ScrollToTop />
      <AuthGate>
      <>
      <GlobalLearningMenu />
      <div className="app-shell">
      <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>불러오는 중…</div>}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/practice" element={<StageGate stage={3}><Practice /></StageGate>} />
        <Route path="/conversation" element={<StageGate stage={4}><Conversation /></StageGate>} />
        <Route path="/sign" element={<Sign />} />
        <Route path="/tactile" element={<TactilePractice />} />
        <Route path="/learn/viseme" element={<VisemeLiteracy />} />
        <Route path="/learn/word" element={<StageGate stage={2}><WordStage /></StageGate>} />
        <Route path="/learn/conversation-multi" element={<MultiConversation />} />
        <Route path="/learn/placement" element={<Placement />} />
        <Route path="/learn/scenario" element={<ScenarioHub />} />
        <Route path="/pillar/:id" element={<PillarHub />} />
        <Route path="/learn/speaking" element={<SpeakingPractice />} />
        <Route path="/learn/tactile" element={<TactilePractice />} />
        <Route path="/learn/tactile/hardware" element={<TactilePractice />} />
        <Route path="/hardware/build" element={<HardwareBuild />} />
        <Route path="/learn/sign" element={<Sign />} />
        <Route path="/review/today" element={<ReviewLanding mode="today" />} />
        <Route path="/review/scheduled" element={<Review />} />
        <Route path="/review/mistakes" element={<ReviewLanding mode="mistakes" />} />
        <Route path="/review/speaking" element={<SpeakingReviewLanding />} />
        <Route path="/review/speaking/session" element={<SpeakingPractice />} />
        <Route path="/review/tactile" element={<TactilePractice />} />
        <Route path="/review/saved" element={<Bookmarks />} />
        <Route path="/analysis/overview" element={<AnalysisDetail mode="overview" />} />
        <Route path="/analysis/activity" element={<AnalysisDetail mode="activity" />} />
        <Route path="/analysis/visemes" element={<AnalysisDetail mode="visemes" />} />
        <Route path="/analysis/scores" element={<AnalysisDetail mode="scores" />} />
        <Route path="/analysis/history" element={<AnalysisDetail mode="history" />} />
        <Route path="/learn/closure" element={<Closure />} />
        <Route path="/pronounce" element={<FreeSpeak />} />
        <Route path="/guide" element={<Guide />} />
        <Route path="/dev-viseme" element={<DevViseme />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      </Suspense>
      </div>
      {/* 앱 어디서나 문장 선택 → 수어 번역 (수어 탭 이동 불필요) */}
      <SignSelectionOverlay />
      </>
      </AuthGate>
    </Router>
    </ErrorBoundary>
  )
}

export default App
