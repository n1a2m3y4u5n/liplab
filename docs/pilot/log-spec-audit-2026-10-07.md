# 파일럿 로그 사양 다시 점검(P0, 2026-10-07)

> `log-spec-audit.md`(10/6, c924554 기준)의 항목마다 지금 코드에서 실제로 기록하고 내보내는지 다시 판정했다. 기준 코드는
> `integrate/2026-09-23`(7205a4d)에 이 작업(브랜치 `pilot-readiness-2026-10`)을 더한 것이고, 줄 번호는 이 작업 뒤의 파일 기준이다.
> 판정: **있음**(기록하고 내보낸다), **부분**(기록만 하거나 일부만), **없음**(기록하지 않는다). '필요'는 분석 계획
> (`design-simulation.md`, `claim-ledger.md` 3·5절, `listen-vocoder-pilot-prereg.md`, `battery.md`)이 그 값을 쓰는지다.
> 필요한 것 가운데 빠진 것은 이번에 넣었고(4절), 필요 없는 것은 까닭을 적고 넣지 않았다.

## 1. 요약

1. 10/6 감사의 '없음' 대부분은 그날 저녁의 P3 검사 묶음과 10/7 소리 듣기 작업으로 이미 채워졌다. 남은 빈 곳 가운데 분석 계획이
   쓰는 것은 넷이었다. **학습량(용량·준수)**, **SNR 계단 수렴 여부**, **유지 검사 예정일**, **학습 초기화 때 소리 듣기 검사 기록 삭제**.
   네 가지를 넣고 내보내기를 판 7로 올렸다.
2. 분석 계획이 쓰지 않는 빈 곳(학습 화면의 `rt_ms`, 문장 연습 보기 원문, 렌더링 꼬리 지표, MRT, 기호 노출 수, 공변량 검사 등)은 까닭을 적고
   넣지 않았다(3절 표의 '조치').
3. 리허설을 자동화했다(`scripts/pilot_rehearsal.py`). 가상 참여자 6명이 등록부터 유지 검사 예약까지 API로 돌고, 내보내기의 분석 필드
   128개와 규칙 검사 25개가 모두 통과했다(5절). 주분석 스크립트(`scripts/pilot_analyze.py`)를 새로 만들어 같은 내보내기로 끝까지 돌렸다.
4. 사람이 해야 할 일은 그대로 남는다. 동의서 5-3·`pilot-data-spec.md` 3절 문구, 촬영(주결과는 실제 얼굴 조건), 학습 효과 지표(아바타
   A-A-B)의 문항 구성, 집단 배정표, 브라우저에서의 팀 리허설(화면이 실제로 값을 보내는지는 API 리허설로 확인할 수 없다)(6절).

## 2. 지금 내보내기(판 7) 한눈에

| 묶음 | 내보내기 키 | 기록 | 내보내기 |
|---|---|---|---|
| P3 회차 × 층 | `battery[]` | `database.py` 564~597(`P3TestSession`) | `main.py` 3752~3782 |
| P3 닫힌 응답 | `battery[].closed[]` | `database.py` 598~625, `main.py` 4212~4233 | `main.py` 3762~3766 |
| P3 열린 응답 | `battery[].open[]` | `database.py` 626~658, `main.py` 4234~4262 | `main.py` 3767~3772 |
| 순서·순번 | `join_seq`·`planned_order`·`b_completed_seq` | `database.py` 168~169, `main.py` 3892~3918(배정) | `main.py` 3785~3792, 3808 |
| 표준검사(아바타 A·B) | `tests[]` | `database.py` 339~342 | `main.py` 3809~3821 |
| 학습 시행 | `trial_log[]`, `progress_log[]` | `database.py` 82~94, 378~393 | `main.py` 3654~3674 |
| 학습량(판 7) | `reading_days[]` | 시행 시각 | `main.py` 3644~3652 |
| 측정 표 | `review_logs`·`mastery_probes`·`retention_results`·`lesson_efforts`·`sentence_practice_logs` | `database.py` 450~561 | `main.py` 3676~3708 |
| 소리 듣기 | `listen.tests`·`word_tests`·`trials_by_stage`·`days`(판 7)·`log` | `database.py` 259~286 | `main.py` 3710~3750 |
| 유지 검사 예정(판 7) | `battery_schedule` | B·R 완료 시각 | `main.py` 4003~4011, 3829 |

