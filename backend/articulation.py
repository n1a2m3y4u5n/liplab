"""
축 E — 조음 원인 진단과 조음 가이드.

독화·웹캠은 '겉으로 보이는' 조음(개구·원순·양순 폐쇄)만 잡는다. 그러나 소리를 가르는
결정적 조음(혀의 위치, 조음 위치·방식)은 입 안에 있어 밖에서는 보이지 않는다. 계획서 E는
이 '보이지 않는 조음'을 가르치고, 관찰 가능한 차원은 목표와 비교해 "혀를 조금 더 앞으로"
같은 교정 방향을 제시한다. 점수만으로는 무엇을 어떻게 고칠지 모른다는 문제를 메운다.

이 모듈은 음소/비심을 조음 자질로 바꾸는 순수 함수다(DB·모델 비의존 → 결정론적 테스트 가능).
  · articulation_target(viseme): 목표 조음 파라미터 + 보이지 않는 내부 조음 교육문
  · articulation_correction(viseme, observed): 관찰 차원(jaw/round/close) 목표 대비 교정
  · articulation_guide(text): 문장을 음절·자모로 풀어 음소별 조음 가이드

실제 음성·영상 AAI(조음 역추정)는 관찰 불가 차원(혀)의 추정치를 이 함수들에 공급할 수 있으나,
현재는 신뢰 가능한 관찰 차원(웹캠 jaw/round/close)만으로 교정이 성립하도록 설계했다.
정직: 혀는 사용자에게서 관찰하는 대신 '목표 조음을 교육'한다(관찰 불가 차원의 과신 방지).
"""
from typing import Dict, List, Optional

import engine

