param(
    [Parameter(Mandatory = $true)][string]$GateReport,      # predeploy_dev.ps1의 -ReportDirectory (PREDEPLOY_DEV_OK.json이 있어야 한다)
    [Parameter(Mandatory = $true)][string]$OutDirectory,    # 배포 기록(직전 이미지·DB 사본·스모크)을 남길 폴더
    [string]$App = 'liplab-dev',
    [string]$Config = 'fly.dev.toml',
    [string]$ContextDirectory = '',                         # 기본은 저장소 루트. 따로 구성한 context를 쓰면 그곳의 Dockerfile·fly.dev.toml이 같은지 대조한다
    [string]$Python = '',
    [string]$BaseUrl = 'https://liplab-dev.fly.dev',
    [int]$ReadyTimeoutSec = 300,
    [switch]$DryRun,                                        # 검사와 계획만 출력하고 flyctl·네트워크는 부르지 않는다
    [switch]$SkipSmoke
)

# liplab-dev 전용 배포(11/03 검토 O3·O4). 전시앱(liplab, fly.toml)에는 쓰지 않는다.
#  1) 앱·설정 이름 고정 → 2) 관문 통과 표식이 지금 커밋·트리와 같은지 → 3) 직전 이미지·커밋 기록 → 4) DB 사본
#  → 5) 배포 → 6) /health/ready → 7) 채점 포함 스모크 → 실패하면 직전 이미지로 되돌림.
# 되돌림은 이미지만 되돌린다(볼륨·DB는 그대로). 토큰(FLY_API_TOKEN)은 출력하거나 기록하지 않는다.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!$Python) {
    $gatePython = 'D:\work\hq\projects\liplab-wt\gate-venv\Scripts\python.exe'
    $Python = if (Test-Path -LiteralPath $gatePython) { $gatePython } else { 'python' }
}
$log = New-Object System.Collections.Generic.List[string]
function Say([string]$m) { Write-Host $m; $log.Add($m) | Out-Null }
function Stop-Deploy([string]$m) { Say "DEPLOY_ABORTED: $m"; throw $m }

# 1) 앱·설정 고정
if ($App -ne 'liplab-dev') { Stop-Deploy "앱 이름이 liplab-dev가 아니다: '$App' (전시앱에는 이 스크립트를 쓰지 않는다)" }
if ($Config -ne 'fly.dev.toml') { Stop-Deploy "설정 파일이 fly.dev.toml이 아니다: '$Config'" }
$cfgText = Get-Content -LiteralPath (Join-Path $root 'fly.dev.toml') -Raw
if ($cfgText -notmatch '(?m)^\s*app\s*=\s*"liplab-dev"\s*$') { Stop-Deploy 'fly.dev.toml의 app이 liplab-dev가 아니다' }
New-Item -ItemType Directory -Force -Path $OutDirectory | Out-Null
$OutDirectory = (Resolve-Path -LiteralPath $OutDirectory).Path

# 2) 관문 표식 ↔ 지금 커밋·트리
Push-Location $root
try {
    $okFile = Join-Path $GateReport 'PREDEPLOY_DEV_OK.json'
    if (!(Test-Path -LiteralPath $okFile)) { Stop-Deploy "관문 통과 표식이 없다: $okFile (predeploy_dev.ps1를 먼저 통과시킨다)" }
    $ok = Get-Content -LiteralPath $okFile -Raw | ConvertFrom-Json
    $head = (git rev-parse HEAD).Trim()
    $tree = (git rev-parse 'HEAD^{tree}').Trim()
    $dirty = @(git status --porcelain --untracked-files=no)
    if ($ok.commit -ne $head -or $ok.tree -ne $tree) { Stop-Deploy "관문이 본 커밋($($ok.commit.Substring(0,10)))과 지금 커밋($($head.Substring(0,10)))이 다르다" }
    if ($dirty.Count -gt 0) { Stop-Deploy "추적 파일에 커밋 안 된 변경이 $($dirty.Count)개 있다" }
    Say "관문 통과 표식 OK: 커밋 $($head.Substring(0,10)) 트리 $($tree.Substring(0,10)) ($($ok.at_utc))"
    if ($ContextDirectory) {
        foreach ($f in 'Dockerfile', 'fly.dev.toml') {
            $a = (Get-FileHash -LiteralPath (Join-Path $root $f) -Algorithm SHA256).Hash
            $b = (Get-FileHash -LiteralPath (Join-Path $ContextDirectory $f) -Algorithm SHA256).Hash
            if ($a -ne $b) { Stop-Deploy "context의 $f 가 관문을 통과한 저장소와 다르다" }
        }
        Say "context $ContextDirectory 의 Dockerfile·fly.dev.toml이 저장소와 같다"
    } else { $ContextDirectory = $root }
} finally { Pop-Location }

