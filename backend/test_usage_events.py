"""임시 DB에서 수집 경계, 개인정보 필터, 권한, 파기 검증."""
import os
import subprocess
import sys
import tempfile


def test_usage():
    code = r'''
import asyncio, os
from fastapi.testclient import TestClient
import main
from sqlalchemy import select, func
from database import AsyncSessionLocal, UsageEvent
from pilot_data import purge, user_data_models
assert UsageEvent in user_data_models()
with TestClient(main.app) as c:
    def reg(name):
        r=c.post('/api/auth/register',json={'email':name+'@example.com','username':name,'password':'test-password-123','agree_terms':True,'age_confirmed':True})
        assert r.status_code==201,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']},r.json()['user']['id']
    h,uid=reg('user')
    a,aid=reg('admin')
    async def count():
        async with AsyncSessionLocal() as db:
            return (await db.execute(select(func.count()).select_from(UsageEvent))).scalar()
    assert asyncio.run(count())==0
    assert c.post('/api/events',headers=h,json={'events':[{'event':'route'}]}).json()=={'enabled':False,'accepted':0}
    assert c.post('/api/events',json={'events':[]}).json()['enabled'] is False
    os.environ['LIPLAB_USAGE_LOG']='1'
    assert c.post('/api/auth/login',json={'email':'user@example.com','password':'test-password-123'}).status_code==200
    assert c.post('/api/auth/logout',headers=h).status_code==200
    assert c.post('/api/events',headers=h,json={'events':[{'event':'route'}]*51}).status_code==422
    assert c.post('/api/events',headers=h,content='x'*32769).status_code==413
    assert c.post('/api/events',headers=h,json={'events':[{'event':'route','props':{'x':'a'*2049}}]}).status_code==413
    assert c.post('/api/events',headers=h,json={'events':[{'event':'login'}]}).status_code==422
    event={'event':'lesson_complete','route':'/learn/word?email=private@example.com','props':{'duration_ms':1250,'email':'secret@example.com','answer':'private answer','message':'private name','action':'done'}}
    assert c.post('/api/events',json={'token':h['Authorization'][7:],'events':[event]}).json()['accepted']==1
    assert c.get('/api/admin/usage',headers=h).status_code==403
    os.environ['LIPLAB_ADMIN_EMAILS']='admin@example.com'
    data=c.get('/api/admin/usage',headers=a,params={'user_id':uid,'include_tests':True}).json()
    assert {'login', 'logout', 'lesson_complete'} <= {r['event'] for r in data['timeline']}
    row=next(r for r in data['timeline'] if r['event']=='lesson_complete')
    assert row['props']=={'duration_ms':1250,'action':'done'},row
    assert row['route'] is None
    assert set(row['ua'])=={'browser','os','mobile'}
    assert data['aggregate'] and data['daily']
    assert data['daily'][0]['connection_times'] and data['daily'][0]['recorded_duration_ms']==1250
    csv=c.get('/api/admin/usage',headers=a,params={'format':'csv','include_tests':True})
    assert csv.status_code==200 and 'attachment' in csv.headers['content-disposition']
    assert 'lesson_complete' in csv.text and 'private' not in csv.text
    assert c.get('/api/admin/usage',headers=a,params={'start':'2020-01-01'}).status_code==422
    for i in range(5):
        assert c.post('/api/events',headers=h,json={'events':[{'event':'route'}]*50}).status_code==200
    assert c.post('/api/events',headers=h,json={'events':[{'event':'route'}]*50}).status_code==429
    async def remove():
        async with AsyncSessionLocal() as db:
            result=await purge(db,uid)
            await db.commit()
            assert result['usage_events']>0
            assert (await db.execute(select(func.count()).select_from(UsageEvent).where(UsageEvent.user_id==uid))).scalar()==0
    asyncio.run(remove())
print('USAGE_OK')
'''
    with tempfile.TemporaryDirectory() as folder:
        env=dict(os.environ,DATABASE_URL=f'sqlite+aiosqlite:///{folder}/usage.db', LIPLAB_USAGE_LOG='0', LIPLAB_CONTENT_WARMUP='0', JWT_SECRET='usage-test-secret-0123456789012345')
        p=subprocess.run([sys.executable,'-c',code],cwd=os.path.dirname(__file__),env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
        assert p.returncode==0,p.stdout[-2000:]+p.stderr[-3000:]
        assert 'USAGE_OK' in p.stdout


def _scenario(code):
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ, DATABASE_URL=f'sqlite+aiosqlite:///{folder}/usage.db',
                   LIPLAB_USAGE_LOG='1', LIPLAB_CONTENT_WARMUP='0', JWT_SECRET='usage-test-secret-0123456789012345',
                   LIPLAB_ADMIN_EMAILS='admin@example.com', T_DB=f'{folder}/usage.db')
        result = subprocess.run([sys.executable, '-c', code], cwd=os.path.dirname(__file__), env=env,
                                capture_output=True, text=True, encoding='utf-8', timeout=120)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-4000:]