# 비심(viseme) → 조음 자질.
#   place   : 조음 위치(양순/치경/경구개/연구개/성문/모음)
#   manner  : 조음 방식(파열·비음·마찰·유음·모음·활음)
#   tip     : 혀끝 들림(0~1)          back : 혀 뒤 들림(0~1)
#   round   : 입술 원순(0~1)          jaw  : 개구도(0~1)
#   close   : 양순 폐쇄(0~1)          nasal: 비음 여부
#   guide   : 밖에서 안 보이는 조음을 가르치는 한 줄(혀·조음 위치·방식 중심)
_ART: Dict[int, Dict] = {
    1:  {"place": "양순", "manner": "파열·비음", "tip": 0.0, "back": 0.0, "round": 0.0, "jaw": 0.05, "close": 1.0,
         "guide": "두 입술을 붙입니다. ㅂ·ㅃ·ㅍ은 떼면서 터뜨리고(ㅍ은 숨을 세게, ㅃ은 목에 힘을 주고 짧게), ㅁ은 붙인 채 "
                  "코로 울립니다. 받침에서는 입술을 붙인 채 멈춥니다."},
    2:  {"place": "모음", "manner": "저모음", "tip": 0.0, "back": 0.0, "round": 0.0, "jaw": 0.92, "close": 0.0,
         "guide": "입을 크게 벌리고 혀를 낮고 가운데에 둡니다."},
    3:  {"place": "모음", "manner": "전설고모음", "tip": 0.3, "back": 0.0, "round": 0.0, "jaw": 0.16, "close": 0.0,
         "guide": "입을 옆으로 벌리고 혀를 앞·위로 올립니다."},
    4:  {"place": "모음", "manner": "후설원순모음", "tip": 0.0, "back": 0.6, "round": 0.9, "jaw": 0.2, "close": 0.0,
         "guide": "입술을 둥글게 오므리고 혀를 뒤로 당깁니다."},
    5:  {"place": "모음", "manner": "중설모음", "tip": 0.0, "back": 0.2, "round": 0.0, "jaw": 0.44, "close": 0.0,
         "guide": "입을 조금만 벌리고 혀를 가운데 편평하게 둡니다."},
    6:  {"place": "치경", "manner": "파열·비음·유음·마찰", "tip": 0.95, "back": 0.0, "round": 0.0, "jaw": 0.24, "close": 0.0,
         "guide": "혀끝을 윗니 뒤 잇몸 쪽으로 올립니다. ㄷ·ㄸ·ㅌ은 댔다 떼며 터뜨리고(ㅌ은 숨을 세게), ㄴ은 댄 채 코로 "
                  "울리고, ㅅ·ㅆ은 닿지 않게 좁은 틈으로 바람을 내보내고, ㄹ은 가볍게 한 번 튕깁니다(받침 ㄹ은 댄 채 혀 "
                  "양옆으로 소리를 흘립니다)."},
    7:  {"place": "연구개", "manner": "파열·비음", "tip": 0.0, "back": 0.85, "round": 0.0, "jaw": 0.24, "close": 0.0,
         "guide": "혀 뒤를 입천장 안쪽(연구개)에 붙입니다. ㄱ·ㄲ·ㅋ은 떼면서 터뜨리고(ㅋ은 숨을 세게), 받침 ㅇ은 붙인 "
                  "채 코로 울립니다. 첫소리 ㅇ은 소리가 없어 모음부터 냅니다."},
    8:  {"place": "성문", "manner": "마찰", "tip": 0.0, "back": 0.0, "round": 0.0, "jaw": 0.30, "close": 0.0,
         "guide": "목(성문)에서 바람을 내보냅니다. 입·혀는 뒤따르는 모음 모양을 미리 잡습니다."},
    9:  {"place": "모음", "manner": "이중모음", "tip": 0.0, "back": 0.3, "round": 0.55, "jaw": 0.34, "close": 0.0,
         "guide": "두 모음을 이어 입·혀 모양을 미끄러지듯 바꿉니다."},
    10: {"place": "경구개", "manner": "파찰", "tip": 0.4, "back": 0.0, "round": 0.0, "jaw": 0.16, "close": 0.0,
         "guide": "혓바닥 앞쪽을 센입천장(경구개) 앞에 붙였다 떼며 바람을 스치듯 냅니다. ㅊ은 숨을 세게, ㅉ은 목에 힘을 "
                  "주고 짧고 단단하게 냅니다."},
    11: {"place": "양순", "manner": "파열·비음", "tip": 0.0, "back": 0.0, "round": 0.0, "jaw": 0.05, "close": 0.92,
         "guide": "두 입술을 붙입니다(양순)."},
    12: {"place": "치경", "manner": "파열·비음·유음", "tip": 0.7, "back": 0.0, "round": 0.0, "jaw": 0.22, "close": 0.0,
         "guide": "혀끝을 윗잇몸에 댑니다(치경)."},
    13: {"place": "연구개", "manner": "파열·비음", "tip": 0.0, "back": 0.55, "round": 0.0, "jaw": 0.20, "close": 0.0,
         "guide": "혀 뒤를 연구개에 붙입니다."},
    14: {"place": "중립", "manner": "휴지", "tip": 0.0, "back": 0.0, "round": 0.0, "jaw": 0.04, "close": 0.0,
         "guide": "입과 혀를 편히 둡니다."},
    15: {"place": "중립", "manner": "휴지", "tip": 0.0, "back": 0.0, "round": 0.0, "jaw": 0.02, "close": 0.0,
         "guide": "입과 혀를 편히 둡니다."},
}

