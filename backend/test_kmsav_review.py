"""P18 비활성·권한·저장·수정·입력 검증."""
from test_usage_events import _scenario

def test_review_lifecycle():
    _scenario(r'''
import os
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    def reg(name):
        r = c.post('/api/auth/register', json={'email':name+'@example.com','username':name,'password':'test-password-123','agree_terms':True,'age_confirmed':True})
        assert r.status_code == 201, r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    admin, user = reg('admin'), reg('user')
    os.environ.pop('LIPLAB_KMSAV_REVIEW', None)
    assert c.get('/api/admin/kmsav', headers=admin).status_code == 404
    os.environ['LIPLAB_KMSAV_REVIEW'] = '1'
    assert c.get('/api/admin/kmsav').status_code == 401
    assert c.get('/api/admin/kmsav', headers=user).status_code == 403
    data = dict(video_id='abcdefghijk',source='https://www.youtube.com/watch?v=abcdefghijk',license_label='CC BY',evidence='영상 페이지 표기 확인',decision='usable')
    assert c.put('/api/admin/kmsav', headers=admin, json=data).status_code == 200
    assert c.put('/api/admin/kmsav', headers=admin, json={**data,'source':'https://evil.example/'}).status_code == 422
    assert c.put('/api/admin/kmsav', headers=admin, json={**data,'license_label':'standard'}).status_code == 422
    assert c.put('/api/admin/kmsav', headers=admin, json={**data,'decision':'rejected'}).status_code == 200
    rows = c.get('/api/admin/kmsav', headers=admin).json()['records']
    assert len(rows) == 1 and rows[0]['decision'] == 'rejected'
    assert 'user_id' not in rows[0]
''')
