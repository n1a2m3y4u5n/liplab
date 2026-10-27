"""개인정보를 최소화한 서비스 이용 기록과 관리자 조회."""
import csv
import io
import json
import os
import re
import time
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from auth import get_current_user
from database import UsageEvent, get_db

router = APIRouter()
_hits = {}
EVENTS = set('route track_enter stage_enter lesson_start lesson_complete lesson_abort bundle_start bundle_complete bundle_abort tab_open volume font_size info_open guide_open recording_start recording_failure webcam_start webcam_failure frontend_error feature_open lesson_interrupt bundle_interrupt control'.split())
ROUTES = {'/tasks', '/signup', '/learn/listening', '/learn/placement', '/analysis/hub', '/learn/scenario', '/practice/hub', '/onboarding', '/learn/viseme', '/analysis/scores', '/', '/pilot/battery', '/lab/cue-video', '/review/saved', '/learn/conversation-multi', '/review/today', '/learn/sign', '/about', '/terms', '/review/hub', '/privacy', '/review/scheduled', '/analysis/overview', '/admin/content-review', '/pronounce', '/listen/review', '/sign', '/dev-viseme', '/learn/speaking', '/analysis', '/listen/classroom', '/conversation', '/analysis/visemes', '/analysis/eval', '/learn/nonsense', '/login', '/analysis/listening', '/learn/endless', '/learn/word', '/practice', '/review/speaking/session', '/review', '/listen/today', '/analysis/history', '/review/speaking', '/analysis/activity', '/profile', '/learn/closure', '/dashboard', '/learn/path', '/review/mistakes'}
PROPS = {'duration_ms', 'stage', 'lesson_id', 'action', 'value', 'error_kind', 'message'}


def enabled():
    return os.getenv('LIPLAB_USAGE_LOG', '0').lower() in {'1', 'true'}


def identifier(value, limit=64):
    return value if isinstance(value, str) and len(value) <= limit and re.fullmatch(r'[a-zA-Z0-9_:/.-]*', value) else None


def clean_props(props):
    if not isinstance(props, dict):
        raise HTTPException(422, 'props must be an object')
    if len(json.dumps(props, ensure_ascii=False).encode()) > 2048:
        raise HTTPException(413, 'props too large')
    out = {}
    for key, value in props.items():
        if key not in PROPS:
            continue
        if key in {'duration_ms', 'stage', 'value'} and isinstance(value, (int, float)) and not isinstance(value, bool):
            if 0 <= value <= 86400000:
                out[key] = value
        elif key == 'message':
            # 예외 원문에는 입력·주소가 섞일 수 있어 알려진 오류 종류만 남긴다.
            if value in {'Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError', 'NetworkError', 'NotAllowedError', 'NotFoundError', 'AbortError', 'UnhandledRejection'}:
                out[key] = value
        elif key in {'lesson_id', 'action', 'error_kind', 'stage'}:
            v = identifier(value)
            if v is not None:
                out[key] = v
    return out


def ua_summary(request):
    ua = request.headers.get('user-agent', '')
    browser = next((name for marker, name in [('Edg/', 'Edge'), ('Firefox/', 'Firefox'), ('Chrome/', 'Chrome'), ('Safari/', 'Safari')] if marker in ua), 'Other')
    system = next((name for marker, name in [('Android', 'Android'), ('iPhone', 'iOS'), ('iPad', 'iOS'), ('Windows', 'Windows'), ('Macintosh', 'macOS'), ('Linux', 'Linux')] if marker in ua), 'Other')
    return {'browser': browser, 'os': system, 'mobile': any(x in ua for x in ['Mobile', 'Android', 'iPhone', 'iPad'])}


async def record_auth(db, uid, event, request):
    if not enabled():
        return
    try:
        db.add(UsageEvent(user_id=uid, event=event, ts=datetime.utcnow(), ua=ua_summary(request)))
        await db.commit()
    except Exception:
        # 이용 기록 실패가 로그인을 막지 않는다.
        await db.rollback()


@router.get('/api/events/status')
async def events_status():
    return {'enabled': enabled()}


