# LIPLAB 백엔드 시작 스크립트
# PowerShell에서 실행: powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1

$PYTHON = "C:\Users\korea\AppData\Local\Programs\Python\Python314\python.exe"
$BACKEND_DIR = "$PSScriptRoot\..\backend"

Write-Host "백엔드 시작중..." -ForegroundColor Green

# 기존 포트 8080 프로세스 정리
$existing = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
if ($existing) {
    # $pid는 PowerShell 5.1의 읽기 전용 자동 변수(현재 프로세스 ID)라 foreach 변수로 쓰면 "Cannot overwrite variable PID"로 멈춘다.
    # 또 8080을 쓰는 아무 프로세스나 끄지 않고, 명령줄에 uvicorn이 있는 것(예전 백엔드)만 끈다.
    $procIds = $existing | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue).CommandLine
        if ($cmd -notmatch 'uvicorn') {
            Write-Host "포트 8080을 쓰는 PID $procId 는 uvicorn이 아니라 종료하지 않았다. 직접 확인해 주세요." -ForegroundColor Red
            exit 1
        }
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "기존 백엔드 종료: PID $procId" -ForegroundColor Yellow
        } catch {
            Write-Host "PID $procId 종료 실패: $($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
    }
    Start-Sleep -Seconds 2
}

# 백엔드 디렉토리로 이동하여 uvicorn 실행
Set-Location $BACKEND_DIR

Write-Host "uvicorn 시작 (포트 8080)..." -ForegroundColor Cyan
& $PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
