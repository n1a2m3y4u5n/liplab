# LIPLAB 리디자인 — 구현 지시 문서

> 이 문서는 Claude Code(VS Code)에게 구조 개편 작업을 지시하기 위한 스펙입니다.
> **디자인(색상/타이포/간격/비주얼)은 Figma에서 별도로 확정하며, 이 문서는 다루지 않습니다.**
> 이 문서는 **정보구조(IA), 컴포넌트 아키텍처, 라우팅, 데이터 흐름, 브랜치 전략**을 다룹니다.
>
> **기준 브랜치/시점**: `feat/content-scaleUI` (2026-09-15 기준 최신 커밋 `082bf7f`). 이 문서를 다시 참고하기 전에 `git log -1`로 기준 커밋과 실제 작업 브랜치가 일치하는지 먼저 확인할 것 — 팀 브랜치가 빠르게 바뀌는 프로젝트이므로 오래된 스냅샷 기준 문서로 작업하면 이번처럼 촉각 트랙 같은 삭제된 기능이 문서에 남아있을 수 있음.
> **중요 변경사항**: 촉각(타도마) 트랙은 **완전히 제거됨** (팀 결정, 2026-09-15). 이 문서의 학습 트랙은 **독화·말하기 2개**로 확정. `TactilePractice.jsx`, `HardwareBuild.jsx`, `TactileFaceSim.jsx`는 저장소에서 이미 삭제된 상태.

---

## 0. 배경 및 목표

- 기존 LIPLAB은 독화(입모양 읽기)·말하기 2개 학습 트랙(촉각/타도마 트랙은 팀 결정으로 제거됨) + 대시보드 + 복습 + 분석으로 구성된 React(Vite) SPA.
- 현재 `frontend/src/pages/`에 24개 페이지가 평면적으로 흩어져 있고, 트랙마다 화면 패턴이 제각각 구현되어 있음(`WordStage.jsx`, `VisemeLiteracy.jsx`, `ScenarioHub.jsx`, `PillarHub.jsx` 등).
- **목표**: "듀오링고류(게임화 학습 플랫폼)"에 가까운 사용자 경험으로 전체 구조를 재편. 단, 듀오링고의 특정 UI(구불구불한 경로형 스킬트리)를 그대로 베끼는 것이 아니라, **잘 만들어진 게임화 학습 플랫폼의 구조적 특징**(일관된 레슨 패턴, 명확한 진행도 표시, 보상 피드백, 신뢰감 있는 분석 화면)을 LIPLAB 맥락에 맞게 적용.
- **팀 협업 제약**: 다른 팀원들이 별도 브랜치에서 기존 컴포넌트를 계속 수정 중. 구조 개편이 전체 파일을 건드리면 merge 충돌이 크게 날 위험이 있음 → **브랜치 전략 섹션(9번) 필수 준수**.

---

## 1. 현재 구조 진단 (AS-IS)

### 1.1 현재 페이지 목록 (`frontend/src/pages/`, 2026-09-15 최신 기준)

| 파일 | 역할(추정) |
|---|---|
| Dashboard.jsx | 홈. 프로필 카드, 오늘의 과제, 히어로 배너, 복습 섹션, 캘린더 모두 포함 (과밀, 분리 대상) |
| Practice.jsx | 독화 연습 세션 |
| Conversation.jsx / MultiConversation.jsx | 대화 시뮬레이션 |
| Sign.jsx | 수어 관련 (현재 라우팅엔 `/learn/sign` 하나만 남음) |
| VisemeLiteracy.jsx | 입모양(viseme) 문해 학습 |
| WordStage.jsx | 단어 단계 학습 |
| Placement.jsx | 레벨 배치고사 |
| ScenarioHub.jsx / PillarHub.jsx | 시나리오/영역별 허브 (소규모) |
| SpeakingPractice.jsx | 말하기 연습 |
| FreeSpeak.jsx | 자유 발화 |
| ReviewLanding.jsx / Review.jsx / SpeakingReviewLanding.jsx | 복습 계열 3종 |
| Bookmarks.jsx | 북마크 모음 |
| AnalysisDetail.jsx | 분석 (mode prop으로 overview/activity/visemes/scores/history 5종 분기) |
| **EvalReport.jsx** | **(신규)** 학습 효과 증빙 리포트 — 개인별 학습곡선, 단계 도달 시행수, 초기 대비 향상도. 공모전 평가/효과성 근거용. `evalAPI` 사용 |
| Closure.jsx | 학습 마무리 |
| Guide.jsx | 사용법 안내 |
| DevViseme.jsx | 개발자 도구 페이지 |

