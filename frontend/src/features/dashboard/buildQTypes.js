// 테스트 탭 문제 유형: 주관식 · 4지선다 · 서술형을 골고루 섞는다.
// (대시보드 본체의 startScenario와 ReviewSection이 함께 쓴다)
const TEST_QTYPES = ['test', 'test-multiple', 'essay']
export function buildQTypes(n) {
  const arr = Array.from({ length: n }, (_, i) => TEST_QTYPES[i % TEST_QTYPES.length])
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}
