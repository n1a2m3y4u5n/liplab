# train538 받은 뒤 ① V3 재적합 자료 재생성(lab-sub 로컬, RTX 3060). 사전 등록: docs/train538-reacquire-prereg-2026-10-28.md 5절.
# 파드 전제였던 scripts/v3_pod/run_v3.sh prep 단계를 로컬 경로로 옮겼다.
#   0) E2 격리 검사(E2 평가 클립 360개·E2 인물·배치가 하나라도 있으면 멈춤)
#   1) extract_blendshapes.py --lips --no-audio   (venv-mp, MediaPipe 0.10.14, CPU 병렬)
#   2) CTC 강제 정렬  v2_avatar_validity.py align  (backend .venv, dgop_ours 정렬기)
#   3) v2_avatar_validity.py select               (화자당 12클립, crc32 절반)
#   4) v3_avatar.py dataset → fit --halves 0       (탐색 절반만으로 표. 확인 절반 지표는 여기서 계산하지 않음)
# 추출·정렬은 이미 끝난 클립을 건너뛰므로 다시 실행해도 된다. 로그: <Out>\rebuild.log
# 실행: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\train538_rebuild.ps1 [-Parts 6] [-AlignShards 2]
param(
    [string]$Data = 'D:\work\hq\projects\liplab-lab\data\train538',
    [string]$Out = 'D:\work\hq\projects\liplab-lab\data\train538\rebuild',
    [string]$VmpPython = 'D:\work\hq\projects\liplab-lab\venv-mp\Scripts\python.exe',
    [string]$AppPython = 'D:\work\hq\projects\liplab\.venv\Scripts\python.exe',
    [string]$Tools = 'D:\work\hq\projects\liplab-lab\tools',
    [int]$Parts = 6,
    [int]$AlignShards = 2
)
$ErrorActionPreference = 'Stop'
$Scripts = $PSScriptRoot
$Backend = Join-Path (Split-Path $Scripts -Parent) 'backend'
$Bs = Join-Path $Out 'real_bs'
$Log = Join-Path $Out 'rebuild.log'
New-Item -ItemType Directory -Force $Out, $Bs | Out-Null
$env:PYTHONUTF8 = '1'; $env:PYTHONUNBUFFERED = '1'; $env:HF_HUB_OFFLINE = '1'

function Say($msg) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"; Write-Output $line; Add-Content -Path $Log -Value $line -Encoding utf8 }
function Fail($msg) { Say "REBUILD_FAIL $msg"; exit 1 }
function Run($exe, [string[]]$argv, $tag) {
    $o = Join-Path $Out "$tag.out"; $e = Join-Path $Out "$tag.err"
    $p = Start-Process -FilePath $exe -ArgumentList $argv -RedirectStandardOutput $o -RedirectStandardError $e -NoNewWindow -PassThru -Wait
    if ($p.ExitCode -ne 0) { Fail "$tag exit $($p.ExitCode) (see $e)" }
    Get-Content $o -Tail 3 | ForEach-Object { Say "$tag | $_" }
}

if (-not (Test-Path (Join-Path $Data 'manifest.tsv'))) { Fail "no manifest: $Data" }
foreach ($x in $VmpPython, $AppPython, (Join-Path $Tools 'extract_blendshapes.py')) { if (-not (Test-Path $x)) { Fail "missing $x" } }
Say "=== train538_rebuild start data=$Data out=$Out"

# 0) E2 격리
Run $AppPython @("$Scripts\train538_rebuild_prep.py", 'guard', '--data', $Data) 'guard'

# 1) 블렌드셰이프 추출
Run $AppPython @("$Scripts\train538_rebuild_prep.py", 'lists', '--data', $Data, '--out', $Out, '--bs', $Bs, '--parts', "$Parts") 'lists'
$procs = @()
for ($k = 0; $k -lt $Parts; $k++) {
    $list = Join-Path $Out "list_real.$k.tsv"
    if ((Get-Item $list).Length -eq 0) { continue }
    $procs += Start-Process -FilePath $VmpPython -ArgumentList @('extract_blendshapes.py', '--list', $list, '--lips', '--no-audio') `
        -WorkingDirectory $Tools -RedirectStandardOutput "$list.log" -RedirectStandardError "$list.err" -NoNewWindow -PassThru
    $null = $procs[-1].Handle   # 핸들을 잡아 두어야 ExitCode가 남는다
}
$procs | ForEach-Object { $_.WaitForExit() }
foreach ($p in $procs) { if ($p.ExitCode -ne 0) { Fail "extract exit $($p.ExitCode)" } }
Say "EXTRACT done json=$((Get-ChildItem $Bs -Filter *.json).Count)"

# 2) CTC 강제 정렬(이미 정렬한 key는 align이 건너뛴다)
$items = Join-Path $Out 'items.jsonl'
$procs = @()
for ($s = 0; $s -lt $AlignShards; $s++) {
    $procs += Start-Process -FilePath $AppPython -ArgumentList @("$Scripts\v2_avatar_validity.py", 'align', '--items', $items, '--backend', $Backend,
        '--shard', "$s", '--nshard', "$AlignShards", '--threads', '2', '--out', (Join-Path $Out "align.$s.jsonl")) `
        -RedirectStandardOutput (Join-Path $Out "align.$s.log") -RedirectStandardError (Join-Path $Out "align.$s.err") -NoNewWindow -PassThru
    $null = $procs[-1].Handle   # 핸들을 잡아 두어야 ExitCode가 남는다
}
$procs | ForEach-Object { $_.WaitForExit() }
foreach ($p in $procs) { if ($p.ExitCode -ne 0) { Fail "align exit $($p.ExitCode)" } }
$align = Join-Path $Out 'align_real.jsonl'
$text = (Get-ChildItem $Out -Filter 'align.*.jsonl' | Sort-Object Name | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join ''
[IO.File]::WriteAllText($align, $text, (New-Object Text.UTF8Encoding $false))   # BOM 없이(파이썬 json.loads)
$nerr = @(Select-String -Path $align -Pattern '"error"').Count
Say "ALIGN done rows=$((Get-Content $align).Count) err=$nerr"

# 3) 선택(화자당 12클립, 절반 0 탐색 / 1 확인)
$sel = Join-Path $Out 'sel.json'
Run $AppPython @("$Scripts\v2_avatar_validity.py", 'select', '--root', $Data, '--per-spk', '12', '--stamp', (Get-Date -Format 'yyyy-MM-dd'), '--out', $sel) 'select'

# 4) V3 자료와 탐색 절반 표
$pkl = Join-Path $Out 'v3_data.pkl'
Run $AppPython @("$Scripts\v3_avatar.py", 'dataset', '--sel', $sel, '--align', $align, '--real-bs', $Bs, '--out', $pkl) 'dataset'
if (Select-String -Path (Join-Path $Out 'dataset.out') -Pattern 'cells_rows=0 ' -Quiet) { Fail 'dataset has no face segments' }
Run $AppPython @("$Scripts\v3_avatar.py", 'fit', '--data', $pkl, '--halves', '0', '--mode', 'add', '--out', (Join-Path $Out 'v3_table_explore.json')) 'fit'
Say 'REBUILD_OK'
