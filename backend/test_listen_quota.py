from datetime import date, datetime, timezone
from types import SimpleNamespace
import json
import os
import subprocess
import sys
import tempfile
import pytest

import listen_curriculum as L


def row(stage=1, session=None, mode="ax", at="2026-10-26T15:00:00", key="x"):
    return SimpleNamespace(stage=stage, session=session, mode=mode,
                           created_at=datetime.fromisoformat(at), item_key=key)


def test_quota_kst_partial_exclusions_and_history():
    today = date(2026, 10, 27)
    rs = [row(at="2026-10-26T14:59:59")] * 24 + [row()] * 13
    rs += [row(session=s) for s in ("practice", "practice:review", "test:x", "wordtest:x")]
    rs += [row(mode="test"), row(mode="wordtest"), row(stage=2)]
    rs += [row(at="2026-10-27T15:00:00")]
    q = L.quota_days(rs, 1, today)
    assert (q["today_n"], q["partial_n"], q["today_answers"], q["met"]) == (1, 1, 13, False)
    assert q["days"] == [{"date": "2026-10-26", "n": 2, "met": True},
                          {"date": "2026-10-27", "n": 1, "met": False}]
    assert L.quota_days(rs, 1, today, keep=1)["days"] == q["days"][-1:]
    assert L.quota_days([], 1, today)["today_n"] == 0
    assert L.quota_days([row(at="2026-10-26T15:00:00+00:00")], 1, today)["today_answers"] == 1
    assert L.quota_days([row()] * 36, 1, today)["today_n"] == 3
    assert L.quota_days([row()] * 24, 1, today)["met"]
    assert set(L.DAILY_QUOTA.values()) == {2}


def test_ling_counts_sessions_not_rows():
    rs = [row(0, "ling:a", "ling", key="ling:" + k) for k in L.LING_KEYS + ["silent"]]
    rs += [rs[-1], row(0, "practice:review", "ling", key="ling:silent")]
    q = L.quota_days(rs, 0, date(2026, 10, 27))
    assert (q["today_n"], q["today_answers"], q["partial_n"]) == (1, 8, 0)
    assert L.counts_for_quota(None) and L.counts_for_quota("ling:a")
    assert not L.counts_for_quota("practice:dictation")


@pytest.mark.parametrize("stage", range(1, 6))
def test_each_stage_two_batches(stage):
    today = date(2026, 10, 27)
    n = L.BATCH_N[stage]
    q = L.quota_days([row(stage)] * (2 * n - 1), stage, today)
    assert q["today_n"] == 1 and not q["met"] and q["partial_n"] == n - 1
    assert L.quota_days([row(stage)] * (2 * n), stage, today)["met"]


def test_recommended_demo_and_placement():
    status = {n: "unlocked" for n in range(6)}
    assert L.recommended_stage(status) == 0
    assert L.recommended_stage(status, ling_done=True) == 1
    assert L.recommended_stage(status, 4, True) == 4
    status[4] = "locked"
    assert L.recommended_stage(status, 4, True) == 1
    status[1] = "mastered"
    assert L.recommended_stage(status, ling_done=True) == 2
    assert L.recommended_stage({n: "mastered" for n in range(6)}, ling_done=True) == 5


