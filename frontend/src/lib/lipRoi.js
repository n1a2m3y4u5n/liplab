/**
 * 화소 입술 ROI 자르기(독화 ①, docs/lipread-roi-2026-10.md 13절). 학습 때 쓴 liplab-lab/tools/lip_roi_extract.py(ROI_VERSION 1)를
 * 그대로 옮겼다. 순수 함수만 두어 노드 테스트와 대조 검사(scripts/lipread_roi/roi_parity.mjs)에서 브라우저와 같은 코드를 돌린다.
 *
 * 규칙(파이썬과 같음)
 *   - 프레임마다 입술 바깥 20점 무게중심(cx, cy), 61↔291 거리(입 너비), 눈꼬리 33→263 각도(roll). 좌표는 화소중심 기준(x·W − 0.5).
 *   - 클립 전체에서: 미검출 프레임은 선형보간, 가운데 이동평균 15프레임, 한 변 = 2.0 × 입 너비 중앙값(클립 안에서 고정).
 *   - 자르기: 회전·정사각 역사상, 원본/출력 화소비가 1.5를 넘으면 정수배 과표본 뒤 평균 축소, 88×88 흑백 uint8.
 *     cv2.warpAffine(INTER_LINEAR, BORDER_REPLICATE)의 고정소수점 계산(좌표 1/1024, 보간 가중치 1/32)을 그대로 따른다.
 *   - 흑백: cv2.COLOR_BGR2GRAY와 같은 정수식.
 *   - 시간: 프레임 시각 → 30 fps 격자(같은 칸이면 마지막, 빈 칸은 가장 가까운 프레임). 유효 = 검출 + 3프레임 이하 공백.
 *   - 모델 입력: 가운데 80×80(학습 CROP), 75프레임보다 짧으면 앞뒤를 가장자리 프레임으로 채운다(판정의 idle75 창 길이),
 *     시퀀스 z-정규화는 float64로 여기서 한다(roiModelInput).
 */

export const ROI_SIZE = 88
export const ROI_CROP = 80
export const ROI_MARGIN = 2.0
export const ROI_SMOOTH = 15
export const ROI_FPS = 30
export const ROI_MIN_LEN = 75
export const MAX_GAP_FILL = 3
export const OVERSAMPLE_AT = 1.5
export const LIP_OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
export const EYE_A = 33
export const EYE_B = 263

/** cvRound(lrint)와 같은 반올림: 가운데 값은 짝수 쪽. */
export function roundHalfEven(x) {
  const r = Math.round(x)
  if (Math.abs(x % 1) === 0.5) return 2 * Math.round(x / 2)
  return r
}

/** MediaPipe 랜드마크(정규화 .x .y) → [cx, cy, width, theta]. lip_roi_extract.landmark_geometry와 같다. */
export function landmarkGeometry(lms, w, h) {
  const px = (i) => [lms[i].x * w - 0.5, lms[i].y * h - 0.5]
  let sx = 0, sy = 0
  const P = LIP_OUTER.map(px)
  for (const [x, y] of P) { sx += x; sy += y }
  const cx = sx / P.length, cy = sy / P.length
  const width = Math.hypot(P[10][0] - P[0][0], P[10][1] - P[0][1])
  const a = px(EYE_A), b = px(EYE_B)
  const theta = Math.atan2(b[1] - a[1], b[0] - a[0])
  return [cx, cy, width, theta]
}

/** 검출 표시 → 유효 표시(양쪽이 검출된 길이 ≤maxGap 공백만 채움). */
export function fillGaps(det, maxGap = MAX_GAP_FILL) {
  const out = det.slice()
  let prev = -1
  for (let i = 0; i < det.length; i++) {
    if (!det[i]) continue
    const gap = i - prev - 1
    if (prev >= 0 && gap >= 1 && gap <= maxGap) for (let j = prev + 1; j < i; j++) out[j] = true
    prev = i
  }
  return out
}

