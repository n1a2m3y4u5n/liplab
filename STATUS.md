# 지금 상태 — 다시 들어왔을 때 여기부터

> **2026-09-24 오전 — GPU 세션 2~5 결과와 결정할 것.**
> - **D-GOP 정렬 결함 수정(4c65e30)과 재측정.** kresnik CTC blank(`[PAD]`) 대신 id 0 음절을 blank로 쓰던 결함을 고치자 538 원점수
>   원본 80.2·경 49.6·중 26.7·심 5.8, 강도 순서 95.7%, 전사 정확도와 0.986. 지금 앵커로도 정상 발화 91점(A-7 문제의 원인이 결함).
> - **융합 검증(B-5·B-6·K-5): 판별력 저하.** 웹캠 입모양 점수(규칙 코사인)가 문장을 가르지 못해(AUC 0.49~0.53) 섞으면 AUC가
>   낮아진다(심 0.778 → 0.583). 비음 보조 효과 0. **결정 필요:** D-GOP를 켤 때 점수는 소리만, 입모양은 따로 보일지(`docs/bfuse-validation.md`).
> - **A2:** 제품 A4 처음 보는 10화자 r 0.627(합성 심 교란에 약함). **D v2:** D6 18.6%(사전 기준 통과), **D-7** 3D-CNN 7.6%(부정 결과),
>   **D-6** 동구형이음 쌍 혼동 25배. **C30:** 공개 자원 1.3.0.
> - **608:** 네 번 받았으나 0개(1차 고른 세션이 TS02에 없음, 2차 범주 28 wav가 deflate라 건너뜀, 3·4차 연결 끊김, 4차는 42GB에서).
>   풀기는 고쳤고(`aihub608.py stream --pick-cat 28`), 약 3시간을 끊김 없이 받아야 한다. **결정 필요:** 밤에 다시 받을지, 그림 8·A-2를 빼고 갈지.
> - **조음 역추정 mm 오차(4.2-13, 세션 5):** 처음 듣는 화자 RMSE 2.11mm, 평균 자세 기준선 2.41mm(오차 12% 감소), r 0.41.
>   복원 스크립트가 원래 r 0.448을 거의 재현했다. RunPod 잔액 $19.35, 파드 없음.

> **2026-09-24 새벽 — 축별 평가에서 빠진 것 구현(원격 푸시됨).** 축별 평가(A 중하, B 중, C 중, D 중상, E 중, F 중,
> G 상, H 상, I 중상, J 상, K 중)에서 코드로 채울 수 있는 것을 넣었다.
> - A-9 공용 음성 백본 서비스(`backend/backbone_service.py`, `GET /api/backbone/status`). '모델 하나' 대신 적재·캐시 지점 하나.
> - B-5·B-6 음소별 융합(소리 점수가 낮을수록 영상 가중↑, 음소 시간 구간의 웹캠 입모양), K-5 비음 확률 보조(±8점, ㅁ/ㅂ·ㄴ/ㄷ·ㅇ/ㄱ만).
>   셋 다 D-GOP 경로가 켜질 때만 동작한다. 실데이터 검증은 세션 3(`liplab-lab/tools/bfuse_validate.py`).
> - C-4 데이터 공간 난이도·최소대립쌍(`docs/c4-data-derived.md`, 규칙판 유지), C-8 공개 배포 묶음(`scripts/build_resource_release.py`,
>   AI Hub 유래 값은 서버·묶음 모두 기본 제외).
> - H-6 다자 대화 화자별 얼굴(`faces.json`, 자산은 사용자), I-9 교사용 인쇄 결과지, Figma 시나리오 화면(225:183·407:140).
> - 파일럿 전 결함 수정: 배치검사 문항 노출, 초기화가 사전검사를 지우던 것, 역균형 비교, 내보내기 2판(문항 기록·참여 뒤 집계·
>   현지 날짜), 가명 비밀키 분리(`LIPLAB_PILOT_SECRET`), 운영자 가명 찾기, 파기 도구를 이미지에, 기호 켬·끔 집단(J-12).
>   파일럿 문서 초안 7종 `docs/pilot/`.
> - 보안: 운영 npm 의존성 7건 수정(잠금 파일만), 남은 2건과 파이썬 점검 결과는 `DEPLOY.md` 5항.
> - 회귀 수정: B-6 시각 계산이 파형 없는 호출에서 멈추던 것. 확인: 백엔드 pytest 239 통과, 프론트 node --test 49, vite build 통과.
> 진행 중: GPU 세션 2(A2·D v2 끝, C30·608·kNN-VC 남음), 608 감음신경성 흘려받기, 세션 2가 끝나면 자동으로 세션 3
> (`liplab-lab/tools/pod/session3.sh`: D-7 입술 영역 3D-CNN, 4.2-13 조음 역추정 mm 오차, 융합 검증).
> 사용자 몫: CC5 얼굴 2~3개(H-6), 파일럿 윤리·보관·보호책임자, 공개 채널·저자 정보(C-8), `jamo_visual_similarity_data` 재배포 확인.

> **2026-09-24 새벽 — GPU 세션 2 보류(AI Hub 국외 반출 조항).** AI Hub 이용정책은 "AI데이터 등의 국외 반출"에
> 수행기관·NIA와의 별도 합의를 요구한다. RunPod은 한국 데이터센터가 없어 AI Hub 원자료(538 영상·음성, 608 음성)를 파드에
> 올리는 것이 여기에 걸릴 소지가 있다. 세션 2는 클립을 올리기 전에 멈추고 파드를 지웠다. AI Hub에 문의한 뒤
> (초안 `liplab-lab/notes/aihub_inquiry_2026-09-24.md`) 해외 파드를 쓸지, 국내 리전 GPU(엘리스클라우드·네이버 클라우드 등)로
> 옮길지 정한다. 그때까지 AI Hub 원자료는 해외 서버에 올리지 않는다. 608 TS02는 노트북으로 흘려받는 중(범위 요청 불가).
> **→ 9/24 새벽 재개:** 사용자가 관계자와 확인해 해외 파드 처리가 가능하다고 해 세션 2를 다시 띄웠다(워치독 600분).

