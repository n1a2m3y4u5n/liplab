"""C1·C2 기계 대리 판독 점수(2026-10-27). avread.py cmd_score와 같은 창·채점식이고, 판독기만 웹용 fp32 ONNX(정규화 밖)를 쓴다.
입력 정규화: x/255 → 시퀀스 평균·표준편차(모집단, 표준편차 하한 1e-2, float64) → float32 (kr_lipread_roi.web.meta.json).
조건마다 낱말별 보기 4개의 점수 전체(scores)와 고른 보기를 남긴다(혼동 분석용). 기계 지표이며 사람 판독이 아니다.
  python c12_score.py --items items.json --split confirm --npz DIR --renders DIR --onnx M.onnx --conds a,b --out score.json
"""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import avread as A  # noqa: E402


def norm(x):
    x = x.astype(np.float64) / 255.0
    m, s = x.mean(), max(x.std(), 1e-2)
    return ((x - m) / s).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--items', required=True); ap.add_argument('--split', required=True)
    ap.add_argument('--npz', required=True); ap.add_argument('--renders', required=True)
    ap.add_argument('--onnx', required=True); ap.add_argument('--conds', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--threads', type=int, default=2)
    a = ap.parse_args()
    import onnxruntime as ort, torch
    from roi_train import ctc_scores
    so = ort.SessionOptions(); so.intra_op_num_threads = a.threads; so.inter_op_num_threads = 1
    sess = ort.InferenceSession(a.onnx, so, providers=['CPUExecutionProvider'])
    inp = sess.get_inputs()[0].name; outn = sess.get_outputs()[0].name
    items = [it for it in json.load(open(a.items, encoding='utf-8'))['items'] if it['split'] == a.split]
    c0 = (A.S_ROI - A.CROP) // 2
    res = {'split': a.split, 'n_items': len(items), 'words': [it['w'] for it in items], 'onnx': os.path.abspath(a.onnx),
           'input': inp, 'conds': {}}
    t0 = time.time()
    for c in a.conds.split(','):
        hit, pick, scs, miss = [], [], [], 0
        for it in items:
            jid = f"w{it['rank']:03d}_{c}"
            npz, sch = os.path.join(a.npz, jid + '.npz'), os.path.join(a.renders, jid + '.sched.json')
            ok = os.path.exists(npz) and os.path.exists(sch)
            w = None
            if ok:
                z = np.load(npz); roi, valid = z['roi'], z['valid']
                w = A.window_idx(len(roi), json.load(open(sch, encoding='utf-8'))['speech'])
            if w is None or float(valid[w].mean()) < 0.5:
                miss += 1; hit.append(0); pick.append(-1); scs.append(None); continue
            X = norm(roi[w][:, c0:c0 + A.CROP, c0:c0 + A.CROP])[None]
            lg = sess.run([outn], {inp: X})[0][0]
            lp = torch.log_softmax(torch.from_numpy(lg).float(), -1)
            sc = ctc_scores(lp, it['labs']); k = int(np.argmax(sc))
            pick.append(k); hit.append(int(k == it['tgt'])); scs.append([float(v) for v in sc])
        res['conds'][c] = {'acc': float(np.mean(hit)), 'hit': hit, 'pick': pick, 'scores': scs, 'miss': miss}
        print(f'C12_SCORE {c} acc={np.mean(hit):.4f} miss={miss} {time.time()-t0:.0f}s', flush=True)
    json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False)
    print('C12_SCORE_OK', a.out)


if __name__ == '__main__':
    main()
