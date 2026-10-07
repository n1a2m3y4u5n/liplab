#!/usr/bin/env python3
"""P3 검사 묶음 촬영 목록. backend/data/pilot/battery_manifest.json에서 화자별 대본·순서·파일 이름을 만든다.

촬영하는 날 파일 이름을 손으로 맞추다 틀리면 검사 묶음이 영상을 못 찾는다('영상 준비 전'). 그래서 목록 파일의 media_pattern을
그대로 써서 저장할 경로까지 적는다. 결과:
  docs/pilot/shot-list.md   화자별 촬영 대본(사람이 보는 판)
  docs/pilot/shot-list.csv  한 줄에 한 클립(talker, set, form, id, text, file, sound, done) — 촬영하며 표시하는 점검표

사용:
  python3 scripts/build_shot_list.py
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "backend", "data", "pilot", "battery_manifest.json")
OUT_MD = os.path.join(ROOT, "docs", "pilot", "shot-list.md")
OUT_CSV = os.path.join(ROOT, "docs", "pilot", "shot-list.csv")

SET_LABEL = {"word": "실제 얼굴 낱말", "sentence": "개방형 문장", "av": "소음 속 문장", "snr": "SNR 맞추기 문장"}
# 소리가 필요한 묶음(소음 속 검사는 영상의 소리를 쓴다). 낱말·개방형 문장은 소리 없이 보이지만 소리도 함께 녹음해 둔다.
NEEDS_SOUND = {"av", "snr"}


def rows(m: dict) -> list:
    out = []
    L = m["layers"]
    for key in ("word", "sentence", "av", "snr"):
        layer = L[key]
        talkers = m["talkers"][key]
        pattern = layer["media_pattern"]
        groups = []
        items = layer["items"]
        if isinstance(items, dict):
            for form, its in items.items():
                groups.append((form, its))
        else:
            groups.append(("-", items))
        if layer.get("reserve"):
            groups.append(("예비", layer["reserve"]))
        for talker in talkers:
            for form, its in groups:
                for it in its:
                    text = it.get("word") or it.get("text") or ""
                    out.append({"talker": talker, "set": key, "form": form, "id": it["id"], "text": text,
                                "file": pattern.format(talker=talker, id=it["id"]),
                                "sound": "필수" if key in NEEDS_SOUND else "녹음만", "done": ""})
    return out


def write_md(m: dict, rs: list) -> str:
    lines = [
        "# P3 검사 묶음 촬영 목록",
        "",
        f"목록 파일 판 `{m['version']}`(상태 {m['status']})에서 `scripts/build_shot_list.py`로 만든다. 목록을 고치면 다시 만든다.",
        "점검표는 `docs/pilot/shot-list.csv`, 촬영 뒤 확인은 `python3 scripts/check_pilot_media.py <영상 폴더>`.",
        "",
        "## 촬영 규칙",
        "",
        "- 1080p, 60fps, H.264 mp4, 음성 48kHz. 정면, 어깨 위부터, 입이 화면 가운데. 조명은 얼굴 앞쪽에서 고르게.",
        "- 클립마다 입을 다문 채 1초 → 한 번 말하기 → 입을 다문 채 1초. 말하기 전후로 웃거나 고개를 끄덕이지 않는다.",
        "- 평소 말 빠르기와 크기로 말한다(일부러 또박또박하지 않는다). 틀리면 그 클립만 다시 찍는다.",
        "- 소리 '필수' 묶음(소음 속 문장, SNR)은 조용한 방에서 녹음한다. 잡음은 나중에 화면에서 섞는다.",
        "- 파일 이름은 아래 '파일' 열 그대로(대소문자 포함). 영상 폴더(LIPLAB_PILOT_MEDIA_DIR) 안에 그 경로로 둔다.",
        "- 같은 자리에서 iPhone ARKit 기록(Live Link Face)을 함께 켠다(계획 P12). 오조음 세트·단독 모음 녹음도 같은 날 받는다.",
        "",
    ]
    talkers = sorted({r["talker"] for r in rs})
    for t in talkers:
        mine = [r for r in rs if r["talker"] == t]
        lines += [f"## 화자 {t} ({len(mine)}클립)", ""]
        for key in ("word", "sentence", "av", "snr"):
            part = [r for r in mine if r["set"] == key]
            if not part:
                continue
            lines += [f"### {SET_LABEL[key]} ({len(part)}클립, 소리 {part[0]['sound']})", "", "| 폼 | 번호 | 대본 | 파일 |",
                      "|---|---|---|---|"]
            lines += [f"| {r['form']} | {r['id']} | {r['text']} | `{r['file']}` |" for r in part]
            lines.append("")
    total = len(rs)
    by = {k: sum(1 for r in rs if r["set"] == k) for k in ("word", "sentence", "av", "snr")}
    lines += ["## 합계", "", f"전체 {total}클립: " + ", ".join(f"{SET_LABEL[k]} {v}" for k, v in by.items()) + ".",
              "잡담 잡음 파일 `noise/babble.wav`(8명 이상 섞은 모노 48kHz) 하나가 따로 필요하다.", ""]
    return "\n".join(lines)


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)
    rs = rows(m)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(write_md(m, rs))
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["talker", "set", "form", "id", "text", "file", "sound", "done"])
        w.writeheader()
        w.writerows(rs)
    print(f"썼음: {OUT_MD}, {OUT_CSV} ({len(rs)}클립)")


if __name__ == "__main__":
    main()
