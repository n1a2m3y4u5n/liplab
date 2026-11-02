"""Choose the first idle 3060 after its registered ROI queue; never claim twice."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(r'D:\work\hq\projects\liplab-lab\data\nextreg_2026-11')
BASE = Path(r'D:\work\hq\projects\liplab-lab\data\roi-kmsav\run_base')
HOST = 'korea@100.84.54.20'
REMOTE = 'D:/work/hq/projects/liplab-gpu2/nextreg_2026-11'
PYTHON = r'D:\work\hq\projects\liplab\.venv\Scripts\python.exe'
QUEUE = r'D:\work\hq\projects\liplab-wt\nextreg\scripts\nextreg_gpu_queue.ps1'


def log(s):
    with (ROOT/'roi-dispatch.log').open('a', encoding='utf-8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ')+s+'\n')


def call(args):
    try:
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=35).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def remote_ready():
    if not call(['ssh','-n','-o','BatchMode=yes',HOST,'powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',REMOTE+'/ready.ps1']):
        return False
    p = ROOT/'main-ready.json'
    if not call(['scp','-o','BatchMode=yes',HOST+':'+REMOTE+'/ready.json',str(p)]):
        return False
    return json.loads(p.read_text(encoding='utf-8-sig')).get('ready', False)


def local_ready():
    if not (BASE/'run_B33s0/train_summary.json').exists():
        return False
    if not call(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'ready-local.ps1')]):
        return False
    return json.loads((ROOT/'local-ready.json').read_text(encoding='utf-8-sig')).get('ready', False)


def main():
    claim = ROOT/'roi-claim.json'
    if claim.exists():
        raise SystemExit('Dispatcher already claimed a GPU; do not duplicate')
    while True:
        if local_ready():
            selected = 'lab-sub'
            break
        if remote_ready():
            selected = 'lab-main'
            break
        log('waiting: B33s0/sub or K2s1/main complete and GPU idle')
        time.sleep(30)
    claim.write_text(json.dumps({'pc':selected,'time':time.strftime('%Y-%m-%d %H:%M:%S')}),encoding='utf-8')
    log('CLAIM '+selected)
    if selected == 'lab-sub':
        p = subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',QUEUE,
                              '-Mode','roi','-Root',str(ROOT),'-Python',PYTHON],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        log('local queue PID='+str(p.pid))
    else:
        if not call(['ssh','-n','-o','BatchMode=yes',HOST,'powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',REMOTE+'/launch-roi.ps1']):
            raise RuntimeError('Claimed main but launch failed; no fallback duplication')
    # Supply only finished same-seed B33 checkpoints. Never read evaluation outputs.
    copied = set()
    def mark(seed):
        marker = ROOT/('baseline_s%d.ready'%seed)
        marker.write_text('copy complete', encoding='utf-8')
        return selected == 'lab-sub' or call(['scp','-o','BatchMode=yes',str(marker),HOST+':'+REMOTE+'/'+marker.name])
    while len(copied) < 2:
        if 0 not in copied and (BASE/'run_B33s0/train_summary.json').exists():
            src = BASE/'run_B33s0/model.pt'
            if selected == 'lab-sub':
                shutil.copyfile(src, ROOT/'baseline_s0.pt')
                if mark(0): copied.add(0)
            elif call(['scp','-o','BatchMode=yes',str(src),HOST+':'+REMOTE+'/baseline_s0.pt']):
                if mark(0): copied.add(0)
        if 1 not in copied:
            summary = call(['scp','-o','BatchMode=yes',HOST+':D:/work/hq/projects/liplab-gpu2/data/run_base/run_B33s1/train_summary.json',str(ROOT/'baseline_s1-summary.json')])
            if summary and call(['scp','-o','BatchMode=yes',HOST+':D:/work/hq/projects/liplab-gpu2/data/run_base/run_B33s1/model.pt',str(ROOT/'baseline_s1.pt')]):
                if selected == 'lab-sub' or call(['scp','-o','BatchMode=yes',str(ROOT/'baseline_s1.pt'),HOST+':'+REMOTE+'/baseline_s1.pt']):
                    if mark(1): copied.add(1)
        log('finished baseline checkpoints supplied: '+str(sorted(copied)))
        if len(copied) < 2:
            time.sleep(30)


if __name__ == '__main__':
    main()