> **2026-09-23 늦은 밤 — 계획서 재대조로 찾은 항목 처리(원격 푸시됨).**
> 표6-C1 데이터 유래 자모 유사도 교체(공개 자원 1.2.0), 4.4-4 검수 기록·병합 재게이트(`scripts/merge_approved.py`),
> 4.7 파일럿 데이터 명세와 보관·파기 스크립트(`docs/pilot-data-spec.md`, `scripts/pilot_retention.py`), G-6 엔드리스 혼합 세션
> (단어 ↔ 문맥), C-현황 엔진 지속시간 실측 비교(`docs/engine-duration-check.md`), A-7 D-GOP 후보 앵커(538 기반, 적용 안 함),
> 그림 5·12 다시 그림(`docs/figures/`), E-8·K-13 학습 스크립트 복원판(`liplab-lab/tools/train_aai.py`·`train_k_facecue.py`).
> 세션 2(`liplab-lab/tools/pod/session2.sh`)는 A1 폴백(`--cond none --steps 5250`)으로 바꾸고 C 30화자 유사도, 608 측정,
> A-2 kNN-VC 충실도를 붙였다. 세션 뒤 로컬에서 D-6(`d6_machine_confusion.py`)과 A-7(608 포함)을 돌린다.
> 사용자 결정 대기: 파일럿 보관 기간·윤리 절차·보호책임자, D-GOP 켜기와 새 앵커, 엔진 지속시간 상수 조정, Figma 비목(집행대장).

> **2026-09-23 밤 — 통합 브랜치에 계획서 잔여 작업과 Figma 적용을 이어서 올렸다(원격 푸시됨).**
> 한 화면 요약은 `docs/고도화_현황_팀공유.md`, 보고서용 수치·정정은 `docs/report-notes.md`.
> 이날 넣은 것: Figma 적용 2/3·3/3(레슨·탭·모달) + 회차 상세 모달(212:24), 문맥 추론·오늘의 복습 레슨 템플릿,
> 연습 탭 '입모양 교실'(웹캠·조음 교정 화면 진입점), 레슨 북마크 저장, H 다자 대화(화자별 아바타·닮은꼴 문장·빈칸 턴·
> 서버 재채점), J-3 문제 중 약한 음절 기호, G-6 문맥 문항 개인화, E-9 교정 세션 오차 기록, B-9 약한 소리 코칭,
> 학습 초기화 범위, 파일럿 계측(§4.7), 공개 자원 1.1.0, 여러 아바타가 한 화면에 안 보이던 버그 수정.
> 확인: 백엔드 pytest 214 통과, 프론트 node --test 49 통과, vite build 통과.
> 진행 중: RunPod 세션 1(A1), AI Hub 538 새 20화자 다운로드, 그 뒤 608 감음신경성 세션과 세션 2(A2·D v2·608 측정).
> 앱 기본값 주의: D-GOP는 여전히 `DGOP_ALIGNER_ID` 미설정이면 꺼져 있다(말하기 회차 상세의 음소 칩·불확실성은 켰을 때만).
> 보안 점검(`scripts/security-audit.sh`, 9/23): npm 운영 의존성에 axios·form-data(high), react-router(moderate)가 걸린다.
> 모두 같은 주 버전 안에 수정판이 있다. 이 워크트리의 `frontend/node_modules`는 메인 체크아웃과 공유(심링크)라 여기서
> `npm audit fix`를 하지 않았다 — 메인 체크아웃에서 올린 뒤 빌드·테스트하고 lockfile을 함께 커밋한다. pip-audit는 미설치.
>
> **2026-09-23 — 통합 브랜치 `integrate/2026-09-23` (검토 요청).** `feat/content-scale`(9f57939)에서 갈라
> `feat/sublexical-feedback` 11커밋(9f08043 이후: Figma §8 이식, G 대량화 525/917/181, 보안·개인정보 보강,
> 문맥문항 id 수정, B·A 문서 정정)을 병합했다. 두 원 브랜치는 건드리지 않았다. 방침은 9/21 병합(2절)과 같다:
> 화면은 Figma 셸, B 채점식은 naive, 촉각 제거 유지, 양쪽 기능 보존. 충돌 8파일 해소.
> 확인: 백엔드 pytest 180 통과, 프론트 node --test 47 통과, vite build 통과, 라우트 66개(중복 0, 촉각 0).
> 병합 중 고친 것: `speak_assess`의 미정의 `acoustic_dgop`(9/21 병합에서 생김, D-GOP 켜면 오류),
> 비로그인 `/terms`·`/privacy`에서 401 인터셉터가 새로고침을 반복하던 문제, 레슨 완료 XP를 서버 값으로,
> 촉각 문구 잔재, 9/21 병합에서 빠진 aa28c05(첫 검사 대비 향상도)·c92fdc3(aria-live) 복원.
> 남은 것: 사전·사후 A/B 검사 진입(Figma 이식 때 제거됨) 복원, 문맥문항 162개가 2지선다(3지 게이트 미달)이고
> `content_pipeline.build_closures`가 2지로 게이트를 불러 새 문항을 못 만듦, JuHana 님 IA 모듈은 여전히 미연결.
> `docs/dgop-demo.md`·`deaf-synthesis.md`의 D-GOP 수치는 옛 `dgop_from_audio` 기준이라 naive로 재측정 예정.
>
> 최종 갱신 2026-09-21 — **`feat/sublexical-feedback` 60커밋을 병합했다(미푸시).** 아래 '브랜치 현황'부터 본다.
> 그 전: 채점식 naive 교체(1단계) 완료, A-6(E1·E2) 실행 완료, 체크포인트 HF 백업 완료.
> 브랜치 `feat/content-scale` — 로컬이 origin(`952f816`)보다 병합 커밋 1개 앞선다. 되돌리려면
> `git reset --hard backup/pre-merge-2-content-scale`.
> 이 파일은 **한 화면짜리 현황판**이다. 근거·수치는 각 항목의 링크를 따라간다.
> 전체 이력은 `DEVELOPMENT_SUMMARY.md`.

