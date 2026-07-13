# LIPLAB 백엔드 시작 스크립트
# PowerShell에서 실행: powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1

$BACKEND_DIR = "$PSScriptRoot\..\backend"
$FRONTEND_DIR = "$PSScriptRoot\..\frontend"
$FRONTEND_INDEX = "$FRONTEND_DIR\dist\index.html"
$VENV_PYTHON = "$PSScriptRoot\..\.venv\Scripts\python.exe"

if (Test-Path $VENV_PYTHON) {
    $PYTHON = $VENV_PYTHON
} else {
    $PYTHON = (Get-Command python -ErrorAction Stop).Source
}

# 8080 단독 실행에서도 React 앱을 제공할 수 있도록 빌드가 없을 때만 생성한다.
if (-not (Test-Path $FRONTEND_INDEX)) {
    $NPM = (Get-Command npm.cmd -ErrorAction Stop).Source
    Write-Host "프론트엔드 빌드가 없어 먼저 생성합니다..." -ForegroundColor Cyan
    Push-Location $FRONTEND_DIR
    try {
        & $NPM run build
        if ($LASTEXITCODE -ne 0) {
            throw "프론트엔드 빌드에 실패했습니다."
        }
    } finally {
        Pop-Location
    }
}

Write-Host "백엔드 시작중..." -ForegroundColor Green

# 기존 포트 8080 프로세스 정리
$existing = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
if ($existing) {
    $pids = $existing | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "기존 프로세스 종료: PID $pid" -ForegroundColor Yellow
        } catch {}
    }
    Start-Sleep -Seconds 2
}

# 백엔드 디렉토리로 이동하여 uvicorn 실행
Set-Location $BACKEND_DIR

Write-Host "uvicorn 시작 (포트 8080)..." -ForegroundColor Cyan
& $PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
