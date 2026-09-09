# 농인 발화 데이터 확보 경로 조사

> 조사일 2026-09-09. 목적: 축 A의 미결 지점(한계 ①)을 판정할 **실제 농인 발화 + 중증도 라벨** 확보.
> 방법: 7개 축 병렬 조사(한국 공개데이터 / 국제 코퍼스 구매 / 농인 특화 / 간접 추출 /
> 기관 협력 / 자체 수집 설계 / 대체 검증 전략).
> 관련: `docs/axis-a-training-plan.md`(축 A 설계·실측), `docs/lipreading-data-research.md`(축 D 영상 데이터 — 별개)

각 항목의 **검증 상태를 명시**한다. `✅직접확인` = 이 문서 작성 중 원문·파일·HTTP 응답으로
확인, `📄보고` = 조사 결과이나 재확인 안 됨, `❓미확인` = 확인 실패.

---

## 0. 결론 — 데이터는 1차 병목이 아니다

조사를 시작한 전제는 *"합성 저하로는 가설이 검증되지 않았으니 실제 농인 발화가 필요하다"*였다.
조사 결과 그 전제가 **절반만 맞다**.

**채점식 `D-GOP = naive × confidence` 자체에 구조적 결함이 있고, 이는 데이터 없이 증명된다.**
`scripts/analyze_dgop_redundancy.py`가 결정론적으로 재현한다 (✅직접확인):

| 측정 | 값 | 의미 |
|---|---|---|
| ρ(naive, confidence) | **0.980** | 두 항이 같은 신호다. 곱셈이 순위 정보를 더하지 못한다 |
| ρ(naive, confidence), naive≥0.8 | 0.999 | 확신 구간에서는 사실상 동일 |

두 항 모두 "분포가 얼마나 뾰족한가"의 단조 함수다. 그래서 `-ρ(severity, score)`가
**구조적으로 naive 이하**가 된다 — A-3/A-5 실측(축 A 1.000→0.998, 베이스라인 0.914→0.813)이
정확히 그 예측값이다.

더 나쁜 것은 방향이다:

| 시나리오 | naive | conf | D-GOP | |
|---|---|---|---|---|
| A 목표에 포화 (= **과신**) | 0.950 | 0.853 | 0.811 | 보정이 거의 안 걷힘 — **통과시킨다** |
| B 다른 음소에 확신 (체계적 치환) | 0.001 | 0.853 | 0.001 | naive가 이미 잡음 |
| C 평평, 목표가 간신히 1등 | 0.024 | 0.000 | 0.000 | **보정이 작동하는 유일한 구간** |

과신이란 **분포가 뾰족한데 틀린 것**이다. `confidence`가 재는 것이 바로 그 뾰족함이라
과신 구간을 통과시킨다. 실제로 걷히는 것은 **과소확신**이다 — 설계 의도와 반대다.

**이 판정에 농인 발화는 필요 없다.** 실제 데이터를 구해도 이 곱셈 형태로는 과신을 못 잡는다.

### 선행 연구가 같은 실험을 한국어로 이미 했다

