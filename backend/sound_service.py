"""소리 조건(C17)·듣기 트랙의 소리 파일 서빙과 동적 문장 캐시(파일·디스크를 다루는 쪽). 찾기 키·음절 시각 같은 순수 계산은 sound_clips.

- 고정 소리: `data/sound/manifest.json` + `data/sound/clips/<id>.{ogg,m4a}`(저장소에 커밋, 이미지에 함께 실린다).
- 동적 소리(LLM 시나리오 문장): 서버 볼륨 캐시 `LIPLAB_SOUND_CACHE_DIR`(기본 /data/sound_cache, 볼륨이 없으면 끔)에 둔다.
  크기 상한 `LIPLAB_SOUND_CACHE_MB`(기본 200MB)를 넘으면 오래 안 쓴 것부터 지운다. 합성은 `LIPLAB_SOUND_DYNAMIC=1`이고
  합성기(sound_tts)가 설치돼 있을 때만 한다. 기본은 끔이라 고정 목록에 없는 글은 '없음'(404)이고 화면은 '소리 준비 중'을 보인다.
- 잡담 잡음: `data/sound/noise/babble.{ogg,m4a}`(듣기 4·5단계).
"""
import json
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import sound_clips as S

_HERE = os.path.dirname(os.path.abspath(__file__))
SOUND_DIR = os.getenv("LIPLAB_SOUND_DIR") or os.path.join(_HERE, "data", "sound")
CODECS = ("ogg", "m4a")
AUDIO_BASE = "/api/sound/audio"
NOISE_BASE = "/api/sound/noise"

_lock = threading.Lock()
_manifest_cache: Dict[str, tuple] = {}


def manifest() -> Dict:
    """고정 목록(파일이 바뀌면 다시 읽는다)."""
    path = os.path.join(SOUND_DIR, "manifest.json")
    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = None
    with _lock:
        hit = _manifest_cache.get(path)
        if hit and hit[0] == mt:
            return hit[1]
        m = S.load_manifest(path) if mt is not None else S.load_manifest("")
        _manifest_cache[path] = (mt, m)
        return m


def voices() -> List[Dict]:
    return list(manifest().get("voices") or [])


def resolve_voice(voice: Optional[str]) -> Optional[str]:
    """요청한 목소리 id → 목록의 id. 생략하면 기본 목소리. 모르는 목소리는 None('없음' 응답)."""
    m = manifest()
    default = m.get("default_voice") or ""
    if not voice:
        return default
    ids = {v.get("id") for v in m.get("voices") or []}
    return voice if voice in ids else None


# ── 동적 캐시 ──────────────────────────────────────────────────────────────

def cache_dir() -> Optional[str]:
    d = os.getenv("LIPLAB_SOUND_CACHE_DIR")
    if d is None:
        d = "/data/sound_cache" if os.path.isdir("/data") else ""
    if not d:
        return None
    try:
        os.makedirs(d, exist_ok=True)
        return d if os.access(d, os.W_OK) else None
    except OSError:
        return None


def cache_cap_bytes() -> int:
    try:
        return max(1, int(os.getenv("LIPLAB_SOUND_CACHE_MB", "200"))) * 1024 * 1024
    except ValueError:
        return 200 * 1024 * 1024


_index: Optional[Dict] = None


def _index_path(d: str) -> str:
    return os.path.join(d, "index.json")


def _load_index(d: str) -> Dict:
    global _index
    if _index is None:
        try:
            with open(_index_path(d), encoding="utf-8") as f:
                _index = json.load(f)
        except (OSError, ValueError):
            _index = {}
    return _index


def _save_index(d: str) -> None:
    tmp = _index_path(d) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_index or {}, f, ensure_ascii=False)
    os.replace(tmp, _index_path(d))


def cache_lookup(text: str, voice: str) -> Optional[Dict]:
    d = cache_dir()
    if not d:
        return None
    key = S.normalize_text(text)
    with _lock:
        idx = _load_index(d)
        clip = (idx.get(voice) or {}).get(key)
        if not clip or not all(os.path.exists(os.path.join(d, f"{clip['id']}.{ext}")) for ext in CODECS):
            return None
        clip["used"] = time.time()
        return {"key": key, **clip}


