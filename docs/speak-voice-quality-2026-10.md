# 발성 단계 목소리 지표: 음높이 수준·안정도·목소리 질(S24, 2026-10-07, 측정 전 사전 등록)

종합 계획 `docs/master-plan-2026-10.md`의 S24(아이디어 다6)다. 1~6절은 결과를 보기 전에 적었고, 탐색 절반을 열기 전에 분석 스크립트와 함께 커밋한다.
탐색 절반에서 정한 값(방향·성별 기준·상관 부호)은 7절에 따로 커밋한 뒤 확인 절반을 연다.

## 1. 질문

말하기 0단계(발성)는 지금 크기와 이어 낸 길이만 본다. 청각장애 화자의 발성은 음높이가 높거나 흔들리고 목소리 질이 다르다고 보고되어 왔다
(Monsen 1979는 청각장애 아동의 음높이·주기 사이 변화·억양 곡선을 측정했다). 음성 평가에서 쓰는 표준 지표가 이 자료에서 608(청각장애)과
538(건청)을 가르고, 608 안에서 문장 전사 오류율(CER, 알아듣기 어려움의 대리 지표)과 함께 움직이면 발성 단계에 넣을 근거가 된다.

## 2. 지표(`backend/voice_quality.py`, numpy만)

Praat(parselmouth)는 GPL이라 앱에 넣지 않는다. 같은 정의를 numpy로 다시 구현하고, 측정에서만 Praat 값과 순위상관을 보고한다(판정에는 쓰지 않음).

| 지표 | 정의 | 근거 |
|---|---|---|
| f0_level_st | 유성 프레임 음높이 중앙값의 성별 기준 대비 반음. 기준 = 538 절반 0 같은 성별 클립 중앙값들의 중앙값 | 음높이 수준 |
| f0_sd_st | 유성 프레임 음높이(문장 중앙값 기준 반음)의 표준편차 | 음높이 안정도(억양 포함) |
| f0_step_st | 이어진 유성 프레임(10ms) 사이 음높이 차(반음) 절댓값의 중앙값 | 짧은 시간 음높이 흔들림 |
| jitter_local | 이웃 주기 차 절댓값 평균 / 주기 평균(%), 주기 0.0001~0.02초, 이웃 비 ≤ 1.3 | Praat jitter (local) |
| shimmer_local | 이웃 주기 진폭 차 절댓값 평균 / 진폭 평균(%), 진폭 비 ≤ 1.6 | Praat shimmer (local) |
| hnr_db | 유성 프레임 정규화 자기상관 r의 10·log10(r / (1 − r)) 평균 | Boersma 1993 |
| cpps_db | 평활 켑스트럼 봉우리(60~330Hz)와 회귀선의 차, 말소리 창 평균 | Hillenbrand·Houde 1996, Maryn 등 2009 |

- 음높이: 40ms Hann 창·10ms 간격, 창 자기상관으로 나눈 정규화 자기상관(Boersma 1993), 75~500Hz, 옥타브 비용 0.01, 유성 문턱 R ≥ 0.45,
  창 RMS가 최대 창의 −30dB 이상. 이어진 유성 구간의 중앙값에서 7반음 넘게 벗어난 창은 두 배·절반으로 고치거나 무성으로.
- 주기 표시: 국소 주기 0.8~1.2배 범위의 양의 최댓값을 차례로(포물선 보간). Praat 'cc' 방식과 다르므로 jitter·shimmer 값의 절대 크기는 Praat와 다를 수 있다.
- 값이 없음: 유성 0.2초 미만이면 음높이 지표, 주기 20개 미만이면 jitter·shimmer가 없고 그 지표의 판정에서 그 문장을 뺀다.
- ASHA 권고 절차(Patel 등 2018)는 연결 발화에서 CPP를, 지속 모음에서 jitter·shimmer·HNR을 함께 보도록 권한다. 이 자료에는 지속 모음이 없어
  모두 문장에서 잰다(5절 한계).

## 3. 자료