---

## 한 줄 요약

축 A(D-GOP 음향 백본)는 학습·평가·보정까지 끝났지만, **그 판정을 만든 채점식에 구조적 결함이
있다**는 것이 드러났다. 2026-09-14에 재설계 실험(E1·E2)을 실제로 돌렸고 결론이 나왔다 —
**곱셈 항을 버리고 `naive`(표준 GOP)로 간다.** 불확실성 보정은 값을 하지 않았다.
지금 1순위는 **교체와 그에 따른 A-3 재측정·A-4 재적합**이다. 체크포인트는 HF에 백업됐다.

그와 **별개로 앱 트랙이 따로 굴러가고 있었다.** 2026-09-15에 `feat/sublexical-feedback`(자모 단위
피드백·비심 혼동행렬·학습 효과 리포트)을 합쳤다. 분기점이 촉각 제거 이전이라 충돌이 많았지만
**두 기둥(독화·말하기) 체제를 기준으로 삼아** 해소했다.

---

## 브랜치 현황 (2026-09-21)

혼자 하던 저장소가 아니다. **같은 파일을 세 갈래가 동시에 고치고 있다.**

| 브랜치 | 사람 | 하는 일 | content-scale 대비 |
|---|---|---|---|
| `feat/content-scale` | duadnwls | 축 A·B(음향 채점), 커리큘럼 | 기준 (`952f816` + 병합 커밋) |
| `feat/sublexical-feedback` | namyunsu | 축 B~K 고도화 + **Figma 리디자인**(9/19, 30커밋) | **병합 완료** (`702c373`까지 60커밋, 2026-09-21) |
| `feat/content-scaleUI` | JuHana | 프론트 IA 재구조화(App.jsx 라우팅·features/ 이동) | **병합 완료** (`eceda09`까지 8커밋, 2026-09-21) — 파일만 들여오고 라우팅은 Figma 셸 유지 |
| `refactor/app-shell-routing` | JuHana | 위 중 셸·라우팅만 | 2커밋 앞섬 |

`feat/content-scaleUI`는 2026-09-15에 content-scale로 fast-forward해 뒀고, 그 뒤 JuHana 님이
그 위에 쌓았다. **`frontend/src/App.jsx`는 세 갈래가 전부 건드린다** — 손대기 전에 순서를 합의한다.

⚠️ **이번 병합으로 프론트 IA가 namyunsu 님의 Figma 리디자인으로 바뀌었다.** 옛 `Dashboard.jsx`·
`PillarHub.jsx`·`GlobalLearningMenu.jsx`는 삭제됐고 진입은 `/learn/path`(CurriculumPath)+`AppShell`이다.
JuHana 님의 `feat/content-scaleUI`는 2026-09-21 두 번째 병합으로 들여왔다 — 단 **App.jsx는 우리(Figma 셸) 것을
유지**했고, JuHana 님의 `layouts/`(AppLayout·TopBar·NavShell)·`features/dashboard/`·`features/learn/shared/`
(TrackHub·LessonList·LessonRunner·LessonComplete)·`config/tracks.js`·`LIPLAB_REDESIGN_SPEC.md`는 **파일로만 들어와
라우팅에 연결돼 있지 않다.** 두 셸 중 무엇을 기준으로 할지는 여전히 팀 결정 — 정해지면 그때 연결하거나 지운다.

---

## 바로 할 일 (우선순위)

> **2026-09-21 — `feat/sublexical-feedback` 60커밋을 병합했다**(`7491547`, 충돌 25파일, **푸시 완료**). 방침은 아래 2절.
> 백엔드 26 + scripts 3 + 프론트 35 테스트 통과, vite build 통과, 라우트 61개(촉각 0).
> 이어서 **`feat/content-scaleUI` 8커밋도 병합**(App.jsx는 Figma 셸 유지, JuHana 님 모듈은 파일로만). 되돌리기 태그:
> `backup/pre-merge-2-content-scale`(1차 직전), `backup/pre-merge-3-content-scale`(2차 직전).
>
> **2026-09-15 — 앱 트랙을 병합했다**(`c82fb9f`). `feat/sublexical-feedback` 6커밋을 촉각 제거를
> 유지한 채 합쳤고 테스트·빌드까지 확인했다. **아직 푸시하지 않았다.** 되돌리려면
> `git reset --hard backup/pre-merge-content-scale`(병합 직전 상태로 걸어 둔 태그).
>
> **2026-09-14 세션에서 ① HF 백업 · ② E1 · ③ E2 · ④ 회수 · 스윕까지 전부 끝냈다.**
> 결과·판정·한계는 `docs/axis-a-training-plan.md` **A-6**. Pod은 정지했다(26분, 약 $1.5).
> 체크포인트는 이제 HF에도 있다 — **더 이상 AP-IN-2 볼륨에 묶이지 않는다.**

### 1. 채점식을 `naive`로 교체 ⭐

