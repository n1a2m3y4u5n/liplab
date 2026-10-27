"""저장한 E2 자료의 신원·형식·길이를 검사한다. 탐색/확인은 실행하지 않는다."""
import collections
import hashlib
import json
import re
import zlib
from pathlib import Path

import cv2
import soundfile as sf

from e2_retry_acquire import ROOT, REPO, EXHASH


def audit():
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    excluded = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    ex = set(excluded.read_text().splitlines())
    plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
    persons = {r['spk']: r['person'] for r in plan}
    rows = [line.split('\t', 2) for line in (ROOT / 'manifest.tsv').read_text(encoding='utf-8').splitlines()]
    counts = collections.Counter(row[1] for row in rows)
    metadata = {r['clip']: r for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
    errors, files = [], []
    for clip, spk, text in rows:
        match = re.search(r'_([CE]\d+)_([A-Z])_\d+', clip)
        if spk in ex or not match or match[1] in ex or match[2] != 'A' or match[1] != persons[spk]:
            errors.append(clip + ': identity/view')
        mp4 = ROOT / 'clips' / clip
        wav = mp4.with_suffix('.wav')
        info = sf.info(wav)
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        ok, _ = cap.read()
        cap.release()
        if info.samplerate != 16000 or info.channels != 1:
            errors.append(clip + ': audio format')
        expected = metadata[Path(clip).stem]['duration']
        if abs(info.duration - expected) > .2:
            errors.append(clip + ': expected duration')
        if not ok or abs(fps - 30) > .01 or width != 640 or frames < 1 or abs(frames / max(fps, 1) - info.duration) > .2:
            errors.append(clip + ': video/duration')
        for path in (mp4, wav):
            files.append({'file': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    halves = [sum(zlib.crc32(s.encode()) % 2 == h for s in counts) for h in (0, 1)]
    if len(counts) > 40 or any(n != 12 for n in counts.values()):
        errors.append('cohort counts')
    if len({row[0] for row in rows}) != len(rows):
        errors.append('duplicate clips')
    if sha(excluded) != EXHASH:
        errors.append('excluded hash')
    transfers = [json.loads(line) for line in (ROOT / 'transfers.jsonl').read_text().splitlines()]
    probes = json.loads((REPO / 'out/aihub538-retry-result.json').read_text())
    probes = [probes] if isinstance(probes, dict) else probes
    result = {
        'speakers': len(counts), 'persons': len({persons[s] for s in counts}),
        'halves': halves, 'clips': len(rows), 'clips_per_speaker': dict(sorted(counts.items())),
        'saved_media_bytes': sum(f['bytes'] for f in files),
        'consumed_download_bytes': sum(t['bytes'] for t in transfers) + sum(p['responseBytes'] for p in probes),
        'download_seconds': sum(t['seconds'] for t in transfers) + sum(float(p['stats'].split('|')[2]) for p in probes),
        'manifest_sha256': sha(ROOT / 'manifest.tsv'), 'plan_sha256': sha(ROOT / 'plan.json'),
        'excluded_sha256': sha(excluded), 'files': files, 'errors': errors,
        'minimum_cohort_met': min(halves) >= 15, 'target_cohort_met': halves == [20, 20],
        'selection_executed': False, 'confirmation_executed': False,
    }
    (ROOT / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('files', 'clips_per_speaker')}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(audit())
