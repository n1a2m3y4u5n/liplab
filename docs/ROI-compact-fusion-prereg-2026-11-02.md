# 작은 ROI+입술80 결합 seed0 개발 선택 사전 등록

2026-11-02 `spec-gpu-fill2.md`의 후보A다. 용량 곡선에서 선택한38% ROI 구조에 기존 결합 모델과 **같은** 좌표80 잔차 경로를 붙여, 큰 결합 모델의 정확도 개선을 작은 기기용 구조에서도 유지하는지 묻는다. 검증12명 개발 선택이며 **판정 없음, 깨끗한 평가 대기**다. 앱·기본 플래그·배포를 바꾸지 않는다.

## 고정 방법과 참조

**증류하지 않고 처음부터 CTC로 학습한다.** full fusion과 같은 CTC 손실을 써서 작은 ROI 구조의 효과를 비교한다. 픽셀만 보는 B33 선생의 로짓을 강제하면 추가 좌표 정보를 억제할 수 있으므로 이번에는 KD를 섞지 않는다. 새 구조·손실·용량 탐색은 하지 않는다. 선행38% 학생의 가중치도 불러오지 않는다.

작은 경로는 `nextreg_roi_distill_capacity.build_student('38')`의 ROI256출력과 후단을 그대로 쓴다. 입력 정규화 후40×40 평균풀링, stem16, 잔차24·48·96·192 각1블록, 선형256, LayerNorm256→양방향GRU2층 hidden224 dropout0.2→자모53이다. 여기에 기존 `nextreg_roi_lips.models/install`과 같은 lips80→LayerNorm80→Linear64→GELU→Linear256 잔차를 프레임별 ROI256에 더한다. 작은 모델2,341,877파라미터(기존38%2,319,893+좌표21,984), 큰 결합6,068,989파라미터다. 저장 태그는 `compact38_roi256_plus_LN80_Linear64_GELU_Linear256_ctc_v1`로 별도다. 같은256 계약이어서 대체 후보가 필요하지 않다.

파일·속도 기준은 완료된 full fusion seed0 **한 파일**을 고정한다. `out/nextreg-2026-11-02/fusion/seed0/model.pt`의 SHA256은 **42b5fc382377c3a6db4567a989d372b741d8b34504323956bd92bb58ed084c35**다. 이 모델의 새 검증 재평가는 하지 않는다. 크기·속도는 이 고정 모델과 작은 모델을 동일한 새2입력 FP32 ONNX로 내보내 한 번 비교한다. 정확도 기준은 같은 시드 B33 seed0 선택 모델 SHA256 **d499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a**와 기존 학습 요약이며 다른 에폭을 다시 고르지 않는다.

## 자료·학습·개발 관문

원래 B33 prep 학습33명·검증12명과 ROI pack을 읽기 전용으로 쓴다. 기존 full fusion과 같은 lips pack, 프레임 offset·어절/문장 제외·분할·문항·idle·속도·crop·반전·시간마스크를 그대로 공유한다. 좌표 결측2프레임 보간·클립 삭제0이라는 기존 계약도 유지한다. 평가19명·clean_eval·E2·KMSAV·OLKAVS 사전학습·새 자료는 쓰지 않는다.

seed0 **한 번**, 처음부터 AdamW lr3e-4 wd1e-4, 배치32,4000유효 프레임 그룹(같은 배치 평균), 최대40에폭, 매2에폭 검증, patience6, 기울기5, idle0.5, 속도0.8~1.25, 기존 무작위80자르기·거울상0.5·시간마스크≤3, AMP bf16=1을 고정한다. full fusion과 같은4지 hard ctc_ll α1·idle75·dup1/2 각각 화자평균의 평균 최고 체크포인트를 선택한다. CER는 그 체크포인트의 검증 문장 자모CER다. resume·추가시드·기준 하향은 없다.

다음 **네 조건을 모두** 만족해야 수치 관문 통과다.

1. 같은 seed B33 대비 검증4지 차이 ≥ **+0.02**.
2. 같은 seed B33 대비 검증 문장CER 차이 ≤ **+0.02**.
3. 작은 FP32 ONNX 바이트 ≤ 고정 full fusion seed0 FP32 ONNX의 **40%**.
4. 같은PC·같은입력 WASM CPU 중앙시간 ≤ 고정 full fusion seed0의 **50%**.

별도 진행 중인 full fusion seed1이 기존 관문에서 미달이면 이 학습을 멈추거나 결과를 버리지 않는다. A의 네 수치 결과는 그대로 보고하고 **결합 미확정(combination_unconfirmed)**으로 표시한다. seed1 확인 전에는 확인 대기다. 통과 모델도 독립 확인이나 Android 실측 결과가 아니다.

## 두 입력 FP32 ONNX와 고정 WASM 측정

두 모델 모두 FP32·opset17, 입력 `roi[B,T,80,80]` 원화소0~255 float32와 `lips[B,T,80]` 얼굴 기준 정규화 좌표, 출력 `[B,T,53]`다. 내부에 원래 시퀀스별 ROI z정규화, 큰 모델 stem24/작은 모델 평균풀링40+stem16, 같은 좌표 잔차와 각 후단을 포함한다. B1T75 합성 입력에서 PyTorch 원경로↔wrapper 및 wrapper↔ONNX CPU 최대 로짓 차이 **<1e-3**를 기술 유효성 조건으로 둔다. 이를 넘으면 조용히 형식이나 기준을 바꾸지 않는다.

