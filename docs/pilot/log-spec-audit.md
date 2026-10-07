# 파일럿 로그 사양 점검(P0, 2026-10-06)

> **10/7에 다시 점검했다: `log-spec-audit-2026-10-07.md`**(항목별 새 판정, 판 7에서 넣은 것, 리허설 자동화). 이 문서는 10/6 기록으로 둔다.

> master-plan 2판 P0 "로그 사양 점검"의 결과다. 코드는 바꾸지 않았다. 빠진 필드는 이름과 형식을 제안만 하고, 넣을지와 동의서 수정은
> 사용자가 정한다. 기준 코드는 통합 브랜치 `integrate/2026-09-23`(c924554)이다.

## 0. 구현 현황(2026-10-06 저녁, P3 검사 묶음 작업)

아래 1~7절은 점검 당시(c924554) 그대로 두고, 그 뒤에 구현한 것을 여기에 적는다. 설계와 리허설 방법은 `battery.md`. 이름은 이 문서의
제안을 따랐고, 다르게 정한 것은 '바꾼 점'에 적었다. 표시: **구현**(기록하고 내보낸다), **일부**, **남음**.

| 제안(절) | 상태 | 구현한 곳 | 바꾼 점 |
|---|---|---|---|
| P3 검사 화면과 표 `p3_test_sessions`·`p3_closed_responses`·`p3_open_responses`(4.1) | 구현 | `backend/pilot_battery.py`, `/api/pilot/battery/*`, `/pilot/battery` | 회차 행은 제안대로 사람 × 회차 × 층. `device_id → render_log` 대신 회차 행에 `render_log` JSON을 바로 둔다. 미완료 층도 행이 남는다 |
| 폼 C, `session_label`(A1·A2·B·R), `planned_order`(3절 폼과 순서) | 구현 | 목록 파일 `forms`·`orders`, `learning_profiles.pilot_seq`·`pilot_order` | 유지 검사 이름은 `R`(제안 `R4`). 표준검사(placement_results)의 A·B 폼은 그대로 두었다 |
| 실제 얼굴 4지선다: 문항 id, 화자, 보기, 고른 답, 정오, `rt_ms`, `plays`(4.1) | 구현(영상 생기면) | `p3_closed_responses` | 영상이 없는 문항은 행이 없고 회차 행 `missing`에 센다 |
| 무의미 낱말 자음 식별: `target_consonants`, 고른 자음(4.1) | 구현 | `p3_closed_responses.target_consonants`·`chosen_consonants`·`consonant_hits` | 자극은 아바타. 문항은 C10 남겨 둔 목록(`battery.md` 2절) |
| 개방형 답 원문 `answer_text`, 자동 점수, `scorer_version`(4.1) | 구현 | `p3_open_responses.answer_text`·`app_score`·`auto_phoneme_acc`·`auto_word_acc`·`n_matched_phonemes`·`n_target_phonemes`·`scorer_version` | 앱 점수(`app_score`, 0~100)와 엄격 음소 정답률(0~1, `strict-v1`)을 함께 남긴다 |
| 소음 속 시청각: `modality`, `snr_db`, `noise_type`, `headphone_check`, `volume_fixed`, `snr_calibrated_db`(4.2) | 구현(구조만) | `p3_open_responses`, `p3_test_sessions` | SNR 계단 시행도 같은 표(`layer='snr'`, `criterion_met`). 문장·음성·잡음 파일은 촬영 뒤 |
| `rt_ms`·`rt_from_onset_ms`(3절 반응 시간) | 구현 | 검사: 둘 다. 학습 시행 `trial_attempts`·`progress`: `rt_from_onset_ms`만 | 학습 화면은 재생 끝 시각을 받지 않아 문항 표시(입모양 재생 시작)부터만 잰다 |
| `trial_attempts.talker`, `progress.talker`(3절 화자) | 구현 | 1·2단계, 문맥, 문맥 추론, 문장, 뜻 없는 말 짝 맞추기 | 레슨 가상 화자 id(`default`, `t1`~`t4`) |
| `trial_attempts.hint_used`, `progress.hint_level`(3절 힌트) | 구현 | 문맥 추론 '힌트 보기', 짝 맞추기 골격 블록, 문장 힌트 단계 0~3 | `progress.practice_only` 행 저장(힌트 3 뒤 제출)은 **남음**. 숙달 판정을 건드려 이번에는 하지 않았다 |
| `progress.options`(3절 보인 보기) | 구현 | 3단계 4지선다 보기(보인 순서) | |
| `probe_kind`(3절 탐침) | 일부 | `trial_attempts.probe_kind='contrast'`(짝 탐색) | 지연 탐침은 `mastery_probes`(C16), 실제 얼굴 탐침(C8)은 기능이 없다 |
| `render_log`(5절 V20) | 일부 | 검사 회차 행, 레슨 노력 문항 행(`lesson_efforts.render_log`) | 프레임 지연(`frameClock.renderTimingSummary`, 레슨 시작마다 다시 셈), 화면·창 크기, 화소 비율, 기기 분류, OS·브라우저 계열, WebGL 여부, 영상 누락(`getVideoPlaybackQuality`). `screen_hz_est`, `interval_err_p95_ms`, `stimulus_ms_*`는 **남음**. GPU 문자열·사용자 에이전트 원문은 받지 않는다 |
| 노력 문항 `effort_ratings`(3절) | 구현(10/6 낮) | `lesson_efforts`(C14) | 표 이름이 다르다 |
| 내보내기 판 5(6절) | 구현 | `PILOT_EXPORT_VERSION = 5` | `battery`, `join_seq`·`planned_order`·`b_completed_seq`, `trial_log` 확장(`target`·`options`·`chosen`(주관식은 비움)·`item_id`·`phase`·`talker`·`rt_from_onset_ms`·`hint_used`·`probe_kind`), `progress_log`(원문 제외), 10/6 표 `review_logs`·`mastery_probes`·`retention_results`·`lesson_efforts` |
| 학습 초기화 때 연구 자료(2절 5) | 일부 | 파일럿 참여자의 P3 세 표는 지우지 않는다(표준검사 A·B, 유지 검사와 같은 규칙) | 학습 시행 기록은 여전히 지워진다. P3 기간 초기화 금지나 `reset_epoch`는 결정 대기 |
| `mrt_decisions`, `covariate_tests`, `lesson_sessions`, `cues_shown`, C9 첫·둘째 답 열 | 남음 | | 기능이 아직 없다 |

