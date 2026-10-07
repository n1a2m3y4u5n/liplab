# 소리 듣기 앱 전체 연동 API (2026-10-07)

소리 듣기(청능훈련) 트랙을 독화·발화와 같은 수준으로 앱 전체(연습 탭, 복습 탭, 과제, 분석)에 넣는 개편의 백엔드 계약이다.
설계는 `docs/auditory-training-design.md`, 고도화 방안은 `docs/listen-advance-plan-2026-10.md`에 있다.
코드는 `backend/listen_curriculum.py`(문항을 만드는 순수 함수), `backend/main.py`의 `/api/listen/*`, `backend/daily_tasks.py`,
`backend/analytics.py`이고, 테스트는 `backend/test_listen_practice.py`(순수 함수 + 임시 DB 흐름)다.

모든 API는 로그인 토큰이 필요하다. 문항의 소리는 지금처럼 `GET /api/sound?text=&voice=`로 찾는다.

## 1. 엔드포인트 표

| Method | Path | 입력 | 응답(주요 칸) | 비고 |
|---|---|---|---|---|
| GET | `/api/listen/practice/modes` | 없음 | `{modes: [{key, title, desc, available, reason?}]}` | 단계 잠금과 무관. Ling 점검을 한 번도 안 했으면 모두 `available: false`와 `reason` |
| GET | `/api/listen/practice/contrast` | `contrast`(선택) | `{mode, n_done, contrast: {key, type, label, slot?, a?, b?, kind?}, source, level, items}` | 문항 12개. `items[].type`이 `ax`(stage 1) 또는 `word`(stage 2) |
| GET | `/api/listen/practice/dictation` | 없음 | `{mode, n_done, items: [{key, id, text, stage: 3}]}` | 10개, 최근에 들은 문장은 뒤로 |
| GET | `/api/listen/practice/noise_endless` | 없음 | `{mode, n_done, items: [{key, id, text, stage: 4}], stair: {practice_ao: {next_db, n_trials, n_reversals, srt_db}}, next_db, condition: "practice_ao", noise: "babble"}` | 10개. 연습 전용 계단 |
| GET | `/api/listen/practice/scenario/places` | 없음 | `{places: [{key, label, n, places}]}` | 장면 묶음 8개, 묶음마다 4문항 이상 |
| GET | `/api/listen/practice/scenario` | `place`(필수: 묶음 key 또는 장소 이름) | `{mode, n_done, place, items: [{key, id, place, line, paraphrase, question, options, stage: 5}], noise_snr_db, conditions, room_rt60, noise_types}` | 그 묶음 문항 전부. 정답 번호 없음. `place` 없으면 400, 모르면 404 |
| GET | `/api/listen/practice/conditions` | `cond`(phone·room·noise, 기본 phone), `noise`(선택, 훈련 잡음만) | `{mode, n_done, cond, noise, snr_db, items: [{key, id, text, cond, rt60?, noise?, snr_db?, stage: 3}], conds, noise_types, room_rt60}` | 10개. room은 잔향 0.3·0.5·0.8초를 돌림, noise는 종류를 고정하거나 돌림 |
| POST | `/api/listen/answer` | 지금 칸 + `practice_mode`(선택) | 지금과 같은 모양 + `counted: false`, `practice_mode` | 2절 |
| GET | `/api/listen/review` | 없음 | `{words: [{key, target, options, level, stage: 2}], sentences: [{key, id, text, stage: 3}], n}` | 낱말 최대 10, 문장 최대 5 |
| GET | `/api/listen/contrasts` | 없음 | `{kinds: [{kind, label, practice_key, lip, desc, pairs: [{a, b, level, lip_same}], words: [{target, partner, distance, contrast, lip_same}]}]}` | 소리 교실. 채점 없음 |
| GET | `/api/listen/today` | 없음 | 지금 칸 + `review_due` | 오늘 복습할 듣기 문항 수를 더함 |
| GET | `/api/listen/summary` | 없음 | 지금 칸 + `practice: {by_mode, noise_srt_db, n_noise}` | 3절 |
| GET | `/api/review/due` | 없음 | 지금 칸 + `listen_count, listen_words, listen_sentences, total_with_listen` | `total`은 그대로(듣기 미포함) |
| GET | `/api/tasks`, POST `/api/tasks/claim` | 없음 | 지금 칸. 듣기를 시작한 사용자는 `daily`에 `listen_15` | 5절 |
| GET | `/api/analysis/overview` | 지금 칸 | 지금 칸 + `listen`(시작 안 했으면 null) | 6절 |

