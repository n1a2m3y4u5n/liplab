# V1-538 학습 입력 준비(lab-sub, CPU만). 사전등록: docs/lipread-v1-538-prereg-2026-10-29.md 5절.
# 파드 전제였던 v1_remote.sh 앞부분(정렬 → 벤치 → 분할 → ROI)을 로컬 경로로 옮겼다. GPU는 쓰지 않는다.
#   1) 어절 구간  v1_538_spans.py(build_cd + dgop_ours 정렬기), manifest를 Shards개로 나눠 동시에 → d\spans.jsonl, 정렬 관문 90%
#   2) 벤치       d_bench.py build --rule 3,3 → bench_v1_538.pkl
#   3) 분할       v1_train.py split --eval-list eval19_538.txt --val-n 12 → split.json
#   4) 입 영역    lip_roi_extract.py(venv-mp, 연구용) → roi\
# 끝난 단계는 건너뛴다(spans 조각·벤치·분할·ROI npz). 로그: <Out>\prep.log
# 실행: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\lipread_v1\v1_538_prep.ps1 [-Shards 4] [-RoiWorkers 4]
param(
    [string]$Data = 'D:\work\hq\projects\liplab-lab\data\train538',
    [string]$Out = 'D:\work\hq\projects\liplab-lab\data\train538\v1prep',
    [string]$VmpPython = 'D:\work\hq\projects\liplab-lab\venv-mp\Scripts\python.exe',
    [string]$AppPython = 'D:\work\hq\projects\liplab\.venv\Scripts\python.exe',
    [string]$Tools = 'D:\work\hq\projects\liplab-lab\tools',
    [string]$Backend = 'D:\work\hq\projects\liplab\backend',
    [int]$Shards = 4,
    [int]$Threads = 4,
    [int]$RoiWorkers = 4,
    [switch]$SkipRoi
)
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Bs = Join-Path $Data 'rebuild\real_bs'
$D = Join-Path $Out 'd'
$Log = Join-Path $Out 'prep.log'
New-Item -ItemType Directory -Force $Out, $D | Out-Null
$env:PYTHONUTF8 = '1'; $env:PYTHONUNBUFFERED = '1'; $env:HF_HUB_OFFLINE = '1'
$env:CUDA_VISIBLE_DEVICES = '-1'; $env:DGOP_DEVICE = 'cpu'   # GPU 금지(Windows는 빈 값을 지우므로 -1)
$env:OMP_NUM_THREADS = "$Threads"; $env:MKL_NUM_THREADS = "$Threads"

function Say($msg) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"; Write-Output $line; Add-Content -Path $Log -Value $line -Encoding utf8 }
function Fail($msg) { Say "V1PREP_FAIL $msg"; exit 1 }
function FreeGB { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1) }
function Run($exe, [string[]]$argv, $tag) {
    $o = Join-Path $Out "$tag.out"; $e = Join-Path $Out "$tag.err"
    $p = Start-Process -FilePath $exe -ArgumentList $argv -RedirectStandardOutput $o -RedirectStandardError $e -NoNewWindow -PassThru -Wait
    if ($p.ExitCode -ne 0) { Fail "$tag exit $($p.ExitCode) (see $e)" }
    Get-Content $o -Tail 3 | ForEach-Object { Say "$tag | $_" }
}

$Man = Join-Path $Data 'manifest.tsv'
foreach ($x in $Man, $Bs, $VmpPython, $AppPython, (Join-Path $Tools 'build_cd.py'), (Join-Path $Tools 'd_bench.py')) {
    if (-not (Test-Path $x)) { Fail "missing $x" }
}
if ($Data -match 'e2_538') { Fail 'E2 폴더는 쓰지 않는다' }
Say "=== v1_538_prep start data=$Data out=$Out shards=$Shards free=$(FreeGB)GB"