def cache_store(key: str, voice: str, clip: Dict, files: Dict[str, bytes]) -> None:
    """합성한 소리를 캐시에 넣고 상한을 넘으면 오래 안 쓴 것부터 지운다."""
    d = cache_dir()
    if not d:
        return
    with _lock:
        for ext, data in files.items():
            tmp = os.path.join(d, f"{clip['id']}.{ext}.tmp")
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(d, f"{clip['id']}.{ext}"))
        idx = _load_index(d)
        idx.setdefault(voice, {})[key] = {**clip, "used": time.time(),
                                          "bytes": sum(len(b) for b in files.values())}
        entries = [(f"{v}\n{k}", int(c.get("bytes") or 0), float(c.get("used") or 0))
                   for v, clips in idx.items() for k, c in clips.items()]
        for name in S.evict_plan(entries, cache_cap_bytes()):
            v, k = name.split("\n", 1)
            c = idx.get(v, {}).pop(k, None)
            if c:
                for ext in CODECS:
                    try:
                        os.remove(os.path.join(d, f"{c['id']}.{ext}"))
                    except OSError:
                        pass
        _save_index(d)


# ── 찾기 ──────────────────────────────────────────────────────────────────

def find(text: str, voice: Optional[str]) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
    """(목록 항목, 출처 'fixed'|'cache', 목소리 id). 목소리를 모르면 (None, None, None)."""
    vid = resolve_voice(voice)
    if vid is None:
        return None, None, None
    m = manifest()
    clips = (m.get("clips") or {}).get(vid) or {}
    clip = S.lookup({"clips": clips}, text)
    if clip:
        return clip, "fixed", vid
    clip = cache_lookup(text, vid)
    if clip:
        return clip, "cache", vid
    return None, None, vid


def response(text: str, clip: Dict, source: str, voice: str) -> Dict:
    out = S.response_for(text, clip, AUDIO_BASE, CODECS, source)
    out["voice"] = voice
    out["available"] = True
    return out


def audio_path(name: str) -> Optional[str]:
    """'/api/sound/audio/<id>.<ext>'의 파일. 고정 폴더 먼저, 다음 캐시."""
    if not S.safe_audio_name(name):
        return None
    p = os.path.join(SOUND_DIR, "clips", name)
    if os.path.isfile(p):
        return p
    d = cache_dir()
    if d:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


# 듣기 트랙 소음 종류(docs/sound-condition.md 4.2): 경쟁 화자 1명(여·남), 2명 겹침, 잡담(12흐름), 말소리 모양 정상 잡음(SSN).
# 인공와우 사용자는 경쟁 화자 수에 따라 어려움이 단조롭지 않아 한 축으로 묶지 않고 종류별로 둔다.
NOISE_NAMES = ("babble", "talker1_f", "talker1_m", "talker2", "ssn")


def noise_path(name: str) -> Optional[str]:
    base, dot, ext = (name or "").rpartition(".")
    if not dot or base not in NOISE_NAMES or ext not in S.CODEC_TYPES:
        return None
    p = os.path.join(SOUND_DIR, "noise", name)
    return p if os.path.isfile(p) else None


def noises() -> List[str]:
    """두 형식(ogg·m4a)이 모두 있는 소음 이름(화면은 있는 것만 쓴다)."""
    return [n for n in NOISE_NAMES if all(noise_path(f"{n}.{ext}") for ext in CODECS)]


def media_type(name: str) -> str:
    return "audio/ogg" if name.endswith(".ogg") else "audio/mp4"


# ── 동적 합성(기본 끔) ──────────────────────────────────────────────────────

def dynamic_enabled() -> bool:
    if os.getenv("LIPLAB_SOUND_DYNAMIC") != "1" or not cache_dir():
        return False
    try:
        import sound_tts
        return sound_tts.available()
    except Exception:
        return False


MAX_DYNAMIC_CHARS = 80


def generate(text: str, voice: str) -> Optional[Dict]:
    """글 하나를 합성·인코딩·정렬해 캐시에 넣고 목록 항목을 돌려준다(스레드에서 부른다). 실패하면 None."""
    import sound_tts
    key = S.normalize_text(text)
    if not key or len(key) > MAX_DYNAMIC_CHARS:
        return None
    vinfo = next((v for v in voices() if v.get("id") == voice), None)
    engine_voice = (vinfo or {}).get("engine_voice")
    if not engine_voice:
        return None
    from korean_numbers import normalize_numbers
    res = sound_tts.synthesize(normalize_numbers(text), engine_voice)
    if not res:
        return None
    wav16, ms, files = res
    syl = sound_tts.align_syllables(wav16, text, ms)
    clip = {"id": S.clip_id(key, voice), "ms": int(ms), "syl": syl, "text": text}
    cache_store(key, voice, clip, files)
    return {"key": key, **clip}