동의서 5-3과 `docs/pilot-data-spec.md` 3절은 고치지 않았다. 판 5는 검사 문항의 답 원문을 실으므로 문구를 고친 뒤에 쓴다.

## 1. 읽은 것

| 대상 | 위치 |
|---|---|
| 저장 모델 | `backend/database.py`(표 정의, 경량 마이그레이션 `_ADD_COLUMNS`) |
| 가명 내보내기 | `backend/main.py` `pilot_export`(3060~3141행), `PILOT_EXPORT_VERSION = 4` |
| 검사 채점·저장 | `backend/main.py` `/api/assessment/placement`(3219행), 채점 저장(3291~3308행), `backend/assessment.py` `score_placement` |
| 시행 저장 | `backend/main.py` 1단계 1886·1935행, 2단계 2162행, 문맥 2508·2556행, 문장 `/api/progress` 795~830행 |
| 명세 | `docs/pilot-data-spec.md`(작업 지시의 `docs/pilot/pilot-data-spec.md`는 없고 이 경로에 있다), `docs/pilot/protocol.md` 5절 |
| 분석이 요구하는 것 | master-plan 2판 5절, idea-sweep 가1·가2·가4·나2·나8·나10·나15·나20·나22, C9·C12·C13·C14·C16·C18, V20 |

판정 기호: **있음**(기록하고 내보낸다), **부분**(기록은 하지만 내보내지 않거나 일부만), **없음**(기록하지 않는다).

## 2. 요약

1. **P3 주결과와 보조 결과를 측정하는 검사 자체가 앱에 없다.** 실제 얼굴 낱말 4지선다, 개방형 문장 타이핑, 무의미 낱말 자음 식별,
   소음 속 시청각 문장, 아바타 대 실제 동등성(나8) 검사는 화면도 저장 표도 없다. 지금 있는 표준검사는 아바타 4지선다 A·B 두 폼
   (`placement_results`)뿐이다. 그래서 아래 3절 표의 P3 줄 대부분은 '새 검사 모듈과 표가 필요'로 나온다.
