#!/usr/bin/env python3
"""V7b 538 전문가 배치 받기(2026-10-09, 앱 docs/newdata-608c27-538-2026-10.md 3절). 맥 전용(AI Hub는 한국 IP만), 한 번에 하나씩.

  survey SPK...        라벨 tar 전체를 흘려 읽어 문장 해시 요약(data/v18/tl_experts_full_c.jsonl)과, 전문가(E) 정면 라벨 JSON의 필요한 부분
                       (Video_info·Sentence_info·speaker_info 등, 얼굴 상자 제외)을 data/v18/v7b_dl2/js/에 남긴다.
  plan                 v7b_read_spont.plan_conditions(10/9 7.4절 규칙)로 전문가 인물마다 낭독·자유발화 대본을 정한다
                       (문장 모음 = tl_survey + tl_experts_full + tl_experts_full_c) → data/v18/v7b_plan2_persons.json
  video SPK [--person P]  영상 tar를 처음부터 흘려 읽는다. --person이 없으면(새 배치) 안쪽 첫 mp4가 E###_A_001이고 그 인물이 두 조건을
                       갖출 때만 쓴다. 쓰는 배치는 계획한 대본의 정면 mp4만 저장하고, 다 모이거나 7.5 GB를 읽으면 멈춘다.
  labels SPK           (3.1의 옛 배치) 라벨 tar를 흘려 읽어 필요한 JSON만 js/에 남긴다
  cut SPK              dl_more.sh와 같은 규칙으로 문장 클립을 자르고(parse_sentences --full, 가드, ffmpeg 30fps·640·AAC + 16kHz wav, 검사)
                       clips/, manifest.tsv, manifest_clips.tsv, manifest_meta.tsv에 더한 뒤 mp4를 지운다
  run SPK...           video → (labels) → cut을 화자마다 차례로
키는 .aihub.key를 0600 임시 헤더 파일로만 curl에 넘기고 출력하지 않는다. 맥 여유가 8 GB 아래면 멈춘다.
"""
import argparse
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unicodedata
import zlib

LAB = os.path.expanduser("~/Downloads/liplab-lab")
V18 = f"{LAB}/data/v18"
ROOT = os.environ.get("V7B_ROOT", f"{V18}/v7b_dl2")
JS, MP4, CLIPS = f"{ROOT}/js", f"{ROOT}/mp4", f"{ROOT}/clips"
KEYF = f"{LAB}/.aihub.key"
URL = "https://api.aihub.or.kr/down/0.6/538.do?fileSn="
MAP = f"{LAB}/data/spkmap538_full.tsv"
APP = os.path.expanduser("~/Downloads/liplab-wt-newdata")
PARSE = f"{LAB}/tools/parse_sentences.py"
MAX_VIDEO_BYTES = 7_500_000_000
MIN_FREE_GB = 8.0
NAME_RE = re.compile(r"_([CE]\d+)_([A-Z])_(\d{3})$")
KEEP_KEYS = ("dataSet", "Video_info", "Audio_info", "Audio_env", "Video_env", "Sentence_info", "speaker_info")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def free_gb():
    return shutil.disk_usage(LAB).free / 1e9


def batches():
    out = {}
    for l in open(MAP):
        if l.startswith("#"):
            continue
        spk, vsn, lsn, st = l.rstrip("\n").split("\t")
        out[spk] = {"vsn": vsn, "lsn": lsn, "set": st}
    # spkNNN = trNNN + 296(dl_more 규칙). spkmap538_full.tsv는 trN·vaN 이름이다.
    m = {}
    for k, v in out.items():
        if k.startswith("tr"):
            m["spk%d" % (int(k[2:]) + 296)] = v
        elif k.startswith("va"):
            m["spk%d" % (int(k[2:]) + 600)] = v
    return m


def sh(t):
    return hashlib.sha1(unicodedata.normalize("NFC", " ".join(str(t).split())).encode()).hexdigest()[:10]