E1에서 **naive를 유의하게 이긴 변형이 하나도 없었다**(naive·maxlogit·prior_maxlogit 모두 단조성
1.000으로 천장). 사전 등록 규칙(축 B §4)대로 **`naive`를 채택한다.** 곱셈 항 `confidence`는 E2에서
**네 규칙 전부 우연 수준**(AUC 0.46~0.62)이라 정보가 없다는 것이 실측으로 굳었다.

| 순서 | 작업 | GPU | 비고 |
|---|---|---|---|
| ~~1~~ | ~~`dgop.dgop_phone`을 naive로 교체~~ | — | ✅ **2026-09-15 완료.** 단언도 '해결 확인'으로 뒤집었다 |
| 2 | A-3 재측정 | **필요**(~12분) | 원점수 눈금이 바뀐다 |
| 3 | A-4 앵커 재적합 → `backend/data/dgop_calibration.json` | **필요**(~11분) | 표시 점수 상한 94.9도 재확인 |
| 4 | 앱 연결 — `DGOP_ALIGNER_ID`/`DGOP_SCORER_ID` | 불필요 | **설정·문서는 2026-09-15에 준비 완료.** 켜는 것만 2·3 이후 |

2·3은 GPU가 필요하니 **한 세션에 묶어서** 돈다. 이제 아무 DC·아무 GPU에서 HF 체크포인트를 받아
돌리면 된다(비공개 저장소라 HF 읽기 토큰 필요).

