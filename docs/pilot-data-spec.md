# 파일럿 데이터 명세(계획서 §4.7)

> 작성 2026-09-23, 통합 브랜치 `integrate/2026-09-23` 기준. 파일럿(당사자 사용성·효과 검증)에서 무엇을 모으고,
> 연구자에게 무엇을 넘기며, 언제 어떻게 지우는지를 코드에 맞춰 적는다. 열 이름은 `backend/database.py`의 실제 열이다.
> **보관 기간, 연구 윤리 절차, 개인정보 보호책임자는 아직 정하지 않았다(4절). 정하기 전에는 파일럿을 켜지 않는다.**

## 1. 앱이 저장하는 것(파일럿 참여와 무관한 일반 서비스 기록)

| 표 | 저장하는 열(자동 번호 id 제외) | 용도 |
|---|---|---|
| `users` | email, username, hashed_password, 가입 시각, is_active, token_version, 레벨·XP·연속 학습·마지막 학습일 | 로그인, 진도 표시 |
| `consent_records` | 약관·처리방침 판본, 만 14세 확인, 시각 | 동의 증빙(학습 초기화로 지우지 않는다) |
| `learning_profiles` | track, current_stage, placed, **pilot_code, cohort** | 커리큘럼 배치, 파일럿 집단 |
| `trial_attempts` | stage, item_type, target(문항), chosen(고른 답), correct, phase, confusions | 입모양·단어·문맥 문항 기록 |
| `progress` | 시나리오, sentence, user_answer(입력 문장), score, 걸린 시간, 난이도, 상황, 비심·음소 오류 | 문장 연습 기록 |
| `speak_attempts` | stage, mode, target, **transcript(음성 인식 결과)**, score, passed, 크기·높낮이·길이, 혼동, 소리·입모양·융합 점수, 불확실성, 음소 점수, 코칭 문구 | 말하기 연습 기록 |
| `placement_results`, `assessment_results` | 폼·판본, 정답 수·정확도, 능력 추정, 수준, 오류 입모양·음소, 문항별 기록(item_log) | 표준검사(사전·사후) |
| `articulation_sessions` | 입모양 그룹, 점수, 처음·끝 오차, 표본 수 | 웹캠 교정 세션 요약 |
| `weak_visemes`, `review_items`, `stage_progress`, `speak_stage_progress`, `bookmarks` | 약점 집계, 복습 일정, 단계 숙달, 저장한 문장 | 개인화·복습 |
| `tactile_*` | 촉각 기능 기록(화면에서 뺐고 새로 쌓이지 않는다) | 없음 |

저장하지 않는 것:
- **원음성**: 채점하는 동안 서버 메모리에서만 처리하고 파일로 남기지 않는다. 남는 것은 인식 결과(transcript)와 수치 지표다.
- **웹캠 영상**: 기기 안에서만 처리하고 서버로 보내지 않는다. 입모양 연습 중에는 기기에서 계산한 입모양 수치
  (턱 벌림·입술 둥글림·입술 다물기)와 점수가 교정 안내·약점 분석용으로 서버에 가지만, 프레임마다의 원본 값은 저장하지 않고
  연습별 점수와 교정 세션의 처음·끝 오차만 남는다(처리방침 `Legal.jsx`의 웹캠 항목과 같은 내용).

## 2. 파일럿 참여

- 운영자가 서버 환경변수로 켠다: `LIPLAB_PILOT=1`, `LIPLAB_PILOT_CODES='코드:집단,코드:집단'`(예: `ALPHA:train,BETA:control`).
- 참여자는 프로필 화면에서 참여 코드를 넣는다(`POST /api/pilot/join`). 코드에 따라 집단이 배정된다.
  공용 데모 계정은 참여할 수 없다. 참여해도 모으는 항목은 1절과 같다(파일럿만을 위한 추가 수집은 없다).
- 가입은 만 14세 이상만 된다(서버가 확인). 만 14세 미만 참여자가 필요하면 법정대리인 동의 절차를 먼저 만들어야 한다.