## 3. 항목별 판정

### 3.1 10/6 감사 3절의 열 가지 항목

| 항목 | 지금 기록(파일:줄) | 내보내기(파일:줄) | 판정 | 필요 | 조치 |
|---|---|---|---|---|---|
| 재생 속도 | 학습 `trial_attempts.speed`(`database.py` 378), `progress.speed`(82). P3 검사는 목록 `playback.speed`(1.0 고정)를 응답마다 `speed`로 남김(`main.py` 4211~4214, `database.py` 622·654) | `trial_log[].speed`, `progress_log[].speed`, `battery[].closed/open[].speed` | 있음 | P3 검사: 예(재생 조건 확인) | 없음 |
| 재생 횟수 | P3 검사 `plays`(`database.py` 621·653, 화면 `PilotBattery.jsx` 247), 소리 듣기 `plays`(276) | `battery[].closed/open[].plays`, `listen.log[].plays` | 있음 | 예(재생 규칙 1~2번 확인) | 없음 |
| 표준검사 `item_log`의 속도·재생 | 없음(`assessment.score_placement`의 `item_log`는 id·word·chosen·correct·difficulty·talker) | `tests[].items[]`(id·correct·chosen·talker) | 없음 | 아니오 | 넣지 않음. 표준검사(아바타 A·B)는 P3 주·보조 결과가 아니고, 화면이 속도 조절을 내지 않는다. 학습 효과 지표(claim-ledger 3.4)를 아바타 A-A-B로 만들 때 P3 묶음의 층으로 넣으면 `speed`·`plays`가 함께 남는다(6절 3) |
| 답 방식 | `progress.answer_mode`(83), P3는 층으로 정해짐(`response`) | `progress_log[].answer_mode` | 있음 | 예(문장 연습 추이) | 없음 |
| 보인 보기 | 학습 `trial_attempts.options`(381), 문장 4지 `progress.options`(88, `main.py` 979), P3 낱말 `options`(613) | `trial_log[].options`, `battery[].closed[].options`. 문장 연습은 `progress_log[].n_options`(개수)만 | 부분 | 아니오(문장 연습 보기) | 넣지 않음. 분석 계획 가운데 문장 연습 보기를 쓰는 것이 없다(C12·C13 문항 분석은 선다형 `trial_log`로 한다). 보기 문장은 콘텐츠라 개인정보는 아니므로 필요해지면 `progress_log`에 `options`를 더하면 된다 |
| 반응 시간 | P3 `rt_ms`·`rt_from_onset_ms`(619~620·651~652, 화면 `lib/pilotBattery.js` `reactionTimes`), 학습 `rt_from_onset_ms`(387, 85), 소리 듣기 `rt_ms`(278) | `battery[]` 응답, `trial_log[]`·`progress_log[]`의 `rt_from_onset_ms`, `listen.log[].rt_ms` | 부분 | P3 검사: 예. 학습 화면 `rt_ms`: 아니오 | 넣지 않음(학습 `rt_ms`). 학습 화면은 재생 끝 시각을 받지 않는다. P3 분석·두 사전 등록 모두 학습 시행 반응 시간을 쓰지 않는다 |
| 화자 | 학습 `talker`(388, 86), P3 응답·회차 `talker`(581·610·639) | `trial_log[].talker`, `progress_log[].talker`, `battery[]` | 있음 | 예(화자 배정 확인) | 없음 |
| 힌트 | `trial_attempts.hint_used`(389), `progress.hint_level`(87). 힌트 3 뒤 제출(practice_only)은 `sentence_practice_logs`(`main.py` 946~952, reason `hint3`) | `trial_log[].hint_used`, `progress_log[].hint_level`, `sentence_practice_logs[]` | 있음 | 보조 | 없음(10/6의 '남음'은 `sentence_practice_logs`로 채워졌다) |
| 탐침 | 짝 탐색 `probe_kind='contrast'`(`main.py` 2499), 지연 탐침 `mastery_probes`(`database.py` 493~499, `mastered_on`·`delay_days`) | `trial_log[].probe_kind`, `mastery_probes[]` | 부분 | C16 지연 탐침: 예(claim-ledger 3.4 보조). 실제 얼굴 탐침: 아니오 | 넣지 않음(실제 얼굴 탐침 C8). 기능이 없다 |
| 노력 문항 | `lesson_efforts.response`('answered'·'skipped'·'left', `database.py` 536), `rating` | `lesson_efforts[]`(`main.py` 3701~3703) | 있음 | 보조(응답률) | 없음. 건너뜀은 `response='skipped'`로 남는다(리허설 확인) |
| 폼과 순서 | `p3_test_sessions.session_label`·`form`·`planned_order`·`join_seq`(573~579), `learning_profiles.pilot_seq`·`pilot_order`(168~169) | `battery[]`, `join_seq`·`planned_order`·`b_completed_seq` | 있음 | 예(주분석 순서 고정효과, 순차 규칙) | 없음 |
| 기기·렌더(V20) | 회차·레슨 `render_log`(`database.py` 539·592, 정리 `pilot_battery.py` 447~473). 키: frames, mean_late_ms, max_late_ms, over20_rate, over50_rate, **screen_hz_est**(10/6 '남음'에서 채워짐, `frameClock.js` 37~52, `pilotBattery.js` 85), 화면·창 크기, dpr, 기기·OS·브라우저 계열, render_mode, webgl, 영상 누락(`video_drop_rate`, 93) | `battery[].render_log`, `lesson_efforts[].render_log` | 부분 | V20 판정선(평균 늦음 ≤ 10 ms, 누락 ≤ 5%): 예 | `interval_err_p95_ms`·`frames_expected`·`gpu_tier`는 넣지 않음. 판정선은 평균과 누락률이라 지금 열(`mean_late_ms`, `video_drop_rate`)로 충분하고, 꼬리는 `max_late_ms`·`over20_rate`·`over50_rate`가 요약한다. GPU 등급은 지문 위험이 있다. `stimulus_ms_actual`은 첫 재생의 `rt_from_onset_ms − rt_ms`로 문항마다 복원된다. `stimulus_ms_designed`는 아바타는 목록 판과 엔진(`text_to_visemes`)으로, 영상은 `check_pilot_media.py`의 길이로 다시 계산한다 |

