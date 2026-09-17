"""
LIPLAB 시각 증강 오버레이 — 고도화 축 J("안 보이는 소리의 시각 증강").

동구형이음(입모양이 같아 눈으로 구별 안 되는 음소)은 유성·기식·비음처럼 입술 밖으로
드러나지 않는 자질에서 갈린다. 이 모듈은 그 자질에만 대응하는 **최소 시각 기호**를
음소·비심 타임라인 위에 얹을 지점을 규칙으로 계산한다. 기호는 임의로 정하지 않고 조음
자질에 대응시킨다(이중부호화). 프론트가 이 결과를 SVG로 렌더한다.

착안: 큐드 스피치(Cued Speech, Cornett 1967)를 손 대신 화면 기호로 자동 생성하고,
숙달도가 오르면 기호를 소거(페이딩)하는 재해석. 한국어 조음 데이터 없이 규칙만으로 동작한다.

자질↔기호 매핑(입술 밖으로 안 드러나는 자질만; 평음은 기준이라 기호 없음)
  · 격음(ㅋㅌㅍㅊㅎ) → aspirated : 바람(기식)
  · 경음(ㄲㄸㅃㅆㅉ) → tense     : 긴장(힘줌)
  · 비음(ㄴㅁㅇ)     → nasal     : 울림(코울림)
"""
from typing import Dict, List, Optional

from content_rules import _INSIDE_CLUSTER, word_visemes  # noqa: F401 (재사용)
from engine import VISEME_MAP, to_pronounced_syllables

# 안 드러나는 자질 → 기호 종류. 프론트가 종류를 받아 SVG 글리프로 그린다.
CUE_FEATURES: Dict[str, Dict] = {
    "aspirated": {"label": "기식", "hint": "바람이 새어 나오는 소리(ㅋㅌㅍㅊㅎ)"},
    "tense": {"label": "긴장", "hint": "목에 힘을 주어 된소리(ㄲㄸㅃㅆㅉ)"},
    "nasal": {"label": "울림", "hint": "코로 울리는 소리(ㄴㅁㅇ)"},
}

_ASPIRATED = set("ㅋㅌㅍㅊㅎ")
_TENSE = set("ㄲㄸㅃㅆㅉ")
_NASAL = set("ㄴㅁㅇ")

# 시각 기호가 유용한 동구형이음 무리: 양순음(1) + 입 안쪽 자음(6·7·8·10).
# 이 무리 안에서는 입모양이 같아 자질 기호가 있어야 구별된다.
_CUEABLE_VISEMES = {1} | set(_INSIDE_CLUSTER)


def phoneme_cue(phoneme: str) -> Optional[str]:
    """음소의 '안 드러나는 자질' 기호 종류. 평음·유음·모음이면 None(기준, 기호 없음)."""
    if phoneme in _ASPIRATED:
        return "aspirated"
    if phoneme in _TENSE:
        return "tense"
    if phoneme in _NASAL:
        return "nasal"
    return None


def is_cueable(phoneme: str) -> bool:
    """이 자음이 동구형이음 무리에 속해 시각 기호가 구별에 도움이 되는가."""
    return VISEME_MAP.get(phoneme) in _CUEABLE_VISEMES


def generate_cues(text: str, target_visemes: Optional[List[int]] = None,
                  mastery: Optional[Dict[int, float]] = None,
                  fade_threshold: float = 0.85,
                  max_cues: Optional[int] = None) -> List[Dict]:
    """
    텍스트를 '소리 나는 대로' 변환한 음절 타임라인에서 기호를 얹을 지점을 찾는다.

    반환: [{"syllable_index", "position"("initial"|"final"), "phoneme", "viseme", "cue",
            "strength", "priority"}]  (타임라인 순 정렬)
    개인화(소거):
      · target_visemes를 주면 그 표적 음소만 기호를 남긴다(집중 학습).
      · mastery를 주면 숙달도에 따라 기호의 strength(0.2~1.0)를 점진적으로 낮추고,
        fade_threshold 이상이면 완전히 소거한다(이진 컷오프가 아닌 점진 페이딩).
        프론트는 strength를 기호의 opacity로 반영한다.
    표시 우선순위(계획서 J: 난이도지수 C 연동):
      · 각 기호에 priority(안 보이는 정도, 0~1)를 매긴다 — 안 보이는 비심일수록 높다.
      · max_cues를 주면 우선순위 상위 N개만 남겨 기호 과다를 막는다(빈도 감소).
    """
    tv = set(target_visemes) if target_visemes else None
    cues: List[Dict] = []
    for i, tok in enumerate(to_pronounced_syllables(text)):
        if not isinstance(tok, list):
            continue
        ini, _med, fin = tok
        for pos, ph in (("initial", ini), ("final", fin)):
            if not ph or not is_cueable(ph):
                continue
            cue = phoneme_cue(ph)
            if cue is None:
                continue
            vid = VISEME_MAP.get(ph)
            if tv is not None and vid not in tv:
                continue  # 표적 음소만 남김
            strength = 1.0
            if mastery is not None:
                m = mastery.get(vid, 0.0)
                if m >= fade_threshold:
                    continue  # 충분히 숙달 → 기호 완전 소거
                # 숙달도가 오를수록 점진적으로 흐리게(하한 0.2로 완전투명 방지)
                strength = round(max(0.2, 1.0 - m / fade_threshold), 3)
            cues.append({"syllable_index": i, "position": pos,
                         "phoneme": ph, "viseme": vid, "cue": cue,
                         "strength": strength})
    # 표시 우선순위 = 난이도지수(C)의 음소 성분(안 보이는 정도). 안 보이는 비심일수록 우선.
    import perceptual as _perc
    for c in cues:
        c["priority"] = _perc.viseme_invisibility(c["viseme"])
    if max_cues is not None and len(cues) > max_cues:
        keep = set(id(c) for c in sorted(cues, key=lambda c: -c["priority"])[:max_cues])
        cues = [c for c in cues if id(c) in keep]
    # 렌더는 타임라인 순으로(초성 먼저) — priority는 프론트가 강조/정렬에 별도로 쓸 수 있다.
    cues.sort(key=lambda c: (c["syllable_index"], 0 if c["position"] == "initial" else 1))
    return cues
