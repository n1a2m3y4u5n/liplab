"""
청인 또래 예비 파일럿(P3)의 사전·사후 검사 묶음(docs/pilot/battery.md).

검사는 네 층이다. 문항과 배정 규칙은 모두 목록 파일(data/pilot/battery_manifest.json)에 동결하고, 이 모듈은 그 파일을 읽어
참여자에게 낼 문항과 순서를 정하고 답을 채점한다. 저장과 화면은 main.py와 frontend/src/pages/PilotBattery.jsx가 맡는다.

- word: 실제 얼굴 낱말 4지선다(영상 파일). 폼마다 24문항.
- sentence: 개방형 문장 타이핑. 실제 얼굴 영상(real) 또는 규칙 엔진 아바타(avatar). 폼마다 40문장.
- nonsense: CVCVC 무의미 낱말 자음 식별. 규칙 엔진 아바타가 말하고, 세 자리 자음을 닫힌 목록에서 고른다. 폼마다 16개.
- av: 잡담 잡음 속 문장(청각만 A, 시청각 AV). 개인 SNR은 A1의 snr 층(적응 계단)에서 정한다. 구조만 있고 문장·음성은 촬영 뒤에 채운다.

회차 이름은 A1·A2(학습 전 두 번), B(학습 뒤), R(유지)이다. 폼 배정은 순환 라틴 방진 세 순서(ABC, BCA, CAB)를 참여 순번대로
돌려 준다(docs/pilot/design-simulation.md 5절). 영상·음성 파일이 없는 문항은 '준비 전'으로 표시하고 내지도 세지도 않는다.

순수 함수만 둔다(DB·FastAPI 없음). 엄격 음소 정답률은 다른 작업에서 만드는 phoneme_accuracy.strict_phoneme_accuracy를 쓰고,
그 모듈이 없으면 None을 남겨 분석 단계에서 다시 계산한다(strict_score).
"""
import hashlib
import json
import os
import random
import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

SCHEMA = "liplab-pilot-battery/1"
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pilot", "battery_manifest.json")
DEFAULT_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pilot", "media")

FORMS = ("A", "B", "C")
ORDERS = ("ABC", "BCA", "CAB")
LABELS = ("A1", "A2", "B", "R")
LAYERS = ("word", "sentence", "nonsense", "snr", "av")
# 회차 이름 → 배정 순서 안의 자리. 유지 검사(R)는 사후(B)와 같은 폼을 다시 본다(C7과 같은 규칙. 새 폼을 쓰려면 4폼이 필요하다)
LABEL_SLOT = {"A1": 0, "A2": 1, "B": 2, "R": 2}
# 앞 회차를 끝내야 다음 회차를 연다
LABEL_PREV = {"A1": None, "A2": "A1", "B": "A2", "R": "B"}
CLOSED_LAYERS = ("word", "nonsense")
OPEN_LAYERS = ("sentence", "av", "snr")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_TALKER_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")

# ── 한글 자모 ──────────────────────────────────────────
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
        "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]


def compose(cho: str, jung: str, jong: str = "") -> str:
    """초성·중성·종성 → 한 음절."""
    return chr(0xAC00 + (CHO.index(cho) * 21 + JUNG.index(jung)) * 28 + JONG.index(jong))


def decompose(syl: str) -> Optional[Tuple[str, str, str]]:
    code = ord(syl) - 0xAC00
    if not (0 <= code < 11172):
        return None
    return CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28]


def syllables(text: str) -> List[str]:
    return [c for c in unicodedata.normalize("NFC", text or "") if "가" <= c <= "힣"]


def phoneme_count(text: str) -> int:
    """채점 음소 수 근사: 음절마다 초성(무음 ㅇ 제외) + 중성 1 + 종성(있으면 1). 표기 기준이다(발음 규칙은 적용하지 않음)."""
    n = 0
    for s in syllables(text):
        cho, _, jong = decompose(s)
        n += (cho != "ㅇ") + 1 + (jong != "")
    return n