lab-sub CNSAi2025, Node24, 설치 ORTWeb1.19.2, WASM CPU EP1스레드에서 두 세션을 먼저 만든다. PRNG xorshift seed20261102를 공유해 ROI75×80×80개를 먼저 uint32%256으로 만들고 이어 lips75×80개를 uint32/2^32−0.5로 만들어 float32로 저장한다. 입력 SHA256은 ROI **3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7**, lips **7c8383e4a505b00880d73e2079d59cb4167efba8aa112109c8affb14b8ce9ad3**, 이어 붙인 입력 **0fe46e1232254fb6193d2fd25d295893394894f2058337f67d018fe771b6c2a8**로 시작 전에 고정했다. 실제 화자 입력은 사용하지 않는다.

모델당5회 예열 후 full→compact/compact→full 순서를 번갈아20쌍의 `session.run` walltime만 측정한다. 로딩·입력 생성·유효성 확인은 타이머 밖이다. 각20회 중앙값 비율, 원시 시간, PC/CPU/ORT/Node/입력/모델 SHA를 보존한다. 유리한 재측정·다른 PC·native ORT 시간으로 바꾸지 않는다.

## 장치·예상 시간·산출물

lab-main RTX3060 cap0.45, CPU2스레드, 미리읽기1개, S4U 예약 작업으로 연결과 독립 실행한다. 시작 전 nvidia-smi로 GPU/DACON 부재, 시스템 여유16GB 이상을 확인하고 Ollama를 내린다. 다른 작업은 중단하지 않는다. 예상 학습10~40분과 내보내기·WASM5~15분이며 실제 시간은 로그로 남긴다. OOM/기술 실패는 그대로 보고하고 설정을 바꿔 재시도하지 않는다.

원격 작업은 `D:\work\hq\projects\liplab-gpu2\nextreg_fill2_2026-11\compact_fusion\` 안에서만 한다. 기존 main `data/run_base`는 읽기 전용, 자기 `lips/`, `full_fusion_s0.pt`, `baseline_B33s0/` 참조 사본만 둔다. 산출물은 `D:\work\hq\projects\liplab\out\nextreg-2026-11-02\compact_fusion\`에 모델·요약·정확도 선택·두 ONNX·크기·WASM·최종4관문·로그·모델 카드를 회수한다. 소스와 등록만 커밋하며 모델·자료는 git에 넣지 않는다. 이 문서의 커밋 뒤에만 학습·내보내기·측정을 시작한다.

## 결과

미실행. 등록 전에 참조 파일 SHA와 합성 입력 SHA, 구조·입력 계약만 확인했다.

## 실행 기록

등록b0814cf9뒤main에서19:48:10 seed0프로세스(PID30352·32996)를시작했고GPU55%2965MiB와실제AMP1/CTC학습배치를확인했다.native좌표동기화/모델계수/합성wrapper검사를통과했다.시작전GPU Python/DACON없음·RAM57160372KiB및B33 prep SHA084b793f...와고정참조2개SHA를확인했다.기존full결합seed1은19:55:33에두관문을통과했으므로상위확인조건은충족됐지만,A자체4관문은아직별도대기다.파일/시간참조는고정seed0그대로다.

## 최종 결과: CTC 작은 결합 경로 NO-GO (20:19 KST)

학습19:48:10~20:16:57,40에폭/최고epoch39·1724초,비교/두입력FP32내보내기20:17:03종료코드0이다.고정WASM을20:19:25 한 번마쳤고finalize가모델/입력SHA·FP32/opset17·출력차이·20쌍중앙값과큰결합seed1통과를확인했다.

| 사전 관문 | 고정 기준→작은 결합 | 후보−기준/비율 | 결과 |
|---|---|---:|---|
|같은seed B33 4지차≥+.02|.4419497422→.4586568157|+0.0167070736|+2%p미달|
|같은seed B33 CER차≤+.02|.6777→.7021|+0.0244|+2%p초과|
|FP32 ONNX≤full결합s0의40%|24287736→9378759바이트|38.6152%|충족|
|같은PC WASM≤full결합s0의50%|466.71945→80.72570ms|17.2964%|충족|

**정확도개선+1.6707%p가하한+2%p에미달하고,CER증가+2.44%p가한도+2%p를넘으므로이처음부터CTC학습한작은결합구조는보류한다.** 파일/속도통과로두성능미달을대체하지않는다.큰결합seed1은통과했으므로상위상태는confirmed_seed1이지만A자체4관문중2개미달로overall_keep_path=false다.구조는구현가능했고두입력ONNX도기술조건을충족했으므로“구현상불가능할때”의대체실험조건은발생하지않았다.손실/시드/문턱을바꿔구제하지않았다.

참조full결합s0/PT SHA42b5fc382377c3a6db4567a989d372b741d8b34504323956bd92bb58ed084c35를끝까지유지했고,작은PT SHA4d0e11601002899f767074b1c1c7495ef88fc5bdf4113aa90c7d357e3a83b598를원격기록과회수본에서대조했다.B33s0정확도기준도d499c9...로고정했다.큰결합s1성능으로참조를갈아끼우지않았다.

out/compact_fusion에model.pt·train_summary.json·architecture.json·accuracy-selection.json·export.json·full/compact.onnx·wasm.json·selection.json·모든로그·모델카드를회수했다.두입력은rawroi[1,75,80,80]와동일프레임정규화lips[1,75,80]이고,검증12명개발선택/판정없음이다.Android실측·앱반영은없고평가19·clean_eval·E2·KMSAV는사용하지않았다.공유원본은보존하고자기입력사본을정리한다.