**GPU를 태우기 전 사전 검증을 2026-09-15에 돌렸다**(런북 §6·§6.5의 "Pod에서 처음 만나면
20분·$1을 버린다"는 그 절차). **일부는 통과했고, 한 가지는 로컬에서 확인 불가로 판명됐다.**

✅ 통과:
- `fit_dgop_calibration.py --smoke` — 측정 루프부터 앵커 적합·표 출력까지 배관 정상
- `huggingface_hub` 1.23.0이 **`HF_TOKEN` 환경변수를 자동으로 읽는다.** `from_pretrained`에
  `token=` 인자가 없어서 여기서 막혔으면 Pod 1분 만에 인증 실패로 죽었을 자리다.
  코드 수정 없이 `export HF_TOKEN=hf_...` 한 줄이면 된다
- 데이터셋(`kresnik/zeroth_korean`)·공개 체크포인트가 로컬 HF 캐시에 있다

❌ **로컬에서 확인할 수 없는 것 — 데이터셋 오디오 디코딩 경로.**
`eval_dgop_discrimination.py --limit 2`가 `ImportError: please install 'torchcodec'`으로
죽었다. 2026-09-14에 "이 경로는 확인되지 않았다"고 적어 둔 바로 그 지점이다. 파고든 결과:

- `requirements-ml.txt`의 `torchcodec>=0.6.0,<0.7.0`은 **로컬 Python 3.14에서 설치 자체가
  안 된다** — 0.6.x에 cp314 휠이 없다(설치 가능한 최소가 0.9.0). 이 파일 전체가 로컬에서
  설치 불가라는 뜻이다
- 짝을 맞추면(torch 2.14 ↔ torchcodec 0.12.x) 추가 설치만으로 끝나지만, **torchcodec이
  FFmpeg 공유 라이브러리를 요구**해 WSL2 기본 상태에선 import가 OSError로 죽는다.
  시스템에 FFmpeg를 깔아야 한다

⇒ **이 경로는 Pod에서만 검증된다.** 실무상 문제는 아니다 — Pod 이미지가
`torch 2.8 / torchcodec 0.6.x` 조합이고 **2026-09-09 A-3·A-4가 실제로 그 조합에서 성공했다.**
다만 **Pod에서 torch를 올리지 말 것** — 올리면 torchcodec도 따라 올라가 CUDA 13을 요구한다.

명령어는 런북 **§6**(A-3)·**§6.5**(A-4)에 HF 저장소 id 기준으로 갱신해 뒀다 — 예전 `/workspace/ckpt/*`
볼륨 경로는 더 이상 필요 없다.

> **🚨 2·3이 끝나기 전에 앱의 D-GOP 경로를 켜지 않는다.** 채점식이 바뀌어 원점수 눈금이 달라졌는데
> `backend/data/dgop_calibration.json`과 `dgop.AXIS_A_SEVERITY_SCORES`는 아직 **구 식으로 잰 앵커**다.
> 지금 켜면 표시 점수가 틀린다. `DGOP_ALIGNER_ID` 미설정이 기본값이라 **현재는 꺼져 있다**(전사 경로).
>
> 켤 때 필요한 것은 `.env.example`의 'D-GOP 음향 채점' 절에 다 적어 뒀다 — **`HF_TOKEN`이 함께
> 있어야 한다**(저장소가 비공개다). 빠뜨리면 모델 로드가 실패하고 전사 경로로 폴백하는데,
> 이제 그 폴백이 조용하지 않다 — 서버 로그에 `[WARN] D-GOP 경로 실패`가 찍힌다.

### 2. 축 B 병합 충돌 정리 ✅ (2026-09-21 병합으로 해소)

**병합에서 이렇게 정했다** — 아래 원래 분석의 권고를 그대로 따랐다.

- `dgop.py`: 그쪽 로지스틱 `calibrate_score(raw01)`는 **삭제**. 앵커 보정 하나만 남았고 `sentence_dgop`의
  `score_calibrated`는 원점수×100을 앵커 보정에 넣는다. 그쪽의 **구간별(per-phone) 후기융합**은 살려서
  같은 눈금으로 옮겼다(`fuse_audio_visual_per_phone`, dgop×100 → 앵커 보정).
- `dgop_acoustic.py`: **우리 것**(`assess_text`, 정렬기/채점기 분리, ctc_align, naive). 그쪽 `dgop_from_audio`는 버렸다.
- `main.py` `/api/speak/assess`: **`DGOP_ALIGNER_ID` 게이트 유지**(미설정 = 전사 경로). D-GOP가 켜지면
  음소별 정보로 구간별 융합, 없으면 문장 단위 융합. 그쪽의 `_server_error` 헬퍼는 채택.
- 실측 확인: `calibrate_score(78.15) = 90.0`(19.5도 98도 아님). 단 **앵커 자체는 여전히 낡았다**(1순위 2·3단계).
- 그 밖의 합집합: closure-answer(서버 채점 + XP·스트릭), 배치검사(`PlacementResult`로 통일 —
  우리 `/api/assessment/history`는 그 테이블을 읽도록 고쳤고 그쪽 `progression`·`benchmark`·`resources`도 있다),
  `AvatarVRM`(음성구동 `bsFrameRef` > 웹캠 거울 `mirrorRef` > viseme), `WebcamMouthCheck`(우리 ref 최신값
  버그수정·입술 기하 + 그쪽 K 분류기·조음 교정·미러). 줄바꿈은 `main.py`·`api.js`·`scoring.py`·`index.css`를 LF로 정규화했다.
- 우리 `MouthMirror.jsx`는 그쪽 `WebcamMouthCheck` 안의 미러와 겹쳐 **화면에서 뺐다**(파일은 남아 있음).

<details><summary>원래 분석(2026-09-16)</summary>

`feat/sublexical-feedback`이 19커밋(57파일, +10,912/−2,245) 앞서 있고, **축 B에서 양쪽이 같은 걸
따로 만들었다.** 시험 병합(`git merge-tree`) 결과 **git이 잡는 충돌 14개 + 조용히 깨지는 곳 1개**.
브리핑은 2026-09-16 namyunsu 님께 전달했다.

**🔴 조용히 깨지는 곳 — `backend/dgop.py`는 충돌 없이 병합된다.**
같은 이름의 `calibrate_score`가 두 개 남고 파이썬은 마지막 정의만 쓴다.

| 위치 | 시그니처 | 입력 단위 | 방식 |
|---|---|---|---|
| 88행 (sublexical) | `calibrate_score(raw01)` | **0~1** | 로지스틱(상수 2개) |
| 240행 ← 살아남음 | `calibrate_score(raw_score, calibration)` | **0~100** | 앵커 + log 보간 |

살아남는 호출부는 sublexical의 `sentence_dgop`이라 0~1을 넘긴다 →
`calibrate_score(0.7815) = 19.5`. **깨끗한 발화가 19.5점이 되고 예외도 경고도 없다.**

**왜** — namyunsu 님 브랜치는 분기점이 9/3이라 ① A-5 구간 뭉갬 수정(`ctc_align.py` 없음)과
② A-6 채점식 교체를 못 받았다. 그 로지스틱은 **버그 있던 눈금**(정상 raw≈0.045)에 튜닝된
곡선이라, 새 눈금에서는 severity 0·1·2가 전부 98.0으로 포화해 구별되지 않는다.

**그 밖에 정해야 할 것:**

- **축 B는 합집합이 아니라 택일** — `backend/dgop_acoustic.py`가 add/add 충돌이다.
  진입점이 `assess_text`(우리, ctc_align·naive·앵커) vs `dgop_from_audio`(그쪽, 정렬 없음·
  곱셈식·로지스틱)로 갈린다. 우리 쪽을 기준으로 삼고 호출부를 갈아끼우는 방향을 권했다.
- **게이팅이 풀린다** — 그쪽은 `is_available()`(torch import 되면 True)라 **기본으로 켜진다.**
  우리는 `DGOP_ALIGNER_ID` 환경변수로 막아 뒀다. 되돌려야 한다.
- **모델이 다르다** — 그쪽은 `kresnik/wav2vec2-large-xlsr-korean` 하드코딩(공개 **음절** vocab).
  축 A 체크포인트는 자모 49토큰이다.
- **충돌 없이 병합되는 겹침 8개가 더 위험하다** — `dgop.py`·`database.py`·`assessment.py`·
  `content_rules.py`·`App.jsx`·`LipSyncPlayer3D.jsx`·`package.json`·`approved.json`.
- **병합 후 실측 확인** — 깨끗한 발화 하나로 채점해 본다. **19.5점이면** 단위 문제가 남은 것,
  **98점이면** 로지스틱이 살아 있는 것이다. 테스트로는 안 잡힌다.

> 이 정리는 1순위 2·3단계(A-3 재측정·A-4 재적합)와 **맞물린다** — 어느 보정을 남길지가
> 앵커 재적합 결과에 달려 있다. 재적합 전까지는 **양쪽 다 켜지 않는다.**

</details>

### 3. 그다음

- **AI Hub 608 샘플 확인** — IRB 불필요, 본인인증만. 확인할 것 3가지는 `docs/deaf-speech-data-research.md` §2
- **정민화 연구실 접촉**(서울대 언어학과) — 이제 E1·E2 실측을 들고 갈 수 있다. 우리 가설을 한국어로 이미 검증했고 코드가 MIT로 공개돼 있다. QoLT·CI 아동 데이터 경로이기도 하다
- **`blank 제외` 변형 재덤프**(GPU ~12분) — A-6 "남은 일" 2번. 지금 npz로는 평가할 수 없다
- ~~CLAUDE.md 로드맵 정리~~ — 2026-09-21 병합 때 반영했다(디렉터리·잠금 지점·백로그).
- **팀 공지** — namyunsu·JuHana 님께 지금 라우팅 기준이 Figma `AppShell`이고 JuHana 님 모듈은 미연결 상태임을 알리고, 셸 기준을 정한다

---

## 어디까지 했나

### ✅ 끝난 것

| 단계 | 내용 | 결과 |
|---|---|---|
| **A-1/A-2 학습** | Scorer(정상 발화) + Aligner(저하 증강) 2모델 분리, 자모 49토큰 vocab | eval_loss 0.2087 / 1.147. H100 2.5시간, $7~8 |
| **A-3 변별력** | 재측정 완료 | **단조성 0.998 / AUC 1.000 / 정렬 1.000 — 합격** |
| **A-4 점수 보정** | severity 앵커 + log 보간 | `backend/data/dgop_calibration.json` 커밋. 5개 severity 전부 채택 |
| **A-5 버그 수정** | 구간 뭉갬 버그 — 중복 토큰이 한 구간으로 합쳐지던 문제 | 깨끗한 발화 **9.51 → 76.56**. 한계 ②의 실제 원인이었다 |
| **CTC 정렬 자체 구현** | `backend/ctc_align.py` (Viterbi) | torchaudio와 프레임 단위 일치 검증. 의존 제거 |
| **100점 도달 불가** | 표시 상한 94.9 | **그대로 두기로 결정** — 발음 교정 앱에서 만점을 주지 않는 편이 낫다 |
| **농인 발화 데이터 조사** | 7개 축 병렬 조사 | `docs/deaf-speech-data-research.md` |
| **채점식 재설계 배관** | E1/E2 실험 도구 일체 | `docs/axis-b-scorer-redesign.md` |
| **체크포인트 HF 백업** | scorer·aligner 최종 모델 | `duadnwls/liplab-dgop-{scorer,aligner}`에 각 **1.26GB**. 업로드 크기 대조 + HF API 재확인 (2026-09-14) |
| **A-6 E1·E2 실행** | 채점식 9종 스윕 + 과신 측정 | **naive 채택 확정.** 구간 22,905 / 22,106개. 결과·한계는 `docs/axis-a-training-plan.md` A-6 |
| **채점식 교체 (1단계)** | `dgop_phone`을 naive로 (2026-09-15) | 곱셈 항 제거. 구 식은 `gop_variants.dgop`·`analyze_dgop_redundancy`에 **비교 기준으로 보존** — A-6 표와 ρ=0.980을 계속 재현한다 |
| **4단계 준비 (앱 연결)** | 설정·문서·실패 가시성 (2026-09-15) | `.env.example`에 DGOP·**HF_TOKEN** 절 신설, 런북 §7.2 보완, D-GOP 로드 실패를 `[WARN]` 로그로. 켜는 것은 2·3 이후 |
| **촉각(타도마) 제거** | 세 기둥 → **두 기둥(독화·말하기)** | 파일 22개·백엔드 엔드포인트 6개 삭제. 대시보드·메뉴·분석·안내 전부 두 기둥 기준으로 재정렬 (`b730c0d`) |
| **앱 트랙 병합** | `feat/sublexical-feedback` 6커밋 통합 (2026-09-15) | **촉각 제거 유지.** 충돌 6파일 해소, 기능 충돌 3건은 합집합 (`c82fb9f`) |
| **근거 기반 독화 피드백** | 오답을 자모·비심 단위로 분석 + 개인별 혼동행렬 | `scoring.viseme_confusions`, `TrialAttempt` 모델, `GET /api/curriculum/confusion-matrix` |
| **학습 효과 리포트** | 학습곡선·향상도·단계 도달 시행수 | `GET /api/eval/summary` + `/analysis/eval`(`EvalReport.jsx`) |

테스트: **backend 22 + scripts 3 + frontend 35, 전부 통과.** 2026-09-15 병합 후 재실행으로 확인했다
(`npx vite build` 성공, `main.py` 임포트 시 라우트 50개 등록·촉각 라우트 0개도 함께 확인) —
반드시 `backend/venv`의 파이썬으로 돌린다(시스템 파이썬엔 numpy·Levenshtein·torch가 없어 실패한다).
축 B §3-2의 스모크·스윕 배관도 로컬에서 끝까지 돌려 확인했다(31초, 구간 240개, blank 0개) —
**Pod에서 그 절은 건너뛰어도 된다.**

### ⚠️ 발견됐지만 아직 안 고친 것

**축 B 구현이 두 갈래로 갈라져 있다** (2026-09-16). `feat/sublexical-feedback`에 독립
구현이 있고, 병합하면 `dgop.py`의 `calibrate_score`가 **충돌 없이 두 개**가 된다 —
깨끗한 발화가 19.5점이 되는데 오류가 나지 않는다. 상세·판단 근거는 위 **바로 할 일 2**.
합치기 전까지 **어느 쪽도 배포에 켜지 않는다.**

**채점식 `D-GOP = naive × confidence`가 구조적으로 결함이다.** 데이터 없이 증명된다
(`python scripts/analyze_dgop_redundancy.py`):

- `ρ(naive, confidence) = 0.980` — 두 항이 같은 신호라 곱셈이 순위 정보를 더하지 못한다
- **보정 방향이 반대다** — 과신(뾰족한데 틀림)은 통과시키고 과소확신을 벌한다
- **순위를 뒤집는다** — '또렷하게 다른 음소'(0.0128)가 '머뭇거리지만 목표가 1등'(0.0015)보다
  8배 높은 점수. 확신에 차서 틀릴수록 점수가 오른다

선행 연구(Yeo et al., Interspeech 2023, 서울대, 코드 MIT)가 한국어 구음장애 발화에서 같은 실험을
이미 했고, **우리가 곱한 두 신호(margin·엔트로피)가 그 논문 표에서 가장 나쁜 둘**이었다.

**통계 인프라 3건 — 조사 문서 §5의 지적이 코드에 그대로 있다** (2026-09-14 확인):

- **유의성 검정이 없다** — `scripts/eval_dgop_discrimination.py`는 조사 문서보다 먼저 마지막으로
  수정된 상태다. 새 스윕(`sweep_gop_scorers.py`)에는 대응표본 부트스트랩이 붙었지만 **단조성
  비교에만** 있고 AUC에는 없다.
- **화자 단위 집계가 없다** — 스윕은 구간을 발화 단위로 접어 한 단계 개선했으나, 부트스트랩이
  뽑는 단위도 발화다. 한 화자의 발화 여러 개를 독립 표본으로 센다(조사 문서 §5-4).
- **합격선 0.90이 그대로다** — 감쇠 때문에 도달 불가일 수 있다는 지적(§5-5)에도
  `eval_dgop_discrimination.TARGET_MONOTONICITY = 0.90`이 유지돼 있다.

**A-6에서 새로 드러난 것 3건** (2026-09-14):

- **blank 불변 검사의 의미가 틀렸다.** `nb_frames != frames`는 정렬이 깨진 것을 잡지 못하고
  **모델 argmax가 blank인 프레임**을 센다. 강제정렬에서는 정상적으로 생기는 일이라 실제 데이터에서
  E1 구간의 **47%**(10,785개)가 걸린다. 따라서 **Cao et al. 2024의 blank 집계 지적은 여전히
  유효하다** — 축 B §6의 "재조사 불필요" 목록에서 그 줄을 내리고, 경고 문구도 고쳐야 한다.
- **`blank 제외` 변형은 평가되지 않았다.** `span_aggregates` docstring은 "전체/비blank 두 방식"을
  계산한다고 적었지만 저장되는 건 전체 구간 평균뿐이다. **재덤프 없이는 잴 수 없다.**
- **E1이 천장에 닿았다.** naive·maxlogit·prior_maxlogit이 모두 단조성 1.000이라 상위 후보를 구별할
  검정력이 없다. "UQ가 도움이 안 된다"가 아니라 **"합성 저하로는 물을 수 없다"**가 정확한 서술이다.

### 🚫 막힌 것

| 항목 | 막힌 이유 | 상태 |
|---|---|---|
| ~~체크포인트 HF 백업~~ | ~~AP-IN-2에 H100 없음~~ | ✅ **2026-09-14 해결** — 재고가 돌아와 기존 Pod이 그냥 켜졌다 |
| ~~E1·E2 실행~~ | ~~같은 GPU 병목~~ | ✅ **2026-09-14 완료** (A-6) |
| **실제 농인 발화** | AI Hub 71434는 IRB+소속증빙 필요(안심존). 608은 본인인증만 | 경로는 조사 완료 |

> **GPU 확보 교훈 (2026-09-14).** 9/9의 24회 실패는 **그때 DC에 H100이 없었기 때문**이고, 닷새 뒤
> `gpuTypes.lowestPrice(dataCenterId:"AP-IN-2").stockStatus`가 `Low`로 돌아오자 기존 Pod의 `start`가
> 한 번에 성공했다. **다음에 막히면 우회로를 찾기 전에 재고를 먼저 조회한다.**
> 우회로 조사(S3 API는 AP-IN-2 미지원, 0 GPU 시작, 새 Pod 배포)는 런북 **§7.2**에, 실기에서 밟은
> 함정(**포트 재매핑**, **Pod 저장소가 9/8에 멈춰 있어 `git pull`이 거부됨**)은 **§2.1**에 적어 뒀다.

### 🔸 결정된 것

**2026-09-15 (병합에서).**

- **`closure-answer`는 두 구현의 합집합이다.** 양쪽 브랜치가 각자 같은 엔드포인트를 만들었다.
  상대의 **서버 채점**(`item_id`/`chosen`을 받아 `CLOSURE_ITEMS`에서 정답을 찾는다) 위에
  우리의 3단계 숙달·취약 입모양·SRS·XP를 얹었다. 한쪽만 고르면 기능이 사라진다.
- **정오답은 서버가 재계산한다 — XP까지.** 클라이언트가 보낸 `data.correct`를 믿으면 숙달·해금·
  평가를 조작할 수 있다. 상대의 감사 수정이 2단계 채점을 고쳤고, 병합하며 **같은 결함이 남아
  있던 XP 보상 1곳**도 서버 재계산값으로 맞췄다.
- **`HardwareBuild` 페이지는 되살리지 않는다.** 촉각 장치용이라 `b730c0d`가 지웠다. 상대 브랜치의
  lazy import를 그대로 받으면 `vite build`가 깨진다 — `EvalReport`만 받았다.

**2026-09-14.**

- **촉각 DB 테이블은 그대로 둔다.** `database.py`의 `TactileStageProgress`·`TactileAttempt`와
  `Bookmark.domain`의 `'tactile'` 값은 조회하는 코드가 없어 무해하다. 기존 행을 잃지 않기 위해
  남기고, **"미사용 · 지우려면 별도 마이그레이션 필요"** 주석만 붙였다.
- **`torch`·`torchaudio` `<2.9.0` 상한은 풀었다.** 근거: 로컬 `backend/venv`가 이미
  **torch 2.14 / torchaudio 2.11**이고 그 조합으로 backend 22파일·scripts 3파일이 전부 통과하며,
  상한의 근거였던 `forced_align`도 2.11에 그대로 살아 있다.
  ⚠️ **실질적 상한은 이제 `torchcodec<0.7.0`**(torch 2.8 계열에 묶여 있다)이다. 학습을 돌릴 때는
  (torch, torchaudio, torchcodec)을 **한 세트로** 맞춘다 — 위 로컬 검증에 torchcodec은 빠져 있어
  **데이터셋 오디오 디코딩 경로는 확인되지 않았다.** 상세는 `requirements-ml.txt` 머리 메모.
- **E1·E2 판정 규칙의 빈칸을 메꿨다.** "세 결과가 배타적"이 아니라는 점, `prior_maxlogit`이 아닌
  변형이 이길 때의 채택 순서, E2의 잔존율·AUC 임계값을 `docs/axis-b-scorer-redesign.md` §4에
  **사전 등록**으로 적었다(결과를 보기 전에 정한 값이다).

---

## 알아둘 함정 (반복해서 밟은 것들)

1. **Pod을 정지하면 GPU 예약이 풀린다.** 볼륨에서 꺼낼 게 있으면 **끄기 전에** 꺼낸다
2. **Pod Start 후 `PUBLIC_KEY` env가 비어 SSH가 막힌다** — env PATCH + 재시작. 그러면 포트가 또 바뀐다 (런북 §2.1)
3. **`--mode perturb`는 자모 vocab 전용** — 음절 vocab으로 돌리면 첫 발화에서 즉시 실패하도록 막아 뒀다
4. ~~`torchaudio<2.9.0` 상한~~ → **2026-09-14 해제됨.** 이제 실제로 막는 것은 `torchcodec<0.7.0`이다
   (torch 2.8 계열에 묶여 있다) — 학습 환경에서는 torch·torchaudio·torchcodec을 한 세트로 맞춘다
5. **줄바꿈이 파일마다 다르다 — `main.py`만이 아니다.** 실측 결과 소스 18개가 CRLF다:
   `backend/{main,database,engine,scoring,llm_service,auth,check_db}.py`,
   `frontend/src/api.js`, `frontend/src/pages/{Practice,Conversation,Bookmarks}.jsx`,
   `frontend/src/components/{LipSyncPlayer3D,QuizForm}.jsx`, `frontend/src/{main.jsx,store/useStore.js}`,
   `frontend/{vite,tailwind,postcss}.config.js`.
   **"나머지는 LF"는 틀렸다 (2026-09-14 정정).** 추적 파일 **36개**가 CRLF거나 섞여 있다 — 위 18개 외에
   `backend/requirements.txt`, `frontend/{index.html,package.json,package-lock.json}`,
   `frontend/src/index.css`, `Dockerfile`, `docker-compose.yml`, `fly.toml`, `.env.example`,
   `scripts/{setup.sh,setup.ps1,start-backend.ps1}`, `DEPLOY.md`, `QUICKSTART.md`, `PROJECT_SUMMARY.md`가
   CRLF이고, `.gitignore`·`backend/data/ksl_dictionary.csv` **2개만 두 방식이 섞여 있다.**
   (**2026-09-15 정정** — `README.md`는 혼합이었으나 상대 브랜치가 고치며 CRLF로 정규화했다.
   합계 36개는 그대로이고 CRLF 34 · 혼합 2로 내역만 바뀌었다. 병합으로 들어온 `fly.dev.toml`·
   `EvalReport.jsx`는 LF다.)
   섞으면 diff가 파일 전체로 뒤집힌다. **편집 전에 확인한다:**
   ```bash
   grep -c $'\r' <파일>                   # 0이면 LF, 줄 수와 같으면 CRLF
   git ls-files --eol | grep -v 'w/lf'    # 저장소 전체를 한 번에 본다
   ```
6. 테스트는 pytest가 아니라 자체 러너 — `PYTHONPATH=. python test_x.py`
7. **`requirements-ml.txt`는 로컬 Python 3.14에 설치되지 않는다** (2026-09-15 실측).
   `torchcodec>=0.6.0,<0.7.0`에 cp314 휠이 없다. 이건 Pod 이미지(torch 2.8) 전용 핀이다.
   데이터셋 오디오 디코딩이 필요한 스크립트는 **로컬 사전 검증이 불가능하다** — Pod에서 돈다.
   `--smoke` 경로는 합성 오디오라 로컬에서도 돌고, 배관 확인은 그걸로 한다.
8. **오래된 분기점에서 갈라진 브랜치를 합칠 때, 자동 병합이 조용히 옛 코드를 남긴다.**
   `feat/sublexical-feedback` 병합에서 `Closure.jsx`가 그랬다 — 양쪽 호출이 나란히 살아남아
   같은 엔드포인트를 두 번 부르고, 두 번째는 바뀐 시그니처와 안 맞아 매번 400이 났다.
   **충돌이 안 난 파일이 오히려 위험하다.** 시그니처를 바꿨다면 호출부를 전부 훑는다.
   2026-09-16에 더 나쁜 사례가 나왔다 — **같은 이름의 함수 두 개가 한 파일에 조용히 남는다.**
   파이썬은 마지막 정의만 쓰고, 호출부는 다른 쪽 것이 살아남아 단위가 어긋난다.
   **합치기 전에 시험 병합으로 조용한 쪽을 먼저 본다:**
   ```bash
   git merge-tree --write-tree <ours> <theirs>   # 충돌 목록 + 병합 트리 해시
   # 충돌에 안 뜨는데 양쪽이 고친 파일이 진짜 위험한 파일이다
   ```

---

## 문서 지도

| 문서 | 언제 보나 |
|---|---|
| **`docs/axis-b-scorer-redesign.md`** | 채점식 후보 9종과 **사전 등록한 판정 규칙**(§4). E1·E2는 끝났고 결과는 A-6에 |
| `docs/axis-a-runbook.md` | RunPod 실행 절차, 시간·비용, 함정 |
| `docs/axis-a-training-plan.md` | 축 A 설계 근거와 실측 이력(A-1~**A-6**) — **1순위 작업의 근거가 A-6에 있다** |
| `docs/deaf-speech-data-research.md` | 데이터 확보 경로 7개 축 + 채점식 결함의 근거 |
| `DEVELOPMENT_SUMMARY.md` | 전체 개발 이력 요약 |
| `CLAUDE.md` | 프로젝트 오리엔테이션(커리큘럼·잠금 규칙·컨벤션) |
