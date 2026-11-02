"""P17: A·AV 아바타·AV 실제 얼굴을 같은 SNR에서 비교. 원자료 없이는 시행하지 않는다."""
import json
import math
import os
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from auth import get_current_user
from database import AvComparison, AvComparisonAnswer, get_db
from pilot_battery import word_hits
from real_face_probe import media_path

router = APIRouter()
DEFAULT = Path(__file__).parent / 'data/pilot/av_comparison.json'
CONDITIONS = ('A', 'avatar', 'real')

async def gate(user, db):
    if os.getenv('LIPLAB_AV_COMPARISON', '0') != '1':
        raise HTTPException(404)
    from main import _battery_gate
    await _battery_gate(user, db)

def manifest():
    try:
        m = json.loads(Path(os.getenv('LIPLAB_AV_COMPARISON_MANIFEST') or DEFAULT).read_text(encoding='utf-8'))
        if m['status'] != 'frozen' or not m['items']:
            return None
        if not isinstance(m['version'], str) or not m['version'] or len(m['version']) > 64:
            raise ValueError('version')
        ids, texts = set(), set()
        for it in m['items']:
            if (not isinstance(it['id'], str) or not 1 <= len(it['id']) <= 40 or it['id'] in ids
                or not isinstance(it['text'], str) or not 1 <= len(it['text']) <= 300 or it['text'] in texts
                or it.get('consent') is not True or not it.get('talker')
                or not isinstance(it.get('speech_rms_dbfs'), (int,float))
                or not math.isfinite(it['speech_rms_dbfs']) or not -100 < it['speech_rms_dbfs'] < 0):
                raise ValueError('item')
            ids.add(it['id']); texts.add(it['text'])
            if not media_path(it['real_media']) or not media_path(it['avatar_media']):
                return None
        if len(ids) % 3 or not media_path(m['noise']):
            return None
        return m
    except (OSError, KeyError, ValueError, TypeError):
        raise HTTPException(503, '비교 목록을 확인해 주세요.')

def gains(rows):
    """낱말 정답수 합/전체수 합. 실제 얼굴 이득 ≤ 0이면 상대 지수를 내지 않는다."""
    proportions = {}
    for condition in CONDITIONS:
        group = [r for r in rows if r.condition == condition]
        total = sum(r.total for r in group)
        proportions[condition] = sum(r.matched for r in group) / total if total else None
    a, avatar, real = [proportions[k] for k in CONDITIONS]
    ready = all(x is not None for x in (a, avatar, real))
    return {'proportions': proportions,
            'avatar_gain': avatar - a if ready else None,
            'real_gain': real - a if ready else None,
            'relative_index': (avatar - a) / (real - a) if ready and real > a else None}

class Start(BaseModel):
    snr_db: float = Field(ge=-20, le=25, allow_inf_nan=False)
    headphone_check: StrictBool
    volume_fixed: StrictBool

async def owned(sid, user, db):
    await gate(user, db)
    row = await db.get(AvComparison, sid)
    if row is None or row.user_id != user.id:
        raise HTTPException(404)
    return row

async def payload(row, db):
    answered = set((await db.execute(select(AvComparisonAnswer.item_id).where(AvComparisonAnswer.session_id == row.id))).scalars())
    items = [{'id': it['id'], 'ready': True, 'answered': it['id'] in answered,
              'modality': 'A' if it['condition'] == 'A' else 'AV',
              'speech_rms_dbfs': it['speech_rms_dbfs'],
              'media': f'/pilot/av-comparison/media/{row.id}/{it["id"]}'} for it in row.snapshot['items']]
    return {'session_id': row.id, 'label': 'P17', 'layer': 'av', 'form': row.snapshot['version'],
            'title': '소음 속 문장 비교', 'response': 'typed', 'playback': {'max_plays': 2, 'speed': 1},
            'items': items, 'snr_db': row.snr_db, 'noise': f'/pilot/av-comparison/noise/{row.id}',
            'missing': {}, 'headphone_check': row.headphone_check, 'volume_fixed': row.volume_fixed}

