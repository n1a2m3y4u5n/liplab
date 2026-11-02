$ErrorActionPreference = 'Stop'
Set-Location 'D:\work\hq\projects\liplab-wt\cleaneval'
$env:PYTHONUTF8 = '1'
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
& 'D:\work\hq\projects\liplab\.venv\Scripts\python.exe' -u scripts\clean_eval_prepare.py
exit $LASTEXITCODE