class Stream:
    """curl … | bsdtar -xOf - (바깥 tar의 조각을 이어 붙인 안쪽 아카이브 바이트). 읽은 바이트를 센다."""

    def __init__(self, sn, max_time=5400):
        fd, self.hf = tempfile.mkstemp(prefix="h.")
        os.close(fd)
        os.chmod(self.hf, 0o600)
        with open(self.hf, "w") as f:
            f.write("apikey:%s\n" % open(KEYF).read().strip())
        rate = os.environ.get("LIPLAB_LIMIT_RATE")    # 예: 2M. 회선을 다른 일에 양보할 때(10/9 사용자 요청)
        lim = f"--limit-rate {rate} " if rate else ""
        cmd = (f"curl -sS -L --connect-timeout 30 --max-time {max_time} {lim}-H @{self.hf} '{URL}{sn}' 2>/dev/null"
               f" | bsdtar -xOf - 2>/dev/null")
        if os.environ.get("V7B_MOCK"):                 # 오프라인 시험: 네트워크 대신 로컬 tar
            cmd = f"cat '{os.environ['V7B_MOCK']}/{sn}.tar' | bsdtar -xOf - 2>/dev/null"
        self.p = subprocess.Popen(["/bin/bash", "-c", cmd], stdout=subprocess.PIPE, start_new_session=True)
        self.n = 0

    def read(self, k=-1):
        b = self.p.stdout.read(k)
        self.n += len(b)
        return b

    def close(self):
        try:
            os.killpg(self.p.pid, 15)
        except OSError:
            pass
        self.p.wait()
        if os.path.exists(self.hf):
            os.remove(self.hf)


def strip_label(raw):
    d = json.loads(raw)
    lst = isinstance(d, list)
    d0 = d[0] if lst else d
    keep = {k: d0[k] for k in KEEP_KEYS if k in d0}
    return [keep] if lst else keep


# ───────────────────────── survey ─────────────────────────
def cmd_survey(spks):
    B = batches()
    os.makedirs(JS, exist_ok=True)
    out = f"{V18}/tl_experts_full_c.jsonl"
    done = set()
    if os.path.exists(out):
        done = {json.loads(l)["spk"] for l in open(out)}
    for spk in spks:
        if spk in done:
            continue
        b = B[spk]
        s = Stream(b["lsn"], max_time=1800)
        files, err, saved = [], None, 0
        try:
            with tarfile.open(fileobj=s, mode="r|") as tf:
                for m in tf:
                    if not m.isfile() or not m.name.endswith(".json"):
                        continue
                    name = os.path.basename(m.name)[:-5]
                    rec = {"name": name, "size": m.size}
                    try:
                        raw = tf.extractfile(m).read()
                        d = json.loads(raw)
                        d = d[0] if isinstance(d, list) else d
                        si = d.get("Sentence_info") or []
                        rec.update(person=d["speaker_info"].get("speaker_ID"), spec=d["speaker_info"].get("Specificity"),
                                   view=d["Video_env"].get("Angle"), noise=d["Audio_env"].get("Noise"),
                                   dur=d["Video_info"].get("video_Duration"), n_sent=len(si),
                                   topics=sorted({str(x.get("topic")) for x in si}),
                                   texts_sha=[sh(x.get("sentence_text", "")) for x in si])
                        if rec["spec"] == "E" and rec["view"] == "A":
                            json.dump(strip_label(raw), open(f"{JS}/{name}.json", "w"), ensure_ascii=False)
                            saved += 1
                    except Exception as e:
                        rec["bad"] = type(e).__name__
                    files.append(rec)
        except Exception as e:
            err = type(e).__name__
        finally:
            nread = s.n
            s.close()
        with open(out, "a") as fo:
            fo.write(json.dumps({"spk": spk, "lsn": b["lsn"], "files": files, "err": err}, ensure_ascii=False) + "\n")
        log("SURVEY", spk, "files", len(files), "E_A_json", saved, "bytes %.2fGB" % (nread / 1e9), "err", err)
    log("SURVEY_OK")


