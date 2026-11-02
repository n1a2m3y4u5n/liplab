# C65 seed0 비교·내보내기 로컬 런타임 기술 부록

48a398cc의 학습과 d7068b06의 병렬 이전은 그대로 둔다. sub seed0은 40에폭/best39·종료0으로 끝났고 인계 watcher가 종료 후 controller만 중지했다. 현재 main seed1이 GPU를 사용하므로, 아직 한 번도 실행하지 않은 **seed0 최종 비교·FP32 내보내기만 유휴 sub에서 실행**한다. 이 부록을 먼저 커밋하고 실행한다. 학습·재개·시드/분할/배치/손실/관문 변경은 없다.

기존 sub Python3.13.3 환경에는 ONNX가 없었다. 같은 main 버전인 ONNX1.23.2와 ml_dtypes0.6.0의 호환 binary wheel 총8,311,846바이트를 공개 PyPI에서 받아 **자기 data/nextreg_fill3_2026-11/onnx-extras/**에만 배치했다. 기존 venv·frontend·공유 ROI 파일은 바꾸지 않았다. ONNX wheel cp312-abi3는 로컬3.13에서 합성 import/checker를 통과했고 ml_dtypes는 cp313 wheel이다. source build는 하지 않았다. numpy2.5.4/protobuf7.36.2/typing_extensions4.16.0은 기존 main·sub 버전이 같다. sub native ORT1.31.0과 main1.31.1, Python3.13.3/3.12.10 차이는 기록하며 기술 유효성 조건인 원경로↔wrapper↔ONNX CPU 최대오차<1e-3를 유지한다. WASM ORTWeb1.19.2/Node24/1스레드와 고정 입력·측정 순서는 바꾸지 않는다.

wheel SHA256은 ONNX `9b382ba898a7c142a0801d03cf04ecabced96c1543c7b643a86f0928143802de`, ml_dtypes `fb87f46b4f7ad7b5d3ad8f4b452b024bd4229d44c8ff934798c1fe656210387a`다. 두 값은 공개 PyPI metadata와 일치했다. 패키지 파일 manifest SHA는 `d05d73bcb51bb6e43a5ffbc1562dfb5c7b7d0f2063b5367e5fc54e16e2fa16f0`이며 공개 URL/ABI/파일별 해시·합성 Identity opset17 checker 근거는 out/onnx-runtime-deps에 보존했다. 이 준비에서는 후보 PT·실제 평가·Torch/GPU를 사용하지 않았다.

같은 `nextreg_distill65.py` SHA `92b916951fdb4975dc05b42ee09167ccd22dbb465cfb74f848516afa15468165`의 `finish --seed 0`을 그대로 사용한다. 선생 D499·prep084b793f…·학습33/검증12·AMP0/cap0.45·FP32/opset17·정확도차≥−.02/크기≤.75/WASM≤.60를 유지한다. 후보 PT는 인계 시 보존한 SHA `4355af944ba41736a12ff0c9e70dff395745f6d18ef2b6c3578688aff547a9ca`다. extras를 이 프로세스의 PYTHONPATH 앞에만 붙이고 기존 코드 경로를 뒤에 유지한다.

GPU 유휴·다른 Python/DACON 없음·RAM16GB 이상을 확인한 뒤 S4U로 분리 실행한다. main의 seed0 비교 작업은 시작하지 않았고, 준비된 main 경로에는 로컬 이전 표식을 남긴다. 로컬은 exclusive once 표식을 만든 뒤 한 번만 비교한다. 선택 JSON 이후 내보내기에 기술 실패가 생기더라도 재학습·재평가를 하지 않고 기존 선택을 보존해 기술 단계만 복구한다. 평가19/clean_eval/E2/KMSAV/OLKAVS·새 자료·앱/배포/푸시를 사용하거나 바꾸지 않는다.
