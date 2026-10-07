# 소리 듣기 고도화 근거 정리 (2026-10-07)

`docs/listen-advance-plan-2026-10.md`의 후보마다 근거를 정리한다. 10/7 하위 조사 다섯 건(Ling·P.56·전화, 블루투스 지연·시청각 비동기,
적응 절차·재검사 신뢰도, 피드백·보코더·화자 다양성, 소음·따라 말하기·표적 훈련)의 결과를 모은 것이다.
표시: [본문 확인] 원문을 직접 읽음, [초록] 초록만, [2차] 다른 문헌의 인용. 수치는 원문 그대로 옮겼고, 괄호 안 '계산'은 정리하면서 한 산술이다.
설계 근거의 1차 정리는 `docs/auditory-training-evidence-2026-10.md`에 있다(겹치는 내용은 줄였다).

## 1. Ling 6소리의 크기와 대역 (F2)

- Scollie·Glista, Ling-6(HL) 사용 안내(2012) [본문 확인]: 여성 화자, 정상 청력자가 dB HL에서 평평한 역치를 얻도록 자극을 다듬었다. 정상 성인 보정값
  /m/ −5, /u/ −5, /a/ −5, /i/ −5, /ʃ/ −10, /s/ −15 dB. https://www.Phonak.com/content/dam/phonak/en/documents/evidence/ling-6hl_instructions.pdf.coredownload.pdf
- Tenhaaf·Scollie 2005(Canadian Acoustics 33(3)) [본문 확인]: 보정 컴퓨터 Ling 검사도 자극을 같은 길이·같은 최대 크기로 맞췄다.
  https://jcaa.caa-aca.ca/index.php/jcaa/article/download/1737/1484/1874
- 자연 말소리에서 /s/는 모음보다 훨씬 약하다(Ladefoged 교재 예시: [s]가 /i/보다 약 17 dB, /ɔ/보다 약 27 dB 약함) [2차].
  https://homepage.ntu.edu.tw/~karchung/Phonetics%20II%20page%20twelve.htm
- 대역(BATOD 2022) [2차]: /m/ 400 Hz 아래, /u/ F1 250~500·F2 700~1200, /a/ F1 500~700·F2 1~1.4 kHz, /i/ F1 200~400·F2 2300~3500,
  /ʃ/ 2 kHz 위, /s/ 4 kHz 위. https://www.batod.org.uk/wp-content/uploads/2022/09/The-Ling-6-Sound-Test.pdf

**결론.** 감지 점검은 임상 보정 검사처럼 크기를 같게 맞추는 지금 방식이 맞다. 자연 대화 크기를 흉내 내는 별도 모드는 2차 자료뿐이라 임상 값으로 내세우지 않는다.

## 2. SNR의 말소리 레벨 (F1)

- ITU-T P.56 방법 B(Kabal 1999 설명) [본문 확인]: |x|를 시간 상수 0.03초로 두 번 지수 평활, 유지 시간 0.2초, 문턱 c_j = 2^j(15단계),
  활성 레벨 A와 문턱 레벨 C의 차이가 15.9 dB가 되는 지점을 보간. 배경 잡음이 섞인 말에는 맞지 않고, SNR은 말 활성 레벨 대 잡음 RMS다.
  https://www.mmsp.ece.mcgill.ca/Documents/Reports/1999/KabalR1999.pdf, VOICEBOX v_activlev
  https://raw.githubusercontent.com/ImperialCollegeLondon/sap-voicebox/master/voicebox/v_activlev.m
- HINT(Nilsson·Soli·Sullivan 1994) [본문 확인]: 문장 앞뒤 무음을 잘라 낸 뒤 평균 제곱 레벨을 계산해 모든 문장을 67 dB로 맞췄다. 잡음은 문장 장기
  평균 스펙트럼으로 거른 백색 잡음, 같은 레벨. https://auditory.org/mhonarc/2025/pdfEbGPhck23j.pdf
- Matrix 검사 권고(ICRA, Akeroyd 외 2015) [본문 확인]: 잡음은 말과 같은 장기 스펙트럼, 65 dB SPL 고정, 말 레벨을 바꾼다.
  https://icra-audiology.org/wp-content/uploads/2024/11/Recommendations-for-multilingual-speech-tests.pdf

**결론.** 무음까지 포함한 전체 RMS는 표준이 아니다(무음 30%면 약 1.5 dB 오차, 계산). 활성 레벨로 바꿨다(12197a1).

## 3. 전화 소리 (S4)

- 인공와우 사용자에게 300~3400 Hz 대역 제한만으로 문장 인식이 약 17% 떨어졌다(Liu·Fu·Narayanan 2009, 9차 버터워스, 코덱 없음) [본문 확인].
  Milchard·Cullington 2004: 17.7% 감소 [초록].
