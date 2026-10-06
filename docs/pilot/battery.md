# 청인 예비 파일럿(P3) 검사 묶음: 목록 파일, 촬영할 매체, 리허설(2026-10-06)

> master-plan 2판 P3(5절)·P0·가1·가4, `design-simulation.md` 5·6절의 추천 설정을 앱에 옮긴 것이다. 촬영 전이라 실제 얼굴 영상과
> 소음 속 문장 음성은 없다. 영상이 없는 문항은 화면에 '영상 준비 전'으로만 알리고 내지도 세지도 않는다. 목록 파일은 초안(status
> "draft")이며, 문장·폼 C 낱말을 사람이 검토해 동결한 뒤 촬영한다. 코드: `backend/pilot_battery.py`, `backend/main.py`
> `/api/pilot/battery/*`, 화면 `frontend/src/pages/PilotBattery.jsx`(`/pilot/battery`), 목록 `backend/data/pilot/battery_manifest.json`.

## 1. 요약

| 항목 | 내용 |
|---|---|
| 대상 | 파일럿 참여자만. `LIPLAB_PILOT=1`이고 참여 코드(`LIPLAB_PILOT_CODES`)를 넣은 계정. 그 밖의 계정과 공용 데모 계정은 403이고, 들어가는 곳은 프로필의 '파일럿 참여' 창뿐이다 |
| 회차 | A1, A2(학습 없이 두 번), B(2주 학습 뒤), R(유지). 앞 회차를 마쳐야 다음 회차가 열린다 |
| 폼 | A·B·C 세 동형 폼. 순서는 순환 라틴 방진 ABC, BCA, CAB를 검사 참여 순번대로 돌려 준다(순번 i의 순서 = ORDERS[(i − 1) % 3]). R은 B와 같은 폼 |
| 층 | 무의미 낱말 자음(16), 실제 얼굴 낱말 4지선다(24), 개방형 문장 타이핑(40), SNR 맞추기(A1만), 소음 속 문장(20, A·AV 반씩) |
| 재생 | 1.0배 고정, 문항당 최대 2번(목록 `playback`). 끝까지 한 번 재생한 뒤에 답할 수 있다. 정답은 알려 주지 않는다 |
| 기록 | 회차 × 층 행(`p3_test_sessions`), 닫힌 응답(`p3_closed_responses`), 열린 응답(`p3_open_responses`). 가명 내보내기 판 5의 `battery` |

검사 참여 순번(`learning_profiles.pilot_seq`)은 참여자가 검사 화면을 처음 열 때 지금까지 가장 큰 순번 + 1로 매긴다. 두 사람이
같은 순간에 처음 열면 같은 순번을 받을 수 있으므로, 리허설과 본 검사에서는 한 사람씩 처음 화면을 연다(4.2 확인 항목).

## 2. 층별 규칙

| 층 | 자극 | 응답 | 화자 배정 | 문항 순서 | 준비 판정 |
|---|---|---|---|---|---|
| `nonsense` | 규칙 엔진 아바타(LipSyncPlayer3D, 기본 얼굴) | 자리별 자음 고르기(첫 자음 13, 가운데 자음 13, 받침 6). 모음은 화면에 보인다 | 아바타 | 사람·회차마다 결정론적으로 섞음 | 늘 준비됨 |
| `word` | 실제 얼굴 영상(소리 없음) | 4지선다 | 화자 4명을 회차 안에서 돌림(24문항이면 화자마다 6문항), 회차마다 시작점을 옮김 | 같음 | 배정 화자의 영상 파일이 있을 때 |
| `sentence` | 실제 얼굴 영상(소리 없음) 또는 아바타(목록 `modality`) | 타이핑 | 화자 2명을 참여자 사이에서 번갈아, 한 사람은 모든 회차에서 같은 화자 | 같음 | real: 영상 파일이 있을 때. avatar: 문장 글이 있을 때 |
| `snr` | 실제 화자 음성(영상은 가림) + 잡담 잡음 | 타이핑 | 문장 층과 같은 규칙 | 같음 | 문장 글, 영상(음성 포함), `speech_rms_dbfs`, 잡음 파일 |
| `av` | A 블록은 소리만, AV 블록은 영상과 소리, 둘 다 잡담 잡음 | 타이핑 | 문장 층과 같은 규칙 | 폼 문장을 앞뒤 절반으로 나눠 A·AV에 배정(참여자 둘마다 바꿈), 블록 순서는 참여자마다 바꿈 | 위 조건 + A1에서 정한 개인 SNR |

