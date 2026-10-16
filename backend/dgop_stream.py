"""
S4 스트리밍(덩어리) 채점 경로. 녹음하는 동안 소리를 창으로 나눠 미리 순전파하고, 녹음이 끝나면 마지막 창 하나만 넣은 뒤
이어 붙인 로그확률로 기존 강제정렬·채점(dgop_acoustic.assess_outputs)을 한다(docs/scorer-stream-latency-2026-10.md 2절·9절).

- 플래그: DGOP_STREAM=1일 때만 켠다(기본 끔). 끄면 /api/speak/stream/* 는 404이고 /api/speak/assess는 예전과 같다.
- 모델: DGOP_STREAM_MODEL. `.onnx` 경로면 S4 학생(입력 `wav` [1, 표본], 출력 정렬 로짓·채점 로짓 [1, 프레임, 49]),
  `teacher`면 지금 정렬기·채점기(DGOP_ALIGNER_ID·DGOP_SCORER_ID)를 창마다 돌린다(비교용). 비어 있으면 스트리밍을 쓰지 않는다.
- 창: 새 소리 DGOP_STREAM_CHUNK_S(기본 4.0초), 왼쪽 문맥 DGOP_STREAM_LEFT_S(2.0초), 오른쪽 문맥 DGOP_STREAM_RIGHT_S(1.0초).
  창마다 가운데 '새 소리' 프레임만 남긴다. 창 나누기는 scripts/phone_tail/pod/stream_lat.py(10/15 등록 측정)와 같다.

프레임 계산: wav2vec2·HuBERT 합성곱 특징 추출부(커널·보폭 (10,5)(3,2)×4(2,2)×2)는 보폭 320표본, 수용 영역 400표본이다.
창 시작을 320표본 배수에 두면 창 안 프레임 j가 전역 프레임 (시작/320 + j)와 정확히 맞는다(각 층 보폭이 시작 이동을 나눈다).
그래서 합성곱만 있는 모델이면 창을 어떻게 나눠도 전체 순전파와 같은 값이 나오고(test_dgop_stream이 확인), 트랜스포머처럼
문장 전체를 보는 모델이면 창 경계에서 값이 바뀐다(10/15 6.3절). 청크 주의로 증류한 학생은 그 차이를 줄이도록 학습한다.
"""
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

SR = 16000
HOP = 320
RECEPTIVE = 400
CONV_LAYERS = ((10, 5), (3, 2), (3, 2), (3, 2), (3, 2), (2, 2), (2, 2))
MAX_SECONDS = 30          # dgop_acoustic.assess_text와 같은 앞 30초 상한


def enabled() -> bool:
    return os.getenv("DGOP_STREAM", "0") == "1"


def conv_frames(n_samples: int) -> int:
    """합성곱 특징 추출부의 출력 프레임 수(transformers `_get_feat_extract_output_lengths`와 같은 식)."""
    n = int(n_samples)
    for k, s in CONV_LAYERS:
        if n < k:
            return 0
        n = (n - k) // s + 1
    return n


@dataclass(frozen=True)
class StreamConfig:
    chunk_s: float = 4.0
    left_s: float = 2.0
    right_s: float = 1.0

    def __post_init__(self):
        if self.chunk_frames <= 0 or self.left_s < 0 or self.right_s < 0:
            raise ValueError(f"창 설정이 잘못됐습니다: {self}")

    @classmethod
    def from_env(cls) -> "StreamConfig":
        g = lambda k, d: float(os.getenv(k) or d)
        return cls(g("DGOP_STREAM_CHUNK_S", 4.0), g("DGOP_STREAM_LEFT_S", 2.0), g("DGOP_STREAM_RIGHT_S", 1.0))

    # 프레임 단위(20 ms)로 반올림한다. 등록 측정(4/2/1초)은 200/100/50프레임으로 정확히 떨어진다.
    @property
    def chunk_frames(self) -> int:
        return int(round(self.chunk_s * SR / HOP))

    @property
    def left_frames(self) -> int:
        return int(round(self.left_s * SR / HOP))

    @property
    def right_frames(self) -> int:
        return int(round(self.right_s * SR / HOP))

    def window_end(self, e: int) -> int:
        """새 소리 프레임 [b, e)를 남길 창의 끝 표본: 오른쪽 문맥 프레임 RF개까지 수용 영역이 다 들어오는 곳."""
        return (e + self.right_frames - 1) * HOP + RECEPTIVE if self.right_frames else (e - 1) * HOP + RECEPTIVE


