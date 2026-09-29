"""파드: 말하기 3단계 자음의 '앱 방향' 대치 판별과 모음 포먼트 화자 정규화 자료를 한 번의 정렬로 만든다(2026-09-29 사전 등록,
docs/speak-consonant-check.md·docs/formant-validation.md).

클립마다 정렬기·채점기 순전파를 한 번만 하고(ctc_log_probs를 클립 안에서 기억), 제 문장과 초성 하나만 바꾼 문장들을 같은 출력에
강제정렬해 바뀐 자리 음소의 D-GOP를 얻는다. 앱의 dgop_acoustic.phone_confidences를 그대로 부르므로 채점은 앱과 같다(int8, CPU).
  - 자음(out/app_dir.json의 cons): 짝 (녹음의 초성 Y → 대어 채점한 목표 X). 'ㅇ'→ㅎ은 ㅎ 탈락(첫소리 없는 모음 음절에 ㅎ을 더함).
    true 행 = 제 문장에서 초성 C 자리의 D-GOP(고정 목표 AUC의 양성).
  - 포먼트(out/app_dir.json의 formant): 제 문장 정렬로 단모음 구간을 잘라(speak_formant_pod_eval.py와 같은 자르기) 화자 번호와 추정
    F1·F2·F3·F0, 앱 vowel_feedback의 자기 모음 판정(분석 재계산 확인용)을 남긴다.
자료: 538 정상 화자 클립 전부(c538/manifest.tsv), 608 감음신경성 문장 컷(out/cuts608.json의 시작·끝 초로 원본 세션을 soundfile로 다시 자름).
    unset LD_LIBRARY_PATH; EVAL_THREADS=1 /workspace/vb/bin/python speak_app_direction_pod_eval.py 15 [최대 클립 수]
"""
import io
import json
import os
import random
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor

W = "/workspace"
os.environ.update(BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1", CUDA_VISIBLE_DEVICES="")
sys.path.insert(0, f"{W}/backend")
AL, SC = f"{W}/backend/models/dgop_ours/aligner", f"{W}/backend/models/dgop_ours/scorer"
SR = 16000
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
# (녹음의 초성 → 목표 초성). 결과 전에 고정(사전 등록).
PAIRS = [("ㄷ", "ㅅ"), ("ㄷ", "ㅈ"), ("ㅊ", "ㅈ"), ("ㅈ", "ㅊ"), ("ㄱ", "ㅎ"), ("ㅇ", "ㅎ"),       # 앱 방향, 새 자음
         ("ㅅ", "ㅆ"), ("ㅈ", "ㅉ"), ("ㅆ", "ㅅ"), ("ㅉ", "ㅈ"),                                 # 된소리 두 방향
         ("ㅅ", "ㄷ"), ("ㅈ", "ㄷ"), ("ㅎ", "ㄱ"),                                                 # 9/28 방향 재확인
         ("ㅂ", "ㅁ"), ("ㅁ", "ㅂ"), ("ㅂ", "ㅍ"), ("ㅍ", "ㅂ"), ("ㄷ", "ㅌ"), ("ㅌ", "ㄷ"), ("ㄱ", "ㅋ"), ("ㅋ", "ㄱ")]
TRUE_CONS = sorted({x for p in PAIRS for x in p if x != "ㅇ"})
MAX_SPOTS = 3
VOWELS = ["ㅣ", "ㅔ", "ㅐ", "ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ"]


def split(ch):
    c = ord(ch) - 0xAC00
    return (c // 588, (c % 588) // 28, c % 28) if 0 <= c < 11172 else None


def join(i, j, k):
    return chr(0xAC00 + (i * 21 + j) * 28 + k)


def spots(text, onset):
    """초성이 onset인 글자 위치. 앞 글자가 받침 있는 한글이면 연음·동화가 끼어 뺀다(9/28과 같은 규칙)."""
    out = []
    for i, ch in enumerate(text):
        s = split(ch)
        if not s or CHO[s[0]] != onset:
            continue
        prev = split(text[i - 1]) if i else None
        if prev and prev[2] != 0:
            continue
        out.append(i)
    return out


def with_onset(text, i, onset):
    s = split(text[i])
    return text[:i] + join(CHO.index(onset), s[1], s[2]) + text[i + 1:]


def locate(base_toks, alt_toks, y, x):
    """바꾼 문장 토큰에서 바뀐 자리 k. 치환은 길이가 같고 한 자리만 달라야 하고, ㅎ 탈락(y='ㅇ')은 ㅎ 토큰 하나만 더해져야 한다."""
    if y == "ㅇ":
        if len(alt_toks) != len(base_toks) + 1:
            return None
        k = next((j for j in range(len(base_toks)) if alt_toks[j] != base_toks[j]), len(base_toks))
        if alt_toks[k] == "o:" + x and alt_toks[:k] + alt_toks[k + 1:] == base_toks:
            return k
        return None
    if len(alt_toks) != len(base_toks):
        return None
    diff = [j for j in range(len(base_toks)) if alt_toks[j] != base_toks[j]]
    if len(diff) == 1 and base_toks[diff[0]] == "o:" + y and alt_toks[diff[0]] == "o:" + x:
        return diff[0]
    return None


def word_initial(text, i):
    return i == 0 or not split(text[i - 1])


_LP = {}


def _install_cache(D):
    """클립 하나 안에서 같은 파형·모델의 순전파를 다시 하지 않게 ctc_log_probs를 감싼다(결과는 같다)."""
    if getattr(D, "_lp_cached", False):
        return
    orig = D.ctc_log_probs

    def cached(waveform, sample_rate, model_id=D.DEFAULT_MODEL_ID):
        k = (id(waveform), model_id)
        if k not in _LP:
            _LP[k] = orig(waveform, sample_rate, model_id)
        return _LP[k]
    D.ctc_log_probs = cached
    D._lp_cached = True


def job(args):
    import numpy as np
    import torch
    torch.set_num_threads(int(os.environ.get("EVAL_THREADS", "2")))
    import dgop_acoustic as D
    import formants as F
    from faster_whisper.audio import decode_audio
    _install_cache(D)
    path, text, spk, group = args
    _LP.clear()
    try:
        data = open(path, "rb").read()
        wave = decode_audio(io.BytesIO(data), sampling_rate=SR)[:SR * 30]      # assess_text와 같은 디코딩
        base_toks = D.tokens_for_text(text, model_id=AL)
        base = D.phone_confidences(wave, SR, base_toks, aligner_id=AL, scorer_id=SC)
        rng = random.Random(zlib.crc32(path.encode()))
        cons, seen_true = [], set()

        def dg(ph, k):
            p = ph[k] if k < len(ph) else {}
            return p.get("dgop") if p.get("aligned") else None

        # 고정 목표 AUC의 양성: 제 문장에서 초성 C 자리의 D-GOP(자리 찾기는 다른 초성으로 바꿔 본 토큰 차이로)
        for c in TRUE_CONS:
            sp = spots(text, c)
            for i in rng.sample(sp, min(MAX_SPOTS, len(sp))):
                probe = "ㄱ" if c != "ㄱ" else "ㄷ"
                k = locate(base_toks, D.tokens_for_text(with_onset(text, i, probe), model_id=AL), c, probe)
                if k is None:
                    continue
                cons.append({"kind": "true", "cons": c, "k": k, "i": i, "wi": word_initial(text, i), "dgop": dg(base, k)})
                seen_true.add((c, i))
        for y, x in PAIRS:
            sp = spots(text, y)
            for i in rng.sample(sp, min(MAX_SPOTS, len(sp))):
                alt_toks = D.tokens_for_text(with_onset(text, i, x), model_id=AL)
                k = locate(base_toks, alt_toks, y, x)
                if k is None:
                    continue
                alt = D.phone_confidences(wave, SR, alt_toks, aligner_id=AL, scorer_id=SC)
                cons.append({"kind": "pair", "y": y, "x": x, "k": k, "i": i, "wi": word_initial(text, i),
                             "same": dg(base, k) if y != "ㅇ" else None, "alt": dg(alt, k)})
        # 포먼트: speak_formant_pod_eval.py와 같은 모음 자르기
        fm = []
        y16 = np.asarray(wave, dtype=np.float32)
        for j, p in enumerate(base):
            tok = p.get("token", "")
            v = tok.split(":", 1)[-1]
            if not tok.startswith("n:") or v not in VOWELS or "t0" not in p:
                continue
            nxt = next((q["t0"] for q in base[j + 1:] if "t0" in q), None)
            end = min(nxt if nxt is not None else p["t0"] + 0.25, p["t0"] + 0.30, len(y16) / SR)
            a, b = int(p["t0"] * SR), int(end * SR)
            if b - a < int(0.08 * SR):
                continue
            if b - a >= int(0.13 * SR):
                m = int((b - a) * 0.2)
                a, b = a + m, b - m
            seg = y16[a:b]
            est = F.estimate_formants(seg)
            if est is None:
                continue
            own = F.vowel_feedback(seg, v)
            fm.append({"vowel": v, "dur": round((b - a) / SR, 3), "dgop": p.get("dgop"), "f1": est["f1"], "f2": est["f2"],
                       "f3": est["f3"], "f0": est.get("f0"),
                       "own_ok_app": bool(own and own["height"] == "ok" and own["front"] == "ok")})
        return {"path": os.path.basename(path), "spk": spk, "group": group, "n_tok": len(base_toks), "cons": cons, "formant": fm}
    except Exception as e:
        return {"path": os.path.basename(path), "spk": spk, "group": group, "error": f"{type(e).__name__}: {e}"}


def cut_608():
    """9/28 GPU 문장 자르기가 남긴 경계(시작·끝 초)로 원본 세션을 다시 자른다(run.py cut_608과 같은 sf.write)."""
    import soundfile as sf
    os.makedirs(f"{W}/cuts", exist_ok=True)
    cuts = [c for c in json.load(open(f"{W}/out/cuts608.json")) if c.get("cut")]
    cache = {}
    for c in cuts:
        if os.path.exists(c["cut"]):
            continue
        if c["file"] not in cache:
            cache.clear()
            audio, sr = sf.read(f"{W}/s608/{c['file']}")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            assert sr == SR, sr
            cache[c["file"]] = audio
        audio = cache[c["file"]]
        sf.write(c["cut"], audio[int(c["start"] * SR):int(c["end"] * SR)], SR)
    return cuts


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    cuts = cut_608()
    jobs = []
    for l in open(f"{W}/c538/manifest.tsv", encoding="utf-8"):
        clip, spk, text = l.rstrip("\n").split("\t")
        p = f"{W}/c538/{clip.replace('.mp4', '.flac')}"
        if os.path.exists(p):
            jobs.append((p, text, spk, "538"))
    jobs += [(c["cut"], c["target"], c["file"].split("-")[4], "608") for c in cuts]
    if limit:
        jobs = jobs[:limit // 2] + jobs[-(limit - limit // 2):]
    # 긴 컷(608)을 앞에 두면 마지막에 한 작업자만 남는 꼬리가 줄어든다
    jobs.sort(key=lambda j: j[3] != "608")
    print("jobs", len(jobs), flush=True)
    out = []
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=2)):
            out.append(r)
            if i % 100 == 0:
                print(i, len(jobs), sum(len(x.get("cons", [])) for x in out), sum(len(x.get("formant", [])) for x in out),
                      sum("error" in x for x in out), flush=True)
    name = "app_dir_smoke.json" if limit else "app_dir.json"
    json.dump(out, open(f"{W}/out/{name}", "w"), ensure_ascii=False)
    print("DONE", len(out), "errors", sum("error" in x for x in out), flush=True)