연습 모드 문항 GET은 Ling 점검(소리 확인)을 한 번도 안 했으면 409(`detail`에 안내 문구)다. 모르는 모드는 404다.
부를 때마다 이어지는 새 묶음을 준다(seed = 사용자·KST 날짜·그 모드의 시행 수 `n_done`). 같은 시행 수에서 다시 부르면 같은 묶음이다.

### 1.1 contrast 쿼리

| 꼴 | 예 | 뜻 |
|---|---|---|
| `onset:<자음>:<자음>` | `onset:ㅂ:ㅍ` | 첫소리 대조. 소리 없는 첫소리는 `ㅇ` |
| `vowel:<모음>:<모음>` | `vowel:ㅓ:ㅗ` | 모음 대조. ㅐ·ㅔ처럼 소리가 같은 짝은 400 |
| `coda:<받침>:<받침>` | `coda:ㄴ:ㅁ`, `coda:ㄴ:-` | 받침 대조. 7대표음, 받침 없음은 `-` |
| `kind:<종류>` | `kind:fricative` | 소리 구별 종류(`length, intonation, vowel, manner, laryngeal, place, fricative, coda`) |

- 문항: 같다·다르다(그 대조로만 갈리는 소리 구별 짝, 같음·다름 반반)와 낱말 고르기(그 대조 하나로만 갈리는 이웃을 보기에 꼭 넣은 4지)를 반씩 섞는다.
  한쪽이 없으면 다른 쪽으로 12개를 채운다(예: `kind:length`·`kind:intonation`은 낱말이 없어 같다·다르다만, `coda:ㄴ:ㅁ`은 풀에 그 대조 하나로만 갈리는 낱말이 없어 같다·다르다만).
- 낱말 문항의 수준은 2단계 지금 수준을 2~3으로 자른 값(`level`)이다. 수준 2는 나머지 보기가 소리 거리 3~6, 수준 3은 1~2다.
- `contrast`가 없으면 `source`가 정한다: `confusions`(낱말 고르기 오답의 혼동 상위, 연습 답 포함) → `ax_stats`(소리 구별에서 다름 시행 4번 이상이고
  정답률 0.9 미만인 가장 약한 종류, Ling에서 쉬·스가 모두 안 들렸으면 마찰음 제외) → `default`(`kind:place`, 보청기·인공와우 사용자가 가장 자주 놓치는 자리 대조).

### 1.2 장면 묶음

장소 이름(`CONVO_ITEMS[].place`)은 문항마다 달라 장소 하나에 한 문항뿐인 곳이 대부분이었다. 그래서 비슷한 장소를 묶었다(`listen_curriculum.SCENES`).

| key | label | 장소 | 문항 수 |
|---|---|---|---|
| clinic | 병원·약국 | 병원, 약국, 병원 접수 | 4 |
| food | 식당·카페 | 카페, 식당, 식당 주문 | 4 |
| transit | 교통 | 버스 안내, 지하철, 기차역, 택시 | 4 |
| shop | 가게·은행·우체국 | 은행, 마트, 미용실, 가게, 우체국 | 5 |
| home | 집·동네 | 아파트, 집, 관리실 안내 | 4 |
| work | 학교·회사·도서관 | 학교, 회사, 수업, 도서관 | 5 |
| notice | 안내 방송 | 일기 예보, 건물 안내, 안내 방송, 도서관 안내 | 4 |
| friends | 친구·전화 | 전화, 친구, 약속 | 4 |