Forward = Callable[[np.ndarray], Sequence[np.ndarray]]


class StreamStitcher:
    """
    소리를 조금씩 받아(feed) 창이 찰 때마다 forward를 돌리고, 끝(finish)에서 마지막 창을 넣어 이어 붙인 출력을 돌려준다.
    forward(파형 float32 1차원) → 출력 배열 목록(각 [프레임, C]). 학생은 (정렬 로짓, 채점 로짓) 두 개다.
    """

    def __init__(self, forward: Forward, cfg: Optional[StreamConfig] = None, max_seconds: float = MAX_SECONDS):
        self.forward = forward
        self.cfg = cfg or StreamConfig()
        self._cap = int(max_seconds * SR)
        self._buf = np.zeros(self._cap, dtype=np.float32)
        self.n = 0                       # 받은 표본 수(상한까지)
        self.dropped = 0                 # 상한을 넘어 버린 표본 수
        self._chunks: List[tuple] = []   # (b, e, s1, [출력 조각...]) — 남긴 전역 프레임 [b, e), 창 끝 표본 s1
        self.window_secs: List[float] = []   # 녹음 중 창마다 순전파 시간(L3 확인용)
        self.final_secs: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def committed_frames(self) -> int:
        return self._chunks[-1][1] if self._chunks else 0

    @property
    def waveform(self) -> np.ndarray:
        return self._buf[:self.n]

    def _run(self, s0: int, s1: int, b: int, e: int):
        """표본 [s0, s1) 창을 넣어 전역 프레임 [b, e)를 잘라 낸다. s0은 320 배수."""
        f0 = s0 // HOP
        outs = self.forward(np.ascontiguousarray(self._buf[s0:s1]))
        pieces = []
        for o in outs:
            o = np.asarray(o)
            if o.shape[0] < e - f0:
                raise ValueError(f"창 출력 프레임이 모자랍니다({o.shape[0]} < {e - f0}, 창 [{s0}, {s1}))")
            pieces.append(o[b - f0:e - f0])
        return pieces

    def feed(self, samples) -> int:
        """새 표본을 붙이고, 창 끝까지 소리가 온 덩어리를 순전파한다. 이번에 돌린 창 수를 돌려준다."""
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        with self._lock:
            room = self._cap - self.n
            take = min(room, len(x))
            self._buf[self.n:self.n + take] = x[:take]
            self.n += take
            self.dropped += len(x) - take
            ran = 0
            cf, lf = self.cfg.chunk_frames, self.cfg.left_frames
            while True:
                b = self.committed_frames
                e = b + cf
                s1 = self.cfg.window_end(e)
                if s1 > self.n:
                    break
                t0 = time.perf_counter()
                pieces = self._run(max(0, b - lf) * HOP, s1, b, e)
                self.window_secs.append(time.perf_counter() - t0)
                self._chunks.append((b, e, s1, pieces))
                ran += 1
            return ran

    def finish(self, n_valid: Optional[int] = None) -> List[np.ndarray]:
        """
        녹음 끝: 앞 n_valid 표본(끝 무음을 자른 길이, 생략하면 받은 전부)만 쓴다. 창 끝이 n_valid를 넘은 덩어리는 버리고
        (자른 무음을 문맥으로 본 덩어리, 등록 측정과 같은 규칙) 남은 부분을 왼쪽 문맥과 함께 한 번 넣는다.
        돌려주는 출력의 프레임 수는 conv_frames(n_valid)로, 같은 소리를 한 번에 넣은 것과 같다.
        """
        with self._lock:
            n = self.n if n_valid is None else max(0, min(int(n_valid), self.n))
            G = conv_frames(n)
            if G <= 0:
                raise ValueError("소리가 너무 짧아 프레임이 없습니다")
            keep = []
            b = 0
            for (cb, ce, s1, pieces) in self._chunks:
                if cb != b or s1 > n or ce > G:
                    break
                keep.append(pieces)
                b = ce
            t0 = time.perf_counter()
            if b < G:
                keep.append(self._run(max(0, b - self.cfg.left_frames) * HOP, n, b, G))
            self.final_secs = time.perf_counter() - t0
            n_out = len(keep[0])
            return [np.concatenate([k[i] for k in keep], axis=0) for i in range(n_out)]

    def summary(self) -> Dict:
        return {"chunk_s": self.cfg.chunk_s, "left_s": self.cfg.left_s, "right_s": self.cfg.right_s,
                "samples": self.n, "dropped": self.dropped, "windows_during": len(self.window_secs),
                "window_max_s": round(max(self.window_secs), 4) if self.window_secs else None,
                "final_window_s": round(self.final_secs, 4) if self.final_secs is not None else None}


