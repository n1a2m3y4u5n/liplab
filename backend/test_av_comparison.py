"""P17 분모·조건별 합산, 권한, 자료 대기, SNR 동결, 서버 채점·완료 검사."""
from types import SimpleNamespace
import pytest
from av_comparison import gains
from test_usage_events import _scenario

@pytest.mark.parametrize('values,index', [((0.3,0.4,0.5),0.5),((0.5,0.6,0.5),None),((0.7,0.8,0.5),None)])
def test_gain_denominator(values, index):
    rows = [SimpleNamespace(condition=c,matched=round(v*10),total=10) for c,v in zip(('A','avatar','real'),values)]
    result = gains(rows)
    if index is None:
        assert result['relative_index'] is None
    else:
        assert result['relative_index'] == pytest.approx(index)
    assert gains([])['relative_index'] is None

def test_av_lifecycle():
    _scenario(r'''
import asyncio, json, os
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select
import main
from database import AsyncSessionLocal, LearningProfile, AvComparison, AvComparisonAnswer
from pilot_data import user_data_models
assert AvComparison in user_data_models() and AvComparisonAnswer in user_data_models()
root=Path(os.environ['T_DB']).parent
os.environ['LIPLAB_REAL_FACE_MEDIA_DIR']=str(root)
os.environ['LIPLAB_AV_COMPARISON_MANIFEST']=str(root/'av.json')
for f in ['real.mp4','avatar.mp4','noise.wav']:
    (root/f).write_bytes(b'test-only-media')
items=[dict(id=str(i),text='문장 '+str(i),real_media='real.mp4',avatar_media='avatar.mp4',speech_rms_dbfs=-20,consent=True,talker='T1') for i in range(6)]
manifest=dict(status='frozen',version='test1',items=items,noise='noise.wav')
(root/'av.json').write_text(json.dumps(manifest),encoding='utf-8')
with TestClient(main.app) as c:
    def reg(name):
        r=c.post('/api/auth/register',json={'email':name+'@example.com','username':name,'password':'test-password-123','agree_terms':True,'age_confirmed':True})
        return {'Authorization':'Bearer '+r.json()['access_token']},r.json()['user']['id']
    h,uid=reg('participant'); other,other_id=reg('other')
    base='/api/pilot/av-comparison'
    os.environ.pop('LIPLAB_AV_COMPARISON',None)
    assert c.get(base,headers=h).status_code==404
    os.environ['LIPLAB_AV_COMPARISON']='1'; os.environ['LIPLAB_PILOT']='1'
    assert c.get(base,headers=h).status_code==403
    async def join():
        async with AsyncSessionLocal() as db:
            p=(await db.execute(select(LearningProfile).where(LearningProfile.user_id==uid))).scalars().first()
            p.pilot_code='test'; await db.commit()
    asyncio.run(join())
    assert c.get(base,headers=h).json()['status']=='ready'
    start=dict(snr_db=-3,headphone_check=True,volume_fixed=True)
    assert c.post(base+'/start',headers=h,json={**start,'headphone_check':False}).status_code==422
    run=c.post(base+'/start',headers=h,json=start).json(); sid=run['session_id']
    assert run['snr_db']==-3 and len(run['items'])==6
    assert all('text' not in it and 'condition' not in it for it in run['items'])
    again=c.post(base+'/start',headers=h,json={**start,'snr_db':10}).json()
    assert again['session_id']==sid and again['snr_db']==-3
    assert c.post(base+'/finish',headers=h,json=dict(session_id=sid)).status_code==409
    assert c.get('/api'+run['items'][0]['media'],headers=other).status_code==403
    # 같은 파일럿의 다른 참여자도 남의 회차에는 닿지 못한다.
    async def join_other():
        async with AsyncSessionLocal() as db:
            p=(await db.execute(select(LearningProfile).where(LearningProfile.user_id==other_id))).scalars().first()
            p.pilot_code='test'; await db.commit()
    asyncio.run(join_other())
    assert c.get('/api'+run['items'][0]['media'],headers=other).status_code==404
    assert c.get(base+'/noise/'+sid,headers=other).status_code==404
    assert c.post(base+'/answer',headers=other,json=dict(session_id=sid,item_id=run['items'][0]['id'],answer_text='x',plays=1,rt_ms=1)).status_code==404
    assert c.post(base+'/finish',headers=other,json=dict(session_id=sid)).status_code==404
    for it in run['items']:
        body=dict(session_id=sid,item_id=it['id'],answer_text='문장 '+it['id'],plays=1,rt_ms=10)
        assert c.post(base+'/answer',headers=h,json=body).json()=={'recorded':True}
        assert c.post(base+'/answer',headers=h,json={**body,'answer_text':'오답'}).status_code==200
    result=c.post(base+'/finish',headers=h,json=dict(session_id=sid)).json()
    assert result['n_answered']==6 and result['proportions']==dict(A=1,avatar=1,real=1)
    assert result['relative_index'] is None
    assert c.post(base+'/start',headers=h,json=start).status_code==409
    async def verify():
        async with AsyncSessionLocal() as db:
            rows=list((await db.execute(select(AvComparisonAnswer))).scalars())
            assert len(rows)==6 and all(r.matched==r.total for r in rows)
            from transfer_export import export_transfer
            exported=await export_transfer(db,uid)
            text=json.dumps(exported)
            assert len(exported['av_comparisons'])==1 and 'real.mp4' not in text and '문장' not in text
            assert 'answer_text' not in text and 'user_id' not in text
    asyncio.run(verify())
    (root/'real.mp4').unlink()
    assert c.get(base,headers=h).json()['status']=='waiting_for_material'
''')
