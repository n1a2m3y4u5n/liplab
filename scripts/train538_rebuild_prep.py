"""train538 재생성 준비: E2 격리 검사와 추출·정렬 입력 목록(train538_rebuild.ps1이 부른다).

  python train538_rebuild_prep.py guard  --data DIR [--e2 DIR]        E2 평가 클립·인물이 하나라도 있으면 종료코드 3
  python train538_rebuild_prep.py lists  --data DIR --out DIR --parts N  추출 목록(list_real.<k>.tsv)·정렬 항목(items.jsonl)
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
E2_ROOT = Path(r'D:\work\hq\projects\liplab-lab\data\e2_538')
COHORT = REPO / 'docs/train538-e2-cohort-2026-10-28.json'
PERSON_RE = re.compile(r'_([CE]\d+)_([A-Z])_\d+')


def manifest(data):
    rows = []
    for line in (Path(data) / 'manifest.tsv').read_text(encoding='utf-8').splitlines():
        p = line.split('\t')
        if len(p) >= 3 and not p[0].startswith('#'):
            rows.append((os.path.splitext(p[0])[0], p[1], unicodedata.normalize('NFC', p[2]).strip()))
    return rows


def guard(data, e2=E2_ROOT):
    """train538에 E2 평가 클립 이름·E2 인물·E2 배치가 있으면 그 목록을 돌려준다(비어야 통과)."""
    rows = manifest(data)
    e2_clips, e2_persons, e2_spk = set(), set(), set()
    meta = Path(e2) / 'manifest-meta.json'
    if meta.exists():
        for d in json.loads(meta.read_text(encoding='utf-8')):
            e2_clips.add(d['clip']); e2_persons.add(d['person']); e2_spk.add(d['spk'])
    cohort = json.loads(COHORT.read_text(encoding='utf-8'))
    e2_persons |= set(cohort['e2_persons']); e2_spk |= set(cohort['e2_plan_spk'])
    bad = []
    for clip, spk, _ in rows:
        m = PERSON_RE.search(clip)
        if clip in e2_clips or spk in e2_spk or (m and m[1] in e2_persons):
            bad.append(clip)
    return bad


def lists(data, out, parts, bs_dir):
    """정면(A) 클립만. 이미 추출·정렬한 것은 다시 넣지 않는다."""
    data, out = Path(data), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    todo, items = [], []
    for clip, spk, text in manifest(data):
        m = PERSON_RE.search(clip)
        if not m or m[2] != 'A':
            continue
        mp4 = data / 'clips' / (clip + '.mp4')
        js = Path(bs_dir) / (clip + '.json')
        if not js.exists():
            todo.append(f'{mp4}\t{js}')
        items.append(json.dumps({'key': 'real:' + clip, 'text': text, 'audio': str(mp4.with_suffix('.wav'))}, ensure_ascii=False))
    for k in range(parts):
        (out / f'list_real.{k}.tsv').write_text(''.join(t + '\n' for t in todo[k::parts]), encoding='utf-8')
    (out / 'items.jsonl').write_text(''.join(i + '\n' for i in items), encoding='utf-8')
    print(f'LISTS extract={len(todo)} align_items={len(items)} parts={parts}')
    return todo, items


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('guard'); s.add_argument('--data', required=True); s.add_argument('--e2', default=str(E2_ROOT))
    s = sub.add_parser('lists'); s.add_argument('--data', required=True); s.add_argument('--out', required=True)
    s.add_argument('--bs', required=True); s.add_argument('--parts', type=int, default=4)
    a = ap.parse_args(argv)
    if a.cmd == 'guard':
        bad = guard(a.data, a.e2)
        if bad:
            print('E2_OVERLAP', len(bad), bad[:5]); sys.exit(3)
        print('E2_GUARD_OK', len(manifest(a.data)))
    else:
        lists(a.data, a.out, a.parts, a.bs)


if __name__ == '__main__':
    main()
