param([ValidateSet('fusion','distill')][string]$Kind,[string]$Root,[string]$Python,[string]$Code,[string]$Run,[string]$Lips,[string]$Teacher)
$ErrorActionPreference='Stop'
$threads=if($Kind -eq 'fusion'){2}else{4}
$env:OMP_NUM_THREADS="$threads"; $env:MKL_NUM_THREADS="$threads"; $env:OPENBLAS_NUM_THREADS="$threads"
$env:PYTHONUTF8='1'; $env:PYTHONPATH=$Code; $env:LIPLAB_TOOLS=$Code
function Log($s){Add-Content -Encoding UTF8 "$Root\queue.log" "$(Get-Date -Format o) $s"}
trap{Log "FAILED $($_.Exception.Message)"; $_.Exception.Message|Set-Content -Encoding UTF8 "$Root\failed.txt"; exit 1}
function Idle {
    if((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 16777216){return $false}
    $g=& nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits
    if($LASTEXITCODE -ne 0 -or -not $g){return $false}
    $v=($g|Select-Object -First 1).Split(',')
    if([int]$v[0].Trim() -ge 20 -or [int]$v[1].Trim() -ge 1500){return $false}
    $apps=& nvidia-smi --query-compute-apps=process_name --format=csv,noheader
    if($LASTEXITCODE -ne 0 -or $apps -match 'python'){return $false}
    if($Kind -eq 'distill'){
        if(Get-Process -Name 'Overwatch*','League*','VALORANT*' -ErrorAction SilentlyContinue){return $false}
        $users=& cmd.exe /c 'query user 2>nul'
        $ko=([char]0xD65C).ToString()+[char]0xC131
        if($users -match "\bActive\b|$ko"){return $false}
    }
    return $true
}
function Train($tag,$arguments){
    $p=Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Root\$tag.log" -RedirectStandardError "$Root\$tag.err"
    $null=$p.Handle; Log "GPU_START $tag PID=$($p.Id)"
    $p.WaitForExit(); Log "GPU_END $tag exit=$($p.ExitCode)"
    if($p.ExitCode -ne 0){throw "$tag failed; no retry"}
}
$stable=0
while($stable -lt 3){if(Idle){$stable++}else{$stable=0}; Log "idle_checks=$stable"; if($stable -lt 3){Start-Sleep 30}}
if($Kind -eq 'fusion'){
    foreach($seed in @(0,1)){
        $args=@('-u',"$Root\nextreg_roi_lips.py",'train','--run',$Run,'--lips',$Lips,'--out',"$Root\seed$seed",'--seed',"$seed",'--gpu-frac','0.45')
        if($seed -eq 1){$args+=@('--previous-selection',"$Root\selection-s0.json")}
        Train "seed$seed" $args
        & $Python "$Root\nextreg_roi_lips.py" compare --run $Run --candidate "$Root\seed$seed" --baseline "$Run\run_B33s$seed" --seed $seed --out "$Root\selection-s$seed.json" *> "$Root\compare-s$seed.log"
        if($LASTEXITCODE){throw 'fusion selection failed'}
        $s=Get-Content -Raw -Encoding UTF8 "$Root\selection-s$seed.json"|ConvertFrom-Json
        Log "SELECTION seed=$seed accuracy=$($s.accuracy_delta) cer=$($s.cer_delta) keep=$($s.keep_path)"
        if(-not $s.keep_path){break}
    }
}else{
    Train 'student' @('-u',"$Root\nextreg_roi_distill.py",'train','--run',$Run,'--teacher',$Teacher,'--out',"$Root\student")
    Train 'finish' @('-u',"$Root\nextreg_roi_distill.py",'finish','--run',$Run,'--teacher',$Teacher,'--student',"$Root\student\model.pt",'--out',"$Root\result")
}
'done'|Set-Content "$Root\done.txt"
Log 'DONE'