- 지금 목록은 문장 층을 `avatar`로 두었다(영상이 생기기 전에도 리허설을 돌릴 수 있게). 촬영 뒤에는 `layers.sentence.modality`를
  `real`로 바꾸고 `version`을 올린다. 주결과는 실제 얼굴 조건이다(master-plan 5절). 아바타 조건 결과는 주결과에 넣지 않는다.
- 무의미 낱말은 짝 맞추기 학습(C10, `backend/nonsense_words.py`)이 남겨 둔 두 목록(2 × 16)을 폼 A·B로 쓰고, A-A-B에 필요한 폼 C는
  같은 생성기로 남겨 둔 목록을 하나 더 만든 것이다(`pilot_battery.nonsense_forms`, 같은 시드에서 세 번째 목록이라 앞 두 목록은
  그대로다). 세 폼 모두 학습 목록 48낱말과 겹치지 않고 자음 골격도 학습 목록에 없다. 폼 C를 만들 때 사람이 보고 '주산', '주곡'을
  더 뺐다(`NONSENSE_EXTRA_EXCLUDED`).
- SNR 맞추기는 가중 상하 계단이다(Kaernbach 1991). 맞으면 3 dB 내리고 틀리면 2 dB 올려 청각만 정답률 약 40%로 수렴한다(가4의
  30~50% 목표). '맞음'은 문장 낱말의 50% 이상을 그대로 쓴 경우다. 반전 8번 또는 24시행에서 멈추고, 마지막 반전 6개의 평균을 개인
  SNR로 쓴다(반전이 모자라면 마지막 6시행 수준의 평균, `estimate_kind = last_levels`). 시작 0 dB, 범위 −20~+10 dB. 계단은 서버가
  저장된 판정으로 다시 계산한다(`pilot_battery.staircase_run`).
- 잡음은 브라우저의 Web Audio로 섞는다. 영상의 소리는 그대로 두고 잡음 이득을 10^((말소리 dBFS − SNR − 잡음 dBFS)/20)으로 맞춘다.
  말소리 크기는 목록의 `speech_rms_dbfs`(매체를 준비할 때 잰 값), 잡음 크기는 받은 잡음 파일에서 브라우저가 잰다. 잡음은 말보다
  0.3초 먼저 시작해 0.3초 뒤에 멈춘다. 헤드폰 착용과 볼륨 고정은 연구진이 화면에서 확인해야 소음 층을 시작할 수 있고, 확인 값이
  회차 행(`headphone_check`, `volume_fixed`)에 남는다.

## 3. 목록 파일 스키마(`schema: liplab-pilot-battery/1`)

`backend/data/pilot/battery_manifest.json`. 서버는 켜질 때가 아니라 검사 요청 때 읽고, 파일이 바뀌면 다시 읽는다. 다른 파일을
쓰려면 `LIPLAB_PILOT_MANIFEST`. 점검(`pilot_battery.validate_manifest`)에 문제가 있으면 검사를 시작하지 않고 화면에 문제를 보인다.