> ❌ **제거됨 (더 이상 존재하지 않음)**: `TactilePractice.jsx`, `HardwareBuild.jsx`, `TactileFaceSim.jsx`(components) — 촉각(타도마) 트랙 자체가 팀 결정으로 삭제됨. 이 문서의 나머지 모든 섹션에서 "3개 트랙"이 아니라 **"독화·말하기 2개 트랙"**으로 읽을 것.

### 1.2 현재 문제점

1. **화면 패턴 중복 구현**: "레슨 목록 보기 → 레슨 진행 → 완료 화면" 흐름이 트랙마다(`WordStage`, `VisemeLiteracy`, `SpeakingPractice`) 개별적으로 구현되어 있어 공통 컴포넌트가 없음.
2. **Dashboard.jsx 과밀**: 프로필, 캘린더, 복습, 히어로 배너, 다음 학습 카드가 한 파일 안에 내부 함수형 컴포넌트로 다 들어있음 (`ActivityCalendar`, `ReviewSection`, `NextUpCard`, `LearnerProfileCard`). 실제 파일 줄 수는 작업 시작 전 `wc -l`로 재확인할 것(리팩토링이 진행 중이라 계속 바뀜).
3. **Review 계열 3분화**: `ReviewLanding`, `Review`, `SpeakingReviewLanding`이 모드별로 나뉘어 있어 일관성 부족.
4. **AnalysisDetail 단일 파일 5분기**: mode prop으로 5개 화면을 한 파일에서 처리 — 각 분석 화면의 독립적 발전이 어려움.
5. **전역 요소 파편화**: `GlobalLearningMenu`, `SignSelectionOverlay`가 App.jsx 레벨에 있지만 상단바/내비게이션 자체의 통일된 컴포넌트가 안 보임(파일 목록 기준 — 실제 위치는 3장에서 팀이 확인 필요).

### 1.3 유지해야 하는 기존 자산 (절대 갈아엎지 말 것)

- **`store/useStore.js` (Zustand)**: 인증 상태, 학습 세션 상태(currentScenario, currentSentence 등) 관리. 로직 유지, 필요시 슬라이스 분리만 고려.
- **`api.js`의 API 그룹**: `authAPI`, `learningAPI`, `curriculumAPI`, `scoreAPI`, `reviewAPI`, `speakAPI`, `seedAPI`, `evalAPI` — 백엔드 계약이므로 엔드포인트 구조 변경 금지. (`tactileAPI`는 촉각 트랙 제거와 함께 이미 삭제됨, 되살리지 말 것)
- **`StageGate` 컴포넌트 (App.jsx 내부)**: 순차 해금 로직. 재사용은 하되 **경로형 UI로 억지로 감싸지 않는다** (사용자 확인: 듀오링고의 시각적 경로 UI를 그대로 복제하지 않음).
- **`AuthGate`**: 데모 계정 자동 로그인 흐름.
- **3D 아바타 컴포넌트군** (`AvatarVRM`, `LipSyncPlayer3D`, `MouthAvatar`, `MouthFallback2D`, `MouthMirror`, `WebcamMouthCheck`): LIPLAB의 핵심 차별화 기능. 리디자인 대상이 아니라 **새 레이아웃 안에 재배치**하는 대상. (`TactileFaceSim`은 촉각 트랙 제거와 함께 이미 삭제됨)
- **lazy loading 경계**: 3D(Three.js)를 쓰는 페이지들은 현재도 지연로딩 처리되어 있음(App.jsx 57~81행 주석 참고). 새 구조에서도 이 경계는 유지.

---

## 2. 새 정보구조 (TO-BE)

### 2.1 최상위 5개 섹션

```
홈(대시보드) — 진입점, 오늘 할 일 요약, 전체 진행도 스냅샷
├── 학습 — 독화 / 말하기 2개 트랙 (촉각은 제거됨, 1.1 참고)
├── 복습 — 오늘 복습 · 오답노트 · 북마크 (기존 3분화된 Review 계열 통합)
├── 분석 — 진도 개요 · 활동 캘린더 · 항목별 정확도 · 히스토리 · 학습효과 리포트(EvalReport, 신규)
└── 설정 — 프로필 · 사용법 가이드
```