2. **A-A-B에 필요한 폼 C, 회차 이름(A1·A2·B·유지), 배정한 순서가 없다.** 지금은 폼 A·B 두 개와 생성 시각만 있어 같은 폼을 두 번
   본 기록과 계획된 회차를 구별할 수 없다.
3. **학습 중 시행 기록은 쓸 만하지만 내보내기가 좁다.** `trial_attempts`에 재생 속도, 보인 보기, 고른 답, 짝 탐색 표시가 있으나
   `trial_log`(`?trials=true`)는 순번·날짜·단계·유형·정오·속도·탐색 여부만 준다. 문장 연습(`progress`)은 내보내기에 전혀 없다.
4. **반응 시간, 훈련 중 화자, 힌트 사용, 기호 노출, 노력 문항, 기기·렌더링 정보는 어디에도 기록하지 않는다.**
5. **학습 초기화가 시행 기록을 지운다.** 파일럿 중 초기화하면 용량(dose)·C12·C18 분석의 원자료가 사라진다. P3 기간에는 파일럿
   참여자의 초기화를 막거나, 지우지 말고 표시만 하는 방식이 필요하다(결정 사항).
6. 개방형 답 원문은 일부러 내보내지 않는다(명세 3절 '넣지 않는 것'). 그러나 주결과 재채점과 P20 사람 채점에는 **검사 문장에 대한
   답 원문**이 꼭 필요하다. 검사 모듈의 답만 내보내도록 범위를 좁히고 동의서 5-3을 먼저 고쳐야 한다.

## 3. 작업 지시의 열 가지 항목

| 항목 | 학습 시행(`trial_attempts`) | 문장 연습(`progress`) | 표준검사(`placement_results.item_log`) | 내보내기(판 4) | 판정 | 추가 제안 |
|---|---|---|---|---|---|---|
| 재생 속도 | `speed`(실제 재생 속도, 9/29~) | `speed`(9/29~) | 없음. 검사 화면이 속도 조절·다시 보기를 허용하는지도 기록 없음 | `trial_log[].speed`만 | 부분 | `item_log[].speed`, `item_log[].plays`(본 횟수). 검사에서 속도·재생을 고정하면 결과 행에 `playback_policy`(예: "1.0x, 2회")를 남긴다. 내보내기 `progress_log[].speed` |
| 답 방식 | `item_type`('word'·'word_typed' 등) | `answer_mode`('choice'·'typed', 9/29~) | 4지선다 고정이라 불필요 | `trial_log[].item_type`만, `progress`는 없음 | 부분 | 내보내기에 `progress_log[].answer_mode`. 새 검사 모듈은 `response_mode`('choice'·'typed') |
| 보인 보기 | `options`(JSON, 보인 순서, 주관식은 NULL) | 없음(문장 4지선다 보기를 저장하지 않음) | 없음. 단 동결 폼 파일(`forms_v1.json` 등)과 `id`·`form_version`으로 복원 가능 | 없음 | 부분 | `trial_log[].options`, `progress.options`(JSON) 열 추가, 검사 결과에는 복원 근거로 폼 파일 해시 `forms_sha` |
| 반응 시간 | 없음 | `time_spent_seconds`(정수 초, 0~3600으로 자름, 힌트 시간 포함, 내보내지 않음) | 없음 | 없음 | 없음 | 모든 응답 행에 `rt_ms`(첫 재생이 끝난 때부터 답 확정까지 ms, 정수). 첫 재생 시작부터 측정하는 `rt_from_onset_ms`를 함께 두면 자극 길이 차이를 분리할 수 있다 |
| 화자 id | 없음(레슨 화자 '화자 1~4'는 화면 `useLessonTalker`에서만 정함) | 없음 | 사후 검사 문항만 `talker`('default'·'h1'·'h2') | `tests[].items[].talker` | 부분 | `trial_attempts.talker`, `progress.talker`('t1'~'t4'·'default'). 실제 얼굴 검사는 `talker`('T1'~'T4') |
| 힌트 사용 | 없음(문맥 '힌트 보기' 기록 없음) | 없음. 힌트 3(문장 보기) 뒤 제출은 `practice_only`라 **행 자체를 저장하지 않는다**(`main.py` 802행) | 해당 없음 | 없음 | 없음 | `trial_attempts.hint_used`(bool), `progress.hint_level`(0~3), `progress.practice_only`(bool)로 저장은 하되 숙달·추이에서는 지금처럼 뺀다 |
| 탐침 표시 | `probe`(짝 탐색 JSON, 5.4-2) | 없음 | 없음 | `trial_log[].probe`(참·거짓만) | 부분 | 탐침 종류를 가르는 `probe_kind`('contrast'·'real_face'(C8)·'delayed_mastery'(C16)), 지연 탐침은 `days_since_mastery` |
| 노력 문항(C14) | 없음 | 없음 | 없음 | 없음 | 없음 | 새 표 `effort_ratings`(user_id, `lesson_kind`, `stage`, `rating` 1~9, `skipped` bool, created_at). 응답률 80% 판정에 `skipped`가 필요하다 |
| 폼과 순서 | 해당 없음 | 해당 없음 | `form`('placement'·'A'·'B'), `form_version`, created_at. 폼 C 없음, 회차 이름·배정 순서 없음 | `tests[].form`, `form_version`, `date` | 부분 | 폼 `C` 추가, `session_label`('A1'·'A2'·'B'·'R4'(4주 유지)), `planned_order`('ABC'·'BCA'·'CAB'), 검사 층 `layer`(4절). 내보내기에 `join_seq`(참여 순번, 시각 대신 순위) |
| 기기·렌더(V20) | 없음 | 없음 | 없음 | 없음 | 없음 | 검사 회차마다 `render_log`(5절). 누락 프레임 비율과 프레임 간격 오차를 판정선(≤ 5%, ≤ 10ms)과 같은 정의로 남긴다 |

