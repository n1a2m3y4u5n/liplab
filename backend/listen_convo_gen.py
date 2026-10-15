"""소리 듣기 대화 생성 문항(docs/listen-convo-tts-2026-10.md 2절, 기본 끔).

장면 묶음(listen_curriculum.SCENES)마다 생성 문항을 목표 수(LIPLAB_LISTEN_GEN_POOL, 기본 6)까지 뒤에서 만든다. 한 문항은
(1) 언어 모델 생성(llm_service.generate_listen_convo_item, 측정·시험은 LIPLAB_LISTEN_GEN_FIXTURE의 대리 문항) → (2) 규칙 점검(validate_item)
→ (3) 대사·바꾼 말을 훈련 목소리마다 서버 합성(sound_service.generate, 실행 중 품질 게이트) → (4) 피할 목소리 정하기 순서다.
쓸 수 있는 훈련 목소리가 둘 이상이면 'ready', 아니면 'rejected'. 준비된 문항만 연습·5단계 문항에 섞고, 없으면 미리 합성한 문항만 낸다.

켜기: LIPLAB_LISTEN_GEN=1 이고 동적 합성(sound_service.dynamic_enabled)이 켜져 있을 때. 문항 저장소는 소리 캐시와 같은 폴더의
convo_items.json이다(문항 id = 대사 찾기 키의 sha1 앞 12자, 같은 대사는 다시 만들지 않는다).
"""
import asyncio
import datetime
import hashlib
import json
import os
import re
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import listen_curriculum as L
import sound_clips as S

STORE_NAME = "convo_items.json"
LINE_MIN, LINE_MAX = 10, 45
OPTION_MAX = 15
QUESTION_MAX = 40
MIN_USABLE_VOICES = 2
PRACTICE_MAX = 3      # 연습 '상황별 대화 듣기' 한 묶음에 섞는 생성 문항 수 상한
STAGE5_MAX = 2        # 5단계 8문항 가운데 생성 문항 수 상한(답은 숙달에 넣지 않는다)
_KST = datetime.timezone(datetime.timedelta(hours=9))
_HANGUL_ONLY = re.compile(r"^[가-힣 .,?!~]+$")

_lock = threading.Lock()
_store: Optional[Dict] = None
_store_path: Optional[str] = None
_pending: List[str] = []
_runner: Optional[asyncio.Task] = None
_fixture: Dict[str, object] = {"path": None, "items": []}


def pool_target() -> int:
    try:
        return max(0, int(os.getenv("LIPLAB_LISTEN_GEN_POOL", "6")))
    except ValueError:
        return 6


def daily_cap() -> int:
    """장면마다 하루 생성 시도 상한(점검·게이트에서 떨어진 것 포함). 언어 모델 호출 수의 상한이기도 하다."""
    try:
        return max(0, int(os.getenv("LIPLAB_LISTEN_GEN_DAILY", "4")))
    except ValueError:
        return 4


def scene_keys() -> List[str]:
    return [s["key"] for s in L.SCENES]


def scene_for(place: Optional[str]) -> Optional[str]:
    """장면 묶음 key나 장소 이름 → 장면 묶음 key."""
    for s in L.SCENES:
        if place == s["key"] or place in s["places"]:
            return s["key"]
    return None


def enabled() -> bool:
    if os.getenv("LIPLAB_LISTEN_GEN") != "1":
        return False
    import sound_service
    return sound_service.dynamic_enabled()


def source_available() -> bool:
    return bool(os.getenv("LIPLAB_LISTEN_GEN_FIXTURE") or os.getenv("ANTHROPIC_API_KEY"))


# ── 문항 점검 ─────────────────────────────────────────────────────────────

def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _nospace(s: str) -> str:
    return re.sub(r"[\s.,?!~]", "", s or "")


_FORBIDDEN_KEYS: Optional[set] = None


def _forbidden_keys() -> set:
    """대사·바꾼 말로 쓰면 안 되는 글의 찾기 키: 검사 문장(지금 판과 바뀌기 전 판)과 기존 대화 문항의 대사·바꾼 말."""
    global _FORBIDDEN_KEYS
    if _FORBIDDEN_KEYS is None:
        ks = {S.normalize_text(s) for f in L.TEST_FORMS.values() for s in f}
        for ch in getattr(L, "TEST_FORM_CHANGES", None) or []:
            for v in ch:
                if isinstance(v, str) and len(v) > 2:
                    ks.add(S.normalize_text(v))
        for c in L.CONVO_ITEMS:
            ks.add(S.normalize_text(c["line"]))
            ks.add(S.normalize_text(c["paraphrase"]))
        _FORBIDDEN_KEYS = ks
    return _FORBIDDEN_KEYS


