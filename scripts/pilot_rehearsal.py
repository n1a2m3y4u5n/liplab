#!/usr/bin/env python
"""
파일럿 리허설 자동화(종합 계획 P0, docs/pilot/log-spec-audit-2026-10-07.md 4절).

가상 참여자 몇 명이 API로 예비 파일럿 전 과정을 돈다. 집단은 둘(소리 듣기 훈련 rh_train, 독화 훈련 rh_ctrl)이고, P3 폼 순서는 검사 참여
순번대로(ABC·BCA·CAB), 소리 듣기 검사 폼 순서는 계정 번호 홀짝대로(A→B·B→A) 다르게 나온다.

  등록 → 참여 코드 → 사전 검사(독화 표준검사 A, P3 A1·A2의 모든 층, 소리 듣기 역치 검사 babble·talker2와 낱말 일반화 검사, 인공와우 모의 sim=ci)
  → 훈련 시행 몇 개(집단별) → 사후 검사(표준검사 B, P3 B, 소리 듣기 검사 다시) → 유지 검사 예약 확인 → 한 명 학습 초기화
  → 운영자 계정으로 가명 내보내기(/api/pilot/export?trials=true)

내보내기에서 분석에 필요한 필드가 모두 값으로 나오는지(필드마다 n·null 비율), 배정·순서·반응 시간·재생 횟수 규칙, 개인정보와 학습 입력
문장이 빠졌는지, 영상이 없는 문항이 '준비 전'(missing)으로 남는지를 검사한다. 끝으로 scripts/pilot_analyze.py를 같은 내보내기에
돌려 주분석이 끝까지 계산되는지 본다.

매체(--media):
  partial(기본)  임시 매체 폴더에 낱말 영상 절반, SNR 문장 영상 전부, 소음 속 문장 영상 절반, 잡음 파일을 만들고(내용 없는 시험 파일),
                 목록 사본에 SNR·소음 문장의 말소리 크기를 넣는다. 영상이 없는 문항은 missing으로 남는다
  none           매체 없음(지금 저장소 상태 그대로). 낱말·SNR·소음 층은 문항이 하나도 준비되지 않아 missing만 남는다

실행(저장소 루트에서, 임시 DB를 쓰는 별도 프로세스와 같은 방식으로 이 프로세스 안에서 앱을 띄운다. 소리·네트워크·유료 API 없음):
  backend/.venv/bin/python scripts/pilot_rehearsal.py --out /tmp/rehearsal          # 보고서·내보내기·분석 결과를 남긴다
  backend/.venv/bin/python scripts/pilot_rehearsal.py --participants 6 --media none

--base-url을 주면 이미 띄운 개발 서버(운영 서버 아님)에 붙는다. 그 서버는 LIPLAB_PILOT=1, LIPLAB_PILOT_CODES에 --codes와 같은 코드,
LIPLAB_ADMIN_EMAILS에 --operator-email이 있어야 하고, 매체는 그 서버의 폴더를 쓴다(이 스크립트가 만들지 않는다).
결과: <out>/rehearsal_report.json(검사 결과), <out>/export.json(가명 내보내기), <out>/analysis/(pilot_analyze 결과). 실패한 검사가
있으면 종료 코드 1.
"""
import argparse
import json
import math
import os
import random
import secrets
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")

CODES = {"RH_TRAIN": "rh_train", "RH_CTRL": "rh_ctrl"}
# 등록 순서별 집단. 운영자가 계정 1번이라 참여자는 2번부터다. 이 순서면 두 집단 모두 짝수·홀수 계정(소리 듣기 검사 폼 순서 A→B·B→A)을 갖는다
GROUP_PATTERN = ("RH_TRAIN", "RH_CTRL", "RH_CTRL", "RH_TRAIN", "RH_TRAIN", "RH_CTRL")
MARK_TRAINING = "리허설학습입력표지"   # 학습 중 입력 문장(내보내기에 나오면 안 된다)


# ───────────────────────── 앱 연결 ─────────────────────────
class Api:
    """TestClient(이 프로세스) 또는 httpx.Client(개발 서버). 같은 get/post 모양."""

    def __init__(self, client):
        self.c = client
        self.calls = 0

    def req(self, method, path, headers=None, ok=(200, 201), **kw):
        self.calls += 1
        r = self.c.request(method, path, headers=headers or {}, **kw)
        if ok and r.status_code not in ok:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return r

    def get(self, path, h=None, **kw):
        return self.req("GET", path, h, **kw)

    def post(self, path, h=None, **kw):
        return self.req("POST", path, h, **kw)


