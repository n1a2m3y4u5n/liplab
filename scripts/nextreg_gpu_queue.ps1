param([ValidateSet('black','roi')][string]$Mode='black', [string]$Root, [string]$Python)
$ErrorActionPreference='Stop'
$env:OMP_NUM_THREADS='4'; $env:MKL_NUM_THREADS='4'; $env:OPENBLAS_NUM_THREADS='4'; $env:PYTHONUTF8='1'
$env:PYTHONPATH="$Root\code\tools"; $env:LIPLAB_TOOLS="$Root\code\tools"
function Log($s) { Add-Content -Encoding UTF8 "$Root\queue-$Mode.log" "$(Get-Date -Format o) $s" }
trap { Log "FAILED $($_.Exception.Message)"; 'failed' | Set-Content "$Root\$Mode-failed.txt"; exit 1 }
function IdleGPU {
    $g=& nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>$null
    if($LASTEXITCODE -ne 0 -or -not $g){return $false}
    $v=($g | Select-Object -First 1).Split(',')
    if([int]$v[0].Trim() -ge 20 -or [int]$v[1].Trim() -ge 1500){return $false}
    $busy=Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and $_.CommandLine -match '(roi_train\.py|nextreg_roi\.py|nextreg_bs_lips\.py)' }
    if($busy){return $false}
    if($Mode -eq 'black') {
        if(Get-Process -Name 'Overwatch*','League*','VALORANT*' -ErrorAction SilentlyContinue){return $false}
        $sessions=& cmd.exe /c 'query user 2>nul'
        if($sessions -match '\bActive\b|활성'){return $false}
    }
    return $true
}
if($Mode -eq 'black') {
    while(-not(Test-Path "$Root\bs-prep-exit.txt")){Log 'waiting CPU preparation'; Start-Sleep 30}
    if((Get-Content "$Root\bs-prep-exit.txt") -ne 'exit=0'){throw 'CPU preparation failed'}
    $stable=0
    while($stable -lt 3){if(IdleGPU){$stable++}else{$stable=0}; Log "waiting GPU idle checks=$stable"; if($stable -lt 3){Start-Sleep 30}}
    foreach($kind in @('bs27','bs107')) {
        $args=@('-u',"$Root\code\tools\nextreg_bs_lips.py",'--bench',"$Root\bench.npz",'--split',"$Root\bs\input\split.json",'--out',"$Root\$kind")
        if($kind -eq 'bs107'){$args+='--lips'}
        $p=Start-Process -FilePath $Python -ArgumentList $args -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Root\$kind.log" -RedirectStandardError "$Root\$kind.err"
        $null=$p.Handle
        Log "GPU_START $kind PID=$($p.Id)"
        $p.WaitForExit()
        Log "GPU_END $kind exit=$($p.ExitCode)"
        if($p.ExitCode -ne 0){throw "$kind training failed"}
    }
    'done' | Set-Content "$Root\bs-done.txt"
} else {
    $run=Join-Path (Split-Path $Root) 'data\run_base'
    if($env:COMPUTERNAME -eq 'CNSAI2025'){$run='D:\work\hq\projects\liplab-lab\data\roi-kmsav\run_base'}
    $p=Start-Process -FilePath $Python -ArgumentList @('-u',"$Root\code\tools\nextreg_roi.py",'train','--run',$run,'--out',"$Root\roi_s0",'--seed','0') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Root\roi_s0.log" -RedirectStandardError "$Root\roi_s0.err"
    $null=$p.Handle
    Log "GPU_START roi_s0 PID=$($p.Id) run=$run"
    $p.WaitForExit(); Log "GPU_END roi_s0 exit=$($p.ExitCode)"
    if($p.ExitCode -ne 0){throw 'ROI training failed'}
    'trained' | Set-Content "$Root\roi-trained.txt"
}