def validate_item(raw: Dict, scene_key: str) -> Tuple[Optional[Dict], str]:
    """날것 → (점검을 통과한 문항, '') 또는 (None, 이유). docs/listen-convo-tts-2026-10.md 2절 2번."""
    sc = next((s for s in L.SCENES if s["key"] == scene_key), None)
    if not sc or not isinstance(raw, dict):
        return None, "bad_input"
    line, para, q = _clean(raw.get("line")), _clean(raw.get("paraphrase")), _clean(raw.get("question"))
    opts = raw.get("options")
    if not (line and para and q and isinstance(opts, list) and len(opts) == 4):
        return None, "missing_fields"
    opts = [_clean(o) for o in opts]
    try:
        ans = int(raw.get("answer"))
    except (TypeError, ValueError):
        return None, "bad_answer"
    if not 0 <= ans < 4:
        return None, "bad_answer"
    for t in (line, para, q, *opts):
        if not t or not _HANGUL_ONLY.match(t):
            return None, "non_hangul"
    if not LINE_MIN <= len(line) <= LINE_MAX or not LINE_MIN <= len(para) <= LINE_MAX + 15:
        return None, "length"
    if len(q) > QUESTION_MAX or any(len(o) > OPTION_MAX for o in opts):
        return None, "length"
    if len(S.syllable_positions(line)) < 5:
        return None, "length"
    if len({_nospace(o) for o in opts}) < 4:
        return None, "dup_options"
    if _nospace(opts[ans]) not in _nospace(line) + "|" + _nospace(para):
        return None, "answer_not_heard"
    kl, kp = S.normalize_text(line), S.normalize_text(para)
    if kl == kp:
        return None, "same_paraphrase"
    import sound_service
    if max(len(kl), len(kp)) > sound_service.MAX_DYNAMIC_CHARS:
        return None, "length"
    if L.gen_words_in(" ".join([line, para, q, *opts])):
        return None, "gen_word"
    forb = _forbidden_keys()
    if kl in forb or kp in forb:
        return None, "known_text"
    place = _clean(raw.get("place"))
    if place not in sc["places"]:
        place = sc["places"][0]
    return {"scene": scene_key, "place": place, "line": line, "paraphrase": para, "question": q, "options": opts,
            "answer": ans}, ""


def item_id(line: str) -> str:
    return "g" + hashlib.sha1(S.normalize_text(line).encode("utf-8")).hexdigest()[:12]


# ── 목소리 ───────────────────────────────────────────────────────────────

def train_voices() -> List[str]:
    """훈련 목소리(목록 순서). 목소리가 셋 이상이면 마지막은 검사 전용이라 뺀다(화면 listenMix.voiceRoles와 같다)."""
    import sound_service
    vids = [v.get("id") for v in sound_service.voices() if v.get("id")]
    return vids[:-1] if len(vids) >= 3 else vids


def avoid_from_list(item: Dict, voices: Sequence[str]) -> List[str]:
    """피하기 목록(data/listen_voice_avoid.json)에서 보기 낱말 가운데 하나를 구별되게 내지 못한다고 적힌 목소리."""
    av = L.voice_avoid()
    keys = {S.normalize_text(o) for o in item.get("options") or []}
    return sorted(v for v in voices if any((av.get(v) or {}).get(k) for k in keys))


# ── 저장소 ───────────────────────────────────────────────────────────────

def _path() -> Optional[str]:
    import sound_service
    d = sound_service.cache_dir()
    return os.path.join(d, STORE_NAME) if d else None


def _load() -> Dict:
    global _store, _store_path
    p = _path()
    if _store is None or _store_path != p:
        data = {"items": {}, "attempts": {}}
        if p:
            try:
                with open(p, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    data["items"] = raw.get("items") or {}
                    data["attempts"] = raw.get("attempts") or {}
            except (OSError, ValueError):
                pass
        _store, _store_path = data, p
    return _store


def _save() -> None:
    p = _path()
    if not p or _store is None:
        return
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_store, f, ensure_ascii=False)
    os.replace(tmp, p)


def reset_cache() -> None:
    """시험용: 메모리의 저장소·대기열을 비운다(파일은 그대로)."""
    global _store, _store_path, _runner
    with _lock:
        _store, _store_path = None, None
        _pending.clear()
        _runner = None
        _fixture.update(path=None, items=[])


def _today() -> str:
    return datetime.datetime.now(_KST).date().isoformat()


def _attempts_today(scene_key: str) -> int:
    return int(((_load().get("attempts") or {}).get(_today()) or {}).get(scene_key) or 0)


