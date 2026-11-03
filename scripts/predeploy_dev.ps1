param(
    [string]$Python = '',
    [string]$ReportDirectory = '',
    [string]$BaseRef = 'origin/main',   # fly.toml(전시앱)·Dockerfile ARG 기본값을 대조할 기준 판
    [switch]$AllowConfigChange          # 전시앱 설정이나 ARG 기본값을 의도해서 바꿀 때만
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
# 기본 Python은 관문 전용 gate-venv다(운영 규칙). 없을 때만 저장소의 .venv로 물러난다.
if (!$Python) {
    $gatePython = 'D:\work\hq\projects\liplab-wt\gate-venv\Scripts\python.exe'
    $Python = if (Test-Path -LiteralPath $gatePython) { $gatePython } else { Join-Path $root '.venv\Scripts\python.exe' }
}
if (!$ReportDirectory) { $ReportDirectory = Join-Path $root 'out' }
$Python = (Resolve-Path -LiteralPath $Python).Path
New-Item -ItemType Directory -Force -Path $ReportDirectory | Out-Null
$ReportDirectory = (Resolve-Path -LiteralPath $ReportDirectory).Path
$savedEnv = @{}
$settings = @{ PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8'; VITE_DGOP_STREAM = '1'; VITE_LIPREAD_ROI = '1' }

function Invoke-Gate([string]$Name, [scriptblock]$Command) {
    Write-Host "=== $Name ==="
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)" }
}

Push-Location $root
try {
    foreach ($name in $settings.Keys) {
        $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    Invoke-Gate 'frontend node_modules matches package-lock.json' { & node scripts/check_node_lock.mjs frontend }
    Invoke-Gate 'gate script unit tests (node)' { & node --test scripts/check_node_lock.test.mjs }
    Invoke-Gate 'model sha256 vs expected (scripts/dev_assets.sha256.json)' {
        & $Python -X utf8 scripts/check_assets.py --report (Join-Path $ReportDirectory 'model-hashes.json')
    }
    Invoke-Gate 'fly.toml / Dockerfile ARG defaults unchanged + gate meta' {
        $cfgArgs = @('--base', $BaseRef, '--meta', (Join-Path $ReportDirectory 'gate-meta.json'))
        if ($AllowConfigChange) { $cfgArgs += '--allow-change' }
        & $Python -X utf8 scripts/check_config.py @cfgArgs
    }
    Invoke-Gate 'API security inventory' { & $Python -X utf8 scripts/api_security_inventory.py --check }
    Invoke-Gate 'installed runtime dependency closure' {
        & $Python -X utf8 scripts/runtime_audit_requirements.py --inference --output (Join-Path $ReportDirectory 'runtime-audit-requirements.txt')
    }
    Invoke-Gate 'pip-audit (runtime dependency closure)' {
        & $Python -X utf8 -m pip_audit --disable-pip --no-deps -r (Join-Path $ReportDirectory 'runtime-audit-requirements.txt') --format json --output (Join-Path $ReportDirectory 'pip-audit.json')
    }
    Push-Location (Join-Path $root 'frontend')
    try { Invoke-Gate 'npm audit (including build dependencies)' { & npm.cmd audit --audit-level=moderate } }
    finally { Pop-Location }
    Invoke-Gate 'gitleaks working tree' {
        $scanner = Get-Command gitleaks -ErrorAction SilentlyContinue
        if ($scanner) { $scannerPath = $scanner.Source }
        elseif (Test-Path -LiteralPath 'D:\tools\gitleaks\gitleaks.exe') { $scannerPath = 'D:\tools\gitleaks\gitleaks.exe' }
        else { throw 'gitleaks is required' }
        & $scannerPath dir . --redact --exit-code 1 --report-format json --report-path (Join-Path $ReportDirectory 'gitleaks.json')
    }
    Invoke-Gate 'dev config / assets / default-off flags' {
        @'
import os, pathlib, re, tomllib
root = pathlib.Path.cwd()
cfg = tomllib.loads((root / 'fly.dev.toml').read_text(encoding='utf-8'))
assert cfg['app'] == 'liplab-dev', 'wrong app'
assert cfg['build']['args'] == {'WITH_ML': '1', 'DGOP_MODEL': 'ours', 'DGOP_STREAM': '1', 'LIPREAD_ROI': '1'}, 'review changed build args'
assert cfg['env']['BACKBONE_QUANT'] == 'int8'
experimental = {'VITE_COART_E', 'VITE_COART_E2', 'VITE_VISEME_V15', 'VITE_LIPREAD_ROI'}
source = root / 'frontend' / 'src'
for p in source.rglob('*'):
    if p.suffix in {'.js', '.jsx', '.mjs'}:
        experimental.update(re.findall(r'VITE_[A-Z0-9_]+', p.read_text(encoding='utf-8')))
experimental -= {'VITE_DGOP_STREAM', 'VITE_LIPREAD_ROI'}
for key in experimental:
    assert os.environ.get(key, '') in {'', '0'}, f'{key} must stay off/unset'
for p in (root / 'frontend').glob('.env*'):
    if p.name.endswith(('.example', '.sample')):
        continue
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        m = re.match(r'\s*(?:export\s+)?(VITE_\w+)\s*=\s*(.*?)\s*$', line)
        if m and m[1] in experimental:
            assert m[2].split('#', 1)[0].strip().strip('"\'') in {'', '0'}, f'{p.name}: {m[1]} must stay off'
for rel in ['backend/models/dgop_ours/aligner/model.int8.safetensors',
            'backend/models/dgop_ours/scorer/model.int8.safetensors',
            'backend/models/dgop_stream/student_w8.onnx',
            'backend/models/dgop_stream/calibration.json',
            'backend/models/kr_a4_wavlm.pt',
            'frontend/public/models/roi/kr_lipread_roi.web.onnx',
            'frontend/public/models/roi/kr_lipread_roi.web.meta.json']:
    p = root / rel
    assert p.is_file() and p.stat().st_size > 0, f'missing/empty asset: {rel}'
    print(f'{rel}: {p.stat().st_size} bytes')
print('liplab-dev config OK; DGOP_STREAM=1; LIPREAD_ROI=1; experimental flags off/unset')
'@ | & $Python -X utf8 -
    }
    Push-Location (Join-Path $root 'backend')
    try { Invoke-Gate 'backend pytest' { & $Python -X utf8 -m pytest -q } }
    finally { Pop-Location }
    Invoke-Gate 'lipread candidate wiring off = identical to pre-wiring (grab / input / logits / scores)' {
        & node scripts/lipread_off_identity.mjs (Join-Path $ReportDirectory 'lipread-off-identity.json')
    }
    Push-Location (Join-Path $root 'frontend')
    try {
        Invoke-Gate 'frontend npm test' { & npm.cmd test }
        Invoke-Gate 'frontend vite build (DGOP_STREAM=1, LIPREAD_ROI=1)' { & npx.cmd --no-install vite build }
    } finally { Pop-Location }
    Invoke-Gate 'scoring regression quick' {
        & $Python -X utf8 scripts/scoring_regress.py --quick --report (Join-Path $ReportDirectory 'scoring-regress-quick.md')
    }
    # deploy_dev.ps1이 읽는 통과 표식(같은 커밋·트리인지 배포 직전에 대조한다)
    $meta = Get-Content -LiteralPath (Join-Path $ReportDirectory 'gate-meta.json') -Raw | ConvertFrom-Json
    @{ ok = $true; commit = $meta.commit; tree = $meta.tree; at_utc = (Get-Date).ToUniversalTime().ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReportDirectory 'PREDEPLOY_DEV_OK.json') -Encoding utf8
    Write-Host 'PREDEPLOY_DEV_OK'
} catch {
    Write-Host "PREDEPLOY_DEV_FAILED: $_"
    exit 1
} finally {
    foreach ($name in $savedEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process')
    }
    Pop-Location
}
