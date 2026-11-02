import { LIP_OUTER, gridSources, roiModelInput } from './lipRoi.js'

// extract_blendshapes.py:60-67, 89-113, 137-149의 순서와 픽셀 좌표 규칙.
export const LIPS_IDX = [...LIP_OUTER, 78, 95, 88, 178, 87, 14, 317, 402, 318, 324,
  308, 415, 310, 311, 312, 13, 82, 81, 80, 191]

export function landmarkLips80(lms, W, H) {
  if (!lms || !(W > 0 && H > 0)) return null
  const ids = [...LIPS_IDX, 33, 263]
  if (!ids.every((i) => Number.isFinite(lms[i]?.x) && Number.isFinite(lms[i]?.y))) return null
  const ex = lms[263].x * W - lms[33].x * W, ey = lms[263].y * H - lms[33].y * H
  const iod = Math.hypot(ex, ey)
  if (!(iod > 1e-9)) return null
  const pts = LIPS_IDX.map((i) => [lms[i].x * W, lms[i].y * H])
  const cx = pts.reduce((s, p) => s + p[0], 0) / 40
  const cy = pts.reduce((s, p) => s + p[1], 0) / 40
  const c = ex / iod, s = ey / iod
  // CPython round(float, 4)와 동일하게 이진 double을 정확한 유리수로 반올림한다.
  return pts.flatMap(([x, y]) => [round4((c * (x - cx) + s * (y - cy)) / iod),
    round4((-s * (x - cx) + c * (y - cy)) / iod)])
}

export function round4(x) {
  if (!Number.isFinite(x) || x === 0) return x
  const buf = new DataView(new ArrayBuffer(8))
  buf.setFloat64(0, Math.abs(x))
  const bits = buf.getBigUint64(0), exp = Number((bits >> 52n) & 2047n)
  let n = (bits & ((1n << 52n) - 1n)) | (exp ? 1n << 52n : 0n)
  const shift = (exp || 1) - 1023 - 52
  n *= 10000n
  let d = 1n
  if (shift >= 0) n <<= BigInt(shift)
  else d <<= BigInt(-shift)
  let q = n / d
  const r = n % d
  if (2n * r > d || (2n * r === d && q % 2n)) q++
  return Math.sign(x) * Number(q) / 10000
}

/** 학습 prepare의 float32 저장→np.interp. 결측을 보간하고 관측 마스크를 보존한다. */
export function coordinateSequence(frames) {
  const { src, exact } = gridSources(frames.map((f) => f.t))
  const det = src.map((s, g) => !!(exact[g] && frames[s].lips?.length === 80 && frames[s].lips.every(Number.isFinite)))
  const good = det.flatMap((v, i) => v ? [i] : [])
  const lips = src.map(() => new Float32Array(80))
  let p = 0
  for (let g = 0; g < src.length && good.length; g++) {
    while (p + 1 < good.length && good[p + 1] <= g) p++
    const a = g <= good[0] ? good[0] : good[p]
    const b = g <= good[0] || g >= good.at(-1) ? a : (good[p + 1] ?? a)
    for (let k = 0; k < 80; k++) {
      const av = Math.fround(frames[src[a]].lips[k]), bv = Math.fround(frames[src[b]].lips[k])
      lips[g][k] = a === b ? av : av + (bv - av) * ((g - a) / (b - a))
    }
  }
  return { lips, det, valid: det.slice(), interpolated: det.map((v) => !v && !!good.length), allMissing: !good.length, src }
}

/** idle75: 같은 화자의 idle 자료가 없는 카메라는 Python p4_window의 양끝 반복 fallback. */
export function fusionModelInput(roi, coordinates, indices = roi.map((_, i) => i)) {
  if (!indices.length || coordinates.lips.length !== roi.length ||
    !indices.every((i) => Number.isInteger(i) && i >= 0 && i < roi.length)) throw new Error('Unaligned fusion frames')
  const selected = indices.slice()
  if (selected.length < 75) {
    const need = 75 - selected.length, nl = Math.floor(need / 2)
    selected.unshift(...Array(nl).fill(selected[0]))
    selected.push(...Array(need - nl).fill(selected.at(-1)))
  }
  const input = roiModelInput(selected.map((i) => roi[i]))
  return { ...input, lips: Float32Array.from(selected.flatMap((i) => Array.from(coordinates.lips[i]))),
    indices: selected, valid: selected.map((i) => coordinates.det[i]),
    interpolated: selected.map((i) => coordinates.interpolated[i]) }
}

export function fusionFeeds(ort, data, T, lips, inputNames = ['roi_z', 'lips']) {
  if (data.length !== T * 80 * 80 || lips?.length !== T * 80 || inputNames.length !== 2) throw new Error('Invalid fusion inputs')
  // 내보내기 이름을 세션 계약으로 확인한다. 순서로 추측하지 않는다.
  if (!inputNames.includes('roi_z') || !inputNames.includes('lips')) throw new Error('Expected roi_z + lips')
  return { roi_z: new ort.Tensor('float32', data, [1, T, 80, 80]),
    lips: new ort.Tensor('float32', lips, [1, T, 80]) }
}
