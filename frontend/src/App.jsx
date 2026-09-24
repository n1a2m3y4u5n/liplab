import { Component, lazy, Suspense, useState, useEffect, useLayoutEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { MotionConfig } from 'framer-motion'

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
      <div className="flex min-h-[100dvh] items-center justify-center bg-page p-6 text-center">
        <div className="flex max-w-[420px] flex-col items-center gap-2">
          <h1 className="text-[18px] font-bold text-ink">
            {isChunk ? '페이지를 불러오지 못했어요' : '문제가 발생했어요'}
          </h1>
          <p className="mb-2 text-[14px] text-ink-muted">
            {isChunk ? '네트워크가 불안정할 수 있어요. 새로고침 해주세요.' : '잠시 후 다시 시도해 주세요.'}
          </p>
          <button type="button" onClick={() => window.location.reload()} className="btn-primary">
            새로고침
          </button>
          {import.meta.env?.DEV && (
            <pre className="mt-2 max-h-[200px] w-full overflow-auto whitespace-pre-wrap text-left text-[11px] text-bad">
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
import A11ySettings from './components/A11ySettings'
import LoadingScreen from './components/LoadingScreen'
import Login from './pages/Login'
// Bookmarks·Guide는 /review/saved·/guide에서만 쓰이므로 지연로딩 —
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
const Guide = lazy(() => import('./pages/Guide'))
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
  // 미인증이면 로그인 화면(Figma 00). '둘러보기(데모)'로 즉시 입장. 단 공개 페이지는 예외.
  if (!isAuthenticated && !PUBLIC_PATHS.includes(pathname)) return <Login />
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

  // 단계 조회 대기 = 페이지 전환 로딩 → 기본 로딩 화면(§4-10, 256:34)
  if (state === 'loading') return <LoadingScreen />
  if (state === 'denied') return <Navigate to="/learn/path" replace />
  return children
}

function HomeRedirect() {
  let onboarded = false
  try { onboarded = localStorage.getItem('liplab_onboarded') === '1' } catch { /* 무시 */ }
  return <Navigate to={onboarded ? '/learn/path' : '/onboarding'} replace />
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

/** 부팅 스플래시 (Figma 08) — 세션당 1회, 앱 진입 시 브랜드 스플래시를 잠깐 보여준다. */
function BootSplash() {
  const [show, setShow] = useState(() => {
    try { return sessionStorage.getItem('liplab_booted') !== '1' } catch { return true }
  })
  useEffect(() => {
    if (!show) return
    const t = setTimeout(() => {
      setShow(false)
      try { sessionStorage.setItem('liplab_booted', '1') } catch { /* 무시 */ }
    }, 1300)
    return () => clearTimeout(t)
  }, [show])
  if (!show) return null
  return <div className="fixed inset-0 z-[100]"><LoadingScreen variant="brand" /></div>
}

/**
 * Main App component with routing
 */
function App() {
  return (
    <ErrorBoundary>
    {/* 동작 최소화 설정 시 framer-motion 애니메이션을 OS 설정에 맞춰 자동 축소(접근성) */}
    <MotionConfig reducedMotion="user">
    <BootSplash />
    <Router>
      <ScrollToTop />
      <AuthGate>
      <>
      <a href="#main-content" className="skip-link">본문으로 건너뛰기</a>
      <main id="main-content" className="app-shell">
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
        <Route path="/guide" element={<Guide />} />
        <Route path="/dev-viseme" element={<DevViseme />} />
        <Route path="/lab/cue-video" element={<CueVideoDemo />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/terms" element={<Legal />} />
        <Route path="/privacy" element={<Legal />} />
        <Route path="/" element={<HomeRedirect />} />
        <Route path="*" element={<Navigate to="/learn/path" replace />} />
      </Routes>
      </Suspense>
      </main>
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
