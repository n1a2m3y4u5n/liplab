"""
목소리별 대조의 사람 블라인드 청취 판정(docs/listen-voice-contrast-2026-10.md 10절, 사전 등록).

기계 판정자는 한 음절 소리 세기 대조에서 서로 반대로 치우쳤다(Whisper는 거센소리 쪽, kresnik CTC는 예사소리 쪽, 맥 음향 분류는 정확도 0.62~0.83).
그래서 피하기 목록과 남은 의심 클립은 사람이 듣고 고른 결과로 정한다. 이 스크립트는 두 가지를 한다.

  build   청취 페이지 하나(HTML, 소리를 안에 담아 오프라인으로 열림)와 정답 열쇠(JSON, 페이지 밖)를 만든다.
          문항(10.1절): (가) 피하기 목록 129개, (나) 같은 글의 대조 클립, (다) 한 음절 소리 세기·마찰음, (라) m3 일반화 검사 네 낱말.
          화면에는 목소리·의도한 글·묶음이 보이지 않는다. 문항·보기 순서는 청취자 이름으로 섞이고, 답은 그 브라우저에만 남으며
          끝나면 CSV로 내려받는다. 소리는 앱 저장소의 합성 소리(backend/data/sound)라 AI Hub 자료가 아니다.
          자동 점검 때는 주소에 ?mute=1을 붙이거나 localStorage.liplab_mute = '1'이면 소리를 내지 않고 재생이 끝난 것처럼 진행한다.
  analyze 여러 청취자의 CSV와 열쇠로 10.2절 판정을 내고 반영 제안을 JSON으로 쓴다(앱 반영은 사람이 결과를 본 뒤 한다).

  python3 scripts/listen_blind_check.py build --out ~/Downloads/liplab-lab/data/listen_blind_check.html
  python3 scripts/listen_blind_check.py analyze 청취자1.csv 청취자2.csv … --key ~/Downloads/liplab-lab/data/listen_blind_check_key.json --out result.json
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BACKEND = os.path.join(ROOT, "backend")
SOUND = os.path.join(BACKEND, "data", "sound")
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
# 같은 자리의 예사·거센·된소리 묶음(ㅅ은 거센소리가 없다)
SERIES = [("ㄱ", "ㅋ", "ㄲ"), ("ㄷ", "ㅌ", "ㄸ"), ("ㅂ", "ㅍ", "ㅃ"), ("ㅈ", "ㅊ", "ㅉ"), ("ㅅ", None, "ㅆ")]
CAT_NAME = {0: "예사", 1: "거센", 2: "된"}
TRAIN_VOICES = ("m1", "f1", "m2", "f2")
TEST_VOICE = "m3"
N_OPTS = 4
GEN_FAILED = ("마늘", "바늘", "오빠", "나물")
LAB = os.path.expanduser("~/Downloads/liplab-lab")
SQA_RUNS = ("20261007_mwo4z0qqys996o", "20261007_y0mn97i6mjalnq")
# 10.2절 판정 상수
MIN_ANSWERED = 0.80
MIN_CONTROL = 0.80
MIN_CONTROL_ITEMS = 10
MIN_LISTENERS = 3
PASS_P = 2 / 3
FAIL_P = 0.5


def split(syl):
    o = ord(syl) - 0xAC00
    return o // 588, (o % 588) // 28, o % 28


def join(cho, jung, jong):
    return chr(0xAC00 + cho * 588 + jung * 28 + jong)


def series_of(syl):
    """한 음절의 첫소리가 속한 묶음과 그 안의 자리(0 예사, 1 거센, 2 된). 해당 없으면 None."""
    if len(syl) != 1 or not ("가" <= syl <= "힣"):
        return None
    c = CHO[split(syl)[0]]
    for s in SERIES:
        if c in s:
            return s, s.index(c)
    return None


def series_options(syl):
    """같은 운(모음·받침)으로 묶음의 다른 소리를 붙인 글. 자리 순서(예사, 거센, 된)."""
    s, _ = series_of(syl)
    _, jung, jong = split(syl)
    return [join(CHO.index(c), jung, jong) for c in s if c]


def tid(set_, voice, text):
    return hashlib.sha1(f"{set_}|{voice}|{text}".encode()).hexdigest()[:10]


def fill(intended, first, more, n=N_OPTS):
    """보기: 의도한 글, first(경쟁 글 전부), 넷이 될 때까지 more에서 순서대로. 같은 글은 한 번."""
    out = [intended]
    for t in list(first):
        if t not in out:
            out.append(t)
    for t in more:
        if len(out) >= n:
            break
        if t not in out:
            out.append(t)
    return out


def unresolved_single():
    out = set()
    for run in SQA_RUNS:
        p = os.path.join(LAB, "data", "pod_runs", run, "sqa", "summary.json")
        try:
            for u in json.load(open(p, encoding="utf-8"))["unresolved"]:
                if series_of(u["key"]):
                    out.add(u["key"])
        except (OSError, ValueError, KeyError):
            print("경고: 저장소 밖 소리 점검 요약이 없어 (다)에서 뺌:", p, file=sys.stderr)
    return out


def plan():
    """10.1절 문항 목록. [{id, set, voice, text, options, intended}]."""
    import listen_curriculum as L
    import listen_contrast_targets as T
    import sound_clips as S
    avoid = json.load(open(os.path.join(BACKEND, "data", "listen_voice_avoid.json"), encoding="utf-8"))
    rows = {r["uid"]: r for r in T.build()}

    def comps_of(set_, voice, text):
        r = rows.get(f"{set_}:{voice}:{S.normalize_text(text)}")
        return [c["text"] for c in (r or {}).get("comps", [])]

    trials, seen = [], set()

    def add(set_, voice, text, options):
        k = (voice, text)
        if set_ != "na" and k in seen:
            return
        seen.add(k)
        trials.append({"id": tid(set_, voice, text), "set": set_, "voice": voice, "text": text, "intended": text,
                       "options": options})

    # (가) 피하기 목록
    ga_opts = {}
    for v in TRAIN_VOICES:
        for t, lst in sorted(avoid["voices"].get(v, {}).items()):
            sets = sorted({x["set"] for x in lst})
            more = [c for s in sets for c in comps_of(s, v, t)]
            opts = fill(t, [x["against"] for x in lst], more)
            ga_opts.setdefault(t, opts)
            add("ga", v, t, opts)
    # (나) 대조 클립: 글마다 피하기 목록에 없는 첫 훈련 목소리
    for t, opts in sorted(ga_opts.items()):
        v = next((v for v in TRAIN_VOICES if t not in avoid["voices"].get(v, {})), None)
        if v:
            add("na", v, t, opts)
    # (다) 한 음절 소리 세기·마찰음
    texts = set()
    for p in L.AX_PAIRS:
        if p["kind"] in ("laryngeal", "fricative"):
            texts |= {t for t in (p["a"], p["b"]) if series_of(t)}
    texts |= unresolved_single()
    for t in sorted(texts):
        for v in TRAIN_VOICES:
            add("da", v, t, series_options(t))
    # (라) m3 일반화 검사 네 낱말
    rep = avoid.get("test_voice_report", {}).get(TEST_VOICE, {})
    gen_opts = {it["target"]: it["options"] for it in L.gen_test_items(L.word_pool(include_gen=True))}
    for w in GEN_FAILED:
        more = [o for o in gen_opts.get(w, []) if o != w] + comps_of("gen", TEST_VOICE, w)
        add("ra", TEST_VOICE, w, fill(w, [x["against"] for x in rep.get(w, [])], more))
    return trials


def build(out):
    import sound_clips as S
    manifest = json.load(open(os.path.join(SOUND, "manifest.json"), encoding="utf-8"))
    trials = plan()
    page_trials, key = [], {}
    missing = []
    for t in trials:
        c = manifest["clips"].get(t["voice"], {}).get(S.normalize_text(t["text"]))
        if not c:
            # (다)의 소리 점검 미해결 한 음절 가운데 듣기 글이 아닌 것(m1·f1만 있음)은 m2·f2 클립이 없다. 있는 목소리만 낸다
            if t["set"] != "da":
                missing.append((t["voice"], t["text"]))
            continue
        src = {}
        for ext, mime in (("ogg", "audio/ogg"), ("m4a", "audio/mp4")):
            with open(os.path.join(SOUND, "clips", f"{c['id']}.{ext}"), "rb") as f:
                src[ext] = f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        page_trials.append({"id": t["id"], "options": t["options"], "src": src})
        key[t["id"]] = {k: t[k] for k in ("set", "voice", "text", "intended", "options")} | {"clip": c["id"]}
    if missing:
        sys.exit(f"클립 없음: {missing[:5]} …")
    page = TEMPLATE.replace("__TRIALS__", json.dumps(page_trials, ensure_ascii=False)).replace("__N__", str(len(page_trials)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    kp = os.path.splitext(out)[0] + "_key.json"
    with open(kp, "w", encoding="utf-8") as f:
        json.dump({"doc": "docs/listen-voice-contrast-2026-10.md 10절", "trials": key}, f, ensure_ascii=False, indent=1)
    n = Counter(k["set"] for k in key.values())
    print(f"문항 {len(page_trials)}개 (가 {n['ga']} · 나 {n['na']} · 다 {n['da']} · 라 {n['ra']}), "
          f"{os.path.getsize(out) / 1e6:.1f} MB → {out}\n열쇠 → {kp}")


def read_answers(files):
    """CSV들 → {청취자: {문항 id: 고른 글('' = 잘 모르겠어요)}}. 같은 청취자의 같은 문항은 처음 답을 쓴다."""
    out = defaultdict(dict)
    for fn in files:
        with open(fn, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                who = (r.get("listener") or "").strip()
                if who and r["trial"] not in out[who]:
                    out[who][r["trial"]] = r.get("chosen", "")
    return out


def spearman(xs, ys):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    a, b = rank(xs), rank(ys)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return round(num / den, 3) if den else None


def analyze(files, keyfile, out):
    key = json.load(open(keyfile, encoding="utf-8"))["trials"]
    ans = read_answers(files)
    na_ids = [i for i, k in key.items() if k["set"] == "na"]
    listeners = {}
    for who, a in sorted(ans.items()):
        answered = sum(1 for i in key if i in a) / len(key)
        ctrl = [a[i] == key[i]["intended"] for i in na_ids if i in a]
        ctrl_p = sum(ctrl) / len(ctrl) if ctrl else None
        check_ctrl = len(na_ids) >= MIN_CONTROL_ITEMS
        ok = answered >= MIN_ANSWERED and (not check_ctrl or (ctrl_p is not None and ctrl_p >= MIN_CONTROL))
        listeners[who] = {"answered": round(answered, 3), "control_p": None if ctrl_p is None else round(ctrl_p, 3),
                          "n_control": len(ctrl), "included": ok}
    inc = [w for w, v in listeners.items() if v["included"]]
    rows = {}
    for i, k in key.items():
        rs = [ans[w][i] for w in inc if i in ans[w]]
        n = len(rs)
        cnt = Counter(r for r in rs if r)
        hit = cnt.get(k["intended"], 0)
        p = hit / n if n else None
        top = max(cnt, key=lambda t: (cnt[t], t == k["intended"])) if cnt else None
        if n < MIN_LISTENERS:
            verdict = "판정 불가"
        elif p >= PASS_P:
            verdict = "통과"
        elif p < FAIL_P and top is not None and top != k["intended"]:
            verdict = "실패"
        else:
            verdict = "보류"
        rows[i] = {"set": k["set"], "voice": k["voice"], "text": k["text"], "n": n, "p_intended": None if p is None else round(p, 3),
                   "top": top, "counts": dict(cnt), "dont_know": sum(1 for r in rs if not r), "verdict": verdict}
    avoid = json.load(open(os.path.join(BACKEND, "data", "listen_voice_avoid.json"), encoding="utf-8"))
    in_avoid = {(v, t) for v, tx in avoid["voices"].items() for t in tx}
    by = lambda s: [r for r in rows.values() if r["set"] == s]   # noqa: E731
    proposal = {
        "remove_from_avoid": sorted([(r["voice"], r["text"]) for r in by("ga") if r["verdict"] == "통과"]),
        "add_to_avoid": sorted([(r["voice"], r["text"]) for r in by("da") if r["verdict"] == "실패"
                                and (r["voice"], r["text"]) not in in_avoid]),
        "gen_human_fail": sorted([r["text"] for r in by("ra") if r["verdict"] == "실패"]),
    }
    # 보고만: 글마다 (가)와 (나)의 p 차이, 소리 세기 방향별 오답, 기계 margin과 사람 p의 순위 상관
    na_p = {r["text"]: r["p_intended"] for r in by("na") if r["p_intended"] is not None}
    diff = [{"voice": r["voice"], "text": r["text"], "p_avoided": r["p_intended"], "p_control": na_p[r["text"]],
             "diff": round(r["p_intended"] - na_p[r["text"]], 3)} for r in by("ga") if r["p_intended"] is not None and r["text"] in na_p]
    direction = Counter()
    for r in by("da"):
        s = series_of(r["text"])
        for t, c in r["counts"].items():
            if t != r["text"] and series_of(t):
                direction[f"{CAT_NAME[s[1]]}→{CAT_NAME[series_of(t)[1]]}"] += c
    mm, pp = [], []
    for r in by("ga"):
        lst = avoid["voices"].get(r["voice"], {}).get(r["text"], [])
        if lst and r["p_intended"] is not None:
            mm.append(min(x["margin"] for x in lst))
            pp.append(r["p_intended"])
    res = {"doc": "docs/listen-voice-contrast-2026-10.md 10.2절",
           "rule": {"min_answered": MIN_ANSWERED, "min_control_p": MIN_CONTROL, "min_control_items": MIN_CONTROL_ITEMS,
                    "min_listeners": MIN_LISTENERS, "pass_if": "p >= 2/3", "fail_if": "p < 0.5 and top != intended"},
           "listeners": listeners, "n_included": len(inc),
           "summary": {s: dict(Counter(r["verdict"] for r in by(s))) for s in ("ga", "na", "da", "ra")},
           "proposal": proposal,
           "report": {"avoided_minus_control": diff, "laryngeal_direction_errors": dict(direction),
                      "spearman_margin_vs_p": spearman(mm, pp), "n_margin_pairs": len(mm)},
           "rows": rows}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"청취자 {len(listeners)}명 중 포함 {len(inc)}명 → {out}")
    for s, name in (("ga", "가 피하기"), ("na", "나 대조"), ("da", "다 소리 세기"), ("ra", "라 m3")):
        print(f"  {name}: {res['summary'][s]}")
    print(f"  제안: 목록에서 뺌 {len(proposal['remove_from_avoid'])}, 넣음 {len(proposal['add_to_avoid'])}, m3 사람 실패 {proposal['gen_human_fail']}")
    return res


TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>소리 듣고 고르기</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e2dc;--teal:#0d9488;--teal-d:#0f766e;--on-teal:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--card:#20201e;--ink:#f1f1ec;--muted:#a3a39b;--line:#34342f;--teal:#14b8a6;--teal-d:#0d9488;--on-teal:#04201d}}
:root[data-theme="dark"]{--bg:#161615;--card:#20201e;--ink:#f1f1ec;--muted:#a3a39b;--line:#34342f;--teal:#14b8a6;--teal-d:#0d9488;--on-teal:#04201d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:560px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}p{margin:0 0 12px;color:var(--muted)}
.card{background:var(--card);border:1.5px solid var(--line);border-radius:16px;padding:20px;margin-top:16px}
button{font:inherit;border-radius:12px;border:2px solid var(--line);background:var(--card);color:var(--ink);min-height:52px;padding:8px 16px;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}.primary{background:var(--teal);border-color:var(--teal-d);color:var(--on-teal);font-weight:700}
.opts{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:16px}.opts button{font-size:26px;font-weight:700;min-height:80px}
.row{display:flex;gap:10px;align-items:center;justify-content:space-between;margin-top:14px;flex-wrap:wrap}
input{font:inherit;padding:10px 12px;border-radius:10px;border:1.5px solid var(--line);width:100%;background:var(--card);color:var(--ink)}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:12px}.bar i{display:block;height:100%;background:var(--teal)}
.muted{color:var(--muted)}
</style></head><body><main>
<h1>소리 듣고 고르기</h1>
<p>합성 음성 낱말이나 한 음절을 듣고, 들린 글을 고릅니다. 소리는 문항마다 두 번까지 들을 수 있어요. 이어폰을 권하고, 소리 크기는 편안하게
맞춰 주세요. 헷갈리면 '잘 모르겠어요'를 눌러도 됩니다. 모두 __N__문항(약 20~25분)이며 중간에 닫아도 같은 이름으로 이어서 할 수 있어요.
답은 이 브라우저에만 남고, 끝나면 CSV 파일로 받아 담당자에게 보내 주세요.</p>
<div class="card" id="start"><label>이름 또는 번호<input id="who" autocomplete="off"></label>
<div class="row"><span id="resume" class="muted"></span><button class="primary" id="go">시작</button></div></div>
<div class="card" id="trial" hidden>
<div class="row"><b id="pos"></b><button id="play" class="primary">소리 듣기</button></div>
<div class="bar"><i id="prog" style="width:0"></i></div>
<div class="opts" id="opts"></div>
<div class="row"><button id="dk">잘 모르겠어요</button><span id="left" class="muted"></span></div>
<div class="row"><button id="pause">잠시 멈추고 지금까지 받기</button></div></div>
<div class="card" id="done" hidden><b id="donemsg">다 했어요. 고맙습니다.</b><p>아래 버튼으로 답을 받아 보내 주세요.</p>
<div class="row"><button class="primary" id="dl">CSV 받기</button><button id="back" hidden>이어서 하기</button></div></div>
</main><script>
const TRIALS = __TRIALS__
const KEY = 'liplab_blind_check_v2'
const $ = (id) => document.getElementById(id)
const MUTED = (() => { try { return new URLSearchParams(location.search).get('mute') === '1' || localStorage.getItem('liplab_mute') === '1' } catch (e) { return false } })()
const loadAll = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {} } catch (e) { return {} } }
const saveAll = (all) => { try { localStorage.setItem(KEY, JSON.stringify(all)) } catch (e) {} }
let all = loadAll(), st = null
function seeded(seed) { let x = 2166136261 >>> 0; for (const ch of seed) { x ^= ch.charCodeAt(0); x = Math.imul(x, 16777619) >>> 0 }
  return () => ((x = (Math.imul(x, 1664525) + 1013904223) >>> 0) / 2 ** 32) }
function shuffle(a, seed) { const r = seeded(seed); for (let i = a.length - 1; i > 0; i -= 1) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]] } return a }
$('who').oninput = () => { const s = all[$('who').value.trim()]; $('resume').textContent = s ? `${Object.keys(s.answers).length} / ${TRIALS.length} 했어요` : '' }
const audio = new Audio()
const ogg = audio.canPlayType('audio/ogg; codecs=opus') !== ''
let cur = null, plays = 0, t0 = 0
$('go').onclick = () => {
  const who = $('who').value.trim(); if (!who) { $('who').focus(); return }
  st = all[who] || { who, order: shuffle(TRIALS.map((t) => t.id), who), answers: {} }
  all[who] = st; saveAll(all); $('start').hidden = true; next()
}
function next() {
  const id = st.order.find((x) => !(x in st.answers))
  const n = Object.keys(st.answers).length
  if (!id) { $('trial').hidden = true; $('done').hidden = false; $('donemsg').textContent = '다 했어요. 고맙습니다.'; $('back').hidden = true; return }
  cur = TRIALS.find((t) => t.id === id); plays = 0
  $('trial').hidden = false; $('done').hidden = true; $('pos').textContent = `${n + 1}번째`
  $('prog').style.width = `${(n / TRIALS.length) * 100}%`; $('left').textContent = `${TRIALS.length - n}개 남음`
  const opts = $('opts'); opts.innerHTML = ''
  for (const o of shuffle([...cur.options], st.who + cur.id)) {
    const b = document.createElement('button'); b.textContent = o; b.disabled = true; b.onclick = () => answer(o); opts.appendChild(b)
  }
  $('dk').disabled = true; $('play').disabled = false; $('play').textContent = '소리 듣기'
}
function heard() {
  if (plays === 1) t0 = performance.now()
  $('play').disabled = plays >= 2; $('play').textContent = plays >= 2 ? '두 번 들었어요' : '한 번 더 듣기'
  for (const b of $('opts').children) b.disabled = false
  $('dk').disabled = false
}
$('play').onclick = () => {
  if (!cur || plays >= 2) return
  plays += 1; $('play').disabled = true
  if (MUTED) { setTimeout(heard, 50); return }   // 자동 점검: 소리를 내지 않는다
  audio.src = ogg ? cur.src.ogg : cur.src.m4a; audio.currentTime = 0
  audio.onended = heard
  audio.play().catch(() => { plays -= 1; $('play').disabled = false })
}
$('dk').onclick = () => answer('')
function answer(text) {
  st.answers[cur.id] = { chosen: text, plays, rt_ms: Math.round(performance.now() - t0), at: new Date().toISOString() }
  saveAll(all); next()
}
$('pause').onclick = () => { $('trial').hidden = true; $('done').hidden = false; $('back').hidden = false
  $('donemsg').textContent = `지금까지 ${Object.keys(st.answers).length}문항 했어요. 받아 두고 나중에 이어서 할 수 있어요.` }
$('back').onclick = () => next()
$('dl').onclick = () => {
  const q = (x) => `"${String(x).replace(/"/g, '""')}"`
  const rows = st.order.filter((id) => id in st.answers).map((id) => { const a = st.answers[id]; return [st.who, id, a.chosen, a.plays, a.rt_ms, a.at].map(q).join(',') })
  const blob = new Blob(['﻿' + ['listener,trial,chosen,plays,rt_ms,at', ...rows].join('\n')], { type: 'text/csv' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `소리판정_${st.who}.csv`; a.click()
}
</script></body></html>
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("csv", nargs="+")
    a.add_argument("--key", required=True)
    a.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "build":
        build(os.path.expanduser(args.out))
    else:
        analyze(args.csv, os.path.expanduser(args.key), os.path.expanduser(args.out))
