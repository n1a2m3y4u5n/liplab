# 아바타 판독 곡선(docs/avatar-readability-2026-10.md) 데스크탑 실행기. 단계마다 끝 표식을 남기고, 이미 있는 렌더·ROI·추출은 건너뛴다.
#   powershell -File avr_run.ps1 -Stage words     탐색 낱말 렌더(36조건 × 150) → ROI → 4지 점수(score_explore.json)
#   powershell -File avr_run.ps1 -Stage fence     울타리 문장 렌더(36조건 × 30 × 1.0·2.0배) → 블렌드셰이프 → fence_eval.json
#   powershell -File avr_run.ps1 -Stage select    관문 0·울타리·선택 → sel.json (이 파일을 커밋한 뒤에 confirm)
#   powershell -File avr_run.ps1 -Stage confirm   확인 낱말(기준·고른 조건, 1.0·2.0배) → 판정 judge.json
param([Parameter(Mandatory = $true)][string]$Stage, [int]$RW = 2, [int]$XW = 2)
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; $env:LIPLAB_TOOLS = 'D:/liplab/v1/dax'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:\liplab\cache\pw'
$env:FFMPEG = 'D:\liplab\vrend\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win64-v4.2.2.exe'
$PY = 'D:\liplab\vlip\Scripts\python.exe'; $RP = 'D:\liplab\vrend\Scripts\python.exe'
$R = 'D:\liplab\avread'; $W = 'D:\liplab\wt-avread\scripts'; $M = 'D:/liplab/mac_archive/liplab-lab/data'
$ONNX = 'D:\liplab\roi\judge\onnx\roi_R2s0.int8.onnx'
$V2 = "$M/v2_avatar/sel.json;$M/pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/align_real.jsonl;$M/pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/bs_real"
$V3 = "$M/v3_avatar/sel_confirm.json;$M/pod_runs/20261017_rjght1io2i277z/v3/align_confirm.jsonl;$M/pod_runs/20261017_rjght1io2i277z/v3/real_bs"
function Run($exe, $argv) { & $exe @argv; if ($LASTEXITCODE -ne 0) { "AVR_STAGE_FAIL $Stage rc=$LASTEXITCODE"; exit $LASTEXITCODE } }
function Render($jobs, $out, $nw) { Run $RP @("$W\v2_render\render_jobs.py", '--harness', "$R\harness", '--jobs', $jobs, '--out', $out, '--workers', "$nw", '--gl', 'd3d11') }
function Roi($clips, $out) { Run $PY @('D:\liplab\v1\dax\lip_roi_extract.py', '--clips', $clips, '--out', $out, '--workers', "$XW", '--preview', '6') }
function Bs($clips, $out) {
  New-Item -ItemType Directory -Force $out | Out-Null
  $todo = Get-ChildItem "$clips\*.mp4" | ? { -not (Test-Path (Join-Path $out ($_.BaseName + '.json'))) } | % { $_.FullName + "`t" + (Join-Path $out ($_.BaseName + '.json')) }
  $ps = @()
  for ($k = 0; $k -lt $XW; $k++) {
    $part = @($todo | ? { ([array]::IndexOf($todo, $_) % $XW) -eq $k })
    if (-not $part.Count) { continue }
    [IO.File]::WriteAllLines("$out\_list$k.tsv", $part)
    $ps += Start-Process -FilePath $PY -ArgumentList @('D:\liplab\v1\dax\extract_blendshapes.py', '--lips', '--no-audio', '--list', "$out\_list$k.tsv") -NoNewWindow -PassThru -RedirectStandardOutput "$out\_bs$k.log" -RedirectStandardError "$out\_bs$k.err"
  }
  $ps | Wait-Process
  "BS_DONE " + (Get-ChildItem "$out\*.json").Count
}
cd "$W\avread"
switch ($Stage) {
  'words' {
    Run $PY @('avread.py', 'jobs', '--items', "$R\items.json", '--split', 'explore', '--conds', 'all', '--out', "$R\jobs_explore.json")
    Render "$R\jobs_explore.json" "$R\rw" $RW
    Roi "$R\rw" "$R\npz_w"
    Run $PY @('avread.py', 'score', '--items', "$R\items.json", '--split', 'explore', '--npz', "$R\npz_w", '--renders', "$R\rw", '--onnx', $ONNX, '--resume', '--out', "$R\score_explore.json")
    'AVR_WORDS_DONE'
  }
  'fence' {
    Run $PY @('avread.py', 'jobs', '--fence', "$R\fence.json", '--fence-jobs', '--conds', 'all', '--out', "$R\jobs_fence.json")
    Render "$R\jobs_fence.json" "$R\rf" $RW
    Bs "$R\rf" "$R\bs_f"
    Run $PY @('avread.py', 'fence', '--fence', "$R\fence.json", '--renders', "$R\rf", '--bs', "$R\bs_f", '--v2', $V2, '--v3', $V3, '--out', "$R\fence_eval.json")
    'AVR_FENCE_DONE'
  }
  'select' {
    Run $PY @('avread.py', 'select', '--score', "$R\score_explore.json", '--fence', "$R\fence_eval.json", '--out', "$R\sel.json")
  }
  'confirm' {
    $sel = (Get-Content "$R\sel.json" -Raw | ConvertFrom-Json).selected
    if (-not $sel) { 'AVR_CONFIRM_SKIP 고른 조건 없음'; exit 0 }
    Run $PY @('avread.py', 'jobs', '--items', "$R\items.json", '--split', 'confirm', '--conds', "V1_j1.0_l1.0,$sel", '--speeds', '1.0,2.0', '--out', "$R\jobs_confirm.json")
    Render "$R\jobs_confirm.json" "$R\rc" $RW
    Roi "$R\rc" "$R\npz_c"
    Run $PY @('avread.py', 'score', '--items', "$R\items.json", '--split', 'confirm', '--npz', "$R\npz_c", '--renders', "$R\rc", '--onnx', $ONNX, '--conds', "V1_j1.0_l1.0,$sel", '--out', "$R\score_confirm.json")
    Run $PY @('avread.py', 'judge', '--score', "$R\score_confirm.json", '--sel', "$R\sel.json", '--out', "$R\judge.json")
    Run $PY @('avread.py', 'score', '--items', "$R\items.json", '--split', 'confirm', '--npz', "$R\npz_c", '--renders', "$R\rc", '--onnx', $ONNX, '--conds', "V1_j1.0_l1.0,$sel", '--speed', '2.0', '--out', "$R\score_confirm_s2.json")
    'AVR_CONFIRM_DONE'
  }
}
exit 0