`?place=`에는 key를 쓴다. 장소 이름 하나(예: `병원`)를 주면 그 장소 문항만 준다.

## 2. 답 보내기(POST /api/listen/answer)

`practice_mode`가 없으면 지금과 똑같다. 있으면 같은 방식으로 채점하고 시행을 `session = 'practice:<모드>'`로 남기기만 한다.
단계 숙달·수준·4단계 계단·단계 상태는 바뀌지 않고, 단계가 잠겨 있어도 받는다.

| practice_mode | 받는 stage | 함께 보내는 칸 | 응답에서 지금과 다른 것 |
|---|---|---|---|
| contrast | 1(같다·다르다 `same`), 2(낱말 `answer`, `level`) | 1·2단계와 같음 | `counted: false`, `practice_mode`. `level`·`level_changed`·`mastery_score`·`status` 없음 |
| dictation | 3 | `answer` | 위와 같음. 정답 기준은 3단계(낱말 0.75) |
| noise_endless | 4 | `answer`, `snr_db`(필수, 없으면 400) | `stair: {practice_ao: …}`, `next_condition: "practice_ao"`(4단계의 `stair.ao·av` 대신) |
| scenario | 5 | `choice`, `condition`(quiet·noise·phone·room) | 위와 같음(`answer`·`line`은 그대로 줌) |
| conditions | 3 | `answer`, `condition`(phone·room·noise, 필수), noise면 `snr_db`(필수)·`noise` | 위와 같음. noise 조건은 낱말 절반, 나머지는 0.75 |
| review | 2(낱말), 3(문장) | 2·3단계와 같음 | 위와 같음 |

- 모드와 stage가 맞지 않거나 모르는 모드면 400.
- `practice: true`(자음 단서를 본 뒤 다시 쓴 답)를 함께 보내면 지금처럼 `session = 'practice'`로 남긴다. 그 답은 복습·혼동에도 넣지 않는다.
- 시행 칸: noise_endless는 `condition = 'practice_ao'`, `noise = 'babble'`. conditions는 `condition`에 고른 조건, noise일 때만 `snr_db`·`noise`.
  울리는 방의 잔향 시간은 기록 칸이 없어 남기지 않는다(화면이 문항의 `rt60`을 쓴다).
- 연습 계단은 4단계 계단과 같은 규칙(`STAIR`, +10 dB 시작, 처음 두 번 방향이 바뀔 때까지 4 dB, 그 뒤 2 dB, 범위 −10 ~ +25 dB)이고
  `practice:noise_endless` 시행만으로 센다.

### 2.1 시행이 어디에 들어가는가

| 쓰는 곳 | session 없음(단계 훈련) | 'practice' | 'practice:*' |
|---|---|---|---|
| 단계 숙달·수준·단계 상태(`/curriculum`, `/stage/{n}`의 level·stair) | 넣음 | 뺌 | 뺌 |
| 4단계 계단·훈련 역치(요약 `training`) | 넣음 | 뺌 | 뺌(조건 이름이 다름) |
| 연습 계단(`stair.practice_ao`, 요약 `practice.noise_srt_db`) | 뺌 | 뺌 | noise_endless만 |
| 간격 복습(`/listen/review`, 2·3단계 안의 복습 문항) | 넣음 | 뺌 | 넣음 |
| 혼동 집계(요약 `confusions`, 2단계 표적 출제, contrast 기본 대조) | 넣음 | 뺌 | 넣음 |
| 소리 구별 정답률(요약 `ax_kinds`, 분석 `listen.ax_accuracy`) | 넣음 | 뺌 | 넣음 |
| 연습량(요약 `days`, `/today`의 `done_today`, 과제 `listen_15`, 분석 `listen.week_minutes`) | 넣음 | 넣음 | 넣음 |
| 내보내기 `trials_by_stage` | 넣음 | 뺌 | 뺌(`practice_by_mode`에 모드·단계·꼴별로 따로) |

