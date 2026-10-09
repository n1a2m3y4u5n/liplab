# 채점 회귀 점검 묶음 (O4, 2026-10-09)

> 계획: `docs/master-plan-2026-10.md` 트랙 O, O4. 코드: `backend/scoring_regress.py`(사례·비교·보고), 기준 파일 `backend/scoring_regress_golden.json`,
> 검사 `backend/test_scoring_regress.py`, 실행기 `scripts/scoring_regress.py`. 저장소에 CI가 없어 실행기 하나로 돈다.

## 1. 목적과 범위

채점 규칙을 고칠 때마다 다른 층의 판정이 함께 바뀌었는지를 사람이 일일이 확인해 왔다. 이 묶음은 네 층의 대표 입력과 그때의 출력을 기준 파일에 고정하고,
코드를 고친 뒤 같은 입력의 출력이 어떻게 달라졌는지를 사람이 읽는 차이 보고로 낸다. 정답을 증명하는 검사가 아니라 '바뀌었는가'를 알리는 검사다.

| 층 | 대상 | 사례 수 |
|---|---|--:|
| 독화 이해 채점 | `scoring.calculate_score`(입모양 v2, 발음 전사 경로 둘 다), `viseme_confusions` | 59 |
| 받아쓰기 낱말 판정 | `sentence_feedback.consonant_feedback`, `listen_curriculum.word_score` | 35 |
| 말하기 판정 규칙 | 단계 상수, `speak_curriculum.score_attempt`(발성·운율·전사·D-GOP 경로), `main.speak_hold`, D-GOP 문장 집계와 보정 앵커 네 벌, `main._ewma_mastery`와 숙달 68 도달 시점, `gain_mastered`, `voiced_attempt`, `probes_ok` | 69 |
| 발음 규칙 엔진 | `engine.to_pronounced_syllables`(입모양 경로, 소리 경로, ㅎ 탈락·ㄴ 첨가, ㄹ 뒤 된소리), `text_to_visemes` | 80 |
| 채점 API 경로 | `/api/speak/assess`(D-GOP 12번, 낱말 단계 향상 경로 20번, 전사 경로 7번), `/api/progress`(주관식 4, 4지선다 2) | 28 |

D-GOP 음향 모델(wav2vec2)과 Whisper는 불러오지 않는다. 말하기 판정 층은 음소별 D-GOP 값(0~1)이나 보정된 문장 점수를 입력으로 고정하고,
그 뒤의 규칙(문장 평균, 보정 앵커, 합격선 65, 판정 보류 ±7.5, 이동 평균 숙달 68, 개인 향상 경로)만 본다. API 층은 임시 DB를 쓰는 별도 프로세스에서
`dgop_acoustic.assess_text`·`speak_service.transcribe`를 가짜로 바꾸고, LLM 호출도 막는다(`ANTHROPIC_API_KEY` 비움, 클라이언트를 예외로 바꿈).
음향 모델의 출력 자체(정렬, 끝 자르기, 음소 사후확률)는 이 묶음에 들어 있지 않다. 그쪽은 `test_dgop_acoustic.py`·`test_dgop_tail_trim.py`가 합성 입력으로 본다.

## 2. 두 겹의 검사

1. **기준 파일과의 차이.** 사례마다 출력 전체를 점 경로로 펴서 비교한다(숫자는 1e-6 안이면 같음). 의도한 변경이면 기준을 다시 쓴다.
2. **고정 기대(`PINNED`, 60개).** 규칙 문서나 결정에 적힌 값이다. 기준을 다시 써도 바뀌지 않고, 바꾸려면 `scoring_regress.py`를 고쳐야 한다.
   예: 4·5단계 합격선 65·숙달 68·`_SPEAK_SEM` 7.5, 65점은 합격이고 64.9점은 불합격, 판정 보류는 57.5·72.5에서 꺼지고 57.6·72.4에서 켜짐,
   확인 낱말과 음절 단계에는 보류 없음, 9/27 감사의 틀린 모음·첫소리 불합격, 받아쓰기 '내일다시 올께요' 3/3, '굳이'의 입모양 경로 '구지',
   소리 경로 '국물 → 궁물'·'백리 → 뱅니', API에서 65점 합격·보류, 낱말 단계 20번째 시도의 향상 경로 숙달.

기존 검사와 겹치는 것은 정리했다. `test_speak_hold.py`(2개)와 `test_speak_mastery_gain.py`의 순수 함수 검사 4개(단계 상수, `gain_mastered` 두 개,
`voiced_attempt`)는 같은 입력과 기대값으로 고정 기대에 옮기고 지웠다. DB를 거치는 향상 경로 검사는 그 파일에 남겼다.
`test_scoring_v2.py`·`test_sentence_feedback.py`·`test_engine.py`·`test_phonetic_rules.py`의 성질 검사(부등식, 규칙의 이유를 적은 것)는 남겼다.
스냅숏은 무엇이 바뀌었는지를 보이고, 성질 검사는 왜 틀렸는지를 보인다. 같은 입력을 스냅숏 사례로도 넣었다.

## 3. 사용법

