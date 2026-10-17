"""S4 청크 주의 학생 평가(docs/scorer-stream-chunk-2026-10.md 4~6절), 데스크탑 쪽. 원 등록 평가 코드(scripts/s4_eval_pod.py)를 그대로 쓰고
음향 출력만 스트리밍 창 나누기(4절·9절: C 4초, 왼쪽 2초, 오른쪽 1초)로 바꾼 백엔드 'stream:ONNX'를 더한다.

    set S4_W=D:/liplab/s4
    python s4c_eval.py prep
    python s4c_eval.py e1|dev BACKEND WORKERS OUT.jsonl     BACKEND = teacher | onnx:경로 | stream:경로
    python s4c_eval.py e2 BACKEND WORKERS OUT.json
    python s4c_eval.py selftest                             창 나누기 점검(창이 전체를 덮으면 전체 순전파와 같음, 프레임 수)

창 경계는 10/15 `scripts/phone_tail/pod/stream_lat.py`의 windows()와 같은 식(프레임 단위)이다.
"""
import os
import sys

import numpy as np

W = os.environ.setdefault("S4_W", "D:/liplab/s4")
sys.path.insert(0, os.path.join(W, "scripts"))
import s4_distill_pod as S  # noqa: E402
import s4_eval_pod as E  # noqa: E402

SR, HOP = 16000, 320
C_S, LC_S, RC_S = 4.0, 2.0, 1.0
CF, LF, RF = int(C_S * SR / HOP), int(LC_S * SR / HOP), int(RC_S * SR / HOP)


def windows(n_samples):
    """stream_lat.windows와 같다: 청크 k는 전역 프레임 [b, e)를 남기고 표본 [s0, s1)을 넣는다. 마지막 청크는 오른쪽 문맥이 없다."""
    G = S.conv_len(n_samples)
    out, b = [], 0
    while b < G:
        e = min(b + CF, G)
        f0 = max(0, b - LF)
        s0 = f0 * HOP
        s1 = n_samples if e >= G else min(n_samples, (e + RF - 1) * HOP + 400)
        out.append((b, e, f0, s0, s1))
        b = e
    return G, out


def stitch(run, y):
    G, ws = windows(len(y))
    al, sc = [], []
    for b, e, f0, s0, s1 in ws:
        a, s = run(y[s0:s1])
        assert a.shape[0] >= e - f0, (a.shape, b, e, f0)
        al.append(a[b - f0:e - f0])
        sc.append(s[b - f0:e - f0])
    al, sc = np.concatenate(al), np.concatenate(sc)
    assert al.shape[0] == G, (al.shape, G)
    return al, sc


class StreamOnnx(E.Onnx):
    def run(self, wave):
        import time
        t0 = time.perf_counter()
        y = np.ascontiguousarray(wave, dtype=np.float32)
        a, s = stitch(lambda w: tuple(x[0] for x in self.sess.run(None, {"wav": np.ascontiguousarray(w)[None]})), y)
        self.fwd.append(time.perf_counter() - t0)
        return {"al": self.torch.from_numpy(a).float(), "sc": self.torch.from_numpy(s).float()}


_orig_make = E.make_backend


def make_backend(spec, threads=2):
    if spec.startswith("stream:"):
        return StreamOnnx(spec[7:], threads)
    return _orig_make(spec, threads)


E.make_backend = make_backend          # 작업자 프로세스(spawn)도 이 모듈을 다시 읽으므로 같은 바꿔치기가 걸린다


def cmd_selftest():
    for n in (int(2.0 * SR), int(5.0 * SR), int(5.02 * SR), int(13.3 * SR), 30 * SR):
        G, ws = windows(n)
        assert ws[0][0] == 0 and ws[-1][1] == G
        assert all(ws[i][1] == ws[i + 1][0] for i in range(len(ws) - 1))
        for b, e, f0, s0, s1 in ws:
            assert S.conv_len(s1 - s0) >= e - f0, (n, b, e, f0, s0, s1)
            assert b - f0 <= LF and s0 % HOP == 0
    # 창 하나면 전체와 같다(짧은 녹음)
    G, ws = windows(int(4.5 * SR))
    assert len(ws) == 1 and ws[0][3] == 0 and ws[0][4] == int(4.5 * SR)
    # 가짜 모델(프레임별 전역 위치를 내는 함수)로 이어 붙인 결과가 전역 순서와 같은지
    def fake(w):
        nf = S.conv_len(len(w))
        x = np.zeros((nf, 49), dtype=np.float32)
        x[:, 0] = np.arange(nf)
        return x, x
    y = np.zeros(int(17.7 * SR), dtype=np.float32)
    a, _ = stitch(fake, y)
    assert a.shape[0] == S.conv_len(len(y))
    print("S4C_EVAL_SELFTEST_OK", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "selftest":
        cmd_selftest()
    elif cmd == "prep":
        E.cmd_prep()
    elif cmd in ("e1", "dev"):
        spec, workers, out = sys.argv[2], int(sys.argv[3]), sys.argv[4]
        E.run_pairs(f"{E.EV}/{cmd}_jobs.json", spec, workers, out, int(os.environ.get("EVAL_THREADS", "2")))
    elif cmd == "e2":
        spec, workers, out = sys.argv[2], int(sys.argv[3]), sys.argv[4]
        sys.path.insert(0, f"{W}/scripts")
        E.run_e2(spec, workers, out, int(os.environ.get("EVAL_THREADS", "2")))
    else:
        sys.exit(f"알 수 없는 명령 {cmd}")
