"""
목표 자모열 오염 검증 — 과신 측정 실험(E3)의 선행 조건.

오염이 잘못되면 실험 전체가 무의미해진다. 특히 두 가지가 치명적이다:
  · 특수토큰(어절경계 `|`)을 건드리면 강제정렬 제약이 깨져 구간 자체가 달라진다
  · 오염이 실제로 아무것도 안 바꿨는데 바꿨다고 착각하면 '정답열 vs 오염열' 비교가
    같은 것끼리 비교하는 셈이 된다

전부 순수 함수라 모델 없이 결정론적으로 검증된다.

실행: PYTHONPATH=. python test_jamo_perturb.py
"""
import jamo_perturb as P
import jamo_vocab as V


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


SENT = "학교에서 국물을 먹었습니다"


def test_rules_produce_valid_vocab_tokens():
    """오염 결과가 vocab에 없는 토큰을 만들면 정렬 단계에서 KeyError로 죽는다."""
    tokens = V.text_to_tokens(SENT)
    for rule in P.RULES:
        out = P.perturb(tokens, rule)
        unknown = [t for t in out if t not in V.VOCAB]
        _ok(not unknown, f"{rule}: vocab에 없는 토큰 생성 {unknown}")


def test_special_tokens_are_never_touched():
    """어절경계는 정렬을 제약한다 — 건드리면 구간이 달라져 비교가 오염된다."""
    tokens = V.text_to_tokens(SENT)
    n_delim = tokens.count(V.WORD_DELIM)
    _ok(n_delim > 0, "이 문장에는 어절경계가 있어야 테스트가 성립")
    for rule in P.RULES:
        out = P.perturb(tokens, rule)
        _ok(out.count(V.WORD_DELIM) == n_delim,
            f"{rule}: 어절경계 개수가 바뀌었다 ({out.count(V.WORD_DELIM)} != {n_delim})")


def test_coda_deletion_removes_only_codas():
    tokens = V.text_to_tokens(SENT)
    codas = [t for t in tokens if t.startswith("c:")]
    _ok(codas, "이 문장에는 종성이 있어야 함")
    out = P.perturb(tokens, "coda_deletion")
    _ok(not [t for t in out if t.startswith("c:")], "종성이 전부 사라져야 함")
    _ok(len(out) == len(tokens) - len(codas),
        f"길이가 종성 수만큼 줄어야 함 ({len(out)} vs {len(tokens) - len(codas)})")
    # 초성·중성은 그대로여야 한다.
    _ok([t for t in out] == [t for t in tokens if not t.startswith("c:")],
        "종성 외에는 손대면 안 됨")


def test_fricative_stopping_maps_expected_pairs():
    out = P.perturb(["o:ㅅ", "n:ㅏ", "o:ㅈ", "c:ㄱ"], "fricative_stopping")
    _ok(out == ["o:ㄷ", "n:ㅏ", "o:ㄷ", "c:ㄱ"], f"ㅅ·ㅈ → ㄷ 여야 함 — 받음 {out}")


def test_nasalization_maps_expected_pairs():
    out = P.perturb(["o:ㅂ", "n:ㅏ", "o:ㄷ"], "nasalization")
    _ok(out == ["o:ㅁ", "n:ㅏ", "o:ㄴ"], f"ㅂ→ㅁ, ㄷ→ㄴ 여야 함 — 받음 {out}")


def test_vowel_centralization_pulls_toward_center():
    out = P.perturb(["n:ㅣ", "n:ㅜ", "n:ㅏ"], "vowel_centralization")
    _ok(out[0] == "n:ㅡ" and out[1] == "n:ㅡ", f"전설·고모음이 ㅡ로 — 받음 {out}")
    _ok(out[2] == "n:ㅏ", "이미 중설·저모음인 ㅏ는 그대로")


def test_perturbation_actually_changes_something():
    """
    '오염했는데 원본과 같다'면 그 표본은 실험에서 빼야 한다.
    report의 usable 플래그가 그 판정을 준다.
    """
    tokens = V.text_to_tokens(SENT)
    for rule in P.RULES:
        rep = P.perturbation_report(tokens, rule)
        _ok(rep["usable"], f"{rule}: 이 문장에서 아무것도 안 바뀌었다")
        _ok(rep["changed"] > 0, f"{rule}: changed가 0")
    # 규칙이 적용될 데가 없는 입력에서는 usable=False 여야 한다.
    rep = P.perturbation_report(["n:ㅏ", "n:ㅏ"], "coda_deletion")
    _ok(not rep["usable"], "종성이 없으면 coda_deletion은 usable=False")


def test_rate_is_deterministic_with_seed():
    """같은 시드면 같은 오염 — 실험 재현성의 전제."""
    import random
    tokens = V.text_to_tokens(SENT)
    a = P.perturb(tokens, "vowel_centralization", rate=0.5, rng=random.Random(1))
    b = P.perturb(tokens, "vowel_centralization", rate=0.5, rng=random.Random(1))
    c = P.perturb(tokens, "vowel_centralization", rate=1.0)
    _ok(a == b, "같은 시드는 같은 결과")
    _ok(a != c, "rate 0.5와 1.0은 달라야 함")


def test_unknown_rule_raises():
    try:
        P.perturb(["n:ㅏ"], "그런규칙없음")
        _ok(False, "없는 규칙은 KeyError여야 함")
    except KeyError:
        pass


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
