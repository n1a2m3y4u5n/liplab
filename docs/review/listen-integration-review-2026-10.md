# 소리 듣기 앱 전체 연동 코드 검토 (2026-10-07)

대상: 10/7 오후에 합쳐진 '소리 듣기 앱 전체 연동'. 프론트 500bc16c(연습 탭 묶음·소리 교실·오늘의 듣기 15분·듣기 복습·과제·분석 연결),
16c07797(머지), 9b4c7a3b(소리 교실 칩 줄·분석 분 반올림), 백엔드 b61926b1(`/api/listen/practice/*`, `/api/listen/today`, `/api/listen/review`,
`/api/listen/contrasts`, 요약 days의 minutes, 과제 listen_15, 분석 overview listen 칸, `listen_curriculum.today_plan` 등).
계약은 `docs/listen-integration-api-2026-10.md`, 이전 검토 `docs/review/listen-code-review-2026-10.md`에서 이미 고친 것(A1~A10, B1~B9)은 다시 적지 않는다.
브랜치 `listen-integration-review-2026-10`(integrate/2026-09-23 6869c548에서 시작).

방식: 결함마다 재현(테스트·스크립트·헤드리스 브라우저로 실패를 먼저 확인) → 수정 → 회귀 테스트. 브라우저는 Chrome `--mute-audio
--disable-features=MacAppCodeSignClone` 헤드리스로 띄우고, localStorage·sessionStorage `liplab_mute='1'`을 먼저 넣어
`(await import('/src/lib/listenAudio.js')).isMuted()`가 true인 것을 확인한 뒤에만 재생을 눌렀다(소리는 나지 않았다).
서버는 임시 DB로 백엔드 :8095, vite :5195(임시 설정 파일, 끝나고 지움)를 잠깐 띄웠다가 껐다.

심각도: 높음(학습·측정 결과가 틀리거나 화면이 멈춤), 중간(특정 조건에서 틀림·엉뚱한 소리), 낮음(표시 불일치·기록 누락·잠재 오류).

## 1. 고친 결함

