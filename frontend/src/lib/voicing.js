// 가장 길게 이어진 발성 구간(초). 발성 단계('아—'를 길게)와 운율 '길게' 연습의 판정에 쓴다. 예전에는 녹음 시작부터 정지 버튼까지의
// 길이로 판정해, '아'를 짧게 내고 2초 기다렸다 멈춰도 '길게 유지'로 통과했다.
// trace: [{t(초), rms}] (녹음 루프가 약 4화면마다 남긴다). rms가 thr보다 큰 표본이 gap 안의 간격으로 이어지면 한 구간으로 본다
// (maxGap 이하의 짧은 끊김은 이어진 것으로). 표본 간격이 길면(느린 기기) 간격의 두 배까지 허용한다.
export function longestVoicedRun(trace, thr = 0.01, maxGap = 0.15) {
  const pts = (trace || []).filter((p) => Number.isFinite(p?.t) && Number.isFinite(p?.rms)).sort((a, b) => a.t - b.t)
  if (pts.length < 2) return 0
  const gaps = pts.slice(1).map((p, i) => p.t - pts[i].t).sort((a, b) => a - b)
  const step = gaps[Math.floor(gaps.length / 2)] || 0.07
  const gapOk = Math.max(maxGap + step, step * 2)   // 발성 표본 사이 거리 = 끊김 + 표본 간격 한 번
  let best = 0
  let start = null
  let last = null
  for (const p of pts) {
    if (p.rms <= thr) continue
    if (start == null || p.t - last > gapOk) start = p.t
    last = p.t
    best = Math.max(best, last - start + step)
  }
  return Math.round(best * 10) / 10
}
