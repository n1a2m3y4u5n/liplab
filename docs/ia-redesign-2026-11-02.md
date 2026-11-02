# 앱 내부 구조 개편 설계 (2026-11-02)

이 문서만 보고 구현한다. 결정은 다 적었다. 코드에서 이 문서와 다른 사실이 나오면, 3·6절의 규칙을 지키는 쪽으로 고치고 구현 보고에 적는다.

- 기준 코드: 브랜치 `ia-2026-11-02`, 커밋 `9b2f5cc2`
- 지시: `D:\work\hq\shared\directive-1102-ia.md`
- 측정: `D:\work\hq\projects\liplab\out\ia-2026-11-02\measure.mjs`, `measure-results.json`, `shots\`
- 표시: **(측정)** 데모 계정에서 실제로 눌러 봄, **(코드)** 코드를 읽어 따라감, **(추측)** 확인하지 못한 판단

## 한눈에 보기

| 항목 | 지금 | 새 구조 |
|---|---|---|
| 탭 수 (폰·아이패드 세로) | 5개 **(측정)** | 4개 |
| 탭 수 (컴퓨터) | 6개 **(측정)** | 4개 |
| 화면 배치 종류 | 3가지: 1024 아래 / 1024 이상 / 1280 이상(오른쪽 패널) **(코드)** | 2가지: 1024 아래 하단 탭 / 1024 이상 왼쪽 메뉴 |
| '오늘 할 일'이 나뉜 곳 | 5곳: 과제 탭, 복습 탭, `/listen/today`, 오른쪽 패널, 소리 듣기 경로의 '오늘 몫' **(코드)** | 1곳: 오늘 탭 |
| 새 경로 | - | `/today`, `/records` 두 개뿐 |

탭 키와 주소:

| 탭 | 키 | 주소 | 아이콘(있는 파일만 쓴다) |
|---|---|---|---|
| 오늘 | `today` | `/today` | `nav-learn.svg` (집 모양, `shots\phone-continue-1.png`로 확인) |
| 학습 | `learn` | `/learn/path` (`?track=`, `?section=`) | `nav-practice.svg` |
| 기록 | `records` | `/records` (`?track=`, `?view=`) | `nav-analytics.svg` |
| 내 정보 | `me` | `/profile` | `nav-profile.svg` |

`/learn/path`와 `/profile`의 주소를 바꾸지 않는 이유: 이용 기록, `A11ySettings`의 `LESSON_PATHS`, `StageGate`의 되돌림, 수십 곳의 `navigate`가 이 주소를 쓴다. 바꿔서 얻는 것이 없다.

---

## 1. 지금 구조의 문제 (코드로 다시 확인)

### 1.1 지시 항목 확인

| 지시 내용 | 판정 | 확인한 곳과 덧붙일 사실 |
|---|---|---|
| 탭 6개가 기능 기준 | 맞음 | `AppShell.jsx` `NAV` |
| 학습은 `?track=`로 트랙을 나눔 | 맞음 | 다만 소리 듣기는 다른 컴포넌트다. `LearnPath.jsx`가 `ListenPath`와 `CurriculumPath`로 가른다. `CurriculumPath` 안의 listen 코드는 지금 쓰이지 않는다. 트랙 전환 버튼도 두 벌이다. |
| 연습은 소리 듣기만 묶음 | 맞음 | `PracticeHub.jsx`. 위쪽 카드 5개는 트랙 표시가 없고, 말하기 전용 카드는 없다. |
| 복습은 `/review/speaking`·`/listen/review`로 흩어짐 | 맞음 | `/review/scheduled`, `/review/mistakes`, `/review/saved`까지 더 있다. |
| 분석은 `/analysis/listening`으로 흩어짐 | 맞음 | 분석 탭의 듣기 요약은 소리 확인 전이면 안 보인다. 데모 계정에도 안 보였다 **(측정)**. |
| '오늘 뭘 하지'가 과제·복습·오늘의 듣기·오른쪽 패널에 나뉨 | 맞음 | 소리 듣기 경로의 '오늘 몫'까지 5곳이다. 오른쪽 패널은 1280 이상에서만 보인다. |
| 홈이 없고 `/dashboard`는 `/learn/path`로 감 | 맞음 | `App.jsx` 241행. `features/dashboard/Dashboard.jsx` 파일은 남아 있지만 부르는 곳이 없다. |
| 모바일 5개, 데스크톱 6개 | 맞음 **(측정)** | 폰: 학습·연습·과제·복습·분석. 컴퓨터는 프로필까지. |
| 입모양 교실이 연습 카드 안에 숨음 | 맞음 | `/learn/viseme?tab=learn`의 메뉴 입구는 이 카드 하나다. `?v=`는 서버가 주는 약점 링크로 들어온다. |
| 수어 보기 주소가 둘 | 맞음 | 부르는 곳은 `/learn/sign`(연습 카드)뿐이다. `/sign`은 라우트와 `ROUTES`에만 있고 호출이 없다. |

### 1.2 지시와 달랐거나 지시에 없던 사실

| 사실 | 근거 | 이 설계에서 |
|---|---|---|
| '자유 발화'는 말하기 채점이 없다. 쓴 문장의 3D 입모양과 성도 옆모습을 보여 주는 도구다. | `FreeSpeak.jsx`, `CLAUDE.md`의 '내 문장 발음 보기' | 이름을 '내 문장 입모양 보기'로 바꾼다. |
| 입모양 읽기 3·4단계의 '이어서'는 레슨이 아니라 상황 입력 칸으로 간다. 칸이 비어 있어 '시작하기'가 꺼져 있다. 탭 표시도 연습으로 바뀐다. | **(측정)** `shots\phone-continue-1.png`, `startButtons` | 입구는 그대로 둔다(LLM 비용과 잠금 때문). 8절 한계에 적는다. |
| 화면에는 '독화·발화'로 쓰여 있다. 지시의 '입모양 읽기·말하기'와 다르다. | `CurriculumPath.jsx` `TRACK_LABEL`, 45개 파일 | 3.8절 범위만 바꾼다. |
| 폰 소리 듣기 경로의 '결과 보기'·'소리 교실' 링크는 처음에 아래 시트에 가려 있다. | **(측정)** `coveredBefore: true`, 크기 51×44 | 자료 구역과 기록 탭으로 옮긴다. |
| 과제 탭에 들어가면 보상을 자동으로 받는다. | `TasksPage.jsx` `tasksAPI.claim()` | 오늘 탭으로 그대로 옮긴다. 빠뜨리면 보상이 안 들어온다. |
| 이용 기록이 경로 이름에 강하게 기댄다. | 5절 | 5절대로 한다. |
| `/learn/path?track=speak`·`listen`의 이용 기록 `track`은 `read`로 남는다(원래 있던 결함). | `lib/track.js`는 경로에 글자가 있는지만 본다 | 고치지 않는다. 5.3절 참고. |
| 데모 계정은 소리 듣기 전 단계가 열려 있고 `listen_started`는 거짓이다. | **(측정)** `measure-results.json` | 소리 듣기 잠김은 데모로 확인할 수 없다. 응답을 가로채 확인한다. |

---

## 2. 전체 화면 지도

`App.jsx`의 모든 경로다. '그대로'는 주소를 바꾸지 않는다는 뜻이다. 일반 탭에 드러내지 않는 화면은 '숨김'으로 표시한다.

### 2.1 탭·허브

| 지금 경로 | 지금 화면 | 새 위치 | 옛 주소 처리 |
|---|---|---|---|
| `/` | HomeRedirect | placed 거짓이면 `/onboarding`, 그 밖과 조회 실패는 `/today` | 그대로, 목적지만 변경 |
| `/dashboard` | `/learn/path`로 넘김 | 오늘 | `/today`로 리다이렉트 |
| `/learn/path` | 학습 경로 | 학습 > 해당 트랙 > 단계 | 그대로 |
| `/practice/hub` | 연습 탭 | 학습 > 기억한 트랙 > 자유 연습 | `/learn/path?track=<기억>&section=free`로 리다이렉트 |
| `/tasks` | 과제 탭 | 오늘 > 오늘의 과제 | `/today#tasks`로 리다이렉트 |
| `/review` | 복습 탭 | 오늘 > 오늘 복습 (목록은 기록 > 틀린 문장) | `/today#review`로 리다이렉트 |
| `/review/hub`, `/review/today` | `/review`로 넘김 | 오늘 > 오늘 복습 | `/today#review`로 리다이렉트 |
| `/analysis` | 분석 탭 | 기록 > 요약 | `/records`로 리다이렉트 |
| `/analysis/hub`, `/analysis/overview` | `/analysis`로 넘김 | 기록 > 요약 | `/records`로 리다이렉트 |
| `/profile` | 프로필 탭 | 내 정보 | 그대로 |

리다이렉트는 `LegacyRedirect` 하나로 만든다. 옛 주소의 쿼리는 지우지 않고 이어 붙인다.

### 2.2 학습 단계·레슨 (주소 그대로, 나가기 목적지만 3.7절대로)