### 3.2 P3 주분석과 보조 결과(10/6 감사 4.1·4.2)

| 분석 | 지금 기록·내보내기 | 판정 | 필요 | 조치 |
|---|---|---|---|---|
| 주지표 (B − A2) − (A2 − A1) | 회차 × 층 행, 미완료 층도 행이 남음(ITT) | 있음 | 예 | `scripts/pilot_analyze.py`가 계산(순서 고정효과, 3갈래 판정) |
| 주결과 개방형 문장 음소 정답률 | `answer_text`·`auto_phoneme_acc`·`n_matched_phonemes`·`n_target_phonemes`·`scorer_version`(`database.py` 642~650, 채점 `main.py` 4245) | 있음 | 예 | 없음. 지금 목록은 문장 층이 아바타 조건이라, 실제 얼굴 영상이 들어오기 전 자료는 주결과로 쓰지 않는다(분석 스크립트가 `--allow-avatar` 없이는 뺀다) |
| 보조: 실제 얼굴 4지선다 | `p3_closed_responses`(영상 있는 문항만) | 있음 | 예 | 없음 |
| 무의미 낱말 자음 | `target_consonants`·`chosen_consonants`·`consonant_hits`(616~618) | 있음 | 예 | 없음 |
| 폼 동등화·RCI | 문항 단위 응답, 폼, A1·A2 | 있음 | 예 | 분석 스크립트가 RCI 비율 계산 |
| ITT와 프로토콜 준수(용량) | 10/6: `active_days`와 단계별 시행 수만, 학습 시간 없음 | 부분 → **있음(판 7)** | 예(claim-ledger 3.3 '함께 보고') | `reading_days[]`(날짜, 시행 수, 분)를 더했다(`main.py` 3644~3652). 분은 소리 듣기 요약과 같은 규칙(`listen_curriculum.practice_minutes`: 시행 간격 합, 3분 넘는 쉼은 끊음)이다. 새 표 `lesson_sessions` 대신 시행 시각에서 추정한다(화면 변경 없음). 용량 기준 값은 등록 전에 정한다 |
| 학습 초기화 영향 | P3 세 표·표준검사 A·B·유지 검사는 남음(`main.py` 385~392). 학습 시행은 지워짐 | 부분 | 예 | 학습 시행 삭제는 결정 대기(10/6 그대로). 소리 듣기 검사는 이번에 남기게 했다(3.4) |
| 순차 베이즈 멈춤 | `b_completed_seq`(`main.py` 3785~3792) | 있음 | 예 | 분석 스크립트가 5명마다 BF+0을 계산(`design-simulation.md` 5절 규칙) |
| 소음 속 시청각 이득(VE) | 응답 `modality`(A·AV)·`snr_db`·`noise_type`, 회차 `snr_calibrated_db`·`headphone_check`·`volume_fixed` | 있음 | 예 | 분석 스크립트가 회차별 VE 계산 |
| SNR 실패 제외 규칙 | 10/6: 계단 추정 방식(`estimate_kind`)은 마침 응답에만 있고 저장하지 않음 | 없음 → **있음(판 7)** | 예(claim-ledger 5절 '탈락·SNR 실패 규칙') | `p3_test_sessions.snr_estimate_kind`·`snr_reversals`(`database.py` 588~589, `_ADD_COLUMNS` 763~764, 저장 `main.py` 4302, 내보내기 3777~3778) |
| 4주 유지 검사 | R 회차 행(B와 같은 폼) | 있음 | 예(보조) | R 예정일을 검사 상태와 내보내기에 더했다(`battery_schedule`, B 마친 날 + `LIPLAB_RETENTION_DAYS`, 막지 않고 알림, 화면 `PilotBattery.jsx` 91~95). 분석은 R과 B 완료 날짜 차이를 쓴다 |
| 숙달 지연 탐침(C16) | `mastery_probes`(`mastered_on`, `delay_days`) | 있음 | 보조 | 없음 |
| MRT 학습 보조 요소(나10) | 없음 | 없음 | 아니오 | 넣지 않음. 두 사전 등록과 claim-ledger에 MRT 분석이 없다 |
| 시각 기호 노출 수 | 집단 단위만(`LIPLAB_PILOT_NOCUE_COHORTS`) | 부분 | 아니오 | 넣지 않음. 시행 단위 노출 수는 MRT를 할 때만 필요하다 |
| 문장 자음 피드백 두 번째 답(C9) | 둘째 답 `sentence_practice_logs`(reason `consonant_retry`, score, 낱말 수), 첫 답은 `progress_log` | 부분(두 행을 잇는 키 없음) | 아니오 | 넣지 않음. C9 효과는 이번 두 파일럿의 주·보조 분석이 아니다. 필요해지면 내보내기에 문장 순번 연결을 더한다 |
| 개인차 공변량(나22) | 없음 | 없음 | 아니오 | 넣지 않음. 동의서와 명세를 먼저 고쳐야 하고 분석 계획에 없다 |
| SUS·설문 | 앱 밖(종이, 가명) | 해당 없음 | 보조 | 없음 |