검사(`test:*`)와 점검(`ling:*`)은 지금처럼 단계 훈련과 같은 쪽(session이 'practice'로 시작하지 않음)으로 센다.
`test_listen_practice.py`가 표의 각 칸을 흐름 테스트로 고정한다.

## 3. 요약(GET /api/listen/summary)에 더한 칸

`practice: {by_mode: {모드: 시행 수}, noise_srt_db, n_noise}`. `by_mode`의 키는 `contrast, dictation, noise_endless, scenario, conditions, review`
가운데 시행이 있는 것이다. 기존 칸은 그대로이고, 2.1절 표대로 `confusions`·`ax_kinds`·`days`에 연습 답이 들어간다.

## 4. 듣기 복습(GET /api/listen/review)

- 계산: `listen_curriculum.due_reviews`(틀리면 다음 날, 그 뒤 한 번 맞히면 사흘 뒤 한 번 더, 두 번 맞히면 빠짐).
- 낱말: 2단계 낱말 고르기 시행 전부(단계 훈련, contrast·review 연습 답, 'practice' 제외). 낱말 고르기 풀에 있는 말만, 오래 기다린 순 10개.
  보기는 수준 2(4지, `word_item`)이고, 이웃이 모자란 말은 수준 1(2지)로 낸다(`level`로 알 수 있다).
- 문장: 3단계 문장 시행 전부(단계 훈련, dictation·conditions·review 답). 오래 기다린 순 5개. 소음 속 문장(4단계·noise_endless)은 계단이
  절반쯤 틀리게 맞추므로 넣지 않는다. 대화(5단계·scenario)와 같다·다르다도 넣지 않는다.
- 2단계와 3단계 화면이 앞에 두는 복습 문항도 같은 기록을 본다. 복습 탭에서 맞힌 낱말은 같은 날 2단계에 복습으로 다시 나오지 않는다(바뀐 점, 7절).
- `GET /api/review/due`: `listen_count = listen_words + listen_sentences`, `total_with_listen = total + listen_count`. `total`과 과제
  '오늘의 복습 정리'(독화·말하기 예정 복습)는 듣기 복습을 세지 않는다. 듣기 복습까지 남은 수를 보이려면 `total_with_listen`을 쓴다.

## 5. 과제와 오늘의 듣기

- `GET /api/listen/today`: 코디네이터가 만든 `today_plan` 그대로(Ling 점검 → 약한 소리 짝 → 문장 → 대화, 15분 안팎)이고 `review_due`(오늘 복습할
  듣기 문항 수)만 더했다.
- 과제 `listen_15`: `{key: "listen_15", label: "소리 듣기 15분", total: 15, xp: 15, period: "day"}`. `cur`는 오늘(KST) 듣기 연습 분의 내림이고 15 이상이면 달성.
  분은 요약 `days[].minutes`와 같은 추정(`practice_minutes`, 시행 간격 합, 3분 넘는 쉼은 뺌, 모든 시행)이다.
- 듣기 트랙을 시작한 사용자(듣기 시행이나 듣기 단계 행이 하나라도 있음)에게만 `daily`에 넣는다. 위치는 하루 과제 맨 뒤다. 보상은 다른 과제처럼
  `POST /api/tasks/claim`이 하루 한 번 준다.

## 6. 분석 탭(GET /api/analysis/overview)

기존 칸은 그대로이고 `listen`을 더했다. 듣기 트랙을 시작하지 않았으면 `null`이다. 날짜는 듣기 요약처럼 KST다.

| 칸 | 뜻 |
|---|---|
| `test_srt_db`, `test_noise`, `test_at` | 가장 최근에 마친 소음 속 문장 검사의 역치·잡음·시작 시각(잡담 잡음 검사가 있으면 그것, 없으면 아무 잡음) |
| `n_tests` | 마친 검사 수 |
| `training_srt_db` | 4단계 훈련 계단의 소리만 역치(요약 `training.srt_ao_db`) |
| `week_minutes` | 오늘로 끝나는 7일의 듣기 연습 분(요약 `days` 합) |
| `week_days` | 그 7일 가운데 듣기 시행이 있는 날 수 |
| `ax_accuracy`, `ax_n` | 소리 구별(같다·다르다) 정답률과 시행 수(1단계와 연습 탭) |

