"""Seal existing prepared E2 inputs and selected models. Does not run inference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from clean_eval_prepare import ROOT,REPO,TOOLS,save


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(2**20):h.update(b)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--k-selection',type=Path,required=True)
    ap.add_argument('--b33-selection',type=Path,required=True)
    ap.add_argument('--r2',type=Path,required=True)
    a=ap.parse_args()
    assert not (ROOT/'JUDGE_ONCE').exists()
    audit=json.loads((ROOT/'final-cohort-audit.json').read_text(encoding='utf-8'))
    assert audit['status']=='items-prepared' and audit['persons']>=30
    models={};selections=[]
    for key,path in [('K',a.k_selection),('B33',a.b33_selection)]:
        d=json.loads(path.read_text(encoding='utf-8'))['selected']
        model=Path(d['model'])
        assert model.is_file(),str(model)
        models[key]={'path':str(model),'sha256':sha(model),'dup':int(d['dup']),
                      'selection':str(path),'selection_sha256':sha(path)}
        selections.extend([path,model])
    models['R2']={'path':str(a.r2),'sha256':sha(a.r2),'dup':1,'report_only':True}
    save('models.json',models)
    wanted=['manifest.tsv','selected-meta.json','preparation-contract.json','bench_final.pkl','bench-metadata.json',
        'items.json','item-parity.json','eval.txt','split.json','final-cohort-audit.json','roi-check.json','models.json','d/spans.jsonl']
    paths=[ROOT/n for n in wanted]
    for dirname,pattern in [('clips','*.mp4'),('clips','*.wav'),('bs','*.json'),('roi','*.npz')]:
        paths.extend(sorted((ROOT/dirname).glob(pattern)))
    paths.extend(selections+[a.r2])
    paths.extend(REPO/'scripts'/n for n in ['clean_eval_prepare.py','clean_eval_prepare.ps1','clean_eval_items.py','clean_eval_judge.py','clean_eval_seal.py',
        'lipread_v1/v1_538_spans.py','lipread_roi/roi_train.py','lipread_roi/roi_pair.py'])
    paths.extend(TOOLS/n for n in ['d_bench.py','build_cd.py','train_lipread.py','folds.py','lip_roi_extract.py','extract_blendshapes.py','train_lip_roi.py','face_landmarker.task'])
    paths.append(REPO/'docs/lipread-e2-reuse-prereg-v2-2026-11-02.md')
    files=[{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(paths),key=str)]
    save('seal.json',{'status':'sealed','label':'절반 1 14명, E2 코호트 재사용, R2 겹침 미확인',
        'persons':audit['persons'],'halves':audit['halves'],'items':audit['items'],
        'files':files,'candidate_inference':0,'network_requests':0,
        'commit_before_seal':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'role':'permanently evaluation-only; no training/tuning/selection'})
    summary={'seal_sha256':sha(ROOT/'seal.json'),'files':len(files),'persons':audit['persons'],
             'halves':audit['halves'],'items':audit['items'],'candidate_inference':0,'network_requests':0}
    save('seal-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