| 지금 경로 | 화면 | 잠금 | 새 위치 | 옛 주소 처리 |
|---|---|---|---|---|
| `/learn/viseme` | 입모양 레슨 | 없음 | 입모양 읽기 > 단계 1 | 그대로 |
| `/learn/viseme?tab=learn`, `?v=` | 입모양 교실 | 없음 | 입모양 읽기·말하기 > 자료 | 그대로 |
| `/learn/word` | 음절·단어 | StageGate 2 | 입모양 읽기 > 단계 2 | 그대로 |
| `/practice` | 문장 | StageGate 3 | 입모양 읽기 > 단계 3 (`/learn/scenario`를 거침) | 그대로 |
| `/conversation` | 대화 | StageGate 4 | 입모양 읽기 > 단계 4 (`/learn/scenario`를 거침) | 그대로 |
| `/learn/speaking` | 말하기 레슨 | 서버 | 말하기 > 단계 | 그대로 |
| `/learn/listening` | 소리 듣기 레슨 | 서버 | 소리 듣기 > 단계 | 그대로 |
| `/learn/placement` | 자가진단·검사 | 없음 | 숨김, 입구는 내 정보·온보딩·기록 | 그대로 |
| `/onboarding` | 첫 설정 | 없음 | 숨김, placed 거짓일 때만 | 그대로 |

### 2.3 자유 연습·자료 (애매한 카드의 결정은 2.7절)

| 지금 경로 | 화면 | 잠금 | 새 위치 | 옛 주소 처리 |
|---|---|---|---|---|
| `/learn/scenario` | 상황별 시나리오 | 3·4단계 잠김 유지 | 입모양 읽기 > 자유 연습 | 그대로 |
| `/learn/conversation-multi` | 여러 명 대화 | 없음 | 숨김, `/learn/scenario` 안에서 들어감 | 그대로 |
| `/learn/endless` | 엔드리스 | 단어 쪽 StageGate 2 | 입모양 읽기 > 자유 연습 | 그대로 |
| `/learn/closure` | 문맥 추론 | 없음 | 숨김, 엔드리스 안에서 들어감 | 그대로 |
| `/learn/nonsense` | 뜻 없는 말 짝 맞추기 | StageGate 2 | 입모양 읽기 > 자유 연습(2단계 열린 뒤 보임) | 그대로 |
| `/pronounce` | 자유 발화 | 없음 | 말하기 > 자유 연습 | 그대로 |
| `/learn/sign` | 수어 보기 | 없음 | 입모양 읽기 > 자료 | 그대로 |
| `/sign` | 수어 보기 | 없음 | 위와 같음 | `/learn/sign`으로 리다이렉트(`?text=` 유지) |
| `/listen/practice/:mode` | 듣기 연습 5종 | 소리 확인 전 잠김 유지 | 소리 듣기 > 자유 연습 | 그대로 |
| `/listen/classroom` | 소리 교실 | 없음 | 소리 듣기 > 자료 | 그대로 |

### 2.4 오늘·복습 세션

| 지금 경로 | 화면 | 새 위치 | 옛 주소 처리 |
|---|---|---|---|
| `/listen/today` | 오늘의 듣기 | 오늘 > '오늘의 듣기' 줄 | 그대로 |
| `/review/scheduled` | 오늘의 복습 세션 | 오늘 > 오늘 복습 | 그대로 |
| `/review/speaking` | 말하기 복습 목록 | 오늘 > 오늘 복습, 말하기 > 자유 연습 | 그대로 |
| `/review/speaking/session` | 말하기 복습 세션 | 위 화면 안 | 그대로 (`SpeakingPractice`가 이 주소로 복습인지 판단한다) |
| `/listen/review` | 듣기 복습 | 오늘 > 오늘 복습 | 그대로 |

### 2.5 기록

| 지금 경로 | 화면 | 새 위치 | 옛 주소 처리 |
|---|---|---|---|
| `/review/mistakes` | 틀린 문장 목록과 다시 풀기 | 기록 > 틀린 문장 > '다시 풀기' 아래 화면 | 그대로 (서버 `main.py` 1461행과 `Practice.jsx` `reviewReturn`이 쓴다) |
| `/review/saved` | 북마크 목록과 다시 연습 | 기록 > 저장한 문장 > '다시 연습' 아래 화면 | 그대로 (`reviewReturn`이 쓴다) |
| `/analysis/listening` | 소리 듣기 보고서 | 기록 > 요약 > 소리 듣기 칩 | `/records?track=listen`으로 리다이렉트 |
| `/analysis/activity` | 활동 캘린더 | 기록 > 요약 아래 화면 | 그대로 |
| `/analysis/visemes` | 약한 입모양 | 기록 > 요약 아래 화면 | 그대로 |
| `/analysis/scores` | 점수 | 기록 > 요약 아래 화면 | 그대로 |
| `/analysis/history` | 회차 히스토리 | 기록 > 요약 아래 화면 | 그대로 |
| `/analysis/eval` | 학습 효과 리포트 | 기록 > 요약 아래 화면 | 그대로 |

### 2.6 일반 탭에 드러내지 않는 화면 (주소·조건 모두 그대로)

| 지금 경로 | 종류 | 조건 |
|---|---|---|
| `/pilot/battery` | 파일럿 | 내 정보의 '파일럿 참여'(`pilot.enabled`일 때만) |
| `/pilot/av-comparison` | 실험 | `VITE_AV_COMPARISON=1` |
| `/admin/feedback`, `/admin/content-review` | 관리자 | 메뉴 없음 |
| `/admin/kmsav` | 관리자 | `VITE_KMSAV_REVIEW=1` |
| `/dev-viseme`, `/lab/cue-video` | 개발·연구 | 메뉴 없음 |
| `/terms`, `/privacy` | 약관 | 공개 주소 유지, 내 정보에 줄 추가 |
| `/about` | 소개 | 공개 주소 유지, 로고에서 들어감 |
| `/login`, `/signup` | `/`로 넘김 | 그대로 |
| `*` | NotFound | 홈 버튼만 `/today`로 |

### 2.7 애매한 카드의 결정

| 카드 | 연결 화면에서 본 것 | 결정 | 새 이름 |
|---|---|---|---|
| 상황별 시나리오 | 상황을 쓰고 문장 테스트 또는 AI 대화로 간다. 3·4단계의 실제 입구다. | **입모양 읽기 > 자유 연습** | 상황별 연습 |
| 자유 발화 | 채점과 필수 마이크가 없다. 쓴 문장의 입모양과 성도 옆모습을 본다. 자기 음성으로 아바타를 움직이는 선택 기능이 있다. 소리를 어떻게 내는지 보는 내용이고, 말하기 트랙에 다른 자유 연습이 없다. | **말하기 > 자유 연습** (미사용 `config/tracks.js`는 독화로 분류했지만, 내용을 근거로 다르게 정했다) | 내 문장 입모양 보기 |
| 엔드리스 | 약점 단어(`/learn/word?endless=1`)와 문맥 추론을 섞어 낸다. 전부 독화다. | **입모양 읽기 > 자유 연습** | 틀린 유형 계속 풀기 |
| 수어 보기 | 트랙, 점수, 단계가 없다. 문장을 수어 영상으로 번역한다. 어느 화면에서나 문장을 고르면 '수어로 보기'가 뜬다(`SignSelectionOverlay`). | **입모양 읽기 > 자료**. 한 곳에만 둔다. 다른 트랙에서는 전역 선택 기능을 쓴다. | 수어 보기 |
| 입모양 교실 | 웹캠 따라 하기, 조음 교정, 아바타 거울, 혀 위치 보기. 보는 내용과 말하는 내용이 함께 있다. | **입모양 읽기 > 자료, 말하기 > 자료**. 같은 화면에 입구 둘. | 입모양 교실 |
| 소리 교실 | 소리 짝을 여러 목소리로 듣는다. | **소리 듣기 > 자료** | 소리 교실 |
| 말하기 복습 | 말하기에서 틀린 소리 목록이다. | **오늘 > 오늘 복습**과 **말하기 > 자유 연습** | 말하기 복습 |
| 뜻 없는 말 짝 맞추기 | 지금은 경로 레슨 카드의 보조 버튼이다. | 그 버튼은 **자유 연습 카드로 옮긴다**(2단계 열린 뒤에만 보임, 지금 조건 그대로) | 뜻 없는 말 짝 맞추기 |

---

## 3. 새 탭 구성

### 3.1 셸 (`components/AppShell.jsx`)

