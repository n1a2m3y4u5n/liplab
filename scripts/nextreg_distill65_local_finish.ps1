param([string]$Root,[string]$Run,[string]$Python,[string]$Code,[string]$Extras)
$ErrorActionPreference='Stop'
trap{$_.Exception.Message|Set-Content "$Root\local-finish-failed.txt";exit 1}
$env:PYTHONPATH="$Extras;$Code";$env:LIPLAB_TOOLS=$Code;$env:PYTHONUTF8='1';$env:PYTHONDONTWRITEBYTECODE='1'
$env:OMP_NUM_THREADS='4';$env:MKL_NUM_THREADS='4';$env:OPENBLAS_NUM_THREADS='4'
if((Get-FileHash "$Extras\manifest.json").Hash -ne 'd05d73bcb51bb6e43a5ffbc1562dfb5c7b7d0f2063b5367e5fc54e16e2fa16f0'){throw 'Dependency manifest mismatch'}
if((Get-FileHash "$Root\nextreg_distill65.py").Hash -ne '92b916951fdb4975dc05b42ee09167ccd22dbb465cfb74f848516afa15468165'){throw 'Registered source changed'}
if((Get-FileHash "$Root\seed0\model.pt").Hash -ne '4355af944ba41736a12ff0c9e70dff395745f6d18ef2b6c3578688aff547a9ca'){throw 'Selected model changed'}
if((Get-FileHash "$Root\teacher_b33s0.pt").Hash -ne 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a'){throw 'Teacher changed'}
if((Get-FileHash "$Run\prep.json").Hash -ne '084b793fbccb636035d9285efa3c78cc4f9d513a8fadd0b603637ded802f1a0b'){throw 'Split changed'}
if((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 16777216){throw 'RAM below16GB; yield'}
$g=& nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits
if($LASTEXITCODE -ne 0 -or !$g){throw 'GPU unavailable'}
$v=($g|Select-Object -First 1).Split(',')
if([int]$v[0].Trim() -ge 20 -or [int]$v[1].Trim() -ge 1500){throw 'GPU occupied; yield'}
if((& nvidia-smi --query-compute-apps=process_name --format=csv,noheader) -match 'python'){throw 'Other Python GPU work; yield'}
$once=[IO.File]::Open("$Root\local-seed0-evaluation-once.txt",[IO.FileMode]::CreateNew)
$once.Close()
$p=Start-Process -FilePath $Python -ArgumentList @('-u',"$Root\nextreg_distill65.py",'finish','--run',$Run,'--teacher',"$Root\teacher_b33s0.pt",'--student',"$Root\seed0\model.pt",'--out',"$Root\seed0_result",'--seed','0') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Root\local-finish.log" -RedirectStandardError "$Root\local-finish.err"
$null=$p.Handle;$p.WaitForExit()
if($p.ExitCode -ne 0){throw "Local finish failed $($p.ExitCode); preserve once marker and any selection JSON"}
'done'|Set-Content "$Root\local-finish-done.txt"
