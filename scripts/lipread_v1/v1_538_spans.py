#!/usr/bin/env python3
"""
V1-538(2026-10-29): train538 클립의 어절 구간(d/spans.jsonl)을 lab-sub에서 CPU로 만든다.
사전등록: docs/lipread-v1-538-prereg-2026-10-29.md 4절.

build_cd.py(liplab-lab/tools)의 매니페스트·텍스트 정규화·건너뛰기·bs 재색인·spans.jsonl 형식을 그대로 쓰고,
정렬 함수(build_cd.align_clip)만 바꿔 끼운다. 원래 정렬기 kresnik/wav2vec2-large-xlsr-korean이 이 PC에 없고
(받기 금지), train538 V3 재생성이 쓴 로컬 정렬기 dgop_ours(자모 CTC, backend/models/dgop_ours/aligner)를 쓴다.
  - 글자(음절) 구간: 자모 토큰 강제정렬(coart_pod_eval.parse_syllables) → 음절 k의 [초성(없으면 중성) 시작,
    종성(없으면 중성) 끝) 초 → 30fps 프레임 [a, b)(build_cd.emit_to_frames와 같은 내림·올림). 음절 수가 글자 수와
    다르면 status=align_fail.
  - asr_greedy·asr_cer: 같은 방출의 그리디 자모 토큰열과 목표 자모 토큰열('|' 제외)의 편집거리 / 목표 길이.
    build_cd의 글자 CER 대신 자모 CER이다. 잘린 클립을 거르는 기준(> 0.6)은 그대로 둔다.
  - align_lp: 정렬 경로 프레임별 로그확률 평균, align_lp_tok: 그중 blank가 아닌 프레임 평균.
사용(liplab backend .venv, GPU 금지):
  (CUDA_VISIBLE_DEVICES는 스크립트가 '-1'로 둔다. Windows는 빈 값을 지운다)
  python v1_538_spans.py --tools <liplab-lab/tools> --backend <liplab/backend> --threads 4 -- \
      --data <train538> --out <out/d.k> --manifest <manifest.k.tsv> --bs <rebuild/real_bs> --clips <train538/clips>
  ('--' 뒤는 build_cd.py 인자 그대로)
"""
import argparse
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tools', required=True, help='build_cd.py가 있는 폴더(liplab-lab/tools)')
    ap.add_argument('--backend', required=True, help='dgop_acoustic.py가 있는 폴더(liplab/backend)')
    ap.add_argument('--aligner', default=None, help='기본 <backend>/models/dgop_ours/aligner')
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('rest', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    rest = a.rest[1:] if a.rest[:1] == ['--'] else a.rest
    # GPU 금지. Windows는 빈 환경변수를 지우므로 '-1'(GPU 없음)로 둔다. 다른 값이 있어도 덮어쓴다.
    if os.environ.get('CUDA_VISIBLE_DEVICES') not in ('', '-1'):
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    os.environ['DGOP_DEVICE'] = 'cpu'
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    sys.path[:0] = [os.path.abspath(a.tools), os.path.join(os.path.dirname(HERE)), os.path.abspath(a.backend)]
    import numpy as np
    import torch
    if torch.cuda.is_available():
        print('V1_538_SPANS_FAIL torch가 GPU를 본다(GPU 금지)', flush=True)
        return 1
    torch.set_num_threads(a.threads)
    import build_cd as BC
    import coart_pod_eval as C
    import ctc_align
    import dgop_acoustic as D
    aligner = a.aligner or os.path.join(os.path.abspath(a.backend), 'models', 'dgop_ours', 'aligner')

    def lev(x, y):
        prev = list(range(len(y) + 1))
        for i, cx in enumerate(x, 1):
            cur = [i]
            for j, cy in enumerate(y, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
            prev = cur
        return prev[-1]

    def align_clip(backend, wav, text_norm, aligner_kind='auto', use_delim=True, base=None):
        out = {'status': 'ok', 'chars': [], 'align_lp': None, 'align_lp_tok': None,
               'asr_greedy': '', 'asr_cer': None}
        text = unicodedata.normalize('NFC', text_norm).strip()
        chars = [ch for ch in text if not ch.isspace()]
        if not chars:
            out['status'] = 'empty_text'
            return out
        tokens = D.tokens_for_text(text, model_id=aligner)
        lp, vocab = D.ctc_log_probs(wav, BC.SR, model_id=aligner)
        if any(t not in vocab for t in tokens):
            out['status'] = 'oov'
            return out
        blank = D.blank_id_for(vocab)
        tgt = [vocab[t] for t in tokens]
        id2tok = {v: k for k, v in vocab.items()}
        greedy, prev = [], None
        for i in lp.argmax(-1).tolist():
            if i != prev and i != blank:
                greedy.append(id2tok.get(i, '?'))
            prev = i
        ref = [t for t in tokens if t != '|']
        hyp = [t for t in greedy if t not in D.SPECIAL_TOKENS]
        out['asr_greedy'] = ' '.join(hyp)
        out['asr_cer'] = round(lev(ref, hyp) / len(ref), 4) if ref else None
        try:
            labels, scores = ctc_align.forced_align(lp, tgt, blank=blank)
        except ValueError:
            out['status'] = 'align_fail'
            return out
        spans = ctc_align.token_spans(labels, tgt, blank=blank)
        if len(spans) != len(tgt):
            out['status'] = 'align_fail'
            return out
        spf = len(wav) / float(BC.SR) / max(1, int(lp.shape[0]))
        sec = [(s['start'] * spf, (s['end'] + 1) * spf) for s in spans]
        syls = C.parse_syllables(tokens, sec)
        if len(syls) != len(chars):
            out['status'] = 'align_fail'
            return out
        for ch, s in zip(chars, syls):
            t0 = (s['on'] or s['nu'])[0]
            t1 = (s['co'] or s['nu'])[1]
            fa = int(np.floor(t0 * BC.FPS + 1e-6))
            fb = int(np.ceil(t1 * BC.FPS - 1e-6))
            out['chars'].append([ch, fa, max(fb, fa + 1)])
        sc = np.asarray(scores, dtype=np.float64)
        lab = np.asarray(labels)
        out['align_lp'] = round(float(sc.mean()), 4)
        out['align_lp_tok'] = round(float(sc[lab != blank].mean()), 4) if (lab != blank).any() else None
        return out

    BC.align_clip = align_clip
    return BC.main(rest, backend=object())


if __name__ == '__main__':
    sys.exit(main() or 0)