| 항목 | 결정 |
|---|---|
| `NAV` | 위 표의 4개. 폰과 컴퓨터가 같은 배열을 쓴다. `filter`를 뺀다. |
| 학습 탭 버튼 | 고정 주소 대신 `learnHref()`로 이동한다. 기억한 트랙이 read면 `/learn/path`, 아니면 `?track=`를 붙인다. |
| 맨 `/learn/path`의 뜻 | **입모양 읽기**로 고정. 레슨의 나가기와 `StageGate`의 되돌림이 입모양 읽기를 기대하기 때문이다. 기억은 맨 주소에 적용하지 않는다. |
| 오른쪽 패널 | 없앤다. `Rail`, `rail`, `rightRail` prop을 지운다. `RailTasksCard`, `RailReviewCard`는 삭제한다. `RailLevelCard`, `RailWeekCard`는 기록 > 요약 맨 아래로 옮긴다. `RailStats`는 컴퓨터 왼쪽 메뉴 아래로 옮긴다. |
| 본문 폭 | 1280 이상에서 `max-w-[816px] mx-auto` (지금 패널 옆 폭과 비슷한 값, **추측**이므로 스크린샷으로 맞춘다) |
| 폰 상단 바 | 로고, 불꽃·별, Aa를 둔다. 아바타는 뺀다(내 정보 탭과 겹침). |
| `active` 값 | 3.1.1 표대로 전부 바꾼다. |
| `closeTo` | `backTo` + `backLabel`로 바꾼다(3.7절). |
| `useLearnTrack`, `data-track` | 그대로 쓴다. |
| 폭 기준 | `lg`(1024)만 쓴다. 아이패드 세로는 하단 탭 4개, 가로는 왼쪽 메뉴 4개. |

#### 3.1.1 `active` 바꾸기

| 파일 | 지금 | 새 값 | `backTo` / `backLabel` |
|---|---|---|---|
| `AnalysisTab` | analysis | 본문을 `RecordsPage`로 옮김 | - |
| `AnalysisDetail`, `EvalReport` | analysis | records | `/records` / 기록 |
| `ListeningReport` | analysis | 본문을 `RecordsPage`로 옮김 | - |
| `Bookmarks` | review | records | `/records?view=saved` / 저장한 문장 |
| `ReviewLanding` | review | records | `/records?view=wrong` / 틀린 문장 |
| `SpeakingReviewLanding` | review | today | `/today` / 오늘 |
| `ReviewTab`, `TasksPage` | review, task | 본문을 옮기고 파일 삭제 | - |
| `CurriculumPath`, `ListenPath` | learn | learn | - |
| `ScenarioHub`, `EndlessPractice` | practice | learn | `/learn/path?section=free` / 자유 연습 |
| `MultiConversation` | practice | learn | `/learn/scenario` / 상황별 연습 |
| `Sign` | practice | learn | `/learn/path?section=res` / 자료 |
| `FreeSpeak` | practice | learn | `/learn/path?track=speak&section=free` / 자유 연습 |
| `PracticeHub` | practice | 내용을 옮기고 파일 삭제 | - |
| `ProfilePage` | profile | me | - |

`ScenarioHub`이 경로 3·4단계에서 열렸을 때는 `backTo`를 `/learn/path`, `backLabel`을 '단계'로 한다. `location.state.from === 'path'`로 구분한다. state가 없으면 자유 연습으로 간다.

### 3.2 오늘 (`pages/TodayPage.jsx`, 새 파일)

화면 순서:

| 순서 | 구역 | 내용 | 안 보이는 경우 |
|---|---|---|---|
| 1 | 제목 | '오늘'. 설명 줄 없음 | - |
| 2 | 지금 할 일 | 큰 버튼 하나(`btn-primary btn-lg`), 위에 트랙·단계 한 줄 | 항상 보임 |
| 3 | 오늘 복습 (`id="review"`) | 합친 개수, 트랙별 칩(눌러서 그 트랙부터), '복습 시작하기' | 합계 0이거나 2번이 이미 복습일 때 |
| 4 | 오늘의 듣기 | 한 줄 카드, '15분', `/listen/today?from=today` | `listen_started` 거짓일 때 |
| 5 | 오늘의 과제 (`id="tasks"`) | `TasksPage`의 `TaskRow`와 특별 과제 | 불러오기 실패 시 `LoadFailed` 작게 |

- 2번 버튼만 `btn-primary`다. 나머지는 `btn-secondary`와 줄 모양이다.
- 폰에서 2번 버튼이 첫 화면에 다 보여야 한다(iPhone SE 375×667).
- 들어올 때 `tasksAPI.claim()`을 부르고 `RewardToast`를 띄운다. `TasksPage`의 순서를 그대로 옮긴다.
- `#tasks`, `#review`로 오면 그 구역으로 스크롤한다. 해당 구역이 없으면 맨 위에 둔다.
- 배지 목록과 `BadgeDetailModal`은 기록 > 요약 아래로 옮긴다.

#### 3.2.1 '지금 할 일 하나' 규칙

순수 함수 `lib/todayNext.js`의 `todayNext(input)`으로 만들고 표의 경우마다 테스트를 둔다. 위에서부터 처음 맞는 줄을 쓴다.

입력: `stages`(`curriculumAPI.getStages`), `speak`(`speakAPI.getCurriculum`), `listen`(`listenAPI.getCurriculum`), `due`(`reviewAPI.getDue`), `tasks`(`tasksAPI.get`), `lastTrack`.

| # | 조건 | 버튼 글자 | 윗줄 | 이동 |
|---|---|---|---|---|
| 1 | `stages` 조회 실패 | 학습으로 가기 | '정보를 가져오지 못했어요', 옆에 '다시 가져오기' | `/learn/path` |
| 2 | `stages.placed === false` | 시작하기 | 없음 | `/onboarding` |
| 3 | `lastTrack==='listen'`이고 `listen.recommended===0`이고 `ling_today` 거짓 | 소리 확인하기 | 소리 듣기 · 1분 | `/learn/listening?stage=0` |
| 4 | 오늘 학습함이고 복습 합계 > 0 | 복습 시작하기 | 오늘 복습 N개 | `todayReviewStart(due)` |
| 5 | `lastTrack==='listen'`이고 추천 단계 몫을 다 함(`quotaView(quota).met`), 복습 합계 > 0 | 복습 시작하기 | 오늘 복습 N개 | `todayReviewStart(due)` |
| 6 | `lastTrack==='listen'`이고 몫을 다 함, 복습 합계 0 | 한 묶음 더 하기 | 소리 듣기 · 오늘 몫을 마쳤어요 | `/learn/listening?stage=<추천>` |
| 7 | `lastTrack` 현재 단계 없음(`pathNodeState().currentIdx < 0`, 모두 숙달), 복습 합계 > 0 | 복습 시작하기 | 오늘 복습 N개 | `todayReviewStart(due)` |
| 8 | 위 7에서 복습 합계 0 | 자유 연습 하기 | 트랙 이름 | `/learn/path?track=<트랙>&section=free` |
| 9 | 그 밖(기본), 현재 단계의 `attempts`가 0 또는 없음 | 학습 시작하기 | 트랙 · N단계 제목 | 아래 경로 표 |
| 10 | 그 밖(기본) | 이어서 학습하기 | 트랙 · N단계 제목 | 아래 경로 표 |

| 값 | 정의 |
|---|---|
| 복습 합계 | `due.total_with_listen`. 없으면 `dueCounts(due).total + (due.listen_count ?? 0)` |
| 오늘 학습함 | `tasks.daily`의 `two_sessions.cur >= 1` 또는 `listen_15.cur >= 1`. `two_sessions`에는 듣기 시행이 들어가지 않으므로(`analytics.overview` 주석) 둘 다 본다. |
| `todayReviewStart(due)` | read > 0이면 `/review/scheduled`, speak > 0이면 `/review/speaking`, listen > 0이면 `/listen/review`, 모두 0이면 `/records?view=wrong`. `dueStartPath`는 지우지 않고 그 위에 만든다(`reviewDue.test.mjs` 유지). |
| 현재 단계 | `pathNodeState(list, track).currentIdx`. 경로 화면과 같은 함수를 써서 다른 답이 나오지 않게 한다. 소리 듣기는 `recommendedStage(listen)`. |
| 트랙 이름 줄의 숫자 | 경로 화면과 같은 `no` 값 |

| 트랙·단계 | 이동 |
|---|---|
| 입모양 읽기 1 | `/learn/viseme` |
| 입모양 읽기 2 | `/learn/word` |
| 입모양 읽기 3 | `/learn/scenario` (`state: {from:'path'}`) |
| 입모양 읽기 4 | `/learn/scenario?mode=conversation` (`state: {from:'path'}`) |
| 말하기 N | `/learn/speaking?stage=N` |
| 소리 듣기 N | `/learn/listening?stage=N` |

`normalizeRead`·`normalizeSpeak`와 `READ_ROUTE`를 `CurriculumPath.jsx`에서 `lib/trackPath.js`로 빼서 경로 화면과 오늘 화면이 함께 쓴다. 숫자와 판단은 바꾸지 않는다.

3번 규칙은 소리 듣기를 고른 사람에게만 작동한다. 다른 사람에게는 소리 확인이 나오지 않는다.

#### 3.2.2 마지막 트랙 기억 (`lib/lastTrack.js`, 새 파일)

| 항목 | 결정 |
|---|---|
| 저장 | `localStorage` `liplab_last_track:${uid}`, 값은 `read`·`speak`·`listen`. `useSoundCondition`의 계정별 키와 같은 방식. 공용 기기에서 다른 사람의 트랙이 나오지 않는다. |
| 쓰는 때 | 학습 탭의 트랙이 바뀔 때, `/learn/speaking`·`/learn/listening`·`/learn/viseme`(`tab=learn` 제외)·`/learn/word`·`/practice`·`/conversation`에 들어갈 때 |
| 값이 없을 때 | 세 트랙의 `attempts` 합이 가장 큰 트랙. 같으면 read > speak > listen. 합이 모두 0이면 read. |
| 다른 기기 | 서버에 저장하지 않는다. 다른 기기에서는 위 계산을 쓴다. DB 변경을 피하려는 기본값이다. |
| 지우기 | `clearUserLocalData`에 넣는다. 저장소가 막혀 있으면 조용히 넘어간다. |