# 자모별 내부 조음. 한 입모양 무리 안에서도 방식이 다르다(터뜨림·코 울림·마찰·튕김, 예사·거센·된소리). 무리 문장 하나를
# 모든 자모에 붙이면 ㅁ도 '터뜨립니다', ㅅ도 '잇몸에 댔다 뗍니다', 받침 ㄱ·ㄷ·ㅂ도 '떼며 터뜨린다'가 됐다.
# (첫소리, 받침) 문장. 받침 파열음은 터뜨리지 않고 멈춘다(불파). 코 울림 안내는 articulation_guide가 붙인다.
_JAMO_GUIDE: Dict[str, tuple] = {
    "ㅂ": ("두 입술을 붙였다 떼며 가볍게 터뜨립니다.", "두 입술을 붙인 채 멈춥니다(터뜨리지 않습니다)."),
    "ㅃ": ("목과 입술에 힘을 주고 두 입술을 붙였다 짧고 단단하게 뗍니다.", None),
    "ㅍ": ("두 입술을 붙였다 떼며 숨을 세게 터뜨립니다.", "두 입술을 붙인 채 멈춥니다(받침 ㅍ은 ㅂ처럼 납니다)."),
    "ㅁ": ("두 입술을 붙인 채 소리를 내다가 입술을 뗍니다.", "두 입술을 붙인 채 끝냅니다."),
    "ㄷ": ("혀끝을 윗잇몸에 댔다 떼며 가볍게 터뜨립니다.", "혀끝을 윗잇몸에 댄 채 멈춥니다(터뜨리지 않습니다)."),
    "ㄸ": ("혀와 목에 힘을 주고 혀끝을 윗잇몸에 댔다 짧고 단단하게 뗍니다.", None),
    "ㅌ": ("혀끝을 윗잇몸에 댔다 떼며 숨을 세게 터뜨립니다.", "혀끝을 윗잇몸에 댄 채 멈춥니다(받침 ㅌ은 ㄷ처럼 납니다)."),
    "ㄴ": ("혀끝을 윗잇몸에 댄 채 소리를 내다가 뗍니다.", "혀끝을 윗잇몸에 댄 채 끝냅니다."),
    "ㄹ": ("혀끝으로 윗잇몸을 가볍게 한 번 튕깁니다.", "혀끝을 윗잇몸에 댄 채 혀 양옆으로 소리를 흘립니다."),
    "ㅅ": ("혀끝을 윗잇몸 가까이 올리되 닿지 않게 하고, 좁은 틈으로 바람을 내보냅니다.",
          "혀끝을 윗잇몸에 댄 채 멈춥니다(받침 ㅅ은 ㄷ처럼 납니다)."),
    "ㅆ": ("ㅅ 자리에서 혀와 목에 힘을 주고 바람을 더 세게 내보냅니다.", "혀끝을 윗잇몸에 댄 채 멈춥니다(받침 ㅆ은 ㄷ처럼 납니다)."),
    "ㅈ": ("혓바닥 앞쪽을 센입천장 앞에 붙였다 떼며 바람을 스치듯 냅니다.", "혀끝을 윗잇몸에 댄 채 멈춥니다(받침 ㅈ은 ㄷ처럼 납니다)."),
    "ㅉ": ("ㅈ 자리에서 혀와 목에 힘을 주고 짧고 단단하게 냅니다.", None),
    "ㅊ": ("ㅈ 자리에서 떼며 숨을 세게 내보냅니다.", "혀끝을 윗잇몸에 댄 채 멈춥니다(받침 ㅊ은 ㄷ처럼 납니다)."),
    "ㄱ": ("혀 뒤를 여린입천장에 붙였다 떼며 가볍게 터뜨립니다.", "혀 뒤를 여린입천장에 붙인 채 멈춥니다(터뜨리지 않습니다)."),
    "ㄲ": ("혀 뒤와 목에 힘을 주고 여린입천장에 붙였다 짧고 단단하게 뗍니다.",
          "혀 뒤를 여린입천장에 붙인 채 멈춥니다(받침 ㄲ은 ㄱ처럼 납니다)."),
    "ㅋ": ("혀 뒤를 여린입천장에 붙였다 떼며 숨을 세게 터뜨립니다.", "혀 뒤를 여린입천장에 붙인 채 멈춥니다(받침 ㅋ은 ㄱ처럼 납니다)."),
    "ㅇ": (None, "혀 뒤를 여린입천장에 붙인 채 끝냅니다."),
    "ㅎ": ("목(성문)에서 바람을 내보냅니다. 입·혀는 뒤따르는 모음 모양을 미리 잡습니다.",
          "받침 ㅎ은 소리가 거의 나지 않고 뒤 소리를 거세게 만듭니다(좋다→조타)."),
}


def _jamo_guide(jamo: str, position: str, linked: bool) -> Optional[str]:
    """자모 하나의 내부 조음 문장. linked: 받침 뒤에 모음으로 시작하는 음절이 붙어 받침이 다음 첫소리로 넘어감(연음)."""
    g = _JAMO_GUIDE.get(jamo)
    if not g:
        return None
    first, final = g
    if position == "초성":
        return first
    if linked and jamo == "ㅎ":
        return "받침 ㅎ은 모음 앞에서 소리 나지 않습니다(좋아→조아)."
    if linked and first and jamo != "ㅇ":
        return "뒤 모음에 이어 첫소리로 냅니다. " + first
    return final


