"""Seal existing prepared E2 inputs and selected models. Does not run inference."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from clean_eval_prepare import ROOT,REPO,TOOLS,save


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(2**20):h.update(b)
    return h.hexdigest()


def freeze_models(a):
    assert all((a.k_selection,a.b33_selection,a.r2)),'selected model paths required for final seal'
    models={};selections=[]
    frozen=ROOT/'models';frozen.mkdir(exist_ok=True)
    for key,path in [('K',a.k_selection),('B33',a.b33_selection)]:
        d=json.loads(path.read_text(encoding='utf-8'))['selected']
        model=Path(d['model'])
        assert model.is_file(),str(model)
        target=frozen/(key+'.pt');selcopy=frozen/(key+'-selection.json')
        shutil.copy2(model,target);shutil.copy2(path,selcopy)
        assert sha(model)==sha(target) and sha(path)==sha(selcopy)
        models[key]={'path':str(target),'sha256':sha(target),'dup':int(d['dup']),
                      'selection':str(selcopy),'selection_sha256':sha(selcopy),'original_model':str(model)}
        selections.extend([selcopy,target])
    r2copy=frozen/'R2.onnx';shutil.copy2(a.r2,r2copy)
    assert sha(a.r2)==sha(r2copy)
    models['R2']={'path':str(r2copy),'sha256':sha(r2copy),'dup':1,'report_only':True,'original_model':str(a.r2)}
    save('models.json',models)
    return selections+[r2copy]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-only',action='store_true')
    ap.add_argument('--k-selection',type=Path)
    ap.add_argument('--b33-selection',type=Path)
    ap.add_argument('--r2',type=Path)
    a=ap.parse_args()
    assert not (ROOT/'JUDGE_ONCE').exists()
    audit=json.loads((ROOT/'final-cohort-audit.json').read_text(encoding='utf-8'))
    assert audit['status']=='items-prepared' and audit['persons']>=30
    model_paths=[] if a.data_only else freeze_models(a)
    prereg=REPO/'docs/lipread-e2-reuse-prereg-v2-2026-11-02.md'
    snapshot=ROOT/'prereg-before-seal.md'
    if not snapshot.exists():
        shutil.copy2(prereg,snapshot)
    assert prereg.read_bytes().replace(b'\r\n',b'\n').startswith(snapshot.read_bytes().replace(b'\r\n',b'\n'))
    old_seal=ROOT/'data-seal.json'
    if old_seal.exists():
        old=json.loads(old_seal.read_text(encoding='utf-8'))
        for r in old['files']:
            assert sha(Path(r['path']))==r['sha256'],'frozen data/code changed: '+r['path']
    wanted=['manifest.tsv','selected-meta.json','preparation-contract.json','bench_final.pkl','bench-metadata.json',
        'items.json','item-parity.json','eval.txt','split.json','final-cohort-audit.json','alignment-audit.json','roi-check.json','d/spans.jsonl','prereg-before-seal.md']
    if not a.data_only:
        wanted.append('models.json')
    paths=[ROOT/n for n in wanted]
    for dirname,pattern in [('clips','*.mp4'),('clips','*.wav'),('bs','*.json'),('roi','*.npz')]:
        paths.extend(sorted((ROOT/dirname).glob(pattern)))
    paths.extend(model_paths)
    paths.extend(REPO/'scripts'/n for n in ['clean_eval_prepare.py','clean_eval_prepare.ps1','clean_eval_items.py','clean_eval_judge.py','clean_eval_seal.py',
        'lipread_v1/v1_538_spans.py','lipread_roi/roi_train.py','lipread_roi/roi_pair.py'])
    paths.extend(TOOLS/n for n in ['d_bench.py','build_cd.py','train_lipread.py','folds.py','lip_roi_extract.py','extract_blendshapes.py','train_lip_roi.py','face_landmarker.task'])
    files=[{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(paths),key=str)]
    source=ROOT.parent/'e2_538/clips'
    for r in files:
        p=Path(r['path'])
        if p.parent==ROOT/'clips':
            assert sha(source/p.name)==r['sha256'],'source/copy mismatch: '+p.name
    name='data-seal.json' if a.data_only else 'seal.json'
    save(name,{'status':'data-sealed-awaiting-models' if a.data_only else 'sealed','label':'절반 1 14명, E2 코호트 재사용, R2 겹침 미확인',
        'persons':audit['persons'],'halves':audit['halves'],'items':audit['items'],
        'files':files,'candidate_inference':0,'network_requests':0,
        'commit_before_seal':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'role':'permanently evaluation-only; no training/tuning/selection'})
    summary={'seal_sha256':sha(ROOT/name),'seal_path':str(ROOT/name),'files':len(files),'persons':audit['persons'],
             'halves':audit['halves'],'items':audit['items'],'candidate_inference':0,'network_requests':0}
    save('data-seal-summary.json' if a.data_only else 'seal-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