### 3.3 학습 (세 트랙 공통)

위에서 아래로:

```
[입모양 읽기 | 말하기 | 소리 듣기]      TrackSwitcher
[단계  자유 연습  자료]                 SectionTabs
(선택한 구역 내용)
```

| 항목 | 결정 |
|---|---|
| 구역을 한 화면에 쌓지 않는 이유 | 단계 구역의 레슨 카드는 폰에서 아래에 고정된 시트다(`device-mobile-sheet`). 그 아래에 다른 내용을 쌓으면 시트에 가린다. 시트를 옮기면 iPhone SE 가로 수정(`24de2f81`)을 다시 해야 한다. |
| 주소 | `?track=read|speak|listen`(read면 생략), `?section=path|free|res`(path면 생략) |
| 트랙 전환 | 구역은 유지하고 `stage`는 지운다. `replace: true`. |
| 구역 전환 | `replace: true`. 뒤로 가기로 탭 밖으로 나가게 한다. |
| 시트 | `section=path`일 때만 그린다. |
| `TrackSwitcher` | `components/learn/TrackSwitcher.jsx`. `CurriculumPath`와 `ListenPath`의 두 벌을 지운다. |
| `SectionTabs` | `components/learn/SectionTabs.jsx`. 버튼 `min-h-11`, `aria-pressed`. |
| 카드 | `PracticeHub`의 `PracticeCard`를 `components/learn/LearnCard.jsx`로 옮긴다. 데이터는 `lib/learnSections.js`. |
| 파일 구조 | `LearnPath.jsx`는 고르기만 한다. `section=path`면 `CurriculumPath` 또는 `ListenPath`, 그 밖이면 새 `LearnSection`. `AppShell`이 각 화면 안에 있으므로 맨 위 두 줄은 새 `components/learn/LearnHeader.jsx`(스위처 + 구역)로 만들어 세 화면이 각자 넣는다. 두 경로 컴포넌트는 옛 스위처 자리만 바꾼다. |
| 제목 | 경로 화면은 지금처럼 히어로의 `h1`을 쓴다. `LearnSection`은 `AppShell`에 title을 주지 않고 `<h1 class="sr-only">트랙 · 구역</h1>`을 둔다. |

세 트랙의 구역 내용:

| 트랙 | 단계 | 자유 연습 | 자료 |
|---|---|---|---|
| 입모양 읽기 | `CurriculumPath` read | 상황별 연습, 틀린 유형 계속 풀기, 뜻 없는 말 짝 맞추기(2단계 열린 뒤) | 입모양 교실, 수어 보기 |
| 말하기 | `CurriculumPath` speak | 내 문장 입모양 보기, 말하기 복습 | 입모양 교실 |
| 소리 듣기 | `ListenPath` | 듣기 연습 5종 + 공통 잠김 안내 | 소리 교실 |

`ListenPath`에서 고칠 곳은 네 가지뿐이다: 스위처 제거, 아래쪽 '소리 교실·결과 보기' 줄 제거, 시트의 '오늘의 듣기' 줄 제거(오늘 탭으로 옮김), `q.met`의 '결과 보기' 이동을 `/records?track=listen`으로 변경.

### 3.4 소리 듣기 트랙을 안 쓰는 사람에게

| 곳 | 소리 확인 전(`listen_started` 거짓) | 소리 확인 후 |
|---|---|---|
| 학습 > 트랙 전환 | '소리 듣기' 버튼은 보임(찾을 수 있어야 함), 맨 뒤 | 같음 |
| 오늘 > 지금 할 일 | 마지막 트랙이 소리 듣기일 때만 관련 내용 | 같음 |
| 오늘 > 복습 칩, 오늘의 듣기, 과제 | 안 보임. 복습 수와 과제는 서버가 이미 주지 않는다. | 보임 |
| 기록 > 트랙 칩 | '소리 듣기' 칩 안 보임 | 보임 |
| 내 정보 > 소리 확인 | 보임, 설정 묶음의 아래쪽 | 같음 |
| 첫 방문 안내(`ListenNotice`) | 소리 듣기 트랙에 들어갈 때만 뜸 | 같음 |

**바꾸지 않는 것**

- 소리 확인 전 잠김: `PracticeHub`의 `avail`, `offReason`, `shared` 계산과 공통 이유 한 줄, '소리 확인 하러 가기' 버튼을 소리 듣기 > 자유 연습으로 그대로 옮긴다. `listenAPI.practiceModes()`를 못 받으면 카드를 열어 두는 것도 그대로다.
- `ListenPractice`의 409 안내.
- '진단·치료하지 않아요' 안내와 합성 음성 표시.

### 3.5 기록 (`pages/RecordsPage.jsx`, 새 파일)

위에서 아래로:

```
기록 (제목)
[요약  틀린 문장  저장한 문장]            ?view=summary|wrong|saved
[전체 입모양 읽기 말하기 소리 듣기]       ?track=all|read|speak|listen
(내용)
```

| 항목 | 결정 |
|---|---|
| 기본값 | `view=summary`, `track=all`. 기본값은 주소에서 생략한다. |
| 기억 | 하지 않는다. 기록 탭은 늘 전체 요약에서 시작한다. |
| 소리 듣기 칩 | `listenAPI.links().listen_started` 거짓이면 안 보임. 단, 주소가 `track=listen`이면 칩을 보인다(옛 링크가 끊기지 않게). |

요약 구역 내용(서버 변경 없음):

| 칩 | 내용 | 자료 |
|---|---|---|
| 전체 | `AnalysisTab`의 본문 그대로 + 레벨·주간 카드 + 배지 | `/api/analysis/overview` |
| 입모양 읽기 | `tracks.read`의 정확도·숙달 단계 수·문항 수, 약한 입모양·학습 효과 리포트 링크 | 같음 |
| 말하기 | `tracks.speak`의 같은 항목, `SpeakTrend` | 같음 |
| 소리 듣기 | `ListeningReport`의 본문 전체 | `listenAPI.summary` |

- 전체 칩의 주간 차트는 세 트랙을 트랙별로 나눈 자료가 없다(`overview.weekly`). **트랙 칩에서는 차트를 숨긴다.** 트랙별 차트 추가는 서버 변경이 필요하므로 이번 범위가 아니다.
- `ListeningReport`는 본문을 `components/records/ListenReportBody.jsx`로 빼고 `data-track="listen"`을 유지한다. 내부의 '연습하러 가기', `Empty`의 링크는 그대로 둔다.
- 약한 입모양, 점수 등 아래 화면은 지금 화면을 그대로 둔다. `AnalysisDetail`의 `ANALYSIS_TABS`는 두 줄만 바꾼다: 첫 항목을 `/records`·'요약'으로, 마지막 항목 이름 '기록'을 '회차'로(탭 이름 '기록'과 겹치기 때문이다).

틀린 문장·저장한 문장 구역:

| 구역 | 내용 | 맨 위 버튼 |
|---|---|---|
| 틀린 문장 | `ReviewTab`의 목록에서 북마크 아닌 것. 트랙 칩으로 거른다(항목의 트랙 값 독화·발화·듣기를 쓴다). | '다시 풀기' → `/review/mistakes` |
| 저장한 문장 | 목록의 북마크. 트랙 칩으로 거른다. | '다시 연습' → `/review/saved` |

- `ReviewTab`의 목록, 선택 삭제, `openItem`은 `components/records/ReviewItems.jsx`로 그대로 옮긴다. 복습 예정 항목도 목록에 남는다.
- 히어로 카드 두 개(`GradientCta`)는 옮기지 않는다. 복습 시작은 오늘 탭이 맡는다.
- `ListenReviewCard`는 지운다. 듣기 복습 입구는 오늘 탭의 복습 칩이다.

### 3.6 내 정보 (`pages/ProfilePage.jsx` 수정)

제목을 '내 정보'로 바꾼다. 맨 위 프로필 카드와 스탯은 그대로 둔다.

| 묶음 | 줄 | 동작 | 상태 |
|---|---|---|---|
| 프로필 | 계정 설정, 나에게 맞춘 안내, 자가진단 다시 하기 | 기존 | 유지 |
| 설정 | 접근성 설정 | `liplab:a11y-toggle` 이벤트(Aa와 같은 패널) | **새 줄** |
| 설정 | 소리와 함께 다시 보기 | 기존 | 유지 |
| 설정 | 소리 확인 | `/learn/listening?stage=0` | **새 줄** |
| 도움말 | 사용법 가이드 | 기존 | 유지 |
| 도움말 | 이용약관, 개인정보처리방침 | `/terms`, `/privacy` | **새 줄** |
| 그 밖 | 파일럿 참여(`pilot.enabled`일 때만), 학습 초기화 | 기존 | 유지 |

