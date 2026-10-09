# 쉬운 한국어 감사 기준 재설정안과 바꿀 UI 용어 후보 (C15 후속, 2026-10-09)

> 대상: C15 감사(`docs/easy-korean-audit.md`, 기준선 `docs/easy-korean-audit-baseline.json`, 스크립트 `scripts/easy_korean_audit.py`).
> 이 문서의 수치: `scripts/easy_korean_rebase.py`(감사 결과 JSON을 여러 기준으로 다시 센다), 낱말 결정표 `scripts/data/easy_korean_termbook.json`(10/9 확정, 예전 이름 `easy_korean_termbook_draft.json`).
> 1~6절은 10/9 오전의 제안이다. 사용자가 결정을 맡겨 같은 날 세 층 기준을 채택하고 용어 일부를 화면에 반영했다(7절).

## 1. 지금 숫자

| | 문자열 | 엄격 통과 | 통과율 |
|---|--:|--:|--:|
| 10/6 감사(고친 뒤) | 2,245 | 727 | 32.4% |
| 10/9 다시 셈(소리 듣기 트랙 화면이 더해짐) | 3,152 | 1,107 | 35.1% |

10/9 실행: `scripts/easy_korean_audit.py --json`(kiwipiepy는 `~/Downloads/KSC2026/.venv`의 것을 썼다). 실패 2,045개 가운데 어휘 실패 2,044, 길이 실패 57이다.
목표는 문자열의 95% 통과(계획 다7)다. 실패는 거의 모두 어휘 기준에서 나온다.

## 2. 기준이 화면 문자열의 성격에 맞는가

### 2.1 짧은 글에서는 비율 기준이 '어려운 말 0개'가 된다

기준은 '내용어 가운데 A·B 등급이 아닌 낱말 ≤ 10%'다. 내용어가 9개 이하인 문자열에서는 어려운 말 하나만 있어도 11~100%가 되어 실패한다.
문자열의 **90.0%**가 내용어 9개 이하다(1개 733, 2개 876, 3개 427, 4개 326). 버튼·탭·제목 같은 이름표(문장 하나, 종결 어미 없음, 내용어 4개 이하)는
1,816개(58%)다. 비율 기준은 원래 이어진 글의 어휘 덮기 비율에서 온 생각인데, 화면 문자열 대부분에서는 '모든 낱말이 A·B'라는 무관용 규칙으로 동작한다.
문자열을 따로 세므로 같은 화면의 글이 짧게 나뉠수록 엄격해지고, 같은 글이 여러 곳에 있으면 여러 번 센다(3,152개 중 서로 다른 글 2,359개).

### 2.2 C 등급은 '어려운 말'과 같지 않다

국립국어원 「한국어 학습용 어휘 목록」(2003)은 외국인 학습용 기본 어휘 5,965개를 가르치는 순서로 A(982)·B(2,111)·C(2,872)로 나눈 것이다.
C도 이 기본 어휘 안에 든다. C에는 답·낱말·짝·화면·목록·안내·기록·단계·올리다·잇다·익히다처럼 기초 고유어와 화면에 늘 나오는 말이 들어 있다.
대상 학습자(선천성·조기 청력 손실, 한국어가 제2언어이거나 읽기 수준이 낮을 수 있음)에게 C를 모두 어려운 말로 세면, 바꿀 수 없는 기초어까지 실패가 된다.

### 2.3 측정 오류

- 명사형 '-기'가 목록에 따로 없어 듣기(87)·말하기(39)·보기(26)·받아쓰기·읽기가 목록 밖으로 센다. 원형 동사는 A다.
- 형태소 분석이 북마크를 북+마크로(마크 28), 숙달도·취약도를 숙달·취약+도로 자른다.
- 이 둘만 고쳐도 35.1% → 38.4%다(화면 문구는 그대로).

### 2.4 바꿀 수 없는 말

- 앱이 가르치는 개념어: 입모양(212), 독화(64), 모음(47), 수어(45), 자음(29), 억양·음절·받침·첫소리·지문자·보청기·인공와우 등. 10/6 문서도 '기준을 맞추려고
  앱 용어를 억지로 풀어 쓰지 않는다'고 적었다. 이 말들은 바꾸는 대신 처음 나올 때 풀이를 보이는 것이 맞다.
- 법·연구 고지 용어: 처리·동의·약관·방침·위탁·가명·보호자·이용자. '진단'(14)은 '진단·치료하지 않아요'라는 필수 안내에 쓰여 빼면 안 된다.
- 목록(2003년)에 없는 일상 말·요즘 말: 맞히다·헷갈리다·되묻다·오므리다·높낮이·말소리·또박또박·이메일·비밀번호·휴대폰·이어폰 등.

## 3. 재설정안(세 층)

### 3.1 기준

| 층 | 대상 | 기준 | 목표 |
|---|---|---|---|
| 낱말 | 화면에 나오는 서로 다른 내용어 가운데 A·B·C가 아닌 것 | 낱말마다 결정 하나: 측정 오류 / 일상 말로 둠 / 고지 용어로 둠 / 앱 핵심 용어로 두고 처음 나올 때 풀이 / 바꿈 | 결정 안 된 낱말 0개 |
| 이름표 | 문장 하나, 종결 어미 없음, 내용어 4개 이하(버튼·탭·제목·짧은 표시) | 결정 안 된 낱말과 '바꿈' 낱말이 0개 | 95% |
| 문장형 | 나머지(안내·피드백·오류 문장) | 화면(파일) 단위 어휘 덮기 비율 ≥ 95%(쉬운 말 = A·B·C + 결정표에서 둔 말), 한 문장 30음절 이하 | 덮기 95%를 넘는 화면 90%, 30음절 이하 문장 95% |

- 덮기 95%는 제2언어 읽기 연구에서 글을 이해하는 최소 어휘 덮기 비율로 쓰는 값이다(Laufer 1989 95%, Hu와 Nation 2000은 98%). 화면 글에 같은 값이 맞는지는
  확인하지 않았다. C6 '쉬운 보기' 학습자에게 보이는 LLM 출력은 더 엄격한 98%와 A·B 기준을 따로 둔다.
- 지금의 엄격 통과율(A·B만, 문자열마다 10%)은 비교를 위해 계속 보고한다. 기준이 바뀌어도 숫자가 이어지게 하기 위해서다.
- 결정표는 낱말 하나에 한 번만 정하면 되므로, 화면이 늘어도 새로 나온 낱말만 보면 된다. 감사 스크립트는 '결정 안 된 낱말' 목록을 내고, 그 목록이
  비어 있지 않으면 실패로 본다.

### 3.2 같은 문자열을 여러 기준으로 다시 센 결과

결정표는 초안이다(측정 오류 11, 일상 말 81, 고지 용어 28, 앱 핵심 용어 33, 바꿀 후보 52). R은 지금처럼 문자열마다 10% 비율 기준이다.

| 기준 | 전체 | 서로 다른 글 | 이름표 | 문장형 |
|---|--:|--:|--:|--:|
| R0 지금 감사(A·B만) | 35.1% | 31.2% | 40.9% | 27.3% |
| R1 + 측정 오류 고침 | 38.4% | 34.1% | 45.5% | 28.7% |
| R2 + C 등급 허용 | 54.4% | 51.0% | 60.8% | 45.6% |
| R3 + 일상 말·고지 용어 | 59.4% | 56.9% | 64.4% | 52.7% |
| R4 + 앱 핵심 용어(풀이 조건) | 71.6% | 69.3% | 74.6% | 67.5% |
| R4 + 바꿀 후보 52개를 모두 바꿨다고 침 | 87.7% | 85.0% | 90.1% | 84.4% |

- 이름표 기준(어려운 말 0개)은 내용어 4개 이하에서 10% 비율 기준과 결과가 같다(2.1절). 그래서 유형을 나눠도 R4의 숫자는 같고, 차이는 문장형을 화면 단위
  덮기 비율로 볼 때 생긴다.
- 문장형 화면 단위 덮기 비율(R4): 전체 90.7%, 114개 파일 중 41개가 95% 이상. 바꿀 후보를 모두 바꿨다고 치면 95.9%, 84개 파일(74%)이 95% 이상.
- 문장형에서 30음절 이하 문장은 95.7%로 이미 목표를 넘는다.
- 바꿀 후보까지 반영해도 실패로 남는 문자열 388개 가운데 57개는 길이, 나머지는 결정 안 된 낱말(289종) 때문이다. 상위는 계정 27, 설정 18, 프로필 14,
  서버 13, dB 11, 합성 8, 브라우저 8, 투명 7, 오류 7, SNR 7, 구간 6, 참고 6이다. 계정·설정·프로필·브라우저·로그아웃은 일상 화면 말로 두는 것을,
  dB·SNR은 듣기 조건 화면의 전문 용어라 풀이를 붙이는 것을, '합성'은 합성 음성 표시(라이선스 조건)라 고지 용어로 두는 것을 제안한다.
- 따라서 재설정안의 목표(이름표 95%, 화면 덮기 95%)는 바꿀 후보를 상당수 받아들이고 결정 안 된 낱말을 분류해야 닿는다. 기준만 바꿔서는 닿지 않는다.

## 4. 바꿀 UI 용어 후보