$fly = if ($env:FLYCTL) { $env:FLYCTL } else { 'flyctl' }
$prevImage = $null
$snapshot = $null
$rolledBack = $false
$smokeOk = $null
function Invoke-Fly([string[]]$FlyArgs) {
    Say ("flyctl " + ($FlyArgs -join ' '))
    if ($DryRun) { return '' }
    $out = & $fly @FlyArgs 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Stop-Deploy "flyctl 실패(종료 코드 $LASTEXITCODE): $($FlyArgs[0..1] -join ' ')" }
    return $out
}

try {
    # 3) 직전 이미지·커밋 기록
    $machines = Invoke-Fly @('machines', 'list', '-a', $App, '--json')
    if (!$DryRun) {
        $m = $machines | ConvertFrom-Json
        $prevImage = $m[0].config.image
        if (!$prevImage) { Stop-Deploy '직전 이미지를 찾지 못했다(되돌릴 곳이 없으면 배포하지 않는다)' }
        @{ app = $App; image = $prevImage; recorded_utc = (Get-Date).ToUniversalTime().ToString('o'); deploying_commit = $head } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutDirectory 'previous-image.json') -Encoding utf8
        Say "직전 이미지 기록: $prevImage"
    }

    # 4) DB 사본(/data/backup/pre-<UTC>.db, 최근 3개만 남긴다)
    # 따옴표가 PowerShell→flyctl→셸을 지나며 깨지지 않게 파이썬 코드를 base64로 보낸다
    $py = "import sqlite3,time,os,glob`nd='/data/backup'`nos.makedirs(d,exist_ok=True)`n" +
          "dst=d+'/pre-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'.db'`n" +
          "c=sqlite3.connect('/data/liplab.db')`nc.execute('VACUUM INTO ?',(dst,))`nc.close()`n" +
          "[os.remove(f) for f in sorted(glob.glob(d+'/pre-*.db'))[:-3]]`nprint('SNAPSHOT',dst,os.path.getsize(dst))`n"
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
    $snapOut = Invoke-Fly @('ssh', 'console', '-a', $App, '-C', "/bin/sh -c 'echo $b64 | base64 -d | python'")
    if (!$DryRun) {
        $line = ($snapOut -split "`n" | Where-Object { $_ -match 'SNAPSHOT' } | Select-Object -First 1)
        if (!$line) { Stop-Deploy "DB 사본을 만들지 못했다" }
        $snapshot = $line.Trim()
        Say $snapshot
    }

    # 5) 배포
    $depOut = Invoke-Fly @('deploy', '-c', (Join-Path $ContextDirectory 'fly.dev.toml'), '-a', $App, '--remote-only', '--dockerfile', (Join-Path $ContextDirectory 'Dockerfile'))
    if (!$DryRun) { Set-Content -LiteralPath (Join-Path $OutDirectory 'fly-deploy.log') -Value $depOut -Encoding utf8 }

    # 6) /health/ready, 7) 스모크
    function Wait-Ready {
        $until = (Get-Date).AddSeconds($ReadyTimeoutSec)
        while ((Get-Date) -lt $until) {
            try { $r = Invoke-WebRequest -Uri "$BaseUrl/health/ready" -UseBasicParsing -TimeoutSec 30; if ($r.StatusCode -eq 200) { return $true } } catch { }
            Start-Sleep -Seconds 10
        }
        return $false
    }
    if ($DryRun) {
        Say "(dry-run) /health/ready 대기 → scripts\smoke_dev.py 실행 → 실패하면 --image $prevImage 로 되돌림"
    } else {
        $ready = Wait-Ready
        if ($ready -and !$SkipSmoke) {
            & $Python -X utf8 (Join-Path $root 'scripts\smoke_dev.py') --base $BaseUrl --out $OutDirectory
            $smokeOk = ($LASTEXITCODE -eq 0)
        } elseif ($ready) { $smokeOk = $true } else { $smokeOk = $false }
        if (!$smokeOk) {
            Say "배포 검증 실패(ready=$ready) → 직전 이미지로 되돌림"
            Invoke-Fly @('deploy', '-c', (Join-Path $ContextDirectory 'fly.dev.toml'), '-a', $App, '--image', $prevImage) | Out-Null
            $rolledBack = $true
            Say ("되돌린 뒤 /health/ready: " + (Wait-Ready))
        }
    }
} finally {
    $report = @(
        "status: $(if ($DryRun) { 'dry-run' } elseif ($rolledBack) { 'rolled-back' } elseif ($smokeOk) { 'deployed' } else { 'failed' })",
        "app: $App", "commit: $head", "tree: $tree",
        "previous_image: $prevImage", "db_snapshot: $snapshot", "smoke_ok: $smokeOk", "rolled_back: $rolledBack", '---') + $log
    $report | Set-Content -LiteralPath (Join-Path $OutDirectory 'deploy-report.txt') -Encoding utf8
}
if ($DryRun) { Write-Host 'DEPLOY_DRY_RUN_OK'; exit 0 }
if ($rolledBack -or !$smokeOk) { Write-Host 'DEPLOY_FAILED'; exit 1 }
Write-Host 'DEPLOY_OK'