def test_anonymous_demo_device_and_test_separation():
    _scenario(r'''
from uuid import uuid4
from fastapi.testclient import TestClient
import main, usage_events
from unittest.mock import patch
D1,D2,S1,S2 = [str(uuid4()) for _ in range(4)]
def ids(d=D1,s=S1):
    return {'X-Usage-Device-ID':d,'X-Usage-Session-ID':s}
def ev(event='landing_view',d=D1,s=S1):
    return {'event':event,'device_id':d,'anon_session_id':s,'is_demo':True,'user_id':123,'props':{'email':'private@example.com'}}
with TestClient(main.app) as c:
    def reg(name,email):
        r=c.post('/api/auth/register',json={'email':email,'username':name,'password':'test-password-123','agree_terms':True,'age_confirmed':True},headers=ids())
        assert r.status_code==201,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    admin=reg('admin','admin@example.com')
    real=reg('person','person@live.org')
    smoke=reg('smoke_check','deploy-smoke-123@live.org')
    for event in ('landing_view','login_view','signup_view','demo_start'):
        r=c.post('/api/events',json={'events':[ev(event)]})
        assert r.status_code==200,r.text
    assert c.post('/api/events',json={'events':[ev('lesson_start')]}).status_code==401
    assert c.post('/api/events',json={'events':[{'event':'landing_view'}]}).status_code==422
    assert c.post('/api/events',json={'token':'invalid','events':[ev()]}).status_code==401
    assert c.post('/api/events',json={'events':[ev()]*11}).status_code==422
    assert c.post('/api/events',headers=real,json={'events':[ev('route')]}).status_code==200
    assert c.post('/api/events',headers=smoke,json={'events':[ev('route',D2,S2)]}).status_code==200
    r=c.post('/api/auth/demo',headers=ids())
    assert r.status_code==200,r.text
    demo={'Authorization':'Bearer '+r.json()['access_token']}
    assert c.post('/api/events',headers=demo,json={'events':[ev('route')]}).status_code==200
    assert c.post('/api/auth/logout',headers={**demo,**ids()}).status_code==200
    assert c.post('/api/auth/demo',headers=ids(D2,S2)).status_code==200
    assert c.post('/api/events',headers=demo,json={'events':[ev('route',D2,S2)]}).status_code==200
    data=c.get('/api/admin/usage',headers=admin).json()
    assert data['test_aggregate'] and not any(r['is_test'] for r in data['timeline'])
    assert {'real','demo','anonymous'} <= {r['audience'] for r in data['timeline']}
    assert all(r['user_id'] is None and not r['is_demo'] and r['props']=={} for r in data['timeline'] if r['event'] in usage_events.PUBLIC_EVENTS)
    assert all(r['is_demo'] and r['device_id'] and r['anon_session_id'] for r in data['timeline'] if r['audience']=='demo')
    assert {'login','logout'} <= {r['event'] for r in data['timeline'] if r['is_demo']}
    assert len({r['device_id'] for r in data['timeline'] if r['is_demo']})==2
    assert not any(r['is_demo'] for r in data['timeline'] if r['audience']=='real')
    device=c.get('/api/admin/usage',headers=admin,params={'device_id':D2,'group_by':'device'}).json()
    assert set(device['timeline_groups'])=={D2}
    assert all(r['device_id']==D2 for r in device['timeline'])
    assert device['device_daily']
    tests=c.get('/api/admin/usage',headers=admin,params={'include_tests':True}).json()
    assert any(r['is_test'] for r in tests['timeline'])
    csv=c.get('/api/admin/usage',headers=admin,params={'include_tests':True,'format':'csv'})
    assert 'is_demo,is_test,audience' in csv.text and D1 in csv.text and 'private' not in csv.text
    usage_events._hits.clear()
    for _ in range(3):
        assert c.post('/api/events',json={'events':[ev()]*10}).status_code==200
    assert c.post('/api/events',json={'events':[ev()]}).status_code==429
    for _ in range(3):
        assert c.post('/api/events',json={'events':[ev(d=D2)]*10}).status_code==200
    assert c.post('/api/events',json={'events':[ev(d=str(uuid4()))]}).status_code==429
    assert all('testclient' not in str(key) for key in usage_events._hits)
    assert any(key[0]=='ip' and len(key[1])==64 for key in usage_events._hits)
''')