'P에서 통과로 바뀜'은 R4 기준에서 그 낱말 하나만 쉬운 대안으로 바꿨다고 칠 때 통과로 바뀌는 문자열 수다. 바꾸면 뜻이 달라질 수 있는 것은 메모에 적었다.
대안의 등급은 국립국어원 목록 등급이다.

### 4.1 먼저 볼 것(효과가 크고 뜻 손실이 적다)

| 지금 말 | 대안 | 문자열 | 파일 | 통과로 바뀜 | 메모 |
|---|---|--:|--:|--:|---|
| 문항 | 문제(A) | 67 | 25 | 43 | 검사·레슨 개수 |
| 불러오다 | 가져오다(A), '여는 중' | 52 | 25 | 37 | 대부분 '불러오는 중…' 안내 |
| 화자 | 말하는 사람(A) | 30 | 7 | 26 | |
| 완료 | 끝(A), 다 했어요 | 31 | 21 | 24 | |
| 저장 | 남기기(B) | 35 | 17 | 21 | |
| 정확도 | 맞힌 비율 | 38 | 13 | 20 | |
| 건너뛰다 | 넘어가다(A) | 26 | 12 | 20 | |
| 항목 | 것, 줄(A) | 26 | 11 | 20 | |
| 오답 | 틀린 문제(A·B) | 22 | 13 | 18 | |
| 회차 | 번째, 차례 | 13 | 7 | 10 | |
| 실전 | 실제 대화 | 13 | 7 | 10 | |
| 예시 | 예(A), 보기 | 21 | 7 | 9 | 대부분 그림 대체 글 |
| 난이도 | 어려운 정도 | 11 | 6 | 6 | |
| 프레임 | 장면 | 7 | 3 | 5 | |
| 추이 | 변화(B) | 9 | 4 | 4 | |
| 곡선 | 선, 그래프 | 14 | 5 | 4 | |
| 획득·삭제·수치·생성·전송·누적·세션·데이터 | 받기·지우기·숫자·만들기·보내기·모두 합친·한 번 연습·기록 | 각 4~12 | | 각 1~3 | |

### 4.2 제품 개념이라 이름·규칙 문서와 함께 바꿔야 하는 것

| 지금 말 | 대안 | 문자열 | 파일 | 통과로 바뀜 | 메모 |
|---|---|--:|--:|--:|---|
| 숙달 | 다 익힘, 익숙해짐 | 46 | 13 | 30 | 단계 해금의 핵심 개념. 규칙 문서·분석 화면 이름이 함께 바뀐다 |
| 발화 | 말하기, 말한 것 | 32 | 15 | 25 | 트랙 이름에 '발화'와 '말하기'가 섞여 있어 하나로 맞출 필요가 있다 |
| 경로 | 길, 순서(A) | 29 | 16 | 22 | '학습 경로'(앱 홈 이름) |
| 유지 | 이어 가기, 남기 | 17 | 11 | 12 | '유지 검사'(파일럿) |
| 트랙 | 갈래, 과정 | 13 | 6 | 10 | 독화·발화·듣기 묶음 이름 |
| 레벨·XP·배지·해금 | 등급·점수·메달·열림 | 15·16·10·2 | | 8·4·4·1 | 게임 요소 이름 |
| 커리큘럼 | 학습 순서 | 9 | 9 | 7 | |
| 운율, 발성 | 크기·길이·높낮이, 소리 내기 | 7, 6 | | 7, 6 | 말하기 1·0단계 이름 |
| 단면 | 입 속 옆모습 | 12 | 7 | 6 | '성도 단면' |
| 추론, 골격 | 짐작, 뼈대 | 7, 4 | | 5, 4 | '문맥 추론', '자음 골격 힌트' |

### 4.3 연구 참여 화면에서는 남길 수 있는 것

파일럿(14, 대안 '시범 연구'), 사후(22, '끝난 뒤'), 시행(8, '번'), 자가(7, '스스로'), 리포트(10, '결과'), 공용(8, '같이 쓰는'). 동의서·검사 일정과 이어지는 말이라,
바꾸면 동의서 문구(`docs/pilot/`)와 맞춰야 한다.

### 4.4 재설정안에서는 바꾸지 않아도 되는 것(C 등급)

입력(35), 진행(22), 재생(18), 연속(16), 초기(15), 채점(14). 지금 기준(A·B만)을 유지하면 바꿀 후보가 되지만, C를 허용하면 대상이 아니다.

## 5. 사용자 결정

1. 기준: 지금 기준(A·B, 문자열마다 10%)을 유지할지, 3절의 세 층 기준으로 바꿀지. 바꾸면 C15 목표 문구(계획 다7)를 함께 고친다.
2. 결정표 초안(`scripts/data/easy_korean_termbook_draft.json`)의 갈래 확인. 특히 일상 말·앱 핵심 용어로 둔 말, 결정 안 된 낱말 상위(계정·설정·프로필·서버·dB·SNR·합성).
3. 바꿀 UI 용어(4.1~4.3) 가운데 무엇을 실제 화면에 반영할지. 반영하면 화면 문구, Figma, 사용 설명 문서, 파일럿 동의서 문구를 함께 고친다.
4. 앱 핵심 용어 풀이를 어디에 보일지(첫 등장 툴팁, 용어 풀이 카드 등). 재설정안은 풀이를 허용의 조건으로 둔다.

## 6. 한계

- 이름표·문장형 구분은 문장 수, 끝 글자, 내용어 수로 정한 어림 규칙이다. 그림 대체 글(alt)과 화면 읽기 프로그램용 이름도 이름표로 섞여 있다.
- 결정표는 이 작업에서 만든 초안이다. 당사자(수어·구어·인공와우 사용자)가 읽어 본 판정이 아니다. 다7의 셋째 기준(쉬운 보기 대화 100턴 표본)도 아직 하지 않았다.
- 형태소 분석(kiwipiepy)의 오류와 2003년 목록의 한계(요즘 말이 없음)는 그대로 남는다. 덮기 비율 95%는 제2언어 읽기 연구의 값을 옮긴 것이다.
- 재설정은 기준을 느슨하게 하는 방향이다. 기준을 바꾼 뒤의 통과율을 지금 통과율과 같은 뜻으로 읽으면 안 된다. 두 숫자를 나란히 보고한다.


## 7. 결정과 반영(2026-10-09 오후, 사용자 위임)

### 7.1 기준

- 감사 판정을 3절의 세 층 기준으로 바꾼다. `scripts/easy_korean_audit.py`의 요약에 `layers`(낱말·이름표·문장형)를 더했고, 계산은
  `scripts/easy_korean_rebase.py`의 `layers()`다. 예전 엄격 통과율(A·B만, 문자열마다 10%)은 숫자가 이어지도록 `pass_rate`로 계속 낸다.
- 목표: 결정 안 된 낱말 0개, 이름표 95%, 문장형 화면 덮기 95% 이상인 파일 90%, 30음절 이하 문장형 95%. 앱 핵심 용어(taught)는 처음 나올 때
  풀이가 있어야 쉬운 말로 친다는 조건을 유지한다(풀이 여부는 자동으로 재지 않는다).

### 7.2 낱말 결정표 확정

초안에서 결정 안 된 낱말 289종을 모두 갈래에 넣었다. 결과는 측정 오류 27, 일상 말 208, 고지 98, 앱 핵심 용어 62, 기술어 47, 바꿀 후보 53이다.

- **기초 IT·화면 말은 일상 말로 둔다**: 계정, 설정, 프로필, 브라우저, 로그아웃(분석기가 로그+아웃으로 자름), 권한, 네트워크, 캘린더, 드래그 등.
- **새 갈래 tech(기술어)**: 학습자에게 보이지 않아도 되는 말이라 쉬운 말로 치지 않고 바꾸거나 숨길 후보로 둔다. 서버, dB, SNR, Hz, 합성, 메모리,
  '95% 구간', 신뢰도, 융합, 불확실성, 이득과 API 오류 문장의 영어 낱말(confirm=true 등). 개인정보 안내의 '서버'·'메모리'는 처리 방식을 알리는
  고지라 지우지 않는다. '합성 음성' 표시는 라이선스 조건이라 지우지 않고 풀이를 붙일 후보다.
- **고지(notice)에 더한 것**: 개인정보 처리방침의 법 용어(도용·보증·시행일 등), 출처·라이선스 표기(CC BY, Wikimedia, Fly.io, Anthropic 등),
  교사·연구용 보고서 용어(판본, 선다형, 동형, 향상도, 전이).
- **앱 핵심 용어(taught)에 더한 것**: 조음 위치 이름(여린입천장·센입천장·목청·양순·연구개), 초성·중성, 원순, 비음, 공명, 기식, 역치, 수형·지화,
  혼동(혼동 지도). 트랙 이름 '발화'와 말하기 단계 이름 '발성'·'운율'은 소개서·커리큘럼과 맞추려고 바꿀 후보에서 빼고 이 갈래로 옮겼다.
  '숙달'도 바꾸지 않고 이 갈래로 옮겨 풀이를 붙였다(7.3절).

### 7.3 화면 문자열에 반영한 것