# ───────────────────────── plan ─────────────────────────
def cmd_plan():
    sys.path.insert(0, f"{APP}/scripts")
    import v7b_read_spont as V
    pool = V.load_pool(f"{V18}/tl_survey.jsonl")
    fulls = [p for p in (f"{V18}/tl_experts_full.jsonl", f"{V18}/tl_experts_full_c.jsonl") if os.path.exists(p)]
    recs = []
    for fp in fulls:
        for l in open(fp, encoding="utf-8"):
            r = json.loads(l)
            recs.append(r)
            for f in r["files"]:
                for h in f.get("texts_sha") or []:
                    pool.setdefault(h, set()).add(f.get("person"))
    plan = {}
    for r in recs:
        persons = sorted({f.get("person") for f in r["files"] if f.get("spec") == "E" and f.get("view") == "A" and f.get("person")})
        for person in persons:
            rows = {}
            for f in r["files"]:
                if f.get("person") != person or f.get("view") != "A":
                    continue
                hs = f.get("texts_sha") or []
                rows[f["name"].rsplit("_", 1)[1]] = sum(1 for h in hs if pool.get(h, set()) - {person}) / max(1, len(hs))
            b = V.plan_conditions(rows)
            plan.setdefault(r["spk"], {})[person] = {"rows": {k: round(v, 3) for k, v in sorted(rows.items())},
                                                    "read": b[0] if b else None, "spont": b[1] if b else None,
                                                    "max_script": b[2] if b else None, "half": V.half_of(r["spk"])}
    json.dump(plan, open(f"{V18}/v7b_plan2_persons.json", "w"), ensure_ascii=False, indent=1)
    for spk in sorted(plan):
        for person, p in plan[spk].items():
            log("PLAN", spk, person, "half", p["half"], "read", p["read"], "spont", p["spont"], "max", p["max_script"])
    log("PLAN_OK")


# ───────────────────────── video ─────────────────────────
def cmd_video(spk, person=None):
    B = batches()
    b = B[spk]
    plan = json.load(open(f"{V18}/v7b_plan2_persons.json"))
    state = f"{ROOT}/state"
    os.makedirs(state, exist_ok=True)
    os.makedirs(MP4, exist_ok=True)
    if free_gb() < MIN_FREE_GB + 2.5:
        log("DISK_STOP before video", spk, "free %.1fGB" % free_gb())
        return 4
    s = Stream(b["vsn"])
    first, want, got, decision = None, set(), [], None
    try:
        with tarfile.open(fileobj=s, mode="r|") as tf:
            for m in tf:
                if not m.isfile() or not m.name.endswith(".mp4"):
                    continue
                base = os.path.basename(m.name)[:-4]
                if base.startswith("._"):
                    continue
                mm = NAME_RE.search(base)
                if first is None:
                    first = base
                    if person is None:                         # 새 배치: 첫 mp4가 전문가 정면 대본 001이어야 한다
                        if not (mm and mm.group(1).startswith("E") and mm.group(2) == "A" and mm.group(3) == "001"):
                            decision = "skip_first_not_E_A_001"
                            break
                        person = mm.group(1)
                    p = plan.get(spk, {}).get(person)
                    if not p or not p["read"] or not p["spont"]:
                        decision = "skip_no_plan_both"
                        break
                    want = {f"_{person}_A_{x}" for x in p["read"] + p["spont"]}
                    log("VIDEO", spk, "first", first, "person", person, "want", sorted(w[-3:] for w in want))
                if mm and any(base.endswith(w) for w in want) and base not in got:
                    dst = f"{MP4}/{base}.mp4"
                    with open(dst + ".part", "wb") as fo:
                        src = tf.extractfile(m)
                        while True:
                            c = src.read(1 << 20)
                            if not c:
                                break
                            fo.write(c)
                    if os.path.getsize(dst + ".part") == m.size:
                        os.replace(dst + ".part", dst)
                        got.append(base)
                        log("  MP4_OK", base, "%.0fMB" % (m.size / 1e6), "at %.2fGB" % (s.n / 1e9), "free %.1fGB" % free_gb())
                    else:
                        os.remove(dst + ".part")
                if want and len(got) == len(want):
                    decision = "all"
                    break
                if s.n > MAX_VIDEO_BYTES:
                    decision = "byte_cap"
                    break
                if free_gb() < MIN_FREE_GB:
                    decision = "disk_stop"
                    break
    except Exception as e:
        decision = decision or f"stream_err:{type(e).__name__}"
    finally:
        nread = s.n
        s.close()
    rec = {"spk": spk, "vsn": b["vsn"], "lsn": b["lsn"], "set": b["set"], "first": first, "person": person, "decision": decision or "eof",
           "want": len(want), "got": got, "bytes": nread, "time": time.strftime("%F %T")}
    json.dump(rec, open(f"{state}/{spk}.video.json", "w"), ensure_ascii=False)
    log("VIDEO_DONE", spk, rec["decision"], "got %d/%d" % (len(got), len(want)), "read %.2fGB" % (nread / 1e9))
    return 0