# 실제 비음 자모(코로 울림). 비심(그룹) 단위가 아니라 자모 단위로 판정해야 정확하다
# (예: 비심7 ㄱㄲㅋㅇ 중 받침 ㅇ만 비음, ㄱ은 아님).
NASAL_JAMO = frozenset({"ㅁ", "ㄴ", "ㅇ"})

def jamo_tip(jamo: str) -> Optional[str]:
    """자모 하나(첫소리 자음 또는 모음)를 내는 법 한 문장. 말하기 코칭의 규칙 폴백과 LLM 참고용. 모르면 None."""
    g = _JAMO_GUIDE.get(jamo)
    if g and g[0]:
        return g[0] + (" 코로 울림을 함께 냅니다." if jamo in NASAL_JAMO else "")
    v = engine.VISEME_MAP.get(jamo)
    return _ART[v]["guide"] if v in (2, 3, 4, 5, 9) and not g else None


# 관찰 가능한 차원(웹캠 역추정 대상). 혀(tip·back)는 밖에서 안 보여 관찰 차원에서 제외한다.
OBSERVABLE = ("jaw", "round", "close")
# 교정 문구(관찰 차원, 방향별). gap>0=부족(더), gap<0=과함(덜).
_CORR = {
    "jaw":   ("입을 더 벌리세요", "입을 덜 벌리세요"),
    "round": ("입술을 더 둥글게 오므리세요", "입술 오므림을 푸세요"),
    "close": ("두 입술을 더 붙이세요", "입술을 살짝 떼세요"),
}
_MIN_GAP = 0.18  # 이 이상 벌어져야 교정 대상(미세 차이는 넘어감)


def _norm_viseme(viseme: Optional[int]) -> int:
    try:
        v = int(viseme)
    except (TypeError, ValueError):
        return 15
    return v if v in _ART else 15


def articulation_target(viseme: int) -> Dict:
    """비심의 목표 조음 파라미터 + 보이지 않는 내부 조음 교육문."""
    v = _norm_viseme(viseme)
    a = _ART[v]
    return {
        "viseme": v,
        "place": a["place"],
        "manner": a["manner"],
        "params": {"tip": a["tip"], "back": a["back"], "round": a["round"], "jaw": a["jaw"], "close": a["close"]},
        "hidden_guide": a["guide"],          # 독화·웹캠으로 안 보이는 조음(혀·위치·방식) 교육
        "nasal": "비음" in a["manner"],
    }


def articulation_correction(viseme: int, observed: Dict[str, float]) -> Dict:
    """관찰 차원(jaw/round/close)을 목표와 비교해 교정 방향을 낸다.
    observed: 웹캠 역추정 {jaw, round, close} (0~1). 가장 크게 어긋난 한 차원을 우선 코칭한다."""
    v = _norm_viseme(viseme)
    tgt = _ART[v]
    gaps = articulation_gaps(v, observed)
    cues: List[Dict] = []
    for dim, gap in gaps.items():
        if abs(gap) >= _MIN_GAP:
            text = _CORR[dim][0] if gap > 0 else _CORR[dim][1]
            cues.append({"dim": dim, "gap": gap, "text": text})
    cues.sort(key=lambda c: -abs(c["gap"]))
    return {
        "viseme": v,
        "ok": len(cues) == 0,
        "primary": cues[0]["text"] if cues else "좋아요, 그대로 유지하세요.",
        "cues": cues,
        "gaps": gaps,                                  # 차원별 목표−관찰(교정 전후 오차 기록용, E-9)
        "error": round(sum(abs(g) for g in gaps.values()) / len(gaps), 3),   # 평균 |차이|
        "hidden_guide": tgt["guide"],  # 관찰로는 안 잡히는 혀·조음은 항상 함께 안내
    }


def articulation_gaps(viseme: int, observed: Dict[str, float]) -> Dict[str, float]:
    """관찰 차원별 목표−관찰 차이(양수 = 부족, 음수 = 과함). 비수치 관측값은 0으로 본다."""
    tgt = _ART[_norm_viseme(viseme)]
    out: Dict[str, float] = {}
    for dim in OBSERVABLE:
        try:
            o = float((observed or {}).get(dim, 0.0) or 0.0)
        except (TypeError, ValueError):
            o = 0.0
        out[dim] = round(float(tgt.get(dim, 0.0)) - o, 3)
    return out


