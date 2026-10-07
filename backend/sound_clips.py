"""소리 조건(종합 계획 C17, 커리큘럼 3-2, 아이디어 나21)의 소리 파일 찾기와 음절 시각(순수 함수).

소리 조건은 소리 없이 보고 답한 뒤에만 소리를 붙여 다시 보여 주고, 이어서 소리 없이 한 번 더 보여 준다. 소리는 브라우저
내장 음성이 아니라 미리 합성해 둔 서버 음성이다(docs/sound-condition.md). 고정 콘텐츠(레슨 문장, 단어 은행, 문맥 추론, 3단계
문장 풀, 대화 대체 대사)는 파드에서 한 번 합성해 `data/sound/`에 두고, 이 모듈의 목록(manifest)이 정규화한 글 → 파일·음절
시각을 잇는다.

음절 시각은 합성한 소리를 앱의 D-GOP 정렬기(자체 학습 자모 CTC 정렬기, dgop_acoustic.phone_confidences)로 강제정렬해 얻는다.
자모 구간을 음절로 묶고(중성 하나가 음절 하나), 음절 k의 끝은 다음 음절의 시작으로 둔다. 다만 어절 사이 쉼이 길면 그 사이를
쉼으로 남긴다. 화면은 이 시각에 맞춰 입모양 프레임을 늘이고 줄여 소리와 같이 움직인다.

번호 공간. 입모양 프레임의 text_index는 engine.to_pronounced_syllables(요청한 글)의 자리 번호다. 목록에는 음절 순번(한글 음절만
센 0, 1, 2 …)으로 시각을 두고, 요청한 글의 음절 자리로 다시 옮겨 돌려준다. 구두점이 다른 같은 문장('밥 먹었어요.'와 '밥
먹었어요')도 음절 순번은 같다. 음절 수가 맞지 않으면 시각 없이 소리만 준다(화면은 길이 비례로 맞춘다).
"""
import hashlib
import json
import os
import re
import unicodedata
from typing import Dict, List, Optional, Sequence

MANIFEST_VERSION = 2
# 어절 사이에서 앞 음절 끝과 다음 음절 시작이 이만큼 넘게 벌어지면 쉼으로 남긴다(ms). 그보다 짧은 틈은 앞 음절이 이어 채운다.
PAUSE_GAP_MS = 180
# 쉼으로 남길 때 앞 음절 마지막 자모 구간 뒤에 붙여 줄 꼬리(ms). CTC 구간은 소리보다 짧게 잡히는 경향이 있다.
TAIL_MS = 60

_KEEP_RE = re.compile(r"[^가-힣A-Za-z0-9\s]")
_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """찾기 키. NFC로 맞추고 한글·영문·숫자·공백만 남겨 공백을 하나로 접는다. 끝이 물음표면 '?'를 붙인다(올림 억양이 소리에 남는다).
    '밥 먹었어요.'와 '밥 먹었어요'는 같은 키, '밥 먹었어요?'는 다른 키다. 빈 글은 ''."""
    t = unicodedata.normalize("NFC", text or "").strip()
    question = t.endswith("?")
    body = _SPACE_RE.sub(" ", _KEEP_RE.sub(" ", t)).strip()
    if not body:
        return ""
    return body + ("?" if question else "")


def clip_id(key: str, voice: str = "", rev: str = "") -> str:
    """파일 이름(16자 16진수). 목소리가 바뀌면 이름도 바뀌어 브라우저 캐시가 옛 소리를 쓰지 않는다.
    같은 글·목소리를 다시 합성하면 rev(새 Ogg 파일 sha1 앞 12자, docs/sound-qa-2026-10.md 6절)를 넣어 새 이름을 받는다.
    소리 파일은 immutable로 1년 캐시되므로, 소리가 바뀌었는데 이름이 같으면 이미 받은 브라우저가 옛 소리를 계속 쓴다.
    rev가 없으면 처음 규칙(목소리 + 키) 그대로다."""
    tail = f"\n{rev}" if rev else ""
    return hashlib.sha1(f"{voice}\n{key}{tail}".encode("utf-8")).hexdigest()[:16]


def audio_rev(ogg_bytes: bytes) -> str:
    """다시 합성한 소리의 rev: Ogg 파일 바이트의 sha1 앞 12자."""
    return hashlib.sha1(ogg_bytes).hexdigest()[:12]


def syllable_positions(text: str) -> List[int]:
    """입모양 엔진이 음절로 읽는 자리 번호(text_index) 목록. 숫자는 엔진처럼 한국어 읽기로 센다."""
    import engine
    t = unicodedata.normalize("NFC", text or "").strip()
    if not t:
        return []
    try:
        toks = engine.to_pronounced_syllables(t)
    except Exception:
        return [i for i, ch in enumerate(t) if "가" <= ch <= "힣"]
    return [i for i, tok in enumerate(toks) if isinstance(tok, list) and len(tok) >= 2 and tok[1]]


