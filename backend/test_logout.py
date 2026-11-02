"""로그아웃 폐기·기존 JWT·데모 세션 격리 회귀(임시 DB만 사용)."""
import os
import subprocess
import sys
import tempfile


def test_logout_revokes_only_presented_token():
    scenario = '''
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from auth import jwt, SECRET_KEY, ALGORITHM
import main
with TestClient(main.app) as c:
    csp = c.get('/api/auth/me').headers['content-security-policy']
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net" in csp
    assert "worker-src 'self' blob:" in csp
    assert "'unsafe-eval'" not in csp
    a = c.post('/api/auth/demo').json()
    b = c.post('/api/auth/demo').json()
    assert a['access_token'] != b['access_token']
    headers = lambda t: {'Authorization': 'Bearer ' + t}
    ha, hb = headers(a['access_token']), headers(b['access_token'])
    assert c.post('/api/auth/logout', headers=ha).status_code == 200
    assert c.get('/api/auth/me', headers=ha).status_code == 401
    assert c.get('/api/auth/me', headers=hb).status_code == 200
    legacy = jwt.encode({'sub': str(a['user']['id']), 'exp': datetime.utcnow() + timedelta(hours=1)}, SECRET_KEY, algorithm=ALGORITHM)
    hl = headers(legacy)
    assert c.get('/api/auth/me', headers=hl).status_code == 200
    assert c.post('/api/auth/logout', headers=hl).status_code == 200
    assert c.get('/api/auth/me', headers=hl).status_code == 401
    expired = jwt.encode({'sub': str(a['user']['id']), 'exp': datetime.utcnow() - timedelta(seconds=1)}, SECRET_KEY, algorithm=ALGORITHM)
    assert c.get('/api/auth/me', headers=headers(expired)).status_code == 401
    bad = jwt.encode({'sub': str(a['user']['id']), 'exp': datetime.utcnow() + timedelta(hours=1)}, 'wrong-signing-key-for-negative-test', algorithm=ALGORITHM)
    assert c.get('/api/auth/me', headers=headers(bad)).status_code == 401
    assert c.post('/api/auth/logout').status_code in (401, 403)
print('logout OK')
'''
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ, DATABASE_URL=f'sqlite+aiosqlite:///{folder}/test.db',
                   LIPLAB_CONTENT_WARMUP='0', PYTHONUTF8='1')
        result = subprocess.run([sys.executable, '-c', scenario],
                                cwd=os.path.dirname(__file__), env=env,
                                capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-3000:]
    assert 'logout OK' in result.stdout
