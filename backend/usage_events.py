"""개인정보를 최소화한 서비스 이용 기록과 관리자 조회."""
import hashlib
import hmac
import secrets
from uuid import UUID
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
from database import UsageEvent, User, get_db

router = APIRouter()
_hits = {}
_IP_HASH_KEY = secrets.token_bytes(32)
PUBLIC_EVENTS = {"landing_view": "/", "login_view": "/login", "signup_view": "/signup", "demo_start": "/login"}
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


def random_id(value):
    try:
        parsed = UUID(value)
        return str(parsed) if parsed.version == 4 else None
    except (ValueError, TypeError, AttributeError):
        return None


def account_flags(user):
    email = (getattr(user, 'email', '') or '').lower()
    name = (getattr(user, 'username', '') or '').lower()
    explicit = {e.strip().lower() for e in os.getenv('LIPLAB_USAGE_TEST_EMAILS', '').split(',') if e.strip()}
    demo = email == 'demo@liplab.app'
    test = email.endswith('@example.com') or email in explicit or email.startswith(('smoke', 'deploy-smoke', 'predeploy-', 'rehearsal-')) or name.startswith(('smoke', 'deploy-smoke'))
    return demo, test


def audience(demo, test, uid):
    return 'test' if test else 'demo' if demo else 'anonymous' if uid is None else 'real'


def limit_events(keys, count):
    now = time.monotonic()
    for key in list(_hits):
        hits = _hits[key]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if not hits:
            del _hits[key]
    if len(_hits) + len(keys) > 10000:
        raise HTTPException(429, 'rate limiter full', headers={'Retry-After': '60'})
    for key, maximum in keys:
        if len(_hits.get(key, ())) + count > maximum:
            raise HTTPException(429, 'event rate exceeded', headers={'Retry-After': '60'})
    for key, maximum in keys:
        _hits.setdefault(key, deque()).extend([now] * count)


async def record_auth(db, uid, event, request):
    if not enabled():
        return
    try:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        demo, test = account_flags(user)
        db.add(UsageEvent(user_id=uid, event=event, ts=datetime.utcnow(), ua=ua_summary(request),
            device_id=random_id(request.headers.get('x-usage-device-id')),
            anon_session_id=random_id(request.headers.get('x-usage-session-id')), is_demo=demo, is_test=test))
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
    user = None
    if token:
        if not isinstance(token, str):
            raise HTTPException(401, 'invalid token')
        user = await get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=token), db)
    if not enabled():
        return {'enabled': False, 'accepted': 0}
    if user is None:
        from ratelimit import _client_key
        ip_hash = hmac.new(_IP_HASH_KEY, _client_key(request).encode(), hashlib.sha256).hexdigest()
        limit_events([(('ip_request', ip_hash), 30)], 1)
    events = body.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= (50 if user else 10):
        raise HTTPException(422, 'invalid batch size')
    demo, test = account_flags(user)
    keys = [(('user', user.id), 300)] if user else []
    if user is None:
        devices = {random_id(item.get('device_id')) for item in events if isinstance(item, dict)}
        if len(devices) != 1 or None in devices:
            raise HTTPException(422, 'one random device ID required')
        keys = [(('device', next(iter(devices))), 30), (('ip', ip_hash), 60)]
    rows = []
    for item in events:
        if not isinstance(item, dict) or not isinstance(item.get('event'), str) or item.get('event') not in EVENTS | PUBLIC_EVENTS.keys():
            raise HTTPException(422, 'unknown event')
        if user is None and item['event'] not in PUBLIC_EVENTS:
            raise HTTPException(401, 'authentication required for event')
        device = random_id(item.get('device_id'))
        session = random_id(item.get('anon_session_id'))
        if user is None and (not device or not session):
            raise HTTPException(422, 'random device and session IDs required')
        route = identifier(item.get('route'), 160)
        if user is None:
            route = PUBLIC_EVENTS[item['event']]

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
        cleaned = clean_props(item.get('props', {}))
        rows.append(UsageEvent(user_id=user.id if user else None, device_id=device, is_demo=demo, is_test=test, ts=ts, event=item['event'], route=route,
            anon_session_id=session, track=item.get('track') if item.get('track') in {'read', 'speak', 'listen', 'test', 'perception', 'language'} else None,
            props=cleaned if user else {}, app_version=identifier(item.get('app_version'), 40), ua=ua_summary(request)))
    limit_events(keys, len(rows))
    db.add_all(rows)
    await db.commit()
    return {'enabled': True, 'accepted': len(rows)}


