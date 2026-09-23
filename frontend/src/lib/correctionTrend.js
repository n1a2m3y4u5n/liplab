// 웹캠 조음 교정 세션의 처음·끝 오차(축 E-9).
// 표본마다 백엔드 articulation_correction이 준 평균 |목표−관찰|(error, 0~1)을 모아 두고,
// 처음 몇 개와 마지막 몇 개의 평균을 비교한다. 0에 가까울수록 목표 조음에 가깝다.

/** 오차열 → { start, end } (각각 최대 5개 평균). 표본이 4개 미만이면 null. */
export function errorEnds(errs) {
  const n = errs.length
  if (n < 4) return null
  const k = Math.min(5, Math.floor(n / 2))
  const mean = (xs) => Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 1000) / 1000
  return { start: mean(errs.slice(0, k)), end: mean(errs.slice(n - k)) }
}
