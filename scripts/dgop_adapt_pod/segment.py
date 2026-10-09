"""파드: 학습 세션 자르기(docs/dgop-608-adapt-2026-10.md 3절).

    python segment.py whisper ROOT SHARD NSHARD     large-v3 낱말 시각 + 대본 문장 맞추기 + VAD 덩어리 → out/seg/<세션>.json
    python segment.py lists ROOT                    적합별 학습 목록(유라벨 조각·무라벨 덩어리)과 소리 파일 → data/train/*.jsonl

맞추기는 scripts/speak_asr_pod_run.cut_608과 같은 규칙(창 60낱말, 최대 40낱말, 길이 0.5~1.6배, difflib 비율, 앞 0.25초·뒤 0.35초).
"""
import difflib
import json
import os
import re
import sys
import time

import numpy as np
import soundfile as sf

SR = 16000
MIN_RATIO_TRAIN = 0.6
MATCH_MIN = 0.5
MAX_LEN, MIN_LEN, MAX_S_PER_SYL = 20.0, 1.0, 1.0
CHUNK_MAX, CHUNK_MIN, CHUNK_GAP = 15.0, 1.0, 0.5
EXCL_RATIO = 0.80
ALLOWED = re.compile(r"^[가-힣\s.,?!'\"‘’“”·~\-+]+$")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def load_audio(root, s):
    y, sr = sf.read(f"{root}/{s['path']}", dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    assert sr == SR, (s["stem"], sr)
    if s.get("crop_s"):
        y = y[:int(s["crop_s"] * SR)]
    return y


def match(words, sents):
    """cut_608과 같은 차례 맞추기. 돌려주는 것: [(문장 번호, 문장, 비율, 시작 초, 끝 초)] (비율 < 0.5는 시각 없음)."""
    wh = [hangul(w[0]) for w in words]
    pos, out = 0, []
    for si, sent in enumerate(sents):
        target = hangul(sent)
        best = (0.0, None, None)
        for i in range(pos, min(len(words), pos + 60)):
            acc = ""
            for j in range(i, min(len(words), i + 40)):
                acc += wh[j]
                if len(acc) > len(target) * 1.6:
                    break
                if len(acc) < len(target) * 0.5:
                    continue
                r = difflib.SequenceMatcher(None, target, acc).ratio()
                if r > best[0]:
                    best = (r, i, j)
        if best[1] is None or best[0] < MATCH_MIN:
            out.append({"si": si, "text": sent, "ratio": round(best[0], 3)})
            continue
        r, i, j = best
        out.append({"si": si, "text": sent, "ratio": round(r, 3), "start": round(max(0.0, words[i][1] - 0.25), 3),
                    "end": round(words[j][2] + 0.35, 3), "big": "".join(w[0] for w in words[i:j + 1]).strip()})
        pos = j + 1
    return out


def vad_chunks(y):
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    ts = get_speech_timestamps(y, VadOptions(threshold=0.5, min_speech_duration_ms=250, min_silence_duration_ms=500, speech_pad_ms=100))
    chunks, cur = [], None
    for t in ts:
        a, b = t["start"] / SR, t["end"] / SR
        if cur and a - cur[1] < CHUNK_GAP and b - cur[0] <= CHUNK_MAX:
            cur[1] = b
            continue
        if cur:
            chunks.append(cur)
        cur = [a, b]
        while cur[1] - cur[0] > CHUNK_MAX:          # 한 말소리 구간이 15초를 넘으면 15초씩 자른다
            chunks.append([cur[0], cur[0] + CHUNK_MAX])
            cur = [cur[0] + CHUNK_MAX, cur[1]]
    if cur:
        chunks.append(cur)
    return [[round(a, 3), round(b, 3)] for a, b in chunks if b - a >= CHUNK_MIN]


def cmd_whisper(root, shard, nshard):
    from faster_whisper import BatchedInferencePipeline, WhisperModel
    sess = json.load(open(f"{root}/meta/sessions.json", encoding="utf-8"))
    order = {"C": 0, "B": 1, "A": 2}                 # F1(B+C) 자료를 먼저
    sess = sorted(sess, key=lambda s: (order[s["group"]], s["stem"]))[shard::nshard]
    os.makedirs(f"{root}/out/seg", exist_ok=True)
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    pipe = BatchedInferencePipeline(model=model)
    log("large-v3 loaded", len(sess), "sessions")
    t0 = time.time()
    for k, s in enumerate(sess):
        dst = f"{root}/out/seg/{s['stem']}.json"
        if os.path.exists(dst):
            continue
        y = load_audio(root, s)
        segs, _ = pipe.transcribe(y, language="ko", beam_size=5, word_timestamps=True, vad_filter=True, batch_size=16)
        words = [(w.word, w.start, w.end) for sg in segs for w in (sg.words or [])]
        m = match(words, s["sents"])
        ch = vad_chunks(y)
        json.dump({"stem": s["stem"], "dur": round(len(y) / SR, 2), "n_words": len(words), "match": m, "chunks": ch},
                  open(dst + ".tmp", "w"), ensure_ascii=False)
        os.replace(dst + ".tmp", dst)
        ok = sum(1 for x in m if "start" in x)
        log(f"[{shard}] {k + 1}/{len(sess)} {s['stem']} {len(y) / SR / 60:.1f}분 문장 {ok}/{len(m)} 덩어리 {len(ch)} {time.time() - t0:.0f}s")
    log(f"SEG_WHISPER_OK shard={shard}")


class Excluder:
    def __init__(self, sents):
        self.sents = [s for s in sents if s]
        self.exact = set(self.sents)
        self.by_len = {}
        for s in self.sents:                          # 평가 문장 쪽(seq2)을 미리 색인해 둔다(SequenceMatcher는 seq2를 기억한다)
            self.by_len.setdefault(len(s), []).append(difflib.SequenceMatcher(None, "", s, autojunk=False))

    def hit(self, h):
        if not h:
            return False
        if h in self.exact:
            return True
        for e in self.sents:                          # 포함 관계(한쪽이 다른 쪽 안에)
            if (len(e) >= 4 and e in h) or (len(h) >= 4 and h in e):
                return True
        lh = len(h)
        for le, sms in self.by_len.items():
            if 2 * min(lh, le) / (lh + le) < EXCL_RATIO:
                continue
            for sm in sms:
                sm.set_seq1(h)
                if sm.quick_ratio() >= EXCL_RATIO and sm.ratio() >= EXCL_RATIO:
                    return True
        return False


def label_text(sent):
    t = re.sub(r"[^가-힣\s]", " ", sent.replace("+", " "))
    return re.sub(r"\s+", " ", t).strip()


def cmd_lists(root):
    sess = json.load(open(f"{root}/meta/sessions.json", encoding="utf-8"))
    excl = json.load(open(f"{root}/meta/excl.json", encoding="utf-8"))
    ex = {f: Excluder(v) for f, v in excl.items()}
    fold_groups = {"F1": ("B", "C"), "F2": ("A", "C")}
    os.makedirs(f"{root}/data/train", exist_ok=True)
    os.makedirs(f"{root}/audio/tseg", exist_ok=True)
    os.makedirs(f"{root}/audio/tchunk", exist_ok=True)
    lists = {f: {"lab": [], "unl": []} for f in fold_groups}
    stats = {f: {"sent": 0, "matched": 0, "ratio_low": 0, "len": 0, "chars": 0, "excluded": 0, "kept": 0, "kept_s": 0.0,
                 "chunks": 0, "chunks_excl": 0, "chunks_s": 0.0} for f in fold_groups}
    missing = []
    for s in sess:
        p = f"{root}/out/seg/{s['stem']}.json"
        if not os.path.exists(p):
            missing.append(s["stem"])
            continue
        r = json.load(open(p, encoding="utf-8"))
        y = None
        folds = [f for f, g in fold_groups.items() if s["group"] in g]
        for f in folds:
            bad_spans = []
            for m in r["match"]:
                st = stats[f]
                st["sent"] += 1
                h = hangul(m["text"])
                hit = ex[f].hit(h)
                if "start" in m and hit:
                    bad_spans.append((m["start"], m["end"]))
                if "start" not in m:
                    continue
                st["matched"] += 1
                if m["ratio"] < MIN_RATIO_TRAIN:
                    st["ratio_low"] += 1
                    continue
                d = m["end"] - m["start"]
                if not (MIN_LEN <= d <= MAX_LEN) or d / max(1, len(h)) > MAX_S_PER_SYL:
                    st["len"] += 1
                    continue
                lt = label_text(m["text"])
                if not ALLOWED.match(m["text"]) or len(hangul(lt)) < 2:
                    st["chars"] += 1
                    continue
                if hit:
                    st["excluded"] += 1
                    continue
                wav = f"audio/tseg/{s['stem']}_{m['si']:04d}.wav"
                if not os.path.exists(f"{root}/{wav}"):
                    if y is None:
                        y = load_audio(root, s)
                    sf.write(f"{root}/{wav}", y[int(m["start"] * SR):int(min(len(y) / SR, m["end"]) * SR)], SR)
                st["kept"] += 1
                st["kept_s"] += d
                lists[f]["lab"].append({"path": wav, "text": lt, "cat": s["cat"], "spk": s["key"], "group": s["group"], "dur": round(d, 2)})
            for k, (a, b) in enumerate(r["chunks"]):
                st = stats[f]
                if any(a < e and s0 < b for s0, e in bad_spans):
                    st["chunks_excl"] += 1
                    continue
                wav = f"audio/tchunk/{s['stem']}_{k:04d}.wav"
                if not os.path.exists(f"{root}/{wav}"):
                    if y is None:
                        y = load_audio(root, s)
                    sf.write(f"{root}/{wav}", y[int(a * SR):int(b * SR)], SR)
                st["chunks"] += 1
                st["chunks_s"] += b - a
                lists[f]["unl"].append({"path": wav, "cat": s["cat"], "spk": s["key"], "group": s["group"], "dur": round(b - a, 2)})
    for f, d in lists.items():
        for kind, rows in d.items():
            with open(f"{root}/data/train/{f}_{kind}.jsonl", "w", encoding="utf-8") as fh:
                for x in rows:
                    fh.write(json.dumps(x, ensure_ascii=False) + "\n")
        st = stats[f]
        st["kept_h"] = round(st.pop("kept_s") / 3600, 2)
        st["chunks_h"] = round(st.pop("chunks_s") / 3600, 2)
        st["lab_cat28"] = sum(1 for x in d["lab"] if x["cat"] == 28)
        st["lab_cat2124"] = sum(1 for x in d["lab"] if x["cat"] != 28)
        st["unl_cat28"] = sum(1 for x in d["unl"] if x["cat"] == 28)
        st["unl_cat2124"] = sum(1 for x in d["unl"] if x["cat"] != 28)
        st["spk_lab"] = len({x["spk"] for x in d["lab"]})
    json.dump({"stats": stats, "missing": missing}, open(f"{root}/out/train_lists.json", "w"), ensure_ascii=False, indent=1)
    log(json.dumps({"stats": stats, "missing": missing}, ensure_ascii=False))
    log("SEG_LISTS_OK" if not missing else f"SEG_LISTS_PARTIAL missing={len(missing)}")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "whisper":
        cmd_whisper(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif c == "lists":
        cmd_lists(sys.argv[2])
    else:
        sys.exit(f"알 수 없는 명령 {c}")