def summarize_sessions(rows: List[Dict]) -> Dict:
    """웹캠 교정 세션 기록(E-9) → 세션 처음·끝의 평균 |차이|와 비심별 요약.

    rows: [{viseme_id, gap_start, gap_end, created_at}] (시간순이 아니어도 된다).
    오차는 관찰 차원(개구·원순·폐쇄) 평균 |목표−관찰|이라 0에 가까울수록 목표와 가깝다.
    """
    ok = [r for r in rows if r.get("gap_start") is not None and r.get("gap_end") is not None]
    if not ok:
        return {"sessions": 0, "gap_start": None, "gap_end": None, "change": None, "by_viseme": []}

    def mean(xs):
        return round(sum(xs) / len(xs), 3)

    by: Dict[int, List[Dict]] = {}
    for r in ok:
        by.setdefault(int(r["viseme_id"]), []).append(r)
    by_viseme = []
    for v, rs in sorted(by.items()):
        s, e = mean([r["gap_start"] for r in rs]), mean([r["gap_end"] for r in rs])
        by_viseme.append({"viseme_id": v, "sessions": len(rs), "gap_start": s, "gap_end": e,
                          "change": round(e - s, 3)})
    s, e = mean([r["gap_start"] for r in ok]), mean([r["gap_end"] for r in ok])
    return {"sessions": len(ok), "gap_start": s, "gap_end": e, "change": round(e - s, 3),
            "by_viseme": by_viseme}


def _jamo_sequence(char: str) -> List[Dict]:
    """한 음절 → [{jamo, position, viseme}] (무음 초성 ㅇ 제외)."""
    cho, jung, jong = engine.decompose_hangul(char)
    # 겹받침(ㄳㄺㄻㅄ 등)은 VISEME_MAP에 없어 그대로 두면 종성이 통째로 누락된다.
    # 발음되는 대표음으로 정규화한다(ㅄ→ㅂ, ㄺ→ㄱ, ㄻ→ㅁ). 다른 파이프라인(word_visemes)과 일치.
    jong = engine.DOUBLE_FINAL.get(jong, jong)
    out = []
    for jamo, pos in ((cho, "초성"), (jung, "중성"), (jong, "종성")):
        if not jamo:
            continue
        if pos == "초성" and jamo == "ㅇ":  # 무음 초성 ㅇ (소리 없음)
            continue
        vid = engine.VISEME_MAP.get(jamo)
        if vid is None:
            continue
        out.append({"jamo": jamo, "position": pos, "viseme": vid})
    return out


def articulation_guide(text: str) -> Dict:
    """문장을 음절·자모로 풀어 음소별 조음 가이드를 만든다(축 E 교구 콘텐츠).
    각 자모에 목표 조음 파라미터·조음 위치·방식·내부 조음 교육문을 담는다."""
    syllables = []
    for i, ch in enumerate(text):
        if not ("가" <= ch <= "힣"):
            continue
        nxt = text[i + 1] if i + 1 < len(text) else ""
        linked = "가" <= nxt <= "힣" and engine.decompose_hangul(nxt)[0] == "ㅇ"   # 옷이→[오시]
        items = []
        for j in _jamo_sequence(ch):
            tgt = articulation_target(j["viseme"])
            # 비음은 비심(그룹)이 아니라 이 자모 자체가 비음인지로 판정한다.
            is_nasal = j["jamo"] in NASAL_JAMO
            base = _jamo_guide(j["jamo"], j["position"], linked) or tgt["hidden_guide"]
            guide = base + (" 코로 울림을 함께 냅니다." if is_nasal else "")
            items.append({
                "jamo": j["jamo"], "position": j["position"], "viseme": j["viseme"],
                "place": tgt["place"], "manner": tgt["manner"],
                "guide": guide, "params": tgt["params"], "nasal": is_nasal,
            })
        if items:
            syllables.append({"syllable": ch, "jamo": items})
    return {"text": text, "syllables": syllables, "n_syllables": len(syllables)}