def test_existing_usage_schema_migrates_without_losing_rows():
    _scenario(r'''
import os, sqlite3
from sqlalchemy import create_engine
from database import User
engine=create_engine('sqlite:///'+os.environ['T_DB'])
with engine.begin() as conn:
    User.__table__.create(conn)
    conn.execute(User.__table__.insert().values(id=1,email='demo@liplab.app',username='demo',hashed_password='unused'))
    conn.exec_driver_sql('CREATE TABLE usage_events (id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,anon_session_id VARCHAR(64),ts DATETIME NOT NULL,event VARCHAR(48) NOT NULL,route VARCHAR(160),track VARCHAR(24),props JSON,app_version VARCHAR(40),ua JSON)')
    conn.exec_driver_sql("INSERT INTO usage_events(id,user_id,ts,event,props,ua) VALUES(1,1,'2026-10-27 00:00:00','login','{}','{}')")
engine.dispose()
from fastapi.testclient import TestClient
from uuid import uuid4
import main
for _ in range(2):
    with TestClient(main.app) as c:
        r=c.post('/api/events',json={'events':[{'event':'landing_view','device_id':str(uuid4()),'anon_session_id':str(uuid4())}]})
        assert r.status_code==200,r.text
with sqlite3.connect(os.environ['T_DB']) as db:
    assert db.execute('SELECT user_id,is_demo FROM usage_events WHERE id=1').fetchone()==(1,1)
    assert db.execute('SELECT count(*) FROM usage_events WHERE user_id IS NULL').fetchone()[0]==2
    assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='index' AND name='ix_usage_events_device_id'").fetchone()[0]==1
''')


def test_anonymous_usage_retention_respects_due_date_and_cutoff():
    _scenario(r'''
import asyncio, importlib.util, os
from datetime import datetime
from database import init_db, AsyncSessionLocal, UsageEvent
from sqlalchemy import select,func
spec=importlib.util.spec_from_file_location('retention','../scripts/pilot_retention.py')
retention=importlib.util.module_from_spec(spec);spec.loader.exec_module(retention)
async def go():
    await init_db()
    async with AsyncSessionLocal() as db:
        db.add_all([UsageEvent(user_id=None,event='landing_view',ts=datetime(2026,1,1)), UsageEvent(user_id=None,event='landing_view',ts=datetime(2026,2,1))])
        await db.commit()
    args=['--study-end','2026-01-01','--retain-days','30','--include-usage','--ledger',os.environ['T_DB']+'.jsonl']
    preview=await retention.run(args+['--today','2026-01-15'])
    assert preview['usage_rows']==1 and not preview['applied']
    early=await retention.run(args+['--today','2026-01-15','--apply','--mode','delete'])
    assert early['refused']
    done=await retention.run(args+['--today','2026-02-01','--apply','--mode','delete'])
    assert done['removed']['usage_events']==1
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(UsageEvent))).scalar()==1
asyncio.run(go())
''')
