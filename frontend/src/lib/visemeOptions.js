// 1단계 입모양 인지·입모양 복습 문항의 오답 보기. 아바타가 그리는 입모양(visemeShapes의 블렌드셰이프 목표값)이 정답과 거의
// 같은 무리는 뺀다. 예전에는 나머지 무리에서 무작위로 3개를 골라, 정답이 중설모음(5, 턱 0.22)일 때 연구개음(7, 턱 0.22, 거리 0.06)·
// 성문음(8, 0.07)·치경음(6, 0.16)·경구개음(10, 0.19)이 88% 확률로 섞였다(1단계 문항의 약 15%가 화면만으로는 풀 수 없었다).
// 2단계 단어 보기에서 입모양이 같은 단어를 뺀 것과 같은 원칙이다. 뚜렷이 다른 무리끼리는 0.7~1.1(양순 1과 개방 2, 전설 3과 원순 4).
import { VISEME_BLENDSHAPES } from './visemeShapes.js'

export const MIN_SHAPE_DISTANCE = 0.2

export function shapeDistance(a, b) {
  const A = VISEME_BLENDSHAPES[a] || {}
  const B = VISEME_BLENDSHAPES[b] || {}
  const keys = new Set([...Object.keys(A), ...Object.keys(B)])
  let s = 0
  for (const k of keys) s += ((A[k] || 0) - (B[k] || 0)) ** 2
  return Math.sqrt(s)
}

/** lessons([{viseme_id, …}]) 가운데 정답과 화면에서 가를 수 있는 무리만 무작위로 k개. */
export function pickVisemeDistractors(targetId, lessons, k = 3, random = Math.random) {
  const pool = lessons.filter((l) => l.viseme_id !== targetId && shapeDistance(targetId, l.viseme_id) >= MIN_SHAPE_DISTANCE)
  return pool.map((l) => [random(), l]).sort((x, y) => x[0] - y[0]).slice(0, k).map(([, l]) => l)
}

/** 한 레슨(n문항)의 정답 무리 순서: 무리마다 고르게(n/무리 수번씩) 섞고 같은 무리가 연달아 나오지 않게 한다.
 *  예전에는 매 문항 무작위(복원추출)라 12문항에 보이는 무리 6개 중 하나 이상이 빠질 확률이 56%였고, 어떤 무리는 4~5번 나왔다. */
export function balancedTargets(items, n, random = Math.random) {
  if (!items.length) return []
  const out = []
  while (out.length < n) {
    const round = items.map((it) => [random(), it]).sort((a, b) => a[0] - b[0]).map(([, it]) => it)
    // 앞 라운드 끝과 이번 라운드 첫 항목이 같으면 뒤 항목과 바꾼다
    if (out.length && round.length > 1 && round[0] === out[out.length - 1]) [round[0], round[1]] = [round[1], round[0]]
    out.push(...round)
  }
  return out.slice(0, n)
}