@router.post('/api/events')
async def collect(request: Request, db=Depends(get_db)):
    # 스트림에서 먼저 크기를 제한해 큰 JSON을 메모리에 올리지 않는다.
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 32768:
            raise HTTPException(413, 'request too large')
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, 'invalid JSON')
    bearer = request.headers.get('authorization', '')
    token = bearer[7:] if bearer.lower().startswith('bearer ') else body.get('token', '')
    if not isinstance(token, str) or not token:
        raise HTTPException(401, 'authentication required')
    user = await get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=token), db)
    if not enabled():
        return {'enabled': False, 'accepted': 0}
    events = body.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 50:
        raise HTTPException(422, '1 to 50 events required')
    now = time.monotonic()
    for uid in list(_hits):
        if not _hits[uid] or now - _hits[uid][-1] >= 60:
            del _hits[uid]
    hits = _hits.setdefault(user.id, deque())
    while hits and now - hits[0] >= 60:
        hits.popleft()
    if len(hits) + len(events) > 300:
        raise HTTPException(429, 'event rate exceeded', headers={'Retry-After': '60'})
    rows = []
    for item in events:
        if not isinstance(item, dict) or not isinstance(item.get('event'), str) or item.get('event') not in EVENTS:
            raise HTTPException(422, 'unknown event')
        route = identifier(item.get('route'), 160)
        # 쿼리·이메일·자유 입력 URL은 저장하지 않는다.
        if route not in ROUTES:
            route = '/listen/practice/:mode' if route and re.fullmatch(r'/listen/practice/[a-z_-]{1,24}', route) else None
        ts = datetime.utcnow()
        if item.get('ts'):
            try:
                from datetime import timezone
                candidate = datetime.fromisoformat(item['ts'].replace('Z', '+00:00'))
                if candidate.tzinfo:
                    candidate = candidate.astimezone(timezone.utc).replace(tzinfo=None)
                if abs((ts - candidate).total_seconds()) <= 86400:
                    ts = candidate
            except (ValueError, TypeError, AttributeError):
                pass
        rows.append(UsageEvent(user_id=user.id, ts=ts, event=item['event'], route=route,
            anon_session_id=identifier(item.get('anon_session_id')), track=item.get('track') if item.get('track') in {'read', 'speak', 'listen', 'test', 'perception', 'language'} else None,
            props=clean_props(item.get('props', {})), app_version=identifier(item.get('app_version'), 40), ua=ua_summary(request)))
    hits.extend([now] * len(rows))
    db.add_all(rows)
    await db.commit()
    return {'enabled': True, 'accepted': len(rows)}


@router.post('/api/auth/logout')
async def logout(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    await record_auth(db, user.id, 'logout', request)
    return {'ok': True}


@router.get('/api/admin/usage')
async def admin_usage(start: date = None, end: date = None, user_id: int = None, format: str = 'json',
                      user=Depends(get_current_user), db=Depends(get_db)):
    from main import _admin_email_gate
    from analytics import sessions, session_minutes, Event
    from pilot_data import user_data_models
    _admin_email_gate(user)
    end = end or datetime.utcnow().date()
    start = start or end - timedelta(days=6)
    if start > end or (end - start).days > 31 or format not in {'json', 'csv'}:
        raise HTTPException(422, 'date range maximum 32 days; format json or csv')
    lo, hi = datetime.combine(start, datetime.min.time()), datetime.combine(end + timedelta(days=1), datetime.min.time())
    q = select(UsageEvent).where(UsageEvent.ts >= lo, UsageEvent.ts < hi)
    if user_id is not None:
        q = q.where(UsageEvent.user_id == user_id)
    rows = list((await db.execute(q.order_by(UsageEvent.ts, UsageEvent.id).limit(10001))).scalars())
    if len(rows) > 10000:
        raise HTTPException(413, 'narrow date range or select a user')
    timeline = [dict(id=r.id, user_id=r.user_id, ts=r.ts.isoformat()+'Z', event=r.event, route=r.route,
                     track=r.track, props=r.props, ua=r.ua, app_version=r.app_version, anon_session_id=r.anon_session_id) for r in rows]
    if format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['user_id', 'ts', 'event', 'route', 'track', 'props', 'ua'])
        for r in timeline:
            writer.writerow([r['user_id'], r['ts'], r['event'], r['route'], r['track'], json.dumps(r['props'], ensure_ascii=False), json.dumps(r['ua'])])
        return Response('\ufeff'+output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="usage.csv"', 'Cache-Control': 'no-store'})
    counts = Counter((r.ts.date().isoformat(), r.event) for r in rows)
    # user_id 모델의 시각만 합친다. 답·입력·기록 원문은 조회하지 않는다.
    activity = defaultdict(list)
    for model in user_data_models():
        if model is UsageEvent or not hasattr(model, 'created_at') or not any(part in model.__tablename__ for part in ('attempt', 'log', 'result', 'progress', 'probe', 'effort', 'test_session', 'response')):
            continue
        query = select(model.user_id, model.created_at).where(model.created_at >= lo, model.created_at < hi)
        if user_id is not None:
            query = query.where(model.user_id == user_id)
        for uid, ts in (await db.execute(query)).all():
            activity[(uid, ts.date().isoformat())].append(Event(ts, 'learning', None, model.__tablename__))
    for r in rows:
        activity[(r.user_id, r.ts.date().isoformat())].append(Event(r.ts, r.track or 'usage', None, r.event))
    daily = []
    for (uid, day), events in sorted(activity.items()):
        ordered = sorted(events, key=lambda e: e.ts)
        daily.append({'user_id': uid, 'day': day, 'first_at': ordered[0].ts.isoformat()+'Z',
                      'last_at': ordered[-1].ts.isoformat()+'Z', 'features': sorted({e.kind for e in events}),
                      'connection_times': [r.ts.isoformat()+'Z' for r in rows if r.user_id == uid and r.ts.date().isoformat() == day and r.event in {'register', 'login'}],
                      'recorded_duration_ms': sum((r.props or {}).get('duration_ms', 0) for r in rows if r.user_id == uid and r.ts.date().isoformat() == day),
                      'estimated_minutes': round(sum(session_minutes(s) for s in sessions(events)), 2)})
    return {'timezone': 'UTC', 'aggregate': [{'day': d, 'event': e, 'count': n} for (d,e),n in sorted(counts.items())],
            'timeline': timeline, 'daily': daily, 'duration_method': '30 minute session gap; last activity plus 1 minute estimate'}
