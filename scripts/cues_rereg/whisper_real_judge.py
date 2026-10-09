"""속삭임 거부 재등록, 실제 녹음으로 판정하는 부분(B). 사전 등록 docs/speak-cues-rereg-2026-10.md 3.5절·4절.

  python whisper_real_judge.py REC_DIR PARAMS.json OUT.json

REC_DIR: whisper_record.html이 내려받은 WAV(참가자_기기_항목_반복.wav). 앱 녹음 루프 이식(크기 변화 없이 파일 그대로)으로
설계 R + 3.3절에서 고른 관문을 적용한다. 참가자 6명·기기 2종 미만이면 '판정 불가'.
출력은 항목별 집계와 참가자별 비율만(파일 이름의 참가자 코드는 남기되 실명은 쓰지 않는다).
"""
import glob, json, os, re, sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import speak_loop_port as lp      # noqa: E402
import whisper_extract as wx       # noqa: E402
import whisper_analyze as wa       # noqa: E402

NOVOICE = ("a_whisper", "a_stagewhisper", "breath", "i_whisper", "u_whisper")
VOICE = ("a_normal", "a_soft")


def main():
    rec, prm_path, out_path = sys.argv[1:4]
    prm = json.load(open(prm_path))
    gate = tuple(prm["chosen"]) if prm.get("chosen") else None
    rows = []
    for p in sorted(glob.glob(os.path.join(rec, "*.wav"))):
        m = re.match(r"([^_]+)_([^_]+)_(.+)_(\d+)\.wav$", os.path.basename(p))
        if not m:
            continue
        y = wx.read_audio(p)
        L = lp.loop(y)
        tr = []
        k = 0
        for q in L["trace"]:
            end = int(round(lp.BUF + k * lp.FRAME_HOP))
            buf = y[end - lp.BUF:end]
            c2 = wx.clarity2(buf, q["hz"])
            tr.append({"t": q["t"], "rms": q["rms"], "hz": q["hz"], "clarity": q["clarity"], "c2": c2, "cpp": wx.buf_cpp(buf)})
            k += lp.TRACE_EVERY
        d = wa.design(tr, gate)
        cur = lp.current_rule(L)
        rows.append({"pid": m.group(1), "dev": m.group(2), "item": m.group(3), "rep": int(m.group(4)), "new": d, "cur": cur})
    pids = {r["pid"] for r in rows}
    devs = {r["dev"] for r in rows}
    # 기준선: 참가자·기기마다 보통 'ㅏ' 가운데 새 규칙 0단계 합격 L의 중앙값(최대 5개)
    B = {}
    for key in {(r["pid"], r["dev"]) for r in rows}:
        Ls = [r["new"]["L"] for r in rows if (r["pid"], r["dev"]) == key and r["item"] == "a_normal" and r["new"]["stage0"]][:5]
        B[key] = float(np.median(Ls)) if len(Ls) >= 2 else None

    def rate(items, f):
        xs = [f(r) for r in rows if r["item"] in items]
        return (round(float(np.mean(xs)), 4) if xs else None, len(xs))

    soft = lambda r: lp.judge_with_baseline(r["new"], B[(r["pid"], r["dev"])])["soft"]
    out = {"gate": gate, "n_files": len(rows), "n_participants": len(pids), "n_devices": len(devs),
           "by_item": {it: {"new_stage0": rate((it,), lambda r: r["new"]["stage0"]), "cur_stage0": rate((it,), lambda r: r["cur"]["stage0"]),
                            "new_soft": rate((it,), soft), "cur_soft": rate((it,), lambda r: r["cur"]["soft"])}
                       for it in sorted({r["item"] for r in rows})}}
    D1, n1 = rate(NOVOICE, lambda r: r["new"]["stage0"])
    D2, n2 = rate(VOICE, lambda r: r["new"]["stage0"])
    D3, n3 = rate(("s_whisper",), soft)
    per = defaultdict(list)
    for r in rows:
        if r["item"] in NOVOICE:
            per[r["pid"]].append(r["new"]["stage0"])
    worst = max((float(np.mean(v)) for v in per.values()), default=None)
    enough = len(pids) >= 6 and len(devs) >= 2
    out["criteria"] = {"D1_novoice_stage0": [D1, n1], "D1_worst_participant": worst, "D2_voice_stage0": [D2, n2], "D3_whisper_sentence_soft": [D3, n3]}
    out["verdict"] = ("판정 불가(참가자 6명·기기 2종 미만)" if not enough else
                      "통과" if (D1 is not None and D1 <= 0.05 and worst <= 0.20 and D2 is not None and D2 >= 0.95 and D3 is not None and D3 <= 0.05)
                      else "실패")
    json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("WHISPER_REAL_OK", out["verdict"], json.dumps(out["criteria"], ensure_ascii=False))


if __name__ == "__main__":
    main()
