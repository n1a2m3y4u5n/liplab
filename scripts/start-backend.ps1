# LIPLAB 백엔드 시작 스크립트
# PowerShell에서 실행: powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1

$PYTHON = "C:\Users\korea\AppData\Local\Programs\Python\Python314\python.exe"
$BACKEND_DIR = "$PSScriptRoot\..\backend"

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
