# KMSAV ROI registered training (docs/lipread-roi-kmsav-prereg-2026-11-02.md section 5).
# One training per GPU. Finished steps are skipped by marker; interrupted steps resume from last.pt.
# Judging is NOT done here. Started by a scheduled task (S4U) on each PC.
#   lab-sub   -Role K1     (K1 s0, K1 s1, B33 s0; B33 s0 moved back from lab-black, prereg section 10)
#   lab-main  -Role K2     (B33 s1, K2 s0, K2 s1)
#   lab-black -Role B33s0  (B33 s0, stopped and not used once lab-sub starts it)
param(
    [Parameter(Mandatory = $true)][string]$Role,
    [Parameter(Mandatory = $true)][string]$Code,      # folder holding roi_train.py
    [Parameter(Mandatory = $true)][string]$Tools,     # folder holding train_lipread.py
    [Parameter(Mandatory = $true)][string]$Data,      # run_k
    [Parameter(Mandatory = $true)][string]$Base,      # run_base
    [Parameter(Mandatory = $true)][string]$Py,
    [int]$MinFreeGb = 16,
    [int]$Omp = 4,
    [string]$GpuFrac = '0.45',
    [string]$MaxFrames = '4000',
    [string]$Amp = '1'
)
$ErrorActionPreference = 'Continue'
$Log = Join-Path $Data "run-$Role.log"
$Logs = Join-Path $Data 'logs'
New-Item -ItemType Directory -Force $Logs | Out-Null
function Say($m) { Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" -Encoding utf8 }
function FreeGb { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1) }
$env:LIPLAB_TOOLS = $Tools; $env:PYTHONPATH = $Tools; $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
$env:OMP_NUM_THREADS = "$Omp"; $env:ROI_PACK_READ = 'file'
$env:PYTORCH_CUDA_ALLOC_CONF = 'max_split_size_mb:128,garbage_collection_threshold:0.8'
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
$Train = Join-Path $Code 'roi_train.py'
$common = @('--patience', '6', '--resume', '--log-every', '100', '--gpu-frac', $GpuFrac, '--max-frames', $MaxFrames, '--amp', $Amp)

function WaitGpu {
    while ($true) {
        $busy = @(& nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader | Where-Object { $_ -match 'python' })
        if ($busy.Count -eq 0 -and (FreeGb) -ge ($MinFreeGb + 4)) { return }
        Say "WAIT gpu=[$($busy -join '; ')] free_gb=$(FreeGb)"
        Start-Sleep -Seconds 300
    }
}

function Step($name, $argv) {
    $lp = Join-Path $Logs "$name.log"
    if ((Test-Path $lp) -and (Select-String -Path $lp -Pattern 'ROI_TRAIN_DONE' -SimpleMatch -Quiet)) { Say "SKIP $name"; return }
    while ($true) {
        WaitGpu
        Say "START $name free_gb=$(FreeGb)"
        $all = @('-u', $Train, 'train') + $argv + $common
        $qs = ($all | ForEach-Object { '"' + $_ + '"' }) -join ' '
        $p = Start-Process -FilePath $Py -ArgumentList $qs -RedirectStandardOutput "$lp.out" -RedirectStandardError "$lp.err" -NoNewWindow -PassThru
        $null = $p.Handle
        $killed = $false
        while (-not $p.HasExited) {
            Start-Sleep -Seconds 60
            if ((FreeGb) -lt $MinFreeGb) {
                Say "LOW_MEM free_gb=$(FreeGb), stopping own process $($p.Id); resumes from last.pt"
                Stop-Process -Id $p.Id -Force
                $killed = $true
                break
            }
        }
        $p.WaitForExit()
        Get-Content "$lp.out", "$lp.err" -Encoding utf8 -ErrorAction SilentlyContinue | Add-Content -Path $lp -Encoding utf8
        if ($killed) { continue }
        if ($p.ExitCode -ne 0 -or -not (Select-String -Path $lp -Pattern 'ROI_TRAIN_DONE' -SimpleMatch -Quiet)) {
            Say "KMS_RUN_FAIL $name rc=$($p.ExitCode)"
            exit 1
        }
        Say "DONE $name"
        return
    }
}

Say "=== start role=$Role"
function B33($s) { Step "train_B33s$s" @('--run', $Base, '--seed', $s, '--cand', 'B33', '--out', "$Base\run_B33s$s", '--epochs', '40') }
switch ($Role) {
    'K1' {
        foreach ($s in '0', '1') {
            Step "train_K1s$s" @('--run', $Data, '--seed', $s, '--cand', 'K1', '--out', "$Data\run_K1s$s", '--epochs', '30', '--kms-frames', '600000')
        }
        B33 '0'
    }
    'B33s0' { B33 '0' }
    'K2' {
        B33 '1'
        foreach ($s in '0', '1') {
            Step "train_K2pre$s" @('--run', $Data, '--seed', $s, '--cand', 'K2pre', '--out', "$Data\run_K2pre$s", '--epochs', '10', '--kms-frames', '1500000', '--kms-only')
            Step "train_K2s$s" @('--run', $Data, '--seed', $s, '--cand', 'K2', '--out', "$Data\run_K2s$s", '--epochs', '20', '--kms-frames', '600000', '--init', "$Data\run_K2pre$s\model.pt", '--init-head')
        }
    }
    default { Say "bad role $Role"; exit 2 }
}
Say 'KMS_RUN_DONE'
