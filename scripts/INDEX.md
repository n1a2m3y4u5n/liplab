# scripts 색인 (11/03 검토 M29)

`scripts/` 최상위에 파일이 약 240개 평평하게 있다. 이름 접두어로 찾는다. 일회성 큐·파드 스크립트는 그 실험의 문서(`docs/`)와 짝이다.

## 배포·운영 (자주 쓰는 것)
| 파일 | 용도 |
|---|---|
| `predeploy_dev.ps1` | liplab-dev 배포 전 관문(pytest·npm test·빌드·감사·lock 일치·모델 sha256·전시앱 설정 불변·후보 배선 끔 동일성·채점 회귀) |
| `deploy_dev.ps1` | liplab-dev 배포(관문 표식 대조 → 직전 이미지 기록 → DB 사본 → 배포 → `/health/ready` → 스모크 → 실패 시 되돌림). 전시앱에는 쓰지 않는다 |
| `smoke_dev.py` | 배포 뒤 스모크(고정 스모크 계정, 말하기 채점 포함) |
| `check_assets.py`, `dev_assets.sha256.json` | git 밖 모델 파일의 sha256 대조·기록 |
| `check_config.py` | `fly.toml`·Dockerfile ARG 기본값이 기준 판과 같은지, 관문이 본 커밋 기록 |
| `check_node_lock.mjs` | `node_modules`가 `package-lock.json`과 같은 판인지 |
| `api_security_inventory.py` | 라우트별 인증·소유 증거표(`docs/api-security-inventory.md`) 생성·검사 |
| `scoring_regress.py` | 채점 회귀 점검(차이 0이어야 한다) |
| `start-backend.ps1`, `setup.ps1` | 로컬 실행·설치 |
| `hosts_config.py` | GPU 호스트 주소를 저장소 밖 설정에서 읽는다(주소는 저장소에 두지 않는다) |

## 브라우저 회귀 (Playwright, 로컬 서버 필요)
`test_tab_load.mjs`(실패→재시도 복구), `test_ia_navigation.mjs`(탭 이동), `qa_crawl.mjs`(화면 순회). Playwright 모듈 경로는 `PLAYWRIGHT_MODULE`로 바꾼다.

## 접두어별
| 접두어 | 내용 |
|---|---|
| `nextreg_*` (36) | 11월 ROI 증류·결합 후보 학습 큐·디스패치·내보내기(`nextreg_roi_dispatch.py` 등은 `hosts_config.py` 필요) |
| `lipread_roi/` | 입술 ROI 학습·내보내기·웹 변환(`roi_train.py`, `roi_web_export.py`), `lipread_web_export.py`는 후보(C65) 웹 내보내기 |
| `fusionweb_*` | 결합 웹 그래프 정확도·속도·꺼짐 동일성(`lipread_off_identity.mjs`가 관문용 후속) |
| `speak_*`, `dgop*`, `s4*`, `phone_tail/` | 말하기 채점(D-GOP)·스트리밍 학생 |
| `listen_*`, `sound*` | 소리 듣기 트랙·합성 음성 |
| `mastery_*`, `scoring*` | 숙달·채점 규칙 시뮬레이션과 회귀 |
| `pilot_*`, `clean*`, `eval*` | 파일럿 도구·클린 평가 |
| `v<번호>_*`, `*_pod/` | 해당 번호 실험의 일회성 스크립트(근거 문서는 `docs/`) |
| `train538*`, `e2_*` | 538 학습 재구성·체인 |
| `export_*`, `build_*` | 자원·표 생성 |

학습 코드의 원본은 저장소 밖 `liplab-lab\tools`에도 있다(`v1_*.py`는 `scripts/lipread_v1/`와 같은 파일이 두 곳에 있으니 고칠 때 둘을 맞춘다).