### 3.3 동등성과 문항 분석(10/6 감사 4.3)

| 분석 | 지금 | 판정 | 필요 | 조치 |
|---|---|---|---|---|
| 아바타 대 실제 동등성(나8, P11) | 응답에 `modality`는 있으나 동등성 층·회차(`EQ`)는 없음 | 없음 | P11은 별도 연구(claim-ledger 5절) | 넣지 않음. 실제 얼굴 영상이 필요하고, P3 묶음과 다른 단독 회차다. 촬영 뒤에 층으로 더한다 |
| 학습 효과 지표(claim-ledger 3.4, 아바타 A-A-B) | 아바타 표준검사는 A·B 두 폼뿐이고 P3 묶음에 아바타 낱말 층이 없음 | 없음 | 예(주장 원장 3.4) | 넣지 않음. 문항 구성이 결정 대기다(claim-ledger 7절 4, battery.md 7절 2). 정하면 P3 묶음에 층을 더하고 분석 스크립트의 `index_rows`를 그 층에 돌린다 |
| IRT·AFM(C12·C13·C18) | `trial_log[]`에 목표·보기·고른 답·속도·화자·순번 | 있음 | 보조 | 없음 |
| 문장 연습 추이 | `progress_log[]` | 있음 | 보조 | 없음 |