```bash
# 저장소 뿌리에서, 백엔드 가상환경의 파이썬으로
~/Downloads/liplab/backend/.venv/bin/python scripts/scoring_regress.py            # 전체(약 50초): 차이 보고 + API 층 + 관련 성질 검사 14개 파일
~/Downloads/liplab/backend/.venv/bin/python scripts/scoring_regress.py --quick    # 순수 함수 층만(약 2초)
~/Downloads/liplab/backend/.venv/bin/python scripts/scoring_regress.py --layers speak,speak_api --report /tmp/regress.md
~/Downloads/liplab/backend/.venv/bin/python scripts/scoring_regress.py --update   # 의도한 변경일 때만 기준을 다시 쓴다
```

- 종료 코드: 차이·고정 기대 위반·성질 검사 실패가 하나라도 있으면 1, 없으면 0. `--update`는 고정 기대 위반이 있으면 기준을 쓰지 않는다.
- 백엔드 전체 검사(`python -m pytest`)에도 `test_scoring_regress.py`가 들어 있어, 기준과 다르면 같은 차이 보고가 실패 메시지로 나온다.
- 채점 규칙을 고친 커밋은 `--report`로 만든 보고를 커밋 설명이나 관련 문서에 붙이고, 같은 커밋에서 `--update`로 기준을 갱신한다.
- 사례를 더할 때는 `scoring_regress.py`의 입력 목록에 넣고 `--update`한다. 보고에는 '새 사례'로 나온다.

## 4. 차이 보고 형식

층별 요약 표(사례, 같음, 바뀜, 새 사례, 없어진 사례, 판정 바뀜) 뒤에 바뀐 사례마다 항목별 '전 → 후(차)'를 적는다. 참·거짓 값(합격·보류·숙달)이나
판정 이름의 항목(맞힌 낱말 수, 피드백 등급, 숙달 도달 시점)이 바뀌면 줄 앞에 '판정'을 붙이고, 층마다 숫자 변화의 평균과 절댓값 최대를 붙인다.
아래는 시험 삼아 입모양 같은 무리의 부분 점수(`VISUAL_SAME_GROUP`)를 0.8에서 0.7로, `_SPEAK_SEM`을 8.0으로 바꿨을 때의 보고 일부다(코드에는 넣지 않음).

```
- 결과: 바뀐 사례 10건, 고정 기대 위반 3건
| 독화 이해 채점 | 59 | 54 | 5 | 0 | 0 | 0 |
| 말하기 판정 규칙 | 69 | 64 | 5 | 0 | 0 | 4 |
## 고정 기대 위반(규칙 문서 값과 다름, --update로 고쳐지지 않음)
- [말하기 판정 규칙] 상수 | 판정·이동 평균: _SPEAK_SEM = 8.0, 기대 7.5
- [말하기 판정 규칙] 판정 보류 | sentence 합격선 65: 57.5 = True, 기대 False
- visual | 바다가 넓어요 ← '마다가 넓어요'
  - score: 98.06 → 97.08 (-0.98)
- 판정 보류 | sentence 합격선 65
  - 판정 57.5: False → True
```

## 5. 첫 실행(2026-10-09, 기준 커밋 d9560917)

- 차이 없음, 고정 기대 위반 0. 백엔드 742 통과(전에 744, 지운 6개와 더한 4개), 프론트 321 통과.
- 기준을 만들며 기록해 둔 지금 동작(결함 판정이 아니라 기록):
  - 입모양 v2에서 '물 좀 주세요'를 '불 좀 주세요'로 적으면 97.67점으로 합격한다. ㅁ·ㅂ은 입모양이 같아 의도대로다. 받아쓰기 판정은 같은 답을 3낱말 중 2개로 본다.
  - D-GOP 문장 점수는 음소 평균이라, 8음소 중 하나만 0이고 나머지가 0.9면 원점수 78.8, 배포 앵커(`dgop_calibration_ours.json`)로 86.5점이 되어 합격한다.
  - 배포 앵커에서 원점수 40은 64.6점(불합격, 보류)이고 공개 kresnik 앵커에서는 67.3점(합격, 보류)이다. 같은 원점수의 합격 여부가 채점기 앵커에 따라 갈린다.
  - 숙달 이동 평균은 초반에 누적 평균에 가까워, 장기 합격률 60%인 순서(합격, 합격, 불합격, 합격, 불합격, …)도 문장 단계(최소 6번)에서 7번째에 68에 닿는다.
    한 번 숙달하면 유지하는 규칙과 합쳐지면 초반 연속 합격이 숙달을 앞당긴다(`docs/mastery-ewma.md`의 가상 학습자 결과와 같은 방향).
  - 받아쓰기는 'KTX'를 '케이티엑스'와 같다고 보지 않는다(0/1). '갈비'를 '갈삐'로 적은 답은 맞힌 것으로 본다(ㄹ 뒤 된소리 표기 통합, 문서화된 관대함).

## 6. 한계

- 기준 파일은 지금 출력이 옳다는 근거가 아니다. 고정 기대 60개만 규칙 문서에 기대고, 나머지는 '지금과 같은가'만 본다.
- 입모양 시각 유사도는 numpy 고전 MDS에서 나온다. 다른 파이썬·numpy에서 소수 넷째 자리 아래가 달라질 수 있어 비교 허용 폭을 1e-6으로 두었다(출력은 이미 반올림됨).
  기준은 파이썬 3.14.6(`~/Downloads/liplab/backend/.venv`)에서 만들었다.
- 사례 id는 입력 문자열의 repr라, 전각 공백 같은 글자는 `　`으로 적힌다.
- API 층의 코칭 문장(LLM 대체 문장)은 비교하지 않는다. 채점·판정과 무관하고 문구 수정이 잦기 때문이다.
