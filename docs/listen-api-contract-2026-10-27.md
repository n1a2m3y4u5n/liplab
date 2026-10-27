# 소리 듣기 API 계약 — 2026-10-27 (L1/L2)

기존 필드는 유지하고 아래 필드만 추가한다. 단계 번호는 서버 기준 0~5, 화면은 1~6. 모든 단계 DAILY_QUOTA=2; BATCH_N={0:8,1:12,2:10,3:8,4:10,5:8}. 약 7~8분은 안내용 추정이며 완료 조건은 시간 아닌 묶음 수다.

## GET /api/listen/curriculum
응답 예시(단계 한 개만 발췌):
```json
{
  "stages": [{"stage":1,"title":"소리 구별","mode":"ax","status":"in_progress","attempts":13,"quota":{"today_n":1,"quota_n":2,"batch_n":12,"today_answers":13,"partial_n":1,"met":false,"days":[{"date":"2026-10-26","n":2,"met":true},{"date":"2026-10-27","n":1,"met":false}]}}],
  "recommended":1,
  "ling_today":true,
  "is_demo":false,
  "all_stages_open":false,
  "experience_label":null,
  "next_node":{"stage":1,"kind":"today","batch":2}
}
```
`today_n` / days[].n = 완료 묶음 수(상한 없이 실제 값), `today_answers` = 유효 답 수, `partial_n` = 다음 묶음에 들어간 답 수. `met`=today_n>=2. 오늘 답이 없으면 today_n=0, days는 기록이 있는 최근 14일만(오름차순). 지난 노드는 days에서 오늘 이전 met=true를 최근 두 개 선택. 내일 노드와 숙달 노드는 클라이언트가 status·quota로 그린다. 현재 링은 recommended 단계에만 둔다.

`recommended`: 소리 확인을 아직 끝내지 않았으면 0; 그 뒤 배치 결과가 있고 접근 가능한 미숙달 단계면 그 단계, 아니면 1~5 중 첫 열린 미숙달 단계; 전부 숙달이면 5. 오늘 몫을 채웠다고 추천 단계를 올리지 않는다. `next_node`: 아직 몫이 남은 추천 단계의 다음 묶음; 몫을 채웠으면 kind="tomorrow", batch=1. is_demo=true이면 모든 단계 열리고 experience_label="체험용 · 모든 단계 열림". 일반 계정은 환경변수 미설정 또는 1이어도 듣기 순차 잠금 유지. 기존 placement 필드는 기존 플래그가 켜진 경우만 제공.

## GET /api/listen/stage/{n}
기존 응답에 `quota`(위와 같음) 추가. 문항 수·문항 형식은 기존 유지.

## POST /api/listen/answer / POST /api/listen/ling
요청은 기존과 같다. 추가 응답 예시:
```json
{"counted":true,"batch_completed":true,"xp_gained":16,"streak_count":1,"quota":{"today_n":1,"quota_n":2,"batch_n":12,"today_answers":12,"partial_n":0,"met":false,"days":[{"date":"2026-10-27","n":1,"met":false}]}}
```
일반 답은 KST 날짜별 누적 유효 답이 BATCH_N의 배수에 도달할 때 묶음 완료·기본 15XP(기존 연속 학습 배수 적용). 중간 답은 batch_completed=false,xp_gained=0. Ling은 한 번의 완전한 results 제출이 한 묶음이며 quota의 today_answers에는 가상 8문항으로 환산. 두 API 모두 해당 단계 quota 반환. Ling에는 기존 summary/session 유지. 연습·다시 쓴 답·검사·일반화 검사·생성 대화는 몫·XP 제외. 연속 학습도 묶음 완료 때만 갱신. 새 완료 API 호출은 필요 없음.

## GET /api/listen/today
기존 blocks/target_min/done_today/review_due 유지. 추가 `recommended`, `quotas`(문자열 단계 번호→quota), `next_node` 제공. 기존 15분 섞어서 듣기 계획은 유지; 그 답도 해당 단계의 몫에 합산.

## GET /api/tasks
기존 listen_15 키 유지(수령 중복 방지 호환). label="소리 듣기 오늘 몫",total=2,cur=오늘 각 학습 단계에서 완료한 묶음 합(최대2),done=cur>=2. 소리 확인(0)은 준비 점검이므로 과제 합산에서 제외. 일반 학습 단계 1~5를 섞어 한 묶음씩 끝내도 인정. 주간 학습일은 기존 듣기 활동 기록 기준 유지. 보상 15XP 및 claim 방식 유지.

## 잠금 환경변수 확인(기준 8c6844db)
`fly.dev.toml` 19행은 `LIPLAB_UNLOCK_ALL="demo"`를 지정한다. `fly.toml`, `Dockerfile`, `.env.example`에는 이 변수가 없다. 배포 서버 secrets 값은 조회하지 않았다. 공통 `_unlock_all_for`의 기본값 `"1"`과 독화·발화 동작은 보존하며, 듣기 `_listen_open`만 체험 계정 판별로 분리했다. 따라서 듣기는 변수 값과 무관하게 데모만 전체 열리고 일반 계정은 순차 잠금·명시적 건너뛰기·배치검사 규칙을 따른다.

## dev 베타 기간 예외(2026-10-27 후속 결정)
`LIPLAB_LISTEN_BETA_OPEN=1`일 때 일반 계정도 듣기 전 단계가 열린다. 코드 기본값은 0이고 `fly.dev.toml`에서만 1로 지정한다. 일반 계정 응답은 `is_beta=true`, `all_stages_open=true`, `beta_label="베타 한정 · 모든 단계 열림"`, `experience_label=null`이며 경로에 배지 하나만 표시한다. 데모는 기존 체험 배지가 우선하고 `is_beta=false`이다. 플래그를 끄면 위 순차 잠금 규칙으로 돌아간다. 독화·발화 잠금, 숙달·추천·하루 몫 계산 규칙은 그대로다.
