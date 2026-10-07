"""
3단계 문장 주관식의 자음 피드백(계획 C9, docs/master-plan-2026-10.md).

정답 문장을 바로 보이는 대신, 첫 답과 정답을 낱말 단위로 맞춰 맞힌 낱말은 그대로 보이고 틀린 낱말은 음절마다 첫소리 자음만
보인다. 학습자는 이 단서를 보고 입모양을 다시 본 뒤 한 번 더 답한다. 근거: 문장 독화 훈련에서 정답 문장을 보이는 피드백은
효과가 없었고, 자음을 짚는 피드백은 소음 속 시청각 문장 인식까지 옮겨 갔다(Bernstein, Auer, Eberhardt 2022, Am J Audiol 31(1)).

순수 함수만 둔다(DB·네트워크 없음). 낱말 비교는 '소리 나는 대로' 자모열로 해서, 표기만 다른 같은 발음(같이/가치, 국물/궁물,
주세요/주새요)을 맞힌 것으로 본다. 띄어쓰기는 보지 않는다(10/7, 아래 consonant_feedback). 듣기 트랙의 받아쓰기·소음 계단·역치 검사도
이 판정을 쓴다(listen_curriculum.word_score).
"""
import re
import unicodedata
from functools import lru_cache
from typing import Dict, List

from engine import decompose_hangul
from scoring import to_pronounced_jamos

_PUNCT = re.compile(r"[^\w가-힣]+")


def _bare(word: str) -> str:
    """비교용: 문장 부호를 뗀 낱말."""
    return _PUNCT.sub("", word)


def _merge_vowels(jamos) -> List:
    """귀로(입모양으로도) 가리지 못하는 모음 표기를 하나로 모은다. 듣기 받아쓰기는 들은 것을 묻는 과제라, 맞춤법만 다른 답
    (주새요, 학생이예요)을 틀렸다고 하면 역치 검사·소음 계단이 철자 실력까지 재게 된다.
      - ㅐ·ㅔ, ㅒ·ㅖ: 지금 서울말에서 합쳐진 모음(젊은 화자 대부분이 소리로 가르지 못함)
      - ㅙ·ㅚ·ㅞ: 모두 [we](표준 발음법 4항 붙임, ㅚ를 [we]로도 발음)
      - 자음 뒤 ㅖ → ㅔ(5항 다만 2, '례'는 그대로), 모음 뒤 '예' → '에'(이에요·이예요, 의자에요·의자예요의 이음 j는 소리로 가르지 못함)
      - 낱말 첫머리가 아닌 '의' → '이'(5항 다만 4). 자음 뒤 ㅢ는 to_pronounced_jamos가 이미 ㅣ로 바꾼다
    낱말 첫머리의 '예·에', '의·이'는 그대로 둔다(예/에, 의사/이사처럼 소리로 갈린다)."""
    out = []
    for k, (i, m, f) in enumerate(jamos):
        m = {"ㅐ": "ㅔ", "ㅒ": "ㅖ", "ㅙ": "ㅞ", "ㅚ": "ㅞ"}.get(m, m)
        after_vowel = k > 0 and not out[-1][2]
        if m == "ㅖ" and ((i and i != "ㄹ") or (not i and after_vowel)):
            m = "ㅔ"
        elif m == "ㅢ" and (i or k > 0):
            m = "ㅣ"
        out.append((i, m, f))
    return out


_LAX = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}


def _merge_tense_after_l(jamos) -> List:
    """ㄹ 받침 뒤 첫소리의 된소리 표기를 예사소리로 모은다(올게요/올께요, 갈 수/갈쑤). 이 자리의 된소리되기는 낱말 형태(관형형 -ㄹ,
    어미 -ㄹ게, 한자어 ㄹ 뒤 ㄷㅅㅈ)에 따라 정해져 발음 변환(phonetic)이 다 잡지 못한다. 비교 키에만 쓰므로 '갈비'를 '갈삐'로 적은 답도
    맞힌 것이 되지만, 들은 말을 소리 나는 대로 적은 답을 틀렸다고 하는 쪽보다 덜 해롭다고 본다."""
    out = []
    for k, (i, m, f) in enumerate(jamos):
        if k > 0 and out[-1][2] == "ㄹ" and i in _LAX:
            i = _LAX[i]
        out.append((i, m, f))
    return out


@lru_cache(maxsize=4096)
def _sound_key(word: str) -> str:
    """낱말의 '소리 나는 대로' 자모열을 문자열 키로. 발음 변환은 실제 소리 기준(평파열음화·비음화·유음화·경음화, phonetic=True)이고,
    소리로 가르지 못하는 모음 표기와 ㄹ 뒤 된소리 표기는 하나로 모은다. 한글이 없으면 부호를 뗀 원문."""
    bare = _bare(word)
    jamos = _merge_tense_after_l(_merge_vowels(to_pronounced_jamos(bare, phonetic=True)))
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


