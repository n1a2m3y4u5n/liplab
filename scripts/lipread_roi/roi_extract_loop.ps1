# roi_extract_loop.ps1 — 데스크탑(2026-10-17): 받은 538 클립의 입술 영역(88x88)을 30분마다 이어 뽑는다(docs/lipread-roi-2026-10.md 4·11절).
#   bg powershell -NoProfile -ExecutionPolicy Bypass -File D:\liplab\roi\roi_extract_loop.ps1
# CPU만 쓴다(GPU 안 씀). 이미 있는 npz는 건너뛴다. 받기가 끝나면(DL_DONE) 마지막으로 한 번 더 돌고 끝난다.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
$py = 'D:\liplab\vlip\Scripts\python.exe'
$lab = 'D:\liplab\lab'; $out = 'D:\liplab\roi\npz'; $log = 'D:\liplab\roi\logs'
New-Item -ItemType Directory -Force $out, $log | Out-Null
$dirs = @("$lab\data\v1_538r\clips", "$lab\data\e538r\clips", "$lab\data\roi538\a\clips", "$lab\data\roi538\b\clips")
foreach ($d in $dirs) { New-Item -ItemType Directory -Force $d | Out-Null }
Set-Location "$lab\tools"
while ($true) {
  $last = Test-Path "$lab\data\roi538\DL_DONE"
  $a = @(); foreach ($d in $dirs) { $a += '--clips'; $a += $d }
  "=== roi pass $(Get-Date -Format s) last=$last ===" | Out-File -Append -Encoding utf8 "$log\roi_extract.log"
  & $py -u lip_roi_extract.py @a --out $out --workers 4 --preview 6 *>> "$log\roi_extract.log"
  "=== roi pass end rc=$LASTEXITCODE $(Get-Date -Format s) npz=$((Get-ChildItem $out -Filter *.npz).Count) ===" | Out-File -Append -Encoding utf8 "$log\roi_extract.log"
  if ($last) { 'ROI_LOOP_DONE' | Out-File -Append -Encoding utf8 "$log\roi_extract.log"; break }
  Start-Sleep -Seconds 1800
}