| 키 | 형식 | 뜻 |
|---|---|---|
| `schema`, `version`, `status` | 문자열 | 스키마 이름, 판(회차 행 `form_version`에 남는다), `draft`·`frozen` |
| `forms` | `["A","B","C"]` | 고정 |
| `orders` | 문자열 3개 | 순환 라틴 방진이어야 한다(자리마다 각 폼 한 번) |
| `label_slot` | 사전 | 회차 → 순서 안 자리(A1 0, A2 1, B 2, R 2). 코드의 `LABEL_SLOT`과 같다(참고용) |
| `layers_by_label` | 회차 → 층 목록 | 회차마다 볼 층과 화면 순서. `snr`은 A1에만 둔다 |
| `playback` | `{speed: 1.0, max_plays}` | 재생 속도(1.0 고정), 문항당 최대 재생 횟수(1~5) |
| `talkers` | 층 → 화자 id 목록 | 영상 파일 경로의 `{talker}` 값. 영문·숫자·`_-` 16자 이내 |
| `noise.babble.file` | 상대 경로 | 잡담 잡음 파일(매체 폴더 기준) |
| `layers.<층>.title`, `response`, `modality` | 문자열 | 화면 이름, 응답 방식(`choice4`·`typed`·`consonant3`), 자극 조건 |
| `layers.<층>.n_per_form` | 정수 | 폼마다 문항 수(점검이 실제 수와 맞춰 본다) |
| `layers.<층>.media_pattern` | 상대 경로 | `{talker}`와 `{id}`가 든 경로. 문항이 `media`(화자 → 경로 사전)를 주면 그것이 먼저다 |
| `layers.<층>.items` | 폼 → 문항 목록(`snr`은 목록 하나) | 문항 id는 목록 전체에서 하나뿐이고 영문·숫자·`_-` 40자 이내 |
| `layers.<층>.reserve` | 문항 목록 | 예비 문항(리허설에서 문제가 된 문항과 바꿀 때) |
| `layers.word.items[]` | `{id, word, options[4], difficulty}` | 정답과 보기(서로 다른 4개, 정답 포함) |
| `layers.sentence.items[]` | `{id, text, syllables, phonemes}` | 6~10음절, 숫자·영문 없음 |
| `layers.nonsense.items[]` | `{id, text, consonants[3], vowels[2]}` | 글자와 자모가 맞아야 하고, 자음은 `consonant_sets`의 자리별 목록 안 |
| `layers.av.items[]`, `layers.snr.items[]` | `{id, text, speech_rms_dbfs}` | 촬영 뒤에 채운다. 지금은 모두 `null`(지어낸 문장·음성 없음) |
| `layers.snr.staircase` | 사전 | `start_db, step_down_db, step_up_db, min_db, max_db, reversals, use_last, max_trials, criterion` |

매체 파일은 저장소에 넣지 않는다(얼굴이 나오는 개인정보, `.gitignore`의 `backend/data/pilot/media/`). 서버의 매체 폴더는
`LIPLAB_PILOT_MEDIA_DIR`(기본 `backend/data/pilot/media`)이고, 화면은 로그인한 참여자의 회차에 속한 문항만 받는다
(`GET /api/pilot/battery/media/{회차}/{문항}`). 경로는 매체 폴더 밖을 가리킬 수 없다.

목록 다시 만들기: `python3 scripts/build_pilot_manifest.py --force`(문장 후보는 스크립트 안의 초안 목록에서 조건을 통과한 것을
음소 수가 고르게 세 폼으로 나눈다. `--check`는 걸러진 후보와 사유만 보인다). 동결한 뒤에는 스크립트를 다시 돌리지 않고 파일을
직접 고친 다음 `version`을 올린다. 테스트(`backend/test_pilot_battery.py`)가 목록 점검, 무의미 낱말이 C10 남겨 둔 목록과 같은지,
폼 C 낱말이 다시 만든 것과 같은지를 확인한다.

## 4. 촬영에서 받아야 할 매체(master-plan 3절, design-simulation 6절과 대조)

