/**
 * 학습 경로(CurriculumPath) 노드 상태: mastered | current | skip | locked.
 * 현재 단계 = 열린 단계(in_progress·unlocked) 중 가장 뒤(건너뛰기로 연 단계가 현재가 된다). 그 앞의 열린 단계는 지나온 단계(✓)로 보인다.
 * 소리 듣기만은 숙달하지 않은 앞의 열린 단계(in_progress·unlocked)를 숙달 표시(✓) 대신 열린 단계(current)로 둔다. 시작 단계 정하기(배치검사)가
 * 1·2단계를 진행 중으로, 3~k단계를 열린 채로 두기 때문이다(docs/listen-placement3-2026-10.md 11절). 어느 것도 숙달 전이라 ✓를 달면 틀린다.
 */
export function pathNodeState(list, track) {
  const openIdx = list.map((s, i) => (s.status === 'in_progress' || s.status === 'unlocked' ? i : -1)).filter((i) => i >= 0)
  const currentIdx = openIdx.length ? openIdx[openIdx.length - 1] : -1
  const nextLockedIdx = currentIdx >= 0 ? currentIdx + 1 : list.findIndex((s) => s.status === 'locked')
  const nodeStatus = (s, i) => {
    if (s.status === 'mastered') return 'mastered'
    if (i === currentIdx) return 'current'
    if (i < currentIdx && track === 'listen' && s.status !== 'locked') return 'current'   // 숙달 전, 함께 열린 단계
    if (i < currentIdx && s.status !== 'locked') return 'mastered'   // 건너뛰고 지나온 단계
    if (i === nextLockedIdx && s.status === 'locked') return 'skip'   // 다음 잠긴 단계 = 건너뛰기 후보
    return 'locked'
  }
  return { currentIdx, nextLockedIdx, nodeStatus }
}
