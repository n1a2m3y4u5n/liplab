"""듣기 트랙 소음(st 가상환경). 모두 모노, 약 60초, 끝 2초를 처음에 교차 페이드해 반복 재생 이음매가 없고 RMS −23 dBFS.
    python noises.py TEXTS.json OUTDIR [LTAS_WAV_DIR ...]
  talker1_f / talker1_m  경쟁 화자 1명(여 F5 / 남 M2), 문장을 짧은 쉼(80ms)으로 이어 읽기
  talker2                경쟁 화자 2명 겹침(여 F4 + 남 M3)
  babble                 잡담 잡음: 목소리 10개 + 빠르기 변형 2개 = 흐름 12개
  ssn                    말소리 모양 잡음: LTAS_WAV_DIR(듣기 자극 전부)의 장기 평균 스펙트럼으로 백색 잡음을 거른 정상 잡음(HINT 방식).
                         한 번의 FFT로 거르므로 원형 합성곱이라 그대로 반복 재생해도 이어진다
경쟁 화자 목소리는 듣기 목록의 목소리(m1·f1·m2·f2·m3 = M1·F1·M4·F3·M5)와 다르게 골랐다(목표와 같은 목소리가 겹치지 않게).
문장은 앱의 어떤 글(TEXTS.json: 레슨·듣기 검사·훈련 문장)과도 겹치지 않는다."""
import glob, json, os, random, re, sys
import numpy as np
import soundfile as sf
from supertonic import TTS

SENTS = [
    "어제 저녁에 동생이랑 만두를 빚었어", "이번 달 관리비가 조금 올랐더라", "아침에 버스가 십 분이나 늦게 왔어",
    "주말에 베란다 화분을 정리했어요", "회사 근처에 새로 생긴 국숫집 가 봤어?", "엄마가 김장 언제 할지 물어보셨어",
    "요즘 저녁마다 줄넘기를 하고 있어", "우리 집 고양이가 또 상자에 들어갔어", "다음 달에 이사 날짜가 잡혔어요",
    "그 드라마 마지막 회 봤어?", "택배가 경비실에 맡겨져 있대", "오후에 비 소식이 있다던데",
    "점심은 회사 식당에서 대충 먹었어", "조카 돌잔치가 토요일이라고 했지?", "새로 산 운동화가 생각보다 편해",
    "주차장 자리가 하나도 없더라고", "그 가게는 월요일마다 쉰대요", "냉장고에 반찬이 거의 없어",
    "도서관 책 반납일이 내일이야", "커피를 너무 많이 마셨나 봐", "할머니 댁에 감을 따러 갔었어",
    "이 근처에 세탁소가 어디 있었지?", "퇴근길에 꽃집에 들렀어요", "아이가 감기 기운이 있어서 걱정이야",
    "휴대폰 화면이 또 깨졌어", "오랜만에 대청소를 했더니 개운하다", "동네 공원에 벚나무를 새로 심었대",
    "그 식당 예약은 내가 해 둘게", "지난번에 빌린 우산 돌려줄게", "다음 주에 건강검진 받으러 가",
]
TARGET_S, XFADE_S, RMS_DBFS = 62.0, 2.0, -23.0


def key(t):
    return re.sub(r"[^가-힣]", "", t)


def loop_norm(x, sr):
    L, X = int(TARGET_S * sr), int(XFADE_S * sr)
    body = x[:L].copy()
    fade = np.linspace(0, 1, X, dtype=np.float32)
    body[:X] = body[:X] * fade + x[L:L + X] * (1 - fade)
    return norm(body)


def norm(x):
    x = x * (10 ** (RMS_DBFS / 20) / (np.sqrt(np.mean(x ** 2)) + 1e-12))
    pk = np.max(np.abs(x))
    return x * (0.99 / pk) if pk > 0.99 else x