def _bump_attempt(scene_key: str) -> None:
    att = _load().setdefault("attempts", {})
    today = _today()
    for d in [d for d in att if d != today]:
        att.pop(d, None)
    day = att.setdefault(today, {})
    day[scene_key] = int(day.get(scene_key) or 0) + 1


def lookup(gid: str) -> Optional[Dict]:
    with _lock:
        it = (_load().get("items") or {}).get(gid)
    return dict(it) if it and it.get("status") == "ready" else None


def _usable_voices(it: Dict, voices: Sequence[str]) -> List[str]:
    """피할 목소리를 뺀 훈련 목소리 가운데 대사·바꾼 말 소리가 지금 있는 것(캐시에서 지워졌으면 빠진다)."""
    import sound_service
    out = []
    for v in voices:
        if v in (it.get("avoid_voices") or []):
            continue
        if all(sound_service.find(t, v)[0] is not None for t in (it["line"], it["paraphrase"])):
            out.append(v)
    return out


def ready_items(scene_key: Optional[str], recent: Sequence[str] = (), limit: int = PRACTICE_MAX) -> List[Dict]:
    """준비된 생성 문항(정답 번호 뺀 꼴, convo_items와 같은 모양 + generated·avoid_voices). scene_key가 None이면 모든 장면.
    최근에 들은 것(recent id)은 뒤로 미루고, 만든 순서대로. 소리가 캐시에서 지워져 목소리가 둘 미만이 된 문항은 뺀다."""
    if limit <= 0 or not enabled():
        return []
    with _lock:
        items = [(k, dict(v)) for k, v in (_load().get("items") or {}).items()
                 if v.get("status") == "ready" and (scene_key is None or v.get("scene") == scene_key)]
    items.sort(key=lambda kv: kv[1].get("created") or 0)
    seen = set(recent)
    items = [kv for kv in items if kv[0] not in seen] + [kv for kv in items if kv[0] in seen]
    voices = train_voices()
    out = []
    for gid, it in items:
        usable = _usable_voices(it, voices)
        if len(usable) < MIN_USABLE_VOICES:
            continue
        out.append({"key": f"g:{gid}", "id": gid, "place": it["place"], "line": it["line"], "paraphrase": it["paraphrase"],
                    "question": it["question"], "options": list(it["options"]), "generated": True,
                    "avoid_voices": sorted(v for v in voices if v not in usable)})
        if len(out) >= limit:
            break
    return out


def mix(static: List[Dict], gen: List[Dict], keep_len: bool = False) -> List[Dict]:
    """미리 합성한 문항 사이에 생성 문항을 섞는다(두 번째부터 하나 걸러). keep_len이면 전체 수를 static과 같게 둔다."""
    if not gen:
        return list(static)
    out = list(static)
    pos = 1
    for g in gen:
        out.insert(min(pos, len(out)), g)
        pos += 2
    return out[:len(static)] if keep_len else out


def status() -> Dict:
    with _lock:
        st = _load()
        items = st.get("items") or {}
        by = {}
        for v in items.values():
            b = by.setdefault(v.get("scene"), {"ready": 0, "rejected": 0, "pending": 0})
            b[v.get("status") if v.get("status") in b else "pending"] += 1
        return {"enabled": enabled(), "source": source_available(), "pool_target": pool_target(), "daily_cap": daily_cap(),
                "scenes": by, "attempts_today": (st.get("attempts") or {}).get(_today()) or {},
                "queue": list(_pending), "running": bool(_runner and not _runner.done()),
                "rejects": [{"id": k, "scene": v.get("scene"), "reason": v.get("reason")} for k, v in items.items()
                            if v.get("status") == "rejected"][-50:]}


# ── 생성 ─────────────────────────────────────────────────────────────────

def _fixture_items() -> List[Dict]:
    p = os.getenv("LIPLAB_LISTEN_GEN_FIXTURE")
    if not p:
        return []
    if _fixture["path"] != p:
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("items") if isinstance(raw, dict) else raw
        except (OSError, ValueError):
            items = []
        _fixture.update(path=p, items=list(items or []))
    return _fixture["items"]  # type: ignore[return-value]


def _fixture_left(scene_key: str) -> List[Dict]:
    with _lock:
        have = set((_load().get("items") or {}).keys())
    return [it for it in _fixture_items() if it.get("scene") == scene_key and item_id(it.get("line", "")) not in have]