### 3.4 소리 듣기 청인 모의 파일럿(10/6 감사에 없던 항목)

| 항목 | 지금 기록(파일:줄) | 내보내기 | 판정 | 필요 | 조치 |
|---|---|---|---|---|---|
| 역치 검사(babble·talker2) | `listen_attempts` mode `test`, `noise`·`sim_mode`·`snr_db`·`correct`(`main.py` 6347~6349), 역치는 회차 기록에서 다시 계산(`_listen_test_state` 5867) | `listen.tests[]`(session, form, noise, sim, n, n_practice, srt_db, started_on) | 있음 | 예(주결과·일반화 1) | 없음 |
| 낱말 일반화 검사 | mode `wordtest`, `rt_ms`·`plays`·`sim_mode`(6413) | `listen.word_tests[]`(accuracy, complete, sim) | 있음 | 예(일반화 2) | 없음 |
| 인공와우 모의 표시 | 훈련·검사 행 `sim_mode='ci'`(`database.py` 284), 화면 `api.js` `withSim` | `listen.tests[].sim`, `log[].sim` | 있음 | 예 | 없음 |
| 집단 | 참여 코드의 집단(`cohort`) | `cohort` | 있음 | 예 | 집단 배정표(4명 묶음, 폼 순서 층화)는 앱 밖(6절) |
| 층화 변수(폼 순서) | 계정 번호 홀짝(`listen_curriculum.test_form_for`) | 첫 `listen.tests[].form` | 있음 | 예 | 분석 스크립트가 층별 인원을 보고 |
| 회기 수·시간(5회기 × 20분) | 시행 시각뿐, 내보내기에는 날짜만 있어 분을 셀 수 없음 | 없음 → **있음(판 7)** | 예(사전 등록 5절 '남음') | `listen.days[]`(날짜, 훈련 시행 수, 분, 인공와우 모의 시행 수, 검사 제외)를 더했다(`main.py` 3716~3725). 대조 집단의 독화 시간은 `reading_days[]` |
| 학습 초기화 | 10/6 이후 코드: 초기화가 `listen_attempts`를 모두 지워 사전·사후 검사가 사라짐 | 없음 → **있음** | 예 | 파일럿 참여자는 `test`·`wordtest` 행을 남기고 훈련 시행만 지운다(`main.py` 392~394, 남긴 수 `kept.listen_tests` 405~408) |
| 검사 답 반응 시간·출력 지연 | 역치 검사 답에는 없음(`ListenTestAnswer` 6285), 훈련 답에는 `rt_ms`·`output_latency_ms` | `listen.log[]` | 부분 | 아니오 | 넣지 않음. 주결과는 역치이고 반응 시간을 쓰지 않는다. 블루투스 지연은 훈련 행의 `output_latency_ms`로 공변량을 본다 |
| 검사 답 원문 | 검사·낱말 검사 답만(`main.py` 3749) | `listen.log[].answer` | 있음 | 사람 확인용 | 훈련 답 원문은 싣지 않는다(리허설 확인) |

## 4. 이번에 넣은 것(내보내기 판 7)