@router.post('/api/auth/logout')
async def logout(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    await record_auth(db, user.id, 'logout', request)
    return {'ok': True}


@router.get('/api/admin/usage')
async def admin_usage(start: date = None, end: date = None, user_id: int = None, device_id: str = None,
                      group_by: str = 'user', include_tests: bool = False, format: str = 'json',
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
    if group_by not in {'user', 'device'} or (device_id is not None and not random_id(device_id)):
        raise HTTPException(422, 'invalid group or device ID')
    users = {u.id: u for u in (await db.execute(select(User))).scalars()}
    q = select(UsageEvent).where(UsageEvent.ts >= lo, UsageEvent.ts < hi)
    if user_id is not None:
        q = q.where(UsageEvent.user_id == user_id)
    if device_id is not None:
        q = q.where(UsageEvent.device_id == device_id)
    rows = list((await db.execute(q.order_by(UsageEvent.ts, UsageEvent.id).limit(10001))).scalars())
    if len(rows) > 10000:
        raise HTTPException(413, 'narrow date range or select a user')
    flags = {uid: account_flags(u) for uid, u in users.items()}
    def row_flags(r):
        current = flags.get(r.user_id, (False, False))
        return bool(r.is_demo or current[0]), bool(r.is_test or current[1])
    test_rows = [r for r in rows if row_flags(r)[1]]
    if not include_tests:
        rows = [r for r in rows if not row_flags(r)[1]]
    timeline = []
    for r in rows:
        demo, test = row_flags(r)
        timeline.append(dict(id=r.id, user_id=r.user_id, device_id=r.device_id, is_demo=demo, is_test=test,
            audience=audience(demo, test, r.user_id), ts=r.ts.isoformat()+'Z', event=r.event, route=r.route,
            track=r.track, props=r.props, ua=r.ua, app_version=r.app_version, anon_session_id=r.anon_session_id))
    if format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['user_id', 'device_id', 'anon_session_id', 'is_demo', 'is_test', 'audience', 'ts', 'event', 'route', 'track', 'props', 'ua'])
        for r in timeline:
            writer.writerow([r['user_id'], r['device_id'], r['anon_session_id'], r['is_demo'], r['is_test'], r['audience'], r['ts'], r['event'], r['route'], r['track'], json.dumps(r['props'], ensure_ascii=False), json.dumps(r['ua'])])
        return Response('\ufeff'+output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="usage.csv"', 'Cache-Control': 'no-store'})
    counts = Counter((r['ts'][:10], r['event'], r['audience']) for r in timeline)
    # user_id 모델의 시각만 합친다. 답·입력·기록 원문은 조회하지 않는다.
    activity = defaultdict(list)
    for model in user_data_models():
        if device_id is not None or group_by == 'device' or model is UsageEvent or not hasattr(model, 'created_at') or not any(part in model.__tablename__ for part in ('attempt', 'log', 'result', 'progress', 'probe', 'effort', 'test_session', 'response')):
            continue
        query = select(model.user_id, model.created_at).where(model.created_at >= lo, model.created_at < hi)
        if user_id is not None:
            query = query.where(model.user_id == user_id)
        for uid, ts in (await db.execute(query)).all():
            if not include_tests and flags.get(uid, (False, False))[1]:
                continue
            activity[(uid, ts.date().isoformat())].append(Event(ts, 'learning', None, model.__tablename__))
    for r in rows:
        activity[(r.user_id, r.ts.date().isoformat())].append(Event(r.ts, r.track or 'usage', None, r.event))
    daily = []
    for (uid, day), events in sorted(activity.items(), key=lambda pair: (str(pair[0][0]), pair[0][1])):
        ordered = sorted(events, key=lambda e: e.ts)
        daily.append({'user_id': uid, 'audience': audience(*flags.get(uid, (False, False)), uid), 'day': day, 'first_at': ordered[0].ts.isoformat()+'Z',
                      'last_at': ordered[-1].ts.isoformat()+'Z', 'features': sorted({e.kind for e in events}),
                      'connection_times': [r.ts.isoformat()+'Z' for r in rows if r.user_id == uid and r.ts.date().isoformat() == day and r.event in {'register', 'login'}],
                      'recorded_duration_ms': sum((r.props or {}).get('duration_ms', 0) for r in rows if r.user_id == uid and r.ts.date().isoformat() == day),
                      'estimated_minutes': round(sum(session_minutes(s) for s in sessions(events)), 2)})
    grouped = defaultdict(list)
    device_days = defaultdict(list)
    for r in timeline:
        key = r['device_id'] if group_by == 'device' else r['user_id']
        grouped[str(key) if key is not None else 'unknown'].append(r)
        device_days[(r['device_id'], r['ts'][:10], r['audience'])].append(r)
    device_daily = []
    for (device, day, category), items in device_days.items():
        events = [Event(datetime.fromisoformat(r['ts'].rstrip('Z')), r['track'] or 'usage', None, r['event']) for r in items]
        device_daily.append({'device_id': device, 'day': day, 'audience': category,
            'features': sorted({r['event'] for r in items}), 'first_at': items[0]['ts'], 'last_at': items[-1]['ts'],
            'estimated_minutes': round(sum(session_minutes(sess) for sess in sessions(events)), 2),
            'recorded_duration_ms': sum((r['props'] or {}).get('duration_ms', 0) for r in items)})
    test_counts = Counter((r.ts.date().isoformat(), r.event) for r in test_rows)
    return {'timezone': 'UTC', 'aggregate': [{'day': d, 'event': e, 'audience': category, 'count': n} for (d,e,category),n in sorted(counts.items())],
            'test_aggregate': [{'day': d, 'event': e, 'audience': 'test', 'count': n} for (d,e),n in sorted(test_counts.items())],
            'include_tests': include_tests, 'group_by': group_by, 'timeline_groups': dict(grouped),
            'timeline': timeline, 'daily': daily, 'device_daily': device_daily,
            'duration_method': '30 minute session gap; last activity plus 1 minute estimate; legacy learning cannot be assigned to devices'}