def stream(tts, sr, voice, speed, sents, rng, gap=(0.08, 0.08)):
    style = tts.get_voice_style(voice_name=voice)
    order = sents[:]
    rng.shuffle(order)
    chunks, total, k = [], 0.0, 0
    while total < TARGET_S + XFADE_S + 6:
        w, _ = tts.synthesize(order[k % len(order)], voice_style=style, lang="ko", speed=speed)
        k += 1
        w = np.asarray(w, dtype=np.float32).reshape(-1)
        # 문장 앞뒤 무음을 줄여 이어 읽기처럼(−45dB 아래를 앞뒤에서 자름)
        a = np.abs(w)
        on = np.where(a > a.max() * 10 ** (-45 / 20))[0]
        if on.size:
            w = w[max(0, on[0] - int(0.02 * sr)):on[-1] + int(0.04 * sr)]
        g = np.zeros(int(sr * rng.uniform(*gap)), np.float32)
        chunks += [w, g]
        total += (len(w) + len(g)) / sr
    x = np.concatenate(chunks)
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-9)


def mix(streams, sr, rng):
    n = int((TARGET_S + XFADE_S) * sr)
    out = []
    for s in streams:
        off = int(rng.uniform(0, 5) * sr)
        out.append(s[off:off + n])
    m = min(len(s) for s in out)
    return np.sum([s[:m] for s in out], axis=0)


def ssn(wav_dirs, sr, rng):
    nfft = 4096
    acc, cnt = np.zeros(nfft // 2 + 1), 0
    for d in wav_dirs:
        for p in glob.glob(os.path.join(d, "*.wav")):
            x, r = sf.read(p, dtype="float32")
            if r != sr or len(x) < nfft:
                continue
            for s in range(0, len(x) - nfft, nfft // 2):
                fr = x[s:s + nfft] * np.hanning(nfft)
                if np.mean(fr ** 2) < 1e-6:      # 무음 창은 뺀다
                    continue
                acc += np.abs(np.fft.rfft(fr)) ** 2
                cnt += 1
    ltas = acc / max(1, cnt)
    n = int(TARGET_S * sr)
    white = np.random.default_rng(31).standard_normal(n)
    spec = np.fft.rfft(white)
    f_full = np.fft.rfftfreq(n, 1 / sr)
    f_ltas = np.fft.rfftfreq(nfft, 1 / sr)
    spec *= np.sqrt(np.interp(f_full, f_ltas, ltas))
    return norm(np.fft.irfft(spec, n).astype(np.float32)), {"frames": cnt, "nfft": nfft}


def main():
    texts, outdir = sys.argv[1], sys.argv[2]
    ltas_dirs = sys.argv[3:]
    pool = {key(e["text"]) for e in json.load(open(texts))}
    sents = [s for s in SENTS if key(s) not in pool]
    os.makedirs(outdir, exist_ok=True)
    tts = TTS(auto_download=True, intra_op_num_threads=4, inter_op_num_threads=1)
    sr = getattr(tts, "sample_rate", None) or 44100
    meta = {"sr": sr, "sentences": sents, "noises": {}}
    rng = random.Random(23)
    plan = {
        "talker1_f": [("F5", 1.0)],
        "talker1_m": [("M2", 1.0)],
        "talker2": [("F4", 1.0), ("M3", 1.0)],
        "babble": [(v, 1.0) for v in ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]] + [("M3", 1.1), ("F2", 0.9)],
    }
    for name, voices in plan.items():
        gap = (0.08, 0.08) if name != "babble" else (0.15, 0.45)
        sts = [stream(tts, sr, v, sp, sents, rng, gap) for v, sp in voices]
        y = loop_norm(sts[0][:int((TARGET_S + XFADE_S) * sr)] if len(sts) == 1 else mix(sts, sr, rng), sr)
        sf.write(os.path.join(outdir, f"{name}.wav"), y, sr, subtype="PCM_16")
        meta["noises"][name] = {"talkers": [f"{v}@{sp}" for v, sp in voices], "seconds": len(y) / sr,
                                "rms_dbfs": round(float(20 * np.log10(np.sqrt(np.mean(y ** 2)))), 2)}
        print("NOISE", name, flush=True)
    if ltas_dirs:
        y, info = ssn(ltas_dirs, sr, rng)
        sf.write(os.path.join(outdir, "ssn.wav"), y, sr, subtype="PCM_16")
        meta["noises"]["ssn"] = {"ltas_from": ltas_dirs, **info, "seconds": len(y) / sr,
                                 "rms_dbfs": round(float(20 * np.log10(np.sqrt(np.mean(y ** 2)))), 2)}
        print("NOISE ssn", flush=True)
    json.dump(meta, open(os.path.join(outdir, "noises.json"), "w"), ensure_ascii=False, indent=1)
    print("NOISES_OK")


if __name__ == "__main__":
    main()
