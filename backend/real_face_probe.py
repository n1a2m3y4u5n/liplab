"""C8: 촬영·동의 확인한 전용 문항만 레슨에 섞는다. P3 검사 폼을 학습에 노출하지 않는다."""
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4, UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from auth import get_current_user
from database import RealFaceProbe, get_db
from mastery_probe import lesson_quota

router = APIRouter()
DEFAULT = Path(__file__).parent / 'data/pilot/real_face_probes.json'

def enabled():
    return os.getenv('LIPLAB_REAL_FACE_PROBES', '0') == '1'

def media_path(rel):
    root = Path(os.getenv('LIPLAB_REAL_FACE_MEDIA_DIR') or DEFAULT.parent / 'probe_media').resolve()
    path = (root / rel).resolve()
    return path if path.is_relative_to(root) and path.is_file() and path.stat().st_size else None

def manifest():
    try:
        data = json.loads(Path(os.getenv('LIPLAB_REAL_FACE_MANIFEST') or DEFAULT).read_text(encoding='utf-8'))
        if data['status'] != 'frozen':
            return data.get('version', 'draft'), []
        items = data['items']
        ids = set()
        for it in items:
            options = it['options']
            if (not isinstance(it['id'], str) or not 1 <= len(it['id']) <= 40 or it['id'] in ids
                or it.get('consent') is not True or it.get('purpose') != 'lesson_probe'
                or len(options) != 4 or len(set(options)) != 4 or it['answer'] not in options
                or any(not isinstance(o, str) or not 1 <= len(o) <= 300 for o in options)
                or not isinstance(it['media'], str) or not it.get('talker')):
                raise ValueError('invalid item')
            ids.add(it['id'])
        if not isinstance(data['version'], str) or not 1 <= len(data['version']) <= 64:
            raise ValueError('invalid version')
        return data['version'], [it for it in items if media_path(it['media'])]
    except (KeyError, TypeError, ValueError, OSError):
        raise HTTPException(503, '문항 목록을 확인해 주세요.')

class Issue(BaseModel):
    lesson_id: UUID
    lesson_len: int = Field(ge=0, le=40)
    used: int = Field(0, ge=0, le=40)

def public(row):
    return {'id': row.id, 'kind': 'real_face', 'options': [{'value': x, 'label': x} for x in row.snapshot['options']],
            'media': '/probes/real-face/media/' + row.id}

@router.post('/api/probes/real-face')
async def issue(data: Issue, user=Depends(get_current_user), db=Depends(get_db)):
    if not enabled():
        return {'items': [], 'status': 'disabled'}
    lid = str(data.lesson_id)
    existing = list((await db.execute(select(RealFaceProbe).where(
        RealFaceProbe.user_id == user.id, RealFaceProbe.lesson_id == lid))).scalars())
    if existing:
        return {'items': [public(r) for r in existing if r.answered_at is None], 'status': 'ready'}
    version, items = manifest()
    seen = set((await db.execute(select(RealFaceProbe.item_id).where(RealFaceProbe.user_id == user.id))).scalars())
    items = [it for it in items if it['id'] not in seen][:lesson_quota(data.lesson_len, data.used)]
    rows = []
    for it in items:
        row = RealFaceProbe(id=str(uuid4()), user_id=user.id, lesson_id=lid, item_id=it['id'], version=version, snapshot=it)
        db.add(row); rows.append(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = list((await db.execute(select(RealFaceProbe).where(
            RealFaceProbe.user_id == user.id, RealFaceProbe.lesson_id == lid))).scalars())
        return {'items': [public(r) for r in existing if r.answered_at is None], 'status': 'ready'}
    return {'items': [public(r) for r in rows], 'status': 'ready' if rows else 'waiting_for_material'}

async def owned(iid, user, db):
    if not enabled():
        raise HTTPException(404)
    row = await db.get(RealFaceProbe, iid)
    if row is None or row.user_id != user.id:
        raise HTTPException(404)
    return row

@router.get('/api/probes/real-face/media/{iid}')
async def media(iid: str, user=Depends(get_current_user), db=Depends(get_db)):
    row = await owned(iid, user, db)
    path = media_path(row.snapshot['media'])
    if not path:
        raise HTTPException(404, '자료 대기')
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'})

class Answer(BaseModel):
    chosen: str = Field(min_length=1, max_length=300)
    rt_ms: int = Field(ge=0, le=3600000)

@router.post('/api/probes/real-face/{iid}/answer')
async def answer(iid: str, data: Answer, user=Depends(get_current_user), db=Depends(get_db)):
    row = await owned(iid, user, db)
    if data.chosen not in row.snapshot['options']:
        raise HTTPException(422, '보기 중에서 골라 주세요.')
    # 조건부 갱신으로 재전송·동시 답변도 처음 답만 남긴다. 정답은 반환하지 않는다.
    await db.execute(update(RealFaceProbe).where(RealFaceProbe.id == iid, RealFaceProbe.answered_at.is_(None)).values(
        chosen=data.chosen, correct=data.chosen == row.snapshot['answer'], rt_ms=data.rt_ms, answered_at=datetime.utcnow()))
    await db.commit()
    return {'recorded': True}