듣기 시행은 분석의 `events`에 넣지 않았다. 학습 시간·정확도·연속 학습·배지 같은 기존 칸의 뜻이 바뀌지 않게 하려는 것이다.

## 7. 소리 교실(GET /api/listen/contrasts)

- 종류는 `AX_KIND_LABEL` 순서(길이, 억양, 모음, 자음 방식, 소리 세기, 소리 자리, 마찰음, 받침)다.
- `desc`: 무엇이 다른지와 보청기·인공와우로 왜 어려운지(`KIND_DESC`) 뒤에 입모양 문장을 붙인다. 입모양은 짝마다 `engine.VISEME_MAP`의 무리로 판정하고
  (`lip_same`, 길이 짝은 다름, 억양 짝은 같음, 받침 없음처럼 정할 수 없으면 null), 종류의 `lip`은 모두 같으면 `same`, 모두 다르면 `differs`, 섞이면 `mixed`다.
  지금 값: 억양·자음 방식·소리 세기는 same, 길이·소리 자리·마찰음은 differs, 모음·받침은 mixed.
- `pairs`: 그 종류의 소리 구별 짝. `words`: 그 종류의 대조 하나로만 갈리는 낱말 짝, 소리 거리가 가까운 순(거리 1부터, 모자라면 2), 종류마다 6개까지,
  한 낱말은 한 번만. 마찰음은 거리 1인 짝이 없어 거리 2다. 길이·억양은 낱말 짝이 없다.
- 낱말 대조의 종류 나눔(`contrast_kind`): 받침 → 받침, 모음 → 모음, 첫소리는 세기만 다르면 소리 세기, 마찰음·파찰음(ㅅ·ㅆ·ㅈ·ㅉ·ㅊ·ㅎ)이 끼고 자리가 다르면
  마찰음, 자리가 같고 방식이 다르면 자음 방식, 자리만 다르면 소리 자리. 소리 구별 짝의 종류와 같게 나뉜다(테스트로 확인).
- 훈련 목소리 모두(목소리가 셋 이상이면 마지막 검사용 목소리를 뺀 것)에 미리 합성된 글만 넣는다. 지금은 소리 구별 음절 70개·낱말 풀 322개가 모두 합성돼 있다.
- `practice_key`(`kind:…`)와 `words[].contrast`(`onset:ㅂ:ㅍ` 꼴)는 `GET /api/listen/practice/contrast?contrast=`에 그대로 쓴다.

## 8. 바뀐 점(기존 동작)

1. **2단계 화면의 혼동 표적 출제와 간격 복습, 3단계 화면의 최근 문장과 간격 복습이 연습 답('practice:*')까지 본다.** 복습 탭이나 연습 탭에서 맞힌 문항이
   단계 화면에서 또 복습으로 나오지 않게 하려는 것이다. 수준·숙달·방금 틀린 낱말(weak)은 지금처럼 단계 훈련 시행만 센다.
2. `_listen_attempts`의 기본값이 'practice:*'를 뺀다(단계 계산에 연습 답이 섞이지 않게). 'practice:*'가 없던 기존 기록에는 영향이 없다.
3. 내보내기(`/api/pilot/export`)의 `listen`에 `practice_by_mode`를 더했다. 판 번호는 6 그대로이고 `trials_by_stage`에는 연습 답이 없다.
4. 대화 문항이 30개에서 34개가 됐다(9절). 5단계 대화 듣기에도 함께 나온다. 정답 자리는 0번 8, 1번 8, 2번 9, 3번 9다(검토 규칙 6~9 안).
5. 상황별 대화의 `place`는 장소 이름이 아니라 장면 묶음 key다(1.2절). 요청 문구의 'CONVO_ITEMS place 집계'를 묶음 단위로 바꾼 것이다.

