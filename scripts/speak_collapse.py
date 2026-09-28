import re
def collapse_repeats(text, min_rep=3, max_n=6):
    """연속으로 min_rep번 이상 되풀이된 어절 n-그램(1~max_n어절)을 한 번으로 접는다. 구두점은 어절에서 떼고 비교."""
    toks = text.split()
    key = [re.sub(r"[^\w]", "", t) for t in toks]
    out, i = [], 0
    while i < len(toks):
        done = False
        for n in range(1, max_n + 1):
            if i + n * min_rep > len(toks):
                break
            unit = key[i:i + n]
            if not any(unit):
                continue
            k = 1
            while i + (k + 1) * n <= len(toks) and key[i + k * n:i + (k + 1) * n] == unit:
                k += 1
            if k >= min_rep:
                out += toks[i:i + n]; i += k * n; done = True; break
        if not done:
            out.append(toks[i]); i += 1
    return " ".join(out)
