#!/usr/bin/env python3
"""
V1(2026-10-15): 538 화자를 늘려 제품용 자모 CTC 독화기를 다시 학습하고 평가 화자 40명으로 판정하기 위한 학습·선택 도구.
사전등록: liplab-integrate docs/lipread-v1-prereg-2026-10.md (학습 전에 커밋). 평가(eval 40명)는 이 파일이 아니라
d_bench.py product4way(기존 코드 그대로)와 v1_judge.py가 한다. 이 파일은 평가 화자의 프레임을 읽지 않는다.

구조는 제품 모델과 같다(train_lipread.build: 입 블렌드셰이프 27 → LayerNorm → BiGRU 3층 256 → 자모 53).
ONNX 계약(bs [B,T,27] → logits [B,T,53])이 그대로라 브라우저 lipreadModel.js에 바로 넣을 수 있다.
538 데이터 외의 사전학습 가중치는 쓰지 않는다(Auto-AVSR는 비상업 조건이라 제품에 못 씀).

하위명령
  split  --bench B --eval-list eval40.txt --val-n 12 --out split.json
         평가 화자 = eval-list(사전등록 규칙으로 맥에서 고정한 목록). 검증 화자 = 나머지 화자 중
         sha256("liplab-v1-val:" + spk) 16진 문자열이 작은 순서로 val-n명. 나머지는 학습 화자.
         학습에서 빼는 것: 검증·평가 화자가 읽은 문장과 같은 문장(한글만 비교, folds.norm_text)의 학습 클립과 그 어절.
  train  --bench B --split split.json --cand A|B --seed S --out DIR [--epochs 60 --batch 64 --eval-every 2 --patience 10]
         A = P2 방식(문장 전체 + 어절 'wide' 구간, train_lipread --aug와 같은 증강).
         B = A + 어절의 절반을 2.5 s(75프레임) 창 안 임의 위치에 두고 나머지를 같은 학습 화자의 쉬는 프레임으로 채움
             (제품 기계 확인의 2.5 s 녹화를 모사, 쉬는 프레임 재료는 d_bench._rest_runs와 같은 규칙).
         체크포인트 = 검증 화자 4지 hard(ctc_ll α=1, idle75, dup1과 dup2 평균, 화자 평균)가 가장 높은 에폭.
         끝 표식 V1_TRAIN_DONE / V1_TRAIN_FAIL.
  select --runs D1,D2,… --out sel.json
         각 run의 최고 체크포인트에서 (run, dup ∈ {2, 1}) 중 검증 4지가 가장 높은 하나. 동점이면 목록 순서(A s0, s1, s2,
         B s0, s1, s2)와 dup2 먼저. → V1_SELECT run=… dup=…
  (시험) train --max-items N --max-val N 으로 작은 경로만 돌려 볼 수 있다(판정용 실행에서는 쓰지 않는다).
의존: numpy, torch. 파드(Python 3.10, torch 2.1)·맥(3.14) 공용.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import folds as FO                                                       # noqa: E402
from build_cd import fill_all                                            # noqa: E402
from train_lipread import MOUTH_KEYS, VOCAB, decompose, build, aug_raw, aug_post, _mirror_perm, \
    forward_packed, _pad, greedy_decode, cer                              # noqa: E402
from d_bench import Bench, Distractors, _rest_runs, _tile, p4_sequences, IDLE_LEN, write_json_atomic  # noqa: E402

DUPS = (2, 1)
ALPHA = 1.0


def h16(tag, spk):
    return hashlib.sha256(f'{tag}{spk}'.encode('utf-8')).hexdigest()


def read_list(p):
    return [x.strip() for x in open(p, encoding='utf-8') if x.strip() and not x.startswith('#')]


# ── split ───────────────────────────────────────────────────────────────────
def cmd_split(a):
    b = Bench(a.bench)
    spks = sorted({c['spk'] for c in b.clips})
    ev = read_list(a.eval_list)
    miss = [s for s in ev if s not in spks]
    rest = [s for s in spks if s not in set(ev)]
    val = sorted(rest, key=lambda s: h16('liplab-v1-val:', s))[:a.val_n]
    tr = sorted(s for s in rest if s not in set(val))
    held_txt = {FO.norm_text(c['text']) for c in b.clips if c['spk'] in set(ev) | set(val)}
    n_tr_clip = sum(1 for c in b.clips if c['spk'] in set(tr))
    n_drop = sum(1 for c in b.clips if c['spk'] in set(tr) and FO.norm_text(c['text']) in held_txt)
    out = {'bench': os.path.abspath(a.bench), 'bench_id': b.bench_id, 'eval': ev, 'eval_missing_in_bench': miss,
           'val': sorted(val), 'train': tr, 'val_rule': 'sha256("liplab-v1-val:"+spk) 오름차순 앞 %d명' % a.val_n,
           'train_clips': n_tr_clip, 'train_clips_dropped_shared_text': n_drop}
    write_json_atomic(out, a.out, indent=1)
    print(f'V1_SPLIT eval={len(ev)} (bench에 없음 {len(miss)}) val={len(val)} train={len(tr)} '
          f'train_clips={n_tr_clip} 문장공유로 제외={n_drop} → {a.out}', flush=True)
    return 0


# ── 데이터 ──────────────────────────────────────────────────────────────────
class Data:
    def __init__(self, bench_path, split, cand, log=print):
        self.b = b = Bench(bench_path)
        sp = json.load(open(split, encoding='utf-8'))
        if sp.get('bench_id') and sp['bench_id'] != b.bench_id:
            raise ValueError('split의 bench_id가 벤치와 다름')
        self.cols = [b.bs_names.index(k) for k in MOUTH_KEYS]
        ev, va, tr = set(sp['eval']), set(sp['val']), set(sp['train'])
        if ev & tr or va & tr or ev & va:
            raise ValueError('분할 겹침')
        held_txt = {FO.norm_text(c['text']) for c in b.clips if c['spk'] in ev | va}
        by_clip = defaultdict(list)
        for it in b.inst:
            if it['ok']:
                by_clip[it['c']].append(it)
        self.sent, self.words = [], []           # (X(T,27), target, spk)
        n_drop = n_low = 0
        for ci, c in enumerate(b.clips):
            if c['spk'] not in tr or c['flag'] or not c['text']:
                continue
            if FO.norm_text(c['text']) in held_txt:
                n_drop += 1
                continue
            X = b.bs[c['off']:c['off'] + c['n']][:, self.cols]
            if (~np.isnan(X[:, 0])).mean() < 0.5:
                n_low += 1
                continue
            X = fill_all(X)
            tg = decompose(c['text'])
            if len(X) >= 10 and tg:
                self.sent.append((X, np.array(tg, np.int64), c['spk']))
            for it in by_clip.get(ci, ()):
                s0, s1 = it['wide']
                tw = decompose(it['w'])
                if s1 - s0 >= 3 and tw:
                    self.words.append((X[s0:s1], np.array(tw, np.int64), c['spk']))
        lead, tail = _rest_runs(b, self.cols)
        self.lead = {s: v for s, v in lead.items() if s in tr}
        self.tail = {s: v for s, v in tail.items() if s in tr}
        self.cand = cand
        log(f'[data] cand={cand} train_spk={len(tr)} sent={len(self.sent)} words={len(self.words)} '
            f'문장공유 제외 클립={n_drop} 얼굴부족={n_low} 쉬는구간 화자={len(self.lead)}/{len(self.tail)}')
        # 검증 문항: product4way와 같은 어휘·오답·idle75 구성(평가 화자는 만들지 않는다)
        pool = list(b.dist_words)
        ps = set(pool)
        dis = Distractors(b, pool)
        self.val_items = []
        for it in b.inst:
            if it['ok'] and it['w'] in ps and it['spk'] in va:
                hard = Distractors.order([it['w']] + dis.hard(it['w']), it['iid'])
                self.val_items.append({'iid': it['iid'], 'spk': it['spk'], 'w': it['w'], 'inst': it,
                                       'labs': [decompose(w) for w in hard], 'tgt': hard.index(it['w'])})
        cnt = defaultdict(int)
        self.val_seq = {}
        for dup in DUPS:
            self.val_seq[dup] = [p4_sequences(b, x['inst'], self.cols, 'idle75', dup, 'wide', lead, tail, cnt)
                                 for x in self.val_items]
        self.val_cer_items = [(X, t) for X, t in ((fill_all(b.bs[c['off']:c['off'] + c['n']][:, self.cols]),
                                                   np.array(decompose(c['text']), np.int64))
                                                  for c in b.clips if c['spk'] in va and not c['flag'] and c['text'])
                              if len(X) >= 10 and len(t)]
        log(f'[data] val_spk={len(va)} val_4way_items={len(self.val_items)} val_sent={len(self.val_cer_items)} '
            f'vocab={len(pool)} idle_fallback={cnt.get("idle_fallback", 0)}')

    def idle_window(self, X, spk, rng):
        L = len(X)
        if L >= IDLE_LEN:
            return X
        need = IDLE_LEN - L
        nl = int(rng.integers(0, need + 1))
        nr = need - nl
        Lr, Rr = self.lead.get(spk), self.tail.get(spk)
        left = _tile(Lr[int(rng.integers(len(Lr)))], nl, True) if Lr else np.repeat(X[:1], nl, 0)
        right = _tile(Rr[int(rng.integers(len(Rr)))], nr, False) if Rr else np.repeat(X[-1:], nr, 0)
        return np.concatenate([left, X, right], 0).astype(np.float32)

    def epoch_items(self, rng):
        items = [(X, t, s, False) for X, t, s in self.sent] + [(X, t, s, True) for X, t, s in self.words]
        order = rng.permutation(len(items))
        return [items[i] for i in order]


# ── 검증 4지 ────────────────────────────────────────────────────────────────
def val_4way(model, data, dev):
    """→ {dup: 화자 평균 정확도}, 그리고 화자별 값. ctc_ll α=1, 동점은 후보 순서(첫 최대)."""
    import torch
    import torch.nn.functional as F
    model.eval()
    res, by_spk_all = {}, {}
    with torch.no_grad():
        for dup in DUPS:
            seqs = data.val_seq[dup]
            hits = defaultdict(list)
            for k in range(0, len(seqs), 256):
                ch = list(range(k, min(k + 256, len(seqs))))
                X = torch.from_numpy(np.stack([seqs[i] for i in ch])).to(dev)
                lp = F.log_softmax(model(X).float(), -1)               # (B,T,V)
                B, T, V = lp.shape
                lp4 = lp.repeat_interleave(4, 0).transpose(0, 1)        # (T,4B,V)
                labs = [data.val_items[i]['labs'][j] for i in ch for j in range(4)]
                tg = torch.tensor([x for l in labs for x in l], dtype=torch.long)
                tl = torch.tensor([len(l) for l in labs], dtype=torch.long)
                il = torch.full((len(labs),), T, dtype=torch.long)
                nll = F.ctc_loss(lp4.cpu().double(), tg, il, tl, blank=0, reduction='none', zero_infinity=False)
                sc = (-nll / tl.double() ** ALPHA).view(len(ch), 4).numpy()
                for r, i in enumerate(ch):
                    it = data.val_items[i]
                    hits[it['spk']].append(int(int(np.argmax(sc[r])) == it['tgt']))
            by = {s: float(np.mean(v)) for s, v in hits.items()}
            res[dup] = float(np.mean(list(by.values()))) if by else float('nan')
            by_spk_all[dup] = by
    return res, by_spk_all


def val_cer(model, data, dev):
    import torch
    model.eval()
    cs = []
    with torch.no_grad():
        for k in range(0, len(data.val_cer_items), 64):
            ch = data.val_cer_items[k:k + 64]
            X, lens = _pad([c[0] for c in ch])
            lo = forward_packed(model, X.to(dev), lens).cpu()
            for j, c in enumerate(ch):
                cs.append(cer(greedy_decode(lo[j, :int(lens[j])]), c[1].tolist()))
    return float(np.mean(cs)) if cs else float('nan')


# ── train ───────────────────────────────────────────────────────────────────
def cmd_train(a):
    import random
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    t0 = time.time()
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    random.seed(a.seed)
    rng = np.random.default_rng(a.seed)
    if a.threads:
        torch.set_num_threads(a.threads)
    os.makedirs(a.out, exist_ok=True)
    data = Data(a.bench, a.split, a.cand)
    if a.max_val:
        data.val_items = data.val_items[:a.max_val]
        data.val_seq = {d: v[:a.max_val] for d, v in data.val_seq.items()}
        data.val_cer_items = data.val_cer_items[:a.max_val]
    if not data.sent or not data.val_items:
        print('V1_TRAIN_FAIL 데이터 없음', flush=True)
        return 1
    perm = _mirror_perm()
    model = build(len(MOUTH_KEYS), len(VOCAB)).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    best, best_ep, bad, hist = -1.0, -1, 0, []
    for ep in range(a.epochs):
        model.train()
        items = data.epoch_items(rng)
        if a.max_items:
            items = items[:a.max_items]
        tl = 0.0
        nb = 0
        for k in range(0, len(items), a.batch):
            ch = items[k:k + a.batch]
            xs = []
            for X, t, s, is_w in ch:
                x = aug_raw(X, rng)
                if a.cand == 'B' and is_w and rng.random() < a.idle_p:
                    x = data.idle_window(x, s, rng)
                xs.append(aug_post(x, rng, perm))
            Xb, lens = _pad(xs)
            logp = F.log_softmax(forward_packed(model, Xb.to(dev), lens), -1).transpose(0, 1)
            tg = torch.from_numpy(np.concatenate([c[1] for c in ch])).to(dev)
            tlen = torch.tensor([len(c[1]) for c in ch], dtype=torch.int64)
            loss = ctc(logp, tg, lens, tlen)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tl += loss.item()
            nb += 1
        if ep % a.eval_every == a.eval_every - 1 or ep == a.epochs - 1:
            acc, by = val_4way(model, data, dev)
            m = float(np.mean([acc[d] for d in DUPS]))
            vc = val_cer(model, data, dev)
            rec = {'epoch': ep, 'train_ctc': round(tl / max(nb, 1), 4), 'val_4way': {str(d): round(acc[d], 4) for d in DUPS},
                   'val_4way_mean': round(m, 4), 'val_cer': round(vc, 4), 'sec': round(time.time() - t0)}
            hist.append(rec)
            print(f'ep{ep:3d} ctc={rec["train_ctc"]:.3f} val4 dup2={acc[2]:.3f} dup1={acc[1]:.3f} mean={m:.3f} '
                  f'cer={vc:.3f} {rec["sec"]}s', flush=True)
            if m > best:
                best, best_ep, bad = m, ep, 0
                state = {k2: v.detach().cpu() for k2, v in model.state_dict().items()}
                meta = {'cand': a.cand, 'seed': a.seed, 'epoch': ep, 'val_4way': rec['val_4way'],
                        'val_4way_mean': rec['val_4way_mean'], 'val_cer': rec['val_cer'], 'split': os.path.abspath(a.split),
                        'bench_id': data.b.bench_id, 'batch': a.batch, 'lr': a.lr, 'idle_p': a.idle_p if a.cand == 'B' else 0}
                mp = os.path.join(a.out, 'model.pt')
                torch.save({'state': state, 'vocab': VOCAB, 'mouth_keys': MOUTH_KEYS, 'meta': meta}, mp + '.tmp')
                os.replace(mp + '.tmp', mp)
                best_by = by
            else:
                bad += 1
                if bad >= a.patience:
                    print(f'조기 종료: {a.patience}회 검증 동안 나아지지 않음', flush=True)
                    break
    summ = {'cand': a.cand, 'seed': a.seed, 'best_epoch': best_ep, 'best_val_4way_mean': best,
            'best': [h for h in hist if h['epoch'] == best_ep][0], 'best_by_spk': {str(d): best_by[d] for d in DUPS},
            'history': hist, 'n_sent': len(data.sent), 'n_words': len(data.words), 'n_val_items': len(data.val_items),
            'time_sec': round(time.time() - t0), 'device': dev}
    write_json_atomic(summ, os.path.join(a.out, 'train_summary.json'), indent=1)
    print(f'V1_TRAIN_DONE cand={a.cand} seed={a.seed} best_ep={best_ep} val4_mean={best:.4f} → {a.out}/model.pt', flush=True)
    return 0


# ── select ──────────────────────────────────────────────────────────────────
def cmd_select(a):
    rows = []
    for order, d in enumerate([x for x in a.runs.split(',') if x]):
        s = json.load(open(os.path.join(d, 'train_summary.json'), encoding='utf-8'))
        for dj, dup in enumerate(DUPS):
            rows.append((-s['best']['val_4way'][str(dup)], order, dj, d, dup, s['cand'], s['seed'], s['best_epoch']))
    rows.sort()
    r = rows[0]
    out = {'rule': '각 run 최고 체크포인트에서 (run, dup) 중 검증 4지(ctc_ll α=1, idle75) 최대, 동점은 run 목록 순서·dup2 먼저',
           'selected': {'run': r[3], 'model': os.path.join(r[3], 'model.pt'), 'dup': r[4], 'cand': r[5], 'seed': r[6],
                        'epoch': r[7], 'val_4way': -r[0]},
           'table': [{'run': x[3], 'cand': x[5], 'seed': x[6], 'dup': x[4], 'epoch': x[7], 'val_4way': -x[0]}
                     for x in sorted(rows, key=lambda x: (x[1], x[2]))]}
    write_json_atomic(out, a.out, indent=1)
    for t in out['table']:
        print(f"  {t['cand']} s{t['seed']} dup{t['dup']} ep{t['epoch']} val4={t['val_4way']:.4f}", flush=True)
    print(f"V1_SELECT run={r[3]} cand={r[5]} seed={r[6]} dup={r[4]} val4={-r[0]:.4f}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('split')
    s.add_argument('--bench', required=True)
    s.add_argument('--eval-list', required=True)
    s.add_argument('--val-n', type=int, default=12)
    s.add_argument('--out', required=True)
    t = sub.add_parser('train')
    t.add_argument('--bench', required=True)
    t.add_argument('--split', required=True)
    t.add_argument('--cand', choices=['A', 'B'], required=True)
    t.add_argument('--seed', type=int, default=0)
    t.add_argument('--out', required=True)
    t.add_argument('--epochs', type=int, default=60)
    t.add_argument('--batch', type=int, default=64)
    t.add_argument('--lr', type=float, default=3e-4)
    t.add_argument('--eval-every', type=int, default=2)
    t.add_argument('--patience', type=int, default=10)
    t.add_argument('--idle-p', type=float, default=0.5)
    t.add_argument('--threads', type=int, default=0)
    t.add_argument('--max-items', type=int, default=0, help='시험용: 에폭당 학습 항목 상한')
    t.add_argument('--max-val', type=int, default=0, help='시험용: 검증 문항 상한')
    e = sub.add_parser('select')
    e.add_argument('--runs', required=True)
    e.add_argument('--out', required=True)
    a = ap.parse_args()
    try:
        rc = {'split': cmd_split, 'train': cmd_train, 'select': cmd_select}[a.cmd](a)
    except Exception as ex:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f'V1_{a.cmd.upper()}_FAIL {type(ex).__name__}: {str(ex)[:200]}', flush=True)
        rc = 1
    sys.exit(rc)


if __name__ == '__main__':
    main()
