"""C1·C2 기계 대리 분석(2026-10-27). 입력은 c12_score.py 출력. 모두 기계 지표이며 사람 판독이 아니다.
  judge   --score S --cand COND --base COND   확인 판정(Δ ≥ +5.0점, 낱말 짝 부트스트랩 10,000회 시드 0 하한 > 0)
  c1      --score S [--score S2] --cond COND  자모 혼동 짝 집계(오답에서 정답→읽은 낱말의 자모 치환)와 입모양 규칙 대조
  c2      --score S [--score S2] --conds a,b,c  낱말 난이도(기계 마진)의 조건 간 안정성과 규칙 지수·음절 수와의 상관
"""
import argparse
import json
import sys
from collections import Counter

import numpy as np

N_BOOT = 10000
CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']


def jamo(word):
    out = []
    for ch in word:
        o = ord(ch) - 0xAC00
        if 0 <= o < 11172:
            out += [('초', CHO[o // 588]), ('중', JUNG[(o % 588) // 28])]
            if JONG[o % 28]:
                out.append(('종', JONG[o % 28]))
    return out


def boot(x, seed=0):
    x = np.asarray(x, float)
    idx = np.random.default_rng(seed).integers(0, len(x), (N_BOOT, len(x)))
    m = x[idx].mean(1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() < 5:
        return None
    ra, rb = a[ok].argsort().argsort(), b[ok].argsort().argsort()
    return float(np.corrcoef(ra, rb)[0, 1])


def load(p):
    return json.load(open(p, encoding='utf-8'))


def margin(sc, tgt):
    """정답 보기의 (점수 − 오답 최대 점수). 클수록 기계가 쉽게 읽는 낱말."""
    if sc is None:
        return float('nan')
    s = np.asarray(sc, float)
    return float(s[tgt] - np.delete(s, tgt).max())


def align(a, b):
    """자모 열 a→b 편집 정렬. 치환·삭제·삽입을 (x, y) 목록으로 돌려준다(∅는 없음)."""
    n, m = len(a), len(b)
    D = np.zeros((n + 1, m + 1), int)
    D[:, 0] = np.arange(n + 1)
    D[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = min(D[i - 1, j] + 1, D[i, j - 1] + 1, D[i - 1, j - 1] + (a[i - 1][1] != b[j - 1][1]))
    i, j, ops = n, m, []
    while i or j:
        if i and j and D[i, j] == D[i - 1, j - 1] + (a[i - 1][1] != b[j - 1][1]):
            if a[i - 1][1] != b[j - 1][1]:
                ops.append((a[i - 1][1], b[j - 1][1]))
            i -= 1
            j -= 1
        elif i and D[i, j] == D[i - 1, j] + 1:
            ops.append((a[i - 1][1], '∅'))
            i -= 1
        else:
            ops.append(('∅', b[j - 1][1]))
            j -= 1
    return ops


def cmd_judge(a):
    s = load(a.score)
    if s.get('split') != 'confirm':
        sys.exit('확인 점수가 아님')
    x, b = np.asarray(s['conds'][a.cand]['hit'], float), np.asarray(s['conds'][a.base]['hit'], float)
    d = x - b
    ci = boot(d)
    delta = float(d.mean())
    out = {'cand': a.cand, 'base': a.base, 'acc_cand': float(x.mean()), 'ci_cand': boot(x), 'acc_base': float(b.mean()), 'ci_base': boot(b),
           'delta': delta, 'delta_ci': ci, 'n_items': len(d), 'n_up': int((d > 0).sum()), 'n_down': int((d < 0).sum()),
           'miss_cand': s['conds'][a.cand]['miss'], 'miss_base': s['conds'][a.base]['miss'],
           'pass': bool(delta >= 0.05 and ci[0] > 0)}
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))


def cmd_c1(a):
    sys.path.insert(0, a.backend)
    from engine import VISEME_MAP
    items = load(a.items)['items']
    cnt, tot, nerr, rel = Counter(), 0, 0, Counter()
    for p in a.score:
        s = load(p)
        c = s['conds'][a.cond]
        its = [it for it in items if it['split'] == s['split']]
        for it, pk, h in zip(its, c['pick'], c['hit']):
            tot += 1
            if h or pk < 0:
                continue
            nerr += 1
            for x, y in align(jamo(it['w']), jamo(it['cands'][pk])):
                cnt[tuple(sorted((x, y)))] += 1
                if x == '∅' or y == '∅':
                    rel['삽입·삭제'] += 1
                else:
                    vx, vy = VISEME_MAP.get(x), VISEME_MAP.get(y)
                    rel['같은 입모양' if vx is not None and vx == vy else '다른 입모양'] += 1
    out = {'cond': a.cond, 'n_items': tot, 'n_errors': nerr, 'n_pairs_distinct': len(cnt), 'viseme_relation_counts': dict(rel),
           'top_pairs': [[list(k), v] for k, v in cnt.most_common(30)], 'repeat_pairs_ge2': sum(1 for v in cnt.values() if v >= 2)}
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ('n_items', 'n_errors', 'n_pairs_distinct', 'viseme_relation_counts', 'repeat_pairs_ge2')}, ensure_ascii=False))


def cmd_c2(a):
    sys.path.insert(0, a.backend)
    import perceptual
    items = load(a.items)['items']
    words, rows = [], {}
    for p in a.score:
        s = load(p)
        its = [it for it in items if it['split'] == s['split']]
        for c in a.conds.split(','):
            if c in s['conds']:
                rows.setdefault(c, []).extend(margin(sc, it['tgt']) for it, sc in zip(its, s['conds'][c]['scores']))
        words += [it['w'] for it in its]
    conds = list(rows)
    rule = [(perceptual.word_difficulty(w) or {}).get('difficulty', float('nan')) for w in words]
    syl = [sum(1 for ch in w if '가' <= ch <= '힣') for w in words]
    stab = {f'{p}|{q}': spearman(rows[p], rows[q]) for i, p in enumerate(conds) for q in conds[i + 1:]}
    # 규칙 지수는 클수록 어렵고 마진은 클수록 쉽다 → 부호를 맞춰 −마진과 비교
    out = {'n_words': len(words), 'conds': conds, 'stability_spearman_between_conditions': stab,
           'spearman_machine_difficulty_vs_rule_index': {c: spearman([-v for v in rows[c]], rule) for c in conds},
           'spearman_machine_difficulty_vs_syllables': {c: spearman([-v for v in rows[c]], syl) for c in conds},
           'rule_index_vs_syllables': spearman(rule, syl),
           'per_word': [{'w': w, **{c: rows[c][i] for c in conds}, 'rule': rule[i]} for i, w in enumerate(words)]}
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in out if k != 'per_word'}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('judge')
    p.add_argument('--score', required=True)
    p.add_argument('--cand', required=True)
    p.add_argument('--base', required=True)
    p.add_argument('--out', required=True)
    for n in ('c1', 'c2'):
        p = sub.add_parser(n)
        p.add_argument('--score', action='append', required=True)
        p.add_argument('--items', required=True)
        p.add_argument('--backend', required=True)
        p.add_argument('--out', required=True)
        p.add_argument('--cond' if n == 'c1' else '--conds', required=True)
    a = ap.parse_args()
    {'judge': cmd_judge, 'c1': cmd_c1, 'c2': cmd_c2}[a.cmd](a)


if __name__ == '__main__':
    main()
