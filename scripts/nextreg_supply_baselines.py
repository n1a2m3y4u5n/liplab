"""Copy completed B33 baselines to the black queue; never start GPU work."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(r'D:\work\hq\projects\liplab-lab\data\nextreg_2026-11')
BASE = Path(r'D:\work\hq\projects\liplab-lab\data\roi-kmsav\run_base')
BLACK = 'cnsai@100.87.95.61:D:/work/liplab-gpu3/nextreg_2026-11/'
MAIN = 'korea@100.84.54.20:D:/work/hq/projects/liplab-gpu2/data/run_base/run_B33s1/'


def call(args):
    try:
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def main():
    done = set()
    while len(done) < 2:
        for seed in (0, 1):
            if seed in done:
                continue
            model = BASE/'run_B33s0/model.pt' if seed == 0 else ROOT/'baseline_s1.pt'
            ready = (BASE/'run_B33s0/train_summary.json').is_file() if seed == 0 else False
            if seed == 1:
                ready = call(['scp','-o','BatchMode=yes',MAIN+'train_summary.json',str(ROOT/'baseline_s1-summary.json')])
                if ready:
                    ready = call(['scp','-o','BatchMode=yes',MAIN+'model.pt',str(model)])
            if not ready:
                continue
            import torch
            ck = torch.load(model, map_location='cpu', weights_only=False)
            assert ck['meta']['seed'] == seed
            assert 'run_base' in ck['meta']['run']
            del ck
            if not call(['scp','-o','BatchMode=yes',str(model),BLACK+'baseline_s%d.pt'%seed]):
                continue
            marker = ROOT/('baseline_s%d.ready'%seed)
            marker.write_text('completed same-seed B33 copied', encoding='utf-8')
            if call(['scp','-o','BatchMode=yes',str(marker),BLACK+marker.name]):
                done.add(seed)
        with (ROOT/'baseline-supply.log').open('a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ')+json.dumps(sorted(done))+'\n')
        if len(done) < 2:
            time.sleep(30)


if __name__ == '__main__':
    main()