def stream_outputs(waveform, forward: Forward, cfg: Optional[StreamConfig] = None, n_valid: Optional[int] = None,
                   feed_samples: Optional[int] = None) -> List[np.ndarray]:
    """파형 전체를 녹음처럼 feed_samples씩(기본 0.1초) 흘려 넣고 finish한 결과. 판정·시험용(앱 경로와 같은 코드)."""
    st = StreamStitcher(forward, cfg)
    y = np.asarray(waveform, dtype=np.float32).reshape(-1)
    step = int(feed_samples or SR // 10)
    for i in range(0, len(y), step):
        st.feed(y[i:i + step])
    return st.finish(n_valid)


# ───────────── 모델 ─────────────

class OnnxStudent:
    """S4 학생 ONNX(scripts/s4_distill_pod.py 내보내기: 입력 `wav`, 출력 `al`·`sc`). onnxruntime은 이 경로에서만 필요하다."""

    def __init__(self, path: str, threads: Optional[int] = None):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads or os.getenv("DGOP_STREAM_THREADS") or 2)
        so.inter_op_num_threads = 1
        self.path = path
        self.sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        names = [o.name for o in self.sess.get_outputs()]
        want = [s.strip() for s in (os.getenv("DGOP_STREAM_OUTPUTS") or "al,sc").split(",")]
        self.output_names = want if all(w in names for w in want) else names[:2]
        if len(self.output_names) != 2:
            raise ValueError(f"학생 ONNX 출력이 둘이 아닙니다: {names}")

    def __call__(self, wave: np.ndarray):
        out = self.sess.run(self.output_names, {self.input_name: np.ascontiguousarray(wave, dtype=np.float32)[None]})
        return [o[0] for o in out]


def teacher_forward(aligner_id: str, scorer_id: Optional[str] = None) -> Forward:
    """지금 정렬기·채점기를 창마다 돌리는 forward(비교용). 정규화는 창마다(processor) 한다."""
    import dgop_acoustic as DA
    scorer_id = scorer_id or aligner_id

    def fwd(wave):
        _lp, al, _v = DA.ctc_outputs(wave, SR, aligner_id)
        if scorer_id == aligner_id:
            return [al.numpy(), al.numpy()]
        _lp2, sc, _v2 = DA.ctc_outputs(wave, SR, scorer_id)
        return [al.numpy(), sc.numpy()]
    return fwd


_MODEL_LOCK = threading.Lock()
_MODEL: Dict[str, object] = {}


def model_spec() -> str:
    return (os.getenv("DGOP_STREAM_MODEL") or "").strip()


def load_backend():
    """(forward, vocab, calibration_path) — DGOP_STREAM_MODEL에 따라 한 번만 올린다. 모델이 없으면 RuntimeError."""
    spec = model_spec()
    if not spec:
        raise RuntimeError("DGOP_STREAM_MODEL이 비어 있습니다")
    with _MODEL_LOCK:
        if spec in _MODEL:
            return _MODEL[spec]
        import dgop_acoustic as DA
        if spec == "teacher":
            aligner = os.getenv("DGOP_ALIGNER_ID") or os.getenv("DGOP_MODEL_ID")
            if not aligner:
                raise RuntimeError("DGOP_STREAM_MODEL=teacher인데 DGOP_ALIGNER_ID가 없습니다")
            scorer = os.getenv("DGOP_SCORER_ID") or aligner
            processor, _ = DA._load(aligner)
            vocab = processor.tokenizer.get_vocab()
            backend = (teacher_forward(aligner, scorer), vocab, os.getenv("DGOP_STREAM_CALIBRATION") or DA.calibration_path_for(scorer))
        else:
            if not os.path.exists(spec):
                raise RuntimeError(f"학생 ONNX가 없습니다: {spec}")
            import jamo_vocab
            vocab = dict(jamo_vocab.VOCAB)      # 학생 출력 49차원은 교사 자모 어휘 순서와 같다(S4 2.2절)
            cal = os.getenv("DGOP_STREAM_CALIBRATION") or os.path.join(os.path.dirname(os.path.abspath(spec)), "calibration.json")
            if not os.path.exists(cal):
                print(f"[WARN] 학생 표시 보정 파일이 없습니다({cal}) — 교사 기본 앵커를 씁니다(표시 점수 눈금이 다를 수 있음)")
                cal = DA.DEFAULT_CALIBRATION_PATH
            backend = (OnnxStudent(spec), vocab, cal)
        _MODEL[spec] = backend
        return backend


