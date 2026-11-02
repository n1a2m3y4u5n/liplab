"""One-shot E2 reuse v2 judgement. Requires sealed inputs and coordinator release."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\work\hq\projects\liplab-lab\data\clean_eval_2026-11')
TOOLS=Path(r'D:\work\hq\projects\liplab-lab\tools')
os.environ.update(CUDA_VISIBLE_DEVICES='-1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',HF_HUB_OFFLINE='1',LIPLAB_TOOLS=str(TOOLS))
sys.path[:0]=[str(TOOLS),str(REPO/'scripts/lipread_roi')]
import numpy as np
import roi_train as RT

LABEL='절반 1 14명, E2 코호트 재사용, R2 겹침 미확인'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(2**20):
            h.update(b)
    return h.hexdigest()


def boot(by):
    v=np.array([by[s] for s in sorted(by)],float)
    rng=np.random.default_rng(0)
    samples=v[rng.integers(0,len(v),(10000,len(v)))].mean(1)
    return {'mean':float(v.mean()),'ci':[float(x) for x in np.percentile(samples,[2.5,97.5])]}


def paired(a,b):
    assert set(a)==set(b)
    return boot({s:a[s]-b[s] for s in a})


def sequences(items):
    cache={};seqs=[]
    meta=json.loads((ROOT/'bench-metadata.json').read_text(encoding='utf-8'))
    for it in items:
        frames=[]
        for ci,fr in it['window']:
            if ci not in cache:
                with np.load(ROOT/'roi'/(meta['clips'][ci]['clip']+'.npz'),allow_pickle=False) as z:
                    cache[ci]=z['roi']
            assert fr<len(cache[ci])
            frames.append(cache[ci][fr])
        seqs.append(np.stack(frames))
    return seqs


def gather(gl):
    L=max(len(g) for g in gl);Tp=int(np.ceil(L/4.0)*4)
    x=np.zeros((len(gl),Tp,80,80),np.uint8)
    for i,g in enumerate(gl):
        x[i,:len(g)]=g[:,4:84,4:84]
    return x,np.array([len(g) for g in gl],np.int64)


def score_onnx(path,seqs,items):
    import onnxruntime as ort
    import torch
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    s=ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])
    hits=defaultdict(list)
    for g,it in zip(seqs,items):
        X,lens=gather([g]);x=X[0,:int(lens[0])].astype(np.float64)/255.0
        x=x-x.mean();x=x/max(float(np.sqrt((x*x).mean())),1e-2)
        lo=s.run(['logits'],{'roi_z':x[None].astype(np.float32)})[0][0]
        lp=torch.log_softmax(torch.from_numpy(lo).float(),-1)
        hits[it['spk']].append(int(int(np.argmax(RT.ctc_scores(lp,it['labs'])))==it['tgt']))
    return {s:float(np.mean(v)) for s,v in hits.items()}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--authorize-file',required=True,help='coordinator release JSON with kmsav_complete/start_e2_reuse true')
    a=ap.parse_args()
    auth=json.loads(Path(a.authorize_file).read_text(encoding='utf-8-sig'))
    assert auth.get('kmsav_complete') is True and auth.get('start_e2_reuse') is True
    seal=json.loads((ROOT/'seal.json').read_text(encoding='utf-8'))
    assert seal['status']=='sealed' and seal['candidate_inference']==0
    for r in seal['files']:
        assert sha(r['path'])==r['sha256'],r['path']
    models=json.loads((ROOT/'models.json').read_text(encoding='utf-8'))
    items=json.loads((ROOT/'items.json').read_text(encoding='utf-8'))
    assert len({it['spk'] for it in items})>=30
    assert all(len(it['labels'])==4 for it in items)
    for it in items:
        it['labs']=it['labels'];it['tgt']=it['target']
    # Claim once before loading models; a failed inference is not silently retried.
    fd=os.open(str(ROOT/'JUDGE_ONCE'),os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        json.dump({'authorization':auth,'seal_sha256':sha(ROOT/'seal.json')},f,ensure_ascii=False)
    import torch
    torch.set_num_threads(2)
    seqs=sequences(items);by={}
    for name in ('K','B33','R2'):
        m=models[name]
        if name=='R2':
            by[name]=score_onnx(m['path'],seqs,items)
        else:
            front,head,ck=RT.load_model(m['path'],'cpu')
            vals=RT.score4(front,head,None,seqs,items,'cpu',False,gather)
            by[name]=vals[int(m['dup'])]
            del front,head,ck
        assert set(by[name])=={it['spk'] for it in items}
        (ROOT/('scores_'+name+'.json')).write_text(json.dumps(by[name],indent=2),encoding='utf-8')
    delta=paired(by['K'],by['B33']);cand=boot(by['K'])
    result={'label':LABEL,'speakers':len(by['K']),'items':len(items),'main':delta,
        'K':cand,'B33':boot(by['B33']),'pass_structure':bool(delta['mean']>=.05 and delta['ci'][0]>0),
        'pass_product':bool(cand['mean']>=.40 and cand['ci'][0]>.30),
        'report_only':{'R2':boot(by['R2']),'K_minus_R2':paired(by['K'],by['R2']),
                       'B33_minus_R2':paired(by['B33'],by['R2'])},
        'app_default_off':True,'inference_once':True}
    (ROOT/'verdict.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