def group_jamo_by_syllable(tokens: Sequence[str]) -> List[List[int]]:
    """자모 CTC 토큰열(jamo_vocab.text_to_tokens) → 음절마다 그 토큰 번호들. 중성(n:) 하나가 음절 하나다.
    초성(o:)은 다음 중성에, 종성(c:)은 앞 중성에 붙는다. 어절 경계('|')와 특수 토큰은 어디에도 넣지 않는다."""
    groups: List[List[int]] = []
    pending: List[int] = []           # 아직 중성을 만나지 못한 초성
    for i, tok in enumerate(tokens):
        if tok.startswith("o:"):
            pending.append(i)
        elif tok.startswith("n:"):
            groups.append(pending + [i])
            pending = []
        elif tok.startswith("c:"):
            if groups:
                groups[-1].append(i)
        # '|' 등은 건너뛴다
    return groups


def syllable_times(phones: Sequence[Dict], tokens: Sequence[str], duration_ms: Optional[float] = None,
                   pause_gap_ms: float = PAUSE_GAP_MS, tail_ms: float = TAIL_MS) -> Optional[List[List[int]]]:
    """정렬 결과(phone_confidences의 t0·t1초, tokens와 같은 순서) → 음절마다 [시작 ms, 끝 ms].
    음절 시작은 첫 자모 구간 시작, 끝은 다음 음절 시작이다. 틈이 pause_gap_ms보다 길면 끝을 마지막 자모 끝 + tail_ms로 줄여 쉼을
    남긴다. 마지막 음절도 같다(소리 길이를 넘지 않게). 정렬되지 않은 자모가 있는 음절이 하나라도 있으면 None."""
    if len(phones) != len(tokens):
        return None
    groups = group_jamo_by_syllable(tokens)
    if not groups:
        return None
    spans = []
    for g in groups:
        t0s = [phones[i].get("t0") for i in g]
        t1s = [phones[i].get("t1") for i in g]
        if any(v is None for v in t0s + t1s):
            return None
        spans.append((min(t0s) * 1000.0, max(t1s) * 1000.0))
    out = []
    for k, (s, e) in enumerate(spans):
        nxt = spans[k + 1][0] if k + 1 < len(spans) else None
        if nxt is not None and nxt - e <= pause_gap_ms:
            end = nxt
        else:
            end = e + tail_ms
            if nxt is not None:
                end = min(end, nxt)
        if duration_ms is not None:
            end = min(end, float(duration_ms))
        out.append([int(round(s)), int(round(max(end, s + 1)))])
    # 앞뒤가 뒤집힌 구간이 없는지(정렬기는 단조지만 반올림·자르기 뒤에도 확인)
    for k in range(1, len(out)):
        if out[k][0] < out[k - 1][0]:
            return None
    return out


def times_for_text(text: str, syllables: Optional[Sequence[Sequence[int]]]) -> Optional[List[Dict]]:
    """목록의 음절 순번 시각 → 요청한 글의 자리 번호 시각 [{i, t0, t1}]. 음절 수가 다르면 None(소리만 준다)."""
    if not syllables:
        return None
    pos = syllable_positions(text)
    if len(pos) != len(syllables):
        return None
    return [{"i": i, "t0": int(s[0]), "t1": int(s[1])} for i, s in zip(pos, syllables)]


# ── 목록(manifest) ──────────────────────────────────────────────────────────
# {"version": 2, "engine": "...", "default_voice": "f1",
#  "voices": [{"id": "f1", "label": "여성 1", "sex": "f", "engine_voice": "F1"}, …],
#  "clips": {목소리 id: {키: {"id": 파일 이름, "ms": 길이, "syl": [[t0, t1], …] 또는 null, "text": 합성에 넣은 글,
#                              "rev": 다시 합성한 소리의 해시(있을 때만), "q": 고른 후보(c0~c7, 다시 합성했을 때만)}}}}
# 기본 목소리(소리 조건)는 고정 글 전부, 듣기 목소리는 듣기 트랙 글(source 'listen')을 갖는다.