## 4. 분석별 필요 필드

### 4.1 P3 주분석(master-plan 5절, 나2, 가1)

| 분석 | 필요한 것 | 지금 | 판정 | 추가할 것 |
|---|---|---|---|---|
| 주지표 (B − A2) − (A2 − A1) | 사람 × 회차 × 층 점수, 회차 이름, 폼, 배정 순서 | A·B 두 폼 기록만 | 없음 | 새 표 `p3_test_sessions`(id, user_id, `session_label`, `layer`, `form`, `form_version`, `planned_order`, `started_at`, `completed_at`, `completed` bool, `device_id` → `render_log`). 미완료 회차도 행을 남겨 ITT에서 결측을 셀 수 있게 한다(지금 검사는 끝까지 풀어야만 저장) |
| 주결과: 실제 얼굴 개방형 문장 음소 정답률 | 문장 id, 화자, 답 원문, 자동 점수(층별), 정렬 결과 | 없음 | 없음 | 새 표 `p3_open_responses`(session_id, `item_id`, `talker`, `answer_text`(원문, NFC), `rt_ms`, `plays`, `auto_phoneme_acc`, `auto_word_acc`, `scorer_version`). 원문은 내보내기 판 5에서 검사 문항에 한해 싣는다(동의서 5-3 수정 필요) |
| 보조: 실제 얼굴 4지선다 | 문항 id, 화자, 보기, 고른 답, 정오, `rt_ms` | 아바타 문항만 | 없음 | 새 표 `p3_closed_responses`(session_id, `item_id`, `talker`, `options`, `chosen`, `correct`, `rt_ms`, `plays`). 아바타 A·B 검사도 같은 표로 옮기면 분석이 한 경로가 된다 |
| 무의미 낱말 자음 식별(가1 첫째 층) | 문항 id, 목표 자음 위치별, 고른 자음 | 없음 | 없음 | `p3_closed_responses`에 `layer`='nonsense', `target_consonants`(예: ["ㅂ","ㄷ"]), `chosen` |
| 폼 동등화(원호), RCI | 문항 단위 응답, 폼, A1·A2 재검사 | A·B 문항 기록 | 부분 | 폼 C와 회차 이름. RCI는 A1·A2 상관으로 계산하므로 별도 필드는 필요 없다 |
| ITT와 프로토콜 준수(용량) | 학습 회기 수와 시간, 완료 기준 | `active_days`, 단계별 시행 수 | 부분 | 학습 시간은 없다. 새 표 `lesson_sessions`(user_id, `kind`, `stage`, `started_at`, `ended_at`, `n_trials`). 내보내기는 시각 대신 날짜와 분 단위 길이(`minutes`)만 준다 |
| 학습 초기화 영향 | 초기화 전 기록 | 초기화하면 지움, 날짜만 남김 | 부분 | P3 기간 파일럿 참여자 초기화 금지, 또는 행을 지우지 않고 `reset_epoch`(정수)로 표시 |
| 순차 베이즈 멈춤(나15) | 사후 검사를 마친 순서 | `tests[].date`(같은 날 순서 모름) | 부분 | 내보내기에 `b_completed_seq`(B 완료 순번). 멈춤 판정은 이 순서로 5명씩 묶는다 |