- 608 범주 28(감음신경성): 10/6 문장 컷 363개 가운데 길이 0.4~15초인 322개(24명). 화자 절반 crc32(이니셜) % 2(10/6과 같음).
  CER: 10/6 앱 설정 전사(faster-whisper base, vad 없음, `asr.json`) 대 대본 문장, 한글·숫자·영문만 남긴 글자 편집 거리 / 대본 길이.
- 538: 스냅숏 클립 1,740개(58명), 화자 절반 crc32(화자 ID) % 2, 같은 방식의 CER(보고만).
- 범주 27 짝 세션 컷은 전사가 없어 지표만 뽑고 판정에 쓰지 않는다.

## 4. 판정 기준(지표마다, 절반 1)

탐색(절반 0): 지표마다 방향(608이 큰 쪽이면 +1)을 AUC로, 608 안 CER과의 스피어만 ρ 부호를 정하고, f0_level_st의 성별 기준을 정한다.

확인(절반 1), 둘 다 만족하면 통과:
- A: 608 대 538 문장 단위 AUC(탐색에서 정한 방향) ≥ 0.70.
- B: 608 안 문장 단위 스피어만 |ρ(지표, CER)| ≥ 0.30이고 부호가 탐색과 같음.

보고만: 화자 단위 부트스트랩 95% 구간(2,000회), 화자 평균 AUC, 성별 AUC, 538 안 ρ, Praat 값과의 순위상관과 Praat 값의 같은 수치, 녹음 조건 차를
보는 잡음 바닥(창 RMS 10백분위 − 최댓값) AUC. 잡음 바닥 AUC가 높으면 A는 녹음 조건 차를 함께 담고 있다는 뜻이고, 그 경우에도 B(608 안 상관)는
녹음 조건과 독립이라 판정은 그대로 두되 해석에 적는다.

## 5. 앱 반영 규칙(통과한 지표만)

- 서버가 0단계 녹음에서 지표를 내어(`voice_quality.features`) 채점 응답과 시도 기록에 넣고, 화면에 '참고' 값과 538 범위(5~95백분위)를 보인다.
  범위 밖이면 한 문장 안내를 붙인다.
- 0단계 합격·점수는 바꾸지 않는다. 근거가 낭독 문장이고 앱은 지속 모음인 데다, 브라우저 잡음 억제가 켜져 있고 jitter·shimmer는 크기에 민감하다
  (Brockmann 등 2011). 지속 모음 자료로 다시 확인하기 전에는 합격선에 쓰지 않는다.
- 통과한 지표가 없으면 앱은 그대로 두고 결과만 적는다.

## 6. 한계(미리)

- 538(영상 녹화)과 608(음성 녹음)은 녹음 장비·환경이 달라 A는 집단 차와 녹음 조건 차를 함께 본다. B가 이를 보완하는 기준이다.
- 608 절반 1은 11명 약 140문장이다. 문장 단위 ρ는 화자 사이 차이가 크게 차지한다(화자 부트스트랩 구간으로 본다).
- CER은 앱 전사기의 오류율이라 사람의 명료도 판정과 같지 않다.

## 참고 문헌

- Boersma, P. (1993). Accurate short-term analysis of the fundamental frequency and the harmonics-to-noise ratio of a sampled sound. IFA Proceedings 17, 97–110.
- Brockmann, M., Drinnan, M. J., Storck, C., & Carding, P. N. (2011). Reliable jitter and shimmer measurements in voice clinics. Journal of Voice, 25(1), 44–53.
- Hillenbrand, J., & Houde, R. A. (1996). Acoustic correlates of breathy vocal quality: Dysphonic voices and continuous speech. JSHR, 39(2), 311–321.
- Maryn, Y., Roy, N., De Bodt, M., Van Cauwenberge, P., & Corthals, P. (2009). Acoustic measurement of overall voice quality: A meta-analysis. JASA, 126(5), 2619–2634.
- Monsen, R. B. (1979). Acoustic qualities of phonation in young hearing-impaired children. JSHR, 22(2), 270–288.
- Patel, R. R., Awan, S. N., Barkmeier-Kraemer, J., 외 (2018). Recommended protocols for instrumental assessment of voice. AJSLP, 27(3), 887–905.
