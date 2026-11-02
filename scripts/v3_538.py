"""V3 train538 재적합(docs/avatar-v3-538-prereg-2026-11-02.md). 탐색 절반(crc32 절반 0)만 다루는 도구. 확인 절반(절반 1)은 읽지 않는다.

  explore-sel  sel.json → 탐색 절반 화자만 남기고 half를 안쪽 겹(fold, sha256("v3-538-fold:" + spk) 첫 바이트 % 2, crc32는 최하위 비트가 선형이라 절반과 묶여 못 쓴다)으로 바꾼 sel_explore.json
  fold-tables  v3_data.pkl의 탐색 절반 구간으로 겹마다 후보 표를 만들어 tables.json에 더한다. 표 이름 <후보>f<판정 겹>은 판정 겹의 반대쪽 겹으로 만든 표다.
  freeze       탐색 절반 전부(v3_table_explore.json과 같은 칸)에 고른 이득·양순 규칙을 얹어 동결 표를 만든다.
"""
import argparse
import hashlib
import json
import pickle

import v3_avatar as A


def fold_of(spk):
    return hashlib.sha256(('v3-538-fold:' + spk).encode()).digest()[0] % 2


def parse_gain(s):
    return {g: float(x) for g, x in zip(A.GAIN_GROUPS, s.split(','))}


def cmd_explore_sel(a):
    sel = json.load(open(a.sel, encoding='utf-8'))
    speakers = [dict(s, half=fold_of(s['spk'])) for s in sel['speakers'] if s['half'] == 0]
    keep = {s['spk'] for s in speakers}
    clips = [dict(c, half=fold_of(c['spk'])) for c in sel['clips'] if c['spk'] in keep]
    sent = {}
    for r in clips:
        e = sent.setdefault((r['sid'], r['half']), {'sid': r['sid'], 'half': r['half'], 'text': r['text'], 'default': False})
        if r['rank'] < sel['params']['n_default']:
            e['default'] = True
    out = {'created': sel['created'], 'per_spk': sel['per_spk'], 'speakers': speakers, 'clips': clips,
           'sentences': sorted(sent.values(), key=lambda e: (e['half'], e['sid'])), 'params': sel['params']}
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    for h in (0, 1):
        print(f"FOLD {h} speakers={sum(s['half'] == h for s in speakers)} clips={sum(c['half'] == h for c in clips)} "
              f"default_sentences={sum(e['half'] == h and e['default'] for e in out['sentences'])}")


def explore_rows(data_path):
    """탐색 절반 구간만. 두 번째 칸(절반)을 안쪽 겹으로 바꾼다."""
    rows = pickle.load(open(data_path, 'rb'))['rows']
    return [(r[0], fold_of(r[0])) + tuple(r[2:]) for r in rows if r[1] == 0]


def cmd_fold_tables(a):
    rows = explore_rows(a.data)
    out = json.load(open(a.out, encoding='utf-8')) if a.merge else {}
    for spec in a.cand:   # 이름=벌림,돌출,폭,닫힘[,양순]
        name, vals = spec.split('=')
        p = vals.split(',')
        for k in (0, 1):
            m = A.fit_table(rows, (1 - k,), 'add', parse_gain(','.join(p[:4])))
            if len(p) > 4 and float(p[4]):
                m['seal'] = float(p[4])
            m['sha256'] = A.table_sha(m)
            out[f'{name}f{k}'] = m
            print(f"TABLE {name}f{k} cells={len(m['cells'])} gain={m['gain']} seal={m.get('seal')}")
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


def cmd_freeze(a):
    base = json.load(open(a.base, encoding='utf-8'))
    m = dict(base, gain=parse_gain(a.gain))
    if a.seal:
        m['seal'] = a.seal
    m.pop('sha256', None)
    m['sha256'] = A.table_sha(m)
    json.dump(m, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f"FREEZE cells={len(m['cells'])} gain={m['gain']} seal={m.get('seal')} base_sha={base['sha256']} sha256={m['sha256']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('explore-sel')
    s.add_argument('--sel', required=True)
    s.add_argument('--out', required=True)
    s = sub.add_parser('fold-tables')
    s.add_argument('--data', required=True)
    s.add_argument('--cand', nargs='+', required=True)
    s.add_argument('--merge', action='store_true')
    s.add_argument('--out', required=True)
    s = sub.add_parser('freeze')
    s.add_argument('--base', required=True)
    s.add_argument('--gain', required=True)
    s.add_argument('--seal', type=float, default=0.0)
    s.add_argument('--out', required=True)
    a = ap.parse_args()
    {'explore-sel': cmd_explore_sel, 'fold-tables': cmd_fold_tables, 'freeze': cmd_freeze}[a.cmd](a)


if __name__ == '__main__':
    main()
