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
    assert c.post('/api/events',json={'events':[]}).status_code==401
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
    data=c.get('/api/admin/usage',headers=a,params={'user_id':uid}).json()
    assert {'login', 'logout', 'lesson_complete'} <= {r['event'] for r in data['timeline']}
    row=next(r for r in data['timeline'] if r['event']=='lesson_complete')
    assert row['props']=={'duration_ms':1250,'action':'done'},row
    assert row['route'] is None
    assert set(row['ua'])=={'browser','os','mobile'}
    assert data['aggregate'] and data['daily']
    assert data['daily'][0]['connection_times'] and data['daily'][0]['recorded_duration_ms']==1250
    csv=c.get('/api/admin/usage',headers=a,params={'format':'csv'})
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