def load_manifest(path: str) -> Dict:
    """목록 파일을 읽는다. 없거나 깨졌으면 빈 목록(소리 조건이 레슨을 막지 않게)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("clips"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": MANIFEST_VERSION, "default_voice": "", "voices": [], "clips": {}}


def lookup(manifest: Dict, text: str) -> Optional[Dict]:
    """글 → 목록 항목(키 포함). manifest는 한 목소리의 {"clips": {키: 항목}}이다. 없으면 None."""
    key = normalize_text(text)
    if not key:
        return None
    clip = (manifest.get("clips") or {}).get(key)
    if not clip or not clip.get("id"):
        return None
    return {"key": key, **clip}


def response_for(text: str, clip: Dict, base_url: str, codecs: Sequence[str], source: str) -> Dict:
    """/api/sound 응답. 시각은 요청한 글의 자리 번호로 옮긴다."""
    return {
        "key": clip["key"],
        "id": clip["id"],
        "duration_ms": int(clip.get("ms") or 0),
        "sources": [{"url": f"{base_url}/{clip['id']}.{ext}", "type": CODEC_TYPES[ext]} for ext in codecs if ext in CODEC_TYPES],
        "syllables": times_for_text(text, clip.get("syl")),
        "source": source,
    }


CODEC_TYPES = {"ogg": "audio/ogg; codecs=opus", "m4a": "audio/mp4"}
_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def safe_audio_name(name: str) -> Optional[tuple]:
    """'<id>.<ext>' → (id, ext). 경로 조작·모르는 확장자는 None."""
    base, dot, ext = (name or "").rpartition(".")
    if not dot or ext not in CODEC_TYPES or not _ID_RE.match(base):
        return None
    return base, ext


# ── 서버 캐시(동적 문장) 크기 상한 ─────────────────────────────────────────────

def evict_plan(entries: Sequence[tuple], cap_bytes: int) -> List[str]:
    """캐시 파일 [(이름, 크기, 마지막 사용 시각)] 가운데 합이 cap_bytes 이하가 되도록 오래 안 쓴 것부터 지울 이름."""
    total = sum(int(sz) for _, sz, _ in entries)
    out = []
    for name, sz, _t in sorted(entries, key=lambda e: e[2]):
        if total <= cap_bytes:
            break
        out.append(name)
        total -= int(sz)
    return out


# ── 비열등 점검(아이디어 나21 판정 기준) ──────────────────────────────────────
# 소리 조건 사용자의 '소리 없는 문항' 향상이 미사용자보다 5%p 넘게 낮지 않아야 한다. 모든 답은 소리 없이 본 뒤에 하므로 시행 기록의
# 정답률이 곧 소리 없는 문항 정답률이다. 사용자 한 명의 향상 = 뒤 절반 정답률 − 앞 절반 정답률(시행 순서). 소리 사용자는 시행의
# 절반 이상에서 sound_condition이 켜져 있던 사람이다(나누는 일은 호출하는 쪽이 한다). 판정은 차이(사용자 − 미사용자)의 단측 95%
# 하한(정규 근사, 웰치)이 −margin보다 크면 비열등, 상한이 −margin보다 작으면 열등, 그 밖은 판정 불가다. 한쪽이라도 min_users명보다
# 적으면 판정 불가다. 문턱(5%p)은 나21에 적힌 값이고, 집단 크기·시행 수 하한은 이 함수의 기본값이다(분석 계획에서 다시 정한다).

def user_gain(correct_seq: Sequence[bool], min_trials: int = 20) -> Optional[float]:
    """시간순 정오 → 뒤 절반 정답률 − 앞 절반 정답률. 시행이 min_trials보다 적으면 None."""
    n = len(correct_seq)
    if n < max(2, min_trials):
        return None
    h = n // 2
    first = sum(1 for c in correct_seq[:h] if c) / h
    last = sum(1 for c in correct_seq[h:] if c) / (n - h)
    return last - first


def noninferiority(users: Sequence[Dict], margin: float = 0.05, min_users: int = 5, min_trials: int = 20) -> Dict:
    """users: [{"sound": bool, "correct": [bool, …](시간순)}] → {verdict, diff, lower, upper, n_sound, n_none, gain_sound, gain_none}."""
    import math
    g = {True: [], False: []}
    for u in users:
        x = user_gain(list(u.get("correct") or []), min_trials)
        if x is not None:
            g[bool(u.get("sound"))].append(x)
    out = {"n_sound": len(g[True]), "n_none": len(g[False]), "margin": margin}
    if len(g[True]) < max(2, min_users) or len(g[False]) < max(2, min_users):
        return {**out, "verdict": "inconclusive", "reason": "too_few_users"}

    def mv(xs):
        m = sum(xs) / len(xs)
        return m, sum((x - m) ** 2 for x in xs) / (len(xs) - 1)

    ms, vs = mv(g[True])
    mn, vn = mv(g[False])
    diff = ms - mn
    se = math.sqrt(vs / len(g[True]) + vn / len(g[False]))
    z = 1.6448536269514722   # 단측 95%
    lower, upper = diff - z * se, diff + z * se
    verdict = "noninferior" if lower > -margin else ("inferior" if upper < -margin else "inconclusive")
    return {**out, "verdict": verdict, "diff": round(diff, 4), "lower": round(lower, 4), "upper": round(upper, 4),
            "gain_sound": round(ms, 4), "gain_none": round(mn, 4)}