FLOW = r"""
import os, json, sqlite3
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post('/api/auth/register', json={'email':'quota@example.com','username':'quota','password':'pw-123456','agree_terms':True,'age_confirmed':True})
    h = {'Authorization':'Bearer '+r.json()['access_token']}
    def path():
        return c.get('/api/listen/curriculum', headers=h).json()
    for flag in ('1','demo','0'):
        os.environ['LIPLAB_UNLOCK_ALL'] = flag
        assert [s['status'] for s in path()['stages']] == ['unlocked'] + ['locked'] * 5
    os.environ.pop('LIPLAB_UNLOCK_ALL', None)
    assert path()['recommended'] == 0 and not path()['is_demo']
    demo = c.post('/api/auth/demo').json()
    dh = {'Authorization':'Bearer '+demo['access_token']}
    for flag in ('1', 'demo', '0'):
        os.environ['LIPLAB_UNLOCK_ALL'] = flag
        dp = c.get('/api/listen/curriculum', headers=dh).json()
        assert dp['is_demo'] and dp['all_stages_open'] and dp['experience_label'] == '체험용 · 모든 단계 열림'
        assert all(s['status'] != 'locked' for s in dp['stages']) and dp['recommended'] == 0
    ling = c.post('/api/listen/ling', headers=h, json={'results':dict.fromkeys(['m','u','a','i','sh','s'], True)}).json()
    assert ling['batch_completed'] and ling['xp_gained'] > 0 and ling['quota']['today_n'] == 1
    assert path()['recommended'] == 1 and path()['ling_today']
    it = c.get('/api/listen/stage/1', headers=h).json()['items'][0]
    req = {'stage':1,'item_key':it['key'],'same':True}
    for k in range(11):
        a = c.post('/api/listen/answer', headers=h, json=req).json()
        assert a['counted'] and not a['batch_completed'] and a['xp_gained'] == 0
    assert a['quota']['partial_n'] == 11
    a = c.post('/api/listen/answer', headers=h, json=req).json()
    assert a['batch_completed'] and a['xp_gained'] > 0 and a['quota']['today_n'] == 1
    for extra in ({'practice':True}, {'practice_mode':'contrast'}):
        a = c.post('/api/listen/answer', headers=h, json={**req, **extra}).json()
        assert not a['counted'] and a['xp_gained'] == 0 and a['quota']['today_n'] == 1
    for k in range(10):
        c.post('/api/listen/answer', headers=h, json=req).raise_for_status()
    def answer(_):
        r = c.post('/api/listen/answer', headers=h, json=req)
        r.raise_for_status()
        return r.json()
    with ThreadPoolExecutor(2) as pool:
        rs = list(pool.map(answer, range(2)))
    assert sum(r['batch_completed'] for r in rs) == 1
    assert sum(r['xp_gained'] > 0 for r in rs) == 1
    p = path()
    assert p['stages'][1]['quota']['today_n'] == 2 and p['stages'][1]['quota']['met']
    assert p['next_node'] == {'stage':1,'kind':'tomorrow','batch':1}
    td = c.get('/api/listen/today', headers=h).json()
    assert td['quotas']['1'] == p['stages'][1]['quota'] and td['next_node'] == p['next_node']
    task = next(t for t in c.get('/api/tasks', headers=h).json()['daily'] if t['key'] == 'listen_15')
    assert task['label'] == '소리 듣기 오늘 몫' and task['total'] == 2 and task['cur'] == 2 and task['done']
    first = c.post('/api/tasks/claim', headers=h).json()
    second = c.post('/api/tasks/claim', headers=h).json()
    assert 'listen_15' in [t['key'] for t in first['claimed']]
    assert 'listen_15' not in [t['key'] for t in second['claimed']]
    con = sqlite3.connect(os.environ['T_DB'])
    xp, streak = con.execute("select total_xp, streak_count from users where email='quota@example.com'").fetchone()
    assert streak == 1 and xp == ling['xp_gained'] + 2 * 16 + first['xp_gained']
    # 첫 묶음을 채우기 전에는 듣기 답 자체가 스트릭을 만들지 않는다.
    con.execute("update users set total_xp=0,streak_count=0,last_practice_date=NULL where email='quota@example.com'")
    con.commit()
    a = answer(0)
    assert a['xp_gained'] == 0 and not a['batch_completed']
    assert con.execute("select streak_count from users where email='quota@example.com'").fetchone()[0] == 0
    con.close()
print('RESULT OK')
"""


def test_quota_api_rewards_and_concurrency():
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f'sqlite+aiosqlite:///{d}/t.db', T_DB=f'{d}/t.db', PYTHONUTF8='1')
        for key in ('ANTHROPIC_API_KEY', 'LISTEN_PLACEMENT', 'LIPLAB_LISTEN_GEN'):
            env.pop(key, None)
        p = subprocess.run([sys.executable, '-c', FLOW], cwd=os.path.dirname(__file__), env=env,
                           capture_output=True, text=True, timeout=300)
    assert p.returncode == 0 and 'RESULT OK' in p.stdout, p.stdout[-2000:] + p.stderr[-5000:]