# ───────────── 녹음 세션 ─────────────

class StreamSession:
    def __init__(self, user_id, forward: Forward, vocab: Dict[str, int], calibration_path: Optional[str],
                 cfg: Optional[StreamConfig] = None):
        self.id = uuid.uuid4().hex
        self.user_id = user_id
        self.vocab = vocab
        self.calibration_path = calibration_path
        self.stitcher = StreamStitcher(forward, cfg or StreamConfig.from_env())
        self.created = self.touched = time.monotonic()

    def feed_pcm16(self, body: bytes) -> int:
        """16 kHz 단일 채널 16비트 PCM(리틀 엔디언) 조각을 받는다."""
        self.touched = time.monotonic()
        x = np.frombuffer(body[:len(body) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        return self.stitcher.feed(x)

    def assess(self, target_text: str, calibrate: bool = True) -> Dict:
        """녹음 끝: 끝 무음을 자르고 마지막 창을 넣은 뒤, 이어 붙인 로짓으로 강제정렬·채점한다(assess_text와 같은 후처리)."""
        import torch
        import dgop_acoustic as DA
        full = self.stitcher.waveform.copy()
        trimmed = DA.trim_trailing_silence(full, SR)
        al, sc = self.stitcher.finish(len(trimmed))
        al_t, sc_t = torch.from_numpy(np.asarray(al, dtype=np.float32)), torch.from_numpy(np.asarray(sc, dtype=np.float32))
        result = DA.assess_outputs(full, trimmed, target_text,
                                   torch.log_softmax(al_t, dim=-1), self.vocab,
                                   torch.log_softmax(sc_t, dim=-1), self.vocab,
                                   sample_rate=SR, calibrate=calibrate, calibration_path=self.calibration_path)
        result["stream"] = self.stitcher.summary()
        return result


class SessionStore:
    """프로세스 메모리의 녹음 세션(서버는 워커 하나, Dockerfile). 오래 안 쓴 세션은 지우고, 사람마다 최근 2개만 둔다."""

    def __init__(self, ttl_s: float = 120.0, per_user: int = 2, total: int = 64):
        self.ttl_s, self.per_user, self.total = ttl_s, per_user, total
        self._s: Dict[str, StreamSession] = {}
        self._lock = threading.Lock()

    def _sweep(self):
        now = time.monotonic()
        for k in [k for k, s in self._s.items() if now - s.touched > self.ttl_s]:
            del self._s[k]

    def create(self, user_id, cfg: Optional[StreamConfig] = None) -> StreamSession:
        forward, vocab, cal = load_backend()
        sess = StreamSession(user_id, forward, vocab, cal, cfg)
        with self._lock:
            self._sweep()
            mine = sorted((s for s in self._s.values() if s.user_id == user_id), key=lambda s: s.created)
            for s in mine[:max(0, len(mine) - self.per_user + 1)]:
                del self._s[s.id]
            if len(self._s) >= self.total:
                del self._s[min(self._s.values(), key=lambda s: s.touched).id]
            self._s[sess.id] = sess
        return sess

    def get(self, sid: str, user_id) -> Optional[StreamSession]:
        with self._lock:
            self._sweep()
            s = self._s.get(sid or "")
            return s if s is not None and s.user_id == user_id else None

    def pop(self, sid: str, user_id) -> Optional[StreamSession]:
        with self._lock:
            s = self._s.get(sid or "")
            if s is None or s.user_id != user_id:
                return None
            return self._s.pop(sid)


SESSIONS = SessionStore()