### 2.2 전역 요소 (모든 화면 공통, 최우선 구현 대상)

- **상단 바(TopBar)**: 로고, 스트릭 카운터, XP/레벨 표시, 캐릭터 미니 위젯, 알림/도움말 아이콘
- **내비게이션(NavShell)**: 홈/학습/복습/분석/설정 5개 진입점. 데스크탑은 좌측 사이드바 또는 상단 탭, 모바일은 하단 탭바 — **레이아웃 형태는 Figma에서 결정, 여기서는 "5개 항목 고정"이라는 정보구조만 확정**.
- **전역 오버레이**: 기존 `SignSelectionOverlay`(문장 선택 시 수어 번역) 유지.

### 2.3 학습 트랙 공통 화면 패턴 (신규 도입 — 가장 중요한 변경)

현재 트랙마다 제각각인 구조를,  **4단계 공통 패턴**으로 통일한다:

```
트랙 허브 (TrackHub)
  → 레슨 목록 (LessonList)
    → 레슨 진행 (LessonRunner)
      → 완료 요약 (LessonComplete)
```

- **TrackHub**: 트랙 소개 + 현재 진행도 + "이어하기" CTA. 기존 `PillarHub`, `ScenarioHub`가 이 역할의 원형.
- **LessonList**: 해당 트랙의 레슨/스테이지 목록. `StageGate`의 locked/unlocked 상태를 시각적으로 표시.
- **LessonRunner**: 실제 학습 진행 화면. 트랙별 상이한 인터랙션(입모양 인식, 발화 인식)은 이 컴포넌트 내부에서 **children/slot 패턴**으로 분기.
- **LessonComplete**: 정답률, 획득 XP, 스트릭 갱신, 다음 추천 레슨 안내.

이 패턴을 공통 컴포넌트로 뽑으면 트랙별 세부 로직(문제, 판정 알고리즘)만 팀원들이 각자 작업해도 레이아웃/진행 흐름은 안전하게 재사용됨 → **9장 브랜치 전략과 직결**.

---

## 3. 디렉토리 구조 제안

```
frontend/src/
├── layouts/                    # 신규
│   ├── TopBar.jsx
│   ├── NavShell.jsx
│   └── AppLayout.jsx           # TopBar + NavShell + <Outlet/> 감싸는 최상위 레이아웃
│
├── features/                   # 신규 — 섹션별로 묶기 (기존 pages/ 평면구조 대체)
│   ├── dashboard/
│   │   ├── Dashboard.jsx       # 기존 787줄에서 아래 컴포넌트로 분리
│   │   ├── ActivityCalendar.jsx
│   │   ├── LearnerProfileCard.jsx
│   │   ├── NextUpCard.jsx
│   │   └── TodayTasksCard.jsx  # 기존 오늘의 과제 리스트 분리
│   │
│   ├── learn/
│   │   ├── shared/             # 트랙 공통 4단계 패턴
│   │   │   ├── TrackHub.jsx
│   │   │   ├── LessonList.jsx
│   │   │   ├── LessonRunner.jsx
│   │   │   └── LessonComplete.jsx
│   │   ├── lipreading/         # 기존 VisemeLiteracy, WordStage, Practice 등 재배치
│   │   └── speaking/           # 기존 SpeakingPractice, FreeSpeak 재배치
│   │        # ❌ tactile/ 폴더 없음 — 촉각 트랙 제거됨(1.1 참고), 새로 만들지 말 것
│   │
│   ├── review/
│   │   ├── ReviewHub.jsx       # 기존 ReviewLanding + Review + SpeakingReviewLanding 통합 진입점
│   │   ├── TodayReview.jsx
│   │   ├── MistakeReview.jsx
│   │   └── Bookmarks.jsx
│   │
│   ├── analysis/
│   │   ├── AnalysisOverview.jsx
│   │   ├── AnalysisActivity.jsx
│   │   ├── AnalysisVisemes.jsx
│   │   ├── AnalysisScores.jsx
│   │   ├── AnalysisHistory.jsx  # 기존 AnalysisDetail mode 분기를 파일 분리
│   │   └── EvalReport.jsx       # 신규 — 학습효과 증빙 리포트, evalAPI 사용, 기존 파일명 그대로 이동
│   │
│   └── account/
│       └── Guide.jsx
│        # ❌ HardwareBuild.jsx 없음 — 삭제된 파일, 이전하지 말 것
│
├── components/                 # 기존 유지 — 3D 아바타, 공용 UI 컴포넌트
│   └── (기존 파일 그대로: AvatarVRM.jsx, LipSyncPlayer3D.jsx 등)
│
├── store/                      # 기존 유지
├── lib/                        # 기존 유지
├── hooks/                      # 기존 유지
├── config/                     # 기존 유지
├── api.js                      # 기존 유지 — 절대 수정 금지 (엔드포인트 계약)
├── App.jsx                     # 라우팅 정의부만, 아래 4장 반영
└── main.jsx
```

