import { Component, lazy, Suspense, useState, useEffect, useLayoutEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { MotionConfig } from 'framer-motion'
import ErrorScreen from './components/ErrorScreen'

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(e) { return { error: e } }
  render() {
    const err = this.state.error
    if (!err) return this.props.children
    // 코드분할(lazy) 청크 로드 실패(불안정 통신망)도 여기로 전파된다 → 원본 스택 대신 Figma '문제 발생'
    // 화면(438:103 / 438:143). 이 경계는 라우터 밖이라 버튼은 주소를 직접 바꾼다. 개발 모드에서만 상세 스택을 보여준다.
    return (
      <ErrorScreen kind="error" onRetry={() => window.location.reload()}
        onHome={() => window.location.assign('/learn/path')}>
        {import.meta.env?.DEV && (
          <pre className="mt-2 max-h-[200px] w-full overflow-auto whitespace-pre-wrap text-left text-[11px] text-bad">
            {err?.message}{'\n'}{err?.stack}
          </pre>
        )}
      </ErrorScreen>
    )
  }
}
import useStore from './store/useStore'
import { authAPI, curriculumAPI, seedAPI } from './api'
import SignSelectionOverlay from './components/SignSelectionOverlay'
import A11ySettings from './components/A11ySettings'
import LoadingScreen from './components/LoadingScreen'
import Login from './pages/Login'
import Landing from './pages/Landing'
// Bookmarks는 /review/saved에서만 쓰이므로 지연로딩 —
// 랜딩(로그인) 진입 청크에서 빼 첫 로딩을 가볍게 한다(저사양·불안정 통신망 배려).

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
const Bookmarks = lazy(() => import('./pages/Bookmarks'))
const DevViseme = lazy(() => import('./pages/DevViseme'))
const Sign = lazy(() => import('./pages/Sign'))
const VisemeLiteracy = lazy(() => import('./pages/VisemeLiteracy'))
const WordStage = lazy(() => import('./pages/WordStage'))
const Review = lazy(() => import('./pages/Review'))
const Closure = lazy(() => import('./pages/Closure'))
const SpeakingPractice = lazy(() => import('./pages/SpeakingPractice'))
const FreeSpeak = lazy(() => import('./pages/FreeSpeak'))
const ScenarioHub = lazy(() => import('./pages/ScenarioHub'))
const ReviewLanding = lazy(() => import('./pages/ReviewLanding'))
const SpeakingReviewLanding = lazy(() => import('./pages/SpeakingReviewLanding'))
const AnalysisDetail = lazy(() => import('./pages/AnalysisDetail'))
const EvalReport = lazy(() => import('./pages/EvalReport'))
const ContentReview = lazy(() => import('./pages/ContentReview'))
const PracticeHub = lazy(() => import('./pages/PracticeHub'))
const TasksPage = lazy(() => import('./pages/TasksPage'))
const ReviewTab = lazy(() => import('./pages/ReviewTab'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const AnalysisTab = lazy(() => import('./pages/AnalysisTab'))
const CurriculumPath = lazy(() => import('./pages/CurriculumPath'))
const EndlessPractice = lazy(() => import('./pages/EndlessPractice'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const Legal = lazy(() => import('./pages/Legal'))
const CueVideoDemo = lazy(() => import('./pages/CueVideoDemo'))

/**
 * AuthGate — 로그인 화면 없이 데모 계정으로 자동 입장.
 * 부팅 시 미인증이면 /api/auth/demo로 자동 로그인하고, 완료까지 스플래시를 보인다.
 * 인증 체계 자체는 유지되므로 진행도·북마크 등은 정상 동작한다.
 */
// 미인증에서도 접근 가능한 공개 페이지(약관·처리방침) — 회원가입 동의 문구 링크 대상.
const PUBLIC_PATHS = ['/terms', '/privacy']
function AuthGate({ children }) {
  const isAuthenticated = useStore((s) => s.isAuthenticated)
  const updateUser = useStore((s) => s.updateUser)
  const { pathname } = useLocation()
  useEffect(() => {
    // 재방문(캐시된 인증)에도 서버 최신값으로 user 동기화 — 스트릭 등 stale 방지
    if (isAuthenticated) { authAPI.getMe().then((u) => { if (u) updateUser(u) }).catch(() => {}) }
  }, [isAuthenticated, updateUser])
  // 미인증이면 "/"는 랜딩(Figma 02. Landing 9:12), 그 밖은 로그인 화면(Figma 00, /signup이면 회원가입부터).
  // '둘러보기(데모)'는 로그인 화면에서 즉시 입장. 공개 페이지(약관·처리방침)는 예외.
  // key: /login ↔ /signup을 오가도 Login을 새로 올려 첫 모드가 주소를 따르게 한다.
  if (!isAuthenticated && !PUBLIC_PATHS.includes(pathname)) {
    if (pathname === '/') return <Landing />
    return <Login key={pathname} initialMode={pathname === '/signup' ? 'signup' : 'login'} />
  }
  return children
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
  // 조회 결과는 어느 단계의 것인지와 함께 둔다. 같은 StageGate가 다른 단계 경로(/practice → /conversation)에
  // 재사용돼도 새 단계의 조회가 끝나기 전에는 이전 단계의 허용으로 자식을 그리지 않고 로딩을 보인다.
  const [gate, setGate] = useState({ stage: null, status: 'loading' })   // status: loading | allowed | denied
  useEffect(() => {
    if (isReview) return undefined
    let cancelled = false
    curriculumAPI.getStages()
      .then((data) => {
        const s = (data?.stages || []).find((x) => x.stage === stage)
        const locked = !s || s.status === 'locked' || s.status === 'coming_soon'
        if (!cancelled) setGate({ stage, status: locked ? 'denied' : 'allowed' })
      })
      .catch(() => { if (!cancelled) setGate({ stage, status: 'allowed' }) })
    return () => { cancelled = true }
  }, [stage, isReview])
  const state = isReview ? 'allowed' : gate.stage === stage ? gate.status : 'loading'

  // 단계 조회 대기 = 페이지 전환 로딩 → 기본 로딩 화면(§4-10, 256:34)
  if (state === 'loading') return <LoadingScreen />
  if (state === 'denied') return <Navigate to="/learn/path" replace />
  return children
}

/**
 * 첫 화면: 서버의 배치 여부(/api/curriculum/stages의 placed)로 정한다. 배치 전이면 온보딩, 아니면 학습 경로.
 * 예전에는 브라우저 전체에 하나인 localStorage 표시(liplab_onboarded)를 봐서, 공용 태블릿의 다음 사람이 온보딩을
 * 건너뛰고 배치 없이 학습 경로에 들어갔다. 조회 중에는 기본 로딩, 실패하면 학습 경로로 보낸다(가용성 우선).
 * 다시 '/'로 오면(로그인 직후 데모 기록 채우기가 끝난 뒤 등) 새로 조회한다.
 */
function HomeRedirect() {
  const { key } = useLocation()
  const [to, setTo] = useState(null)
  useEffect(() => {
    let cancelled = false
    setTo(null)
    curriculumAPI.getStages()
      .then((data) => { if (!cancelled) setTo(data?.placed === false ? '/onboarding' : '/learn/path') })
      .catch(() => { if (!cancelled) setTo('/learn/path') })
    return () => { cancelled = true }
  }, [key])
  if (!to) return <LoadingScreen />
  return <Navigate to={to} replace />
}

/**
 * 본문으로 건너뛰기: 셸 화면은 AppShell의 <main id="main-content">(사이드바 다음)로 포커스를 옮긴다.
 * 셸이 없는 화면(레슨·온보딩 등)은 그 화면의 <main>, 없으면 화면 영역(#app-content) 처음으로 옮긴다.
 * 주소에 #을 붙이지 않고 포커스만 옮겨, 라우터가 새 주소로 보고 맨 위로 스크롤하지 않게 한다.
 */
function SkipLink() {
  const skip = (e) => {
    const root = document.getElementById('app-content')
    const target = document.getElementById('main-content') || root?.querySelector('main') || root
    if (!target) return
    e.preventDefault()
    if (!target.hasAttribute('tabindex')) {
      target.setAttribute('tabindex', '-1')
      target.classList.add('outline-none')   // 본문 전체에 포커스 테두리를 그리지 않는다
    }
    target.focus()
  }
  return <a href="#main-content" className="skip-link" onClick={skip}>본문으로 건너뛰기</a>
}

/**
 * 앱 어디서나 떠 있는 요소 — 문장 선택 → 수어 번역, 접근성 설정.
 * 공개 페이지(약관·처리방침)에서는 수어 첫 방문 안내 모달이 약관을 가리지 않도록 수어 오버레이를 뺀다.
 * 접근성 설정은 글자 크게·고대비를 약관에도 적용해야 하므로 남긴다.
 */
function GlobalOverlays() {
  const { pathname } = useLocation()
  return (
    <>
      {!PUBLIC_PATHS.includes(pathname) && <SignSelectionOverlay />}
      <A11ySettings />
    </>
  )
}

/** 없는 주소(Figma 404 438:83 / 438:123): 예전에는 학습 경로로 조용히 돌려보냈다(변경 내역 §1). */
function NotFound() {
  const navigate = useNavigate()
  return <ErrorScreen kind="notfound" onHome={() => navigate('/learn/path')} />
}

/**
 * Main App component with routing
 */
function App() {
  return (
    <ErrorBoundary>
    {/* 동작 최소화 설정 시 framer-motion 애니메이션을 OS 설정에 맞춰 자동 축소(접근성) */}
    <MotionConfig reducedMotion="user">
    <Router>
      <ScrollToTop />
      <AuthGate>
      <>
      <SkipLink />
      {/* 화면 영역. <main>은 AppShell(셸 화면)이나 각 화면이 둔다(여기서 감싸면 셸의 <main>과 겹친다). */}
      <div id="app-content" className="app-shell">
      <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/dashboard" element={<Navigate to="/learn/path" replace />} />
        <Route path="/practice" element={<StageGate stage={3}><Practice /></StageGate>} />
        <Route path="/conversation" element={<StageGate stage={4}><Conversation /></StageGate>} />
        <Route path="/sign" element={<Sign />} />
        <Route path="/learn/viseme" element={<VisemeLiteracy />} />
        <Route path="/learn/word" element={<StageGate stage={2}><WordStage /></StageGate>} />
        <Route path="/learn/conversation-multi" element={<MultiConversation />} />
        <Route path="/learn/placement" element={<Placement />} />
        <Route path="/learn/scenario" element={<ScenarioHub />} />
        <Route path="/learn/speaking" element={<SpeakingPractice />} />
        <Route path="/learn/sign" element={<Sign />} />
        {/* 복습·분석 탭 — 새 Figma 화면을 대표 경로로 */}
        <Route path="/review" element={<ReviewTab />} />
        <Route path="/analysis" element={<AnalysisTab />} />
        {/* 구 경로 → 새 대표 경로 리다이렉트(신구 화면 혼재 방지) */}
        <Route path="/review/hub" element={<Navigate to="/review" replace />} />
        <Route path="/review/today" element={<Navigate to="/review" replace />} />
        <Route path="/analysis/hub" element={<Navigate to="/analysis" replace />} />
        <Route path="/analysis/overview" element={<Navigate to="/analysis" replace />} />
        {/* 새 화면 안에서 '더 보기'로 진입하는 상세 경로 — 유지 */}
        <Route path="/review/scheduled" element={<Review />} />
        <Route path="/review/mistakes" element={<ReviewLanding mode="mistakes" />} />
        <Route path="/review/speaking" element={<SpeakingReviewLanding />} />
        <Route path="/review/speaking/session" element={<SpeakingPractice />} />
        <Route path="/review/saved" element={<Bookmarks />} />
        <Route path="/analysis/activity" element={<AnalysisDetail mode="activity" />} />
        <Route path="/analysis/visemes" element={<AnalysisDetail mode="visemes" />} />
        <Route path="/analysis/scores" element={<AnalysisDetail mode="scores" />} />
        <Route path="/analysis/history" element={<AnalysisDetail mode="history" />} />
        <Route path="/analysis/eval" element={<EvalReport />} />
        <Route path="/admin/content-review" element={<ContentReview />} />
        <Route path="/practice/hub" element={<PracticeHub />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/learn/path" element={<CurriculumPath />} />
        <Route path="/learn/endless" element={<EndlessPractice />} />
        <Route path="/learn/closure" element={<Closure />} />
        <Route path="/pronounce" element={<FreeSpeak />} />
        <Route path="/dev-viseme" element={<DevViseme />} />
        <Route path="/lab/cue-video" element={<CueVideoDemo />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/terms" element={<Legal />} />
        <Route path="/privacy" element={<Legal />} />
        <Route path="/" element={<HomeRedirect />} />
        {/* 로그인한 채 /login·/signup에 오면 첫 화면으로(로그인 뒤 이동 경로) */}
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/signup" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      </Suspense>
      </div>
      {/* 앱 어디서나 문장 선택 → 수어 번역 (수어 탭 이동 불필요) + 접근성 설정 */}
      <GlobalOverlays />
      </>
      </AuthGate>
    </Router>
    </MotionConfig>
    </ErrorBoundary>
  )
}

export default App
