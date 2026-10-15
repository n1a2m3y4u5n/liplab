# V1 실행 기록: 538 화자를 늘린 제품용 독화기 재학습(2026-10-15, 받기 전에 멈춤)

사전등록은 `lipread-v1-prereg-2026-10.md`(ea1c7af9, 받기·학습 전 커밋)다. 이 문서는 실행 상태와 결과를 적는다.

## 1. 상태(10/15 21:55)

- 사전등록, 받기·학습·판정·파드 도구를 커밋했다. 맥에서 기존 자료(9/24 벤치 30명 + 9/25 26명)로 파드 쪽 전 과정(벤치 → 분할 →
  후보 A·B 학습 1에폭 → 선택 → product4way → 판정)을 작게 돌려 끝 표식까지 나오는 것을 확인했다. 판정용 수치는 아니다.
- 받기는 시작하지 않았다. 19:46부터 다른 세션의 608 범주 27 둘째 묶음 받기(`fetch608_c27b.py`, 약 93 GB 흘려받기)가 끝나기를
  기다리던 중, 사용자 결정("맥 CPU를 써야 하는 건 다음에")으로 대기 프로세스를 껐다(21:53). 파드는 쓰지 않았다(비용 0달러).
- 판정 없음. 웹캠 기계 확인 기본값은 그대로다. 미달에 대비한 빌드 플래그만 준비했다(4절).

## 2. 다음에 이어서 할 순서

받기 시작 조건: (1) 사용자가 맥 CPU 사용을 허락함, (2) 다른 AI Hub 받기가 없음(`pgrep -fl "aihub|fetch608|v7b_|538.do|dl_more|v1_dl"`가
빈 결과, 다른 세션이 띄운 감시 셸도 이 패턴에 걸리므로 목록을 눈으로 확인), (3) 맥 여유 20 GB 이상(`df -h /`).

1. 받기(맥, 약 3~9시간). 다른 받기가 끝나기를 기다렸다가 시작하는 감시 스크립트를 띄운다. 받기와 ffmpeg 컷은 `nice -n 20`, 동시 2개 이하,
   회선은 `data/v1_538r/.limit_rate`(지금 `4M`)로 제한된다. 4 MB/s면 약 130 GB에 약 9시간, 제한을 풀면 10/6~10/7 실측으로 3~6시간.
   ```
   cd ~/Downloads/LIPLAB_ALL/liplab-lab && nohup caffeinate -i bash tools/v1r_after_other.sh > data/v1_538r/v1r_dl.out 2>&1 &
   # 진행: grep -c CUT_OK data/v1_538r/dl_more.out / 끝: grep V1R_DL data/v1_538r/v1r_dl.out
   # 회선 조절: echo 2M > data/v1_538r/.limit_rate (다음 요청부터), 제한 해제: rm data/v1_538r/.limit_rate
   ```
   중간에 멈춰도 같은 명령으로 이어 받는다. 디스크 여유가 8 GB 아래면 감시가 받기를 끈다.
2. 평가 화자 고정(맥, 1분). `python3 tools/v1_pick_eval.py --root data/v1_538r --out data/v1_538r/eval40.txt`.
   `V1_PICK_SHORT`(후보 80명 미만이나 학습+검증 120명 미만)면 `N_QUEUE=173`으로 1을 다시 돌린다. 목록을 저장소
   `scripts/lipread_v1/eval40.txt`로 복사하고 사전등록 부록 A에 붙여 커밋·push한다(파드 스크립트가 커밋된 판과 같은지 확인한다).
3. 파드(약 2.5~3.5시간, 약 1.5~2.5달러, 워치독 330분이 상한). 먼저 `bash tools/pod/pod.sh status`로 잔액(5달러 이상)과 남은 파드 0을 본다.
   ```
   cd ~/Downloads/LIPLAB_ALL/liplab-lab && bash tools/pod/v1_session.sh --stage-only   # 묶음만(약 1.6 GB, 네트워크 없음)
   bash tools/pod/v1_session.sh                                                     # 생성 → 추출·정렬 → 학습·판정 → 받기 → terminate
   ```
   결과는 `data/pod_runs/<날짜>_<파드>/dax/`(판정 `v1/v1_verdict.json`, 로그 `logs/v1.log`의 `V1_GATE`). 끝에 terminate와
   `pod.sh status`의 파드 0을 확인한다.
4. 정리(맥). 새 화자 블렌드셰이프·입술 좌표·정렬·입 영역을 받은 것을 확인한 뒤 자른 클립과 묶음을 지운다
   (`data/v1_538r/clips`, `data/v1stage`). 이 문서 3절에 결과를 적고 STATUS를 고친다.
5. 판정에 따른 조치(사전등록 6절). 미달이면 4절의 플래그 기본값을 `research`로 바꾸자고 제안한다(배포는 사용자 결정).

## 3. 결과

아직 없다.

## 4. 앱 쪽 준비(기본값 그대로)

- `frontend/src/lib/lipreadGate.js`: 빌드 플래그 `VITE_LIPREAD_CHECK`. `on`(기본, 지금과 같음), `research`(연구 빌드
  `VITE_LIPLAB_RESEARCH=1`에서만 보이고 꼬리표를 '연구 기능', 안내를 "처음 보는 사람의 입모양은 아직 거의 읽지 못해서 … 결과를 내 입모양
  점수로 보지 마세요"로 바꿈), `off`(숨김). 숨길 때는 단어 레슨이 기계 확인 칸의 코드도 받지 않는다(`WordStage.jsx`).
- 시험 `lib/lipreadGate.test.mjs` 3개 통과. 맥 CPU를 아끼려고 vite 빌드와 전체 시험은 돌리지 않았다(다음에 확인).

## 5. 도구(사본은 `scripts/lipread_v1/`, 실행본은 `liplab-lab/tools/`)

| 파일 | 하는 일 |
|---|---|
| `v1r_after_other.sh` | 다른 AI Hub 받기가 1분 간격 세 번 연속 없으면 `v1r_dl.sh` 시작 |
| `v1r_dl.sh` | queue_v1.tsv 앞 130개를 `data/v1_538r`로 받기(VBYTES 1.0 GB, nice 20, 회선 제한, 여유 8 GB 감시) |
| `dl_more_limit_rate.patch` | `dl_more.sh`에 더한 회선 제한(`LIPLAB_LIMIT_RATE` 또는 `$ROOT/.limit_rate`, 요청마다 다시 읽음) |
| `v1_pick_eval.py` | 평가 화자 40명 고정(사전등록 3.2절) |
| `v1_train.py` | 분할(검증 12명·내용 분리), 후보 A·B 학습, 검증 화자만으로 선택 |
| `v1_judge.py` | 주 지표·관문(≥ 40%, 화자 부트스트랩 하한 > 30%)과 보고용 대조 |
| `pod/v1_session.sh`, `pod/v1_remote.sh` | 파드 한 번에(묶음, 생성, 추출, 정렬, 학습, 평가, 받기, terminate) |

- 10/14 정리로 `archive/liplab_gpu_snapshot/expand538*`가 없어져, 인물 중복 검사는 기존 68명의 `pod_runs` manifest_all 세 개로 한다.
- 10/6 받기 기록(`data/v1_538`)의 `.state`는 그대로 두었다(같은 화자를 건너뛰지 않도록 새 루트를 썼다).
