# GPU 개발 C·D·F 검증 완료 (2026-10-28)

- backend 전체: 921 passed, 11 warnings, 1752.35s. PYTHONUTF8=1, 공유 main .venv, 현재 gpu-dev 작업트리 backend에서 실행. 기존 datetime/audio 경고만 남음.
- frontend 전체: 396 tests, 396 pass, 0 fail.
- npx vite build: 통과14.43초, 기존 큰 chunk 경고.
- 앱 코드·플래그·기본값 변경 없음. predeploy는 실행하지 않았다.
- 실험: 사전등록된 D-GOP ONNX 스레드 비교 탐색27회; 후보 출력 관문 미달로 선택null·확인0회. 실패한 후보를 통과했다고 하지 않는다.
- C: 중복 비교0회, 대리 관문 미달로 우위 판정 없음.
- D: 허용 학습 자료 없음, E2 보존, V3/V17 학습0회.
- 산출물: D:/work/hq/projects/liplab/out/gpu-dev-2026-10-28.md 및 model-dev-candidates-2026-10-28.md, gpu-dev-*-2026-10-28 로그/JSON.
- 배포·push·유료 사용 없음. 남은 재학습은 자료와 독립 확인 집합 조건을 충족한 뒤 별도 실행등록부터 진행한다.
