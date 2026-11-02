"""Metadata-only final cohort/item audit; never loads a candidate checkpoint."""
import collections
import json
import os
from pathlib import Path
import sys

from clean_eval_prepare import ROOT, TOOLS, save
sys.path[:0]=[str(TOOLS),str(Path(__file__).resolve().parent/'lipread_roi')]
import numpy as np
import roi_train as RT
from d_bench import Bench
from train_lipread import MOUTH_KEYS
from roi_pair import check_items


def main():
    b=Bench(str(ROOT/'bench_e2_reuse.pkl'))
    ck=json.loads((ROOT/'roi-check.json').read_text(encoding='utf-8'))
    if ck['fails']:
        raise ValueError('ROI contract check failed: '+str(ck['fails']))
    spks={c['spk'] for c in b.clips}
    initial=RT.h4_items(b,spks)
    good=set();bad=[]
    for ci,c in enumerate(b.clips):
        p=ROOT/'roi'/(c['clip']+'.npz')
        if c['flag'] or not p.exists():
            bad.append({'clip':c['clip'],'reason':'flagged or missing ROI'});continue
        with np.load(p,allow_pickle=False) as z:
            v=z['valid']
            if len(v)!=c['n'] or float(v.mean())<0.5:
                bad.append({'clip':c['clip'],'reason':'ROI valid below .5 or length mismatch'});continue
        good.add(ci)
    byspk=collections.defaultdict(set)
    for it in initial:
        if it['inst']['c'] in good:
            byspk[it['spk']].add(it['inst']['c'])
    eligible={s for s,cs in byspk.items() if len(cs)>=3}
    sel=json.loads((ROOT/'selected-meta.json').read_text(encoding='utf-8'))
    half={x['spk']:x['half'] for x in sel}
    audit={'persons':len(eligible),'halves':dict(collections.Counter(half[s] for s in eligible)),
        'by_spk_valid_item_clips':{s:len(byspk[s]) for s in sorted(spks)},
        'removed_spk':sorted(spks-eligible),'bad_clips':bad,'candidate_inference':0,
        'network_requests':0,'label':'절반 1 14명, E2 코호트 재사용, R2 겹침 미확인',
        'status':'blocked' if len(eligible)<30 else 'auditing-windows'}
    save('final-cohort-audit.json',audit)
    if len(eligible)<30:
        save('status.json',audit)
        print(json.dumps(audit,ensure_ascii=False));return 3
    # Keep fixed vocabulary/distractor construction; exclude disallowed instances only.
    for it in b.meta['instances']:
        if it['c'] not in good or it['spk'] not in eligible:
            it['ok']=False
    for ci,c in enumerate(b.meta['clips']):
        if ci not in good:
            c['flag']=True
    with np.load(ROOT/'bench_e2_reuse.pkl',allow_pickle=False) as z:
        arrays={k:z[k] for k in z.files}
    arrays['meta_json']=np.frombuffer(json.dumps(b.meta,ensure_ascii=False).encode('utf-8'),dtype=np.uint8)
    with (ROOT/'bench_final.pkl').open('wb') as f:
        np.savez_compressed(f,**arrays)
    b=Bench(str(ROOT/'bench_final.pkl'))
    save('bench-metadata.json',b.meta)
    rep,problems=check_items(b,eligible)
    if problems or rep['win_none_roi'] or rep['win_none_v1']:
        save('item-parity.json',{'report':rep,'problems':problems})
        raise ValueError('item/window contract failed')
    save('item-parity.json',{'report':rep,'problems':problems})
    cols=[b.bs_names.index(k) for k in MOUTH_KEYS]
    lead,tail=RT.rest_runs_idx(b,cols,eligible)
    items=[]
    for it in RT.h4_items(b,eligible):
        win=RT.p4_window(b,it['inst'],cols,lead,tail)
        assert win is not None and len(win)==75 and len(it['labs'])==4
        for ci,fr in win:
            assert ci in good and (ROOT/'roi'/(b.clips[ci]['clip']+'.npz')).exists()
        items.append({'iid':it['iid'],'spk':it['spk'],'word':it['w'],'target':it['tgt'],
            'labels':it['labs'],'clip':b.clips[it['inst']['c']]['clip'],'window':win})
    save('items.json',items)
    (ROOT/'eval.txt').write_text('\n'.join(sorted(eligible))+'\n',encoding='utf-8')
    save('split.json',{'bench_id':b.bench_id,'eval':sorted(eligible),'train':[],'val':[],
        'role':'evaluation-only; permanently forbidden for training/tuning/selection'})
    audit.update(status='items-prepared',items=len(items),vocab=len(b.dist_words))
    save('final-cohort-audit.json',audit);save('status.json',audit)
    print(json.dumps({k:v for k,v in audit.items() if k!='bad_clips'},ensure_ascii=False))
    return 0


if __name__=='__main__':
    sys.exit(main())