| 묶음 | master-plan 3절 지금 목록 | 이 검사 묶음에 필요한 양 | 파일 이름(매체 폴더 기준) | 비고 |
|---|---|---|---|---|
| 실제 얼굴 낱말 | 화자 4명 × A·B 48낱말 | **화자 4명 × 72낱말(폼 C 24개 추가) = 288개** | `words/T1~T4/{A1..A24,B1..B24,C1..C24}.mp4` | 폼 A·B 낱말은 표준검사 forms_v2(촬영 키트 4절)와 같다. 폼 C 초안은 목록 파일. 아바타 검사(사전·사후 A·B)와 같은 낱말을 쓰는 문제는 결정 필요(6절) |
| 개방형 문장 | 2 × 20문장 | **3폼 × 40문장 + 예비 12 = 132문장 × 화자 2명 = 264개** | `sentences/T1~T2/{SA01..SC40, SR01..SR12}.mp4` | 문장은 목록 파일의 초안. 촬영 전에 사람이 검토해 동결한다. 화자 1인당 132문장 × 2테이크로 약 50~60분 |
| 무의미 낱말 | 2 × 16 CVCVC | 지금은 아바타로 내므로 촬영 없이 돌아간다. 실제 얼굴로 내려면 3 × 16 = 48낱말 | (실제 얼굴로 바꿀 때) `nonsense/T…/{NA01..NC16}.mp4` | 폼 C까지 세 목록이 필요하다. C10 학습 목록 48낱말은 찍어도 검사에 쓰지 않는다 |
| 소음 속 문장 | 위 문장의 깨끗한 음성 | **개방형 문장과 다른 문장**, 3폼 × 20문장 + 예비, 화자 2명. 영상과 소리를 함께 | `av/T1~T2/{VA01..VC20}.mp4` | 같은 회차에 같은 문장을 두 번 보면 안 된다(design-simulation 6절). 문장을 정해 목록 `text`에 넣는다 |
| SNR 맞추기 문장 | 없음 | 24문장 × 화자 2명(소리만 쓰지만 같은 촬영으로) | `av/T1~T2/{VK01..VK24}.mp4` | 위 두 문장 묶음과 겹치지 않게. 계단이 24시행 안에 끝나므로 24개 |
| 잡담 잡음 | 없음 | 여러 사람(8명 이상 권장) 말소리를 섞은 잡음 1개, 모노 48 kHz, 30초 이상 | `noise/babble.wav` | 팀원 녹음을 섞어 만들거나 이용 허락이 분명한 자료로. 지어내지 않는다 |
| 말소리 크기 | 없음 | 소음 층·SNR 문장마다 RMS(dBFS) | 목록 `speech_rms_dbfs` | 앞뒤 무음 1초를 뺀 말소리 구간에서 잰다. 클립끼리 크기를 맞춘 뒤 잰다 |

공통 형식(촬영 키트 `docs/real-talker-test-kit.md` 2절과 같고, design-simulation 6절에 맞춰 60fps 고정):

- 1080p, 60fps 고정, H.264 mp4(브라우저 재생). 소리는 AAC 48 kHz. 소리 없는 층(낱말·문장)도 소리를 남겨 두되 화면은 음소거로 낸다.
- 입을 다문 1초 → 말하기 → 입을 다문 1초. 자를 때 앞뒤 0.5초 여유. 첫 정상 테이크 규칙(키트 2절).
- 영상 누락 점검(V20)과 같은 기준으로 재기 위해 프레임을 바꾸는 후처리(보간)를 하지 않는다.
- iPhone ARKit 동시 기록(P12)은 같은 촬영에서 함께(master-plan 3절).

master-plan 3절 표에서 고칠 것: 문장 2 × 20 → 3 × 40(+예비), 무의미 낱말 2 × 16 → 3 × 16(실제 얼굴로 낼 때), 실제 얼굴 낱말에 폼
C 24개, 소음 속 문장은 별도 문장 3 × 20과 SNR 문장 24, 잡담 잡음 파일. 1인당 촬영 시간은 '15~30분 추가'보다 길다(문장만 50~60분).

