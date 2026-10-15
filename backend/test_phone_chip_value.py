"""칩 값 보정 E1(docs/phone-tail-2026-10.md): 기본 끔, 켰을 때만 chip이 붙고 문장 점수는 그대로, 표는 E1일 때만."""
import json

import pytest

import phone_chip_value as PCV
import phone_reliability as PR


def test_mode_default_off(monkeypatch):
    monkeypatch.delenv("DGOP_CHIP_VALUE", raising=False)
    assert PCV.mode() is None
    monkeypatch.setenv("DGOP_CHIP_VALUE", "e1")
    assert PCV.mode() == "E1"
    monkeypatch.setenv("DGOP_CHIP_VALUE", "EVG")      # 등록 후보 중 떨어진 것은 받지 않는다
    assert PCV.mode() is None


def test_e1_takes_neighbor_frame_max():
    probs = [[0.9, 0.1], [0.99, 0.01], [0.2, 0.8], [1.0, 0.0]]
    # 구간 [1, 1]의 목표(1) 확률은 0.01이지만 바로 뒤 프레임이 0.8
    assert PCV.e1(probs, 1, 1, 1, 0.01) == 0.8
    # 두 프레임 밖(3번 다음)은 보지 않는다
    assert PCV.e1(probs, 1, 0, 0, 0.1) == 0.1
    # 구간 평균보다 낮아지지 않는다
    assert PCV.e1(probs, 0, 3, 3, 1.0) == 1.0


def test_table_path_follows_mode(monkeypatch):
    monkeypatch.delenv("DGOP_CHIP_VALUE", raising=False)
    assert PR.table_path() == PR.TABLE_PATH
    monkeypatch.setenv("DGOP_CHIP_VALUE", "E1")
    assert PR.table_path() == PR.TABLE_PATH_E1


def test_e1_table_is_valid():
    t = json.load(open(PR.TABLE_PATH_E1, encoding="utf-8"))
    assert t["chip_value"] == "E1"
    assert set(t["reliable"]) == {"n:ㅏ", "o:ㄴ", "o:ㄹ"}
    assert all(t["sounds"][s]["reliable"] for s in t["reliable"])
    assert t["system_gate"]["A1_definite_red_per_sentence"] <= 1.0


def test_annotate_uses_e1_table_only_when_on(monkeypatch):
    phones = [{"token": "o:ㄴ", "aligned": True, "scorable": True}, {"token": "n:ㅏ", "aligned": True, "scorable": True},
              {"token": "o:ㄱ", "aligned": True, "scorable": True}, {"token": "n:ㅏ", "aligned": True, "scorable": True}]
    monkeypatch.delenv("DGOP_CHIP_VALUE", raising=False)
    import os
    if not os.path.exists(PR.TABLE_PATH):
        assert PR.annotate([dict(p) for p in phones]) is False
    monkeypatch.setenv("DGOP_CHIP_VALUE", "E1")
    ph = [dict(p) for p in phones]
    assert PR.annotate(ph) is True
    assert [p["reliable"] for p in ph] == [True, True, False, False]   # 마지막 음절(가)은 늘 참고


def test_phone_confidences_adds_chip_only_when_on(monkeypatch):
    torch = pytest.importorskip("torch")
    import dgop_acoustic as DA
    lp = torch.log(torch.tensor([[0.98, 0.01, 0.01], [0.98, 0.01, 0.01], [0.2, 0.79, 0.01], [0.98, 0.01, 0.01]]))
    span = {"start": 1, "end": 1}
    ph = {"naive": 0.01}
    monkeypatch.delenv("DGOP_CHIP_VALUE", raising=False)
    DA._add_chip_value(ph, lp, 1, span)
    assert "chip" not in ph
    monkeypatch.setenv("DGOP_CHIP_VALUE", "E1")
    DA._add_chip_value(ph, lp, 1, span)
    assert ph["chip"] == pytest.approx(0.79, abs=1e-3) and ph["naive"] == 0.01