## 3. 연구자에게 넘기는 것(가명 내보내기)

`GET /api/pilot/export` — 운영자(`LIPLAB_ADMIN_EMAILS`)만, 파일럿이 켜져 있을 때만. 참여자 한 명당:

| 필드 | 내용 |
|---|---|
| `pid` | 가명. 서버 비밀키(`JWT_SECRET`)로 만든 HMAC 앞 12자리. 키 없이는 계정으로 되돌릴 수 없다 |
| `cohort`, `track` | 집단, 학습 트랙 |
| `tests` | 표준검사 폼·판본·정확도·수준·날짜 |
| `trials_by_stage` | 단계별 시행 수와 정답 수 |
| `speak` | 말하기 시도 수와 평균 점수 |
| `active_days` | 학습한 날 수 |

넣지 않는 것: 이메일, 사용자 이름, 입력 문장, 음성 인식 결과(transcript), 코칭 문구, 시각 단위 기록.
문항 단위 분석(IRT 보정 등)이 필요해지면 `item_log`를 가명으로 넘기는 판을 따로 만들고 이 표를 고친다.

## 4. 보관과 파기

정해야 할 것(사용자·연구 책임자 결정):
- **보관 기간**: 연구 종료일로부터 며칠 보관할지(예: 1년). 윤리 심의를 받으면 그 승인 내용을 따른다.
- **파기 방식**: 기한이 되면 파일럿에서만 빼는지(`unlink`), 계정과 기록까지 지우는지(`delete`).
  연구 참여만을 위해 만든 계정이면 `delete`, 계속 쓰는 학습자면 `unlink`가 맞다.
- **가명 내보내기 사본**: 연구자가 받은 가명 자료를 언제까지 두는지(서버 밖 사본이라 스크립트가 지우지 못한다).

절차(`scripts/pilot_retention.py`, 앱과 같은 `DATABASE_URL`·`JWT_SECRET`으로 `backend/`에서 실행):

```bash
python ../scripts/pilot_retention.py --study-end 2026-12-31 --retain-days 365                # 대상과 행 수만 본다
python ../scripts/pilot_retention.py --study-end 2026-12-31 --retain-days 365 --apply --mode delete
python ../scripts/pilot_retention.py --withdraw <pid> --apply --mode delete                    # 동의 철회
```

- 기본은 보고만 한다. 기한 전에는 `--apply`를 거부한다. 동의 철회는 기한과 무관하게 바로 처리한다.
- `delete` 범위는 계정 삭제(`DELETE /api/account`)와 같다: 1절의 사용자 표 전부와 계정.
- 처리할 때마다 파기 대장(`--ledger`, 기본 `pilot_destruction_ledger.jsonl`)에 한 줄을 덧붙인다. 대장은 연구 기록과 함께
  보관한다. 대장에는 가명만 남고 이메일·이름은 남지 않는다.

파기 대장 양식(사람이 확인·서명하는 판):

| 처리일 | 사유(기한 만료·동의 철회) | 방식(unlink·delete) | 집단 | 대상 가명 수 | 지운 행 수 | 처리자 | 확인자 |
|---|---|---|---|---|---|---|---|

## 5. 동의 철회

참여자가 철회하면: ① 운영자가 가명 내보내기에서 그 참여자의 `pid`를 찾는다(참여자에게 프로필 화면의 가명을 보여 주는
기능은 아직 없어, 운영자가 계정과 대조한다) ② `--withdraw <pid> --apply --mode delete`로 지운다 ③ 이미 연구자에게
넘긴 가명 자료에서 같은 `pid` 행을 지우도록 연구자에게 알린다 ④ 대장에 남는다.

## 6. 근거 코드

- 참여·가명 내보내기: `backend/main.py`(`/api/pilot/*`), 가명·파기 공용 함수 `backend/pilot_data.py`
- 파기 스크립트와 테스트: `scripts/pilot_retention.py`, `backend/test_pilot_retention.py`
- 처리방침 문구: `frontend/src/pages/Legal.jsx`(수집 항목, 웹캠·음성 처리)
