import json, collections, re
d = [r for r in json.load(open(__import__('sys').argv[1] if len(__import__('sys').argv) > 1 else 'out/formant.json')) if 'error' not in r]
print('rows', len(d), collections.Counter(r['group'] for r in d))
def summ(rows, label):
    if not rows: return
    spec = sum(r['own_ok'] for r in rows) / len(rows)
    oth = [v for r in rows for v in r['others_ok'].values()]
    sens = 1 - sum(oth) / max(1, len(oth))
    print(f'{label:28s} n={len(rows):4d} 자기모음 ok {spec:.3f} | 다른모음 교정 {sens:.3f}')
for g in ('538', '608'):
    rs = [r for r in d if r['group'] == g]
    summ(rs, f'[{g}] all')
    summ([r for r in rs if (r.get('dgop') or 0) >= 0.5], f'[{g}] dgop>=0.5')
    for v in ["ㅣ", "ㅔ", "ㅐ", "ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ"]:
        summ([r for r in rs if r['vowel'] == v], f'   {v}')
    c = collections.Counter((r['own_height'], r['own_front']) for r in rs)
    print('   own verdicts', c.most_common(6))
# 가까운 모음 짝 교정률(다른 모음을 목표로 했을 때 'ok'가 아닌 비율)
for g in ('538', '608'):
    rs = [r for r in d if r['group'] == g]
    m = collections.defaultdict(list)
    for r in rs:
        for w, ok in r['others_ok'].items(): m[(r['vowel'], w)].append(ok)
    worst = sorted(((sum(v)/len(v), k, len(v)) for k, v in m.items() if len(v) >= 20), reverse=True)[:6]
    print(g, '다른 모음인데 ok로 본 비율 상위', [(k, round(p, 2), n) for p, k, n in worst])