- 실제 통신망 차이는 훨씬 크다: Mantokoudis 2017 인공와우 19명, 손실 0%에서 Skype 91.6% 대 유선 42.5% [본문 확인(도구 요약)].
- 대역 제한 음성으로 훈련한 무작위 시험(Ihler 외 2017, 인공와우 20명): 70.7 → 78.9% 대 70.0 → 73.6%, P = .034 [초록].

**결론.** 대역 제한 모의는 문헌에서 널리 쓰이고 훈련 근거도 있다. 가파른 필터, 8 kHz 표본화, μ-law를 더했다. 실제 전화 어려움을 재현한다고는 말하지 않는다.

## 4. 블루투스 지연과 시청각 비동기 (F3)

- ASHA(안드로이드 보청기) 규격 [본문 확인]: 지연 목표 수치는 없고, 버퍼 깊이 8 × 연결 간격 20 ms(약 160 ms, 계산). 기기가 RenderDelay를 알려 영상
  지연에 쓰게 한다. https://source.android.com/docs/core/connect/bluetooth/asha
- LE Audio(Hunn 2022) [본문 확인]: 최적화하면 약 20 ms, 기본 표시 지연 40 ms. 일반 블루투스 음악 스트리밍 100~200 ms.
- 시청각 비동기 허용(소리가 늦을 때 양수):
  - Grant·van Wassenhove·Poeppel 2004: 동기 감지 약 −45 ~ +200 ms [초록].
  - Başkent·Bazo 2011, 청각장애 11명: 소리 앞섬 50% 지점 −122 ms, 늦음 +210 ms, 정상과 차이 없음 [본문 확인].
  - Hay-McCutcheon 2009: 인공와우 중년 −136 / +261 ms, 고령 −154 / +296 ms [본문 확인].
  - EBU R37: 소리가 그림보다 앞섬 ≤ 40 ms, 늦음 ≤ 60 ms [본문 확인].
- Web Audio outputLatency [본문 확인]: Chrome 102·Firefox 70·Safari 18.4. 블루투스에서 실제보다 작게 나온다는 사용자 보고가 있다 [2차].

**결론.** 출력 지연만큼 입모양을 늦추되 소리가 앞서지 않게 덜 보정한다(80%, 최대 250 ms), 지연값을 기록한다(dd27c1a).

## 5. 적응 절차와 재검사 신뢰도 (M1·M2·F4)

- 같은 20문장 재료에서 개인 내 SD: 문장 단위 1-up-1-down 1.1 dB 대 낱말 점수(Brand·Kollmeier) 0.4 dB(Jansen 외 2012 프랑스 Matrix) [본문 확인].
- 몬테카를로(Dingemanse·Goedegebure 2020): 문장 2 dB 0.92, HINT식 약 0.73, 낱말 점수 0.55~0.58 dB. 이론 최소(낱말 점수 20문장) 정상 0.616,
  인공와우 1.77 dB [본문 확인]. https://repub.eur.nl/pub/127230/Repub_127230_O-A.pdf
- 낱말 점수 규칙(ICRA 표1 각주): SNR_next = SNR − f(i)·(p − tar)/slope, f(i) = 1.5·1.41^(−i), 하한 0.1 [본문 확인].
- K-HINT: 문장 이해도는 SNR 1 dB당 약 9%(Moon 2005) [초록], Matrix 15~17%/dB보다 완만하다.
- 한국어 Matrix 재검사(Jung 2021·2022): 말소리 모양 잡음 MDC 정상 0.92~1.21, 청각장애 2.06 dB [본문 확인(도구 요약)].
- 훈련 목표치: 최적 정답률 약 85%(Wilson 2019, 이론) [본문 확인(도구 요약)], 65% 저정확도 훈련은 피드백 없이는 학습 없음(Liu·Lu·Dosher 2012)
  [본문 확인], 지각 학습은 보통 약 75%(Micheyl 2009) [2차], 계속 어려운 시간 압축 말 훈련이 가장 작은 효과(Gabay 2017) [초록].
- 2 dB 문구의 출처 추정: Plomp·Mimpen의 '신뢰도 1 dB면 측정값이 참값과 2 dB 안' 표현은 측정 한 번 대 참값이고, 두 측정 비교는 약 2.8 dB다.

**결론.** 지금 검사로는 MDC 약 3 dB(시뮬레이션 2.84 → 3.0)로 문구를 바꿨다. 낱말 점수·베이지안 절차와 훈련 목표 상향은 시뮬레이션
(`docs/listen-adaptive-sim-2026-10.md`)에서 사전 기준을 넘지 못해 넣지 않았다.

## 6. 피드백: 글 먼저, 같은 왜곡 소리 다시 (L1)

- Davis 외 2005 [본문 확인]: 6채널 보코더 30문장에 0%에서 약 70%. 왜곡-깨끗-왜곡(DCD)이 왜곡-왜곡-깨끗보다 학습이 빠르고(F1(1,40) = 5.77),
  글을 보인 뒤 왜곡 소리(DWD)는 깨끗한 소리 피드백과 같은 크기. https://www.mrc-cbu.cam.ac.uk/personal/matt.davis/pubs/davis_et_al_JEPG_2005.pdf
