#!/usr/bin/env python3
"""P3 검사 묶음 촬영 목록. backend/data/pilot/battery_manifest.json에서 화자별 대본·순서·파일 이름을 만든다.

촬영하는 날 파일 이름을 손으로 맞추다 틀리면 검사 묶음이 영상을 못 찾는다('영상 준비 전'). 그래서 목록 파일의 media_pattern을
그대로 써서 저장할 경로까지 적는다. 결과:
  docs/pilot/shot-list.md   화자별 촬영 대본(사람이 보는 판)
  docs/pilot/shot-list.csv  한 줄에 한 클립(talker, set, form, id, text, file, sound, done) — 촬영하며 표시하는 점검표
  docs/pilot/teleprompter.html  촬영용 프롬프터(브라우저로 열기, 화자·묶음·폼 고르기, 스페이스·→ 다음, ← 이전).
                                한 묶음을 이어 찍은 뒤 scripts/split_takes.py로 자른다

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
OUT_HTML = os.path.join(ROOT, "docs", "pilot", "teleprompter.html")

SET_LABEL = {"word": "실제 얼굴 낱말", "sentence": "개방형 문장", "av": "소음 속 문장", "snr": "SNR 맞추기 문장"}
# 소리가 필요한 묶음(소음 속 검사는 영상의 소리를 쓴다). 낱말·개방형 문장은 소리 없이 보이지만 소리도 함께 녹음해 둔다.
NEEDS_SOUND = {"av", "snr"}


TELEPROMPTER = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIPLAB 촬영 프롬프터</title>
<style>
:root{--bg:#101014;--fg:#f4f4f6;--sub:#9a9aa8;--accent:#7d53de}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:Pretendard,'Apple SD Gothic Neo',sans-serif;height:100dvh;display:flex;flex-direction:column}
header{display:flex;gap:8px;padding:12px 16px;align-items:center;flex-wrap:wrap;color:var(--sub);font-size:14px}
select,button{background:#1c1c24;color:var(--fg);border:1px solid #33333f;border-radius:8px;padding:6px 10px;font-size:14px}
main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding:16px;text-align:center}
#text{font-size:min(14vw,120px);font-weight:700;line-height:1.2;word-break:keep-all}
#meta{color:var(--sub);font-size:18px}#pause{height:8px;width:min(80vw,600px);background:#22222c;border-radius:4px;overflow:hidden}
#bar{height:100%;width:0;background:var(--accent)}#next{color:var(--sub);font-size:22px}
</style></head><body>
<header>
  화자 <select id="talker"></select> 묶음 <select id="set"></select> 폼 <select id="form"></select>
  <button id="prev">← 이전</button><button id="nextBtn">다음 →</button><span id="pos"></span>
</header>
<main>
  <div id="meta"></div><div id="text"></div><div id="pause"><div id="bar"></div></div><div id="next"></div>
</main>
<script>
const SHOTS = __SHOTS__;
const LABEL = {word:'실제 얼굴 낱말', sentence:'개방형 문장', av:'소음 속 문장', snr:'SNR 맞추기'};
const $ = (id) => document.getElementById(id);
const uniq = (xs) => [...new Set(xs)];
let list = [], i = 0, timer = null;
function fill(sel, vals, label) { sel.innerHTML = vals.map(v => `<option value="${v}">${label ? label(v) : v}</option>`).join(''); }
function refresh(level) {
  if (level <= 0) fill($('set'), uniq(SHOTS.filter(s => s.talker === $('talker').value).map(s => s.set)), v => LABEL[v] || v);
  if (level <= 1) fill($('form'), uniq(SHOTS.filter(s => s.talker === $('talker').value && s.set === $('set').value).map(s => s.form)));
  list = SHOTS.filter(s => s.talker === $('talker').value && s.set === $('set').value && s.form === $('form').value);
  i = 0; show();
}
function show() {
  const s = list[i];
  $('text').textContent = s ? s.text : '끝';
  $('meta').textContent = s ? `${s.id} · ${s.file}` : '이 묶음을 다 찍었어요. 녹화를 멈추고 split_takes.py로 자르세요.';
  $('next').textContent = list[i + 1] ? `다음: ${list[i + 1].text}` : '';
  $('pos').textContent = `${Math.min(i + 1, list.length)} / ${list.length}`;
  // 넘길 때마다 2초 쉼 막대: 입을 다물고 기다린 뒤 읽는다(자르기가 쉼으로 구간을 나눈다)
  clearInterval(timer); const t0 = Date.now(); $('bar').style.width = '0';
  timer = setInterval(() => { const p = Math.min(1, (Date.now() - t0) / 2000); $('bar').style.width = (p * 100) + '%'; if (p >= 1) clearInterval(timer); }, 50);
}
function step(d) { i = Math.max(0, Math.min(list.length, i + d)); show(); }
fill($('talker'), uniq(SHOTS.map(s => s.talker)));
$('talker').onchange = () => refresh(0); $('set').onchange = () => refresh(1); $('form').onchange = () => refresh(2);
$('prev').onclick = () => step(-1); $('nextBtn').onclick = () => step(1);
document.addEventListener('keydown', (e) => { if (e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); step(1) } if (e.key === 'ArrowLeft') step(-1) });
refresh(0);
</script></body></html>
'''


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
    shots = [{k: r[k] for k in ("talker", "set", "form", "id", "text", "file")} for r in rs]
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(TELEPROMPTER.replace("__SHOTS__", json.dumps(shots, ensure_ascii=False)))
    print(f"썼음: {OUT_MD}, {OUT_CSV}, {OUT_HTML} ({len(rs)}클립)")


if __name__ == "__main__":
    main()