| 번호 | 심각도 | 위치 | 결함 | 재현 | 수정 | 테스트 |
|---|---|---|---|---|---|---|
| R1 | 중간 | `frontend/src/pages/ListenClassroom.jsx` 62~73행(ListenPanel `playVoices`) | '같은 말, 다른 목소리'는 목소리마다 소리를 받은 뒤(await) 튼다. 받는 동안 다른 짝을 고르거나(판이 key로 새로 그려짐) 연습 탭으로 나가도, 받은 뒤 앞 짝의 소리가 재생됐다. 사라진 판의 재생기라 멈춤 버튼도 없다 | 헤드리스(음소거 확인 뒤): m1 외 목소리 소리 받기를 1.5초 늦추고 버튼을 누른 직후 다른 짝을 고름 → 재생 시작 1회. 고친 뒤 0회 | 판에 세대 값(`gen`)을 두고 짝·목소리가 바뀌거나 판이 사라지면 올린다. 받기 전 세대와 다르면 틀지 않는다 | 브라우저 재현 스크립트(JSX 컴포넌트라 `node --test` 대상 밖) |
| R2 | 중간 | `frontend/src/pages/ListenClassroom.jsx` 78~115행, `frontend/src/lib/listenFlow.js` 292~309행(`pairMissing`) | 소리 교실은 useClip의 못 받은 이유(reason)를 보지 않고 늘 '이 짝의 소리는 아직 준비되지 않았어요'라고 적었고, 다시 받기 버튼이 없었다. 인터넷이 잠깐 끊겨도 서버에 소리가 없는 것처럼 보이고, 같은 짝을 다시 눌러도 판이 새로 그려지지 않아 다시 받지 않는다 | 헤드리스: `/api/sound?` 요청을 끊으면 '준비되지 않았어요'만 보이고 버튼 없음 | 이유마다 글(`not_prepared`·`network`·`decode`)을 달리하고, 서버에 없는 소리가 아니면 '다시 받기'(두 소리 모두 다시 받음). 고친 뒤 끊김 → '인터넷 연결이 끊겨…' + 다시 받기, 누르면 '버튼을 누르면 소리가 나와요' | listenFlow.test '소리 교실 짝을 못 받은 이유' |
| R3 | 낮음 | `frontend/src/pages/CurriculumPath.jsx` 217행, `frontend/src/pages/ListenToday.jsx` 61·141~146행, `frontend/src/lib/listenFlow.js` 235·250~262행 | 과제 '소리 듣기 15분'은 오늘 분을 내림하는데(`daily_tasks.progress`, 14.6 → 14, 미달), 화면은 반올림했다. 14.6분이면 학습 경로 버튼이 '15 / 15분', 오늘의 듣기 끝 화면이 '15분 / 15분'인데 제목은 '오늘의 듣기를 마쳤어요'(미달)와 '1분쯤 남았어요'가 함께 보였다 | 오늘 14.6분인 사용자(임시 DB): 서버 과제 cur 14·미달, 고치기 전 계산으로는 화면 15 | `goalMinutes`·`fmtGoalMinutes`(내림)를 두고 목표와 견주는 곳(학습 경로 버튼, 오늘의 듣기 시작·끝 화면)에 쓴다. 남은 분은 보이는 내림 분 기준(`todayTotals().left`). 고친 뒤 헤드리스에서 '오늘의 듣기 · 14 / 15분', '오늘 연습한 시간 14분 / 15분' | listenFlow.test '목표 분은 과제 listen_15처럼 내림한다' |
| R4 | 낮음 | `frontend/src/pages/ListenToday.jsx` 92~94·115·136행 | 끝 화면이 오늘 기록을 다시 받기 전에(after = null) '시작 전 분 + 이번 회기 걸린 시간' 어림으로 먼저 그려졌다가 서버 분으로 바뀌었다. 걸린 시간은 3분 넘는 쉼도 세어 서버 분보다 클 수 있어, 15분 언저리에서 '오늘 15분을 채웠어요'가 잠깐 보였다 사라질 수 있다 | 코드 경로(받기 전 렌더 → 받은 뒤 렌더). 소리 재생이 필요한 회기 완주라 브라우저로는 재현하지 않음 | 받는 중(undefined)에는 자리 표시만 그리고, 받지 못했을 때(null)만 어림을 쓴다 | 없음(화면 상태, 순수 계산 todayTotals는 기존 시험) |
| R5 | 낮음 | `frontend/src/components/listen/ConvoTask.jsx` 70~72행 | 대화 문항 답에 잡음 이름(`noise`)을 조건을 고정했을 때만 붙였다. 문항마다 잡음을 돌리는 5단계와 상황별 대화 듣기 연습의 소음 조건은 `listen_attempts.noise`가 비어 어떤 잡음으로 들었는지 알 수 없었다(계약 2절·ListenAnswer 주석은 5단계 소음 종류를 남긴다고 함). 5단계 쪽은 b79d5157 전부터 있던 누락이다 | 헤드리스(음소거 확인 뒤): 장면 '병원·약국'에서 소음 조건으로 한 문항 → 고치기 전 코드 경로는 noise 없음 | 소음 조건이면 늘 들려준 잡음 이름을 보낸다. 고친 뒤 행 `noise | talker1_f | 10.0 | practice:scenario` | 브라우저 확인 |
| R6 | 낮음 | `backend/listen_curriculum.py` 1037~1041행(`practice_minutes`) | (시각, rt_ms) 짝 그대로 정렬해, 같은 시각에 rt_ms가 없는 시행(소리 확인·검사)과 있는 시행이 겹치면 None과 int 비교로 TypeError. 요약·오늘의 듣기·과제·분석·파일럿 내보내기(독화 reading_days 포함)가 모두 이 함수를 써서 500이 된다. 또 `_listen_today_minutes`는 ORDER BY가 없어 같은 시각의 순서가 요약과 달라질 수 있었다(겹치면 분이 다르게 나옴) | `practice_minutes([(t, None), (t, 5000)])` → TypeError | 시각으로 정렬하고 같은 시각이면 rt_ms가 있는 것을 앞에 둔다(들어온 순서와 상관없이 같은 값). 지금 기록에서 같은 시각은 드물어 잠재 결함이다 | test_listen_curriculum.test_practice_minutes(같은 시각·순서 뒤집기) |

## 2. 확인했고 문제가 없던 것

- **연습 세션이 새는 곳.** `listen_attempts`를 읽는 모든 곳을 훑었다. 단계 숙달·수준·4단계 계단·`/curriculum`·`/stage/{n}`의 level·weak·stair, 검사(`mode='test'`·`wordtest`)
  상태와 역치, 5단계 잡음 SNR(`_listen_noise_snr`)은 `_listen_attempts` 기본값(‘practice’·‘practice:*’ 뺌)이나 mode 'test'만 본다. 연습 답 경로는 진행 행을
  읽지도 쓰지도 않아 잠긴 단계가 연습으로 열리지 않는다(`_listen_open`의 'n in sp_map'). 내보내기 `trials_by_stage`에는 없고 `practice_by_mode`·`log`(session 칸)로 갈린다.
