"""파드: V14(docs/avatar-validity-2026-10.md 6.4). 무료 TTS(MeloTTS 한국어, MIT)로 538 문장 50개를 읽히고, 제품 음성 구동 모델
A4(backend/audio2face.py, kr_a4_wavlm.pt)로 실제 음성과 TTS 음성에서 52계수(30fps)를 낸다.

  # TTS 전용 venv(MeloTTS가 옛 판을 고정한다)
  python v14_tts_a4.py tts --sel sel.json --out out/tts
  # 앱 venv(torch·transformers 5.17)
  python v14_tts_a4.py a4 --sel sel.json --clips clips --tts out/tts --backend backend --out out/v14
  → out/v14/a4_real/<clip>.json, out/v14/a4_tts/<sid>.json({fps, names, frames}), 정렬 항목 out/v14/align_items_tts.jsonl
"""
import argparse
import json
import os
import subprocess
import sys


def cmd_tts(a):
    from melo.api import TTS
    sel = json.load(open(a.sel, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    dev = "cuda" if os.environ.get("V14_CUDA", "1") == "1" else "cpu"
    try:
        import torch
        if not torch.cuda.is_available():
            dev = "cpu"
    except Exception:
        dev = "cpu"
    model = TTS(language="KR", device=dev)
    spk = model.hps.data.spk2id["KR"]
    n = 0
    for it in sel["v14"]:
        wav16 = os.path.join(a.out, it["sid"] + ".wav")
        if os.path.exists(wav16):
            n += 1
            continue
        raw = os.path.join(a.out, it["sid"] + ".raw.wav")
        model.tts_to_file(it["text"], spk, raw, speed=1.0, quiet=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-ac", "1", "-ar", "16000", wav16], check=True)
        os.remove(raw)
        n += 1
    print(f"V14_TTS_OK n={n} device={dev}")


def cmd_a4(a):
    sys.path.insert(0, os.path.abspath(a.backend))
    os.environ.setdefault("LIPLAB_A4_CKPT", os.path.join(os.path.abspath(a.backend), "models", "kr_a4_wavlm.pt"))
    import audio2face as A
    sel = json.load(open(a.sel, encoding="utf-8"))
    for sub in ("a4_real", "a4_tts"):
        os.makedirs(os.path.join(a.out, sub), exist_ok=True)
    items = []
    n = 0
    for it in sel["v14"]:
        for kind, wav, key, name in (("a4_real", os.path.join(a.clips, it["clip"] + ".wav"), "real:" + it["clip"], it["clip"]),
                                     ("a4_tts", os.path.join(a.tts, it["sid"] + ".wav"), "tts:" + it["sid"], it["sid"])):
            if not os.path.exists(wav):
                continue
            outp = os.path.join(a.out, kind, name + ".json")
            if not os.path.exists(outp):
                r = A.blendshapes_from_audio(open(wav, "rb").read())
                json.dump({"fps": r["fps"], "names": r["names"], "frames": r["frames"]}, open(outp, "w"))
            n += 1
            if kind == "a4_tts":
                items.append({"key": key, "text": it["text"], "audio": wav})
    with open(os.path.join(a.out, "align_items_tts.jsonl"), "w", encoding="utf-8") as fo:
        for it in items:
            fo.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"V14_A4_OK n={n} tts_items={len(items)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("tts")
    s.add_argument("--sel", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("a4")
    s.add_argument("--sel", required=True)
    s.add_argument("--clips", required=True)
    s.add_argument("--tts", required=True)
    s.add_argument("--backend", required=True)
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    {"tts": cmd_tts, "a4": cmd_a4}[a.cmd](a)


if __name__ == "__main__":
    main()
