"""앱 내 신고·긍정판 SUS. 기존 이용 기록의 보관·삭제를 재사용한다."""
import csv
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select
from auth import get_current_user
from database import UsageEvent, FeedbackDaily, get_db
from sqlalchemy.exc import IntegrityError
from usage_events import enabled, ua_summary, random_id, account_flags, limit_events, ROUTES

router = APIRouter()
KINDS = ('feedback_report', 'sus_prompt', 'sus_response', 'sus_skip')

def today_start():
    now = datetime.now(timezone(timedelta(hours=9)))
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)

async def prompted(db, uid):
    return (await db.execute(select(UsageEvent.id).where(UsageEvent.user_id == uid,
        UsageEvent.event == 'sus_prompt', UsageEvent.ts >= today_start()).limit(1))).first() is not None

class Feedback(BaseModel):
    kind: Literal['report', 'prompt', 'sus', 'skip']
    route: str = Field('', max_length=160)
    text: str = Field('', max_length=500)
    answers: list[StrictInt] = Field(default_factory=list, max_length=10)
    width: int = Field(0, ge=0, le=20000)
    height: int = Field(0, ge=0, le=20000)

def sus_score(answers):
    if len(answers) != 10 or any(type(v) is not int or not 1 <= v <= 5 for v in answers):
        raise HTTPException(422, 'ten ratings from 1 to 5 required')
    return sum(v - 1 for v in answers) * 2.5

@router.post('/api/feedback')
async def submit(data: Feedback, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    if not enabled():
        return {'enabled': False, 'accepted': False}
    limit_events([(('feedback', user.id), 20)], 1)
    if data.kind == 'report' and not data.text.strip():
        raise HTTPException(422, 'report text required')
    props = {'width': data.width, 'height': data.height}
    if data.kind == 'prompt':
        if await prompted(db, user.id):
            return {'enabled': True, 'accepted': False}
        event = 'sus_prompt'
    elif data.kind in {'sus', 'skip'}:
        if not await prompted(db, user.id):
            raise HTTPException(409, 'claim daily prompt first')
        previous = (await db.execute(select(UsageEvent.id).where(UsageEvent.user_id == user.id,
            UsageEvent.ts >= today_start(), UsageEvent.event.in_(['sus_response', 'sus_skip'])).limit(1))).first()
        if previous:
            return {'enabled': True, 'accepted': False}
        event = 'sus_response' if data.kind == 'sus' else 'sus_skip'
        if data.kind == 'sus':
            props.update(answers=data.answers, score=sus_score(data.answers), version='positive-ko-draft-2026-10-06')
    else:
        event = 'feedback_report'
        props['text'] = data.text.strip()
    if data.kind != 'report':
        db.add(FeedbackDaily(user_id=user.id, day=(today_start() + timedelta(hours=9)).date().isoformat(),
            kind='prompt' if data.kind == 'prompt' else 'response'))
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            return {'enabled': True, 'accepted': False}
    route = data.route if data.route in ROUTES else None
    if route is None and re.fullmatch(r'/listen/practice/[a-z_-]{1,24}', data.route):
        route = '/listen/practice/:mode'
    demo, test = account_flags(user)
    db.add(UsageEvent(user_id=user.id, device_id=random_id(request.headers.get('x-usage-device-id')),
        anon_session_id=random_id(request.headers.get('x-usage-session-id')), event=event,
        route=route, ua=ua_summary(request), props=props,
        is_demo=demo, is_test=test))
    await db.commit()
    return {'enabled': True, 'accepted': True}

@router.get('/api/admin/feedback')
async def overview(start: date = None, end: date = None, format: Literal['json', 'csv'] = 'json', include_tests: bool = False,
                   user=Depends(get_current_user), db=Depends(get_db)):
    from main import _admin_email_gate
    _admin_email_gate(user)
    end = end or datetime.utcnow().date()
    start = start or end - timedelta(days=6)
    if start > end or (end - start).days > 31:
        raise HTTPException(422, 'date range maximum 32 days')
    lo = datetime.combine(start, datetime.min.time())
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time())
    query = select(UsageEvent).where(UsageEvent.event.in_(KINDS), UsageEvent.ts >= lo, UsageEvent.ts < hi)
    if not include_tests:
        query = query.where(UsageEvent.is_test.is_(False))
    rows = list((await db.execute(query.order_by(UsageEvent.ts.desc(), UsageEvent.id.desc()).limit(1001))).scalars())
    if len(rows) > 1000:
        raise HTTPException(413, 'narrow the date range')
    records = [dict(id=r.id, user_id=r.user_id, device_id=r.device_id, session_id=r.anon_session_id,
        ts=r.ts.isoformat()+'Z', event=r.event, route=r.route, ua=r.ua, props=r.props,
        is_demo=r.is_demo, is_test=r.is_test) for r in rows if include_tests or not r.is_test]
    if format == 'json':
        return {'records': records}
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    keys = ['id', 'user_id', 'device_id', 'session_id', 'ts', 'event', 'route', 'ua', 'props', 'is_demo', 'is_test']
    writer.writerow(keys)
    for record in records:
        writer.writerow([json.dumps(record[k], ensure_ascii=False) if isinstance(record[k], dict) else record[k] for k in keys])
    return Response('\ufeff'+output.getvalue(), media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="feedback.csv"', 'Cache-Control': 'no-store'})
