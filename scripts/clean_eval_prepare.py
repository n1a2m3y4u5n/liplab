"""CPU-only E2 reuse v2 preparation. No candidate model inference or network."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
BASE = Path(r'D:\work\hq\projects\liplab-lab')
ROOT = BASE / 'data/clean_eval_2026-11'
SOURCE = BASE / 'data/e2_538'
TOOLS = BASE / 'tools'
MP = BASE / 'venv-mp/Scripts/python.exe'
APP = Path(r'D:\work\hq\projects\liplab\.venv\Scripts\python.exe')
os.environ.update(CUDA_VISIBLE_DEVICES='-1', DGOP_DEVICE='cpu', HF_HUB_OFFLINE='1',
                  OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
                  PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONPATH=str(TOOLS), LIPLAB_TOOLS=str(TOOLS))


def save(name, obj):
    (ROOT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def ram_guard():
    while True:
        r = subprocess.run(['powershell','-NoProfile','-Command',
            '(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'], capture_output=True, text=True, check=True)
        if int(r.stdout.strip()) >= 8*1024**2:
            return
        save('status.json', {'status':'waiting-memory','pid':os.getpid(),'time':time.time()})
        time.sleep(30)


def run(tag, cmd):
    ram_guard()
    marker=ROOT/(tag+'.done')
    if marker.exists():
        return
    save('status.json', {'status':'preparing','stage':tag,'pid':os.getpid(),'time':time.time()})
    with (ROOT/(tag+'.log')).open('a',encoding='utf-8') as f:
        p=subprocess.Popen([str(x) for x in cmd], cwd=REPO, stdout=f, stderr=subprocess.STDOUT)
        save('child.json', {'stage':tag,'pid':p.pid,'parent':os.getpid(),'time':time.time()})
        # Stop only our child when memory drops; leave other jobs untouched.
        while p.poll() is None:
            time.sleep(15)
            r=subprocess.run(['powershell','-NoProfile','-Command',
                '(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'],capture_output=True,text=True,check=True)
            if int(r.stdout.strip()) < 8*1024**2:
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
                raise RuntimeError('own preparation stopped: available RAM below 8GB; resumable stage')
        if p.returncode:
            raise RuntimeError(tag+' failed; see '+str(ROOT/(tag+'.log')))
    marker.write_text('completed\n',encoding='utf-8')


def materialize():
    ROOT.mkdir(parents=True,exist_ok=True)
    prereg=REPO/'docs/lipread-e2-reuse-prereg-v2-2026-11-02.md'
    committed=subprocess.run(['git','show','HEAD:docs/lipread-e2-reuse-prereg-v2-2026-11-02.md'],
        cwd=REPO,capture_output=True,check=True).stdout
    assert prereg.read_bytes().replace(b'\r\n',b'\n') == committed.replace(b'\r\n',b'\n')
    texts={}
    for name in ('run_base','run_k'):
        d=json.loads((BASE/'data/roi-kmsav'/name/'prep.json').read_text(encoding='utf-8'))
        texts[name]={''.join(re.findall('[가-힣]',c['text'])) for c in d['clips'] if c['role']=='train' and c.get('text')}
    excluded=texts['run_base']|texts['run_k']
    meta=json.loads((SOURCE/'manifest-meta.json').read_text(encoding='utf-8'))
    byclip={r['clip']:r for r in meta}
    rows=[]
    for line in (SOURCE/'manifest.tsv').read_text(encoding='utf-8').splitlines():
        a=line.split('\t')
        if len(a)==3 and ''.join(re.findall('[가-힣]',a[2])) not in excluded:
            rows.append(a)
    counts={s:sum(a[1]==s for a in rows) for s in {a[1] for a in rows}}
    rows=[a for a in rows if counts[a[1]]>=3]
    assert len(rows)==304 and len({a[1] for a in rows})==32
    (ROOT/'clips').mkdir(exist_ok=True);(ROOT/'bs').mkdir(exist_ok=True)
    manifest=''.join('\t'.join(a)+'\n' for a in rows)
    (ROOT/'manifest.tsv').write_text(manifest,encoding='utf-8')
    selected=[]; jobs=[]
    for a in rows:
        clip=Path(a[0]).stem
        for ext in ('.mp4','.wav'):
            src=SOURCE/'clips'/(clip+ext);dest=ROOT/'clips'/src.name
            if not dest.exists():
                shutil.copy2(src,dest)
            assert dest.stat().st_size==src.stat().st_size
        selected.append(byclip[clip])
        if not (ROOT/'bs'/(clip+'.json')).exists():
            jobs.append(str(ROOT/'clips'/(clip+'.mp4'))+'\t'+str(ROOT/'bs'/(clip+'.json')))
    (ROOT/'bs-list.tsv').write_text('\n'.join(jobs)+'\n',encoding='utf-8')
    save('selected-meta.json',selected)
    save('preparation-contract.json',{'prereg_sha256':hashlib.sha256(prereg.read_bytes()).hexdigest(),
        'role':'evaluation-only; never train/tune/select','persons':32,'clips':304,
        'network_requests':0,'candidate_inference':0,'source':str(SOURCE)})


def main():
    materialize()
    run('blendshapes',[MP,TOOLS/'extract_blendshapes.py','--list',ROOT/'bs-list.tsv','--lips','--no-audio'])
    run('roi',[MP,TOOLS/'lip_roi_extract.py','--clips',ROOT/'clips','--out',ROOT/'roi','--workers','2','--preview','0'])
    run('spans',[APP,REPO/'scripts/lipread_v1/v1_538_spans.py','--tools',TOOLS,'--backend',REPO/'backend',
        '--aligner',Path(r'D:\work\hq\projects\liplab\backend\models\dgop_ours\aligner'),
        '--threads','2','--','--data',ROOT,'--out',ROOT/'d','--manifest',ROOT/'manifest.tsv','--bs',ROOT/'bs','--clips',ROOT/'clips'])
    run('build',[APP,TOOLS/'d_bench.py','build','--spans',ROOT/'d/spans.jsonl','--bs',ROOT/'bs',
        '--rule','3,3','--out',ROOT/'bench_e2_reuse.pkl'])
    run('roi-check',[MP,TOOLS/'train_lip_roi.py','check','--bench',ROOT/'bench_e2_reuse.pkl','--roi',ROOT/'roi','--out',ROOT/'roi-check.json'])
    save('status.json',{'status':'preprocessed-awaiting-item-audit','pid':os.getpid(),'time':time.time(),
                        'candidate_inference':0,'network_requests':0})


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        ROOT.mkdir(parents=True,exist_ok=True)
        save('status.json',{'status':'blocked','error':str(e),'pid':os.getpid(),'time':time.time()})
        raise