def _local_env(tmp: str, media_mode: str) -> dict:
    """이 프로세스 안에서 앱을 띄울 환경. main을 불러오기 전에 정한다."""
    sys.path.insert(0, BACKEND)
    os.chdir(BACKEND)
    media = os.path.join(tmp, "media")
    os.makedirs(media, exist_ok=True)
    os.environ.update({
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp}/rehearsal.db", "PYTHONDONTWRITEBYTECODE": "1",
        "LIPLAB_PILOT": "1", "LIPLAB_PILOT_CODES": ",".join(f"{k}:{v}" for k, v in CODES.items()),
        "LIPLAB_ADMIN_EMAILS": "rehearsal-op@example.com", "LIPLAB_PILOT_MEDIA_DIR": media,
        "LIPLAB_PILOT_SECRET": "rehearsal-" + secrets.token_hex(8), "LIPLAB_RETENTION_DAYS": "28",
    })
    for k in ("ANTHROPIC_API_KEY", "LIPLAB_PILOT_NOCUE_COHORTS", "LIPLAB_PILOT_MANIFEST"):
        os.environ.pop(k, None)
    import pilot_battery as pb
    m = pb.load_manifest()
    made = []
    if media_mode == "partial":
        # 시험용 목록 사본: SNR·소음 문장에 말소리 크기를 넣는다(실제 값은 촬영 뒤에 측정한다). 사본은 임시 폴더에만 둔다
        for it in m["layers"]["snr"]["items"]:
            it["speech_rms_dbfs"] = -23.0
        for f in pb.FORMS:
            for it in m["layers"]["av"]["items"][f]:
                it["speech_rms_dbfs"] = -23.0
        mp = os.path.join(tmp, "manifest.json")
        with open(mp, "w", encoding="utf-8") as fh:
            json.dump(m, fh, ensure_ascii=False)
        os.environ["LIPLAB_PILOT_MANIFEST"] = mp

        def touch(rel):
            p = os.path.join(media, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(b"\x00" * 16)
            made.append(rel)
        L = m["layers"]
        for f in pb.FORMS:   # 낱말·소음 속 문장: 폼마다 한 문항 건너 하나만 모든 화자 영상(A·AV 두 블록에 고루). 나머지는 missing
            for it in L["word"]["items"][f][::2]:
                for t in m["talkers"]["word"]:
                    touch(pb.media_relpath(L["word"], it, t))
            for it in L["av"]["items"][f][::2]:
                for t in m["talkers"]["av"]:
                    touch(pb.media_relpath(L["av"], it, t))
        for it in L["snr"]["items"]:
            for t in m["talkers"]["snr"]:
                touch(pb.media_relpath(L["snr"], it, t))
        touch(pb.noise_relpath(m, "babble"))
    return {"manifest": m, "media_files": len(made)}


# ───────────────────────── 가상 응답 ─────────────────────────
def logistic(x):
    return 1.0 / (1.0 + math.exp(-x))


class Virtual:
    """가상 참여자의 응답 모형. 능력은 사람마다 다르고, 사후(B)에는 집단에 따라 조금 오른다(분석이 끝까지 도는지만 본다)."""

    def __init__(self, idx: int, group: str, seed: int):
        self.idx, self.group = idx, group
        self.rng = random.Random(f"{seed}:{idx}")
        self.base = 0.30 + 0.25 * self.rng.random()      # 독화 문장 음소 정답 확률
        self.srt = 2.0 + 3.0 * self.rng.random()          # 소리 듣기 역치(dB, 인공와우 모의)

    def p_read(self, label: str) -> float:
        bump = {"A1": 0.0, "A2": 0.03, "B": 0.03 + (0.10 if self.group == "RH_CTRL" else 0.04), "R": 0.06}[label]
        return min(0.95, self.base + bump)

    def srt_at(self, phase: str) -> float:
        if phase == "pre":
            return self.srt
        return self.srt - (3.0 if self.group == "RH_TRAIN" else 1.0)

    def sentence(self, text: str, p: float) -> str:
        out = []
        for word in text.split():
            kept = "".join(ch for ch in word if self.rng.random() < p)
            if kept:
                out.append(kept)
        return " ".join(out)

    def choose(self, target, options, p):
        if self.rng.random() < p:
            return target
        others = [o for o in options if o != target] or list(options)
        return self.rng.choice(others)


def render_log(mode: str, rng, video=False) -> dict:
    """화면(lib/pilotBattery.js buildRenderLog)이 보내는 것과 같은 키."""
    out = {"scope": "layer", "frames": rng.randint(200, 900), "mean_late_ms": round(rng.uniform(0.5, 6.0), 1),
           "max_late_ms": rng.randint(8, 40), "over20_rate": round(rng.uniform(0, 0.03), 3),
           "over50_rate": 0.0, "screen_hz_est": 60, "screen_w": 1440, "screen_h": 900, "viewport_w": 1280,
           "viewport_h": 760, "dpr": 2, "device_class": "desktop", "os_family": "mac", "browser_family": "chrome",
           "render_mode": mode, "webgl": True}
    if video:
        out.update(video_total_frames=1800, video_dropped_frames=12, video_drop_rate=round(12 / 1800, 4))
    return out


# ───────────────────────── 한 사람의 흐름 ─────────────────────────
def register(api, email, name, ip):
    pw = "rh-" + secrets.token_hex(6)
    r = api.post("/api/auth/register", {"fly-client-ip": ip},
                 json={"email": email, "username": name, "password": pw, "agree_terms": True, "age_confirmed": True}).json()
    return {"Authorization": "Bearer " + r["access_token"], "fly-client-ip": ip}, pw


def placement(api, h, v: Virtual, form: str, label: str, log: dict):
    got = api.get("/api/assessment/placement", h, params={"form": form}).json()
    items = got["items"]
    p = v.p_read(label)
    resp = {it["id"]: v.choose(it["word"], it.get("options") or [it["word"]], 0.25 + 0.75 * p) for it in items}
    r = api.post("/api/assessment/score", h, json={"items": items, "responses": resp, "form": form}).json()
    log.setdefault("placement", []).append({"form": form, "n": r.get("total"), "post": got.get("post")})


def battery_label(api, h, v: Virtual, manifest, label: str, log: dict):
    st = api.get("/api/pilot/battery/status", h).json()
    lab = next(x for x in st["labels"] if x["label"] == label)
    form = lab["form"]
    maxp = (manifest.get("playback") or {}).get("max_plays", 2)
    out = {"form": form, "layers": {}}
    for x in lab["layers"]:
        layer = x["layer"]
        r = api.req("POST", "/api/pilot/battery/start", h, ok=None, json={"label": label, "layer": layer})
        if r.status_code != 200:
            out["layers"][layer] = {"start_status": r.status_code, "detail": r.json().get("detail")}
            continue
        s = r.json()
        L = manifest["layers"][layer]
        if layer == "snr":
            pool = {it["id"]: it for it in L["items"]}
        else:
            pool = {it["id"]: it for it in L["items"][s["form"]]}
        n_ans, stair_done, last_next = 0, False, None
        for it in s["items"]:
            if not it["ready"] or it["answered"]:
                continue
            src = pool[it["id"]]
            plays = 1 if v.rng.random() < 0.7 else min(2, maxp)
            stim = v.rng.randint(1500, 3500)
            rt = v.rng.randint(600, 6000)
            body = {"session_id": s["session_id"], "item_id": it["id"], "rt_ms": rt, "rt_from_onset_ms": rt + stim, "plays": plays}
            p = v.p_read(label)
            if layer == "word":
                body["chosen"] = v.choose(src["word"], it["options"], 0.25 + 0.75 * p)
            elif layer == "nonsense":
                sets = s["consonant_sets"]
                body["chosen_consonants"] = [c if v.rng.random() < p + 0.2 else v.rng.choice(sets[pos])
                                             for c, pos in zip(src["consonants"], ("C1", "C2", "C3"))]
            elif layer in ("snr", "av"):
                level = (s.get("staircase") or {}).get("next_db") if layer == "snr" else s.get("snr_db")
                if layer == "snr" and n_ans:
                    level = last_next
                q = logistic(((level if level is not None else 0.0) - (-4.0 + 4 * (0.5 - v.base))) / 2.0)
                if it.get("modality") == "AV":
                    q = min(0.98, q + 0.25)
                body["answer_text"] = src["text"] if v.rng.random() < q else v.sentence(src["text"], 0.2)
            else:
                body["answer_text"] = v.sentence(src["text"], p)
            a = api.post("/api/pilot/battery/answer", h, json=body).json()
            n_ans += 1
            if layer == "snr":
                last_next = a["staircase"]["next_db"]
                if a["staircase"]["done"]:
                    stair_done = True
                    break
        fin = api.req("POST", "/api/pilot/battery/finish", h, ok=None, json={
            "session_id": s["session_id"],
            "render_log": render_log("video" if layer in ("word", "snr", "av") else "avatar3d", v.rng,
                                     video=layer in ("word", "snr", "av") and s["n_ready"] > 0),
            **({"headphone_check": True, "volume_fixed": True} if layer in ("snr", "av") else {})})
        out["layers"][layer] = {"n_items": s["n_items"], "n_ready": s["n_ready"], "missing": s["missing"], "answered": n_ans,
                                "finish_status": fin.status_code, "finish": fin.json(),
                                **({"stair_done": stair_done} if layer == "snr" else {})}
    log.setdefault("battery", {})[label] = out
    return st


def listen_test(api, h, v: Virtual, noise: str, phase: str, log: dict):
    s = api.post("/api/listen/test/start", h, json={"noise": noise, "route": "earphone"}).json()
    srt = v.srt_at(phase) + (1.5 if noise == "talker2" else 0.0)
    level = s["start_db"]
    last = None
    for it in s["items"]:
        ok = v.rng.random() < logistic((level - srt) / 1.5)
        ans = it["text"] if ok else ("모르겠어요" if v.rng.random() < 0.5 else v.sentence(it["text"], 0.3))
        last = api.post("/api/listen/test/answer", h, json={"session": s["session"], "item_key": it["key"], "answer": ans,
                                                            "voice": "m3", "plays": 1, "route": "earphone", "sim": "ci",
                                                            "noise": noise}).json()
        level = last["next_db"]
    log.setdefault("listen_tests", []).append({"phase": phase, "noise": noise, "form": s["form"], "srt_db": last.get("srt_db"),
                                               "done": last.get("done")})


def listen_wordtest(api, h, v: Virtual, phase: str, log: dict):
    s = api.post("/api/listen/wordtest/start", h).json()
    p = 0.45 + (0.15 if phase == "post" and v.group == "RH_TRAIN" else 0.03 if phase == "post" else 0.0)
    last = None
    for it in s["items"]:
        last = api.post("/api/listen/wordtest/answer", h, json={"session": s["session"], "item_key": it["key"],
                                                                "answer": v.choose(it["target"], it["options"], p),
                                                                "voice": "m3", "plays": 1, "rt_ms": v.rng.randint(900, 4000),
                                                                "route": "earphone", "sim": "ci"}).json()
    log.setdefault("word_tests", []).append({"phase": phase, "n": len(s["items"]), "accuracy": last.get("accuracy")})


def train_listen(api, h, v: Virtual, log: dict):
    """소리 듣기 훈련(인공와우 모의): 1단계 소리 구별, 2단계 낱말 고르기 몇 개."""
    for n in (1, 2):
        api.post("/api/listen/skip", h, json={"stage": n})
    n_done = 0
    st = api.get("/api/listen/stage/1", h).json()
    for it in st["items"][:6]:
        same = v.rng.random() < 0.5
        api.post("/api/listen/answer", h, json={"stage": 1, "item_key": it["key"], "same": same, "level": st.get("level"),
                                                "voice": "m1", "plays": 1, "rt_ms": v.rng.randint(800, 3000), "route": "earphone",
                                                "output_latency_ms": 40, "pick": st.get("pick_mode"), "sim": "ci"})
        n_done += 1
    st = api.get("/api/listen/stage/2", h).json()
    for it in st["items"][:4]:
        opts = it.get("options") or []
        tgt = it.get("target") or (it.get("key", "")[2:])
        api.post("/api/listen/answer", h, json={"stage": 2, "item_key": it["key"], "answer": v.choose(tgt, opts or [tgt], 0.6),
                                                "level": st.get("level"), "voice": "m1", "plays": 1,
                                                "rt_ms": v.rng.randint(800, 3000), "route": "earphone", "sim": "ci",
                                                "pick": st.get("pick_mode")})
        n_done += 1
    log["listen_train_trials"] = n_done


def train_reading(api, h, v: Virtual, n_closure: int, log: dict):
    """독화 훈련: 문맥 추론 몇 개(화자·반응 시간·힌트·보기), 문장 연습 둘(보기 고름·직접 입력), 레슨 노력 문항(답함·건너뜀)."""
    items = api.get("/api/curriculum/closure", h).json()["items"][:n_closure]
    for k, it in enumerate(items):
        opts = list(it.get("options") or [])
        api.post("/api/curriculum/closure-answer", h, json={
            "item_id": it["id"], "chosen": v.choose(it["answer"], opts, 0.6), "options": opts,
            "rt_from_onset_ms": v.rng.randint(1500, 7000), "talker": ("t1", "t2", "t3", "t4")[k % 4], "hint_used": k % 3 == 0})
    sent = "오늘은 날씨가 맑아요"
    opts = [sent, "오늘은 날씨가 흐려요", "어제는 날씨가 맑았어요", "내일은 비가 와요"]
    api.post("/api/progress", h, json={"scenario_id": "rehearsal-1", "sentence": sent, "user_answer": sent,
                                       "time_spent_seconds": 12, "situation": "일상", "difficulty_level": 1,
                                       "answer_mode": "choice", "speed": 1.0, "rt_from_onset_ms": 5200, "talker": "t2",
                                       "hint_level": 0, "options": opts})
    api.post("/api/progress", h, json={"scenario_id": "rehearsal-1", "sentence": sent, "user_answer": MARK_TRAINING,
                                       "time_spent_seconds": 20, "situation": "일상", "difficulty_level": 1,
                                       "answer_mode": "typed", "speed": 0.75, "rt_from_onset_ms": 9100, "talker": "t3",
                                       "hint_level": 1})
    for sid, resp, rating in ((f"rh-{v.idx}-a", "answered", 4), (f"rh-{v.idx}-b", "skipped", None)):
        api.post("/api/lesson/effort", h, json={"session_id": sid, "lesson_kind": "closure", "stage": 3, "rating": rating,
                                                "response": resp, "n_items": n_closure, "accuracy": 0.6,
                                                "render_log": render_log("avatar3d", v.rng) | {"scope": "lesson"}})
    log["reading_train_trials"] = len(items) + 2


def run(api, n_participants=6, seed=20261007, manifest=None, out_dir=None, analyze=True, reset_one=True,
        operator_email="rehearsal-op@example.com"):
    t0 = time.time()
    op, _ = register(api, operator_email, "rh_operator", "10.9.0.1")
    people = []
    for i in range(n_participants):
        code = GROUP_PATTERN[i % len(GROUP_PATTERN)]
        ip = f"10.9.{i + 1}.1"
        h, _ = register(api, f"rehearsal{i + 1}@example.com", f"rh_person{i + 1}", ip)
        api.post("/api/pilot/join", h, json={"code": code})
        people.append({"i": i, "code": code, "h": h, "v": Virtual(i, code, seed), "log": {}})
    # 사전: 한 사람씩 처음 검사 화면을 연다(참여 순번이 겹치지 않게, battery.md 1절)
    for p in people:
        h, v, log = p["h"], p["v"], p["log"]
        st = api.get("/api/pilot/battery/status", h).json()
        log["seq"], log["order"] = st["seq"], st["order"]
        placement(api, h, v, "A", "A1", log)
        battery_label(api, h, v, manifest, "A1", log)
        h["fly-client-ip"] = h["fly-client-ip"][:-1] + "2"   # 회차마다 다른 주소(검사 답 요청 수 제한을 리허설이 넘지 않게)
        battery_label(api, h, v, manifest, "A2", log)
        listen_test(api, h, v, "babble", "pre", log)
        listen_test(api, h, v, "talker2", "pre", log)
        listen_wordtest(api, h, v, "pre", log)
    # 훈련
    for p in people:
        h, v, log = p["h"], p["v"], p["log"]
        if p["v"].group == "RH_TRAIN":
            train_listen(api, h, v, log)
            train_reading(api, h, v, 3, log)
        else:
            train_reading(api, h, v, 6, log)
    # 사후와 유지 검사 예약
    for p in people:
        h, v, log = p["h"], p["v"], p["log"]
        h["fly-client-ip"] = h["fly-client-ip"][:-1] + "3"
        placement(api, h, v, "B", "B", log)
        st = battery_label(api, h, v, manifest, "B", log)
        listen_test(api, h, v, "babble", "post", log)
        listen_test(api, h, v, "talker2", "post", log)
        listen_wordtest(api, h, v, "post", log)
        st = api.get("/api/pilot/battery/status", h).json()
        r = next(x for x in st["labels"] if x["label"] == "R")
        log["retention_battery"] = {"available": r["available"], "schedule": r.get("schedule")}
        log["retention_placement"] = api.get("/api/assessment/retention", h).json()
        if p["i"] == 0:
            # 한 사람은 유지 검사(R)를 바로 본다(예정일 전이어도 막지 않는다). 내보내기의 R 행과 분석의 R − A2 경로를 확인한다
            battery_label(api, h, v, manifest, "R", log)
    reset = None
    if reset_one and people:
        p = people[-1]
        reset = api.post("/api/account/learning-reset", p["h"], params={"confirm": True}).json()
    ex = api.get("/api/pilot/export", op, params={"trials": True}).json()
    checks = check_export(ex, people, manifest, reset)
    report = {"elapsed_s": round(time.time() - t0, 1), "api_calls": api.calls, "n_participants": n_participants,
              "participants": [{"i": p["i"], "group": p["v"].group, **{k: v for k, v in p["log"].items()}} for p in people],
              "reset": reset, **checks}
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "export.json"), "w", encoding="utf-8") as fh:
            json.dump(ex, fh, ensure_ascii=False, indent=1)
    if analyze and out_dir:
        sys.path.insert(0, HERE)
        import pilot_analyze as PA
        res = PA.analyze(ex, p3_cohorts=list(CODES.values()), listen_train=[CODES["RH_TRAIN"]],
                         listen_control=[CODES["RH_CTRL"]], allow_avatar=True)
        PA.write_outputs(res, os.path.join(out_dir, "analysis"))
        report["analysis"] = {"p3_primary": res["p3"]["primary"], "p3_sequential_last": (res["p3"]["sequential"]["looks"] or [None])[-1],
                              "listen_primary": res["listen"]["primary"], "warnings": res["warnings"]}
        report["checks"].append(_chk("분석 스크립트가 P3 주지표를 계산했다", res["p3"]["primary"].get("estimate") is not None,
                                     res["p3"]["primary"]))
        report["checks"].append(_chk("분석 스크립트가 소리 듣기 집단 차이를 계산했다",
                                     res["listen"]["primary"].get("diff") is not None, res["listen"]["primary"]))
    report["ok"] = all(c["ok"] for c in report["checks"]) and all(f["ok"] for f in report["fields"])
    if out_dir:
        with open(os.path.join(out_dir, "rehearsal_report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    return report


# ───────────────────────── 내보내기 검사 ─────────────────────────
def _chk(name, ok, detail=None):
    return {"check": name, "ok": bool(ok), **({"detail": detail} if detail is not None and not ok else {})}


def _field(stats, path, values, required=True, allow=()):
    """값 목록의 null 비율. required면 null이 하나도 없어야 통과(allow에 든 값은 null로 보지 않는다)."""
    n = len(values)
    nul = sum(1 for x in values if x is None and None not in allow)
    stats.append({"field": path, "n": n, "n_null": nul, "null_ratio": round(nul / n, 3) if n else None,
                  "required": required, "ok": (n > 0 and nul == 0) if required else True})


# 분석에 쓰는 필드(log-spec-audit-2026-10-07.md 3절 표의 '분석 계획' 열)
OPEN_FIELDS = ("seq", "item_id", "talker", "modality", "target", "answer_text", "app_score", "auto_phoneme_acc", "auto_word_acc",
               "n_matched_phonemes", "n_target_phonemes", "scorer_version", "rt_ms", "rt_from_onset_ms", "plays", "speed")
CLOSED_FIELDS = ("seq", "item_id", "talker", "modality", "target", "options", "chosen", "correct", "rt_ms", "rt_from_onset_ms",
                 "plays", "speed")
SESSION_FIELDS = ("session_label", "layer", "form", "form_version", "manifest_sha", "planned_order", "modality", "started_on",
                  "completed", "n_items", "n_ready", "missing")


def check_export(ex, people, manifest, reset) -> dict:
    checks, fields = [], []
    parts = ex.get("participants") or []
    checks.append(_chk("내보내기 판이 7 이상", (ex.get("version") or 0) >= 7, ex.get("version")))
    checks.append(_chk("참여자 수가 맞다", len(parts) == len(people), len(parts)))
    text = json.dumps(ex, ensure_ascii=False)
    leaks = [s for s in ["@example.com", "rh_person", MARK_TRAINING] if s in text]
    checks.append(_chk("이메일·사용자명·학습 입력 문장이 없다", not leaks, leaks))
    pk = ("pid", "cohort", "joined_on", "join_seq", "planned_order", "b_completed_seq", "battery", "tests", "listen",
          "reading_days", "trial_log", "progress_log", "lesson_efforts", "battery_schedule")
    for k in pk:
        _field(fields, f"participants[].{k}", [p.get(k) for p in parts])
    # 순서 배정: 순번 i의 순서 = ORDERS[(i − 1) % 3], A1·A2·B 폼이 모두 다르고 계획과 같다
    orders = {p["join_seq"]: p["planned_order"] for p in parts if p.get("join_seq")}
    checks.append(_chk("폼 순서가 순번대로 ABC·BCA·CAB", all(o == ("ABC", "BCA", "CAB")[(s - 1) % 3] for s, o in orders.items()), orders))
    bad_forms = []
    for p in parts:
        lab = {}
        for b in p.get("battery") or []:
            lab.setdefault(b["session_label"], set()).add(b["form"])
        fs = [next(iter(lab.get(x, {None}))) for x in ("A1", "A2", "B")]
        if len({f for f in fs if f}) != 3 or "".join(f or "?" for f in fs) != p.get("planned_order"):
            bad_forms.append((p["pid"], fs, p.get("planned_order")))
    checks.append(_chk("한 사람의 A1·A2·B 폼이 서로 다르고 계획과 같다", not bad_forms, bad_forms))
    checks.append(_chk("B 완료 순번이 1부터 빈틈없다", sorted(p["b_completed_seq"] for p in parts if p.get("b_completed_seq"))
                       == list(range(1, sum(1 for p in parts if p.get("b_completed_seq")) + 1))))
    rows = [b for p in parts for b in (p.get("battery") or [])]
    for k in SESSION_FIELDS:
        _field(fields, f"battery[].{k}", [b.get(k) for b in rows])
    done_rows = [b for b in rows if b["completed"]]
    _field(fields, "battery[completed].completed_on", [b.get("completed_on") for b in done_rows])
    _field(fields, "battery[completed].render_log", [b.get("render_log") for b in done_rows])
    for rk in ("frames", "mean_late_ms", "over20_rate", "screen_hz_est", "device_class", "os_family", "browser_family",
               "render_mode", "webgl"):
        _field(fields, f"battery[completed].render_log.{rk}", [(b.get("render_log") or {}).get(rk) for b in done_rows])
    vid = [b for b in done_rows if b["layer"] in ("word", "snr", "av") and b["n_ready"] > 0]
    if vid:
        _field(fields, "battery[video].render_log.video_drop_rate", [(b.get("render_log") or {}).get("video_drop_rate") for b in vid])
    opens = [(b, r) for b in rows if b.get("open") for r in b["open"]]
    closeds = [(b, r) for b in rows if b.get("closed") for r in b["closed"]]
    for k in OPEN_FIELDS:
        _field(fields, f"battery[].open[].{k}", [r.get(k) for _, r in opens])
    for k in CLOSED_FIELDS:
        _field(fields, f"battery[].closed[].{k}", [r.get(k) for _, r in closeds])
    ns = [r for b, r in closeds if b["layer"] == "nonsense"]
    for k in ("target_consonants", "chosen_consonants", "consonant_hits"):
        _field(fields, f"battery[nonsense].closed[].{k}", [r.get(k) for r in ns])
    snr_rows = [b for b in done_rows if b["layer"] == "snr" and b["n_ready"] > 0]
    av_rows = [b for b in rows if b["layer"] == "av" and b["n_ready"] > 0]
    if snr_rows:
        for k in ("snr_calibrated_db", "snr_estimate_kind", "snr_reversals", "headphone_check", "volume_fixed"):
            _field(fields, f"battery[snr].{k}", [b.get(k) for b in snr_rows])
        for k in ("snr_db", "criterion_met", "noise_type"):
            _field(fields, f"battery[snr].open[].{k}", [r.get(k) for b in snr_rows for r in b["open"]])
    if av_rows:
        _field(fields, "battery[av].snr_calibrated_db", [b.get("snr_calibrated_db") for b in av_rows])
        for k in ("snr_db", "noise_type"):
            _field(fields, f"battery[av].open[].{k}", [r.get(k) for b in av_rows for r in b["open"]])
        checks.append(_chk("소음 속 문장 응답이 A·AV 둘 다 있다", {r["modality"] for b in av_rows for r in b["open"]} == {"A", "AV"}))
    # 반응 시간·재생 규칙
    maxp = (manifest or {}).get("playback", {}).get("max_plays", 2)
    resp = [r for _, r in opens + closeds]
    checks.append(_chk("rt_ms ≤ rt_from_onset_ms", all(r["rt_ms"] <= r["rt_from_onset_ms"] for r in resp
                                                       if r.get("rt_ms") is not None and r.get("rt_from_onset_ms") is not None)))
    checks.append(_chk(f"plays가 1~{maxp}", all(1 <= (r.get("plays") or 0) <= maxp for r in resp)))
    checks.append(_chk("검사 재생 속도가 1.0", all(r.get("speed") == 1.0 for r in resp)))
    # 영상 준비 전(missing): 회차 행이 남고 missing 합 = 문항 수 − 준비 수, 응답 수 ≤ 준비 수
    bad_missing = [(b["session_label"], b["layer"], b["n_items"], b["n_ready"], b["missing"]) for b in rows
                   if sum((b.get("missing") or {}).values()) != b["n_items"] - b["n_ready"]]
    checks.append(_chk("missing 합 = 문항 수 − 준비된 수", not bad_missing, bad_missing))
    word_rows = [b for b in rows if b["layer"] == "word"]
    checks.append(_chk("실제 얼굴 낱말 층에 '영상 준비 전'(missing.media)이 남는다",
                       word_rows and all((b.get("missing") or {}).get("media", 0) > 0 for b in word_rows),
                       [(b["session_label"], b["missing"]) for b in word_rows]))
    over = [(b["session_label"], b["layer"]) for b in rows if len((b.get("open") or b.get("closed") or [])) > b["n_ready"]]
    checks.append(_chk("응답 수가 준비된 문항 수를 넘지 않는다", not over, over))
    # 개방형 답 원문: 검사 문항에서만(학습 입력은 위 표지로 확인)
    checks.append(_chk("개방형 검사 답 원문이 남는다", any((r.get("answer_text") or "") for _, r in opens)))
    # 표준검사(아바타 A·B)
    tests = [t for p in parts for t in (p.get("tests") or [])]
    for k in ("form", "form_version", "accuracy", "date", "items", "trials_before"):
        _field(fields, f"tests[].{k}", [t.get(k) for t in tests])
    # 학습 시행
    tl = [t for p in parts for t in (p.get("trial_log") or [])]
    for k in ("day", "stage", "item_type", "target", "options", "item_id", "talker", "rt_from_onset_ms", "hint_used"):
        _field(fields, f"trial_log[].{k}", [t.get(k) for t in tl])
    pl = [t for p in parts for t in (p.get("progress_log") or [])]
    for k in ("answer_mode", "speed", "hint_level", "talker", "rt_from_onset_ms", "score"):
        _field(fields, f"progress_log[].{k}", [t.get(k) for t in pl])
    le = [t for p in parts for t in (p.get("lesson_efforts") or [])]
    _field(fields, "lesson_efforts[].response", [t.get("response") for t in le])
    _field(fields, "lesson_efforts[].render_log", [t.get("render_log") for t in le])
    checks.append(_chk("노력 문항의 건너뜀(skipped)이 남는다", any(t.get("response") == "skipped" for t in le)))
    rd = [d for p in parts for d in (p.get("reading_days") or [])]
    for k in ("day", "n", "minutes"):
        _field(fields, f"reading_days[].{k}", [d.get(k) for d in rd])
    # 소리 듣기
    lt = [t for p in parts for t in ((p.get("listen") or {}).get("tests") or [])]
    for k in ("session", "form", "noise", "sim", "n", "n_practice", "srt_db", "started_on"):
        _field(fields, f"listen.tests[].{k}", [t.get(k) for t in lt])
    checks.append(_chk("소리 듣기 검사가 babble·talker2 모두, 모두 인공와우 모의", {t["noise"] for t in lt} == {"babble", "talker2"}
                       and all(t.get("sim") == "ci" for t in lt)))
    bad_lf = []
    for p in parts:
        for noise in ("babble", "talker2"):
            fs = [t["form"] for t in (p.get("listen") or {}).get("tests", []) if t["noise"] == noise]
            if len(fs) < 2 or fs[0] == fs[1]:
                bad_lf.append((p["pid"], noise, fs))
    checks.append(_chk("소리 듣기 사전·사후 폼이 다르다", not bad_lf, bad_lf))
    first_forms = {(p.get("listen") or {}).get("tests", [{}])[0].get("form") for p in parts if (p.get("listen") or {}).get("tests")}
    checks.append(_chk("소리 듣기 검사 폼 순서가 A→B와 B→A 둘 다 나온다", first_forms == {"A", "B"}, sorted(first_forms)))
    wt = [t for p in parts for t in ((p.get("listen") or {}).get("word_tests") or [])]
    for k in ("accuracy", "complete", "sim", "started_on"):
        _field(fields, f"listen.word_tests[].{k}", [t.get(k) for t in wt])
    ld = [d for p in parts for d in ((p.get("listen") or {}).get("days") or [])]
    for k in ("day", "n", "minutes", "n_ci"):
        _field(fields, f"listen.days[].{k}", [d.get(k) for d in ld])
    lg = [r for p in parts for r in ((p.get("listen") or {}).get("log") or [])]
    for k in ("stage", "mode", "item_key", "correct", "sim", "route"):
        _field(fields, f"listen.log[].{k}", [r.get(k) for r in lg])
    checks.append(_chk("소리 듣기 훈련 답 원문은 싣지 않는다", all(r.get("answer") is None for r in lg if r["mode"] not in ("test", "wordtest"))))
    # 유지 검사 예약
    sch = [p.get("battery_schedule") or {} for p in parts]
    checks.append(_chk("B를 마친 참여자 모두 유지 검사 예정일이 있다(waiting, R을 본 사람은 done)",
                       all(s.get("state") in ("waiting", "done") and s.get("due_on") for s in sch)
                       and sum(s.get("state") == "done" for s in sch) == 1, sch))
    r_rows = [b for b in rows if b["session_label"] == "R"]
    checks.append(_chk("유지 검사(R)는 B와 같은 폼이다", r_rows and all(
        b["form"] == next(x["form"] for p in parts for x in p["battery"] if x["session_label"] == "B" and x["layer"] == b["layer"]
                          and b in p["battery"]) for b in r_rows)))
    # 학습 초기화(마지막 참여자): P3 기록과 소리 듣기 검사가 남는다
    if reset is not None:
        kept = reset.get("kept") or {}
        checks.append(_chk("학습 초기화 뒤에도 P3 회차·표준검사·소리 듣기 검사가 남는다",
                           kept.get("p3_test_sessions", 0) > 0 and kept.get("placement_results_ab") == 2 and kept.get("listen_tests", 0) > 0,
                           kept))
        last = max(parts, key=lambda p: p.get("join_seq") or 0) if parts else {}
        checks.append(_chk("초기화한 참여자의 내보내기에 소리 듣기 사전·사후 검사가 남는다",
                           len((last.get("listen") or {}).get("tests") or []) == 4 and last.get("learning_reset_on")))
    return {"checks": checks, "fields": fields}


def main(argv=None):
    ap = argparse.ArgumentParser(description="파일럿 리허설 자동화(P0)")
    ap.add_argument("--participants", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--media", choices=("partial", "none"), default="partial")
    ap.add_argument("--out", default=None, help="보고서·내보내기·분석 결과 폴더(없으면 임시 폴더에 쓰고 지운다)")
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--base-url", default=None, help="이미 띄운 개발 서버(운영 서버 아님)")
    ap.add_argument("--operator-email", default="rehearsal-op@example.com")
    a = ap.parse_args(argv)
    tmp = tempfile.mkdtemp(prefix="liplab-rehearsal-")
    out_dir = os.path.abspath(a.out) if a.out else os.path.join(tmp, "out")
    try:
        if a.base_url:
            import httpx
            sys.path.insert(0, BACKEND)
            import pilot_battery as pb
            client = httpx.Client(base_url=a.base_url, timeout=120)
            rep = run(Api(client), a.participants, a.seed, pb.load_manifest(), out_dir, not a.no_analyze,
                      operator_email=a.operator_email)
        else:
            env = _local_env(tmp, a.media)
            from fastapi.testclient import TestClient
            import main as app_main
            with TestClient(app_main.app) as c:
                rep = run(Api(c), a.participants, a.seed, env["manifest"], out_dir, not a.no_analyze)
            rep["media_files"] = env["media_files"]
        failed = [c for c in rep["checks"] if not c["ok"]] + [f for f in rep["fields"] if not f["ok"]]
        print(f"리허설: 참여자 {rep['n_participants']}명, API {rep['api_calls']}회, {rep['elapsed_s']}초")
        print(f"검사 {len(rep['checks'])}개 중 실패 {sum(not c['ok'] for c in rep['checks'])}, "
              f"필드 {len(rep['fields'])}개 중 실패 {sum(not f['ok'] for f in rep['fields'])}")
        for f in failed:
            print("  실패:", f.get("check") or f.get("field"), json.dumps(f.get("detail", f), ensure_ascii=False)[:300])
        if a.out:
            print("결과:", os.path.abspath(out_dir))
        print("RESULT " + json.dumps({"ok": rep["ok"], "n_failed": len(failed)}, ensure_ascii=False))
        return 0 if rep["ok"] else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # 임시 DB·매체(결과는 --out에 남는다)


if __name__ == "__main__":
    sys.exit(main())
