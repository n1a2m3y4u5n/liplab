"""deploy_dev.ps1의 dry-run 아닌 경로를 가짜 flyctl로 시험한다(11/03 v38 사고 재발 방지).

Windows PowerShell 5.1에서 $ErrorActionPreference='Stop'일 때 `& flyctl ... 2>&1`은 flyctl이 stderr에 쓰는 진행 문구('Connecting to ...')를
NativeCommandError로 던졌다. dry-run은 flyctl을 부르지 않아 이 문제를 못 잡는다. 가짜 flyctl(.cmd)은 stderr에 쓰고도 0으로 끝난다.
Windows PowerShell(powershell.exe)이 없으면 건너뛴다.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "deploy_dev.ps1")
pytestmark = pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell 5.1이 필요하다")

FAKE_FLY = r'''@echo off
>> "%FAKE_FLY_LOG%" echo %*
echo Connecting to fake-host... 1>&2
echo [fly] progress line on stderr 1>&2
if "%1"=="machines" goto machines
if "%1"=="ssh" goto ssh
if "%1"=="deploy" goto deploy
exit /b 1
:machines
echo [{"config":{"image":"registry.fly.io/liplab-dev:deployment-PREV"}}]
exit /b 0
:ssh
if "%FAKE_FLY_SSH_FAIL%"=="1" exit /b 1
echo SNAPSHOT /data/backup/pre-20261103T000000Z.db 4096
exit /b 0
:deploy
echo Deploying... 1>&2
echo ok
exit /b 0
'''


class _Ready(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health/ready" else 404)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "deploy_dev.ps1")
    (root / "fly.dev.toml").write_text('app = "liplab-dev"\n', encoding="utf-8")
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "x")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=root, capture_output=True, text=True).stdout.strip()
    gate = tmp_path / "gate"
    gate.mkdir()
    (gate / "PREDEPLOY_DEV_OK.json").write_text(json.dumps({"ok": True, "commit": head, "tree": tree, "at_utc": "2026-11-03T00:00:00Z"}), encoding="utf-8")
    fly = tmp_path / "fakefly.cmd"
    fly.write_text(FAKE_FLY, encoding="ascii")
    return root, gate, fly


def _run(root, gate, fly, out, port, extra_env=None, extra_args=()):
    env = dict(os.environ, FLYCTL=str(fly), FAKE_FLY_LOG=str(out.parent / "fly.log"), **(extra_env or {}))
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "scripts" / "deploy_dev.ps1"),
         "-GateReport", str(gate), "-OutDirectory", str(out), "-BaseUrl", f"http://127.0.0.1:{port}", "-SkipSmoke",
         "-ReadyTimeoutSec", "20", *extra_args],
        cwd=root, env=env, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")


@pytest.fixture
def ready_server():
    srv = HTTPServer(("127.0.0.1", 0), _Ready)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()


def test_stderr_progress_text_does_not_abort_a_real_run(tmp_path, ready_server):
    root, gate, fly = _repo(tmp_path)
    out = tmp_path / "out"
    r = _run(root, gate, fly, out, ready_server)
    assert "DEPLOY_OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    assert r.returncode == 0
    report = (out / "deploy-report.txt").read_text(encoding="utf-8-sig")
    assert "status: deployed" in report and "deployment-PREV" in report and "SNAPSHOT" in report
    assert json.loads((out / "previous-image.json").read_text(encoding="utf-8-sig"))["image"].endswith("deployment-PREV")
    calls = (tmp_path / "fly.log").read_text(encoding="utf-8", errors="replace")
    assert "machines list" in calls and "ssh console" in calls and "deploy -c" in calls and "-a liplab-dev" in calls


def test_nonzero_flyctl_exit_still_aborts(tmp_path, ready_server):
    root, gate, fly = _repo(tmp_path)
    out = tmp_path / "out"
    r = _run(root, gate, fly, out, ready_server, {"FAKE_FLY_SSH_FAIL": "1"})
    assert r.returncode != 0 and "DEPLOY_OK" not in r.stdout
    calls = (tmp_path / "fly.log").read_text(encoding="utf-8", errors="replace")
    assert "deploy -c" not in calls          # DB 사본 단계에서 멈추면 배포하지 않는다


def test_token_like_text_is_not_written_to_report(tmp_path, ready_server):
    root, gate, fly = _repo(tmp_path)
    out = tmp_path / "out"
    r = _run(root, gate, fly, out, ready_server, {"FLY_API_TOKEN": "FlyV1 fm2_SECRETVALUE123"})
    assert r.returncode == 0
    for name in os.listdir(out):
        assert "SECRETVALUE123" not in (out / name).read_text(encoding="utf-8-sig", errors="replace")
    assert "SECRETVALUE123" not in r.stdout