## 5. 기록과 내보내기

| 표 | 한 행 | 주요 열 |
|---|---|---|
| `p3_test_sessions` | 사람 × 회차 × 층 | `session_label`, `layer`, `form`, `form_version`(목록 판), `manifest_sha`, `planned_order`, `join_seq`, `modality`, `talker`, `n_items`, `n_ready`, `missing`(못 낸 까닭별 수), `snr_calibrated_db`, `headphone_check`, `volume_fixed`, `render_log`, `completed`, `started_at`, `completed_at` |
| `p3_closed_responses` | 낱말·무의미 낱말 문항 | `seq`(제시 순번), `item_id`, `talker`, `target`, `options`, `chosen`, `correct`, `target_consonants`, `chosen_consonants`, `consonant_hits`, `rt_ms`, `rt_from_onset_ms`, `plays`, `speed` |
| `p3_open_responses` | 문장·소음·SNR 문항 | `answer_text`(원문, NFC), `app_score`(지금 앱 채점 `calculate_score` visual, 0~100), `auto_phoneme_acc`·`auto_word_acc`(엄격 채점 0~1), `n_matched_phonemes`·`n_target_phonemes`, `scorer_version`(`strict-v1`), `rt_ms`, `rt_from_onset_ms`, `plays`, `modality`(real·avatar·A·AV), `snr_db`, `noise_type`, `criterion_met` |

- `rt_ms`는 첫 재생이 끝난 때부터, `rt_from_onset_ms`는 첫 재생이 시작한 때부터 답을 확정할 때까지(ms)다.
- 엄격 음소 정답률은 `backend/phoneme_accuracy.py`의 `strict_phoneme_accuracy(target, answer)`(기본 설정: 낱자 버림, 발음 규칙
  없음)로 답을 받을 때 계산한다. 회차 점수는 문장 비율의 평균이 아니라 `n_matched_phonemes` 합 / `n_target_phonemes` 합으로 낸다.
  모듈을 불러오지 못하면 NULL로 두고 `scripts/pilot_battery_rescore.py`로 내보내기 파일을 다시 채운다(채점 규칙을 바꿨을 때는 `--all`).
- 영상이 없어 내지 않은 문항은 응답 행이 없고, 회차 행의 `missing`에만 센다. 끝내지 못한 층도 회차 행이 남는다(ITT).
- 학습 초기화: 파일럿 참여자의 P3 세 표는 지우지 않는다(사전·사후 표준검사, 유지 검사와 같은 규칙). 계정 삭제와 파일럿 파기는
  모든 표를 지운다(`pilot_data.user_data_models`).
- 가명 내보내기 판 5: 참여자마다 `join_seq`, `planned_order`, `b_completed_seq`(B 문장 층을 마친 순번, 순차 멈춤 규칙용), `battery`
  (회차 × 층, 문항 응답 포함). 개방형 검사 문항에 한해 답 원문이 들어가므로, **동의서 5-3 '연구진이 받는 것'과
  `docs/pilot-data-spec.md` 3절을 고친 뒤에** 쓴다. 학습 중 입력 문장은 넣지 않는다.

## 6. 팀 리허설(P0 판정 '리허설에서 필요한 필드가 모두 내보내기 판에 나옴')

### 6.1 준비(로컬 또는 개발 서버, 운영 서버 아님)

```bash
cd backend
export LIPLAB_PILOT=1 LIPLAB_PILOT_CODES=REHEARSAL:train LIPLAB_ADMIN_EMAILS=<운영자 계정 이메일>
export LIPLAB_PILOT_MEDIA_DIR=<매체 폴더>      # 비워 두면 영상 문항은 모두 '영상 준비 전'
python -m uvicorn main:app --port 8080
```

