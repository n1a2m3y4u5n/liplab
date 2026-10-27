"""격리 DB에서 권한·하루 제한·삭제·점수를 검증한다."""
import pytest
from fastapi import HTTPException
from feedback import sus_score
from test_usage_events import _scenario

@pytest.mark.parametrize('answers,score', [([1]*10, 0), ([3]*10, 50), ([5]*10, 100), ([1,2,3,4,5]*2, 50)])
def test_score(answers, score):
    assert sus_score(answers) == score

@pytest.mark.parametrize('answers', [[], [1]*9, [6]*10, [True]*10, [2.5]*10])
def test_invalid_score(answers):
    with pytest.raises(HTTPException):
        sus_score(answers)

def test_feedback_end_to_end():
    _scenario(r'''
import asyncio, os
from uuid import uuid4
from fastapi.testclient import TestClient
import main
from sqlalchemy import select, func
from database import AsyncSessionLocal, UsageEvent, FeedbackDaily
from pilot_data import purge, user_data_models
assert FeedbackDaily in user_data_models()
with TestClient(main.app) as c:
    def reg(name):
        r=c.post('/api/auth/register',json={'email':name+'@example.com','username':name,'password':'test-password-123','agree_terms':True,'age_confirmed':True})
        assert r.status_code==201,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}, r.json()['user']['id']
    h,uid=reg('user'); a,_=reg('admin')
    h.update({'X-Usage-Device-ID':str(uuid4()),'X-Usage-Session-ID':str(uuid4()),'User-Agent':'Chrome/1 Windows'})
    def post(**kw):
        return c.post('/api/feedback',headers=h,json=kw)
    assert c.post('/api/feedback',json={'kind':'report','text':'test'}).status_code==401
    os.environ['LIPLAB_USAGE_LOG']='0'
    assert post(kind='prompt').json()['accepted'] is False
    os.environ['LIPLAB_USAGE_LOG']='1'
    assert post(kind='report',text='x'*501).status_code==422
    assert post(kind='report',text=' ').status_code==422
    assert post(kind='report',text='=bad,\nline',route='/learn/word',width=1200,height=800).json()['accepted']
    assert post(kind='sus',answers=[5]*10).status_code==409
    assert post(kind='prompt').json()['accepted']
    assert not post(kind='prompt').json()['accepted']
    assert post(kind='sus',answers=[True]*10).status_code==422
    assert post(kind='sus',answers=[0]*10).status_code==422
    assert post(kind='sus',answers=[5]*10).json()['accepted']
    assert not post(kind='skip').json()['accepted']
    assert post(kind='report',text='듣기',route='/listen/practice/sentence').json()['accepted']
    assert c.get('/api/admin/feedback',headers=h).status_code==403
    assert c.get('/api/admin/feedback?start=2020-01-01',headers=a).status_code==422
    assert c.get('/api/admin/feedback?start=2020-01-01&end=2020-01-02',headers=a).json()['records']==[]
    assert c.get('/api/admin/feedback',headers=a).json()['records']==[]
    rows=c.get('/api/admin/feedback?include_tests=true',headers=a).json()['records']
    report=next(r for r in rows if r['event']=='feedback_report' and r['route']=='/learn/word')
    assert any(r['route']=='/listen/practice/:mode' for r in rows)
    assert report['device_id']==h['X-Usage-Device-ID'] and report['session_id']==h['X-Usage-Session-ID']
    assert report['props']=={'text':'=bad,\nline','width':1200,'height':800}
    assert report['ua']=={'browser':'Chrome','os':'Windows','mobile':False}
    assert next(r for r in rows if r['event']=='sus_response')['props']['score']==100
    csv=c.get('/api/admin/feedback?format=csv&include_tests=true',headers=a)
    assert csv.status_code==200 and 'feedback_report' in csv.text and csv.headers['cache-control']=='no-store'
    async def remove():
        async with AsyncSessionLocal() as db:
            result=await purge(db,uid); await db.commit()
            assert result['feedback_daily']==2
            assert not (await db.execute(select(UsageEvent).where(UsageEvent.user_id==uid))).first()
    asyncio.run(remove())
''')


def test_daily_skip_rollover_and_retention():
    _scenario(r'''
import asyncio, importlib.util, os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, update
import main
from database import AsyncSessionLocal, FeedbackDaily, UsageEvent, User
with TestClient(main.app) as c:
    r=c.post('/api/auth/register',json={'email':'skip@example.com','username':'skip','password':'test-password-123','agree_terms':True,'age_confirmed':True})
    h={'Authorization':'Bearer '+r.json()['access_token']}; uid=r.json()['user']['id']
    def send(kind):
        return c.post('/api/feedback',headers=h,json={'kind':kind}).json()
    assert send('prompt')['accepted']
    assert send('skip')['accepted']
    assert not send('prompt')['accepted']
    assert not send('skip')['accepted']
    async def age():
        async with AsyncSessionLocal() as db:
            await db.execute(update(UsageEvent).where(UsageEvent.user_id==uid).values(ts=datetime(2020,1,1)))
            await db.execute(update(FeedbackDaily).where(FeedbackDaily.user_id==uid).values(day='2020-01-01',created_at=datetime(2020,1,1)))
            await db.commit()
    asyncio.run(age())
    assert send('prompt')['accepted']
    assert send('skip')['accepted']
    spec=importlib.util.spec_from_file_location('pr',os.path.join('..','scripts','pilot_retention.py'))
    pr=importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)
    args=['--study-end','2020-01-02','--retain-days','30','--include-usage','--ledger',os.environ['T_DB']+'.ledger']
    preview=asyncio.run(pr.run(args+['--today','2020-01-10','--apply','--mode','delete']))
    assert preview['refused'] and preview['feedback_daily_rows']==2
    result=asyncio.run(pr.run(args+['--today','2020-02-02','--apply','--mode','delete']))
    assert result['removed']['feedback_daily']==2 and result['removed']['usage_events']==3
    async def remain():
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(User).where(User.id==uid))).first()
            assert len((await db.execute(select(FeedbackDaily).where(FeedbackDaily.user_id==uid))).all())==2
    asyncio.run(remain())
''')
