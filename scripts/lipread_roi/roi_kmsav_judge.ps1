# KMSAV ROI single judgment on lab-sub (docs/lipread-roi-kmsav-prereg-2026-11-02.md sections 6-8).
# Select on validation 12 only, then score the selected candidate, the selected B33 and R2 s0 once on the
# 19 evaluation speakers (clean + 5 degraded copies), then judge. Ends with KMS_JUDGE PASS|FAIL.
param(
    [string]$Py = 'D:\work\hq\projects\liplab\.venv\Scripts\python.exe',
    [string]$D = 'D:\work\hq\projects\liplab-lab\data\roi-kmsav',
    [string]$Prep = 'D:\work\hq\projects\liplab-lab\data\train538\v1prep',
    [string]$R2 = 'D:\work\hq\projects\liplab-lab\models\lipread_roi_R2s0_2026-10-21\kr_lipread_roi.web.onnx'
)
$ErrorActionPreference = 'Continue'   # python stderr lines must not abort; exit codes are checked
$Code = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Code '..\..')).Path
$env:LIPLAB_TOOLS = 'D:\work\hq\projects\liplab-lab\tools'; $env:PYTHONPATH = $env:LIPLAB_TOOLS
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; $env:OMP_NUM_THREADS = '4'
$J = Join-Path $D 'judge'
New-Item -ItemType Directory -Force $J | Out-Null
$Log = Join-Path $J 'judge.log'
function Say($m) { Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" -Encoding utf8 }
function Run($argv) {
    Say ("RUN " + ($argv -join ' '))
    $out = & $Py -u @argv 2>&1 | ForEach-Object { "$_" }
    $out | Add-Content -Path $Log -Encoding utf8
    if ($LASTEXITCODE -ne 0) { Say "KMS_JUDGE_RUN_FAIL rc=$LASTEXITCODE"; exit 1 }
    return $out
}
$Train = Join-Path $Code 'roi_train.py'
$EvalList = Join-Path $Repo 'scripts\lipread_v1\eval19_538.txt'
$spk = (Get-Content $EvalList -Encoding utf8 | Where-Object { $_ -match '^spk\d+' } | ForEach-Object { $_.Trim() }) -join ','
Say "=== judge start speakers=$spk"
$K = Join-Path $D 'run_k'; $B = Join-Path $D 'run_base'
Run @($Train, 'select', '--runs', "$K\run_K1s0,$K\run_K1s1,$K\run_K2s0,$K\run_K2s1", '--out', "$J\sel.json") | Out-Null
Run @($Train, 'select', '--runs', "$B\run_B33s0,$B\run_B33s1", '--out', "$J\sel_b33.json") | Out-Null
$selK = (Get-Content "$J\sel.json" -Raw -Encoding utf8 | ConvertFrom-Json).selected
$selB = (Get-Content "$J\sel_b33.json" -Raw -Encoding utf8 | ConvertFrom-Json).selected
Say "SELECTED cand=$($selK.model) dup=$($selK.dup) b33=$($selB.model) dup=$($selB.dup)"
$conds = New-Object System.Collections.ArrayList
[void]$conds.Add(@('', "$Prep\roi"))
foreach ($c in 'low', 'jpeg', 'geo', 'bright', 'all') { [void]$conds.Add(@("_$c", "$D\degraded\$c")) }
foreach ($m in @(@('cand', '--model', $selK.model), @('b33', '--model', $selB.model), @('r2s0', '--onnx', $R2))) {
    $dir = Join-Path $J $m[0]
    New-Item -ItemType Directory -Force $dir | Out-Null
    foreach ($c in $conds) {
        $o = Join-Path $dir "p4$($c[0]).json"
        if (Test-Path $o) { Say "SKIP $o"; continue }
        Run @($Train, 'p4', $m[1], $m[2], '--bench', "$Prep\bench_v1_538.pkl", '--npz', $c[1], '--speakers', $spk,
              '--eval-list', $EvalList, '--judge', '--out', $o) | Out-Null
    }
}
$r = Run @((Join-Path $Code 'roi_kmsav.py'), 'judge', '--sel', "$J\sel.json", '--b33-sel', "$J\sel_b33.json",
           '--cand-dir', "$J\cand", '--base-dir', "$J\r2s0", '--b33-dir', "$J\b33", '--out', "$J\judge.json")
Say 'KMS_JUDGE_SCRIPT_DONE'