def _need(scene_key: str) -> bool:
    if not enabled() or not source_available():
        return False
    with _lock:
        items = (_load().get("items") or {}).values()
        n = sum(1 for v in items if v.get("scene") == scene_key and v.get("status") in ("ready", "pending"))
    if n >= pool_target() or _attempts_today(scene_key) >= daily_cap():
        return False
    if os.getenv("LIPLAB_LISTEN_GEN_FIXTURE"):
        return bool(_fixture_left(scene_key))
    return True


async def _raw_item(scene_key: str) -> Optional[Dict]:
    if os.getenv("LIPLAB_LISTEN_GEN_FIXTURE"):
        left = _fixture_left(scene_key)
        return dict(left[0]) if left else None
    import llm_service
    sc = next(s for s in L.SCENES if s["key"] == scene_key)
    with _lock:
        existing = [v["line"] for v in (_load().get("items") or {}).values() if v.get("scene") == scene_key]
    existing += [c["line"] for c in L.CONVO_ITEMS if c["place"] in sc["places"]]
    return await llm_service.generate_listen_convo_item(sc["label"], list(sc["places"]), existing)


async def produce(scene_key: str, slot: Callable) -> Optional[Dict]:
    """한 문항을 만든다. slot()은 추론 대기열(main._ml_slot)이고 클립 하나마다 잡는다. 저장소에 남긴 기록을 돌려준다."""
    import sound_service
    t0 = time.time()
    with _lock:
        _bump_attempt(scene_key)
        _save()
    raw = await _raw_item(scene_key)
    if not raw:
        return None
    item, why = validate_item(raw, scene_key)
    gid = item_id((item or raw).get("line", "") if isinstance(item or raw, dict) else "")
    if item is None:
        rec = {"scene": scene_key, "status": "rejected", "reason": why, "line": _clean(raw.get("line")), "created": time.time()}
        with _lock:
            _load()["items"][gid] = rec
            _save()
        return rec
    with _lock:
        if gid in _load()["items"]:
            return dict(_load()["items"][gid])
        _load()["items"][gid] = {**item, "status": "pending", "created": time.time()}
        _save()
    voices = train_voices()
    avoid = set(avoid_from_list(item, voices))
    clips = {}
    synth_s = []
    for v in voices:
        if v in avoid:
            continue
        for text in (item["line"], item["paraphrase"]):
            if sound_service.find(text, v)[0] is not None:
                clips[f"{v}:{text}"] = "have"
                continue
            t1 = time.time()
            try:
                async with slot():
                    c = await asyncio.to_thread(sound_service.generate, text, v)
            except Exception as e:
                print(f"[WARN] 대화 문항 합성 실패: {type(e).__name__}: {e}")
                c = None
            synth_s.append(round(time.time() - t1, 3))
            clips[f"{v}:{text}"] = "ok" if c else "rejected"
            if not c:
                avoid.add(v)
                break
    usable = [v for v in voices if v not in avoid]
    st = "ready" if len(usable) >= MIN_USABLE_VOICES else "rejected"
    rec = {**item, "status": st, "avoid_voices": sorted(avoid), "created": time.time(), "build_s": round(time.time() - t0, 2),
           "synth_s": synth_s, "clips": clips}
    if st == "rejected":
        rec["reason"] = "voices"
    with _lock:
        _load()["items"][gid] = rec
        _save()
    return rec


async def _run(slot: Callable) -> None:
    global _runner
    try:
        while _pending:
            sc = _pending.pop(0)
            if not _need(sc):
                continue
            try:
                await produce(sc, slot)
            except Exception as e:
                print(f"[WARN] 대화 문항 생성 실패: {type(e).__name__}: {e}")
            if _need(sc):
                _pending.append(sc)
    finally:
        _runner = None


def kick(scene_key: Optional[str], slot: Callable) -> bool:
    """그 장면의 생성 문항이 목표보다 적으면 뒤에서 만들기 시작한다(요청은 기다리지 않는다). 한 번에 한 문항씩, 장면을 돌아가며 만든다."""
    global _runner
    if scene_key not in scene_keys() or not _need(scene_key):
        return False
    if scene_key not in _pending:
        _pending.append(scene_key)
    if _runner is None or _runner.done():
        _runner = asyncio.get_running_loop().create_task(_run(slot))
    return True


def neediest_scene() -> Optional[str]:
    """준비된 문항이 가장 적은 장면(5단계가 뒤 생성을 시작할 때 고른다)."""
    with _lock:
        items = (_load().get("items") or {}).values()
        cnt = {k: 0 for k in scene_keys()}
        for v in items:
            if v.get("scene") in cnt and v.get("status") in ("ready", "pending"):
                cnt[v["scene"]] += 1
    cands = [k for k in scene_keys() if cnt[k] < pool_target()]
    return min(cands, key=lambda k: cnt[k]) if cands else None
