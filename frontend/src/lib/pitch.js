// 녹음 중 음높이(Hz) 추정(ACF2+ 자기상관). 녹음 루프가 약 4화면마다 2,048표본 버퍼로 부른다.
// 예전에는 모든 지연(버퍼 길이만큼)의 자기상관을 계산해 호출당 약 200만 번 곱셈이었는데, 쓰는 음높이는 70~500Hz라 지연을
// sampleRate/MIN_HZ까지만 계산한다(48kHz에서 약 690, 계산 약 45% 감소). 범위 밖(더 낮은 음)의 최댓값에 끌려 버려지던
// 프레임도 줄어든다. 결과가 범위 밖이면 -1.
export const MIN_HZ = 70
export const MAX_HZ = 500

export function autoCorrelate(buf, sampleRate) {
  const SIZE = buf.length
  let rms = 0
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i]
  rms = Math.sqrt(rms / SIZE)
  if (rms < 0.006) return -1
  let r1 = 0
  let r2 = SIZE - 1
  const thres = 0.2
  for (let i = 0; i < SIZE / 2; i++) if (Math.abs(buf[i]) < thres) { r1 = i; break }
  for (let i = 1; i < SIZE / 2; i++) if (Math.abs(buf[SIZE - i]) < thres) { r2 = SIZE - i; break }
  const b = buf.subarray ? buf.subarray(r1, r2) : buf.slice(r1, r2)
  const n = b.length
  if (n < 8) return -1
  const maxLag = Math.min(n - 1, Math.ceil(sampleRate / MIN_HZ) + 2)
  const c = new Float64Array(maxLag + 1)
  for (let i = 0; i <= maxLag; i++) {
    let s = 0
    for (let j = 0; j < n - i; j++) s += b[j] * b[j + i]
    c[i] = s
  }
  let d = 0
  while (d < maxLag && c[d] > c[d + 1]) d++
  let maxval = -Infinity
  let maxpos = -1
  for (let i = d; i <= maxLag; i++) if (c[i] > maxval) { maxval = c[i]; maxpos = i }
  let T0 = maxpos
  if (T0 <= 0) return -1
  const x1 = c[T0 - 1] || 0
  const x2 = c[T0]
  const x3 = T0 + 1 <= maxLag ? c[T0 + 1] : 0
  const a = (x1 + x3 - 2 * x2) / 2
  const bb = (x3 - x1) / 2
  if (a) T0 = T0 - bb / (2 * a)
  return sampleRate / T0
}