def _match_words(c_words: List[str], answer: str) -> List[bool]:
    """정답 낱말마다 답에서 찾았는지. 답의 띄어쓰기는 보지 않는다: 공백·부호를 뺀 답 글자열을 순서대로 조각내어, 조각의 소리 키가
    정답 낱말의 키와 같으면 맞힌 것으로 센다(조각과 정답 낱말 모두 홀로 발음한 키). 맞힌 낱말 수가 가장 많아지게 나누는
    동적 계획법이고, 순서가 바뀐 낱말은 세지 않는다(예전 낱말 열 최장 공통 부분열과 같은 원칙).
    예: '내일다시 올께요' → 내일·다시·올게요 모두 맞음(예전에는 0개)."""
    chars = [ch for ch in _bare("".join(answer.split()))]
    n, L = len(c_words), len(chars)
    if not n or not L:
        return [False] * n
    keys = [_sound_key(w) for w in c_words]
    lens = [len(_bare(w)) for w in c_words]
    dp = [[0] * (L + 1) for _ in range(n + 1)]
    back = [[None] * (L + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(0, L + 1):
            best, how = dp[i - 1][j], ("skip_word", None)
            if j > 0 and dp[i][j - 1] > best:
                best, how = dp[i][j - 1], ("skip_char", None)
            # 같은 소리 키면 음절 수도 같으므로 정답 낱말 길이 근처만 본다(숫자·영문이 섞이면 ±1)
            for size in (lens[i - 1], lens[i - 1] - 1, lens[i - 1] + 1):
                k = j - size
                if size <= 0 or k < 0:
                    continue
                if dp[i - 1][k] + 1 > best and _sound_key("".join(chars[k:j])) == keys[i - 1]:
                    best, how = dp[i - 1][k] + 1, ("match", k)
            dp[i][j], back[i][j] = best, how
    hit = [False] * n
    i, j = n, L
    while i > 0:
        kind, k = back[i][j]
        if kind == "match":
            hit[i - 1] = True
            i, j = i - 1, k
        elif kind == "skip_char":
            j -= 1
        else:
            i -= 1
    return hit


_DIGITS = re.compile(r"\d+")


def _number_readings(answer: str) -> List[str]:
    """답에 아라비아 숫자가 있으면 읽는 말로 바꾼 후보들(문맥 읽기, 모두 한자어 수, 모두 고유어 수). 듣기 문장은 숫자를 '삼십 분'처럼
    한글로 적어 두는데 학습자는 '30분'으로 적기 쉽다. '7번'은 번호면 칠 번, 횟수면 일곱 번이라 문맥 읽기만으로는 틀릴 수 있어
    세 후보 가운데 가장 많이 맞는 쪽을 쓴다(정답 쪽은 바꾸지 않는다)."""
    if not _DIGITS.search(answer):
        return [answer]
    from korean_numbers import native, normalize_numbers, sino
    out = [answer]
    try:
        out.append(normalize_numbers(answer))
    except Exception:
        pass
    out.append(_DIGITS.sub(lambda m: sino(int(m.group())) if len(m.group()) <= 15 else m.group(), answer))
    out.append(_DIGITS.sub(lambda m: native(int(m.group())) if len(m.group()) <= 15 else m.group(), answer))
    return out


def consonant_feedback(correct: str, answer: str) -> Dict:
    """정답 문장의 낱말마다 맞혔는지와, 틀린 낱말의 자음 골격을 돌려준다.

    words: [{"text": 맞힌 낱말 원문 또는 None, "correct": bool, "skeleton": 틀린 낱말의 초성 목록 또는 None}]
    맞힌 낱말 판정은 _match_words(띄어쓰기 무시, 순서 유지)다. 답에서 낱말 순서가 바뀐 부분은 맞힌 것으로 세지 않는다.
    """
    correct = unicodedata.normalize("NFC", correct or "").strip()
    answer = unicodedata.normalize("NFC", answer or "").strip()[:400]   # 아주 긴 답은 자른다(계산량)
    c_words = [w for w in correct.split() if _bare(w)]
    hit = max((_match_words(c_words, a) for a in _number_readings(answer)), key=sum)
    words = [
        {"text": w, "correct": True, "skeleton": None} if ok else {"text": None, "correct": False, "skeleton": skeleton(w)}
        for w, ok in zip(c_words, hit)
    ]
    n_ok = sum(hit)
    return {"words": words, "correct_words": n_ok, "total_words": len(c_words)}