/** np.interp(t, t[good], x[good]) (양끝 밖은 끝값). */
function interpGood(x, good) {
  const idx = []
  for (let i = 0; i < x.length; i++) if (good[i]) idx.push(i)
  const out = new Float64Array(x.length)
  let p = 0
  for (let i = 0; i < x.length; i++) {
    if (i <= idx[0]) { out[i] = x[idx[0]]; continue }
    if (i >= idx[idx.length - 1]) { out[i] = x[idx[idx.length - 1]]; continue }
    while (idx[p + 1] < i) p++
    const a = idx[p], b = idx[p + 1]
    out[i] = a === i ? x[a] : x[a] + (x[b] - x[a]) * ((i - a) / (b - a))
  }
  return out
}

/** 가운데 이동평균(끝은 가장자리 반복), 길이 보존. */
export function smooth(x, win) {
  const n = x.length
  if (win <= 1 || n < 2) return Float64Array.from(x)
  const h = Math.floor(win / 2), L = 2 * h + 1
  const out = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let j = i - h; j <= i + h; j++) s += x[Math.min(n - 1, Math.max(0, j))]
    out[i] = s / L
  }
  return out
}

function median(a) {
  const s = Float64Array.from(a).sort()
  const n = s.length
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2
}

/** np.unwrap(기본 discont=π). */
function unwrap(a) {
  const out = Float64Array.from(a)
  let off = 0
  for (let i = 1; i < a.length; i++) {
    const d = a[i] - a[i - 1]
    let dd = ((d + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI
    if (dd === -Math.PI && d > 0) dd = Math.PI
    const corr = dd - d
    if (Math.abs(d) >= Math.PI) off += corr
    out[i] = a[i] + off
  }
  return out
}

/** geoms: [[cx,cy,width,theta] | null] (프레임마다) → {cx, cy, theta, side} 또는 null(검출 0). */
export function planCrops(geoms, { margin = ROI_MARGIN, win = ROI_SMOOTH, rotate = true } = {}) {
  const n = geoms.length
  const ok = geoms.map((g) => !!g && g.every(Number.isFinite) && g[2] > 1e-6)
  if (!ok.some(Boolean)) return null
  const col = (k) => geoms.map((g, i) => (ok[i] ? g[k] : NaN))
  const cx = smooth(interpGood(col(0), ok), win)
  const cy = smooth(interpGood(col(1), ok), win)
  let theta
  if (rotate) {
    const th = col(3)
    const okIdx = th.map((_, i) => i).filter((i) => ok[i])
    const uw = unwrap(okIdx.map((i) => th[i]))
    okIdx.forEach((i, j) => { th[i] = uw[j] })
    theta = smooth(interpGood(th, ok), win)
  } else theta = new Float64Array(n)
  const side = margin * median(geoms.filter((_, i) => ok[i]).map((g) => g[2]))
  return { cx, cy, theta, side }
}

/** 출력 (u,v) → 원본 (x,y) 2×3 [a, b, c, d, e, f] (x = a·u + b·v + c). */
export function cropMatrix(cx, cy, theta, side, out) {
  const s = side / out
  const c = Math.cos(theta), sn = Math.sin(theta)
  const A = [s * c, -s * sn, s * sn, s * c]
  const o = (out - 1) / 2
  return [A[0], A[1], cx - (A[0] * o + A[1] * o), A[2], A[3], cy - (A[2] * o + A[3] * o)]
}

const AB_BITS = 10, AB_SCALE = 1 << AB_BITS, INTER_BITS = 5, INTER_TAB = 1 << INTER_BITS
const ROUND_DELTA = AB_SCALE / INTER_TAB / 2
const satInt = (v) => roundHalfEven(v)

/**
 * cv2.warpAffine(src, M, (big,big), INTER_LINEAR | WARP_INVERSE_MAP, BORDER_REPLICATE)와 같은 계산.
 * gray: Uint8Array(W*H) 또는 Float32Array. 반환: uint8이면 Uint8Array, float이면 Float32Array.
 */
export function warpAffineCv(gray, W, H, M, big, isFloat) {
  const out = isFloat ? new Float32Array(big * big) : new Uint8Array(big * big)
  const adelta = new Int32Array(big), bdelta = new Int32Array(big)
  for (let x = 0; x < big; x++) { adelta[x] = satInt(M[0] * x * AB_SCALE); bdelta[x] = satInt(M[3] * x * AB_SCALE) }
  const f = Math.fround
  for (let y = 0; y < big; y++) {
    const X0 = satInt((M[1] * y + M[2]) * AB_SCALE) + ROUND_DELTA
    const Y0 = satInt((M[4] * y + M[5]) * AB_SCALE) + ROUND_DELTA
    for (let x = 0; x < big; x++) {
      const X = (X0 + adelta[x]) >> (AB_BITS - INTER_BITS)
      const Y = (Y0 + bdelta[x]) >> (AB_BITS - INTER_BITS)
      const sx = X >> INTER_BITS, sy = Y >> INTER_BITS
      const ax = X & (INTER_TAB - 1), ay = Y & (INTER_TAB - 1)
      const x0 = Math.min(W - 1, Math.max(0, sx)), x1 = Math.min(W - 1, Math.max(0, sx + 1))
      const y0 = Math.min(H - 1, Math.max(0, sy)), y1 = Math.min(H - 1, Math.max(0, sy + 1))
      const p00 = gray[y0 * W + x0], p01 = gray[y0 * W + x1], p10 = gray[y1 * W + x0], p11 = gray[y1 * W + x1]
      if (isFloat) {
        const fx = f(ax / INTER_TAB), fy = f(ay / INTER_TAB)
        const vx0 = f(1 - fx), vy0 = f(1 - fy)
        const w00 = f(vy0 * vx0), w01 = f(vy0 * fx), w10 = f(fy * vx0), w11 = f(fy * fx)
        out[y * big + x] = f(f(f(f(p00 * w00) + f(p01 * w01)) + f(p10 * w10)) + f(p11 * w11))
      } else {
        // 8U 표: 가중치 (32−a)(32−b)·32 등(합 32768, 정확), 결과 (합 + 2^14) >> 15
        const w00 = (INTER_TAB - ax) * (INTER_TAB - ay) * 32, w01 = ax * (INTER_TAB - ay) * 32
        const w10 = (INTER_TAB - ax) * ay * 32, w11 = ax * ay * 32
        const v = (p00 * w00 + p01 * w01 + p10 * w10 + p11 * w11 + (1 << 14)) >> 15
        out[y * big + x] = v < 0 ? 0 : v > 255 ? 255 : v
      }
    }
  }
  return out
}

/** 흑백 프레임 → 회전·정사각 자르기 (out×out) Uint8Array. lip_roi_extract.crop_frame(cv2 경로)와 같다. */
export function cropFrame(gray, W, H, cx, cy, theta, side, out = ROI_SIZE) {
  const k = Math.max(1, Math.ceil(side / out / OVERSAMPLE_AT))
  const big = out * k
  const M = cropMatrix(cx, cy, theta, side, big)
  if (k === 1) return warpAffineCv(gray, W, H, M, big, false)
  const src = gray instanceof Float32Array ? gray : Float32Array.from(gray)
  const patch = warpAffineCv(src, W, H, M, big, true)
  const res = new Uint8Array(out * out)
  const kk = k * k
  for (let v = 0; v < out; v++) {
    for (let u = 0; u < out; u++) {
      let s = 0
      for (let a = 0; a < k; a++) {
        const row = (v * k + a) * big + u * k
        for (let b = 0; b < k; b++) s += patch[row + b]
      }
      const m = Math.fround(s / kk)
      const r = roundHalfEven(m)
      res[v * out + u] = r < 0 ? 0 : r > 255 ? 255 : r
    }
  }
  return res
}

/** RGBA(캔버스 getImageData) → 흑백 Uint8Array. cv2.cvtColor(BGR2GRAY, OpenCV 4.x)의 정수식(R 9798, G 19235, B 3735, 15비트). */
export function rgbaToGray(rgba, n) {
  const g = new Uint8Array(n)
  for (let i = 0, j = 0; i < n; i++, j += 4) g[i] = (rgba[j] * 9798 + rgba[j + 1] * 19235 + rgba[j + 2] * 3735 + 16384) >> 15
  return g
}

/** 프레임 시각(ms, 첫 프레임 기준 아니어도 됨) → 30 fps 격자 칸마다 쓸 프레임 번호와 정확 여부(grid_sources와 같음). */
export function gridSources(timesMs, fps = ROI_FPS) {
  if (!timesMs.length) return { src: [], exact: [] }
  const t0 = timesMs[0]
  // 파이썬 round(짝수 쪽)와 같게. 학습은 t_ms = round(i/fps·1000)을 먼저 정수로 만든 뒤 칸을 정했다
  const ks = timesMs.map((t) => roundHalfEven(roundHalfEven(t - t0) * fps / 1000))
  const T = ks[ks.length - 1] + 1
  const src = new Array(T).fill(-1), exact = new Array(T).fill(false)
  ks.forEach((k, j) => { if (k >= 0 && k < T) { src[k] = j; exact[k] = true } })
  const ex = []
  for (let g = 0; g < T; g++) if (exact[g]) ex.push(g)
  for (let g = 0; g < T; g++) {
    if (exact[g]) continue
    let best = null
    for (const e of ex) if (best === null || Math.abs(e - g) < Math.abs(best - g)) best = e
    src[g] = src[best]
  }
  return { src, exact }
}

/**
 * 녹화한 프레임 [{t, gray, geom}] (gray = 흑백 Uint8Array(W*H), geom = landmarkGeometry 결과 또는 null) → ROI 시퀀스.
 * 반환 {roi: Uint8Array[], valid: bool[], det: bool[], side} 또는 null(얼굴이 한 번도 안 잡힘·프레임 없음).
 */
export function extractRoiSequence(frames, W, H) {
  if (!frames || !frames.length) return null
  const plan = planCrops(frames.map((f) => f.geom))
  if (!plan) return null
  const crops = frames.map((f, i) => cropFrame(f.gray, W, H, plan.cx[i], plan.cy[i], plan.theta[i], plan.side))
  const det = frames.map((f) => !!f.geom)
  const { src, exact } = gridSources(frames.map((f) => f.t))
  const detG = src.map((s, g) => det[s] && exact[g])
  return { roi: src.map((s) => crops[s]), valid: fillGaps(detG), det: detG, side: plan.side }
}

/**
 * ROI 시퀀스 → 모델 입력 roi_z Float32Array(T·80·80)와 T. 짧으면 앞뒤를 가장자리 프레임으로 채워 minLen에 맞춘다.
 * 정규화(학습 normalize와 같은 식: /255, 시퀀스 전체 평균·모분산, 표준편차 하한 1e-2)는 float64로 여기서 한다. 모델 그래프 안에서
 * float32로 수십만~백수십만 화소를 더하면 엔진마다 오차가 달라 logits가 0.1 넘게 어긋났다(roi_web_export.py, 13.2절).
 */
export function roiModelInput(roi, minLen = ROI_MIN_LEN, size = ROI_SIZE, crop = ROI_CROP) {
  let seq = roi
  if (seq.length && seq.length < minLen) {
    const need = minLen - seq.length, nl = Math.floor(need / 2), nr = need - nl
    seq = [...new Array(nl).fill(seq[0]), ...seq, ...new Array(nr).fill(seq[seq.length - 1])]
  }
  const T = seq.length, c0 = (size - crop) >> 1, N = T * crop * crop
  const raw = new Uint8Array(N)
  for (let t = 0; t < T; t++) {
    const fr = seq[t], base = t * crop * crop
    for (let y = 0; y < crop; y++) {
      const r = (y + c0) * size + c0
      for (let x = 0; x < crop; x++) raw[base + y * crop + x] = fr[r + x]
    }
  }
  // 화소값이 0~255 정수라 도수분포로 합을 구하면 float64에서도 순서와 무관하게 정확하다
  const hist = new Float64Array(256)
  for (let i = 0; i < N; i++) hist[raw[i]]++
  let s1 = 0
  for (let v = 0; v < 256; v++) s1 += hist[v] * (v / 255)
  const m = s1 / N
  let s2 = 0
  for (let v = 0; v < 256; v++) { const d = v / 255 - m; s2 += hist[v] * d * d }
  const sd = Math.max(Math.sqrt(s2 / N), 1e-2)
  const lut = new Float32Array(256)
  for (let v = 0; v < 256; v++) lut[v] = (v / 255 - m) / sd
  const data = new Float32Array(N)
  for (let i = 0; i < N; i++) data[i] = lut[raw[i]]
  return { data, T }
}