초기화·삭제·로그아웃 뒤 이동 `/learn/path`는 `/today`로 바꾼다. 로그아웃이면 어차피 인증 화면이 먼저 뜬다.

**묶음 이름 '프로필'을 남기는 이유**: 처리방침(`Legal.jsx` 88~89행)에 '프로필 → 계정 설정'이라고 적혀 있다. 법적 문구는 이번에 고치지 않는다. 묶음 이름과 '계정 설정'이 남으면 안내대로 찾아갈 수 있다. `A11ySettings.jsx` 136행, `learnerProfile.js` 85행은 앱 문구이므로 '내 정보'로 고친다.

### 3.7 위치 표시와 돌아가기·나가기

| 화면 종류 | 위치 표시 | 돌아가기 | 예 |
|---|---|---|---|
| 탭 화면 | 탭 강조 + 제목 | 없음 | `/today`, `/records`, `/profile` |
| 학습 구역 | 탭 강조 + 트랙·구역 강조 | 없음 | `/learn/path?section=free` |
| 탭 아래 화면(`AppShell` 사용) | 탭 강조 + 제목 | 제목 위 왼쪽에 `‹ 돌아갈 곳 이름`. 44px 이상, 글자가 항상 보임. 오른쪽 X는 없앤다. | 수어 보기, 활동 캘린더 |
| 집중 화면(레슨·검사·세션, 탭 없음) | 지금 레슨 머리글 | 왼쪽 위 X, `aria-label="나가기"` 하나. 위치는 지금 그대로. | `/learn/word`, `/practice` |

나가기 목적지(바꾸는 곳만):

| 파일 | 지금 | 새 목적지 | 새 글자 |
|---|---|---|---|
| `VisemeLiteracy.jsx` `exitTo` (`tab=learn`) | `/practice/hub` | `/learn/path?track=<마지막>&section=res` (`speak`일 때만 `track`) | - |
| `Closure.jsx` `hubOf` (엔드리스 아님) | `/practice/hub` | `/learn/path?section=free` | '자유 연습으로 돌아가기' |
| `ListenClassroom.jsx` `exit` | `/practice/hub` | `/learn/path?track=listen&section=res` | '자료로' |
| `ListenPractice.jsx` `HUB` | `/practice/hub` | `/learn/path?track=listen&section=free` | '자유 연습으로' |
| `lib/listenFlow.js` `practiceActions` | '연습 탭으로' | 같음(글자만) | '자유 연습으로' (`listenFlow.test.mjs` 191행도 수정) |
| `ListenReview.jsx` `exit` | `/review` | `/today` | '오늘로' |
| `ListenToday.jsx` `back` | `tasks` 또는 경로 | `from`이 `today`·`tasks`면 `/today`, 그 밖은 `/learn/path?track=listen` | - |
| `Review.jsx` 52, 58, 163, 181행 | `/review` | `/today` | `homeLabel` '오늘로' |
| `Review.jsx` `onNext` | `/learn/path` | `/today` | - |
| `Bookmarks.jsx` 빈 상태 | `/dashboard` | `/learn/path` | - |
| `ContentReview.jsx` `onExit` | `/dashboard` | `/today` | - |
| `App.jsx` `ErrorBoundary`, `NotFound` 홈 | `/learn/path` | `/today` | - |
| `Onboarding.jsx` '나중에 할게요' | `/learn/path` | `/today` | - |

바꾸지 않는 곳: `StageGate`의 `/learn/path`, `Practice.jsx`의 `reviewReturn`과 `/learn/path`, `SpeakingPractice.jsx`, `ListeningPractice.jsx`, `Placement.jsx`, `PilotBattery.jsx`의 나가기.

### 3.8 이름

`lib/iaLabels.js` 한 곳에 모은다. 등급은 `scripts/data/nikl_learner_vocab.tsv`, '없음'은 그 목록에 없다는 뜻이다.

| 자리 | 이름 | 등급 | 메모 |
|---|---|---|---|
| 탭 | 오늘 | A | |
| 탭 | 학습 | B | |
| 탭 | 기록 | C | 지시 지정 |
| 탭 | 내 정보 | 내 C, 정보 B | 지시 지정 |
| 트랙 | 입모양 읽기 | 입 A, 모양 B, 읽다 A | '입모양' 한 낱말로는 없음 |
| 트랙 | 말하기 | 말하다 A | |
| 트랙 | 소리 듣기 | 소리 B, 듣다 A | |
| 구역 | 단계 | C | 이미 쓰는 말 |
| 구역 | 자유 연습 | 자유 B, 연습 A | |
| 구역 | 자료 | B | |
| 기록 구역 | 요약 | 없음 | 대안 없음. 바꾸려면 '한눈에 보기' |
| 기록 구역 | 틀린 문장 | 틀리다 B, 문장 B | |
| 기록 구역 | 저장한 문장 | 저장 없음, 문장 B | 지시 지정. audit 대안은 '남긴 문장'이고 라벨 한 줄만 바꾸면 된다 |
| 버튼 | 이어서 학습하기 | 이어서 C, 학습 B | 지금 문구 |
| 버튼 | 학습 시작하기, 복습 시작하기 | B, A | |

문구 바꾸는 범위:

| 범위 | 바꿈 |
|---|---|
| 셸, 트랙 전환, 오늘, 기록, 내 정보, 학습 구역 | '입모양 읽기·말하기'로 바꾼다. |
| 과제 라벨 | 서버는 그대로. `iaLabels`에서 `read_once`를 '입모양 읽기 1회'로 표시한다. |
| `GuideModal`, `GuideMockups`, `ReviewItems`의 트랙 배지, `CurriculumPath` 헤더 | 바꾼다. |
| 레슨 안 화면 문구 | 정리 단계에서 사용자에게 보이는 글자만, 검사·실험 화면을 뺀 곳에서 바꾼다. |
| 검사·파일럿 화면, 처리방침, 서버 응답 값(`독화`·`발화` 비교에 쓰는 값) | **바꾸지 않는다.** `ReviewItems`의 `it.track === '발화'` 같은 비교를 조심한다. 표시만 바꾼다. |

새 안내 문구는 추가하지 않는다. 오늘의 윗줄 한 줄과 잠김 공통 안내(이미 있음)가 전부다. 구역 제목 아래 설명 줄도 두지 않는다.

---

## 4. 핵심 과제 8개 클릭 수

측정 조건: 2026-11-02, `https://liplab-dev.fly.dev`, 데모 계정(로그인 화면 '둘러보기'), 크로미움, 폰 390×844 · 컴퓨터 1440×900, `liplab_mute='1'` 먼저 설정, 이용 기록 전송 막음, 답 제출·시나리오 시작·건너뛰기·초기화 안 함. 시작점은 로그인 뒤 첫 화면 `/learn/path`다.

첫 방문 안내(수어 안내 '알겠어요' 1번, 소리 듣기 안내 '확인' 1번)는 과제 클릭에서 뺐다. 처음 쓰는 사람은 **그만큼 더 누른다.** dev 판(`index-BixP5BTH.js`)과 기준 커밋이 같은지는 확인하지 않았다.

| # | 과제 | 누르는 순서(지금) | 폰 | 컴퓨터 | 설계 목표 | 새 순서 |
|---|---|---|---|---|---|---|
| 1 | 첫 시작 | 건너뛰기 → 나중에 할게요 → 학습 시작하기 | **3** (측정*) | **3** (측정*) | **3** | 건너뛰기 → 나중에 할게요 → 학습 시작하기(오늘) |
| 2 | 이어서 학습 | 레슨 카드 '이어서 학습하기' | **1** (측정**) | **1** (측정**) | **1** | 오늘의 큰 버튼 |
| 3 | 트랙 바꾸기 | 학습 탭에서 트랙 버튼 | **1** (측정) | **1** (측정) | **1** | 같음 |
| 3-1 | 다른 탭에서 트랙 바꾸기 | 학습 탭 → 트랙 버튼 | **2** (측정) | **2** (측정) | **2** | 같음 |
| 4 | 오늘 복습 | 복습 탭 → 틀린 문제 복습하기 | **2** (측정) | **2** (측정). 패널 '복습하기'로 **1** (측정) | **1** | 오늘의 '복습 시작하기' |
| 5 | 틀린 문장 찾기 | 복습 탭 → '틀린 문제' 칩 | **2** (측정). 전용 화면까지 3 | **2** (측정). 전용 화면까지 3 | **2** | 기록 탭 → 틀린 문장 |
| 6 | 듣기 진행 보기 | 소리 듣기 트랙 → 결과 보기 | **2** + 스크롤(시트에 가림) (측정) | **2** (측정) | **2** | 기록 탭 → 소리 듣기 칩 |
| 7 | 접근성 설정 | Aa 버튼 | **1** (측정) | **1** (측정) | **1** | 같음. 내 정보 탭 → 접근성 설정 줄(2)도 생김 |
| 8 | 소리 교실 찾기 | 연습 탭 → 소리 교실 카드 | **2** + 스크롤 (측정) | **2** + 스크롤 (측정) | **3~4** | 학습 탭 → (트랙) → 자료 → 소리 교실. 트랙이 소리 듣기로 기억돼 있으면 3, 아니면 4 |