### 4.2 P3 보조 결과와 학습 보조 요소

| 분석 | 필요한 것 | 지금 | 판정 | 추가할 것 |
|---|---|---|---|---|
| 소음 속 시청각 이득 VE(가4) | 개인 SNR, 조건(A·AV), 잡음 종류, 문항, 점수, 헤드폰 확인 | 없음 | 없음 | `p3_open_responses`에 `modality`('A'·'AV'·'V'), `snr_db`, `noise_type`('babble'·'vocoder'), 회차 행에 `headphone_check` bool, `volume_fixed` bool, `snr_calibrated_db` |
| 4주 유지 검사 | 회차 이름 | 없음 | 없음 | `session_label`='R4' |
| 숙달 지연 탐침(C16) | 숙달 시각, 탐침 문항, 경과 일수 | `stage_progress.mastered_at`(있음), 탐침 문항 없음 | 부분 | `trial_attempts.probe_kind`='delayed_mastery', `days_since_mastery`. 내보내기에 단계별 `mastered_on`(날짜) |
| MRT 학습 보조 요소(나10) | 결정 지점마다 무작위 배정(요소, 켬·끔, 확률), 근접 결과 탐침 | 없음 | 없음 | 새 표 `mrt_decisions`(user_id, `decision_id`, `component`('focus_guide'·'cue'·'adaptive_slow'·'target_acc'), `assigned` bool, `p_assign`, `rng_seed`, created_at). 근접 결과 탐침은 `trial_attempts.mrt_decision_id`로 연결 |
| 시각 기호 노출 | 기호가 보였는지, 몇 개, 세기 | 없음(명세 3절, protocol 5.3) | 없음 | `trial_attempts.cues_shown`(정수 개수), `cue_opacity`(0~1 평균). MRT 요소로 쓰면 필수 |
| 문장 단계 자음 피드백과 두 번째 응답(C9) | 첫 응답, 두 번째 응답, 피드백 종류 | 기능 없음 | 없음 | 구현할 때 `progress.first_answer`·`second_answer`(원문은 내보내지 않음), `first_score`·`second_score`, `feedback_kind`('consonant'·'sentence'). 숙달에는 첫 응답만 쓴다는 규칙을 열로 확인할 수 있게 한다 |
| 개인차 공변량(나22) | 작업기억 폭, 처리 속도 점수, 어휘 판단 점수 | 없음 | 없음 | 새 표 `covariate_tests`(user_id, `test`('corsi'·'symbol'·'lexdec'), `score`, `n_items`, `completed_at`). 동의서와 명세 먼저 수정 |
| 긍정판 SUS(P15)·노력(C14) 설문 | 응답, 가명 연결 | 앱 밖 종이 설문(`survey.md`) | 앱 밖 | SUS는 앱 밖으로 두고 설문지에 가명만 적는 지금 방식 유지(`checklist.md` 부록 A). 노력 문항은 레슨마다라 앱 안 `effort_ratings` |

### 4.3 아바타 대 실제 동등성(나8)과 문항 분석(C12, C13, C18)

| 분석 | 필요한 것 | 지금 | 판정 | 추가할 것 |
|---|---|---|---|---|
| TOST ±10%p, 문항 × 모달리티 GLMM(나8) | 시청자 × 낱말 × 모달리티(아바타·실제·아바타+실제 움직임) 정오 | 없음 | 없음 | `p3_closed_responses`에 `modality`('avatar'·'real'·'avatar_arkit'), 회차 행에 `layer`='equivalence'. 학습 없는 단독 회차라 `session_label`='EQ' |
| 설명적 IRT(C12), 다기술 학습자 모형(C13), 학습 곡선 AFM(C18) | 시행 단위의 목표, 보기, 고른 답, 속도, 화자, 순서, 문항 특징 | `trial_attempts`에 목표·보기·고른 답·속도·탐색 있음, 화자 없음 | 부분 | 내보내기 `trial_log`에 `target`, `options`, `chosen`, `item_id`, `phase` 추가(검사 단어·보기는 개인정보가 아니다. 주관식 `chosen`은 원문이라 빼거나 자모 정렬 결과만), `talker`, `rt_ms` |
| 문장 연습 추이(eval-metrics 4절) | 답 방식, 속도, 난이도, 점수 | `progress`에 있음 | 부분 | 내보내기에 `progress_log`(순번, 날짜, `difficulty_level`, `answer_mode`, `speed`, `score`, `hint_level`). 입력 문장 원문은 넣지 않는다 |

