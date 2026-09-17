"""
자모 단위 CTC vocab — 축 A(D-GOP 음향 백본) 학습 라벨.

왜 필요한가. 기존 체크포인트 kresnik/wav2vec2-large-xlsr-korean의 CTC vocab은 **한글 음절
단위 1,205토큰**이라, dgop.py가 설계한 '음소별(초성·중성·종성) D-GOP'가 나오지 않는다
(dgop_acoustic.py 모듈 docstring의 B.6 한계). 어차피 미세조정을 할 거면 encoder는 그대로
두고 lm_head만 이 자모 vocab으로 교체하는 편이 낫다 — 한계가 함께 풀린다.

부수 효과로 1,205 → 49가 되면 D-GOP의 엔트로피 신호 자체가 안정된다. 지금은 롱테일
1,200여 클래스가 normalized_entropy를 지배해 '분포가 평평하다'는 신호가 흐려진다.

위치 구분. 초성 ㄱ(파열)과 종성 ㄱ(미파열 [k̚])은 음향적으로 다른 소리라 별도 토큰으로
둔다. 덕분에 '종성 발음'만 따로 채점할 수 있어 발성 교육(축 A의 최종 목적)에 직결된다.

7종성. 라벨은 engine.to_pronounced_syllables(phonetic=True)를 거치므로 평파열음화가 적용돼
종성이 표준발음법 7종성(ㄱㄴㄷㄹㅁㅂㅇ)으로 수렴한다. 겹받침·ㅅ·ㅊ 등은 vocab에 없다.
초성 ㅇ은 무음이라 토큰을 만들지 않는다(중성만 남는다).
"""
import json
from typing import Dict, List

from scoring import to_pronounced_jamos

PAD = "<pad>"      # CTC blank. wav2vec2 관례상 id 0 — dgop_acoustic.align_targets의 기본 blank_token.
UNK = "<unk>"
WORD_DELIM = "|"   # 어절 경계. 정렬을 제약해 강제정렬 품질을 올린다(D-GOP 채점 대상은 아님).

# 초성 18 — 무음 ㅇ 제외(중성만 남는다).
ONSETS: List[str] = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅈㅉㅊㅋㅌㅍㅎ")
# 중성 21 — 단모음·이중모음 전체.
NUCLEI: List[str] = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
# 종성 7 — 표준발음법 제8항의 대표음. phonetic 모드가 여기로 수렴시킨다.
CODAS: List[str] = list("ㄱㄴㄷㄹㅁㅂㅇ")

_PREFIX = {"onset": "o:", "nucleus": "n:", "coda": "c:"}


def _build_vocab() -> Dict[str, int]:
    tokens = [PAD, UNK, WORD_DELIM]
    tokens += [_PREFIX["onset"] + j for j in ONSETS]
    tokens += [_PREFIX["nucleus"] + j for j in NUCLEI]
    tokens += [_PREFIX["coda"] + j for j in CODAS]
    return {t: i for i, t in enumerate(tokens)}


VOCAB: Dict[str, int] = _build_vocab()
ID_TO_TOKEN: Dict[int, str] = {i: t for t, i in VOCAB.items()}
VOCAB_SIZE: int = len(VOCAB)          # 49
SPECIAL: frozenset = frozenset((PAD, UNK, WORD_DELIM))


def is_scorable(token: str) -> bool:
    """D-GOP 점수 집계 대상인가. 특수토큰(blank·unk·어절경계)은 발음 채점 대상이 아니다."""
    return token not in SPECIAL


def text_to_tokens(text: str) -> List[str]:
    """
    한국어 텍스트 → 자모 CTC 토큰열. 어절 사이에는 WORD_DELIM을 넣는다.

    phonetic=True로 '실제 소리'까지 변환한다(평파열음화·비음화·유음화·경음화).
    라벨이 발음과 어긋나면 학습이 통째로 오염되므로 이 경로를 반드시 거쳐야 한다.
    """
    out: List[str] = []
    for w_i, word in enumerate(text.split()):
        if w_i:
            out.append(WORD_DELIM)
        for onset, nucleus, coda in to_pronounced_jamos(word, phonetic=True):
            if onset:
                out.append(_PREFIX["onset"] + onset)
            out.append(_PREFIX["nucleus"] + nucleus)
            if coda:
                out.append(_PREFIX["coda"] + coda)
    return out


def tokens_to_ids(tokens: List[str]) -> List[int]:
    """토큰열 → id열. vocab에 없는 토큰은 UNK로 떨어진다(학습 전 점검용 — 정상이면 0건)."""
    unk = VOCAB[UNK]
    return [VOCAB.get(t, unk) for t in tokens]


def text_to_ids(text: str) -> List[int]:
    return tokens_to_ids(text_to_tokens(text))


def oov_tokens(text: str) -> List[str]:
    """vocab을 벗어난 토큰 목록. 코퍼스 전체에 대해 비어 있어야 학습을 시작할 수 있다."""
    return [t for t in text_to_tokens(text) if t not in VOCAB]


def save_vocab_json(path: str) -> str:
    """
    HF Wav2Vec2CTCTokenizer가 읽는 vocab.json으로 저장한다.
    학습 스크립트가 tokenizer를 만들 때:
        Wav2Vec2CTCTokenizer(path, unk_token="<unk>", pad_token="<pad>", word_delimiter_token="|")
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(VOCAB, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    print(f"vocab {VOCAB_SIZE}토큰 = 특수 3 + 초성 {len(ONSETS)} + 중성 {len(NUCLEI)} + 종성 {len(CODAS)}")
    for s in ("안녕하세요", "국물 먹었다", "학교 갔다"):
        print(f"  {s!r:<16} → {' '.join(text_to_tokens(s))}")