\* 서버 변경 없이 재려고 `/api/curriculum/stages`를 새 사용자처럼 가로채고 `POST /curriculum/track`을 막았다. `/learn/viseme`에 도착했다. 가입 양식 입력은 재지 않았다(코드: 이메일·비밀번호·동의 뒤 온보딩으로 온다).

\*\* 데모는 4단계가 현재 단계라 상황 입력 칸에 도착했다. 문항까지는 상황을 쓰고 '시작하기'를 더 눌러야 한다(코드: 입력 + 1클릭). 1·2단계와 말하기·소리 듣기는 바로 레슨으로 간다(코드, `/learn/viseme` 도착은 측정). 새 구조에서도 같다.

설계 목표는 구현 전 값이다. 구현 뒤 같은 스크립트를 고쳐 다시 재서 `comparison.html`에 낸다. 데모 계정은 `listen_started`가 거짓이라 6번은 기록 탭에 소리 듣기 칩이 안 보인다. 6번 재측정은 `/api/listen/links` 응답을 가로채 `listen_started: true`로 하고 그 사실을 적는다.

**숫자가 나빠지는 곳을 숨기지 않는다**

| 과제 | 지금 | 목표 | 이유 |
|---|---|---|---|
| 8. 소리 교실 | 2 | 3~4 | 자료를 구역으로 나눠서 한 번 더 누른다. 대신 스크롤이 없어지고, 소리 듣기를 안 쓰는 사람의 첫 화면에서 빠진다. |
| (8개 밖) 입모양 교실 | 2 (코드) | 3~4 | 같은 이유 |
| (8개 밖) 상황별 시나리오 | 2 (코드) | 3~4 | 자유 연습 구역을 거친다. 입모양 읽기 3·4단계의 입구로는 그대로 1~2 |

구현 후 8번이 불편하다는 파일럿 결과가 나오면 소리 듣기 단계 구역에 소리 교실 링크를 돌려놓는 것이 첫 대안이다.

---

## 5. 이용 기록과 옛 주소

### 5.1 경로 이름에 기대는 곳

| 곳 | 기대는 방식 | 할 일 |
|---|---|---|
| `backend/usage_events.py` `ROUTES` | 허용 목록. 없는 경로는 `route=NULL`로 저장 | `/today`, `/records` **추가**. 옛 경로는 지우지 않는다. |
| `backend/usage_events.py` | `/listen/practice/:mode`는 정규식 | 그대로 |
| `backend/feedback.py` | 같은 `ROUTES`를 가져옴 | 자동 반영 |
| `frontend/src/lib/track.js` `trackRoute` | `/learn|practice|review|analysis|tasks|listen/` 정규식이 `feature_open`을 보냄 | 정규식에 `today|records` 추가. `track.test.mjs`에 경우 추가 |
| `track.js` `trackRoute` | `/learn/`이면 `stage_enter`(마지막 조각) | 그대로 |
| `track.js` `track` 값 | 경로 글자로 추정 | **그대로**. 5.3절 |
| `frontend/src/lib/feedback.js` `screenName` | 경로별 이름표 | `/today` 오늘, `/records` 기록, `/profile` 내 정보, `/learn/path` 학습, 옛 `/practice/hub`와 `/tasks` 줄은 지움 |
| `components/A11ySettings.jsx` `LESSON_PATHS` | 정확히 같은 경로 | 그대로. `/today`, `/records`는 셸 화면이라 넣지 않는다. |
| `SpeakingPractice.jsx` | pathname이 `/review/speaking/session`인지 | 그대로 |
| `AppShell.jsx` `useLearnTrack` | `/learn/path` | 그대로 |
| `docs/pilot-data-spec.md` 130행 | '화면 경로, 트랙' 수집 명시 | 수집 항목은 그대로. 5.3의 전환 사실 한 문단 추가 |
| `scripts/pilot_retention.py` | 시각만 씀 | 영향 없음 |
| `/api/admin/usage` | route를 그대로 내보냄 | 영향 없음, 분석 쪽에서 5.3 표를 쓴다 |

### 5.2 옛 주소를 쓰는 곳

3.7절 표에 없는 것만 적는다.

| 곳 | 옛 주소 | 처리 |
|---|---|---|
| `AppShell.jsx` `NAV`, `Rail*` | `/practice/hub`, `/tasks`, `/review`, `/analysis` | 1단계에서 교체·삭제 |
| `AppShell.jsx` 상단 아바타 | `/profile` | 삭제 |
| `App.jsx` 241, 262~268, 280, 284, 285, 174·175, 20, 220행 | 위 표 | 2.1절 대로 |
| `AnalysisTab.jsx` `FullStats`, `SessionDetail` | `/analysis/listening`, `row.route` | `RecordsPage`로 옮길 때 `/records?track=listen`. `row.route`는 서버 값이라 그대로 |
| `ListenPath.jsx` 83, 88행 | `/analysis/listening`, `/listen/classroom` | 3.3절 |
| `ListenToday.jsx` 결과 보기 | `/analysis/listening` | `/records?track=listen` |
| `Placement.jsx` 252, 376행 | `/analysis/eval` | 그대로 |
| `TasksPage.jsx` `review_clear`, `listen_15` | `dueStartPath`, `/listen/today?from=tasks` | 옮길 때 `todayReviewStart`, `?from=today` |
| `ReviewLanding.jsx` `mode='today'` 코드 | 라우트 없음 | 정리 단계에서 삭제 후보 (7.6절) |
| `GuideModal.jsx` 76, 89, 97, 107, 182, 183행, 197~257행 탭 설명 | 탭 이름 | 정리 단계에서 다시 쓴다 |
| `guide/GuideMockups.jsx` 326, 603행, `MOCKS` 918~936행 | 그림과 alt | 정리 단계. `overview`·`learn`·`analysis`·`profile`은 고치고 `practice`·`task`·`review`는 오늘·기록 그림으로 교체 |
| `A11ySettings.jsx` 88, 136행 | `/profile`, '프로필 → 계정 설정' | 주소 유지, 글자 '내 정보 → 계정 설정' |
| `Legal.jsx` 88~89행 | '프로필 → 계정 설정' | **바꾸지 않는다** (3.6절) |
| `frontend/public/sw.js` | 탭 주소 없음(`SHELL`은 `/`와 자산뿐), 이동은 네트워크 우선 | 주소 변경 불필요. 셸을 바꾸므로 `CACHE`를 `liplab-v7`로 올린다. `swCache.test.mjs` 통과 확인 |
| `frontend/public/manifest.webmanifest` | `start_url: '/'` | 그대로 (`/`가 `/today`로 간다) |
| 푸시 알림 | 없음(`showNotification`, `webpush` 검색 결과 없음) | 할 일 없음 |
| `backend/curriculum.py` 154~157행 | STAGES route | 그대로 (주소 유지) |
| `backend/main.py` 1437~1464행 | 활동 route | 그대로 (`/review/mistakes`, `/learn/*`만 쓴다) |
| `backend/listen_curriculum.py` 1227, 1265행 | `/listen/practice/...`, `/learn/viseme?v=` | 그대로 |
| `backend/daily_tasks.py` | 주소 없음 | 그대로 |
| `scripts/qa_crawl.mjs` 9행 | 경로 목록 | `/today`, `/records` 추가, 리다이렉트 경로는 남김 |
| `scripts/test_tab_load.mjs` 45~49, 53~54행 | `/review`와 빈 상태 글, `/tasks`와 '오늘의 과제' | `/records?view=wrong`, `/today`와 새 화면의 글로 변경 |
| `docs/api-security-inventory.md` 등 문서 4개 | `/tasks`는 API 경로 뜻 | 수정 불필요(API 경로다) |
| `CLAUDE.md`, `STATUS.md` | 탭 구조 설명 | 정리 단계에서 갱신 |

### 5.3 이전 기록과 맞추는 방법

**옛 행은 고치지 않는다(UPDATE 금지).** 분석할 때 아래 표로 읽는다. 전환 시점은 dev·전시 배포 시각을 `docs/pilot-data-spec.md`에 적어 `ts`로 나눈다. `app_version`은 쓰지 않는다.

| 옛 route | 전환 뒤 같은 뜻 | 메모 |
|---|---|---|
| `/learn/path` | `/learn/path` | 같음 |
| `/practice/hub` | `/learn/path` + `tab_open` `learn:free:*` | 옛 행은 트랙 구분 없음 |
| `/tasks`, `/review/hub`, `/review/today` | `/today` | |
| `/review` | `/today`, 또는 `/records` + `tab_open` `records:wrong:*` | 옛 복습 탭이 두 역할을 했다. 나눌 수 없다. |
| `/analysis`, `/analysis/hub`, `/analysis/overview` | `/records` | |
| `/analysis/listening` | `/records` + `tab_open` `records:summary:listen` | 쿼리는 저장되지 않는다 |
| `/sign` | `/learn/sign` | |
| `/dashboard`, `/` | `/today` | |
| 그 밖 레슨·세션 경로 | 같음 | |

전환 뒤 기록 규칙:

| 항목 | 결정 |
|---|---|
| 쿼리 | 서버가 저장하지 않으므로 그대로 둔다. |
| 구역·트랙 구분 | 이미 허용된 이벤트 `tab_open`을 쓴다. `track('tab_open', {action})`. `action`은 `learn:free:listen`, `records:wrong:read`처럼 `화면:구역:트랙`. `identifier()` 정규식을 통과하고 스키마 변경이 없다. 지금 프런트에는 보내는 곳이 없어 옛 행과 섞이지 않는다. |
| `track` 필드 | 고치지 않는다. 고치면 같은 칸의 뜻이 전환 시점에 달라진다. `/learn/path`, `/today`, `/records` 행의 `track`은 전환 전후 모두 **믿지 않고**, `tab_open`을 본다. |
| 리다이렉트 중복 | 옛 주소로 들어오면 옛 경로와 새 경로가 각각 한 행씩 남을 수 있다 **(추측)**. 구현 때 확인해 보고에 적는다. 막지는 않는다. |

---

## 6. 건드리면 안 되는 것

| 분야 | 파일·이름 | 허용되는 변경 |
|---|---|---|
| 채점 | `backend/scoring.py`, `scoring_regress.py`, `scoring_regress_golden.json`, `articulation.py`, `formants.py`, `speak_curriculum.py`, `listen_curriculum.py`, `listen_placement.py`, `visual_difficulty.py`, `eval_metrics.py` | 없음 |
| 학습 규칙 | `backend/curriculum.py`, `srs.py`, `fsrs_shadow.py`, `mastery_probe.py`, `daily_tasks.py`; `main.py`의 `_STAGEn_*`, `_ewma_mastery`, `_settle_mastery`, `_bump_stage_progress`, `_compute_stages`, `_stage_open`, 복습 API; `frontend/src/lib/visemeTiming.js`, `hooks/useSlowWeak.js`, `lib/listenQuota.js`, `lib/pathNodes.js` | 없음. `lib/pathNodes.js`, `listenQuota.js`는 호출만 |
| 단계 잠금 | `App.jsx`의 `StageGate` 함수와 네 라우트(`/learn/word` 2, `/learn/nonsense` 2, `/practice` 3, `/conversation` 4), 되돌림 `/learn/path`; `ScenarioHub.jsx`의 잠금 버튼; `CurriculumPath.jsx`의 잠긴 노드 `disabled` | 없음 |
| 플래그 | `VITE_AV_COMPARISON`, `VITE_KMSAV_REVIEW`, `VITE_VISEME_V15`, `VITE_COART_E`, `VITE_RIG_MAP`, `VITE_LIPLAB_RESEARCH`, `VITE_LIPREAD_CHECK` 등 모든 `VITE_*`; `backend`의 모든 `LIPLAB_*`, `fly*.toml` | 기본값 변경 없음, 새 플래그 없음 |
| 검사·실험 화면 | `pages/Placement.jsx`, `PilotBattery.jsx`, `AvComparison.jsx`, `CueVideoDemo.jsx`; `components/listen/NoiseTest.jsx`, `WordTest.jsx`, `PlacementRun.jsx`, `LingCheck.jsx`; `components/EffortCheck.jsx`, `MasteryProbeBlock.jsx`, `RetentionPrompt.jsx`; `hooks/useMasteryProbes.js` | 없음. 모션·문구·배치 모두 그대로 |
| 레슨의 자극과 응답 | `VisemeLiteracy`(퀴즈), `WordStage`, `Practice`, `Conversation`, `Closure`, `NonsensePairing`, `SpeakingPractice`, `ListeningPractice`, `ListenPractice`, `ListenToday`, `ListenReview`, `Review` | 나가기 목적지와 3.7절 글자만 |
| 파일럿 도구 | `backend/pilot_battery.py`, `pilot_data.py`, `av_comparison.py`, `kmsav_review.py`, `content_review.py`; `scripts/pilot_*`; `docs/pilot/`; `pages/AdminFeedback.jsx`, `ContentReview.jsx`, `KmsavReview.jsx` | `ContentReview`의 `onExit` 목적지만 |
| 재생 지연 기록 | `lib/measurement.js`(`trialMeta`, `rt_from_onset_ms`), `lib/listenAudio.js`(`outputLatencyMs`, 블루투스 보정), `lib/frameClock.js`, `hooks/useLessonTalker.js`; `database.py`의 `rt_from_onset_ms`, `output_latency_ms` | 없음 |
| 듣기 안내 | `ListenNotice.jsx`, '진단·치료하지 않아요', 합성 음성 표시, 소리 조건(`useSoundCondition`, `useSoundReplay`) | 없음 |
| 이용 기록 저장 | `usage_events` 표 구조, `EVENTS`, `PROPS`, 옛 행 | `ROUTES`에 두 개 추가만 |
| 법적 문구 | `pages/Legal.jsx` 내용과 판본 | 없음 |

---

## 7. 구현 단계

단계마다 커밋한다. 커밋마다 `npm test`와 `npx vite build`를 통과시킨다. 앱은 단계마다 쓸 수 있어야 한다.

공통 재료(새로 만들지 않는다):

| 종류 | 이름 |
|---|---|
| 컴포넌트 | `components/UI.jsx`의 `Button`, `Card`, `Chip`, `Progress`, `EmptyState`, `TableRegion`, `MotionPanel`, `useUIMotion`; `Modal`, `LoadFailed`, `LoadingScreen` |
| 토큰 | `--control-min`, `--radius-control`, `--radius-card`, `--space-card`, `--text-body`, `--text-title`, `--focus-ring`, `--tabbar-h`, `[data-track]`의 `--track*` |
| 클래스 | `.ui-card`, `.ui-chip`, `.card`, `.icon-chip`, `.icon-chip-sm`, `.side-item`, `.side-item-active`, `.btn-primary`, `.btn-secondary`, `.btn-lg`, `.btn-md`, `device-mobile-sheet`, `device-mobile-path` |
| 모션 | `lib/uiMotion.js`의 `UI_MOTION`, `entranceMotion(reduced, 'card'|'page')`. 오늘의 카드와 구역 전환에만 쓴다. 검사, 자극 제시, 응답 대기에는 쓰지 않는다. 동작 줄이기 설정을 따른다. |

### 7.1 1단계: 셸·탭

| 항목 | 내용 |
|---|---|
| 바꿀 파일 | `components/AppShell.jsx`, `App.jsx`, 새 `components/LegacyRedirect.jsx`, 새 `lib/lastTrack.js`, 새 `lib/iaLabels.js`, 새 `pages/TodayPage.jsx`(이 단계는 제목과 큰 버튼 '학습으로 가기'만), 새 `pages/RecordsPage.jsx`(이 단계는 `AnalysisTab` 본문만), `lib/track.js`, `lib/feedback.js`, `backend/usage_events.py`, `public/sw.js`, `pages/ProfilePage.jsx`, 3.1.1 표의 파일 |
| 주의 | 이 단계에서는 `/tasks`, `/review`, `/practice/hub`를 **리다이렉트하지 않는다.** 내용이 옮겨 갈 때까지 라우트로 남긴다. 탭에서만 뺀다. 탭 강조는 임시로 today·learn에 맞춘다. |
| 완료 확인 | 폰·아이패드·컴퓨터에서 탭 4개(스크립트로 이름 비교), 오른쪽 패널 없음, `test_usage_events.py` 통과(`/today`, `/records` 저장 경우 추가), 1280·1440·1920 본문 폭 스크린샷, Aa 버튼이 열림 |

### 7.2 2단계: 오늘

| 항목 | 내용 |
|---|---|
| 바꿀 파일 | `pages/TodayPage.jsx`, 새 `lib/todayNext.js`+테스트, 새 `lib/trackPath.js`, `lib/reviewDue.js`(`todayReviewStart` 추가)+테스트, `pages/CurriculumPath.jsx`(함수 빼기만), `pages/TasksPage.jsx`의 조각을 `components/today/`로, `pages/ListenToday.jsx`, `pages/ListenReview.jsx`, `pages/Review.jsx`, `pages/SpeakingReviewLanding.jsx`, `pages/Onboarding.jsx`, `App.jsx`(`/`, `/dashboard`, `/tasks`, `/review*` 처리) |
| 완료 확인 | `todayNext` 표 10줄 테스트 통과; 응답 가로채기로 2·3번 규칙 화면 확인; `tasksAPI.claim` 호출과 토스트 확인; iPhone SE에서 큰 버튼이 첫 화면에 있음; 소리 확인 전 계정에서 듣기 칩·오늘의 듣기 안 보임; `/tasks`, `/review`, `/dashboard`, `/review/today` 도착 주소 확인 |

### 7.3 3단계: 학습 트랙 구조