> **팀원 참고**: `pages/` 폴더를 하루아침에 삭제하지 않는다. 4장의 마이그레이션 전략을 따를 것.

---

## 4. 라우팅 재설계

### 4.1 신규 라우트 트리 (React Router)

```jsx
<Route element={<AppLayout />}>           {/* TopBar + NavShell 공통 레이아웃 */}
  <Route path="/" element={<Navigate to="/dashboard" replace />} />
  <Route path="/dashboard" element={<Dashboard />} />

  <Route path="/learn/:track" element={<TrackHub />} />           {/* track: lipreading | speaking (촉각 제거됨) */}
  <Route path="/learn/:track/lessons" element={<LessonList />} />
  <Route path="/learn/:track/lesson/:lessonId" element={<StageGate><LessonRunner /></StageGate>} />
  <Route path="/learn/:track/complete/:lessonId" element={<LessonComplete />} />

  <Route path="/review" element={<ReviewHub />} />
  <Route path="/review/today" element={<TodayReview />} />
  <Route path="/review/mistakes" element={<MistakeReview />} />
  <Route path="/review/saved" element={<Bookmarks />} />

  <Route path="/analysis" element={<Navigate to="/analysis/overview" replace />} />
  <Route path="/analysis/overview" element={<AnalysisOverview />} />
  <Route path="/analysis/activity" element={<AnalysisActivity />} />
  <Route path="/analysis/visemes" element={<AnalysisVisemes />} />
  <Route path="/analysis/scores" element={<AnalysisScores />} />
  <Route path="/analysis/history" element={<AnalysisHistory />} />
  <Route path="/analysis/eval" element={<EvalReport />} />         {/* 신규, 기존 경로 그대로 */}

  <Route path="/account/guide" element={<Guide />} />
</Route>

<Route path="*" element={<Navigate to="/dashboard" replace />} />
```

### 4.2 구 URL → 신 URL 매핑 (리다이렉트 필수)

기존에 배포된 링크/북마크가 깨지지 않도록, 구 경로는 신 경로로 `<Navigate>` 리다이렉트 처리:

| 구 경로 | 신 경로 |
|---|---|
| `/practice` | `/learn/lipreading/lessons` |
| `/conversation` | `/learn/lipreading/lesson/conversation` (실제 lessonId는 팀 확인) |
| `/learn/viseme` | `/learn/lipreading/lesson/viseme` |
| `/learn/word` | `/learn/lipreading/lesson/word` |
| `/learn/speaking` | `/learn/speaking` |
| `/review/today` | `/review/today` (동일) |
| `/review/mistakes` | `/review/mistakes` (동일) |
| `/review/saved` | `/review/saved` (동일) |
| `/review/scheduled` | `/review/today` 로 통합 검토 |
| `/review/speaking`, `/review/speaking/session` | `/review/mistakes?track=speaking` 형태 검토 |
| `/analysis/*` (overview·activity·visemes·scores·history) | 동일 유지 |
| `/analysis/eval` | 동일 유지 (신규 페이지, 이미 이 경로) |
| `/guide` | `/account/guide` |
| `/pronounce` | `/learn/speaking` 내부로 통합 검토 |
| `/learn/sign` | 별도 트랙 유지할지, 학습 트랙 내 기능으로 흡수할지 **팀 논의 필요** (미결정 항목, 5장 참고) |
| `/dev-viseme` | 유지 (개발 전용, 라우팅 노출 안 함) |

