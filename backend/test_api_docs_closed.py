"""배포 환경에서는 API 문서(/docs·/redoc·/openapi.json)가 닫히고, 개발·LIPLAB_API_DOCS=1에서는 열린다.
main이 import 시점에 환경변수를 읽으므로 임시 DB를 지정한 별도 프로세스로 확인한다."""
import json
import os
import subprocess
import sys
import tempfile

_SCRIPT = r'''
import json
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    print(json.dumps({p: c.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json", "/health")}))
'''


def _run(extra_env):
    with tempfile.TemporaryDirectory() as d:
        env = {k: v for k, v in os.environ.items() if k not in ("FLY_APP_NAME", "ENVIRONMENT", "LIPLAB_API_DOCS")}
        env.update({"DATABASE_URL": f"sqlite+aiosqlite:///{os.path.join(d, 't.db')}", "JWT_SECRET": "t" * 40,
                    "PYTHONUTF8": "1"})
        env.update(extra_env)
        r = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=os.path.dirname(os.path.abspath(__file__)),
                           env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-800:]
        return json.loads([l for l in r.stdout.splitlines() if l.startswith("{")][-1])


def test_docs_closed_when_deployed():
    out = _run({"FLY_APP_NAME": "liplab-dev"})
    assert all(out[p] == 404 for p in ("/docs", "/redoc", "/openapi.json"))
    assert out["/health"] == 200


def test_docs_open_in_dev_and_when_forced():
    assert _run({})["/openapi.json"] == 200
    assert _run({"FLY_APP_NAME": "liplab-dev", "LIPLAB_API_DOCS": "1"})["/openapi.json"] == 200