1. 팀원마다 시험 계정을 만들고 프로필 → 파일럿 참여에 `REHEARSAL`을 넣는다. 한 사람씩 '검사 회차 열기'를 눌러 참여 순번을 받는다.
2. 영상이 없어도 돌아가는 층: 무의미 낱말, 개방형 문장(아바타). 영상 몇 개를 매체 폴더 규칙대로 넣으면 그 문항만 '준비됨'으로 바뀐다.
3. 소음 층을 시험하려면 시험용 목록 사본(`LIPLAB_PILOT_MANIFEST`)에 SNR·소음 문장 몇 개의 `text`와 `speech_rms_dbfs`를 넣고 매체를
   둔다. 이 사본은 저장소에 넣지 않는다.

### 6.2 진행과 확인

| 확인 | 방법 | 기준 |
|---|---|---|
| 회차 순서와 폼 | 세 명이 차례로 순번을 받고 A1을 연다 | 순서가 ABC, BCA, CAB로 돌고, 한 사람의 A1·A2·B 폼이 모두 다르다 |
| 준비 전 문항 | 영상 일부만 넣고 낱말 층을 연다 | 영상 있는 문항만 나오고, 회차 행 `missing.media`가 나머지 수와 같다 |
| 시간 | 층마다 시작·끝 시각을 적는다 | 문장 40개 15~18분, 낱말 24개 약 5분, 무의미 낱말 16개 약 3분(design-simulation 5절). 소음 층까지 40분을 넘으면 소음 층을 A1·B에만 둘지 정한다 |
| 반응 시간·재생 | 내보내기 `battery[].closed/open` | `rt_ms ≤ rt_from_onset_ms`, `plays` 1~2 |
| 개방형 답 | 일부러 오타·띄어쓰기를 섞어 답한다 | `answer_text`가 친 그대로, `auto_phoneme_acc`와 음소 수가 채워진다. 200개를 P20(`typed-scoring-check.md`)에 넘긴다 |
| 렌더링 | 학교 기기(V20)에서 같은 층을 연다 | 회차 행 `render_log`의 `mean_late_ms`, `over20_rate`, 영상 층의 `video_drop_rate ≤ 0.05` |
| 학습 시행 | 1·2단계 레슨을 한 번씩 | 내보내기 `trial_log[]`에 `talker`, `rt_from_onset_ms`, `options`, `target`; 레슨 노력 문항 행에 `render_log` |
| 초기화 | 한 명이 학습 초기화 | P3 회차 기록이 남는다(`kept.p3_test_sessions`) |

### 6.3 끝난 뒤

- `GET /api/pilot/export?trials=true`(운영자 계정)로 받아 `log-spec-audit.md` 7절 목록을 확인하고, 빠진 값을 적는다.
- 리허설 자료로 design-simulation 2.3의 추측값(사전 평균, 문장 안 상관, 상태 잡음)을 다시 잡는다.
- 리허설 계정은 계정 삭제로 지운다(모든 P3 표가 함께 지워진다).

## 7. 결정할 것

1. 개방형 문장 120 + 예비 12 동결(지금 목록은 초안). 폼 C 낱말 24개와 무의미 낱말 폼 C 16개 검토.
2. 실제 얼굴 낱말이 아바타 표준검사(A·B 48낱말)와 같은 낱말이다. 같은 회차에 둘 다 볼지, 낱말을 나눌지(design-simulation 6절).
3. 소음 속 문장을 매 회차에 둘지(시간), 유지 검사(R)를 새 폼으로 할지(4폼이면 문장 160개 필요). 지금은 R = B와 같은 폼, 소음 층 없음.
4. 무의미 낱말을 실제 얼굴로도 낼지(지금은 아바타. 가1 첫째 층을 실제 얼굴로 하려면 48낱말 × 화자를 찍는다).
5. 동의서 5-3과 `pilot-data-spec.md` 3절에 검사 문항 답 원문을 넣는 문구.
6. P3 기간 파일럿 참여자의 학습 초기화(지금은 학습 시행 기록이 지워지고 검사 기록만 남는다, `log-spec-audit.md` 2절 5).
