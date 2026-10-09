#!/usr/bin/env python3
"""AI Hub 608 TS02에서 범주 27(전음성) 새 화자의 문장 낭독 세션을 흘려받는다(2026-10-09, '다른 청각장애 집단' 확인용).

선택 규칙(받기 전에 정함, liplab-integrate docs/newdata-608c27-538-2026-10.md 2절과 같다. 라벨만 본다):
  - 화자 키 = 이니셜-성별-나이(aihub608.Picker.speaker_key). 이미 어떤 분석에든 쓴 범주 27 화자(맥 hi608의 wav·wav16·pair16·pair_wav·
    wav16_new에 범주 27 파일이 있는 화자 24명, KSC e27도 같은 pair16 22명)는 뺀다. 이니셜·성별이 같고 나이 차가 2살 이하인 화자도
    같은 사람일 수 있어 뺀다.
  - 쓸 수 있는 세션: 과제 02(문장 낭독, 이름의 여섯째 칸이 02), 라벨 문장부호(. ? !) 10개 이상, playTime 20분 이하.
  - 화자마다 02-01(이야기 문장)과 02-02(평서·의문 짧은 문장) 갈래에서 각각 playTime이 가장 짧은 세션 하나(같으면 이름 순). 최대 2세션.
  - 화자 순서 = 흘려받는 순서(파일 이름 순, 이니셜 가나다순). 쓸 수 있는 세션이 있는 화자 가운데 처음 30명.
  - 아카이브에서 범주 27은 약 6~93GB 구간에 이름 순으로 들어 있어, 30명째 화자를 지나면 흘려받기를 멈춘다.
저장: data/hi608/c27/wav48(받는 중 원본, FLAC 변환 뒤 지움) → data/hi608/c27/flac16(16kHz 단일 채널 FLAC). 기존 hi608 폴더는 건드리지 않는다.
디스크: 맥 여유가 8GB 아래로 떨어지면 받기를 멈춘다(DISK_STOP). 키·서명 URL은 aihub608.Fetcher가 0600 임시 파일로만 다루고 출력하지 않는다.

  python3 tools/fetch608_c27.py --dry-run          # 네트워크 없음: 고른 화자·세션·용량
  python3 tools/fetch608_c27.py --probe            # 키 확인만(302)
  nohup caffeinate -i python3 tools/fetch608_c27.py > data/hi608/c27/fetch.log 2>&1 &
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aihub608 as A  # noqa: E402

LAB = A.LAB
HI = os.path.join(LAB, "data/hi608")
OUT = os.path.join(HI, "c27")
WAV = os.path.join(OUT, "wav48")
FLAC = os.path.join(OUT, "flac16")
N_SPK = 30
MIN_SENT, MAX_MIN = 10, 20.0
MIN_FREE_GB = 8.0
USED_DIRS = ("wav", "wav16", "pair16", "pair_wav", "wav16_new", "wav_new")


def free_gb(path=LAB):
    return shutil.disk_usage(path).free / 1e9


def spk_key(stem):
    return A.Picker.speaker_key(stem + ".wav")


def used_keys():
    keys = set()
    for d in USED_DIRS:
        for f in glob.glob(os.path.join(HI, d, "*")):
            b = os.path.basename(f).rsplit(".", 1)[0]
            if "-27-" in b:
                keys.add(spk_key(b))
    return keys


def near_used(key, used):
    """이니셜·성별이 같고 나이 차 ≤ 2이면 같은 사람일 수 있다."""
    try:
        ini, sex, age = key.split("-")
        age = int(age)
    except ValueError:
        return key in used
    for u in used:
        try:
            ui, us, ua = u.split("-")
            if ui == ini and us == sex and abs(int(ua) - age) <= 2:
                return True
        except ValueError:
            continue
    return False


def labels27():
    rows = []
    for p in sorted(glob.glob(os.path.join(HI, "labels", "*", "*.json"))):
        cat = unicodedata.normalize("NFC", os.path.basename(os.path.dirname(p)))
        if not cat.startswith("27."):
            continue
        stem = os.path.basename(p)[:-5]
        d = json.load(open(p, encoding="utf-8"))
        parts = stem.split("-")
        rows.append({"stem": stem, "key": spk_key(stem), "task": parts[5],
                     "sub": parts[6] if parts[6] not in ("M", "F") else "",
                     "min": round(float(d.get("playTime") or 0) / 60, 2),
                     "nsent": len(re.findall(r"[.?!]", d.get("Transcript", "")))})
    return rows


def select():
    used = used_keys()
    rows = labels27()
    by = {}
    for r in rows:
        if r["task"] != "02" or r["sub"] not in ("01", "02") or r["nsent"] < MIN_SENT or r["min"] > MAX_MIN:
            continue
        if r["key"] in used or near_used(r["key"], used):
            continue
        by.setdefault(r["key"], []).append(r)
    order = sorted(by, key=lambda k: min(x["stem"] for x in by[k]))
    chosen = []
    for k in order[:N_SPK]:
        for sub in ("01", "02"):
            c = sorted((x for x in by[k] if x["sub"] == sub), key=lambda x: (x["min"], x["stem"]))
            if c:
                chosen.append(dict(c[0], group=sub))
    return used, order, chosen


def shrink_one(wav):
    b = os.path.basename(wav)[:-4]
    dst = os.path.join(FLAC, b + ".flac")
    part = os.path.join(FLAC, b + ".part.flac")
    r = subprocess.run(["nice", "-n", "15", "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", wav,
                        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", part])
    if r.returncode == 0 and os.path.exists(part) and os.path.getsize(part) > 0:
        os.replace(part, dst)
        os.remove(wav)
        print("  SHRINK_OK %s %.1fMB free=%.1fGB" % (b, os.path.getsize(dst) / 1e6, free_gb()), flush=True)
        return True
    if os.path.exists(part):
        os.remove(part)
    print("  SHRINK_FAIL %s" % b, flush=True)
    return False


class Shrinker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()

    def sweep(self):
        for w in sorted(glob.glob(os.path.join(WAV, "*.wav"))):
            shrink_one(w)

    def run(self):
        while not self.stop.wait(20):
            self.sweep()


class C27Picker:
    """want에 든 세션만 고른다. 범주 27보다 뒤 범주가 나오거나 마지막 대상 이름을 지나면 끝난 것으로 본다. 디스크가 모자라면 멈춘다."""

    def __init__(self, want, last_stem):
        self.want = set(want)
        self.last = last_stem
        self.picked = set()
        self.passed = False
        self.disk_stop = False
        self._n = 0

    @property
    def done(self):
        return self.passed or self.disk_stop

    def wants(self, base, name):
        self._n += 1
        if self._n % 5 == 0 and free_gb() < MIN_FREE_GB:
            self.disk_stop = True
            print("DISK_STOP free=%.1fGB < %.1fGB" % (free_gb(), MIN_FREE_GB), flush=True)
            return False
        c = A.category_of(name)
        stem = os.path.splitext(base)[0]
        if (c is not None and c > 27) or (c == 27 and stem > self.last):
            self.passed = True
        return base in self.want and not os.path.exists(os.path.join(FLAC, stem + ".flac"))

    def mark(self, base):
        self.picked.add(base)


class StopStream(A.TarStream):
    """picker.done이 되면 EOF처럼 끝난다(남은 아카이브를 흘려받지 않는다). 받던 파일은 CRC가 맞지 않아 버려진다."""

    def __init__(self, raw, picker):
        super().__init__(raw)
        self.picker = picker

    def read(self, n):
        if self.picker.done:
            return b""
        return super().read(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--retries", type=int, default=2)
    a = ap.parse_args()
    used, order, chosen = select()
    spk = sorted({c["key"] for c in chosen})
    tot = sum(c["min"] for c in chosen)
    print("C27_SELECT used=%d eligible_speakers=%d chosen_speakers=%d sessions=%d minutes=%.0f flac16_GB~%.2f last=%s" %
          (len(used), len(order), len(spk), len(chosen), tot, tot * 60 * 32000 * 0.6 / 1e9, max(c["stem"] for c in chosen)),
          flush=True)
    if a.dry_run:
        for c in chosen:
            print("  %s %-10s %s %5.1fmin %3d" % (c["group"], c["key"], c["stem"], c["min"], c["nsent"]))
        return
    os.makedirs(WAV, exist_ok=True)
    os.makedirs(FLAC, exist_ok=True)
    json.dump({"used_keys": sorted(used), "eligible_order": order, "chosen": chosen}, open(os.path.join(OUT, "select.json"), "w"),
              ensure_ascii=False, indent=1)
    f = A.Fetcher(A.KEYFILE)
    if a.probe:
        f.resolve()
        print("C27_PROBE_OK", flush=True)
        return
    if free_gb() < MIN_FREE_GB + 1:
        sys.exit("여유 %.1fGB: 시작하지 않음" % free_gb())
    want = {c["stem"] + ".wav" for c in chosen}
    last = max(c["stem"] for c in chosen)
    done = lambda: {os.path.basename(p)[:-5] + ".wav" for p in glob.glob(os.path.join(FLAC, "*.flac"))}  # noqa: E731
    print("C27_FETCH start %s want=%d have=%d free=%.1fGB" % (time.strftime("%F %T"), len(want), len(want & done()), free_gb()), flush=True)
    sh = Shrinker()
    sh.start()
    why = "skip"
    picker = None
    for attempt in range(a.retries + 1):
        left = want - done()
        if not left:
            break
        picker = C27Picker(left, last)
        f.resolve()
        cfg = f._private('url = "%s"\n' % f.signed.replace('"', '%22'))
        proc = subprocess.Popen(["curl", "-sS", "--connect-timeout", "30", "--speed-limit", "20000", "--speed-time", "180",
                                 "-o", "-", "-K", cfg], stdout=subprocess.PIPE, stderr=sys.stderr)
        try:
            got, why = A.stream_zip(StopStream(proc.stdout, picker), set(left), WAV, every_gb=2.0, picker=picker)
        finally:
            proc.kill()
            proc.wait()
            if os.path.exists(cfg):
                os.remove(cfg)
            f.signed = None
        sh.sweep()
        print("C27_FETCH pass=%d reason=%s passed=%s disk_stop=%s have=%d/%d free=%.1fGB %s" %
              (attempt + 1, why, picker.passed, picker.disk_stop, len(want & done()), len(want), free_gb(), time.strftime("%F %T")),
              flush=True)
        if picker.done or why in ("central_dir", "data_descriptor", "all"):
            break
    sh.stop.set()
    sh.sweep()
    have = done()
    per = {}
    for c in chosen:
        per.setdefault(c["key"], []).append(c["stem"] + ".wav" in have)
    summ = {"finished": time.strftime("%F %T"), "last_reason": why, "disk_stop": bool(picker and picker.disk_stop),
            "sessions_have": len(want & have), "sessions_want": len(want),
            "speakers_with_any": sorted(k for k, v in per.items() if any(v)),
            "missing": sorted(c["stem"] for c in chosen if c["stem"] + ".wav" not in have), "free_gb": round(free_gb(), 1)}
    json.dump(summ, open(os.path.join(OUT, "fetch_summary.json"), "w"), ensure_ascii=False, indent=1)
    print("C27_FETCH_OK sessions=%d/%d speakers=%d/%d reason=%s disk_stop=%s" % (summ["sessions_have"], len(want),
          len(summ["speakers_with_any"]), len(per), why, summ["disk_stop"]), flush=True)


if __name__ == "__main__":
    main()