- Loebach·Pisoni·Svirsky 2010 [본문 확인]: 왜곡 소리 + 글 .42 → .63, 깨끗한 소리 피드백 .37 → .52, 피드백 없음 .36 → .52. https://pmc.ncbi.nlm.nih.gov/articles/PMC2818425
- Sohoglu 2014 [본문 확인]: 글이 소리보다 먼저일 때 효과가 가장 크고, 소리 시작 뒤 120 ms를 넘으면 줄었다.

**결론.** 틀린 문장은 정답 글을 보인 뒤 같은 소음·SNR로 자동 한 번 더 들려준다(afeb426).

## 7. 정상 청력자 보코더 훈련 (V2)

- Nogaki·Fu·Galvin 2007 [본문 확인]: 5회 1시간, 문장 30.2 → 54.7%, 주당 횟수는 차이 없음. https://pmc.ncbi.nlm.nih.gov/articles/PMC3580208
- Stacey·Summerfield 2007 [본문 확인]: 여러 화자 훈련 +12 대 한 화자 +7 %p(3 mm 이동), 새 화자 13.1 대 8.6 %p(p = .051).
- Loebach·Pisoni 2008 [본문 확인]: 약 45분에 문장 .40 → .64. 노출 없음 집단도 +11 %p(Loebach 2010) → 대조군이 꼭 필요하다.

**결론.** 대조군이 있으면 학습 연구로 유효하다. 주장은 기제까지이고 임상 효과는 아니다(`docs/pilot/listen-vocoder-pilot-prereg.md`).

## 8. 화자 다양성과 합성음 (목소리 묶음, S2·S3)

- 여러 화자 훈련(Logan 1991, Lively 1993, Bradlow 1997) [본문 확인]은 새 화자로 일반화되지만, 한 화자 훈련은 그렇지 않았다.
- Perrachione 외 2011 [본문 확인]: 잘하는 학습자는 여러 화자가 도움(d = 0.73), 서툰 학습자는 방해(d = 1.30), 묶어서 내면 도움.
- 합성음 대 실제 말: 신경망 TTS가 정상 청력자에게 약 1.2 dB 쉬움(Ibelings 2022) [본문 확인], 인공와우 사용자에게는 합성음 손해가 더 큼
  (Ji 2013, Shi 2018) [본문 확인]. 합성음 훈련이 실제 말로 옮겨 가는지 직접 시험한 청각장애 연구는 찾지 못했다.

**결론.** 숙달 50 전에는 목소리를 묶음 단위로 낸다(afeb426). 실제 사람 녹음 검사 세트가 필요하다.

## 9. 소음 종류와 잔향 (S1)

- 잡담 화자 수 효과는 단조롭지 않다(Simpson·Cooke 2005: N = 8에서 최저) [본문 확인]. Rosen 2013: 1 → 2명에서 가장 크게 나빠짐 [본문 확인].
- 인공와우 사용자는 경쟁 화자 1명이 가장 어렵다: Chen 2020 1명 +5.9 dB, 4명 +2.8 dB(정상은 반대 −22.0 → −5.2 dB) [본문 확인].
- 잔향: 인공와우 문장 인식 90% → RT60 0.3초 약 60% → 1.0초 약 20%(Kokkinakis 2011) [본문 확인]. 여러 방에서 훈련할 때만 새 방으로 일반화
  (Vlahou 2019) [본문 확인].

**결론.** 잡음은 종류별로 따로 두고 5단계에서 돌린다(talker2는 일반화용). 잔향 0.3·0.5·0.8초를 문항마다 바꾼다(de6fd2c, 435af80).

## 10. 표적 대조 훈련과 따라 말하기 (P1·L2)

- Fu 외 2005 인공와우 10명: 보기 수와 소리 유사도를 자동 조절, 모음 +15.8, 자음 +13.5 %p [본문 확인(2차 문헌 전문)].
- Woods 2015 보청기 16명: 자음마다 적응 SNR, 자음 역치 9.1 dB 향상, 문장 전이 0.46 dB(유의하지 않음) [본문 확인].
- 혼동행렬로 문항을 고르는 방식 자체를 시험한 연구는 찾지 못했다 → 학습자를 둘로 나눠 표적·무작위를 비교 기록한다.
- 따라 말하기(shadowing)를 인공와우·보청기 훈련으로 통제 시험한 연구는 없다. 가장 가까운 것은 말 따라잡기(tracking)로, 묶음 프로그램 안에서 도움.
  → 넣더라도 선택 연습으로 두고 앱 안에서 평가한다.

## 11. 확인하지 못한 것

Scollie 2012 소리별 dB SPL 표, Ling 원저의 대역 설명, Fletcher 1953 음소별 크기 표, Kollmeier 2015·Wagener 1999 본문, P.56 원문(Kabal·VOICEBOX로 확인),
MFi 보청기·인공와우 스트리밍 실측 지연, K-HINT 재검사 SD, Hervais-Adelman 2008·2011 수치.
