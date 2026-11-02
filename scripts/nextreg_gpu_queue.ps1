param([ValidateSet('black','roi')][string]$Mode='black', [string]$Root, [string]$Python)
$ErrorActionPreference='Stop'
$env:OMP_NUM_THREADS='4'; $env:MKL_NUM_THREADS='4'; $env:OPENBLAS_NUM_THREADS='4'; $env:PYTHONUTF8='1'
$env:PYTHONPATH="$Root\code\tools"; $env:LIPLAB_TOOLS="$Root\code\tools"
function Log($s) { Add-Content -Encoding UTF8 "$Root\queue-$Mode.log" "$(Get-Date -Format o) $s" }
trap { Log "FAILED $($_.Exception.Message)"; 'failed' | Set-Content "$Root\$Mode-failed.txt"; exit 1 }
function IdleGPU {
    if($Mode -eq 'roi' -and (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 16777216){return $false}
    $g=& nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>$null
    if($LASTEXITCODE -ne 0 -or -not $g){return $false}
    $v=($g | Select-Object -First 1).Split(',')
    if([int]$v[0].Trim() -ge 20 -or [int]$v[1].Trim() -ge 1500){return $false}
    $apps=& nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>$null
    if($apps -match 'python'){return $false}
    $busy=Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and $_.CommandLine -match '(roi_train\.py|nextreg_roi\.py|nextreg_bs_lips\.py)' }
    if($busy){return $false}
    if($Mode -eq 'black' -or $Root.StartsWith('D:\work\liplab-gpu3\')) {
        if(Get-Process -Name 'Overwatch*','League*','VALORANT*' -ErrorAction SilentlyContinue){return $false}
        $sessions=& cmd.exe /c 'query user 2>nul'
        $activeKorean=([char]0xD65C).ToString()+[char]0xC131
        if($sessions -match "\bActive\b|$activeKorean"){return $false}
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
    $b=Get-Content -Raw -Encoding UTF8 "$Root\bs27\train_summary.json" | ConvertFrom-Json
    $c=Get-Content -Raw -Encoding UTF8 "$Root\bs107\train_summary.json" | ConvertFrom-Json
    $delta=$c.best_val_4way_mean-$b.best_val_4way_mean
    $cer=$c.best.val_cer-$b.best.val_cer
    @{status='validation_selection_only_no_adjudication'; accuracy_delta=$delta; cer_delta=$cer; keep_path=($delta -ge 0.03 -and $cer -le 0.02)} | ConvertTo-Json | Set-Content -Encoding UTF8 "$Root\bs-selection.json"
    'done' | Set-Content "$Root\bs-done.txt"
} else {
    $run=Join-Path (Split-Path $Root) 'data\run_base'
    if($env:COMPUTERNAME -eq 'CNSAI2025'){$run='D:\work\hq\projects\liplab-lab\data\roi-kmsav\run_base'}
    if($env:COMPUTERNAME -eq 'CNSAI') {
        & ollama stop qwen3.6:35b-a3b *> "$Root\ollama-stop.log"
        if($LASTEXITCODE){throw 'Ollama stop failed; do not start GPU training'}
    }
    $stable=0
    while($stable -lt 3){if(IdleGPU){$stable++}else{$stable=0}; Log "waiting GPU idle checks=$stable"; if($stable -lt 3){Start-Sleep 30}}
    $fraction='0.45'
    if($Root.StartsWith('D:\work\liplab-gpu3\')){$fraction='0.92'}
    foreach($seed in @(0,1)) {
        $p=Start-Process -FilePath $Python -ArgumentList @('-u',"$Root\code\tools\nextreg_roi.py",'train','--run',$run,'--out',"$Root\roi_s$seed",'--seed',"$seed",'--gpu-frac',$fraction) -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Root\roi_s$seed.log" -RedirectStandardError "$Root\roi_s$seed.err"
        $null=$p.Handle
        Log "GPU_START roi_s$seed PID=$($p.Id) run=$run"
        $p.WaitForExit(); Log "GPU_END roi_s$seed exit=$($p.ExitCode)"
        if($p.ExitCode -ne 0){throw 'ROI training failed'}
        while(-not(Test-Path "$Root\baseline_s$seed.ready")){Log "waiting same-seed B33 baseline $seed"; Start-Sleep 30}
        & $Python "$Root\code\tools\nextreg_roi.py" compare --run $run --candidate "$Root\roi_s$seed\model.pt" --baseline "$Root\baseline_s$seed.pt" --out "$Root\roi-selection-s$seed.json" *> "$Root\roi-compare-s$seed.log"
        if($LASTEXITCODE){throw 'ROI comparison failed'}
        $result=Get-Content -Raw -Encoding UTF8 "$Root\roi-selection-s$seed.json" | ConvertFrom-Json
        Log "SELECTION seed=$seed clean=$($result.clean_delta) degraded=$($result.degraded_delta) keep=$($result.keep_path)"
        if(-not $result.keep_path){break}
    }
    'done' | Set-Content "$Root\roi-done.txt"
}