- **다시 쓴 답(practice: true) + practice_mode.** session이 'practice'가 되어 혼동·간격 복습·연습 계단·`by_mode`에 들어가지 않는다(새 흐름 시험으로 고정).
- **검사 문항이 연습으로 새는가.** 연습·복습 답은 훈련 문장(`TRAIN_BY_ID`), 훈련 낱말 풀(일반화 검사 낱말 제외), 대화(`CONVO_BY_ID`), 소리 구별 키만 받는다. 듣기 조건의
  잡음은 훈련 잡음만(talker2는 400), 소리 교실·연습 화면 목소리는 훈련 목소리만 쓴다.
- **오늘의 듣기 분과 15분 과제.** 요약 days(시행을 created_at + 9시간으로 묶음), `/api/listen/today`의 done_today(요약 days 그대로), 과제 listen_15
  (`_listen_today_minutes`: 오늘 0시 KST의 UTC부터 하루), 분석 week_minutes(요약 days 합)가 같은 시행·같은 `practice_minutes`를 쓴다. 판정은 `int(분) ≥ 15`이고
  오늘의 듣기 끝 화면의 '채웠어요'(분 ≥ 15)와 같다. 자정을 가로지르는 간격은 어느 날에도 넣지 않는다(새 흐름 시험: 어제 23시 59분 + 오늘 0시 1분부터 2분 간격).
- **날짜 경계.** 시드(`_kst_today`), 간격 복습 날짜(`_listen_day`), 요약 days, 과제, 분석 listen 칸이 모두 KST다. 분석 탭의 다른 칸은 화면의 tz_offset_min을 쓰고
  listen 칸만 KST인 것은 계약 6절에 적힌 대로다.
- **처음 사용자.** 오늘의 듣기는 소리 확인 한 블록, 연습 문항 GET은 409, 복습 0, 과제에 listen_15 없음, 분석 listen null(새 시험). 연습 탭 카드는 모두 잠김과 한 줄 안내.
- **인증·다른 사용자.** 새 엔드포인트 모두 `get_current_user`이고 조회가 user_id로 묶인다. 사용자 id를 받는 칸이 없다. A의 연습이 B의 요약·복습에 보이지 않는다(새 시험).
- **hooks 규칙.** 새 화면·컴포넌트(ListenPractice·PracticeSession·ContrastChooser·PlaceChooser·ListenToday·TodayBlock·ListenBlocks·ListenReview·ListenClassroom·
  ListenPanel·ContrastRun·PracticeHub·CurriculumPath)의 hook이 모두 이른 return 앞에 있고 조건 안에서 부르지 않는다.
- **언마운트 뒤 setState.** 데이터 받기는 대부분 `on` 깃발로 막혀 있다. 막지 않은 곳(소리 교실 목록·입모양 프레임, ContrastChooser, 제목 줄의 종류·장소 이름)은
  React 18 이후 경고도 부작용도 없어 두었다. 부작용이 있던 곳은 R1(소리 재생)뿐이다.
- **소리 준비 안 된 문항.** 과제 화면(소리 구별·낱말·문장·대화)은 이전 검토 A10대로 이유마다 문구와 다시 받기·넘기기가 있다. 소리 교실만 빠져 있었다(R2).
- **모바일 390px.** 헤드리스 390 × 844에서 `/practice/hub`, `/listen/classroom`, 연습 다섯 모드의 고르는 화면과 첫 문항(`?kind=place`, `?place=clinic`,
  `?condition=noise&noise=ssn`, 받아쓰기·소음 속 듣기), `/listen/today`(시작 화면과 첫 블록), `/listen/review`, `/tasks`, `/analysis`, `/review`,
  `/learn/path?track=listen`의 문서 가로 넘침과 화면 밖으로 나간 요소(가로 스크롤 줄 안은 뺌)가 0이었다. 콘솔 오류 0(R2 재현에서 일부러 끊은 요청 제외).
- **키보드.** 새 화면의 고르는 칸·짝·칩·장소·과제 줄이 모두 button이고, 잠긴 연습 카드는 disabled다. 스페이스·숫자·Enter는 입력칸·버튼 위에서 가로채지 않는다
  (`listenKeyAction`). 소리 교실의 스페이스(번갈아)·1·2도 같다.