| 항목 | 내용 |
|---|---|
| 바꿀 파일 | `pages/LearnPath.jsx`, 새 `components/learn/LearnHeader.jsx`, `TrackSwitcher.jsx`, `SectionTabs.jsx`, `LearnCard.jsx`, `LearnSection.jsx`, 새 `lib/learnSections.js`+테스트, `pages/CurriculumPath.jsx`, `pages/ListenPath.jsx`, `App.jsx`(`/practice/hub`, `/sign`), `pages/VisemeLiteracy.jsx`, `Closure.jsx`, `ListenClassroom.jsx`, `ListenPractice.jsx`, `lib/listenFlow.js`+테스트, `Sign.jsx`, `FreeSpeak.jsx`, `EndlessPractice.jsx`, `ScenarioHub.jsx`, `MultiConversation.jsx`; `PracticeHub.jsx` 삭제 |
| 완료 확인 | 세 트랙 × 세 구역 9칸 스크린샷; 소리 확인 전 응답으로 공통 잠김 한 줄과 버튼 확인; 2단계 안 열린 응답에서 '뜻 없는 말' 안 보임; 잠긴 단계 `/practice` 직접 진입이 `/learn/path`로 감; iPhone SE 세로·가로에서 시트 가림·넘침 0; 옛 연습 카드 11개가 모두 도착 주소로 연결 |

### 7.4 4단계: 기록

| 항목 | 내용 |
|---|---|
| 바꿀 파일 | `pages/RecordsPage.jsx`, 새 `components/records/ListenReportBody.jsx`, `ReviewItems.jsx`, `TrackSummary.jsx`; `pages/AnalysisTab.jsx`, `ListeningReport.jsx`, `ReviewTab.jsx`, `TasksPage.jsx` 삭제(조각은 옮김), `AnalysisDetail.jsx`, `Bookmarks.jsx`, `ReviewLanding.jsx`, `EvalReport.jsx`, `App.jsx`(`/analysis*`), `AppShell.jsx`에서 옮긴 `Rail*` |
| 완료 확인 | 구역 3 × 칩 4 스크린샷; 소리 듣기 보고서 숫자가 옮기기 전과 같음(같은 데모 응답으로 비교); 선택 삭제, `openItem` 경로 동작; `listen_started` 거짓에서 칩 숨김, `?track=listen` 직접 진입은 보임; `/analysis/listening`, `/analysis` 도착 주소 확인 |

### 7.5 5단계: 정리

| 항목 | 내용 |
|---|---|
| 바꿀 파일 | `GuideModal.jsx`, `guide/GuideMockups.jsx`, 3.8절의 문구, 3.7절의 나머지, `A11ySettings.jsx` 문구, `lib/learnerProfile.js`, `docs/pilot-data-spec.md`, `CLAUDE.md`, `STATUS.md`, `scripts/qa_crawl.mjs`, `scripts/test_tab_load.mjs`, `tab_open` 호출, 7.6절 삭제 |
| 기기 점검 포함 | `out\devices-2026-11-02\findings.md`의 작은 터치 후보(소개 로고, 프로필, 접근성 설정, 나가기, 보청기·인공와우 칩, 분석 탭)와 하단 탭 가림 후보(회차 히스토리, 문장 테스트, 활동 캘린더, 시작하기, 소리 확인)를 새 화면에서 다시 검사한다. iPhone SE 수정(`24de2f81`, `de28aecd`)의 클래스와 줄바꿈을 유지한다. 최근 점검(`out\practice-2026-11-02\summary.json`)은 44px 미만·넘침 0이었으니 그 값에서 나빠지면 안 된다. |
| 완료 확인 | 전체 검증: `npx vite build`, `npm test`, backend pytest, `scoring_regress`, 대비 검사, 기기 점검(Playwright + Android Emulator); 2절 표의 **모든 경로**를 도는 자동 검사(옛 주소 도착 일치, 빈 화면 없음); 사용자 글자에 '연습 탭', '복습 탭', '과제 탭', '분석 탭'이 남지 않음(`grep`); `scripts/easy_korean_audit.py` 통과율이 지금(32.4%)보다 낮아지지 않음; 8개 과제 재측정, 폰·아이패드·컴퓨터 전후 스크린샷을 `out\ia-2026-11-02\comparison.html`에 |

### 7.6 안 쓰는 화면

라우트 없음, `import`·`lazy` 호출 없음을 `grep`으로 확인했다. 지우기 직전 다시 `grep`하고 빌드한다.

| 지울 후보 | 확인 |
|---|---|
| `features/dashboard/Dashboard.jsx` | 호출 0 |
| `features/dashboard/ActivityCalendar.jsx` | 호출 0 |
| `features/dashboard/ReviewSection.jsx` | 호출 0 |
| `features/dashboard/NextUpCard.jsx`, `LearnerProfileCard.jsx`, `components/DashboardPet.jsx` | `Dashboard.jsx`에서만 호출 |
| `features/dashboard/buildQTypes.js` | `Dashboard.jsx`, `ReviewSection.jsx`에서만 호출 |
| `layouts/AppLayout.jsx` | 호출 0 |
| `layouts/NavShell.jsx`, `TopBar.jsx` | `AppLayout.jsx`에서만 호출 |
| `components/MouthMirror.jsx` | `import` 호출 0 (`lib/mouthMirror`는 별개이므로 지우지 않는다) |
| `ReviewLanding.jsx`의 `mode='today'` 분기 | 라우트는 `mode="mistakes"`뿐 |
| `pages/PracticeHub.jsx`, `TasksPage.jsx`, `ReviewTab.jsx`, `AnalysisTab.jsx`, `ListeningReport.jsx` | 이번 개편으로 내용을 옮긴 뒤 |

| 확신이 없어 남길 것 | 이유 |
|---|---|
| `features/learn/shared/*` (`TrackHub`, `LessonList`, `LessonRunner`, `LessonComplete`, `useTrackLessons`, `trackProgress`), `config/tracks.js` | 화면 호출은 없지만 테스트(`trackProgress.test.mjs`, `tracks.test.mjs`)가 있다. 다른 작업의 준비 코드인지 모른다. |
| `pages/DevViseme.jsx`, `CueVideoDemo.jsx`, `KmsavReview.jsx`, `AvComparison.jsx`, `ContentReview.jsx`, `AdminFeedback.jsx`, `PilotBattery.jsx` | 플래그·운영·연구 도구 |
| `CurriculumPath.jsx` 안의 listen 코드 | 지금 쓰이지 않지만 `normalizeListen`을 옮길 때 건드리면 위험하다. 이번에는 남기고 보고한다. |

### 7.7 구현자가 조심할 것

| 위험 | 어떻게 되는가 | 막는 법 |
|---|---|---|
| 자동 보상과 공유 캐시 | `tasksAPI.claim`을 빠뜨리거나 `sharedGet` 순서가 바뀌면 보상과 숫자가 어긋난다. 오늘 탭은 과제 탭보다 자주 열린다. | `TasksPage`의 순서를 그대로 옮기고 두 번 들어와도 보상이 한 번인지 확인 |
| 맨 `/learn/path`에 기억 적용 | 입모양 읽기 레슨을 나왔는데 소리 듣기 화면이 뜬다. 잠긴 단계 되돌림도 엉뚱한 트랙으로 간다. | 기억은 `learnHref()`와 `/practice/hub` 리다이렉트에서만 쓴다 |
| 비교에 쓰는 글자까지 일괄 변경 | `it.track === '발화'`, `/소리 확인/.test(shared)`, 서버의 `독화` 값 비교가 조용히 깨진다. | 문구는 `iaLabels`로 표시할 때만 바꾸고, 바꾼 뒤 `grep`으로 비교식을 확인 |

---

## 8. 한계

| 항목 | 내용 |
|---|---|
| 사람 시험 | **사람으로 시험하지 않았다.** 이 문서와 `comparison.html`에는 클릭 수와 화면 수만 적는다. '쓰기 편해졌다'는 판단은 적지 않는다. |
| 클릭 수의 뜻 | 누른 횟수일 뿐, 찾는 시간이나 헷갈림은 재지 않았다. 스크롤과 첫 방문 안내는 따로 표시했다. |
| 측정 계정 | 공용 데모 계정 하나다. 모든 소리 듣기 단계가 열려 있고 입모양 읽기는 4단계까지 열려 있어, 새 사용자와 다르다. 첫 시작은 응답을 가로채 흉내 냈다. |
| 측정하지 못한 것 | 가입 양식, 시나리오 시작 뒤(LLM 비용), 소리 확인 전 실제 잠금 화면, 아이패드 폭. 아이패드는 구현 후 재측정에 넣는다. |
| 3·4단계 '이어서' | 한 번 눌러도 상황 입력 칸까지만 간다. 입력 없이 이어지려면 시나리오 저장과 LLM 호출 결정이 필요해 이번 범위에서 뺐다. |
| 다른 기기의 트랙 | 기기별로 저장한다. 다른 기기에서는 시도 수로 추정하므로 다른 트랙이 나올 수 있다. |
| 예비 파일럿 항목 | 실제 사용자에게 확인할 것: (1) 처음 온 사람이 오늘의 큰 버튼을 바로 누르는가, (2) 자유 연습·자료 이름으로 카드를 찾는가, (3) 소리 교실이 한 번 더 깊어진 것이 문제인가, (4) 소리 듣기를 안 쓰는 사람이 트랙 버튼을 방해로 느끼는가, (5) '저장한 문장', '요약', '입모양 읽기'를 이해하는가. |