@router.get('/api/pilot/av-comparison')
async def status(user=Depends(get_current_user), db=Depends(get_db)):
    await gate(user, db)
    rows = list((await db.execute(select(AvComparison).where(AvComparison.user_id == user.id).order_by(AvComparison.created_at.desc()))).scalars())
    reports = []
    for row in rows:
        answers = list((await db.execute(select(AvComparisonAnswer).where(AvComparisonAnswer.session_id == row.id))).scalars())
        reports.append({'id': row.id, 'completed': row.completed, 'snr_db': row.snr_db, 'version': row.snapshot['version'],
                        'n_answered': len(answers), **(gains(answers) if row.completed else {})})
    return {'status': 'ready' if manifest() else 'waiting_for_material', 'sessions': reports}

@router.post('/api/pilot/av-comparison/start')
async def start(data: Start, user=Depends(get_current_user), db=Depends(get_db)):
    await gate(user, db)
    if not data.headphone_check or not data.volume_fixed:
        raise HTTPException(422, '헤드폰과 고정 볼륨을 확인해 주세요.')
    previous = (await db.execute(select(AvComparison).where(AvComparison.user_id == user.id, AvComparison.completed.is_(False)))).scalars().first()
    if previous:
        return await payload(previous, db)
    # 미완료 회차를 이어 쓰며, 완료 후 같은 문장으로 다시 검사하지 않는다.
    if (await db.execute(select(AvComparison.id).where(AvComparison.user_id == user.id))).first():
        raise HTTPException(409, '이미 비교를 마쳤어요.')
    m = manifest()
    if not m:
        raise HTTPException(409, '자료 대기')
    items = [{**it, 'condition': CONDITIONS[(i + user.id) % 3]} for i, it in enumerate(m['items'])]
    row = AvComparison(id=str(uuid4()), user_id=user.id, snapshot={**m, 'items': items}, snr_db=data.snr_db,
                       headphone_check=True, volume_fixed=True)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        row = (await db.execute(select(AvComparison).where(AvComparison.user_id == user.id))).scalars().one()
        if row.completed:
            raise HTTPException(409, '이미 비교를 마쳤어요.')
    return await payload(row, db)

@router.get('/api/pilot/av-comparison/media/{sid}/{iid}')
async def media(sid: str, iid: str, user=Depends(get_current_user), db=Depends(get_db)):
    row = await owned(sid, user, db)
    it = next((it for it in row.snapshot['items'] if it['id'] == iid), None)
    path = media_path(it['avatar_media'] if it and it['condition'] == 'avatar' else it['real_media']) if it else None
    if not path:
        raise HTTPException(404, '자료 대기')
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'})

@router.get('/api/pilot/av-comparison/noise/{sid}')
async def noise(sid: str, user=Depends(get_current_user), db=Depends(get_db)):
    row = await owned(sid, user, db)
    path = media_path(row.snapshot['noise'])
    if not path:
        raise HTTPException(404)
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'})

class Answer(BaseModel):
    session_id: str
    item_id: str
    answer_text: str = Field(max_length=300)
    plays: int = Field(ge=1, le=2)
    rt_ms: int = Field(ge=0, le=3600000)

@router.post('/api/pilot/av-comparison/answer')
async def answer(data: Answer, user=Depends(get_current_user), db=Depends(get_db)):
    row = await owned(data.session_id, user, db)
    if row.completed:
        raise HTTPException(409)
    it = next((it for it in row.snapshot['items'] if it['id'] == data.item_id), None)
    if not it:
        raise HTTPException(404)
    matched, total = word_hits(it['text'], data.answer_text)
    db.add(AvComparisonAnswer(user_id=user.id, session_id=row.id, item_id=it['id'], condition=it['condition'],
           answer_text=data.answer_text, matched=matched, total=total, plays=data.plays, rt_ms=data.rt_ms))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # 처음 답을 유지한다.
    return {'recorded': True}

class Finish(BaseModel):
    session_id: str

@router.post('/api/pilot/av-comparison/finish')
async def finish(data: Finish, user=Depends(get_current_user), db=Depends(get_db)):
    row = await owned(data.session_id, user, db)
    answers = list((await db.execute(select(AvComparisonAnswer).where(AvComparisonAnswer.session_id == row.id))).scalars())
    if len(answers) != len(row.snapshot['items']):
        raise HTTPException(409, '아직 답하지 않은 문항이 있어요.')
    row.completed = True
    await db.commit()
    return {'n_answered': len(answers), 'n_ready': len(row.snapshot['items']), **gains(answers)}
