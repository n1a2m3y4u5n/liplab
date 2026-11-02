param([ValidateSet('C','D')][string]$Mode,[int]$Seed=0,[string]$Root,[string]$Python,[string]$Code,[string]$Run)
$ErrorActionPreference='Stop'
$threads=4
$env:OMP_NUM_THREADS="$threads";$env:MKL_NUM_THREADS="$threads";$env:OPENBLAS_NUM_THREADS="$threads"
$env:PYTHONUTF8='1';$env:PYTHONPATH=$Code;$env:LIPLAB_TOOLS=$Code
function Log($s){Add-Content -Encoding UTF8 "$Root\queue.log" "$(Get-Date -Format o) $s"}
trap{Log "FAILED $($_.Exception.Message)";$_.Exception.Message|Set-Content -Encoding UTF8 "$Root\failed.txt";exit 1}
function Idle {
    if((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 16777216){return $false}
    $g=& nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits
    if($LASTEXITCODE -ne 0 -or -not $g){return $false}
    $v=($g|Select-Object -First 1).Split(',')
    if([int]$v[0].Trim() -ge 20 -or [int]$v[1].Trim() -ge 1500){return $false}
    $apps=& nvidia-smi --query-compute-apps=process_name --format=csv,noheader
    if($LASTEXITCODE -ne 0 -or $apps -match 'python'){return $false}
    if($Mode -eq 'D'){
        if(Get-Process -Name 'Overwatch*','League*','VALORANT*' -ErrorAction SilentlyContinue){return $false}
        $sessions=& cmd.exe /c 'query user 2>nul'
        $ko=([char]0xD65C).ToString()+[char]0xC131
        if($sessions -match "\bActive\b|$ko"){return $false}
    }
    return $true
}
function Step($tag,$arguments){
    $p=Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Root\$tag.log" -RedirectStandardError "$Root\$tag.err"
    $null=$p.Handle;Log "STEP_START $tag PID=$($p.Id)"
    $p.WaitForExit();Log "STEP_END $tag exit=$($p.ExitCode)"
    if($p.ExitCode -ne 0){throw "$tag failed; no retry"}
}
if($env:COMPUTERNAME -eq 'CNSAI'){
    $body=@{model='qwen3.6:35b-a3b';keep_alive=0;stream=$false}|ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -Body $body -ContentType 'application/json' -TimeoutSec 30|ConvertTo-Json|Set-Content "$Root\ollama-stop.log"
}
$stable=0
while($stable -lt 3){if(Idle){$stable++}else{$stable=0};Log "idle_checks=$stable";if($stable -lt 3){Start-Sleep 30}}
if($Mode -eq 'C'){
 $entry="$Root\nextreg_distill50.py"
 Step 'student' @('-u',$entry,'train','--run',$Run,'--teacher',"$Root\teacher_b33s0.pt",'--out',"$Root\student",'--seed',"$Seed")
 if($env:COMPUTERNAME -eq 'CNSAI2025'){'export_on_main_required'|Set-Content "$Root\export-pending.txt"}else{
 Step 'finish' @('-u',$entry,'finish','--run',$Run,'--teacher',"$Root\teacher_b33s0.pt",'--student',"$Root\student\model.pt",'--out',"$Root\result",'--seed',"$Seed")
 }
}else{
 $entry="$Root\nextreg_fusion_distill65.py"
 Step 'student' @('-u',$entry,'train','--run',$Run,'--teacher',"$Root\full_fusion_s0.pt",'--lips',"$Root\lips",'--baseline',"$Root\baseline_B33s0",'--out',"$Root\seed0")
 Step 'finish' @('-u',$entry,'finish','--run',$Run,'--teacher',"$Root\full_fusion_s0.pt",'--lips',"$Root\lips",'--baseline',"$Root\baseline_B33s0",'--student',"$Root\seed0\model.pt",'--out',"$Root\result")
}
'done'|Set-Content "$Root\done.txt"
Log 'DONE compute; local finalization may remain'