원칙: 뜻이 확실히 쉬워지고 기존 의미를 바꾸지 않는 것만 바꾼다. 트랙 이름(독화·발화·소리 듣기), 입모양, 단계 이름은 그대로다.
소리 듣기 화면(`components/listen/`, `pages/Listen*.jsx`, `lib/listen*.js`)은 다른 작업과 겹치지 않게 이번에 고치지 않고 7.5절 목록에만 둔다.
개인정보 처리방침(`Legal.jsx`), 연구 검사(`PilotBattery`), 다른 작업이 맡았던 `pages/Practice.jsx`도 그대로다.

| 말 | 바꾼 말 | 곳 | 그대로 둔 곳과 까닭 |
|---|---|--:|---|
| 문항 | 문제 | 29 | 사전·사후 검사 보고서(`EvalReport`), 연구 검사, 서버의 검사 오류 안내(검사 용어) |
| 불러오다 | 가져오다 | 43 | 소리 듣기 화면, `Practice.jsx` |
| 오답 | 틀린 문제(복습 개수·탭), 틀린 문장(문장 복습 목록), 틀린 답(설명), 틀림(결과 칸) | 19 | 코드 주석 |
| 추이 | 변화 | 9 | |
| 획득 | 받은, 받음, 받았어요 | 8 | |
| 데이터 | 기록 | 5 | '계정·데이터 삭제'(고지), 수어 자료 출처 |
| 전송·생성·누적 | 보내기, 만들지 못했어요, 모은·모두 합쳐 | 3·2·3 | 분석 상세의 '누적 성과' |
| 취약·근접·적정 | 약한, 비슷한(수어), 알맞은·알맞음 | 3·2·3 | |
| 합성(기술어) | '오디오 합성을 지원하지 않습니다' → '소리를 만들 수 없습니다' | 1 | 합성 음성 표시(라이선스) |
| 건너뛰기 링크 | 본문으로 바로 가기 | 1 | 단계 건너뛰기('여기로 건너뛸까요?')는 '넘어가다'로 바꾸면 '건너뛴다'는 뜻이 흐려져 그대로 |

합계 127쌍, 130곳, 48파일(전체 목록 7.6절). 그 밖에:

- **'숙달' 풀이**: 가이드의 '지금 내 상태' 카드에서 숙달 기준 바로 위에 "숙달: 다음 단계가 열릴 만큼 충분히 익혔다는 뜻이에요."를 보인다
  (`components/GuideModal.jsx`). 경로 화면의 '숙달'·'숙달 중' 표시에서 가이드 버튼으로 바로 닿는 자리다.
- 바꾸지 않은 바꿀 후보: 정확도('맞힌 비율'은 말하기 '발음 정확도'와 뜻이 다르다), 완료('끝'과 '다 했어요'가 섞여 이름표가 흔들린다), 저장·삭제·항목·회차·
  예시(맥락마다 대안이 달라 일괄로 바꾸면 뜻이 흐려진다), 화자(`lib/talkers.js`의 가상 화자 이름, 아바타 작업과 함께 볼 것), 경로·트랙·커리큘럼·레벨·XP
  (제품 이름, 4.2절). 이들은 결정표에 바꿀 후보로 남아 있다.
- 테스트 기대값 1곳(`lib/speakFeedback.test.mjs`, 적정선 → 알맞은 선)을 함께 고쳤다.

### 7.4 다시 잰 결과(10/9, 같은 결정표로 전후 비교)

| | 고치기 전 | 고친 뒤 | 목표 |
|---|--:|--:|--:|
| 문자열 | 3,152 | 3,154 | |
| 예전 엄격 통과율(A·B, 문자열마다 10%) | 35.1% | 36.3% | (참고) |
| 낱말: 결정 안 된 낱말 | 289종(초안) → 0종(확정) | 0종 | 0 |
| 이름표: 어려운 말 0개 | 84.1% | 86.2% | 95% |
| 문장형: 화면 덮기 95% 이상인 파일 | 54.4%(62/114) | 59.6%(68/114) | 90% |
| 문장형: 전체 덮기 | 94.5% | 95.3% | (참고) |
| 문장형: 30음절 이하 | 95.7% | 95.7% | 95% |

- '고치기 전'도 확정 결정표로 다시 센 값이다. 그래서 두 열의 차이는 화면 문자열을 바꾼 효과만이다. 결정표를 확정한 효과(초안 대비)는 낱말 층의 289 → 0이다.
- 세 층 가운데 낱말 층과 30음절 기준은 통과, 이름표와 화면 덮기는 미달이다. 이름표 실패 251개 가운데 68개가 이번에 손대지 않은 화면(소리 듣기·고지·연구)에
  있다. 남은 실패의 상위는 정확도 28, 완료 21, 문항 21(소리 듣기·검사 화면), 경로 19, XP 11, 항목 11, 레벨·커리큘럼·사후 각 8이다.
- 바꿀 후보를 모두 바꿨다고 치면(P+swap) 96.3%로, 기준만 바꿔서는 닿지 않고 제품 이름 결정(4.2절)이 남아 있다는 3.2절의 결론은 그대로다.

### 7.5 소리 듣기 화면에서 다음에 고칠 것(이번에는 목록만)

같은 결정표로 본 소리 듣기 화면의 어려운 말이다. 그 화면을 맡은 작업이 끝난 뒤 7.3절과 같은 원칙으로 고친다.

| 말 | 갈래 | 문자열 수 | 위치 |
|---|---|--:|---|
| 경로 → 길, 순서(A) | 바꿀 후보 | 23 | `listen/ConvoTask.jsx:22`, `listen/LingCheck.jsx:16`, `listen/NoiseTest.jsx:83`, `listen/NoiseTest.jsx:91`, `listen/NoiseTest.jsx:109`, `listen/NoiseTest.jsx:111` 외 |
| 문항 → 문제(A) | 바꿀 후보 | 21 | `listen/AxDrill.jsx:76`, `listen/ContrastRun.jsx:30`, `listen/ConvoTask.jsx:90`, `listen/ListenBlocks.jsx:54`, `listen/StateCard.jsx:22`, `listen/StateCard.jsx:24` 외 |
| 불러오다 → 가져오다(A), '여는 중' | 바꿀 후보 | 20 | `pages/ListenClassroom.jsx:183`, `pages/ListenClassroom.jsx:184`, `pages/ListenPractice.jsx:68`, `pages/ListenPractice.jsx:128`, `pages/ListenPractice.jsx:128`, `pages/ListenPractice.jsx:129` 외 |
| dB | 기술어 | 7 | `lib/listenMix.js:238`, `lib/listenMix.js:239`, `lib/listenReport.js:25`, `lib/listenReport.js:25`, `pages/ListeningReport.jsx:97`, `pages/ListeningReport.jsx:105` 외 |
| 저장 → 남기기(B) | 바꿀 후보 | 6 | `listen/LingCheck.jsx:48`, `listen/LingCheck.jsx:85`, `listen/LingCheck.jsx:85`, `listen/LingCheck.jsx:86`, `listen/ListenSetup.jsx:69`, `listen/ListenSetup.jsx:71` |
| 건너뛰다 → 넘어가다(A) | 바꿀 후보 | 5 | `listen/ListenBlocks.jsx:52`, `listen/NoiseTest.jsx:105`, `pages/ListenToday.jsx:36`, `pages/ListenToday.jsx:153`, `pages/ListeningPractice.jsx:52` |
| 예시 → 예(A), 보기 | 바꿀 후보 | 3 | `listen/ListenSetup.jsx:39`, `listen/ListenSetup.jsx:41`, `listen/ListenSetup.jsx:41` |
| 합성 | 기술어 | 3 | `listen/ListenSetup.jsx:41`, `listen/SoundCard.jsx:34`, `listen/ui.jsx:10` |
| 서버 | 기술어 | 3 | `listen/NoiseTest.jsx:108`, `listen/StateCard.jsx:22`, `listen/WordTest.jsx:74` |
| 이득 | 기술어 | 2 | `pages/ListeningReport.jsx:156`, `pages/ListeningReport.jsx:163` |
| 파일럿 → 시범 연구 | 바꿀 후보 | 1 | `listen/ListenSetup.jsx:63` |
| 정확도 → 맞힌 비율 | 바꿀 후보 | 1 | `listen/SentenceTask.jsx:161` |
| 오답 → 틀린 문제(A·B) | 바꿀 후보 | 1 | `listen/ui.jsx:75` |
| 회차 → 번째, 차례 | 바꿀 후보 | 1 | `pages/ListeningReport.jsx:114` |


### 7.6 바꾼 문자열 전체 목록

위치의 줄 번호는 바꾼 뒤 파일 기준이다. 경로는 `frontend/src/`를 뺐다.

