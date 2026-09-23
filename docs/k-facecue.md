# 입술 너머 확장 조음 단서(축 K) — 소규모 실증 기록

고도화계획서 §3.11(K)의 목표 수준은 "설계와 소규모 실증"이다. 입술 밖의 얼굴 움직임(턱·볼·콧방울)에서
입모양으로 보이지 않는 자질(유성, 비음)을 추정할 수 있는지 시험했다. 제품에는 웹캠 입모양 연습 화면
(`frontend/src/components/WebcamMouthCheck.jsx`)이 브라우저에서 `public/k-model/facecue_k.onnx`로 추론한다.

## 1. 방법

- **입력.** MediaPipe 얼굴 블렌드셰이프 8차원: `jawOpen`, `cheekPuff`, `cheekSquintLeft/Right`,
  `noseSneerLeft/Right`, `mouthPressLeft/Right`. 30프레임 창(`public/k-model/meta.json`).
- **라벨.** 같은 클립의 음성에서 자동으로 만든다. 유성은 pYIN 유성 판정, 비음은 주파수 대역 에너지 비율 휴리스틱.
  사람이 붙인 라벨이 아니라 음향에서 파생한 대리 라벨이다.
- **모델.** BiGRU 분류기(유성·비음 2출력). 평가는 학습에 쓰지 않은 화자(홀드아웃)로 한다.
- **데이터.** AI Hub 538(OLKAVS) 문장 영상.

## 2. 결과

| 실험 | 데이터 | 유성 AUC | 비음 AUC | 평균 AUC |
|---|---|---|---|---|
| 2026-09-16 초기(제품 탑재판) | 16클립, 홀드아웃 spk55142 | 0.55–0.59 | 0.60–0.64 | 0.596 |
| 확대 1 | 160클립 | – | – | 0.705 |
| 확대 2 | 1,115클립 | – | – | 0.680 |
| 확대 2 + 미세 움직임 확대(EVM) 전처리 | 1,115클립 | – | – | 약 0.69 (+0.01) |

(확대 실험은 평균 AUC만 기록되어 있다. 원자료는 `liplab-lab/notes/09-gpu-results.md`와 연구 메모.)

## 3. 해석과 결정

- **비음은 얼굴에 일부 드러난다.** 비음 AUC가 우연(0.5)보다 높게 나왔다. 제품은 비음 확률만 보여 준다.
- **유성은 얼굴에서 거의 읽히지 않는다(K-3).** 유성 AUC는 우연 수준이라 제품 화면에서 숨겼다. 이것은 실패가 아니라
  부정 결과로 기록한다. 유성은 성대 진동이라 목(후두) 부위가 단서인데, MediaPipe 얼굴 메시는 목을 덮지 않는다(K-1).
  목 부위를 보려면 별도 랜드마크 모델이 필요하다.
- **데이터를 늘려도 오르지 않았다.** 160클립 0.705에서 1,115클립 0.680으로, 데이터가 7배가 되어도 오르지 않았다.
  라벨이 음향에서 만든 대리 지표라 라벨 품질이 한계로 보인다.
- **미세 움직임 확대(EVM)는 채택하지 않았다(K-8).** +0.01의 이득에 비해 전처리 비용이 커서 넣지 않았다.

## 4. 불일치와 재현성(K-13)

- 제품에 탑재된 모델은 16클립판(평균 AUC 0.596)이다. 보고서에 160클립 수치(0.705)를 쓸 때는 제품 모델과 다른
  실험임을 함께 밝혀야 한다. 160클립판을 제품에 넣으려면 그 체크포인트를 ONNX로 다시 내보내야 한다.
- 파드에서 쓴 학습·라벨 생성 스크립트는 `/tmp`에 있다가 사라졌다. 재현하려면 위 방법대로 다시 작성해야 하며,
  pYIN 설정과 비음 대역 경계 같은 세부 값은 남아 있지 않다.

## 5. 남은 일

- K→J 연결(K-4): 웹캠 연습 중 비음 확률이 높으면 J의 '울림' 기호를 켜서, 추정 신호를 기호로 보여 준다.
  원래 설계는 화자 영상에서 뽑은 신호를 학습자에게 보여 주는 것이지만, 앱에는 실제 화자 영상이 없어
  학습자 본인의 발화에 대한 되먹임으로 먼저 연결한다.
- K→B 융합(K-5)과 목 부위 재시도(K-1)는 결정 사항이다.
- 당사자 발화로 보정(K-12)은 파일럿 뒤에 한다.

## 6. 근거

- Ladefoged, P., & Johnson, K. (2014). *A course in phonetics* (7th ed.). Cengage Learning.
  비음의 연구개 하강, 유성의 성대 진동 등 조음음성학 관찰.
- Zhang, Y., Yang, S., Xiao, J., Shan, S., & Chen, X. (2020). Can we read speech beyond the lips? Rethinking RoI
  selection for deep visual speech recognition. In *Proceedings of the 15th IEEE International Conference on
  Automatic Face and Gesture Recognition (FG 2020)*. 입술 밖 얼굴 영역이 립리딩 정확도를 높인다는 결과.
- Wu, H.-Y., Rubinstein, M., Shih, E., Guttag, J., Durand, F., & Freeman, W. T. (2012). Eulerian video
  magnification for revealing subtle changes in the world. *ACM Transactions on Graphics, 31*(4), 65.
  미세 움직임 확대(EVM).
