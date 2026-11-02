"""C8: 자료 없음, 동의·보류 검사, 상한 공유, 서버 채점·다른 계정 경계."""
from test_usage_events import _scenario

def test_probe_lifecycle():
    _scenario(r'''
import asyncio, json, os
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select
import main
from database import AsyncSessionLocal, RealFaceProbe
from pilot_data import user_data_models, purge
assert RealFaceProbe in user_data_models()
root = Path(os.environ['T_DB']).parent
os.environ['LIPLAB_REAL_FACE_MEDIA_DIR'] = str(root)
os.environ['LIPLAB_REAL_FACE_MANIFEST'] = str(root/'probe.json')
items = [dict(id=str(i),options=['가','나','다','라'],answer='가',media='video.mp4',talker='T1',consent=True,purpose='lesson_probe') for i in range(5)]
(root/'video.mp4').write_bytes(b'test-only-media')
def write(status='frozen'):
    (root/'probe.json').write_text(json.dumps(dict(version='test1',status=status,items=items)),encoding='utf-8')
write()
with TestClient(main.app) as c:
    def reg(name):
        r=c.post('/api/auth/register',json={'email':name+'@example.com','username':name,'password':'test-password-123','agree_terms':True,'age_confirmed':True})
        return {'Authorization':'Bearer '+r.json()['access_token']}, r.json()['user']['id']
    h,uid=reg('first'); other,_=reg('second')
    def issue(used=2):
        return c.post('/api/probes/real-face',headers=h,json=dict(lesson_id=str(uuid4()),lesson_len=12,used=used))
    os.environ.pop('LIPLAB_REAL_FACE_PROBES',None)
    assert issue().json()['items']==[]
    os.environ['LIPLAB_REAL_FACE_PROBES']='1'
    write('draft'); assert issue().json()['status']=='waiting_for_material'
    write(); items[0]['consent']=False; write(); assert issue().status_code==503
    items[0]['consent']=True; write()
    r=issue(); assert r.status_code==200,r.text
    rows=r.json()['items']; assert len(rows)==1
    it=rows[0]; assert 'answer' not in it and 'snapshot' not in it
    assert c.get('/api'+it['media'],headers=other).status_code==404
    assert c.get('/api'+it['media'],headers=h).content==b'test-only-media'
    path='/api/probes/real-face/'+it['id']+'/answer'
    assert c.post(path,headers=other,json=dict(chosen='가',rt_ms=10)).status_code==404
    assert c.post(path,headers=h,json=dict(chosen='없음',rt_ms=10)).status_code==422
    assert c.post(path,headers=h,json=dict(chosen='나',rt_ms=10)).json()=={'recorded':True}
    assert c.post(path,headers=h,json=dict(chosen='가',rt_ms=20)).status_code==200
    assert issue(used=3).json()['items']==[]
    async def verify():
        async with AsyncSessionLocal() as db:
            row=await db.get(RealFaceProbe,it['id'])
            assert row.correct is False and row.chosen=='나' and row.rt_ms==10
            from transfer_export import export_transfer
            exported=await export_transfer(db,uid)
            assert exported['real_face_probes'][0]['correct'] is False
            assert 'snapshot' not in json.dumps(exported) and 'video.mp4' not in json.dumps(exported)
            result=await purge(db,uid); await db.commit()
            assert result['real_face_probes']==1
    asyncio.run(verify())
''')