| 무엇 | 어디 | 왜 |
|---|---|---|
| `reading_days[]`: 날마다 독화 시행 수와 분 | `main.py` 3644~3652 | P3 프로토콜 준수(용량)와 소리 듣기 대조 집단의 활동량. 화면 변경 없이 시행 시각에서 추정 |
| `listen.days[]`: 날마다 소리 듣기 훈련 시행 수·분·모의 청취 시행 수(검사 제외) | `main.py` 3716~3725 | 소리 듣기 사전 등록의 5회기 × 20분 준수 |
| `battery[].snr_estimate_kind`·`snr_reversals` | `database.py` 588~589, `_ADD_COLUMNS` 763~764, `main.py` 4302·3777 | SNR 계단이 반전으로 수렴했는지(제외 규칙). 운영 중인 DB에는 켜질 때 열이 더해진다 |
| `battery_schedule`와 검사 상태의 R `schedule` | `main.py` 4003~4011·4038·3829, `PilotBattery.jsx` 91~95 | 유지 검사 예정일(B + 28일, 14~28일 사이로 바꿀 수 있음). 막지 않고 알린다 |
| 학습 초기화 때 소리 듣기 검사 보존 | `main.py` 365~420 | 청인 모의 파일럿 사전·사후 자료 보호(P3·표준검사와 같은 규칙) |
| 판 번호 7과 테스트 | `main.py` 3594, `test_pilot.py`, `test_pilot_battery.py` | 판 7 키와 SNR·학습량 값 확인 |

소리 듣기 쪽은 내보내기 필드(`listen.days`)와 학습 초기화만 고쳤고 `/api/listen/*`와 `listen_curriculum.py`, 듣기 화면은 건드리지 않았다.
판 7도 판 5·6처럼 검사 문항 답 원문을 싣는다. 동의서 5-3과 `pilot-data-spec.md` 3절을 고친 뒤에 쓴다.

## 5. 리허설 자동화와 결과

`scripts/pilot_rehearsal.py`(테스트 `backend/test_pilot_rehearsal.py`, 임시 DB를 쓰는 별도 프로세스).

- 가상 참여자: 기본 6명, 집단 둘(`rh_train` 소리 듣기 훈련 + 인공와우 모의, `rh_ctrl` 독화 훈련). P3 폼 순서는 순번대로 ABC·BCA·CAB가
  두 번씩, 소리 듣기 검사 폼 순서는 두 집단 모두 A→B와 B→A가 섞이게 등록 순서를 정했다.
- 흐름: 등록 → 참여 코드 → 사전(표준검사 A, P3 A1 다섯 층·A2 네 층, 소리 듣기 역치 검사 babble·talker2, 낱말 일반화 검사, 모두 sim=ci)
  → 훈련(소리 듣기 1·2단계 10시행과 문맥 추론 3개, 또는 문맥 추론 6개, 문장 연습 2개, 노력 문항 답함·건너뜀) → 사후(표준검사 B, P3 B,
  소리 듣기 검사 다시) → 유지 검사 예약(P3 R 예정일, 표준검사 유지 검사 상태), 한 명은 R을 바로 봄 → 마지막 한 명 학습 초기화
  → 운영자 내보내기(trials=true) → 검사 → `pilot_analyze.py`.
- 매체: 기본 `partial`. 임시 폴더에 낱말 영상은 한 문항 건너 하나, 소음 속 문장도 한 문항 건너 하나, SNR 문장 전부와 잡음 파일을
  내용 없는 시험 파일로 만든다. 목록 사본에만 말소리 크기를 넣는다. 영상이 없는 문항은 응답 없이 회차 행의 `missing.media`로 남는다.
  `--media none`이면 지금 저장소 그대로(낱말·SNR·소음 층은 준비된 문항이 없다).
- 검사: 필드마다 n과 null 비율(분석에 쓰는 128개, null이 하나라도 있으면 실패), 규칙 25개(분석 스크립트 확인 2개 포함, 폼 순서와 계획 일치, A1·A2·B 폼이 서로 다름,
  B 완료 순번, `rt_ms ≤ rt_from_onset_ms`, `plays` 1~2, 검사 속도 1.0, `missing` 합 = 문항 수 − 준비 수, 낱말 층 missing 기록, 응답 수 ≤
  준비 수, A·AV 두 블록, 이메일·사용자명·학습 입력 문장 없음, 훈련 답 원문 없음, 노력 건너뜀, 소리 듣기 사전·사후 폼 다름과 층화,
  유지 검사 예정일, R = B 폼, 초기화 뒤 보존, 분석 스크립트 계산).