# ───────────────────────── labels ─────────────────────────
def cmd_labels(spk):
    B = batches()
    v = json.load(open(f"{ROOT}/state/{spk}.video.json"))
    need = {g for g in v["got"] if not os.path.exists(f"{JS}/{g}.json")}
    if not need:
        log("LABELS_OK", spk, "already")
        return 0
    os.makedirs(JS, exist_ok=True)
    s = Stream(B[spk]["lsn"], max_time=1800)
    try:
        with tarfile.open(fileobj=s, mode="r|") as tf:
            for m in tf:
                name = os.path.basename(m.name)
                if m.isfile() and name.endswith(".json") and name[:-5] in need:
                    json.dump(strip_label(tf.extractfile(m).read()), open(f"{JS}/{name}", "w"), ensure_ascii=False)
                    need.discard(name[:-5])
                    if not need:
                        break
    except Exception as e:
        log("LABELS_ERR", type(e).__name__)
    finally:
        nread = s.n
        s.close()
    log("LABELS_DONE", spk, "missing", sorted(need), "read %.2fGB" % (nread / 1e9))
    return 0 if not need else 1


# ───────────────────────── cut(dl_more.sh cut_one·walk와 같은 규칙) ─────────────────────────
def probe(path, *args):
    r = subprocess.run(["ffprobe", "-v", "error", *args, path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.stdout.strip()


def cut_one(src, st, du, tmp):
    for e in (".mp4", ".wav"):
        if os.path.exists(tmp + e):
            os.remove(tmp + e)
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-threads", "2", "-ss", st, "-t", du, "-i", src,
                        "-map", "0:v:0", "-map", "0:a:0?", "-r", "30", "-vf", "scale=640:-2", "-c:v", "libx264", "-preset", "veryfast",
                        "-threads", "2", "-c:a", "aac", "-b:a", "96k", "-ac", "1", tmp + ".mp4",
                        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", tmp + ".wav"],
                       stdin=subprocess.DEVNULL, capture_output=True)
    if r.returncode != 0:
        return None, "ffmpeg"
    wd = probe(tmp + ".wav", "-show_entries", "format=duration", "-of", "csv=p=0")
    nf = probe(tmp + ".mp4", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0")
    na = probe(tmp + ".mp4", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0").split("\n")[0]
    try:
        ok = na == "audio" and abs(float(wd) - float(du)) <= 0.1 and float(nf) >= 0.9 * float(du) * 30
    except ValueError:
        ok = False
    if not ok:
        return None, f"검사(wav={wd} frames={nf} audio={na or 'none'})"
    return (wd, nf), None


def cmd_cut(spk):
    v = json.load(open(f"{ROOT}/state/{spk}.video.json"))
    if os.path.exists(f"{ROOT}/state/{spk}.done"):
        log("CUT_OK", spk, "already")
        return 0
    os.makedirs(CLIPS, exist_ok=True)
    rows, crow, cnt, used, nrej = [], [], 0, [], 0
    for b in sorted(v["got"]):
        mp4 = f"{MP4}/{b}.mp4"
        js = f"{JS}/{b}.json"
        if not os.path.exists(mp4) or not os.path.exists(js):
            log("  CUT_SKIP", b, "mp4" if not os.path.exists(mp4) else "json")
            continue
        vd = probe(mp4, "-show_entries", "format=duration", "-of", "csv=p=0")
        try:
            vint = int(float(vd))
        except ValueError:
            log("  CUT_SKIP", b, "duration")
            continue
        r = subprocess.run([sys.executable, PARSE, "--full", "--expect", b, js], capture_output=True, text=True)
        if r.returncode != 0:
            log("  CUT_SKIP", b, "parse rc", r.returncode)
            continue
        person = NAME_RE.search(b).group(1)
        u = 0
        for line in r.stdout.splitlines():
            idx, sid, rs, re_, st, du, tx = line.split("\t", 6)
            if not int(float(st) + float(du)) + 1 <= vint:
                continue
            res, why = cut_one(mp4, st, du, f"{CLIPS}/.tmp")
            if res is None:
                nrej += 1
                log("  거부", spk, b, idx, why)
                continue
            name = f"{spk}_{b}_{cnt}"
            os.replace(f"{CLIPS}/.tmp.mp4", f"{CLIPS}/{name}.mp4")
            os.replace(f"{CLIPS}/.tmp.wav", f"{CLIPS}/{name}.wav")
            rows.append(f"{name}.mp4\t{spk}\t{tx}")
            crow.append("\t".join([name, spk, person, b, idx, sid, st, du, rs, re_, vd, res[0], res[1], "0"]))
            cnt += 1
            u = 1
        if u:
            used.append(b)
    with open(f"{ROOT}/manifest.tsv", "a") as f:
        for x in rows:
            f.write(x + "\n")
    with open(f"{ROOT}/manifest_clips.tsv", "a") as f:
        for x in crow:
            f.write(x + "\n")
    with open(f"{ROOT}/manifest_meta.tsv", "a") as f:
        f.write("\t".join([spk, v["vsn"], v["person"] or "-", "-", "-", "+".join(x[-3:] for x in used), str(cnt), v["lsn"], v["set"], "A", "-",
                           ",".join(used), "new", "v7b_stream", f"rejected:{nrej}", "0"]) + "\n")
    for b in v["got"]:
        if os.path.exists(f"{MP4}/{b}.mp4"):
            os.remove(f"{MP4}/{b}.mp4")
    open(f"{ROOT}/state/{spk}.done", "w").close()
    log("CUT_OK", spk, "clips", cnt, "rejected", nrej, "free %.1fGB" % free_gb())
    return 0


def cmd_run(spks, known):
    for spk in spks:
        if os.path.exists(f"{ROOT}/state/{spk}.done"):
            log("SKIP_DONE", spk)
            continue
        if free_gb() < MIN_FREE_GB + 2.5:
            log("DISK_STOP", "free %.1fGB" % free_gb())
            return 4
        vj = f"{ROOT}/state/{spk}.video.json"
        if not os.path.exists(vj):
            cmd_video(spk, known.get(spk))
        v = json.load(open(vj))
        if not v["got"]:
            log("NO_VIDEO", spk, v["decision"])
            continue
        if cmd_labels(spk) != 0:
            log("LABELS_MISSING", spk)
        cmd_cut(spk)
    log("RUN_OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("spks", nargs="*")
    ap.add_argument("--person")
    ap.add_argument("--known", default="", help="spk=person,... (3.1 옛 배치의 인물)")
    a = ap.parse_args()
    os.makedirs(ROOT, exist_ok=True)
    known = dict(x.split("=") for x in a.known.split(",") if x)
    if a.cmd == "survey":
        cmd_survey(a.spks)
    elif a.cmd == "plan":
        cmd_plan()
    elif a.cmd == "video":
        sys.exit(cmd_video(a.spks[0], a.person))
    elif a.cmd == "labels":
        sys.exit(cmd_labels(a.spks[0]))
    elif a.cmd == "cut":
        sys.exit(cmd_cut(a.spks[0]))
    elif a.cmd == "run":
        sys.exit(cmd_run(a.spks, known))
    else:
        sys.exit("survey|plan|video|labels|cut|run")


if __name__ == "__main__":
    main()