> ❌ **삭제된 라우트라 매핑 불필요**: `/tactile`, `/learn/tactile`, `/learn/tactile/hardware`, `/hardware/build`, `/review/tactile` — 촉각 트랙 제거로 App.jsx에서 이미 사라짐. 새 라우팅에도 만들지 말 것.

> ⚠️ 이 매핑표는 초안입니다. 실제 백엔드 API 호출 경로(`api.js`)와는 무관하며, 프론트 라우팅에만 해당합니다. 팀 확정 후 표를 갱신하세요.

---

## 5. 미결정 항목 (팀 논의 필요 — 코드 작성 전 확정할 것)

1. **`/sign` (수어) 트랙의 위치**: 독립된 4번째 학습 트랙으로 승격할지, 기존처럼 전역 오버레이 기능(문장 선택 → 수어 번역)으로만 남길지.
2. **`Closure.jsx`(학습 마무리)의 역할**: `LessonComplete`와 통합 가능한지, 별도의 "트랙 전체 완주" 화면인지 확인 필요.
3. **`Placement.jsx`(배치고사)의 진입 시점**: 온보딩 최초 1회만인지, 언제든 재응시 가능한지에 따라 라우팅 위치가 `/onboarding/placement`가 될 수도, `/learn/placement`로 남을 수도 있음.
4. **모바일/데스크탑 내비게이션 형태**: 하단 탭바 vs 사이드바 — Figma 작업과 함께 결정.
5. **레슨 ID 체계**: `LessonList → LessonRunner`로 넘어갈 때 사용할 lessonId의 실제 발급 방식(백엔드 `curriculumAPI.getStages()` 응답 구조 확인 필요).

---

## 6. 컴포넌트 설계 상세

### 6.1 `AppLayout.jsx` (신규, 최우선 구현)

```jsx
// 모든 라우트를 감싸는 최상위 레이아웃.
// TopBar + NavShell을 한 번만 렌더링하고, 나머지는 <Outlet/>으로 위임.
// 기존 App.jsx의 <GlobalLearningMenu/>, <SignSelectionOverlay/>는
// 이 레이아웃 레벨 또는 그 바깥(Router 최상위)에 유지 — 3장 참고하여 팀이 위치 확정.

function AppLayout() {
  return (
    <div className="app-shell">
      <TopBar />
      <NavShell />
      <main>
        <Outlet />
      </main>
    </div>
  )
}
```

**구현 시 주의**:
- 기존 `app-shell` 클래스명 그대로 유지 (전역 CSS 재활용).
- `TopBar`가 표시할 데이터(스트릭, XP, 유저명)는 기존 `useStore`의 `user` 상태에서 그대로 가져올 것 — 새 API 호출 만들지 말 것.

### 6.2 학습 트랙 공통 패턴 (가장 중요)

```jsx
// features/learn/shared/TrackHub.jsx
// props로 track('lipreading'|'speaking')을 받아 (촉각 트랙 제거됨)
// 해당 트랙의 진행도 요약 + 레슨 목록 진입 CTA를 렌더링.
// 트랙별 차이(아이콘, 소개문구)는 config 객체로 분리해 하드코딩 방지.

// config/tracks.js (신규 파일 제안)
// ❌ 촉각(tactile) 트랙은 제거됨 — 항목 추가하지 말 것
export const TRACKS = {
  lipreading: { label: '독화', hubTitle: '입모양으로 읽어요', apiNamespace: 'learningAPI' },
  speaking:   { label: '말하기', hubTitle: '소리 내어 말해요', apiNamespace: 'speakAPI' },
}
```

```jsx
// features/learn/shared/LessonRunner.jsx
// 트랙 공통 뼈대(진행바, 문제 카드 영역, 하단 답변 인터랙션 영역)만 갖고,
// 실제 인터랙션 컴포넌트는 slot으로 주입받는다.

function LessonRunner({ track, lessonId }) {
  const InteractionComponent = TRACK_INTERACTIONS[track]  // 트랙별 실제 연습 컴포넌트 매핑
  return (
    <div className="lesson-runner">
      <ProgressBar />
      <InteractionComponent lessonId={lessonId} />
      <AnswerControls />
    </div>
  )
}
```

