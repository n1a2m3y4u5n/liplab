# roi_train_launch.ps1: 데스크탑(2026-10-18): 독화 ① R1·R2 등록 학습 실행기(docs/lipread-roi-2026-10.md 12.1절 점검표).
#   cd D:\liplab\roi; bg powershell -NoProfile -ExecutionPolicy Bypass -File D:\liplab\repo\scripts\lipread_roi\roi_train_launch.ps1
# ROI 추출이 끝날 때까지(ROI_LOOP_DONE) 기다린 뒤 prep → teacher → R1 s0 → R2 s0(사전학습 → 미세조정) → R1 s1 → R2 s1 → select를
# 한 번에 하나씩 돌린다. 끊기면 같은 명령으로 다시 띄운다(끝난 단계는 건너뛰고, 학습 중이던 단계는 마지막 에폭부터 이어 한다).
# 평가 화자 40명의 ROI는 읽지 않는다. 판정(p4 --judge)은 이 스크립트가 하지 않는다.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONUNBUFFERED = '1'
$env:HF_HOME = 'D:/liplab/cache/hf'; $env:TORCH_HOME = 'D:/liplab/cache/torch'
$env:LIPLAB_TOOLS = 'D:/liplab/v1/dax'                                      # d_bench·train_lipread·folds·build_cd
$env:PYTORCH_CUDA_ALLOC_CONF = 'max_split_size_mb:128,garbage_collection_threshold:0.8'
if (-not $env:ROI_GPU_FRAC) { $env:ROI_GPU_FRAC = '0.45' }                   # 12 GB의 45% = 약 5.4 GB 상한
if (-not $env:ROI_MAX_FRAMES) { $env:ROI_MAX_FRAMES = '4000' }               # 한 번에 GPU에 올리는 유효 프레임
$run = if ($env:ROI_RUN) { $env:ROI_RUN } else { 'D:/liplab/roi/run' }
$py = 'D:\liplab\vlip\Scripts\python.exe'
$tool = Join-Path $PSScriptRoot 'roi_train.py'
$wait = @(); if ($env:ROI_WAIT -ne '0') { $wait += '--wait-roi' }   # if 식은 원소 하나짜리 배열을 문자열로 풀어 @wait가 글자 단위로 쪼개짐(10/18 고침)
New-Item -ItemType Directory -Force $run | Out-Null
"=== ROI_LAUNCH $(Get-Date -Format s) run=$run tool=$tool frac=$env:ROI_GPU_FRAC maxf=$env:ROI_MAX_FRAMES git=$(git -C $PSScriptRoot rev-parse --short HEAD)"
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
& $py -u $tool all --run $run --seeds 0,1 @wait
$rc = $LASTEXITCODE
"=== ROI_LAUNCH end rc=$rc $(Get-Date -Format s)"
exit $rc
