"""Prepare only permitted 33/12-speaker inputs, without opening evaluation frames."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(r'D:\work\hq\projects\liplab-lab')
OUT = ROOT/'data/nextreg_2026-11'
REPO = Path(__file__).resolve().parents[1]


def main():
    prep = json.loads((ROOT/'data/roi-kmsav/run_base/prep.json').read_text(encoding='utf-8'))
    train_indices = {int(item[0]) for item in prep['sent']}
    allowed = {c['clip']: c['spk'] for i, c in enumerate(prep['clips']) if c['role'] == 'val' or i in train_indices}
    speakers = set(prep['meta']['train_spk']) | set(prep['meta']['val_spk'])
    assert len(speakers) == 45 and {c['role'] for c in prep['clips']} == {'train', 'val'}
    spans = {}
    for line in (ROOT/'data/train538/v1prep/d/spans.jsonl').read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r['clip'] in allowed:
            assert r['spk'] == allowed[r['clip']]
            spans[r['clip']] = line
    report = {'allowed_speakers': sorted(speakers), 'allowed_clips': len(allowed), 'missing_spans': len(set(allowed)-set(spans)), 'kept': 0, 'low_lips': 0}
    with zipfile.ZipFile(OUT/'bs-input.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        kept = []
        for clip in sorted(spans):
            p = ROOT/'data/train538/rebuild/real_bs'/(clip+'.json')
            d = json.loads(p.read_text(encoding='utf-8'))
            valid = sum(f.get('lips') is not None and len(f['lips']) == 80 for f in d['frames'])
            if valid/max(d.get('n_read', d['n_frames']), 1) < .8:
                report['low_lips'] += 1
                continue
            d['frames'] = [{k: f[k] for k in ('t_ms','bs','lips') if k in f} for f in d['frames']]
            d.pop('video', None)
            d['audio_wav'] = None
            z.writestr('input/bs/'+clip+'.json', json.dumps(d, separators=(',',':')))
            kept.append(spans[clip])
        z.writestr('input/spans.jsonl', '\n'.join(kept)+'\n')
        split = {'train': prep['meta']['train_spk'], 'val': prep['meta']['val_spk'], 'eval': []}
        z.writestr('input/split.json', json.dumps(split))
        report['kept'] = len(kept)
    hashes = {}
    with zipfile.ZipFile(OUT/'code.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        files = [(p, 'tools/'+p.name) for p in (ROOT/'tools').glob('*.py') if p.name not in ('v1_train.py','roi_train.py')]
        files += [(REPO/'scripts/lipread_v1/v1_train.py', 'tools/v1_train.py'),
                  (REPO/'scripts/lipread_roi/roi_train.py', 'tools/roi_train.py')]
        files += [(REPO/'scripts'/name, 'tools/'+name) for name in ('nextreg_bs_lips.py','nextreg_roi.py')]
        for p, dst in files:
            z.write(p, dst)
            hashes[dst] = hashlib.sha256(p.read_bytes()).hexdigest()
    report['input_zip_sha256'] = hashlib.sha256((OUT/'bs-input.zip').read_bytes()).hexdigest()
    report['code_hashes'] = hashes
    (OUT/'bundle-manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('BUNDLE', report['kept'], 'low_lips', report['low_lips'], 'zip_bytes', (OUT/'bs-input.zip').stat().st_size)


if __name__ == '__main__':
    main()
