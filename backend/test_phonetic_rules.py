"""
발음 규칙 검증 — 축 A(CTC 학습 라벨)의 선결 과제.

engine.to_pronounced_syllables()는 원래 '입모양(viseme)을 바꾸는 규칙'만 구현했다.
그 판단은 viseme 경로에서는 옳지만(비음화 ㄱ→ㅇ은 둘 다 viseme 7, 경음화도 전부 동일 그룹),
음향 모델의 CTC 라벨은 '실제 소리'와 일치해야 하므로 phonetic=True 모드가 필요하다.
라벨이 발음과 어긋나면 학습이 통째로 오염된다.

이 테스트가 지키는 두 가지:
  1) phonetic=True가 평파열음화·유음화·비음화·경음화를 규칙 순서대로 적용한다
  2) phonetic=False(기본)는 기존 viseme 경로와 **완전히 동일**하다 — 앱 회귀 방지

실행: PYTHONPATH=. python3 test_phonetic_rules.py
"""
from engine import to_pronounced_syllables

_ONS = list('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ')
_NUC = list('ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ')
_COD = [''] + list('ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _compose(tokens):
    """[초,중,종] 열을 완성형 음절로 되돌린다(검증 가독성용). 무음 초성은 ㅇ으로 복원."""
    out = []
    for t in tokens:
        if not isinstance(t, list):
            out.append(t)
            continue
        out.append(chr(0xAC00 + _ONS.index(t[0] or 'ㅇ') * 588
                       + _NUC.index(t[1]) * 28 + _COD.index(t[2])))
    return ''.join(out)


def _say(text, phonetic=True):
    return _compose(to_pronounced_syllables(text, phonetic=phonetic))


def test_coda_neutralization():
    """평파열음화(8항) — 종성은 7개 대표음으로만 발음된다."""
    for src, exp in [('옷', '옫'), ('꽃', '꼳'), ('앞', '압'), ('밖', '박'), ('솥', '솓')]:
        _ok(_say(src) == exp, f"{src} → {exp} (얻은 값 {_say(src)})")


def test_nasalization():
    """비음화(18항) — 대표음 ㄱ·ㄷ·ㅂ이 ㄴ·ㅁ 앞에서 같은 조음위치 비음으로."""
    for src, exp in [('국물', '궁물'), ('닫는', '단는'), ('밥물', '밤물')]:
        _ok(_say(src) == exp, f"{src} → {exp} (얻은 값 {_say(src)})")
    # 평파열음화가 먼저 걸려야 성립하는 연쇄 (밭만 → 받만 → 반만)
    _ok(_say('밭만') == '반만', f"밭만 → 반만 (얻은 값 {_say('밭만')})")


def test_lateralization_and_l_nasalization():
    """유음화(20항)와 ㄹ의 비음화(19항). 적용 순서가 어긋나면 연쇄가 깨진다."""
    _ok(_say('신라') == '실라', f"신라 → 실라 (얻은 값 {_say('신라')})")
    _ok(_say('설날') == '설랄', f"설날 → 설랄 (얻은 값 {_say('설날')})")
    _ok(_say('종로') == '종노', f"종로 → 종노 (얻은 값 {_say('종로')})")
    # ㄹ 비음화가 자음 비음화보다 먼저 돌아야 한다: 백리 → 백니 → 뱅니
    _ok(_say('백리') == '뱅니', f"백리 → 뱅니 (얻은 값 {_say('백리')})")


def test_tensification():
    """경음화(23항) — 대표음 ㄱ·ㄷ·ㅂ 뒤 평음이 된소리로."""
    _ok(_say('학교') == '학꾜', f"학교 → 학꾜 (얻은 값 {_say('학교')})")
    _ok(_say('있다') == '읻따', f"있다 → 읻따 (얻은 값 {_say('있다')})")
    # 연음 → 평파열음화 → 경음화 3단 연쇄
    _ok(_say('먹었다') == '머걷따', f"먹었다 → 머걷따 (얻은 값 {_say('먹었다')})")


def test_default_path_unchanged():
    """phonetic=False는 기존 viseme 경로 그대로 — 앱 동작이 바뀌면 안 된다."""
    expected = {
        '안녕하세요': '안녕하세요', '밥을': '바블', '굳이': '구지', '같이': '가치',
        '좋다': '조타', '입학': '이팍', '닭이': '달기', '값': '갑',
        '강아지': '강아지', '붙여': '부쳐', '많다': '만타', '국화': '구콰',
        # 기본 경로에서는 아래 규칙들이 적용되지 않아야 한다(의도된 생략)
        '국물': '국물', '학교': '학교', '옷': '옷', '신라': '신라',
    }
    for src, exp in expected.items():
        got = _say(src, phonetic=False)
        _ok(got == exp, f"기본 경로 {src} → {exp} 여야 함 (얻은 값 {got})")


def test_non_hangul_passthrough():
    """공백·문장부호는 원문 그대로 유지되고, 그 경계를 넘어 규칙이 걸리지 않는다."""
    _ok(_say('밥 먹자') == '밥 먹짜', f"공백 경계 유지 (얻은 값 {_say('밥 먹자')})")
    _ok(_say('좋다!') == '조타!', f"문장부호 유지 (얻은 값 {_say('좋다!')})")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