# 1) 어절 구간: manifest를 줄 번호 % Shards로 나눠 동시에 정렬
$spans = Join-Path $D 'spans.jsonl'
if (-not (Test-Path $spans)) {
    $rows = @(Get-Content $Man -Encoding utf8 | Where-Object { $_.Trim() -and -not $_.StartsWith('#') })
    $procs = @()
    for ($s = 0; $s -lt $Shards; $s++) {
        $ms = Join-Path $Out "manifest.$s.tsv"
        $part = for ($i = $s; $i -lt $rows.Count; $i += $Shards) { $rows[$i] }
        [IO.File]::WriteAllLines($ms, [string[]]$part, (New-Object Text.UTF8Encoding $false))
        $ds = Join-Path $Out "d.$s"
        if (Test-Path (Join-Path $ds 'spans.jsonl')) { continue }
        $procs += Start-Process -FilePath $AppPython -ArgumentList @("$Here\v1_538_spans.py", '--tools', $Tools, '--backend', $Backend,
            '--threads', "$Threads", '--', '--data', $Data, '--out', $ds, '--manifest', $ms, '--bs', $Bs, '--clips', (Join-Path $Data 'clips')) `
            -RedirectStandardOutput (Join-Path $Out "spans.$s.log") -RedirectStandardError (Join-Path $Out "spans.$s.err") -NoNewWindow -PassThru
    }
    while (@($procs | Where-Object { -not $_.HasExited }).Count -gt 0) {
        Start-Sleep -Seconds 60
        $n = 0; for ($s = 0; $s -lt $Shards; $s++) { $f = Join-Path $Out "d.$s\spans.jsonl"; if (Test-Path $f) { $n++ } }
        Say "spans running=$(@($procs | Where-Object { -not $_.HasExited }).Count) done_shards=$n free=$(FreeGB)GB"
    }
    foreach ($p in $procs) { if ($p.ExitCode -ne 0) { Fail "spans exit $($p.ExitCode)" } }
    # 조각을 manifest 원래 순서로 합친다(벤치 행 순서가 조각 수와 상관없게)
    $byClip = @{}
    for ($s = 0; $s -lt $Shards; $s++) {
        foreach ($l in [IO.File]::ReadAllLines((Join-Path $Out "d.$s\spans.jsonl"), [Text.Encoding]::UTF8)) {
            if ($l.Trim()) { $byClip[($l | ConvertFrom-Json).clip] = $l }
        }
    }
    $merged = foreach ($r in $rows) { $b = ($r -split "`t")[0] -replace '\.mp4$', ''; if ($byClip.ContainsKey($b)) { $byClip[$b] } else { Fail "spans 빠짐 $b" } }
    [IO.File]::WriteAllLines("$spans.tmp", [string[]]$merged, (New-Object Text.UTF8Encoding $false))
    Move-Item -Force "$spans.tmp" $spans
}
$st = Get-Content $spans -Encoding utf8 | ForEach-Object { $_ | ConvertFrom-Json }
$elig = @($st | Where-Object { $_.status -notin @('skip_chars', 'empty_text', 'no_bs', 'no_wav') }).Count
$ok = @($st | Where-Object { $_.status -eq 'ok' }).Count
$flag = @($st | Where-Object { $_.status -eq 'ok' -and $_.flag }).Count
$ratio = if ($elig) { [math]::Round(($ok - $flag) / $elig, 4) } else { 0 }
$byStatus = ($st | Group-Object status | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ' '
Say "SPANS rows=$($st.Count) eligible=$elig ok=$ok flagged=$flag usable_ratio=$ratio $byStatus"
if ($ratio -lt 0.9) { Fail "정렬 관문 미달(usable/eligible $ratio < 0.9)" }

# 2) 벤치
$bench = Join-Path $Out 'bench_v1_538.pkl'
if (-not (Test-Path $bench)) {
    Run $AppPython @((Join-Path $Tools 'd_bench.py'), 'build', '--spans', $spans, '--bs', $Bs, '--rule', '3,3', '--out', $bench) 'build'
}

# 3) 분할(평가 19명은 커밋된 목록)
$split = Join-Path $Out 'split.json'
$ev = Join-Path $Here 'eval19_538.txt'
Copy-Item -Force $ev (Join-Path $Out 'eval19_538.txt')
$env:PYTHONPATH = $Tools   # 저장소 사본 v1_train.py가 tools의 folds·d_bench·train_lipread를 쓴다
Run $AppPython @((Join-Path $Here 'v1_train.py'), 'split', '--bench', $bench, '--eval-list', $ev, '--val-n', '12', '--out', $split) 'split'

# 4) 입 영역(연구용, 판정에 안 씀)
if (-not $SkipRoi) {
    $roi = Join-Path $Out 'roi'
    if (-not (Test-Path (Join-Path $roi '_extract_stats.json'))) {
        Run $VmpPython @((Join-Path $Tools 'lip_roi_extract.py'), '--clips', (Join-Path $Data 'clips'), '--out', $roi, '--workers', "$RoiWorkers",
            '--preview', '4') 'roi'
    }
}
Say "V1PREP_OK free=$(FreeGB)GB"