> 이렇게 하면 독화팀/말하기팀이 각자 `TRACK_INTERACTIONS` 안의 자기 컴포넌트만 건드리면 되고, `LessonRunner.jsx` 자체(레이아웃)는 거의 안 바뀜 → 충돌 최소화.

### 6.3 `Dashboard.jsx` 분리

기존 파일 내부의 함수형 컴포넌트 4개(`ActivityCalendar`, `ReviewSection`, `NextUpCard`, `LearnerProfileCard`)를 각각 별도 파일로 추출.

- 이 작업은 **로직 변경 없이 파일만 쪼개는 순수 리팩토링**으로 진행할 것 (동작 동일해야 함).
- 분리 후 `Dashboard.jsx`는 레이아웃 조립 역할만 하도록 축소.

### 6.4 `AnalysisDetail.jsx` 분리

기존 `mode` prop 분기(`overview`/`activity`/`visemes`/`scores`/`history`)를 5개 파일로 분리.

- 공통으로 쓰이는 로직(데이터 fetch, 로딩/에러 상태)이 있다면 `useAnalysisData(mode)` 같은 커스텀 훅으로 추출해 중복 방지.

---

## 7. 상태 관리 (Zustand) 변경 범위

- **변경 금지**: 인증 관련 슬라이스(`user`, `token`, `isAuthenticated`, `setAuth`, `logout`).
- **검토 대상**: `currentScenario`, `currentSentence`, `currentSentenceIndex`, `practiceMode` — 이 필드들이 특정 트랙(기존 Practice/Conversation)에 종속된 이름이라, 신규 `LessonRunner` 공통 패턴에서 트랙 무관하게 쓰려면 이름을 일반화할지 검토:
  - 예: `currentScenario` → `currentLesson`, `practiceMode` → `lessonMode`
  - **주의**: 이름을 바꾸면 이 필드를 참조하는 모든 기존 컴포넌트를 함께 수정해야 하므로, 이 작업은 **9장의 "구조 변경 브랜치"에서 가장 먼저, 단독으로** 처리할 것. 다른 팀원이 이 필드명을 쓰는 새 코드를 짜기 전에 끝내야 함.

---

## 8. API 연동 원칙

- `api.js`의 API 그룹(`authAPI`, `learningAPI`, `curriculumAPI`, `scoreAPI`, `reviewAPI`, `speakAPI`, `seedAPI`, `evalAPI`)은 **엔드포인트/함수 시그니처 변경 금지**.
- 새 컴포넌트(`TrackHub`, `LessonList` 등)는 기존 API 함수를 그대로 호출. 트랙별 분기가 필요하면 `config/tracks.js`의 `apiNamespace`를 참조해 동적으로 매핑(6.2 참고).
- 백엔드(FastAPI) 쪽 변경은 이 스펙 범위 밖 — 프론트 구조 개편만으로 완결되게 설계되어 있음. 만약 백엔드 응답 구조 자체를 바꿔야 하는 상황이 생기면 **즉시 팀 채팅으로 공유하고 이 문서를 갱신**.

---

## 9. 브랜치 전략 (충돌 방지 — 반드시 준수)

### 9.1 기본 원칙

> 다른 팀원들이 기존 파일을 계속 수정 중이므로, 구조 개편은 **"먼저, 짧게, 단독으로"** 처리하고 최대한 빨리 main에 merge한다. 오래 끌수록 충돌 범위가 기하급수적으로 커진다.

### 9.2 작업 순서 (이 순서를 반드시 지킬 것)

1. **1단계 — 레이아웃 뼈대만 (1~2일 내 완료 목표)**
   - `layouts/AppLayout.jsx`, `TopBar.jsx`, `NavShell.jsx` 신규 생성
   - `App.jsx` 라우팅을 4.1의 새 트리로 교체 (단, 각 라우트가 렌더링하는 컴포넌트는 **당장은 기존 `pages/*.jsx`를 그대로 import** — 아직 옮기지 않음)
   - 이 상태로 즉시 PR 올리고 리뷰 요청 → merge
   - **이유**: 이 레이어가 가장 많은 사람이 공유하는 공통 자산이라, 가장 먼저 고정시켜야 다른 브랜치들이 여기에 맞춰 rebase 가능.

