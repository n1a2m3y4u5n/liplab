"""범주별 정확 전사 비율(large-v3-turbo CER 0)과 CER(문항당 1로 자름). python bycat.py RUN_DIR"""
import glob, json, os, sys
run = sys.argv[1]
sample = {e["key"]: e for e in json.load(open(os.path.join(run, "sample.json")))}


def cat(e):
    if e["n_syl"] == 1:
        return "1음절"
    s = e["sources"]
    return "문맥" if "closure" in s else "문장" if "sentence" in s else "대화" if "convo" in s else "단어"


for f in sorted(glob.glob(os.path.join(run, "asr", "*.asr.jsonl"))):
    rs = [json.loads(l) for l in open(f)]
    for m in ("base", "large-v3-turbo"):
        by = {}
        for r in rs:
            b = by.setdefault(cat(sample[r["key"]]), [0, 0])
            b[0] += 1
            b[1] += r["cer"][m] == 0
        cap = sum(min(1, r["cer"][m]) for r in rs) / len(rs)
        ex = sum(r["cer"][m] == 0 for r in rs) / len(rs)
        print(os.path.basename(f)[:-10], m, "n", len(rs), "capCER %.3f exact %.3f" % (cap, ex),
              " ".join("%s %d/%d" % (k, v[1], v[0]) for k, v in sorted(by.items())))