- **문구.** 새 글에 '치료'·'청력 개선' 류 표현이 없다(학습 경로의 '진단하거나 치료하지 않아요' 안내만 있음).

## 3. 고치지 않은 것(취향·설계 결정·영향 작음)

1. **파일럿 사전 검사 전에 소음 훈련이 가능하다.** 단계 레슨 4단계는 사전 검사 안내(NoiseStage intro, `needs_pretest`)를 먼저 보이지만, 오늘의 듣기의 4단계 블록과
   연습 탭 '소음 속 듣기'는 안내 없이 훈련한다(계약 그대로, 의도된 설계). 청인 모의 파일럿(`docs/pilot/listen-vocoder-pilot-prereg.md`)에서 사전 검사를 앱 안내에
   맡긴다면 연습 효과가 사전 검사에 섞일 수 있다. 또 사전 등록의 훈련은 '1~5단계'이고 활동 대조 집단은 '왜곡된 소리에 노출하지 않음'인데, 연습 탭 소리 듣기 묶음은 두 집단
   모두에게 열린다. 파일럿 절차(검사를 먼저 감독 아래 보게 할지, 대조 집단에 연습 탭 듣기를 닫을지)는 연구 쪽에서 정할 일이라 코드는 두었다.
2. **복습 탭의 '듣기 복습' 카드는 듣기를 한 번도 안 한 사용자에게도 '다시 들을 소리가 없어요'로 보인다.** 분석 탭은 기록이 없으면 칸을 숨긴다. 어느 쪽이 맞는지는 화면 결정이라 두었다.
3. **`/api/review/due`의 listen_words는 보기를 만들기 전 수다.** `/api/listen/review`는 보기를 못 만드는 낱말을 뺀다. 지금 풀에서는 수준 1(2지)까지 내려 모두 만들어져 차이가 없고,
   프론트도 listen_count를 쓰지 않는다(복습 탭은 `/api/listen/review`의 목록 길이를 씀).
4. **엔드리스 연습에서 모든 문항을 넘기면(소리 준비 전) 시행 수(n_done)가 그대로라 다음 묶음이 같은 문장이다.** 저절로 되풀이되지는 않고(넘기기는 사람이 누름), 소리가 합성되면
   풀린다.
5. **연습 탭 멈춤 요약의 '연습한 시간'은 모드를 연 때부터 잰 벽시계 시간이다**(고르는 화면·쉼 포함). 서버의 연습 분과 정의가 다르지만 그 화면 안의 참고 값이라 두었다.
6. **TodayBlock의 finish가 렌더마다 새 객체다**(ListenBlocks의 done이 매번 새 함수). TaskEnd가 한 번만 보내도록 막혀 있어 동작 차이는 없다.
7. **잘못된 대조 이름(`?contrast=onset:ㅂ:ㅂ`)이나 모르는 장면 key**는 400·404라 연습 화면이 각각 '불러오지 못했어요(인터넷 확인)'·'준비 중'으로 보인다. 주소를 손으로 고친
   경우뿐이라 두었다.

## 4. 시험

- 백엔드: `test_listen_practice.py`에 두 번째 흐름 시나리오(임시 DB)를 더했다. 처음 사용자(오늘의 듣기·409·복습·과제·분석), 다시 쓴 답 + practice_mode가 혼동·복습·연습 계단·
  by_mode에 들어가지 않음, 다른 사용자 분리, KST 자정 경계에서 요약 days·오늘의 듣기·과제 listen_15·분석 week_minutes가 같은 날짜와 같은 분(14.5분 미달 → 16.5분 달성).
  `test_listen_curriculum.test_practice_minutes`에 같은 시각 겹침(고치기 전 TypeError)·순서 무관. 전체 `pytest -q` 733개 통과(시작 때 729개).
- 프론트: `listenFlow.test.mjs`에 목표 분 내림(`goalMinutes`·`fmtGoalMinutes`·`todayTotals().left`)과 소리 교실 못 받은 이유(`pairMissing`). `npm test` 317개 통과(시작 때 315개),
  `npx vite build` 통과.
- 브라우저(헤드리스, 음소거 확인 뒤): R1 재현(고치기 전 재생 1회 → 고친 뒤 0회), R2(끊김 → 이유 글·다시 받기 → 복구), R3(14.6분 → '14 / 15분'), R5(소음 이름 기록),
  390px 넘침 점검(2절).