**Yeo, Choi, Kim, Chung (Interspeech 2023)**, "Speech Intelligibility Assessment of Dysarthric
Speech by using Goodness of Pronunciation with Uncertainty Quantification"
([arXiv:2305.18392](https://arxiv.org/abs/2305.18392), 코드 [MIT](https://github.com/juice500ml/dysarthria-gop),
서울대 언어학과). 구음장애 발화, 영어·**한국어**·타밀어. 한국어 Kendall τ:

| 방법 | 한국어 τ |
|---|---|
| GMM-GoP (베이스라인) | −0.524 |
| **Entropy** | **−0.264** ← 베이스라인의 절반 |
| **Margin** | **−0.443** ← 베이스라인보다 나쁨 |
| Prior + **MaxLogit** | **−0.544** ← 유일한 승자 (상대 개선 3.91%) |

우리가 곱한 두 신호(margin·엔트로피)가 **그 표에서 가장 성능이 낮은 둘**이다. 이긴 것은
MaxLogit뿐이고 이유가 명확하다 — **softmax를 탈출한다**. OOD 입력에서는 로짓이 전부 낮은데
softmax 정규화가 그 정보를 지운다. 우리 세 항은 전부 같은 softmax 위에서 계산된다.

개선폭도 정직하게 봐야 한다: 한국어 상대 **3.91%**. 극적인 것이 아니다.

### ~~구현 결함 하나 더 — CTC blank~~ → **이미 해결돼 있었다** (2026-09-09 정정)

Cao, Fan, Svendsen, Salvi (Interspeech 2024)의 CTC 음소 평가 프레임워크는 *"only non-blank
tokens contribute to the estimation, while the blank tokens are skipped"*라고 명시한다
([PDF](https://www.isca-archive.org/interspeech_2024/cao24b_interspeech.pdf)).

이 문서 초판은 *"A-5에서 정렬은 고쳤지만 집계는 아직 안 고쳤다"*고 적었는데 **틀렸다.**
구현을 실측하니 `ctc_align.token_spans`는 **같은 비blank 라벨이 이어지는 run만** 구간으로
잡으므로 구간 안에 blank가 **원리적으로 0개**다. blank는 구간 *사이*에만 있다.

지적 자체는 유효했지만 그 대상은 **A-5 이전 구현**이었다 — 그때는 정렬 경로를 토큰 id로
필터링해 `min~max` 구간을 잡았고 거기에 blank가 잔뜩 들어갔다. **구간 뭉갬 버그를 고치면서
이 문제도 함께 사라졌다.**

정렬 방식이 바뀌어 blank가 섞이기 시작하면 `dump_gop_features.span_aggregates`의 불변
검사(`nb_frames != frames`)와 `test_dump_gop_features.test_spans_contain_no_blank_frames`가
알려준다.

---

## 1. 지금 당장 받을 수 있는 것

| 자원 | 병인 | 규모 | 중증도 라벨 | 비용 | 검증 |
|---|---|---|---|---|---|
| **TORGO** (토론토대 직배포) | 구음장애 (CP·ALS) | 장애 8 + 대조 7 | Frenchay 명료도 | **$0** | ✅직접확인 — 4파일 HTTP 200, 총 9.58GB, 인증 없음 |
| **speechocean762** | L2 영어 발음 | 5,000발화 / 250화자 | **음소별 정확도 0–2, 전문가 5인** | **$0** | 📄보고 — CC BY 4.0(**상업 가능**), Kaldi 공식 GOP 레시피 |
| **SPAL 메타데이터** | **농인 발화** | 34화자 (농 25 + 정상 9) | High 4 / Med 10 / Low 11명 | **$0** | ✅직접확인 — CSV 850행 파싱, **오디오 없음** |
| **EasyCall** | 구음장애 (이탈리아어) | 21 + 26화자, 16,683녹음 | TOM 4등급 | **$0** | 📄보고 — CC BY-NC 2.0 |

> ⚠️ **TORGO를 LDC에서 사지 말 것.** LDC2012S02가 비회원 $1,200 / Reduced $600인데, 원 배포처인
> 토론토대에서 동일 데이터를 무료로 받는다: `cs.toronto.edu/~complingweb/data/TORGO/`
> (F 1.14GB / FC 2.53GB / M 2.51GB / MC 3.40GB). 학술·비영리 한정, 논문 인용 의무.

**SPAL CSV의 구조** (✅직접확인): `subject_id`, `passage_id`, `groundtruth`(정답 전사),
AWS/Azure/Whisper/GoogleChirp 4종 ASR 출력과 각 WER, `speech_intelligibility`(High/Medium/Low),
`onset_hearing_loss`(Pre 239 / Post 347), `communication_mode`(Oral 93 / Oral+Sign 260 / Sign Only 233).
`Group`은 Deaf 586 / Normal-Hearing 264.
출처: [koenecke/ASR_dDhh_performance](https://github.com/koenecke/ASR_dDhh_performance) (LICENSE 파일 없음 — 사용 전 확인 필요).

---

## 2. 절차가 필요한 것

### AI Hub 「구음장애 음성인식 데이터」 (dataSetSn=608) — 가장 현실적인 한국어 경로

| 항목 | 내용 |
|---|---|
| 규모 | 1,200명+ / 5,000~5,250시간 / **429GB** |
| 병인 분포 | 후두 48.83% / **언어청각 30.35% (≈91,192분 ≈1,520시간)** / 뇌신경 20.82% |
| 중증도 라벨 | `Disease.Subcategory2` = 0 경도 / 1 중등도 / 2 고도, `GradeCategory1` = 0 언어 / 1 청각 |
| 정답 텍스트 | `Test.Transcript` + `Test.TestMethod`(단어 11.2% / 문장 61.7% / 문단 23.9% / 준자유·자유 3.3%) |
| 포맷 | WAV 44.1kHz + JSON (16kHz 리샘플 필요) |
| 접근 | 회원가입 → **휴대폰 본인인증(내국인 한정)** → 신청 → 자동승인 → API 다운로드 |
| 라이선스 | 무료. **"AI 학습모델의 학습용으로만"**, 재배포 금지, 상업 이용은 수행기관 별도 협의 |

**접근 등급 판정** (✅직접확인 — 조사 중 에이전트 간 결론이 갈려 원본 HTML로 확정):

```
dataSetSn=608    s3FileCnt = '8'   ← S3에 파일 존재
dataSetSn=71434  s3FileCnt = '0'
dataSetSn=71393  s3FileCnt = '0'

if (s3FileCnt == 0 && ...) { alert('데이터 준비중입니다.'); }
else { location.href = '/aihubdata/data/dwld.do' + ... }
```

608만 다운로드 분기를 탄다. 세 페이지 모두 "보건의료 데이터는 안심존을 통해 개방됩니다"
문구가 29~32회 나오지만 이는 **모든 데이터셋 페이지에 붙는 보일러플레이트**다(같은 페이지에
국방·방송영상 안내가 나란히 붙는다). 이 문구만 보고 608을 안심존으로 판정하면 틀린다.
※ 로그인 상태의 실제 다운로드 버튼까지는 확인하지 못했다.

**착수 전 확인해야 할 것 (이 경로의 성패를 가른다):**
1. `GradeCategory1 == 1(청각)` 화자가 실제로 분리되는가, 몇 명인가
2. 3등급이 **말명료도**인가 아니면 청력손실 정도·의학적 장애등급인가 — 후자면 D-GOP 점수와의
   순위상관이 이론적으로 흐려진다
3. 선천성 농 / 후천성 난청 구분 필드가 있는가 (71434에는 `hearingLoss`가 있으나 608에는 미확인)

→ **로그인만 하면 받을 수 있는 샘플(경량) 데이터로 위 셋을 먼저 확인**하면 429GB를 받기 전에
리스크가 사라진다.

### AI Hub 「구음장애인 명령어 데이터」 (dataSetSn=71434) — 농인 발화로는 국내 최고

| 항목 | 내용 |
|---|---|
| 규모 | 2,976,422건 중 **청각장애 2,102,837건 (70.65%)** |
| 라벨 | `intelligibility`(말명료도 SIR 1~5) · `degree`(장애정도) · **`hearingLoss`(청력손실 시기 → 선천/후천 판별)** · `device`·`deviceUsedAge` · `comunicationTool` · `rehabilitation` |
| **조음 오류 정답** | `spellingForm`(목표 철자) vs `pronunciationForm`(실제 발음 전사) **쌍**. 예: `"(애츨할)/(외출할) 때 티브이 꺼 (즈어.)/(줘.)"` |
| 발화 | 13종 주제 명령어 (단문 — 문장 운율 평가에는 한계) |
| 포맷 | WAV 16kHz/16bit/mono + JSON |
| 접근 | **온라인 안심존.** IRB 심의결과 통지서(**또는 면제 서류**) + IRB 승인 연구계획서 + **소속 증빙**(재직·재학증명서·근로계약서 택1) + 이용신청서 + 보안서약서. 심사 최대 2주, 환경구성 최대 5일 |
| 환경 | GPU 서버(V100 32GB) 제공, Docker + Jupyter. **데이터 반출 불가 — 학습모델만 반출 심사 후 전달** |
| 문의 | safezone1@aihub.kr / 02-525-7708, 7709 |

`spellingForm`/`pronunciationForm` 쌍은 이 프로젝트에 특히 값지다 — 발화별 조음 왜곡의
ground truth라 "체계적 치환에서 GOP가 어떻게 반응하는가"를 직접 잴 수 있다.

### 그 밖의 요청 경로

| 자원 | 내용 | 연락처 |
|---|---|---|
| **COPAS** (네덜란드) | 📄보고 — 이번 조사에서 **유일하게 농인 26명과 구음장애 48명을 같은 명료도 척도(DIA)로** 담은 코퍼스. 무료, 이메일+비번만으로 등록. ❓우리 확인은 HTTP 403으로 실패 | [INT Taalmaterialen](https://taalmaterialen.ivdnt.org/download/tstc-corpus-pathologische-en-normale-spraak-copas/) |
| **SPAL 오디오** | 농인 발화 11시간, SIC 0–7 명료도. 가격 미공개 | `lmendel@memphis.edu`, `mpousson@memphis.edu` |
| **QoLT** (한국어) | 구음장애 70화자 / 700발화, **언어병리사 5인 5점 척도**. 비공개, `available by request`. **Yeo et al.의 벤치마크가 이 데이터라 재현 기준선이 있다** | 서울대 정민화 연구실 |
| **SNU 인공와우 아동** | 한국어 CI 아동 7~8명, 이식 후 5년 종단, **전문가 평정 말산출 점수** | 같은 연구실 |
| **SSNCE Tamil** | LDC2021S04, 20 + 10화자 | **$300** (Reduced $150) |

> ⚠️ 과거 배포처 **SiTEC(sitec.or.kr)은 HTTP 500으로 소멸**했다. 기관 경유 배포 경로는 없다.

### 가장 중요한 연결

**Yeo et al.(GOP+UQ, 한국어)의 Kim·Chung = SNU 인공와우 코퍼스의 Kim·Chung = QoLT 접근 경로
= 같은 연구실**(서울대 언어학과 정민화). 한 곳이 (a) 우리 가설을 한국어로 이미 검증했고 코드를
MIT로 공개했으며, (b) QoLT·CI 아동 데이터에 닿아 있다. **접촉 1순위**이고,
"데이터를 달라"보다 **"당신들 방법을 자모 CTC에 적용했더니 이렇게 나왔다"**로 접근하는 것이 맞다.

---

## 3. 막힌 길 (전수 확인된 음성 결과)

| 경로 | 결과 |
|---|---|
| 국립국어원 모두의말뭉치 | **138종 전수 확인, 병리 발화 0.** 음성은 정상 화자만. 수어는 영상, 점자는 텍스트 |
| 공공데이터포털 | '구음장애' **0건**. '청각장애 음성' 5건은 전부 수어영상·통계 CSV |
| ETRI aiopen | **2025-06-30 운영 종료** |
| SiTEC | **HTTP 500, 소멸** |
| ELRA/ELDA | 6개 질의 **0건**. `deaf` 검색은 수어 코퍼스만 반환 |
| OpenSLR | 157개 리소스 중 병리음성 **0건** |
| Zenodo / OSF / figshare | 농인 발화 오디오 **0건**. 나오는 것은 전부 *지각* 실험이거나 교육학 논문 |
| HuggingFace | 원본 없음. 재업로드뿐이고 일부는 **라이선스 표기가 원본과 불일치**(TORGO 미러가 `license:mit` — 신뢰하지 말 것) |
| LDC 카탈로그 | 2000–2026년 **873개 전수 검색 → 병리음성 2건**(TORGO, SSNCE Tamil) |

**소속 기관이 없으면 불가능한 것:** UASpeech(*"government and academic research labs"* 한정),
Speech Accessibility Project(DUA에 연구자 + **소속기관 책임자 두 사람 서명** 필요 — 999화자
1,500시간으로 품질은 최고급이라 가장 아깝다), TalkBank 임상 DB(faculty 한정),
Google Euphonia(참가자 동의서상 외부 공유 불가).

---

## 4. 권장하지 않는 경로

### 공개 미디어(유튜브) 간접 추출 — 반대

법·윤리 이전에 **과학적으로 성립하지 않는다.** 유튜브에 음성으로 방송하는 농인은 정의상
**명료도 상위권**이다(확인된 채널의 크리에이터들이 오랜 구화 훈련을 거쳤다). 재려는 중증도
축의 절반이 잘려나간 자로 단조성을 재는 셈이다. 국내 장애인 유튜브 채널 전체가 207개이고
그중 청각장애는 소수라 **화자 10~30명이 상한**이다.

그 위에 세 가지가 각각 독립적으로 치명적이다:
- **라벨** — 자동자막을 정답으로 쓰면 발음이 나쁜 구간일수록 라벨도 틀리는 **순환 오염**.
  수동자막은 정제된 문어라 음소 정렬이 어긋난다. 통제 낭독이 없다
- **법** — 국내 저작권법에 **TDM 면책 조항이 없다**(2021년 개정안 임기만료 폐기, 22대 재발의안
  미통과, 게다가 "비상업적·공익적" 한정이라 앱은 대상 밖). 공정이용 4요소 중 3개 불리.
  YouTube 약관은 다운로드·자동수집을 이중으로 금지
- **개인정보** — **장애 정보는 민감정보**(개인정보보호법 제23조)라 별도 동의가 필수고,
  개인정보위가 인정하는 "정당한 이익"(제15조)은 **민감정보에 적용되지 않는다**

윤리도 가볍지 않다. 청각장애인을 위한 앱의 채점기를 청각장애인의 동의 없이 수집한 데이터로
만드는 것이고, 붙이는 라벨이 하필 "이 사람의 발음은 부정확하다"이다.

### 자체 수집 — 기각 (검정력이 안 나온다)

Steiger's Z 폐형식 + 몬테카를로 4,000회 교차검증 (📄보고):

| 시나리오 | 필요 화자 수 |
|---|---|
| Δρ=.20, 라벨 완벽 | 15~20명 |
| **Δρ=.10, 신뢰도 .90/.90 (기준)** | **150명 안팎** |
| AUC 비교까지 (ΔAUC=.08) | 정상 48 + 중증 48 |

**"대충 30명"은 극적 효과 + 거의 완벽한 라벨일 때만 성립한다.** 30명으로 돌려 null이 나오면
"효과 없음"이 아니라 "검정력 없음"이 되어 아무것도 판정하지 못한다. 비용도 **9~15개월,
1,000만원 이상**(AI Hub 경로는 1~2개월, 수만~수십만원).

법적으로도 정규 IRB를 피할 수 없다 — **장애인은 취약한 연구대상자라 심의면제 대상에서
명시적으로 제외**된다.

---

## 5. 이 조사가 드러낸 우리 쪽 문제

데이터와 별개로, 실데이터를 넣기 전에 고쳐야 하는 것들이다.

| # | 문제 | 위치 |
|---|---|---|
| 1 | **채점식이 구조적으로 결함** — §0. naive와 confidence가 중복(ρ=0.980)이고 보정 방향이 반대 | `dgop.dgop_phone` |
| 2 | ~~blank 프레임이 구간 평균에 포함~~ — **오진이었다**(2026-09-09). A-5 구간 수정으로 이미 해결돼 있었고, 불변 검사로 고정했다 | — |
| 3 | **유의성 검정·신뢰구간 없음** — "naive 0.914 > D-GOP 0.813"에 검정이 안 붙어 있어 우연인지 모른다. 스크립트가 이미 발화별 `rhos_dgop`/`rhos_naive` 쌍을 들고 있으므로 대응표본 검정을 붙이면 된다 | `scripts/eval_dgop_discrimination.py` |
| 4 | **AUC가 발화 단위 pooling** — 한 화자의 발화 20개는 독립 표본 20개가 아니다. 화자 단위 집계 또는 클러스터 부트스트랩 필요 | 같은 파일 |
| 5 | **합격선 0.90이 감쇠 때문에 도달 불가일 수 있음** — 관측 ρ = ρ_true × √(R_점수 × R_중증도). 참값 0.95라도 신뢰도 0.90/0.90이면 관측 0.855. **재정의가 데이터보다 먼저** | `eval_dgop_discrimination.TARGET_*` |
| 6 | **모집단 전제** — 2023 장애인 실태조사 기준 청각장애인의 **84.2%가 주 의사소통 수단이 "말"**이고 수어 주사용자는 3% 내외다. 대다수는 노인성·후천성이라 발화가 정상이다. 발화가 실제로 저하된 집단은 **언어습득 전 고도–심도 난청**이라는 훨씬 작은 하위집단이다 | 문서 전반 |

> §6과 관련해 **청력손실 dB를 중증도 대리 지표로 쓰면 안 된다.** dB는 "듣기"의 지표이지 자기
> 발화의 명료도가 아니다 — 후천성 난청 성인은 90dB HL이어도 발화가 멀쩡하다. AI Hub 71393의
> 연속 dB 라벨이 "5단계보다 정밀하다"는 판단은 이 이유로 철회한다. 71434의 **말명료도**
> 라벨이 필요한 것이다.

한국어 **표준화 성인 명료도 검사 도구는 사실상 없다**(U-TAP2·APAC·KS-PAPT는 전부 아동
조음검사). 직접 만들어야 하고, 청취자 평가로 R=0.90을 얻으려면 비숙련 청자 8~10명 또는
언어재활사 4~6명이 필요하다.

---

## 6. 권고 순서

1. **채점식부터 고친다.** span 분포와 **raw logit**을 npz로 덤프해두고 채점식 비교를 순수 함수
   replay로 돌린다(GPU 1회, 이후 무료). 후보: naive / D-GOP / GMM-GoP / NN-GoP / DNN-GoP /
   **Prior+MaxLogit** / LogitMargin / **blank 제외 변형**.
   세 결과가 배타적이라 무엇이 문제인지 갈린다 —
   *Prior+MaxLogit이 이기면* 방향은 옳고 곱셈 형태가 틀린 것,
   *어떤 UQ도 naive를 못 이기면* 합성 저하에서 UQ 자체가 무의미,
   *blank 제외가 크게 이기면* 구현 결함이었지 가설 문제가 아니다.
2. **과신의 존재 자체를 직접 잰다.** 깨끗한 Zeroth 발화를 그대로 두고 **목표 토큰열만**
   오염시킨다(종성 탈락 / `o:ㅅ`→`o:ㄷ` / `o:ㅂ`→`o:ㅁ` / 모음 중성화). 오염 목표에서 naive가
   높게 남으면 과신이 실재하는 것이고, 붕괴하면 이 모델은 애초에 과신하지 않는 것이다.
   **오디오 합성이 필요 없다** — 합성 저하가 못 만든 "체계적 치환" 조건을 만든다.
3. **TORGO·speechocean762로 오늘 대리 검증.** 승인 절차가 없다. 여기서도 naive를 못 이기면
   한국 데이터를 기다릴 이유가 없다.
4. **AI Hub 608 샘플 확인** → §2의 세 항목 판정 → 통과하면 언어청각 파트만 부분 다운로드.
5. 병행: 71434 안심존 문의(GPU 추론 가능 여부를 **가장 먼저** 물을 것), COPAS 등록, Memphis 메일,
   정민화 연구실 접촉.
6. **통계 인프라**(§5의 3·4·5)를 실데이터 투입 전에 정리.

> `deaf_speech_synthesis.py` 정교화는 **채점식 교체 이후**에 한다. 지금 합성을 다듬으면
> 잘못된 자를 더 정밀하게 만드는 셈이다. (문헌 근거: 농인 발화의 분절 오류는
> Osberger & McGarr 1982, 한국어 모음 포먼트 중앙화는 서경희·심홍임·고도흥 2002.)

---

## 참고

- [Yeo et al., GoP with Uncertainty Quantification (Interspeech 2023, arXiv:2305.18392)](https://arxiv.org/abs/2305.18392) · [코드(MIT)](https://github.com/juice500ml/dysarthria-gop)
- [Cao et al., Phoneme-Level Pronunciation Assessment Using CTC (Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/cao24b_interspeech.pdf)
- [Hu, Qian, Soong & Wang, GOP 변형(LPP/LPR), Speech Communication 2015](https://github.com/kaldi-asr/kaldi/blob/master/egs/gop_speechocean762/README.md)
- [Huang et al., Less peaky CTC forced alignment by label priors (ICASSP 2024, arXiv:2406.02560)](https://arxiv.org/abs/2406.02560)
- [speechocean762 (OpenSLR SLR101, CC BY 4.0)](https://www.openslr.org/101/) · [HF](https://huggingface.co/datasets/mispeech/speechocean762)
- [TORGO (토론토대 무료 배포)](https://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html)
- [Mendel et al., Corpus of deaf speech (JASA 2017)](https://pubs.aip.org/asa/jasa/article/142/1/EL102/662623/) · [SPAL 메타데이터](https://github.com/koenecke/ASR_dDhh_performance) · [U. Memphis CSD](https://www.memphis.edu/csd/research/)
- [AI Hub 608](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=608) · [71434](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71434) · [71393](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71393) · [안심존 안내](https://aihub.or.kr/intrcn/safetyzoneintrcn.do)
- [QoLT (LREC 2012)](https://aclanthology.org/L12-1196/) · [COPAS](https://taalmaterialen.ivdnt.org/download/tstc-corpus-pathologische-en-normale-spraak-copas/)
- [Speech Accessibility Project](https://speechaccessibilityproject.beckman.illinois.edu/) · [UASpeech](https://speechtechnology.web.illinois.edu/uaspeech/)
- [공용기관생명윤리위원회](https://www.irb.or.kr/menu02/commonConvention.aspx) · [개인정보보호법 제23조](https://www.law.go.kr/%EB%B2%95%EB%A0%B9/%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%EB%B3%B4%ED%98%B8%EB%B2%95/%EC%A0%9C23%EC%A1%B0)
- Osberger & McGarr (1982), Speech Production Characteristics of the Hearing Impaired
- 서경희·심홍임·고도흥 (2002), 청각장애 남성과 건청 남성이 산출한 단모음의 포먼트 특성, 언어치료연구 11(1)