| # | 갈래 | 위치 | 고치기 전 | 고친 뒤 |
|--:|---|---|---|---|
| 1 | 문항 | `components/GuideModal.jsx:75` | 수준이 분명해지면 5문항 만에도 끝나고, 길어도 12문항이에요. 문항마다 정답은 알려 주지 않아요. | 수준이 분명해지면 5문제 만에도 끝나고, 길어도 12문제예요. 문제마다 정답은 알려 주지 않아요. |
| 2 | 문항 | `components/GuideModal.jsx:82` | 숙달하면 직접 적는 문항도 나와요. | 숙달하면 직접 적는 문제도 나와요. |
| 3 | 문항 | `components/GuideModal.jsx:83` | 잘할수록 직접 적는 문항이 늘어요. | 잘할수록 직접 적는 문제가 늘어요. |
| 4 | 문항 | `components/GuideModal.jsx:123` | 2단계 레슨의 2문항과 문맥 추론은 | 2단계 레슨의 2문제와 문맥 추론은 |
| 5 | 문항 | `components/GuideModal.jsx:124` | 12문항을 마치면 정답률·XP·걸린 시간이 나와요. | 12문제를 마치면 정답률·XP·걸린 시간이 나와요. |
| 6 | 문항 | `components/GuideModal.jsx:128` | "12문항 중 4문항은 읽은 단어를 직접 적어요. | "12문제 중 4문제는 읽은 단어를 직접 적어요. |
| 7 | 문항 | `components/GuideModal.jsx:162` | 최근 통과율과 시도 수가 문항 아래에 보여요. | 최근 통과율과 시도 수가 문제 아래에 보여요. |
| 8 | 문항 | `components/GuideModal.jsx:163` | 약하게 나온 소리가 든 문항을 앞쪽에 섞어 내요. | 약하게 나온 소리가 든 문제를 앞쪽에 섞어 내요. |
| 9 | 문항 | `components/GuideModal.jsx:203` | 두 레슨이 12문항씩 번갈아 나와요. | 두 레슨이 12문제씩 번갈아 나와요. |
| 10 | 문항 | `components/GuideModal.jsx:209` | 가장 빠른 속도에서 최근 12문항 중 10개를 맞히면 | 가장 빠른 속도에서 최근 12문제 중 10개를 맞히면 |
| 11 | 문항 | `components/GuideModal.jsx:253` | 사전·사후 검사(각 24문항)는 난이도가 같아서 훈련 전과 후를 비교할 수 있어요. 사후 문항 절반은 | 사전·사후 검사(각 24문제)는 난이도가 같아서 훈련 전과 후를 비교할 수 있어요. 사후 문제 절반은 |
| 12 | 문항 | `components/RetentionPrompt.jsx:32` | 사후 검사와 같은 24문항, 5분 안팎이에요. | 사후 검사와 같은 24문제, 5분 안팎이에요. |
| 13 | 문항 | `components/MasteryProbeBlock.jsx:55` | 확인 문항 · 보통 빠르기, 도움 없이 | 확인 문제 · 보통 빠르기, 도움 없이 |
| 14 | 문항 | `components/guide/GuideMockups.jsx:920` | alt: '단어 독화 문항 예시. | alt: '단어 독화 문제 예시. |
| 15 | 문항 | `components/guide/GuideMockups.jsx:924` | alt: '발화 문항 예시. | alt: '발화 문제 예시. |
| 16 | 문항 | `lib/changeTone.js:6` | '문항이 적어 한 사람의 차이는 잡음이 커요. | '문제가 적어 한 사람의 차이는 잡음이 커요. |
| 17 | 문항 | `lib/talkers.js:15` | '문항 12개씩이라 한 사람 점수 차는 잡음이 커요. | '문제 12개씩이라 한 사람 점수 차는 잡음이 커요. |
| 18 | 문항 | `pages/WordStage.jsx:379` | 다음 속도: 지금 가장 빠른 속도에서 12문항 중 10개 | 다음 속도: 지금 가장 빠른 속도에서 12문제 중 10개 |
| 19 | 문항 | `pages/WordStage.jsx:433` | >문장으로 고르는 문항이에요< | >문장으로 고르는 문제예요< |
| 20 | 문항 | `pages/WordStage.jsx:435` | 이 문항은 단어 단계 숙달에는 들어가지 않아요. | 이 문제는 단어 단계 숙달에는 들어가지 않아요. |
| 21 | 문항·불러오다 | `pages/Placement.jsx:169` | message="문항을 불러오지 못했어요." | message="문제를 가져오지 못했어요." |
| 22 | 문항 | `pages/Placement.jsx:194` | {result.total}문항 정답<br /> | {result.total}문제 정답<br /> |
| 23 | 문항 | `pages/Placement.jsx:211` | 사전 검사(A)를 봐 두세요. 24문항, 5분 안팎이에요. | 사전 검사(A)를 봐 두세요. 24문제, 5분 안팎이에요. |
| 24 | 문항 | `pages/Placement.jsx:248` | 사후 검사와 같은 문항이라 기억 효과가 | 사후 검사와 같은 문제라 기억 효과가 |
| 25 | 문항 | `backend/main.py:4591` | out["note"] = "사후 검사와 같은 문항이라 기억 효과가 조금 섞일 수 있어요." | out["note"] = "사후 검사와 같은 문제라 기억 효과가 조금 섞일 수 있어요." |
| 26 | 문항 | `pages/AnalysisDetail.jsx:173` | description: `정확도 · ${read?.questions \|\| 0}문항` | description: `정확도 · ${read?.questions \|\| 0}문제` |
| 27 | 문항 | `pages/AnalysisTab.jsx:74` | note: '같다·다르다 문항' } | note: '같다·다르다 문제' } |
| 28 | 문항 | `pages/AnalysisTab.jsx:511` | {it.total}문항 중 {it.correct}문항 · Lv.{it.level} | {it.total}문제 중 {it.correct}문제 · Lv.{it.level} |
| 29 | 문항 | `pages/AnalysisTab.jsx:605` | label="이 회차 문항"> | label="이 회차 문제"> |
| 30 | 불러오다 | `components/ErrorScreen.jsx:62` | message = '불러오지 못했어요.' | message = '가져오지 못했어요.' |
| 31 | 불러오다 | `components/LipReadCheck.jsx:93` | '입모양 모델을 불러오지 못했어요. 다시 눌러 보세요.' | '입모양 모델을 가져오지 못했어요. 다시 눌러 보세요.' |
| 32 | 불러오다 | `components/LipReadCheck.jsx:158` | '모델 불러오는 중…' | '모델 가져오는 중…' |
| 33 | 불러오다 | `components/MouthCalibration.jsx:68` | '입모양 모델을 불러오지 못했어요. 네트워크를 확인해 주세요.' | '입모양 모델을 가져오지 못했어요. 네트워크를 확인해 주세요.' |
| 34 | 불러오다 | `components/VocalTractVTL.jsx:140` | 성도 단면을 불러오지 못했어요. | 성도 단면을 가져오지 못했어요. |
| 35 | 불러오다 | `components/WebcamMouthCheck.jsx:294` | '모델 불러오는 중…' | '모델 가져오는 중…' |
| 36 | 불러오다 | `components/MouthMirror.jsx:115` | '모델 불러오는 중…' | '모델 가져오는 중…' |
| 37 | 불러오다 | `components/SignPanel.jsx:237` | 입모양 불러오는 중… | 입모양 가져오는 중… |
| 38 | 불러오다 | `components/SignSelectionOverlay.jsx:113` | >불러오는 중…< | >가져오는 중…< |
| 39 | 불러오다 | `components/SoundReplayBar.jsx:11` | loading: '소리 불러오는 중', | loading: '소리 가져오는 중', |
| 40 | 불러오다 | `features/learn/shared/LessonList.jsx:43` | 진행도를 불러오지 못해 잠금 표시 없이 보여드려요. | 진행도를 가져오지 못해 잠금 표시 없이 보여드려요. |
| 41 | 불러오다 | `features/learn/shared/TrackHub.jsx:31,55` | '불러오는 중…' | '가져오는 중…' | (2곳)
| 42 | 불러오다 | `features/learn/shared/TrackHub.jsx:32` | '진행도를 불러오지 못했어요' | '진행도를 가져오지 못했어요' |
| 43 | 불러오다 | `features/dashboard/ReviewSection.jsx:61` | >불러오는 중...< | >가져오는 중...< |
| 44 | 불러오다 | `hooks/useFaceLandmarker.js:40` | '모델을 불러오지 못했어요. 네트워크를 확인해 주세요.' | '모델을 가져오지 못했어요. 네트워크를 확인해 주세요.' |
| 45 | 불러오다 | `layouts/AppLayout.jsx:16` | >불러오는 중…< | >가져오는 중…< |
| 46 | 불러오다 | `pages/AnalysisTab.jsx:569` | 기록을 불러오지 못했어요. | 기록을 가져오지 못했어요. |
| 47 | 불러오다 | `pages/AnalysisTab.jsx:571` | text-ink-muted">불러오는 중…</p> | text-ink-muted">가져오는 중…</p> |
| 48 | 불러오다 | `pages/Conversation.jsx:109` | '입모양을 불러오지 못했어요. 무슨 말인지 보기로 문장을 확인할 수 있어요.' | '입모양을 가져오지 못했어요. 무슨 말인지 보기로 문장을 확인할 수 있어요.' |
| 49 | 불러오다 | `pages/CurriculumPath.jsx:307` | 학습 경로를 불러오지 못했어요. | 학습 경로를 가져오지 못했어요. |
| 50 | 불러오다 | `pages/CurriculumPath.jsx:308` | className="btn-primary">다시 불러오기</button> | className="btn-primary">다시 가져오기</button> |
| 51 | 불러오다 | `pages/EvalReport.jsx:279` | 리포트를 불러오지 못했습니다. | 리포트를 가져오지 못했습니다. |
| 52 | 불러오다 | `pages/MultiConversation.jsx:182` | 대화를 불러오는 중… | 대화를 가져오는 중… |
| 53 | 불러오다 | `pages/MultiConversation.jsx:185` | >대화를 불러오지 못했어요.< | >대화를 가져오지 못했어요.< |
| 54 | 불러오다 | `pages/MultiConversation.jsx:186,212` | >다시 불러오기</button> | >다시 가져오기</button> | (2곳)
| 55 | 불러오다 | `pages/MultiConversation.jsx:211` | 새 대화를 불러오지 못했어요. | 새 대화를 가져오지 못했어요. |
| 56 | 불러오다 | `pages/NonsensePairing.jsx:159` | message="짝 맞추기를 불러오지 못했어요." | message="짝 맞추기를 가져오지 못했어요." |
| 57 | 불러오다 | `pages/SpeakingPractice.jsx:53` | '입모양 자료를 불러오지 못해 아바타가 움직이지 않아요. | '입모양 자료를 가져오지 못해 아바타가 움직이지 않아요. |
| 58 | 불러오다 | `pages/SpeakingPractice.jsx:250` | setErr('복습을 불러오지 못했어요.') | setErr('복습을 가져오지 못했어요.') |
| 59 | 불러오다 | `pages/SpeakingPractice.jsx:260` | setErr('단계를 불러오지 못했어요.') | setErr('단계를 가져오지 못했어요.') |
| 60 | 불러오다 | `pages/SpeakingPractice.jsx:269` | setErr('콘텐츠를 불러오지 못했어요.') | setErr('콘텐츠를 가져오지 못했어요.') |
| 61 | 불러오다 | `pages/SpeakingPractice.jsx:617` | text-ink">단계를 불러오지 못했어요</p> | text-ink">단계를 가져오지 못했어요</p> |
| 62 | 불러오다 | `pages/SpeakingPractice.jsx:620` | text-sm">다시 불러오기</button> | text-sm">다시 가져오기</button> |
| 63 | 불러오다 | `pages/SpeakingReviewLanding.jsx:58` | 복습 항목을 불러오지 못했어요 | 복습 항목을 가져오지 못했어요 |
| 64 | 불러오다 | `pages/SpeakingReviewLanding.jsx:60` | text-sm">다시 불러오기</button> | text-sm">다시 가져오기</button> |
| 65 | 불러오다 | `pages/VisemeLiteracy.jsx:180` | message="콘텐츠를 불러오지 못했어요." | message="콘텐츠를 가져오지 못했어요." |
| 66 | 불러오다 | `pages/VisemeLiteracy.jsx:272` | 카메라 모듈 불러오는 중… | 카메라 모듈 가져오는 중… |
| 67 | 불러오다 | `pages/VisemeLiteracy.jsx:628` | '입모양을 불러오는 중' | '입모양을 가져오는 중' |
| 68 | 불러오다 | `pages/WordStage.jsx:515` | text-ink-faint">불러오는 중…</div> | text-ink-faint">가져오는 중…</div> |
| 69 | 불러오다 | `pages/TasksPage.jsx:230` | 과제를 불러오는 중… | 과제를 가져오는 중… |
| 70 | 오답 | `components/AppShell.jsx:162` | <p className="text-[17px] text-ink">오답 <span | <p className="text-[17px] text-ink">틀린 문제 <span |
| 71 | 오답 | `components/guide/GuideMockups.jsx:347` | <p className="text-[17px] text-ink">오답 <span | <p className="text-[17px] text-ink">틀린 문제 <span |
| 72 | 오답 | `components/GuideModal.jsx:97` | 다시 풀 오답 수(틀린 문장·말하기 포함) | 다시 풀 틀린 문제 수(틀린 문장·말하기 포함) |
| 73 | 오답 | `components/GuideModal.jsx:230` | ['오답 복습', | ['틀린 문제 복습', |
| 74 | 오답 | `components/guide/GuideMockups.jsx:731` | title="복습할 오답 5개" sub="약 3분이면 끝나요" btn="오답 복습하기" | title="복습할 틀린 문제 5개" sub="약 3분이면 끝나요" btn="틀린 문제 복습하기" |
| 75 | 오답 | `components/guide/GuideMockups.jsx:745` | ['오답', 5] | ['틀린 문제', 5] |
| 76 | 오답 | `components/guide/GuideMockups.jsx:922` | alt: '단어 독화 오답 예시. | alt: '단어 독화에서 틀렸을 때의 예시. |
| 77 | 오답 | `components/guide/GuideMockups.jsx:932` | 오답·북마크 복습 카드와 | 틀린 문제·북마크 복습 카드와 |
| 78 | 오답 | `pages/ReviewTab.jsx:200` | { key: 'wrong', label: '오답', | { key: 'wrong', label: '틀린 문제', |
| 79 | 오답 | `pages/ReviewTab.jsx:256` | title="복습할 오답" sub="오답 다시보기" | title="복습할 틀린 문제" sub="틀린 문제 다시 보기" |
| 80 | 오답 | `pages/ReviewTab.jsx:257` | btn="오답 복습하기" | btn="틀린 문제 복습하기" |
| 81 | 오답 | `pages/ProfilePage.jsx:196` | `오답 ${n(lost?.wrong)}개 · 북마크 | `틀린 문제 ${n(lost?.wrong)}개 · 북마크 |
| 82 | 오답 | `pages/ReviewLanding.jsx:80` | text-red-700">오답 {String | text-red-700">틀린 문장 {String |
| 83 | 오답 | `pages/ReviewLanding.jsx:92` | 새로운 문장 학습을 완료하면 오답이 이곳에 모입니다. | 새로운 문장 학습을 완료하면 틀린 문장이 이곳에 모입니다. |
| 84 | 오답 | `pages/AnalysisTab.jsx:531` | homophene ? '입모양 맞음' : '오답'} | homophene ? '입모양 맞음' : '틀림'} |
| 85 | 오답 | `pages/MultiConversation.jsx:234` | result.closure_correct ? '정답' : '오답'} | result.closure_correct ? '정답' : '틀림'} |
| 86 | 오답 | `pages/AnalysisDetail.jsx:155` | >오답률 {item.error_rate}%< | >틀린 비율 {item.error_rate}%< |
| 87 | 오답 | `pages/WordStage.jsx:415` | 가를 수 없는 차이라 오답으로 보지 않고 | 가를 수 없는 차이라 틀린 답으로 보지 않고 |
| 88 | 오답 | `pages/EvalReport.jsx:459` | hint="오답 중 시각적으로 같은 입모양" | hint="틀린 답 중 시각적으로 같은 입모양" |
| 89 | 추이 | `components/GuideModal.jsx:244` | ['학습시간 추이', | ['학습 시간 변화', |
| 90 | 추이 | `components/GuideModal.jsx:245` | ['정확도 추이', | ['정확도 변화', |
| 91 | 추이 | `components/GuideModal.jsx:252` | 결과 보기를 누르면 검사 추이와 자주 헷갈린 소리를 | 결과 보기를 누르면 검사 결과의 변화와 자주 헷갈린 소리를 |
| 92 | 추이 | `components/guide/GuideMockups.jsx:816` | title="학습시간 추이" | title="학습 시간 변화" |
| 93 | 추이 | `components/guide/GuideMockups.jsx:835` | title="정확도 추이" | title="정확도 변화" |
| 94 | 추이 | `components/guide/GuideMockups.jsx:934` | 가운데에 학습시간과 정확도 추이 그래프. | 가운데에 학습 시간과 정확도 변화 그래프. |
| 95 | 추이 | `pages/AnalysisTab.jsx:261` | <ChartCard title="학습시간 추이"> | <ChartCard title="학습 시간 변화"> |
| 96 | 추이 | `pages/AnalysisTab.jsx:262` | <ChartCard title="정확도 추이"> | <ChartCard title="정확도 변화"> |
| 97 | 추이 | `pages/EvalReport.jsx:471` | title="문장 점수 추이" | title="문장 점수 변화" |
| 98 | 획득 | `components/LessonComplete.jsx:32` | >획득 XP< | >받은 XP< |
| 99 | 획득 | `features/learn/shared/LessonComplete.jsx:31` | ['획득 XP', | ['받은 XP', |
| 100 | 획득 | `pages/VisemeLiteracy.jsx:346` | >획득 XP< | >받은 XP< |
| 101 | 획득 | `pages/WordStage.jsx:75` | >획득 XP< | >받은 XP< |
| 102 | 획득 | `pages/AnalysisTab.jsx:639` | { label: '획득 배지', | { label: '받은 배지', |
| 103 | 획득 | `pages/TasksPage.jsx:143` | >가 획득했어요< | >가 받았어요< |
| 104 | 획득 | `pages/TasksPage.jsx:258` | {badges.length}개 획득</span> | {badges.length}개 받음</span> |
| 105 | 획득 | `components/guide/GuideMockups.jsx:685` | 4 / 12개 획득 | 4 / 12개 받음 |
| 106 | 전송 | `pages/Conversation.jsx:426` | 전송 | 보내기 |
| 107 | 전송 | `components/MouthMirror.jsx:103` | 영상은 기기 안에서만 처리 · 저장/전송 안 함 | 영상은 기기 안에서만 처리 · 저장하거나 보내지 않음 |
| 108 | 전송 | `components/WebcamMouthCheck.jsx:275` | 영상은 기기 안에서만 처리 · 저장/전송 안 함 | 영상은 기기 안에서만 처리 · 저장하거나 보내지 않음 |
| 109 | 생성 | `features/dashboard/Dashboard.jsx:174` | '시나리오 생성에 실패했습니다. 다시 시도해주세요.' | '시나리오를 만들지 못했습니다. 다시 시도해주세요.' |
| 110 | 생성 | `pages/FreeSpeak.jsx:55` | '입모양 생성에 실패했어요. 잠시 후 다시 시도해주세요.' | '입모양을 만들지 못했어요. 잠시 후 다시 시도해주세요.' |
| 111 | 누적 | `layouts/TopBar.jsx:20` | title="레벨 · 누적 경험치" | title="레벨 · 모은 경험치" |
| 112 | 누적 | `pages/ProfilePage.jsx:229` | label="누적 XP" | label="모은 XP" |
| 113 | 누적 | `lib/badges.js:12` | desc: '누적 100문제를 풀어내기' | desc: '모두 합쳐 100문제를 풀어내기' |
| 114 | 데이터 | `components/A11ySettings.jsx:127` | >내 데이터</p> | >내 기록</p> |
| 115 | 데이터 | `components/A11ySettings.jsx:130` | 내 학습 데이터 내려받기 <span | 내 학습 기록 내려받기 <span |
| 116 | 데이터 | `components/GuideModal.jsx:263` | 내 학습 데이터 내려받기도 여기 있어요. | 내 학습 기록 내려받기도 여기 있어요. |
| 117 | 데이터 | `pages/EvalReport.jsx:90` | <EmptyLine>데이터가 쌓이면 학습곡선이 표시됩니다.</EmptyLine> | <EmptyLine>기록이 쌓이면 학습곡선이 표시됩니다.</EmptyLine> |
| 118 | 데이터 | `pages/EvalReport.jsx:468` | <EmptyLine>혼동 데이터가 쌓이면 표시됩니다.</EmptyLine> | <EmptyLine>혼동 기록이 쌓이면 표시됩니다.</EmptyLine> |
| 119 | 취약 | `pages/AnalysisDetail.jsx:15` | visemes: { title: '취약 입모양', | visemes: { title: '약한 입모양', |
| 120 | 취약 | `pages/AnalysisDetail.jsx:24` | { mode: 'visemes', label: '취약 입모양' } | { mode: 'visemes', label: '약한 입모양' } |
| 121 | 취약 | `pages/AnalysisDetail.jsx:141` | 연습을 더 하면 입모양 유형별 취약도가 이곳에 표시됩니다. | 연습을 더 하면 입모양 유형별로 약한 정도가 이곳에 표시됩니다. |
| 122 | 근접 | `components/SignPanel.jsx:218,388` | ’은 사전에 없어 근접 수어 ‘{token.signed_as}’로 | ’은 사전에 없어 비슷한 수어 ‘{token.signed_as}’로 | (2곳)
| 123 | 적정 | `lib/speakFeedback.js:50` | '크기 곡선이 적정선 아래로 자주 내려갔어요 | '크기 곡선이 알맞은 선 아래로 자주 내려갔어요 |
| 124 | 적정 | `pages/SpeakingPractice.jsx:1059` | style={{ fill: 'var(--warn-strong)' }}>적정</text> | style={{ fill: 'var(--warn-strong)' }}>알맞음</text> |
| 125 | 적정 | `pages/SpeakingPractice.jsx:1076` | : '적정 크기'} | : '알맞은 크기'} |
| 126 | 합성 | `components/VocalTractSimulator.jsx:226` | 이 브라우저는 오디오 합성을 지원하지 않습니다. | 이 브라우저에서는 소리를 만들 수 없습니다. |
| 127 | 건너뛰다 | `App.jsx:188` | >본문으로 건너뛰기</a> | >본문으로 바로 가기</a> |

## 8. 2차 반영: 소리 듣기 화면과 제품 이름 일부(2026-10-09 밤)

### 8.1 원칙

7.3절과 같다. 뜻이 확실히 쉬워지고 기존 의미를 바꾸지 않는 것만 바꾼다. 트랙 이름(독화·발화·소리 듣기), 입모양, 단계 이름, 발성·운율은 그대로다.
개인정보 처리방침(`Legal.jsx`), 연구 검사(`PilotBattery`·`lib/pilotBattery.js`)와 서버의 연구 검사 안내, 다른 작업이 맡은 `pages/Practice.jsx`도 그대로다.
같은 시각 소리 듣기 검사 폼 데이터를 고치는 작업(`liplab-wt-forms`)과 겹치지 않게 이번에는 화면 문구만 고쳤다(서버 응답·자료는 손대지 않음).

기술어는 화면 종류로 나눴다.

- **연습 화면**(학습자가 문제를 푸는 동안 보는 글): 숨기거나 쉬운 말로 바꾼다. 소음 속 듣기의 크기 차이 안내(`listenMix.snrLabel`)는 dB 숫자를
  숨기고 '조금'(5 dB 이하)·'훨씬'(6 dB 이상)으로 말한다. 계단 흐름(`StairTrace`)도 같은 말을 쓰고, 계단 흐름이 보이는 연습에서는 문제 위
  안내 줄에서 같은 말을 한 번 뺐다. '서버에서'는 지웠다(소리를 아직 만들지 않았다는 뜻만 남김).
- **검사 결과**(소리 듣기 결과·검사 끝 화면·경로 카드의 역치): 역치 숫자와 단위 dB는 그대로 둔다. 결과 화면 설명의 첫 자리에 '말과 소음의
  크기 차이(dB)'로 쉬운 말과 괄호 원어를 붙였고, '입모양 이득'은 '입모양 도움'으로 쓰고 설명에 '(이득)'을 남겼다.
- **합성 음성 표시**(라이선스 조건): 지우지 않고 쉬운 말을 앞에 둔다. 소리 카드 '합성 음성' → '기계 목소리(합성)'.

### 8.2 제품 이름

| 말 | 결정 | 곳 | 까닭 |
|---|---|--:|---|
| 경로 | '학습 경로' → '학습 화면'(경로 화면을 가리키는 버튼·안내만) | 29 | 아래 탭 이름이 '학습'이고 그 탭이 경로 화면이라 같은 곳을 같은 말로 부른다. '학습 경로를 가져오지 못했어요'는 '학습 단계를', 가이드의 '트랙마다 경로와 진도'는 '단계와 진도', 그림 설명의 '학습 경로와 레슨 카드'는 '단계 목록과 레슨 카드' |
| 완료 | 동사와 끝 화면 제목만 '마치다'('레슨 완료!' → '레슨을 마쳤어요!', '완료하면' → '마치면', '먼저 완료해주세요' → '먼저 마쳐 주세요') | 18 | 앱이 이미 '검사를 마쳤어요'처럼 쓰는 말이다. 상태 표시 '완료'(경로 노드·레슨 목록)와 개수 표시('○ / ○ 완료')는 '끝'으로 바꾸면 길의 끝으로 읽힐 수 있고 '마침'은 부사와 헷갈려 그대로 |
| 정확도 | 소리 듣기 문장 끝 화면의 '낱말 정확도' → '맞힌 낱말 비율' 1곳만 | 1 | 첫 답에서 맞힌 낱말의 평균 비율이라 뜻이 정확히 같다. 독화 '정확도'(유형 보정 정답률)와 말하기 '발음 정확도'는 7.3절 까닭대로 그대로 |
| 회차 | 소리 듣기 결과 표 머리 '회차' → '차례' | 1 | 칸 값이 '처음·2번째'다. 분석 탭·프로필의 '학습 회차'(30분 공백으로 나눈 회차)는 정의가 따로 있어 그대로 |
| 파일럿 | 소리 듣기 설정의 연구용 안내 '예비 파일럿' → '예비 시범 연구' | 1 | 프로필·서버의 파일럿 참여 안내는 연구 동의 문서의 이름과 맞춰야 해 그대로 |
| 해금 | '대화 실전이 해금됩니다' → '열립니다' | 1 | '완료하면'을 고친 같은 문장 |
| XP·레벨·트랙·커리큘럼·저장·건너뛰다·예시 | 그대로 | | XP·레벨은 게임 보상 체계 이름이라 바꾸려면 보상 화면을 함께 정해야 한다. 트랙은 트랙 이름 규칙과 함께 볼 것. '저장 → 남기기'와 '예시 → 예·보기'는 소리 듣기 화면에서 뜻이 흐려지고('보기'는 답 고르기 보기와 겹침), 단계 '건너뛰기'는 7.3절과 같은 까닭 |

### 8.3 소리 듣기 화면에 반영한 것

7.5절 목록 가운데 바꾼 것: 문항 → 문제 22곳, 불러오다 → 가져오다 23곳, 경로(학습 화면) 23곳, 서버 숨김 3곳, dB 연습 화면 숨김 3곳과 결과 설명 1곳,
합성 2곳, 이득 2곳, 파일럿·정확도·회차·오답 각 1곳(문항과 서버를 함께 고친 곳이 하나라 소리 듣기 화면은 모두 82곳이다). 그대로 둔 것은 저장 6, 건너뛰다 5, dB(검사 결과) 5, 예시 3, 합성(이미 풀이가 붙은 안내 등) 2,
이득(설명의 괄호 원어) 1이다.

### 8.4 다시 측정한 결과(같은 결정표로 전후 비교)

결정표에는 '시범'(시범 연구)을 일상 말로 더했다. 두 열 모두 이 결정표로 센 값이다.

| | 고치기 전(7절 반영 뒤) | 고친 뒤 | 목표 |
|---|--:|--:|--:|
| 문자열 | 3,159 | 3,161 | |
| 예전 엄격 통과율(A·B, 문자열마다 10%) | 36.3% | 37.4% | (참고) |
| 낱말: 결정 안 된 낱말 | 0종 | 0종 | 0 |
| 이름표: 어려운 말 0개 | 86.2% | 89.1% | 95% |
| 문장형: 화면 덮기 95% 이상인 파일 | 59.6%(68/114) | 67.0%(77/115) | 90% |
| 문장형: 전체 덮기 | 95.3% | 95.7% | (참고) |
| 문장형: 30음절 이하 | 95.7% | 95.7% | 95% |
| 소리 듣기 화면만(24파일): 이름표 | 86.1% | 98.3% | |
| 소리 듣기 화면만: 덮기 95% 이상인 파일 | 62.5%(15/24) | 83.3%(20/24) | |

- 첫 열은 7.4절 '고친 뒤'와 같은 값이다(문자열이 그 뒤 다른 작업으로 5개 늘었다).
- 세 층 가운데 낱말 층과 30음절 기준은 통과, 이름표와 화면 덮기는 여전히 미달이다. 이름표 실패는 251 → 198개이고, 남은 상위는 정확도 27,
  완료 13(상태·개수 표시), XP 11, 항목 10, 레벨·커리큘럼·사후 각 8, 트랙 7이다. 남은 몫의 대부분은 8.2절에서 그대로 두기로 한 제품 이름이다.

### 8.5 바꾼 문자열 전체 목록

위치의 줄 번호는 바꾼 뒤 파일 기준이고 경로는 `frontend/src/`를 뺐다. 92쌍 106곳, 42파일이다(테스트 기대값 `lib/listenFlow.test.mjs` 2곳,
`lib/listenMix.test.mjs`의 snrLabel 검사, `features/learn/shared/trackProgress.test.mjs` 2곳을 함께 고쳤다).

| # | 갈래 | 위치 | 고치기 전 | 고친 뒤 |
|--:|---|---|---|---|
| 1 | 문항 | `components/listen/ContrastRun.jsx:30` | ${n}문항 중 ${c}문항(정답률 아래 줄) | ${n}문제 중 ${c}문제 |
| 2 | 문항 | `components/listen/AxDrill.jsx:76` | ${n}문항 중 ${c}문항(정답률 아래 줄) | ${n}문제 중 ${c}문제 |
| 3 | 문항 | `components/listen/ConvoTask.jsx:90` | ${n}문항 중 ${c}문항(정답률 아래 줄) | ${n}문제 중 ${c}문제 |
| 4 | 문항 | `components/listen/WordId.jsx:74` | ${n}문항 중 ${c}문항(정답률 아래 줄) | ${n}문제 중 ${c}문제 |
| 5 | 문항 | `components/listen/ListenBlocks.jsx:54` | `${r.n}문항 중 ${r.c}문항 · | `${r.n}문제 중 ${r.c}문제 · |
| 6 | 문항·서버 | `components/listen/StateCard.jsx:22` | '이 소리는 서버에서 아직 만들지 않았어요. 이 문항은 세지 않고 넘어가요.' | '이 소리는 아직 만들지 않았어요. 이 문제는 세지 않고 넘어가요.' |
| 7 | 문항 | `components/listen/StateCard.jsx:24` | 다른 브라우저로 열거나 이 문항은 세지 않고 | 다른 브라우저로 열거나 이 문제는 세지 않고 |
| 8 | 문항 | `components/listen/StateCard.jsx:30` | 다시 받아 보거나, 이 문항은 세지 않고 | 다시 받아 보거나, 이 문제는 세지 않고 |
| 9 | 문항 | `components/listen/StateCard.jsx:31` | '이 문항 넘기기' | '이 문제 넘기기' |
| 10 | 문항 | `lib/listenFlow.js:13` | ${n}문항은 세지 않고 넘겼어요. | ${n}문제는 세지 않고 넘겼어요. |
| 11 | 문항 | `lib/listenReport.js:85` | unit: useMin ? '분' : '문항' | unit: useMin ? '분' : '문제' |
| 12 | 문항 | `pages/ListenPractice.jsx:95` | {p.n}문항</span> | {p.n}문제</span> |
| 13 | 문항 | `pages/ListenPractice.jsx:157` | `지금까지 ${doneN}문항` | `지금까지 ${doneN}문제` |
| 14 | 문항 | `pages/ListenPractice.jsx:174` | "지금 낼 문항이 없어요" | "지금 낼 문제가 없어요" |
| 15 | 문항 | `pages/ListenPractice.jsx:241` | { label: '푼 문항', value: `${tally.n}문항` | { label: '푼 문제', value: `${tally.n}문제` |
| 16 | 문항 | `pages/ListenToday.jsx:143` | { label: '푼 문항', value: `${t.n}문항` } | { label: '푼 문제', value: `${t.n}문제` } |
| 17 | 문항 | `pages/ListeningReport.jsx:248` | 막대는 날마다 푼 문항 수예요. | 막대는 날마다 푼 문제 수예요. |
| 18 | 문항 | `pages/ListeningReport.jsx:253` | `약 ${week.totalMin}분 · ${week.total}문항` : `${week.total}문항` | `약 ${week.totalMin}분 · ${week.total}문제` : `${week.total}문제` |
| 19 | 불러오다 | `pages/ListenPractice.jsx:68` | '종류 목록을 불러오지 못했어요.' | '종류 목록을 가져오지 못했어요.' |
| 20 | 불러오다 | `pages/ListenPractice.jsx:128` | title="연습을 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러와 주세요." | title="연습을 가져오지 못했어요" body="인터넷 연결을 확인하고 다시 가져와 주세요." |
| 21 | 불러오다 | `pages/ListenPractice.jsx:129` | label: '다시 불러오기' | label: '다시 가져오기' |
| 22 | 불러오다 | `pages/ListenClassroom.jsx:182` | '소리 짝을 불러오지 못했어요' | '소리 짝을 가져오지 못했어요' |
| 23 | 불러오다 | `pages/ListenClassroom.jsx:183` | '인터넷 연결을 확인하고 다시 불러와 주세요.' | '인터넷 연결을 확인하고 다시 가져와 주세요.' |
| 24 | 불러오다 | `pages/ListenClassroom.jsx:184` | label: '다시 불러오기' | label: '다시 가져오기' |
| 25 | 불러오다 | `pages/ListenReview.jsx:47` | '복습할 소리를 불러오지 못했어요' | '복습할 소리를 가져오지 못했어요' |
| 26 | 불러오다 | `pages/ListenReview.jsx:48` | 다시 불러와 주세요. | 다시 가져와 주세요. |
| 27 | 불러오다 | `pages/ListenReview.jsx:49` | label: '다시 불러오기' | label: '다시 가져오기' |
| 28 | 불러오다 | `pages/ListenToday.jsx:36` | title="이 연습을 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러오거나, 이 연습은 건너뛰어요." | title="이 연습을 가져오지 못했어요" body="인터넷 연결을 확인하고 다시 가져오거나, 이 연습은 건너뛰어요." |
| 29 | 불러오다 | `pages/ListenToday.jsx:37,128` | label: '다시 불러오기' | label: '다시 가져오기' (2곳) |
| 30 | 불러오다 | `pages/ListenToday.jsx:126` | '오늘의 계획을 불러오지 못했어요' | '오늘의 계획을 가져오지 못했어요' |
| 31 | 불러오다 | `pages/ListenToday.jsx:127` | '인터넷 연결을 확인하고 다시 불러와 주세요.' | '인터넷 연결을 확인하고 다시 가져와 주세요.' |
| 32 | 불러오다 | `pages/ListeningPractice.jsx:47` | title="단계를 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러와 주세요." | title="단계를 가져오지 못했어요" body="인터넷 연결을 확인하고 다시 가져와 주세요." |
| 33 | 불러오다 | `pages/ListeningPractice.jsx:48` | label: '다시 불러오기' | label: '다시 가져오기' |
| 34 | 불러오다 | `pages/ListeningReport.jsx:90` | "결과를 불러오지 못했어요" | "결과를 가져오지 못했어요" |
| 35 | 불러오다 | `pages/ListeningReport.jsx:91` | 다시 불러와 주세요. | 다시 가져와 주세요. |
| 36 | 불러오다 | `pages/ListeningReport.jsx:92` | >다시 불러오기</button> | >다시 가져오기</button> |
| 37 | 불러오다 | `pages/ListeningReport.jsx:54` | aria-label="불러오는 중" | aria-label="가져오는 중" |
| 38 | 불러오다 | `pages/ListeningReport.jsx:56` | >불러오는 중이에요< | >가져오는 중이에요< |
| 39 | 불러오다 | `components/listen/ui.jsx:98` | aria-label="불러오는 중" | aria-label="가져오는 중" |
| 40 | 불러오다 | `components/listen/ui.jsx:104` | >불러오는 중이에요< | >가져오는 중이에요< |
| 41 | 오답 | `components/listen/ui.jsx:75` | wrong: ', 고른 답, 오답' | wrong: ', 고른 답, 틀린 답' |
| 42 | 서버 | `components/listen/NoiseTest.jsx:108` | body="서버에서 검사 문장 소리를 만드는 중이라 | body="검사 문장 소리를 아직 만드는 중이라 |
| 43 | 서버 | `components/listen/WordTest.jsx:74` | body="서버에서 검사 낱말 소리를 만드는 중이라 | body="검사 낱말 소리를 아직 만드는 중이라 |
| 44 | 합성 | `components/listen/SoundCard.jsx:35` | ''}합성 음성<span | ''}기계 목소리(합성)<span |
| 45 | 합성 | `components/listen/ListenSetup.jsx:41` | '예시 소리 듣기(합성 모음)' | '예시 소리 듣기(기계로 만든 모음)' |
| 46 | 파일럿 | `components/listen/ListenSetup.jsx:64` | 예비 파일럿에서만 켜요. | 예비 시범 연구에서만 켜요. |
| 47 | 정확도 | `components/listen/SentenceTask.jsx:161` | { label: '낱말 정확도', value: avgWords, note: '첫 답 평균' } | { label: '맞힌 낱말 비율', value: avgWords, note: '첫 답 평균' } |
| 48 | 회차 | `pages/ListeningReport.jsx:114` | font-bold">회차</th> | font-bold">차례</th> |
| 49 | 이득 | `pages/ListeningReport.jsx:156` | 입모양 이득은 두 역치의 차이예요. | 입모양 도움(이득)은 두 역치의 차이예요. |
| 50 | 이득 | `pages/ListeningReport.jsx:163` | label="입모양 이득" | label="입모양 도움" |
| 51 | dB | `pages/ListeningReport.jsx:97` | '말과 소음의 크기 차이'예요. 낮을수록 시끄러운 곳에서 잘 알아들어요. 두 검사 사이 ${MDC_DB} dB 안쪽의 차이는 측정 오차일 수 있어요. | '말과 소음의 크기 차이(dB)'예요. 낮을수록 시끄러운 곳에서 잘 알아들어요. 두 검사의 차이가 ${MDC_DB} dB보다 작으면 측정 오차일 수 있어요. |
| 52 | 경로 | `components/listen/NoiseTest.jsx:83,91,109,111` | label: '학습 경로로' | label: '학습 화면으로' (4곳) |
| 53 | 경로 | `components/listen/WordTest.jsx:63,67,75,77` | label: '학습 경로로' | label: '학습 화면으로' (4곳) |
| 54 | 경로 | `pages/ListeningPractice.jsx:48,53,55` | label: '학습 경로로' | label: '학습 화면으로' (3곳) |
| 55 | 경로 | `components/listen/LingCheck.jsx:16` | exitLabel = '학습 경로로' | exitLabel = '학습 화면으로' |
| 56 | 경로 | `components/listen/ConvoTask.jsx:22` | exitLabel = '학습 경로로' | exitLabel = '학습 화면으로' |
| 57 | 경로 | `components/listen/SentenceTask.jsx:27` | exitLabel = '학습 경로로' | exitLabel = '학습 화면으로' |
| 58 | 경로 | `lib/listenFlow.js:19` | exitLabel = '학습 경로로' | exitLabel = '학습 화면으로' |
| 59 | 경로 | `components/listen/StateCard.jsx:35` | exitLabel = '학습 경로로' | exitLabel = '학습 화면으로' |
| 60 | 경로 | `pages/ListeningPractice.jsx:44` | exitAria="나가기, 학습 경로로" | exitAria="나가기, 학습 화면으로" |
| 61 | 경로 | `pages/ListeningPractice.jsx:52` | 학습 경로에서 바로 앞 단계를 | 학습 화면에서 바로 앞 단계를 |
| 62 | 경로 | `pages/ListenPractice.jsx:126` | 지금은 학습 경로의 소리 듣기 단계로 | 지금은 학습 화면의 소리 듣기 단계로 |
| 63 | 경로 | `pages/ListenClassroom.jsx:183` | 지금은 학습 경로의 소리 구별 단계로 | 지금은 학습 화면의 소리 구별 단계로 |
| 64 | 경로 | `pages/ListenToday.jsx:42` | body="학습 경로에서 앞 단계를 마치면 열려요." | body="학습 화면에서 앞 단계를 마치면 열려요." |
| 65 | 경로 | `pages/ListenToday.jsx:127` | 지금은 학습 경로에서 단계를 하나씩 | 지금은 학습 화면에서 단계를 하나씩 |
| 66 | 경로 | `pages/ListenToday.jsx:130` | body="학습 경로에서 소리 듣기 단계를 열면 | body="학습 화면에서 소리 듣기 단계를 열면 |
| 67 | 경로 | `pages/Placement.jsx:251` | >학습 경로로</button> | >학습 화면으로</button> |
| 68 | 경로 | `pages/NonsensePairing.jsx:183` | >학습 경로로</button> | >학습 화면으로</button> |
| 69 | 경로 | `pages/CurriculumPath.jsx:307` | 학습 경로를 가져오지 못했어요. | 학습 단계를 가져오지 못했어요. |
| 70 | 경로 | `components/GuideModal.jsx:110` | 트랙마다 경로와 진도가 따로 저장돼요. | 트랙마다 단계와 진도가 따로 저장돼요. |
| 71 | 경로 | `components/GuideModal.jsx:382` | 경로에서 건너뛸 수도 있어요. | 학습 화면에서 건너뛸 수도 있어요. |
| 72 | 경로 | `components/guide/GuideMockups.jsx:916` | 가운데 학습 경로와 레슨 카드 | 가운데 단계 목록과 레슨 카드 |
| 73 | 완료 | `components/LessonComplete.jsx:24` | >레슨 완료!</h1> | >레슨을 마쳤어요!</h1> |
| 74 | 완료 | `features/learn/shared/LessonComplete.jsx:39` | >레슨 완료!</h1> | >레슨을 마쳤어요!</h1> |
| 75 | 완료 | `pages/VisemeLiteracy.jsx:338` | >레슨 완료!</h1> | >레슨을 마쳤어요!</h1> |
| 76 | 완료 | `pages/WordStage.jsx:67` | >레슨 완료!</h1> | >레슨을 마쳤어요!</h1> |
| 77 | 완료 | `components/MouthCalibration.jsx:149` | >본뜨기 완료!</div> | >본뜨기를 마쳤어요!</div> |
| 78 | 완료 | `pages/Conversation.jsx:444` | text-ink">대화 완료</h2> | text-ink">대화를 마쳤어요</h2> |
| 79 | 완료 | `pages/Conversation.jsx:451` | 번의 대화를 완료했습니다! | 번의 대화를 마쳤습니다! |
| 80 | 완료·해금 | `features/dashboard/Dashboard.jsx:52` | '3단계 문장 독화를 완료하면 대화 실전이 해금됩니다.' | '3단계 문장 독화를 마치면 대화 실전이 열립니다.' |
| 81 | 완료 | `features/dashboard/Dashboard.jsx:157` | 2단계(음절·단어)를 먼저 완료해주세요. | 2단계(음절·단어)를 먼저 마쳐 주세요. |
| 82 | 완료 | `features/dashboard/LearnerProfileCard.jsx:48` | '첫 학습을 완료했어요' | '첫 학습을 마쳤어요' |
| 83 | 완료 | `features/learn/shared/trackProgress.js:53` | 를 먼저 완료해주세요.` | 를 먼저 마쳐 주세요.` |
| 84 | 완료 | `features/learn/shared/trackProgress.js:54` | '직전 단계를 먼저 완료해주세요.' | '직전 단계를 먼저 마쳐 주세요.' |
| 85 | 완료 | `lib/badges.js:17` | '새벽 시간에 학습을 완료하기' | '새벽 시간에 학습을 마치기' |
| 86 | 완료 | `pages/ReviewLanding.jsx:92` | 새로운 문장 학습을 완료하면 | 새로운 문장 학습을 마치면 |
| 87 | 완료 | `pages/ScenarioHub.jsx:23` | '단어 학습을 완료하면 문장 학습이 열려요.' | '단어 학습을 마치면 문장 학습이 열려요.' |
| 88 | 완료 | `pages/ScenarioHub.jsx:23` | '문장 학습을 완료하면 대화 실전이 열려요.' | '문장 학습을 마치면 대화 실전이 열려요.' |
| 89 | 완료 | `pages/SpeakingReviewLanding.jsx:101` | 새로운 말하기 학습을 완료하면 | 새로운 말하기 학습을 마치면 |
| 90 | 완료 | `pages/AnalysisDetail.jsx:97` | description="기간 내 완료한 학습 항목" | description="기간 안에 마친 학습 항목" |
| 91 | dB(숨김) | `lib/listenMix.js:243` | 말이 소음보다 ${v} dB 커요 / 소음이 말보다 ${-v} dB 커요 | 말이 소음보다 조금·훨씬 커요 / 소음이 말보다 조금·훨씬 커요(5 dB 이하 조금, 6 dB 이상 훨씬) |
| 92 | dB(숨김) | `components/listen/StairTrace.jsx:16` | 지금 소음 차이 {fmtDb(now)} | 지금은 {snrLabel(now)} |
