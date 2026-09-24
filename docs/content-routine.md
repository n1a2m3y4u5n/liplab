# 콘텐츠 월간 생성·검수 루틴(G-10, 9/24 확정)

계획서 표 9는 콘텐츠 확장(G)을 전 기간에 걸쳐 병행한다고 했다. 한 번에 대량으로 만들고 끝내지 않고, 한 달에 한 번 적은 양을
만들어 규칙 게이트와 사람 검수를 거친 뒤 승인 판본에 더한다. 주기와 양, 표본 비율은 9/24에 아래 값으로 정했다(운영하며 조정).

## 1. 지금 규모(2026-09-24)

- 앱이 쓰는 커리큘럼: 단어 528, 최소대립쌍 921, 문맥 문항 186.
- 그중 승인 판본(`backend/data/curriculum/approved.json`): 단어 525, 쌍 917, 문맥 문항 181. 앱 기동 때 기본 콘텐츠에 병합된다.

## 2. 한 달 한 번(담당: G 검수 팀원)

1. **후보 만들기.** `python scripts/gen_content.py --words 60 --closures 30` → `backend/data/curriculum/candidates_<시각>.json`
   (Claude API 사용, 상태 `candidate`). `--auto-approve`는 데모용이라 쓰지 않는다.
2. **규칙 게이트.** 생성 단계에서 `content_rules`가 자동으로 건다. 문맥 문항은 보기 3개 이상, 눈으로 헷갈리는 오답 2개
   이상이어야 한다. 2지 문항이 섞였으면 `python scripts/upgrade_closures.py --dry-run`으로 보고 강화한다.
3. **사람 검수.** 운영자 화면 `/admin/content-review`(서버에 `LIPLAB_REVIEW=1`, `LIPLAB_ADMIN_EMAILS`에 검수자 이메일) 또는
   `python scripts/review_content.py`. 표본 규칙(초안):
   - 문맥 문항은 전부 본다(문장이 어색하거나 답이 둘인 문항이 가장 해롭다).
   - 단어는 난이도 3단계 이상은 전부, 1~2단계는 무작위 20%를 본다. 표본에서 반려가 10%를 넘으면 그 달 단어를 전부 본다.
   - 쌍은 규칙으로 만든 것이라 무작위 10%만 본다.
   - 반려 사유는 한 줄로 적는다. 결정은 `approved.json`의 `meta.review_log`에 검수자 가명 태그와 시각으로 남는다.
4. **검사 단어 제외 확인.** 표준검사 전용 단어(`assessment.test_only_words()`)로 학습하면 사전·사후 검사가 문항 암기를 재게
   된다. 앱은 학습 문항·문맥 문항·배치검사를 낼 때 이 단어를 걸러 내므로 새 콘텐츠에도 그대로 적용된다. 승인 뒤
   `pytest backend/test_pilot.py -k placement_hides_test_words`로 한 번 더 본다.
5. **병합과 시험.** 여러 브랜치에서 승인 판본이 따로 자랐으면 `python scripts/merge_approved.py ours.json theirs.json --dry-run`
   으로 보고한 뒤 `--out`으로 합친다(합친 뒤 규칙 게이트를 다시 건다). 이어서
   `pytest backend/test_content_rules.py backend/test_content_review.py backend/test_content_merge.py`.
6. **기록.** 월별로 생성 수, 규칙 탈락 수, 검수 수, 반려 수와 주된 사유를 `docs/report-notes.md`의 G 항목 아래에 한 줄로 적는다.
   파일럿 중이면 새 콘텐츠는 파일럿 집단 사이에 똑같이 들어가므로 따로 조정하지 않는다.

## 3. 멈출 조건

- 반려율이 두 달 연속 30%를 넘으면 생성 프롬프트나 규칙을 먼저 고친다.
- 파일럿 사후 검사 직전 한 주는 새 콘텐츠를 넣지 않는다(학습 조건이 바뀌지 않게).