2. **2단계 — Strangler 패턴으로 점진 이전**
   - 기존 `pages/Dashboard.jsx`를 직접 고치지 말고, `features/dashboard/Dashboard.jsx`를 **새로 생성**.
   - 새 파일이 완성되면 라우팅에서 import 경로만 교체 (`pages/Dashboard` → `features/dashboard/Dashboard`).
   - 기존 `pages/Dashboard.jsx`는 아무도 안 쓰게 된 후에 삭제 (다른 팀원이 그 사이 기존 파일을 고쳤어도 이미 안 쓰는 파일이라 충돌 없음).
   - 이 패턴을 모든 페이지에 반복 적용.

3. **3단계 — 공통 패턴(6.2) 우선 구현**
   - `features/learn/shared/` 4개 컴포넌트를 먼저 완성해서 merge.
   - 이후 독화/말하기 트랙 세부 구현은 **팀원별로 별도 브랜치에서 병렬 진행 가능** — 각자 `TRACK_INTERACTIONS` 매핑 객체에 자기 컴포넌트만 등록하면 되므로 서로 다른 파일을 건드림 → 충돌 안 남.

4. **4단계 — 상태 관리 필드명 변경(7장)은 1단계와 함께, 최대한 빨리**
   - 이 변경은 여러 파일에 걸쳐 참조되므로 뒤로 미룰수록 위험. 1단계 작업과 같은 PR 또는 바로 다음 PR로 처리.

### 9.3 Git 실무 명령어

```bash
# 작업 시작 전 항상 최신 main 기준
git checkout main && git pull
git checkout -b refactor/app-shell-routing   # 1단계용 브랜치

# 작업 중간중간 main의 변경사항을 계속 흡수 (충돌을 작은 단위로 미리 해결)
git fetch origin main
git rebase origin/main

# 1단계 완료 후 즉시 PR → 리뷰 → merge
# 이후 2단계는 새 브랜치에서
git checkout main && git pull
git checkout -b feature/dashboard-migration
```

### 9.4 커밋 단위 원칙

- "구조 이동"과 "로직 변경"을 같은 커밋에 섞지 않는다. 파일을 옮기기만 하는 커밋과, 그 안의 로직을 바꾸는 커밋을 분리하면 리뷰어가 diff를 읽기 쉽고, 충돌 발생 시 원인 파악이 쉬움.
- 예시:
  - `refactor: move Dashboard sub-components to features/dashboard/ (no logic change)`
  - `feat: extract ActivityCalendar as standalone component`

---

## 10. Figma 연동 지점 (디자인 작업과의 접점)

- 이 문서의 컴포넌트 단위(`TopBar`, `NavShell`, `TrackHub`, `LessonList`, `LessonRunner`, `LessonComplete`, 대시보드 하위 카드들)가 **Figma에서 만들 프레임/컴포넌트 단위와 1:1 대응**하도록 이름을 맞춰서 작업하면, 이후 Figma Dev Mode에서 값을 가져와 코드에 반영할 때 어느 컴포넌트에 어떤 스타일을 적용해야 할지 헷갈리지 않음.
- 즉, **Figma 쪽 페이지/프레임 이름도 이 문서의 컴포넌트명(TopBar, TrackHub, LessonList...)과 동일하게 맞출 것을 권장**.
- 디자인이 먼저 나온 컴포넌트부터 순서 상관없이 코드에 스타일 반영 가능 — 구조(이 문서)와 스타일(Figma)은 독립적으로 진행 가능하도록 설계됨.

---

## 11. 체크리스트 (Claude Code 작업 시작 전 확인)

- [ ] `git log -1`로 현재 브랜치 최신 커밋이 이 문서 상단의 "기준 브랜치/시점"과 일치하는가? (팀 브랜치가 자주 바뀌므로 매번 재확인)
- [ ] 5장의 "미결정 항목" 5가지를 팀과 논의해서 확정했는가?
- [ ] `api.js`, `store/useStore.js`의 기존 로직을 건드리지 않는 것을 재확인했는가?
- [ ] 9.2의 작업 순서(1→2→3→4단계)를 따르고 있는가? 순서를 건너뛰지 않았는가?
- [ ] 각 단계마다 PR을 짧게 끊어서 빨리 merge하고 있는가?
- [ ] 구조 이동 커밋과 로직 변경 커밋을 분리했는가?
- [ ] 4.2의 구 URL 리다이렉트 매핑을 라우팅에 반영했는가?
