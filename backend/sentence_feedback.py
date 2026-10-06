"""
3단계 문장 주관식의 자음 피드백(계획 C9, docs/master-plan-2026-10.md).

정답 문장을 바로 보이는 대신, 첫 답과 정답을 낱말 단위로 맞춰 맞힌 낱말은 그대로 보이고 틀린 낱말은 음절마다 첫소리 자음만
보인다. 학습자는 이 단서를 보고 입모양을 다시 본 뒤 한 번 더 답한다. 근거: 문장 독화 훈련에서 정답 문장을 보이는 피드백은
효과가 없었고, 자음을 짚는 피드백은 소음 속 시청각 문장 인식까지 옮겨 갔다(Bernstein, Auer, Eberhardt 2022, Am J Audiol 31(1)).

순수 함수만 둔다(DB·네트워크 없음). 낱말 비교는 채점과 같이 '소리 나는 대로' 자모열로 해서, 표기만 다른 같은 발음(같이/가치)을
맞힌 것으로 본다.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List

from engine import decompose_hangul
from scoring import to_pronounced_jamos

_PUNCT = re.compile(r"[^\w가-힣]+")


def _bare(word: str) -> str:
    """비교용: 문장 부호를 뗀 낱말."""
    return _PUNCT.sub("", word)


def _sound_key(word: str) -> str:
    """낱말의 '소리 나는 대로' 자모열을 문자열 키로. 한글이 없으면 부호를 뗀 원문."""
    bare = _bare(word)
    jamos = to_pronounced_jamos(bare)
    return "".join(i + m + f for i, m, f in jamos) if jamos else bare


def skeleton(word: str) -> List[str]:
    """음절마다 첫소리 자음(초성). 한글이 아닌 글자(숫자, 영문)는 그대로, 문장 부호는 뺀다.
    받침과 모음은 보이지 않는다(첫소리 ㅇ은 'ㅇ'으로 보인다)."""
    out: List[str] = []
    for ch in _bare(word):
        if "가" <= ch <= "힣":
            out.append(decompose_hangul(ch)[0])
        else:
            out.append(ch)
    return out


def consonant_feedback(correct: str, answer: str) -> Dict:
    """정답 문장의 낱말마다 맞혔는지와, 틀린 낱말의 자음 골격을 돌려준다.

    words: [{"text": 맞힌 낱말 원문 또는 None, "correct": bool, "skeleton": 틀린 낱말의 초성 목록 또는 None}]
    맞힌 낱말 판정은 낱말 열의 최장 공통 부분열(순서 유지)이다. 답에서 낱말 순서가 바뀐 부분은 맞힌 것으로 세지 않는다.
    """
    correct = unicodedata.normalize("NFC", correct or "").strip()
    answer = unicodedata.normalize("NFC", answer or "").strip()
    c_words = [w for w in correct.split() if _bare(w)]
    a_words = [w for w in answer.split() if _bare(w)]
    c_keys = [_sound_key(w) for w in c_words]
    a_keys = [_sound_key(w) for w in a_words]
    hit = [False] * len(c_words)
    if c_words and a_words:
        sm = SequenceMatcher(a=c_keys, b=a_keys, autojunk=False)
        for block in sm.get_matching_blocks():
            for k in range(block.size):
                hit[block.a + k] = True
    words = [
        {"text": w, "correct": True, "skeleton": None} if ok else {"text": None, "correct": False, "skeleton": skeleton(w)}
        for w, ok in zip(c_words, hit)
    ]
    n_ok = sum(hit)
    return {"words": words, "correct_words": n_ok, "total_words": len(c_words)}
