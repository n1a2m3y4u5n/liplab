"""LLM 호출 하루 한도(비용 상한).

IP별 분당 제한(ratelimit)만으로는 IP를 여러 개 쓰거나 한도 아래로 계속 부르면 Anthropic 비용이 끝없이 늘었다.
둘러보기(데모) 토큰은 로그인 없이 받으므로 누구나 부를 수 있다. 모든 messages.create 호출 앞에서
(1) 서버 전체 하루 호출 수와 (2) 클라이언트 IP별 하루 호출 수를 세어, 넘으면 BudgetExceeded를 던진다.
호출하는 쪽은 이미 예외를 잡아 저장 문장·대체 대사·규칙 코칭으로 넘어가므로 사용자 화면은 그대로 동작한다.

한도(한국 시간 자정에 초기화):
- LIPLAB_LLM_DAILY_MAX: 서버 전체, 기본 1500회(상황 문장 sonnet 호출 약 1센트 기준 하루 약 15달러 이하).
- LIPLAB_LLM_CLIENT_DAILY_MAX: IP당, 기본 150회.
서버 전체 수는 DB와 같은 폴더(/data 볼륨)의 JSON 파일에 남겨 기계가 멈췄다 켜져도 이어 센다. IP별 수는 메모리에만 둔다.
진짜 최종 안전장치는 Anthropic 콘솔의 월 사용 한도다(코드로 대신할 수 없다).
"""
import contextvars
import datetime
import json
import os
import threading

current_client: contextvars.ContextVar = contextvars.ContextVar("llm_client", default="unknown")

_KST = datetime.timezone(datetime.timedelta(hours=9))
_lock = threading.Lock()
_state = {"date": None, "total": 0, "clients": {}}


class BudgetExceeded(RuntimeError):
    pass


def _limits():
    def num(name, default):
        try:
            return max(0, int(os.getenv(name, default)))
        except ValueError:
            return int(default)
    return num("LIPLAB_LLM_DAILY_MAX", "1500"), num("LIPLAB_LLM_CLIENT_DAILY_MAX", "150")


def _state_path():
    p = os.getenv("LIPLAB_LLM_BUDGET_FILE")
    if p:
        return p
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("sqlite") and ":////" in url:          # sqlite+aiosqlite:////data/liplab.db → /data
        return os.path.join(os.path.dirname("/" + url.split(":////", 1)[1]), "llm_budget.json")
    return None


def _today():
    return datetime.datetime.now(_KST).date().isoformat()


def _load(today):
    path = _state_path()
    if not path:
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return int(d.get("total", 0)) if d.get("date") == today else 0
    except Exception:
        return 0


def _save():
    path = _state_path()
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": _state["date"], "total": _state["total"]}, f)
        os.replace(tmp, path)
    except Exception:
        pass


def charge(client_key=None):
    """호출 1회를 센다. 한도를 넘으면 세지 않고 BudgetExceeded."""
    daily, per_client = _limits()
    key = client_key or current_client.get()
    with _lock:
        today = _today()
        if _state["date"] != today:
            _state.update(date=today, total=_load(today), clients={})
        used = _state["clients"].get(key, 0)
        if _state["total"] >= daily:
            raise BudgetExceeded("LLM 하루 한도(서버 전체)")
        if used >= per_client:
            raise BudgetExceeded("LLM 하루 한도(IP)")
        _state["total"] += 1
        _state["clients"][key] = used + 1
        _save()


def usage():
    daily, per_client = _limits()
    with _lock:
        return {"date": _state["date"], "total": _state["total"], "daily_max": daily,
                "client_daily_max": per_client, "clients": len(_state["clients"])}


def guard(client):
    """AsyncAnthropic 클라이언트의 messages.create 앞에 charge를 건다. 같은 클라이언트에 두 번 걸지 않는다."""
    msgs = client.messages
    if getattr(msgs, "_liplab_budget", False):
        return client
    original = msgs.create

    async def create(*args, **kwargs):
        charge()
        return await original(*args, **kwargs)

    msgs.create = create
    msgs._liplab_budget = True
    return client