## 5. 기기·렌더링 기록 제안(V20)

검사 회차와 학습 회기마다 한 행. 프레임마다의 원값은 남기지 않고 요약만 남긴다(웹캠 처리와 같은 원칙).

| 필드 | 형식 | 정의 |
|---|---|---|
| `render_mode` | 'avatar3d'·'avatar2d_fallback'·'video' | 실제로 쓰인 자극 경로(WebGL 실패 시 2D 대체 포함) |
| `device_class` | 'desktop'·'tablet'·'phone' | 화면 크기 기준 거친 분류 |
| `os_family`, `browser_family` | 문자열 | 사용자 에이전트에서 계열만(판 번호는 주 번호까지) |
| `screen_hz_est` | 정수 | requestAnimationFrame 간격 중앙값으로 추정한 화면 주사율 |
| `gpu_tier` | 'low'·'mid'·'high'·'unknown' | WebGL 렌더러 문자열을 그대로 저장하지 않고 등급으로만(지문 위험) |
| `frames_expected`, `frames_presented`, `frames_dropped` | 정수 | 아바타는 엔진 프레임 목록 기준, 영상은 `getVideoPlaybackQuality()`의 `totalVideoFrames`·`droppedVideoFrames` |
| `drop_rate` | 실수 | frames_dropped / frames_expected. 판정선 ≤ 0.05 |
| `interval_err_mean_ms`, `interval_err_p95_ms` | 실수 | 설계 프레임 시각과 실제 표시 시각(rAF 또는 `requestVideoFrameCallback`의 presentationTime) 차의 절댓값 평균·95백분위. 판정선 평균 ≤ 10ms |
| `stimulus_ms_designed`, `stimulus_ms_actual` | 정수 | 문항 자극 길이의 설계값과 실측값(속도 단계가 의도대로 나오는지) |

V20 점검은 파일럿 기기에서 이 기록을 먼저 모아 판정하고, P3 동안에는 같은 기록을 공변량으로 둔다(master-plan 8절 위험 대응).

## 6. 내보내기 판 5에 넣을 것(제안 순서)

1. `p3_test_sessions`, `p3_closed_responses`, `p3_open_responses`(검사 문항 답 원문 포함), `render_log` 요약.
2. `trial_log` 확장(`target`, `options`, `chosen`(선다형만), `item_id`, `phase`, `talker`, `rt_ms`, `hint_used`, `probe_kind`, `mrt_decision_id`).
3. `progress_log`(원문 제외), `effort_ratings`, `mrt_decisions`, `covariate_tests`, 단계별 `mastered_on`.
4. 순서 정보: `join_seq`, `b_completed_seq`, `planned_order`.

넣기 전에 할 일: `docs/pilot-data-spec.md` 3절, 동의서 5-3 "연구진이 받는 것", `scripts/pilot_analysis.py`의 판 확인. 참여가
시작된 뒤 항목을 바꾸면 다시 동의를 받는다(명세 3절).

## 7. 리허설에서 확인할 것(P0 판정 기준)

P0 판정은 "리허설에서 필요한 필드가 모두 내보내기 판에 나옴"이다. 팀원 리허설 1회 뒤 내보내기 JSON에서 다음을 확인한다.

- 3절 열 가지 항목이 모두 값으로 나오는지(빈 값이면 화면이 보내지 않는 것).
- 한 사람의 A1·A2·B가 서로 다른 폼이고 `planned_order`와 일치하는지.
- 개방형 답 원문이 검사 문항에서만 나오고 학습 입력 문장은 나오지 않는지.
- `render_log`의 `drop_rate`, `interval_err_mean_ms`가 기기마다 채워지는지.
- 리허설 개방형 답 200개를 P20(`typed-scoring-check.md`)에 넘길 수 있는지.