# ── 목록 파일 ─────────────────────────────────────────
def load_manifest(path: Optional[str] = None) -> Dict:
    with open(path or MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def manifest_sha(manifest: Dict) -> str:
    """목록 내용의 해시 앞 12자리. 회차 행에 남겨 어떤 목록으로 봤는지 복원할 수 있게 한다."""
    blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _is_cyclic_latin(orders) -> bool:
    if sorted(orders) != sorted(set(orders)) or len(orders) != len(FORMS):
        return False
    for o in orders:
        if sorted(o) != sorted(FORMS):
            return False
    return all(sorted(o[i] for o in orders) == sorted(FORMS) for i in range(len(FORMS)))


def validate_manifest(m: Dict) -> List[str]:
    """목록 파일 점검. 문제 문장 목록(비면 통과). 서버는 시작할 때와 검사 상태를 줄 때 이 결과를 함께 보인다."""
    err: List[str] = []
    if not isinstance(m, dict):
        return ["목록이 사전이 아니다"]
    if m.get("schema") != SCHEMA:
        err.append(f"schema가 {SCHEMA}가 아니다")
    if not m.get("version"):
        err.append("version이 없다")
    if tuple(m.get("forms") or ()) != FORMS:
        err.append("forms는 A·B·C여야 한다")
    if not _is_cyclic_latin(tuple(m.get("orders") or ())):
        err.append("orders가 세 폼의 라틴 방진(자리마다 각 폼 한 번)이 아니다")
    lbl = m.get("layers_by_label") or {}
    for label in LABELS:
        for layer in lbl.get(label, []):
            if layer not in LAYERS:
                err.append(f"{label}: 알 수 없는 층 {layer}")
    if "snr" in sum((lbl.get(x, []) for x in ("A2", "B", "R")), []):
        err.append("snr 층은 A1에만 둔다(SNR은 사전에 정하고 사후에도 그대로 쓴다)")
    pb = m.get("playback") or {}
    if not (isinstance(pb.get("max_plays"), int) and 1 <= pb["max_plays"] <= 5):
        err.append("playback.max_plays는 1~5")
    if pb.get("speed") != 1.0:
        err.append("playback.speed는 1.0(검사는 속도 조절 없음)")
    talkers = m.get("talkers") or {}
    seen_ids = set()
    layers = m.get("layers") or {}
    for name in ("word", "sentence", "nonsense", "av", "snr"):
        L = layers.get(name)
        if not isinstance(L, dict):
            err.append(f"layers.{name}가 없다")
            continue
        pat = L.get("media_pattern")
        if name != "nonsense":
            if not (isinstance(pat, str) and "{talker}" in pat and "{id}" in pat and ".." not in pat and not pat.startswith("/")):
                err.append(f"{name}.media_pattern에 {{talker}}와 {{id}}가 있어야 하고 상대 경로여야 한다")
            ts = talkers.get(name) or []
            if not ts or not all(isinstance(t, str) and _TALKER_RE.match(t) for t in ts):
                err.append(f"talkers.{name}가 비었거나 이름 형식이 틀렸다")
        groups = {"calibration": L.get("items") or []} if name == "snr" else (L.get("items") or {})
        if name != "snr":
            n_per = L.get("n_per_form")
            for f in FORMS:
                if len(groups.get(f) or []) != n_per:
                    err.append(f"{name}.{f} 문항 수 {len(groups.get(f) or [])} != n_per_form {n_per}")
        for key, items in list(groups.items()) + [("reserve", L.get("reserve") or [])]:
            for it in items:
                iid = it.get("id")
                if not (isinstance(iid, str) and _ID_RE.match(iid)):
                    err.append(f"{name}.{key}: 문항 id 형식이 틀렸다({iid!r})")
                    continue
                if iid in seen_ids:
                    err.append(f"문항 id 중복: {iid}")
                seen_ids.add(iid)
                err += _validate_item(name, it, L)
    st = (layers.get("snr") or {}).get("staircase") or {}
    if st:
        if not (st.get("step_down_db", 0) > 0 and st.get("step_up_db", 0) > 0):
            err.append("snr.staircase 계단 크기는 양수")
        if not (st.get("min_db", 0) < st.get("start_db", 0) < st.get("max_db", 0)):
            err.append("snr.staircase는 min_db < start_db < max_db")
        if not (2 <= st.get("use_last", 0) <= st.get("reversals", 0)):
            err.append("snr.staircase는 2 <= use_last <= reversals")
    return err


def _validate_item(layer: str, it: Dict, L: Dict) -> List[str]:
    err = []
    iid = it.get("id")
    if layer == "word":
        opts = it.get("options") or []
        if len(opts) != 4 or len(set(opts)) != 4 or it.get("word") not in opts:
            err.append(f"word {iid}: 보기는 서로 다른 4개이고 정답을 포함해야 한다")
    elif layer == "nonsense":
        cs, vs = it.get("consonants") or [], it.get("vowels") or []
        sets = L.get("consonant_sets") or {}
        if len(cs) != 3 or len(vs) != 2:
            err.append(f"nonsense {iid}: 자음 3개·모음 2개가 필요하다")
        else:
            for pos, c in zip(("C1", "C2", "C3"), cs):
                if c not in (sets.get(pos) or []):
                    err.append(f"nonsense {iid}: {pos} {c}가 자음 목록에 없다")
            try:
                if it.get("text") != compose(cs[0], vs[0]) + compose(cs[1], vs[1], cs[2]):
                    err.append(f"nonsense {iid}: text가 자음·모음과 맞지 않는다")
            except ValueError:
                err.append(f"nonsense {iid}: 자모가 틀렸다")
    elif layer in ("sentence", "av", "snr"):
        text = it.get("text")
        if text is not None:
            n = len(syllables(text))
            lo, hi = (L.get("syllable_range") or [6, 10])
            if not (lo <= n <= hi):
                err.append(f"{layer} {iid}: 음절 수 {n}가 {lo}~{hi} 밖")
            if re.search(r"[0-9A-Za-z]", text):
                err.append(f"{layer} {iid}: 숫자·영문이 있다")
        if layer in ("av", "snr"):
            rms = it.get("speech_rms_dbfs")
            if rms is not None and not (-80 <= rms <= 0):
                err.append(f"{layer} {iid}: speech_rms_dbfs는 -80~0")
    return err


# ── 배정 ──────────────────────────────────────────────
def assign_order(join_seq: int, orders: Iterable[str] = ORDERS) -> str:
    """참여 순번(1부터) → 폼 순서. 모집 순 (i − 1) % 3(design-simulation.md 6절)."""
    orders = tuple(orders)
    return orders[(max(1, int(join_seq)) - 1) % len(orders)]


def form_for(order: str, label: str) -> str:
    if label not in LABEL_SLOT:
        raise ValueError(f"알 수 없는 회차 {label}")
    return order[LABEL_SLOT[label]]


def sentence_talker(join_seq: int, talkers: List[str]) -> str:
    """문장 층 화자. 한 참여자는 모든 회차에서 같은 화자를 보고, 화자는 참여자 사이에서 번갈아 반씩 배정한다."""
    return talkers[(max(1, int(join_seq)) - 1) % len(talkers)]


def word_talker(join_seq: int, label: str, position: int, talkers: List[str]) -> str:
    """낱말 층 화자. 한 회차 안에서 화자를 돌려(24문항이면 4명 × 6문항) 화자 난이도가 회차 점수에 고르게 섞이게 하고,
    회차마다 시작점을 옮겨 같은 낱말 자리에 같은 화자가 반복되지 않게 한다."""
    return talkers[(int(position) + max(1, int(join_seq)) - 1 + LABEL_SLOT[label]) % len(talkers)]


def presentation_order(items: List[Dict], join_seq: int, label: str, layer: str) -> List[Dict]:
    """문항 제시 순서. 참여자·회차·층마다 결정론적으로 섞는다(같은 사람이 다시 들어와도 같은 순서)."""
    rng = random.Random(f"pilot-battery:{int(join_seq)}:{label}:{layer}")
    out = list(items)
    rng.shuffle(out)
    return out


def av_blocks(items: List[Dict], join_seq: int) -> List[Dict]:
    """소음 속 문장의 A·AV 배정. 폼 문장을 앞뒤 절반으로 나눠 한쪽은 청각만(A), 다른 쪽은 시청각(AV)으로 낸다.
    어느 절반이 A인지는 참여자 둘마다 바꾸고, 블록 순서(A 먼저·AV 먼저)는 참여자마다 바꾼다(역균형)."""
    s = max(1, int(join_seq))
    half = len(items) // 2
    first, second = list(items[:half]), list(items[half:])
    a_half, av_half = (first, second) if ((s - 1) // 2) % 2 == 0 else (second, first)
    blocks = [("A", a_half), ("AV", av_half)] if s % 2 == 1 else [("AV", av_half), ("A", a_half)]
    out = []
    for block, its in blocks:
        rng = random.Random(f"pilot-battery-av:{s}:{block}")
        its = list(its)
        rng.shuffle(its)
        out += [dict(it, block=block) for it in its]
    return out


# ── 매체 ──────────────────────────────────────────────
def media_dir() -> str:
    return os.path.abspath(os.getenv("LIPLAB_PILOT_MEDIA_DIR") or DEFAULT_MEDIA_DIR)


def media_relpath(layer_cfg: Dict, item: Dict, talker: str) -> Optional[str]:
    """문항 매체 파일의 상대 경로. 문항이 media(화자별 경로 사전)를 직접 주면 그것을, 아니면 층의 media_pattern을 쓴다."""
    iid = item.get("id") or ""
    if not (_ID_RE.match(iid) and talker and _TALKER_RE.match(talker)):
        return None
    direct = (item.get("media") or {}).get(talker) if isinstance(item.get("media"), dict) else None
    rel = direct or (layer_cfg.get("media_pattern") or "").format(talker=talker, id=iid)
    return rel or None


def media_path(rel: Optional[str], base: Optional[str] = None) -> Optional[str]:
    """상대 경로 → 매체 폴더 안의 절대 경로. 폴더 밖을 가리키면 None(경로 조작 방지)."""
    if not rel:
        return None
    root = os.path.abspath(base or media_dir())
    p = os.path.abspath(os.path.join(root, rel))
    return p if p.startswith(root + os.sep) else None


def media_exists(rel: Optional[str], base: Optional[str] = None) -> bool:
    p = media_path(rel, base)
    return bool(p and os.path.isfile(p) and os.path.getsize(p) > 0)


def noise_relpath(manifest: Dict, kind: str = "babble") -> Optional[str]:
    return ((manifest.get("noise") or {}).get(kind) or {}).get("file")


def item_ready(layer: str, modality: str, item: Dict, media_ok: bool, noise_ok: bool = True,
               snr_db: Optional[float] = None) -> Tuple[bool, Optional[str]]:
    """(낼 수 있는가, 못 내는 까닭). 까닭: 'media'(영상·음성 준비 전) | 'text'(문장 미정) | 'noise'(잡음 파일 없음) | 'snr'(개인 SNR 미정)."""
    if layer == "nonsense":
        return (bool(item.get("text")), None if item.get("text") else "text")
    if layer == "sentence" and modality == "avatar":
        return (bool(item.get("text")), None if item.get("text") else "text")
    if layer in ("sentence", "av", "snr") and not item.get("text"):
        return False, "text"
    if not media_ok:
        return False, "media"
    if layer in ("av", "snr"):
        if item.get("speech_rms_dbfs") is None:
            return False, "media"
        if not noise_ok:
            return False, "noise"
        if layer == "av" and snr_db is None:
            return False, "snr"
    return True, None


# ── 무의미 낱말 생성 ──────────────────────────────────
NONSENSE_C1 = ["ㅂ", "ㅍ", "ㅁ", "ㄷ", "ㅌ", "ㄴ", "ㅅ", "ㅈ", "ㅊ", "ㄱ", "ㅋ", "ㅎ"]   # 어두 ㄹ·무음 ㅇ·된소리는 뺀다
NONSENSE_C2 = ["ㅂ", "ㅍ", "ㅁ", "ㄷ", "ㅌ", "ㄴ", "ㄹ", "ㅅ", "ㅈ", "ㅊ", "ㄱ", "ㅋ"]   # 모음 사이 ㅎ은 약해져 뺀다
NONSENSE_C3 = ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅇ"]                               # 대표 받침 7개
NONSENSE_V = ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅣ"]


def _balanced(pool: List[str], n_forms: int, per_form: int, rng: random.Random) -> List[List[str]]:
    """폼마다 per_form칸. 각 폼에 목록 전체가 먼저 한 번씩 들어가고, 남는 칸은
    폼을 가로질러 고르게 돌려 채운다. 전체 빈도는 많아야 1 차이다."""
    if len(pool) > per_form:
        raise ValueError("자음 목록이 폼 칸보다 길다")
    n_extra = per_form - len(pool)
    extras: List[str] = []
    while len(extras) < n_forms * n_extra:
        block = list(pool)
        rng.shuffle(block)
        extras += block
    forms = []
    for i in range(n_forms):
        f = list(pool) + extras[i * n_extra:(i + 1) * n_extra]
        rng.shuffle(f)
        forms.append(f)
    return forms


def generate_nonsense(seed: int, n_forms: int = 3, per_form: int = 16, avoid: Iterable[str] = ()) -> List[List[Dict]]:
    """CVCVC 무의미 낱말 목록(폼별). 같은 seed면 같은 목록이다(목록 파일에 동결하고 테스트가 다시 만들어 대조한다).
    자리마다 자음 빈도를 폼 사이에서 고르게 맞추고, 실제 낱말(avoid)과 겹치거나 폼 안에서 같은 낱말이 나오면 모음만 다시 뽑는다."""
    rng = random.Random(int(seed))
    avoid = set(avoid)
    c1 = _balanced(NONSENSE_C1, n_forms, per_form, rng)
    c2 = _balanced(NONSENSE_C2, n_forms, per_form, rng)
    c3 = _balanced(NONSENSE_C3, n_forms, per_form, rng)
    used = set()
    forms = []
    for f in range(n_forms):
        items = []
        for i in range(per_form):
            for _ in range(200):
                v1, v2 = rng.choice(NONSENSE_V), rng.choice(NONSENSE_V)
                text = compose(c1[f][i], v1) + compose(c2[f][i], v2, c3[f][i])
                if text not in avoid and text not in used:
                    break
            else:
                raise RuntimeError("무의미 낱말을 만들지 못했다")
            used.add(text)
            items.append({"id": f"N{FORMS[f]}{i + 1:02d}", "text": text, "consonants": [c1[f][i], c2[f][i], c3[f][i]],
                          "vowels": [v1, v2]})
        forms.append(items)
    return forms


# ── 채점 ──────────────────────────────────────────────
def score_choice(item: Dict, chosen: Optional[str]) -> bool:
    return chosen is not None and chosen == item.get("word")


def score_nonsense(item: Dict, chosen: List[Optional[str]]) -> Dict:
    """자리별 자음 정오. hits는 맞힌 자리 수(0~3), correct는 세 자리 모두 맞음."""
    tgt = list(item.get("consonants") or [])
    ch = list(chosen or [])[:3] + [None] * (3 - len(list(chosen or [])[:3]))
    per = [bool(c is not None and c == t) for c, t in zip(ch, tgt)]
    return {"target": tgt, "chosen": ch, "per_position": per, "hits": sum(per), "correct": all(per) and len(per) == 3}


def clean_answer(text: Optional[str], max_len: int = 300) -> str:
    """타이핑 답 원문 정리: NFC, 앞뒤 공백 제거, 길이 제한. 안쪽 공백·오타는 그대로 둔다(사람 채점·재채점용 원문)."""
    return unicodedata.normalize("NFC", text or "").strip()[:max_len]


STRICT_HOOK = "phoneme_accuracy.strict_phoneme_accuracy"


def strict_score(target: str, answer: str) -> Optional[Dict]:
    """엄격 음소 정답률 연결 지점. backend/phoneme_accuracy.py의 strict_phoneme_accuracy(target, answer) -> dict를 부른다.
    모듈이 아직 없거나 오류가 나면 None을 돌려 저장 열을 비워 두고, 분석 때 scripts/pilot_battery_rescore.py로 다시 계산한다."""
    try:
        from phoneme_accuracy import strict_phoneme_accuracy   # noqa: WPS433 (선택 모듈)
    except ImportError:
        return None
    try:
        r = strict_phoneme_accuracy(target, answer)
    except Exception as e:   # 채점 실패가 답 저장을 막지 않게 한다
        print(f"[WARN] strict_phoneme_accuracy 실패: {e}")
        return None
    return r if isinstance(r, dict) else None


def strict_fields(r: Optional[Dict]) -> Dict:
    """엄격 채점 결과에서 저장 열을 꺼낸다. 키 이름이 정해지기 전이라 흔한 이름 몇 가지를 받는다."""
    if not r:
        return {"auto_phoneme_acc": None, "auto_word_acc": None, "strict_version": None}
    pa = next((r[k] for k in ("phoneme_accuracy", "accuracy", "phoneme_acc") if isinstance(r.get(k), (int, float))), None)
    wa = next((r[k] for k in ("word_accuracy", "word_acc") if isinstance(r.get(k), (int, float))), None)
    ver = r.get("version") or r.get("scorer_version")
    return {"auto_phoneme_acc": float(pa) if pa is not None else None,
            "auto_word_acc": float(wa) if wa is not None else None,
            "strict_version": str(ver)[:24] if ver else None}


def word_proportion(target: str, answer: str) -> float:
    """낱말 단위 일치 비율(문장부호를 지운 띄어쓰기 낱말이 답에 그대로 있는 비율). SNR 계단의 '맞음' 판정에만 쓴다."""
    norm = lambda s: re.sub(r"[^\w\s]", "", unicodedata.normalize("NFC", s or "")).split()   # noqa: E731
    t, a = norm(target), norm(answer)
    if not t:
        return 0.0
    pool = list(a)
    hit = 0
    for w in t:
        if w in pool:
            pool.remove(w)
            hit += 1
    return hit / len(t)


# ── 적응 계단(SNR) ────────────────────────────────────
def staircase_run(params: Dict, outcomes: List[bool]) -> Dict:
    """가중 상하 계단(Kaernbach 1991). 맞으면 SNR을 step_down만큼 내리고(어렵게), 틀리면 step_up만큼 올린다(쉽게).
    수렴점의 정답률 p는 step_down·p = step_up·(1 − p)에서 정해진다(3 dB·2 dB면 p = 0.4, 가4의 '청각만 30~50%' 목표).
    outcomes는 지금까지의 판정(시간순). {next_db, reversals, done, estimate_db, history} 를 돌려준다.
    끝: 반전 수가 reversals에 닿거나 시행이 max_trials에 닿을 때. 추정값은 마지막 use_last개 반전의 평균(반전이 부족하면 None)."""
    start, lo, hi = float(params["start_db"]), float(params["min_db"]), float(params["max_db"])
    down, up = float(params["step_down_db"]), float(params["step_up_db"])
    need, use_last, max_trials = int(params["reversals"]), int(params["use_last"]), int(params["max_trials"])
    level = start
    history, revs = [], []
    last_dir = 0
    for ok in outcomes[:max_trials]:
        history.append(level)
        d = -1 if ok else 1
        if last_dir and d != last_dir:
            revs.append(level)
        last_dir = d
        level = min(hi, max(lo, level - down if ok else level + up))
    done = len(revs) >= need or len(history) >= max_trials
    est, kind = None, None
    if len(revs) >= use_last:
        est, kind = round(sum(revs[-use_last:]) / use_last, 2), "reversals"
    elif done and len(history) >= use_last:
        # 시행 상한에 닿도록 반전이 모자라면 마지막 use_last개 시행 수준의 평균을 쓰고 그렇게 했다고 표시한다
        est, kind = round(sum(history[-use_last:]) / use_last, 2), "last_levels"
    return {"next_db": None if done else round(level, 2), "reversals": len(revs), "done": done,
            "estimate_db": est, "estimate_kind": kind, "history": history, "n_trials": len(history)}


def noise_gain(speech_rms_dbfs: float, noise_rms_dbfs: float, snr_db: float) -> float:
    """잡음 이득(선형). 말소리 크기를 그대로 두고 잡음을 (말소리 − SNR) 수준으로 맞춘다. 화면 lib/pilotBattery.js와 같은 식이다."""
    return 10 ** ((speech_rms_dbfs - snr_db - noise_rms_dbfs) / 20)


# ── 기기·렌더링 기록 ──────────────────────────────────
_RENDER_NUM = {"frames": (0, 10 ** 7), "mean_late_ms": (0, 10 ** 5), "max_late_ms": (0, 10 ** 6), "over20_rate": (0, 1),
               "over50_rate": (0, 1), "screen_w": (0, 20000), "screen_h": (0, 20000), "viewport_w": (0, 20000),
               "viewport_h": (0, 20000), "dpr": (0, 10), "video_total_frames": (0, 10 ** 7),
               "video_dropped_frames": (0, 10 ** 7), "video_drop_rate": (0, 1), "screen_hz_est": (0, 500)}
_RENDER_STR = {"render_mode": ("avatar3d", "avatar2d_fallback", "video", "mixed"),
               "device_class": ("desktop", "tablet", "phone"),
               "os_family": ("windows", "mac", "ios", "android", "chromeos", "linux", "other"),
               "browser_family": ("chrome", "edge", "safari", "firefox", "samsung", "other"),
               "scope": ("layer", "lesson")}


def clean_render_log(raw) -> Optional[Dict]:
    """화면이 보낸 기기·렌더링 요약에서 정해진 키만 남긴다(지문으로 쓸 수 있는 GPU 문자열·사용자 에이전트 원문은 받지 않는다)."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, (lo, hi) in _RENDER_NUM.items():
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
            out[k] = round(min(hi, max(lo, float(v))), 4)
    for k, allowed in _RENDER_STR.items():
        v = raw.get(k)
        if isinstance(v, str) and v in allowed:
            out[k] = v
    if isinstance(raw.get("webgl"), bool):
        out["webgl"] = raw["webgl"]
    return out or None


# ── 실제 얼굴 낱말 폼 C ───────────────────────────────
def build_word_form_c(seed: int, n: int = 24) -> List[Dict]:
    """실제 얼굴 낱말 폼 C 초안. 폼 A·B(동결 표준검사 v2 문항, 촬영 키트 48낱말)의 문항 짝마다 두 난이도의 평균에 가장 가까운
    단어를 단어 은행에서 하나씩 고른다(표준검사 단어·드문 말·이미 고른 단어는 뺀다). 오답 보기는 표준검사와 같은 규칙
    (assessment._confusable_options)으로 seed를 고정해 고른다. 결과는 목록 파일에 동결한다."""
    from collections import Counter
    import assessment as _asmt
    import content_rules as _cr
    import curriculum as _cur
    import perceptual as _perc
    forms = _asmt.frozen_forms(build_if_missing=False) or {}
    a, b = forms.get("A") or [], forms.get("B") or []
    bank = [w["word"] for w in _cur.WORD_BANK]
    skip = set(_asmt.test_only_words()) | set(getattr(_cur, "STAGE2_EXCLUDED", {}))
    pool_words = [w for w in dict.fromkeys(bank) if _cr.is_hangul_word(w)]
    sig = Counter(_cr.viseme_signature(w) for w in pool_words)
    cands = [e for e in (_perc.word_difficulty(w, sig) for w in pool_words if w not in skip) if e]
    rng = random.Random(int(seed))
    targets = sorted(((x["difficulty"] + y["difficulty"]) / 2, len(x["word"])) for x, y in zip(a, b))[:n]
    used, out = set(), []
    for i, (d, length) in enumerate(targets):
        best = min((e for e in cands if e["word"] not in used),
                   key=lambda e: (abs(e["difficulty"] - d), abs(len(e["word"]) - length), e["word"]))
        used.add(best["word"])
        opts = _asmt._confusable_options(best["word"], pool_words, closeness=best["difficulty"], rng=rng) + [best["word"]]
        rng.shuffle(opts)
        out.append({"id": f"C{i + 1}", "word": best["word"], "options": opts, "difficulty": best["difficulty"],
                    "visemes": best["visemes"]})
    return out