## 9. 더한 콘텐츠와 새로 합성할 글

대화 문항 넷(c31~c34)을 더해 장면 묶음마다 4문항 이상이 되게 했다. 콘텐츠 검토(`docs/review/listen-content-review-2026-10.md` 5절)의 (가)~(바)를 따랐다.
들어야만 풀리고(시각·요일·층은 상식으로 정해지지 않음), 들은 말 안에 소리가 비슷한 오답이 있고, 정답이 혼자 가장 긴 보기가 아니다.
대사·바꾼 말은 P3 파일럿 문장·검사 문장·훈련 문장·다른 대화와 `similarity_reasons(both_ways=True)`에 걸리지 않고, 일반화 검사 낱말이 들어 있지 않다
(`test_new_convo_items_content_rules`).

| id | 장소(묶음) | 대사 | 질문 | 보기(정답) |
|---|---|---|---|---|
| c31 | 친구(friends) | 영화는 일곱 시에 시작하니까 여섯 시 오십 분까지 극장 앞으로 와. | 몇 시까지 와야 해요? | 여섯 시, 일곱 시, **여섯 시 오십 분**, 일곱 시 오십 분 |
| c32 | 회사(work) | 출장은 수요일에 가고, 금요일 아침에 돌아와요. | 언제 돌아와요? | 수요일 아침, 목요일 저녁, 금요일 저녁, **금요일 아침** |
| c33 | 도서관 안내(notice) | 오 층 열람실은 공사 중이라 이 층 열람실만 쓸 수 있습니다. | 어느 열람실을 쓸 수 있어요? | 오 층 열람실, 일 층 열람실, **이 층 열람실**, 사 층 열람실 |
| c34 | 아파트(home) | 내일 승강기 검사가 있어서 열 시부터 열두 시까지 못 타요. | 승강기는 언제부터 못 타요? | 아홉 시부터, 열한 시부터, 열두 시부터, **열 시부터** |

처음 쓴 판(여섯 시 반, 삼 층, 한 시간 동안)은 c01('두 시 반'), c09('삼 층 큰 방'), 훈련 문장('한 시간 늦어졌어요')과 이어진 어절이 같아 유사도 점검에 걸려 고쳤다.
c34는 정답이 혼자 가장 짧은 보기(한 글자 차이)다. 검토 문서 5절의 c06·c08·c30처럼 자연스러운 말이라 두었다.

**새로 합성할 글(8개, 듣기 목소리 전부).** `listen_curriculum.inventory_texts()`에 이미 들어 있어 `scripts/sound_inventory.py`(source 'listen')가 잡는다.
합성 전에는 화면이 이 문항을 '소리 준비 전'으로 건너뛴다.

1. 영화는 일곱 시에 시작하니까 여섯 시 오십 분까지 극장 앞으로 와.
2. 여섯 시 오십 분까지 극장 앞에 와. 영화는 일곱 시야.
3. 출장은 수요일에 가고, 금요일 아침에 돌아와요.
4. 수요일에 출장을 가요. 금요일 아침에 와요.
5. 오 층 열람실은 공사 중이라 이 층 열람실만 쓸 수 있습니다.
6. 오 층 열람실은 고치는 중이에요. 이 층 열람실로 가세요.
7. 내일 승강기 검사가 있어서 열 시부터 열두 시까지 못 타요.
8. 내일 열 시부터 열두 시까지는 승강기를 쓸 수 없어요.

## 10. 남은 것

- 듣기 시행을 분석 탭의 학습 시간·연속 학습(`events`)에 넣을지는 정하지 않았다. 넣으면 기존 칸의 값이 바뀌므로 화면과 함께 정한다.
- 과제 '오늘의 복습 정리'가 듣기 복습까지 끝내야 달성인지도 정하지 않았다(지금은 듣기 복습을 세지 않음).
- 울리는 방의 잔향 시간을 시행 기록에 남기려면 열을 하나 더해야 한다(지금은 `condition = 'room'`만).
