# ROI + 좌표80 브라우저 입력 준비

`VITE_LIPREAD_FUSION`은 미설정/0이면 기존 R2 경로다. `1`일 때만 같은 FaceLandmarker 결과에서 좌표80을 보존하고 두 입력을 전달한다. `VITE_LIPREAD_ROI=1`도 필요하다. 기본값, 채점, StageGate, API와 DB는 바꾸지 않는다.

모델은 저장소나 public에 복사하지 않는다. 로컬 개발 서버에서만 다음 환경변수로 연결할 수 있다.

```powershell
$env:VITE_LIPREAD_ROI='1'
$env:VITE_LIPREAD_FUSION='1'
$env:VITE_LIPREAD_FUSION_MODEL_URL='http://127.0.0.1:5190/fusion.onnx'
$env:VITE_LIPREAD_FUSION_META_URL='http://127.0.0.1:5190/fusion.meta.json'
npx vite --host 127.0.0.1
```

위 URL은 예시다. 별도 로컬 HTTP 서버의 루트는 승인된 산출물 폴더의 임시 모델 경로로 한정하고 Vite 원점에 대한 CORS를 제공해야 한다. 새 모델을 다운로드하거나 public으로 복사하지 않는다. 메타데이터는 해당 모델의 `n_vocab`, `vocab`, `alpha`를 담아야 한다. 프로덕션에서는 fusion 세션 로드를 거부한다. 켬 빌드는 크기 측정용이며 배포 대상이 아니다.

세션은 입력 이름 `roi_z`, `lips` 두 개를 확인한다. 각각 float32 `[1,T,80,80]`, `[1,T,80]`이며 idle75 창에서는 T=75다. 실제 ONNX 파일의 이 이름과 메타데이터를 확인하기 전에는 모델 연결 완료로 보지 않는다. 이름이 다르면 조용히 순서로 맞추지 않고 로드를 실패시킨다. 기존 ROI와 같이 75보다 긴 녹화는 자르거나 시간축을 재표본화하지 않고 T를 보존한다. 고정 T=75 모델을 연결할 경우 호출자가 양쪽에 같은 선택 인덱스를 제공해야 한다.

좌표 순서는 `extract_blendshapes.py`의 고정 LIPS_IDX 40점이다. x*W/y*H 픽셀에서 33→263 눈꼬리 roll을 제거하고 입술40점 중심/눈꼬리 거리로 정규화한다. y는 아래가 양수이며 Python `round(float,4)`와 같은 이진 double 반올림을 쓴다. 화면 CSS의 거울 효과를 입력에 적용하지 않는다. 캔버스는 원영상 방향 그대로이며 학습의 임의 반전 증강은 추론 때 수행하지 않는다.

좌표는 ROI와 같은 `gridSources`를 쓴다. 같은 격자 중복은 마지막 소스가 이기고, 빈 격자는 원검출로 표시하지 않는다. `scripts/nextreg_roi_lips.py:prepare`처럼 먼저 float32로 저장한 다음 각 채널을 선형 보간하고 양끝을 반복한다. 전체 결측이면 0을 만들지만 실제 predict에서는 추론을 거부한다. `det`/`valid`는 원래 관측 마스크이며, `interpolated`는 채운 프레임 표시다. 긴 결측도 수치 보간은 하되 유효 관측으로 바꾸지 않는다. 개발 자료의 결측 2프레임 이력을 실카메라 허용 관문으로 일반화하지 않는다.

`fusionModelInput`은 선택 인덱스를 두 입력과 마스크에 공유한다. 75 미만은 왼쪽 floor((75-T)/2), 오른쪽 나머지를 반복한다. 이는 Python `roi_train.py:p4_window`에서 같은 화자 idle 자료가 없는 경우의 fallback이다. 학습의 다른 화자 idle 프레임을 카메라에서 만들어 내지 않는다. ROI는 기존 roiModelInput으로 중앙80 crop/전체 시퀀스 z 정규화를 하고 좌표에는 별도 z 정규화를 하지 않는다.

검증 명령(새 패키지 설치 없음):

```powershell
# worktree 루트
python scripts/fusionweb_parity.py --out D:\work\hq\projects\liplab\out\fusionweb-2026-11-02\parity.json
# frontend 안
npm test
npx vite build --outDir D:/work/hq/projects/liplab/out/fusionweb-2026-11-02/build-off
# VITE_LIPREAD_FUSION=1로 같은 명령을 build-on에 실행한다.
```

`fusionweb_measure.mjs`는 127.0.0.1:5187의 Vite와 이미 설치된 Playwright/Chrome을 사용한다. 무음 headless Chromium에서 640×360 합성 캔버스와 고정 랜드마크를 사용하고, 기존 grabRoiFrame 대비 좌표 추출 추가분을 100프레임×20쌍 교대 순서로 측정한다. 얼굴 검출·모델 추론·네트워크·실카메라 지연은 포함하지 않는다. 첫 묶음은 index.html의 entry/modulepreload/CSS 합계이며 지연 로딩 LipReadCheck 청크는 별도 집계한다. 금지된 평가 자료, 실제 영상/음성은 사용하지 않는다. 실카메라와 실제 결합 ONNX 추론은 미확인이다.