10/7 실행 결과(6명, `--media partial`): API 2,769회(약 84초), 필드 128개와 검사 25개 모두 통과. 분석은 끝까지 돌았다(P3 D 추정과 구간,
순차 규칙 5명 확인 1회, RCI, VE, R − A2, 소리 듣기 집단 차이·일반화·층화·용량). 가상 응답이라 수치 자체는 뜻이 없다.

```bash
backend/.venv/bin/python scripts/pilot_rehearsal.py --out <폴더>     # 보고서 rehearsal_report.json, export.json, analysis/
backend/.venv/bin/python scripts/pilot_analyze.py <export.json> --out <폴더> \
    --p3-cohorts <집단들> --listen-train <집단> --listen-control <집단> [--allow-avatar]
```

주분석 스크립트가 계산하는 것: P3 주지표 D(순서 고정효과 평균, 95% 구간, 3갈래 판정, MME 5%p), B − A2 상한, 낱말·무의미 낱말 층 D(판정
없음), R − A2와 B 뒤 날수, RCI 비율, ITT(배정·회차별 완료·끝내지 못한 층·준비 전 문항·제외 사유), SNR 미수렴 목록, VE, 학습량,
순차 멈춤(B 완료 순번, 5명마다 한쪽 JZS BF+0 r = 0.707, 10명 전에는 멈추지 않음, 6과 1/6, 최대 40명, BF는 `pilot_design_sim.bf_table`과
같은 적분). 소리 듣기: 인공와우 모의 babble 역치 개선(사전 − 사후)의 집단 차이와 Welch 구간, 성공(≥ 2 dB이고 하한 > 0)·실패(상한 < 1 dB)·
판정 불가, talker2와 낱말 일반화(판정 없음), 첫 검사 폼 층화, 집단마다 12명에서의 들여다보기, 5회기 준수. 경계 값은 스크립트 위 상수다.

## 6. 남은 사람 몫

1. **동의서 5-3과 `pilot-data-spec.md` 3절**: 판 5부터 검사 문항 답 원문, 판 7은 날마다 학습량(분)이 더해졌다. 문구를 고친 뒤 내보낸다.
2. **촬영과 목록 동결**: 주결과는 실제 얼굴 조건이다. 지금 문장 층은 아바타라 리허설 자료는 `--allow-avatar`로만 계산된다.
3. **학습 효과 지표(claim-ledger 3.4)**: 아바타 A-A-B 문항 구성 결정(7절 4). 정해지면 P3 묶음에 층을 더한다.
4. **용량 기준 값**: P3 프로토콜 준수 기준(날 수·분)과 소리 듣기 5회기 × 20분의 판정 방식(날 수만 볼지, 분까지 볼지)을 등록 전에 정한다.
   지금 분석 스크립트는 소리 듣기만 '훈련한 날 5일 이상'으로 센다.
5. **집단 배정표**: 소리 듣기 파일럿의 4명 묶음 무작위 배정(폼 순서 층화)은 앱 밖에서 만든다. 앱은 참여 코드로 집단을 받는다.
6. **브라우저 팀 리허설**: API 리허설은 화면이 값을 실제로 보내는지 확인하지 못한다(예: `render_log`의 `screen_hz_est`, `video_drop_rate`,
   소리 듣기 화면의 `sim=ci`). 팀원 기기에서 `battery.md` 6절대로 한 번 돌리고, 받은 내보내기를 `pilot_rehearsal.check_export`와 같은
   목록으로 본다. 소리는 연구진 확인 아래에서만 낸다.
7. **학습 초기화 정책**: P3 기간 파일럿 참여자의 학습 시행 삭제(막을지, 표시만 할지)는 결정 대기다. 지금은 검사 기록만 남는다.
