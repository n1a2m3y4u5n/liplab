"""소리별 음소 피드백 신뢰도(S2, docs/phoneme-feedback-reliability-2026-10.md): 표 읽기, 끝 음절 참고, 코칭이 믿을 만한 소리만 짚기."""
import json

import main
import phone_reliability as PR


def _table(tmp_path, reliable):
    p = tmp_path / "phone_reliability.json"
    p.write_text(json.dumps({"version": "test", "reliable": reliable, "sounds": {}}, ensure_ascii=False), encoding="utf-8")
    PR.load_table.cache_clear()
    return str(p)


def _ph(tok, dgop, **kw):
    return {"token": tok, "aligned": True, "scorable": tok != "|", "dgop": dgop, "naive": dgop, **kw}


def test_no_table_leaves_phones_untouched(tmp_path):
    PR.load_table.cache_clear()
    phones = [_ph("o:ㄱ", 0.9), _ph("n:ㅏ", 0.2)]
    assert PR.annotate(phones, path=str(tmp_path / "없음.json")) is False
    assert all("reliable" not in p for p in phones)


def test_broken_table_is_ignored(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    PR.load_table.cache_clear()
    assert PR.load_table(str(p)) is None
    p2 = tmp_path / "noreliable.json"
    p2.write_text(json.dumps({"sounds": {}}), encoding="utf-8")
    assert PR.load_table(str(p2)) is None


def test_final_syllable_start():
    # 가방 → o:ㄱ n:ㅏ o:ㅂ n:ㅏ c:ㅇ : 끝 음절은 o:ㅂ부터
    assert PR.final_syllable_start(["o:ㄱ", "n:ㅏ", "o:ㅂ", "n:ㅏ", "c:ㅇ"]) == 2
    # 아이 → n:ㅏ n:ㅣ : 끝 음절은 마지막 중성(앞에 초성 없음)
    assert PR.final_syllable_start(["n:ㅏ", "n:ㅣ"]) == 1
    assert PR.final_syllable_start(["|"]) == 1


def test_annotate_marks_reliable_and_keeps_final_syllable_reference(tmp_path):
    path = _table(tmp_path, ["o:ㄱ", "n:ㅏ", "c:ㅇ", "o:ㅂ"])
    # 가 방 가방 → 마지막 '방'(o:ㅂ n:ㅏ c:ㅇ)은 표에 있어도 참고
    phones = [_ph("o:ㄱ", 0.9), _ph("n:ㅏ", 0.8), _ph("|", 0.9), _ph("o:ㅂ", 0.1), _ph("n:ㅓ", 0.1),
              _ph("o:ㅂ", 0.2), _ph("n:ㅏ", 0.2), _ph("c:ㅇ", 0.2)]
    assert PR.annotate(phones, path=path) is True
    assert [p["reliable"] for p in phones] == [True, True, False, True, False, False, False, False]


def test_annotate_never_marks_silent_h_or_unaligned(tmp_path):
    path = _table(tmp_path, ["o:ㅎ", "o:ㄴ"])
    phones = [_ph("o:ㅎ", 0.1, silent_h=True), {"token": "o:ㄴ", "aligned": False, "scorable": True}, _ph("n:ㅣ", 0.9)]
    PR.annotate(phones, path=path)
    assert [p["reliable"] for p in phones] == [False, False, False]


def test_weak_phones_only_reliable_when_annotated():
    phones = [_ph("o:ㄱ", 0.02, reliable=False), _ph("n:ㅏ", 0.9, reliable=True), _ph("o:ㄴ", 0.05, reliable=True),
              _ph("n:ㅣ", 0.95, reliable=True)]
    weak = main._weak_phones({"phones": phones})
    assert [w["label"] for w in weak] == ["ㄴ"]          # 가장 낮은 ㄱ은 참고 소리라 짚지 않는다
    # 믿을 만한 소리가 모두 높으면 약한 소리를 짚지 않는다
    phones2 = [_ph("o:ㄱ", 0.02, reliable=False), _ph("n:ㅏ", 0.9, reliable=True)]
    assert main._weak_phones({"phones": phones2}) == []


def test_weak_phones_unchanged_without_reliability_keys():
    phones = [_ph("o:ㄱ", 0.02), _ph("n:ㅏ", 0.9)]
    assert [w["label"] for w in main._weak_phones({"phones": phones})] == ["ㄱ"]


def test_shipped_table_if_present_is_aggregate_only():
    """저장소에 표가 있으면 집계값만 있어야 한다(문장·음소별 원자료 없음), 끝 음절은 참고."""
    PR.load_table.cache_clear()
    t = PR.load_table()
    if t is None:
        return
    assert t.get("final_syllable") == "reference"
    import jamo_vocab
    for tok in t["reliable"]:
        assert tok in jamo_vocab.VOCAB and jamo_vocab.is_scorable(tok)
        assert t["sounds"][tok]["reliable"] is True
    for tok, row in t["sounds"].items():
        assert set(row) <= {"reliable", "auc", "auc_ci", "false_red", "n_pos", "n_neg", "kappa", "retest_agree", "n_retest"}
