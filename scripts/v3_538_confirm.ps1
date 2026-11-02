# V3 train538 재적합 확인 판정(docs/avatar-v3-538-prereg-2026-11-02.md 7절). 판정은 한 번뿐이다.
#   렌더·추출은 끊기면 다시 돌려도 되지만, 지표 계산을 시작하면 표식 CONFIRM_EVAL_STARTED를 남기고 그 뒤에는 실행을 거부한다.
param(
    [string]$Rebuild = 'D:\work\hq\projects\liplab-lab\data\train538\rebuild',
    [string]$Python = 'D:\work\hq\projects\liplab\.venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'; $env:HF_HUB_OFFLINE = '1'
$W = Join-Path $Rebuild 'v3_2026-11-02'
$Scripts = $PSScriptRoot
$Mark = Join-Path $W 'CONFIRM_EVAL_STARTED'
if (Test-Path $Mark) { 'V3C_REFUSED 확인 지표를 이미 계산했다'; exit 2 }
$Frozen = Join-Path $Scripts 'data\v3_538_frozen.json'
$Clf = Join-Path $W 'clf.pkl'
if ((Get-FileHash $Frozen -Algorithm SHA256).Hash.ToLower() -ne '9f8a1db97ad24fe111f815a8c2654067e45e3bba86429ef8a74f2a408704c8ad') { 'V3C_FAIL 동결 표 sha256'; exit 1 }
if ((Get-FileHash $Clf -Algorithm SHA256).Hash.ToLower() -ne 'e627f220faaf944ea8b01a02589d6122ffc844c7c5da48fe6047625998c6db49') { 'V3C_FAIL 판독기 sha256'; exit 1 }
$Sel = Join-Path $Rebuild 'sel.json'
$Tables = Join-Path $W 'tables_confirm.json'
$Jobs = Join-Path $W 'jobs_confirm.json'
Set-Location $Scripts
& $Python -W ignore v3_avatar.py tables --v15 (Join-Path $Scripts 'data\viseme_v15.json') --v3 $Frozen --out $Tables
if ($LASTEXITCODE -ne 0) { 'V3C_FAIL tables'; exit 1 }
& $Python -W ignore v3_avatar.py jobs --sel $Sel --backend (Join-Path (Split-Path $Scripts -Parent) 'backend') --half 1 --cond 'v1,v15,v3:v3_538_frozen,v3app' --out $Jobs
if ($LASTEXITCODE -ne 0) { 'V3C_FAIL jobs'; exit 1 }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Scripts 'v3_538_render.ps1') -Name cf -Jobs $Jobs -Tables $Tables -Port 5296
if ($LASTEXITCODE -ne 0) { 'V3C_FAIL render'; exit 1 }
$need = [int](& $Python -c "import json,sys; print(len(json.load(open(sys.argv[1], encoding='utf-8'))))" $Jobs)
$nr = (Get-ChildItem (Join-Path $W 'cf\renders') -Filter *.sched.json).Count
$nb = (Get-ChildItem (Join-Path $W 'cf\bs') -Filter *.json).Count
if ($nr -ne $need -or $nb -ne $need) { "V3C_FAIL 렌더 수 need=$need renders=$nr bs=$nb (지표 계산 전이라 다시 돌려도 된다)"; exit 1 }
Set-Content -Path $Mark -Value (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -Encoding utf8
& $Python -W ignore v3_avatar.py evaluate --sel $Sel --align (Join-Path $Rebuild 'align_real.jsonl') --real-bs (Join-Path $Rebuild 'real_bs') `
    --renders (Join-Path $W 'cf\renders') --render-bs (Join-Path $W 'cf\bs') --clf $Clf --half 1 --verdict --v3 v3-v3_538_frozen --v1 v1 --cands v15 v3app `
    --out (Join-Path $W 'ev_confirm.json')
if ($LASTEXITCODE -ne 0) { 'V3C_FAIL evaluate(표식이 남아 있으니 같은 코드 오류만 고치고 10절에 적는다)'; exit 1 }
'V3C_OK'
