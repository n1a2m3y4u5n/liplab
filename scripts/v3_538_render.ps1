# V3 train538 재적합(docs/avatar-v3-538-prereg-2026-11-02.md) 렌더 → 블렌드셰이프 추출. 이미 있는 결과는 건너뛴다. 끝 표식 V3R_<Name>_OK
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v3_538_render.ps1 -Name r1 -Jobs a.json,b.json -Tables tables.json
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string[]]$Jobs,
    [Parameter(Mandatory = $true)][string]$Tables,
    [string]$Work = 'D:\work\hq\projects\liplab-lab\data\train538\rebuild\v3_2026-11-02',
    [string]$VmpPython = 'D:\work\hq\projects\liplab-lab\venv-mp\Scripts\python.exe',
    [string]$Tools = 'D:\work\hq\projects\liplab-lab\tools',
    [int]$RW = 4,
    [int]$Parts = 6,
    [int]$Port = 5196
)
$ErrorActionPreference = 'Stop'
$env:CHROME = "$env:LOCALAPPDATA\ms-playwright\chromium-1248\chrome-win64\chrome.exe"
$env:FFMPEG = 'D:\work\hq\projects\liplab-lab\venv-mp\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'
$env:PYTHONUTF8 = '1'
$O = Join-Path $Work $Name
$Rn = Join-Path $O 'renders'; $Bs = Join-Path $O 'bs'
New-Item -ItemType Directory -Force $Rn, $Bs | Out-Null
$jargs = @(); foreach ($j in ($Jobs -join ',') -split ',') { $jargs += '--jobs'; $jargs += $j }
$log = Join-Path $O 'render.log'
& node (Join-Path $PSScriptRoot 'v2_render\render_jobs_cdp.mjs') --harness (Join-Path $Work 'harness') @jargs --tables $Tables --out $Rn --workers $RW --gl d3d11 --port $Port *> $log
if ($LASTEXITCODE -ne 0) { "V3R_${Name}_FAIL render rc=$LASTEXITCODE"; exit 1 }
Select-String -Path $log -Pattern 'RJ_GL|RJ_DONE|RJ_WORKER_FAIL|RJ_FAIL' | ForEach-Object { $_.Line.Substring(0, [Math]::Min(300, $_.Line.Length)) }
$todo = @(Get-ChildItem $Rn -Filter *.mp4 | Where-Object { $_.Name -notlike '*.part.mp4' -and -not (Test-Path (Join-Path $Bs ($_.BaseName + '.json'))) } | ForEach-Object { $_.FullName + "`t" + (Join-Path $Bs ($_.BaseName + '.json')) })
$procs = @()
for ($k = 0; $k -lt $Parts; $k++) {
    $part = @(for ($i = $k; $i -lt $todo.Count; $i += $Parts) { $todo[$i] })
    if (-not $part.Count) { continue }
    $list = Join-Path $O "list.$k.tsv"
    [IO.File]::WriteAllLines($list, [string[]]$part, (New-Object Text.UTF8Encoding $false))
    $procs += Start-Process -FilePath $VmpPython -ArgumentList @('extract_blendshapes.py', '--list', $list, '--lips', '--no-audio') -WorkingDirectory $Tools `
        -RedirectStandardOutput "$list.log" -RedirectStandardError "$list.err" -NoNewWindow -PassThru
    $null = $procs[-1].Handle   # 핸들을 잡아 두어야 ExitCode가 남는다
}
$procs | ForEach-Object { $_.WaitForExit() }
foreach ($p in $procs) { if ($p.ExitCode -ne 0) { "V3R_${Name}_FAIL extract exit $($p.ExitCode)"; exit 1 } }
"V3R_${Name}_OK renders=$((Get-ChildItem $Rn -Filter *.sched.json).Count) bs=$((Get-ChildItem $Bs -Filter *.json).Count)"
