/**
 * 배지 — 표시 정보(아이콘·설명)와 서버 판정(GET /api/analysis/overview 의 badges)을 합친다.
 * 판정 규칙은 backend/analytics.py(BADGES·badges()). 과제 탭 그리드와 분석 탭 '획득 배지' 수가 공용.
 * '수어 탐험'은 서버 기록이 없어 브라우저가 판정한다(수어 화면에 들어오면 markSignExplored()).
 * 희귀도("전체 사용자 중 N%")는 계산 API가 없어 percent=null — 핸드오프 §7-3에 따라 표시하지 않는다.
 */
const BADGE_META = [
  { key: 'first_step', label: '첫 걸음', icon: '/ui/medal-0.svg', desc: '첫 학습을 마치고 여정을 시작하기' },
  { key: 'streak7', label: '7일 연속', icon: '/ui/medal-1.svg', desc: '이레 동안 하루도 빠짐없이 학습하기' },
  { key: 'viseme_master', label: '입모양 마스터', icon: '/ui/medal-2.svg', desc: '모든 입모양 그룹을 완벽하게 익히기' },
  { key: 'acc90', label: '정확도 90%', shape: 'check', desc: '한 레슨에서 정확도 90% 이상을 달성하기' },
  { key: 'q100', label: '100문제 돌파', icon: '/ui/medal-3.svg', desc: '누적 100문제를 풀어내기' },
  { key: 'review_king', label: '복습왕', icon: '/ui/medal-4.svg', desc: '예정된 복습을 미루지 않고 모두 끝내기' },
  { key: 'free_talk', label: '자유 발화', icon: '/ui/medal-5.svg', desc: '대화 실전 단계에서 자유롭게 말해보기' },
  { key: 'sign', label: '수어 탐험', icon: '/ui/medal-6.svg', desc: '한국수어 학습을 처음으로 경험하기' },
  { key: 'streak30', label: '30일 연속', icon: '/ui/medal-7.svg', desc: '한 달 내내 학습 스트릭을 이어가기' },
  { key: 'dawn', label: '새벽 학습', icon: '/ui/medal-8.svg', desc: '새벽 시간에 학습을 완료하기' },
  { key: 'complete', label: '완주', icon: '/ui/medal-9.svg', desc: '전체 커리큘럼을 끝까지 마치기' },
  { key: 'level5', label: '레벨 5', shape: 'lock', desc: '학습을 반복해 레벨 5에 도달하기' },
]

const SIGN_KEY = 'liplab.signExplored'

export function markSignExplored() {
  try { localStorage.setItem(SIGN_KEY, '1') } catch { /* 저장소 차단 시 무시 */ }
}

function signExplored() {
  try { return localStorage.getItem(SIGN_KEY) === '1' } catch { return false }
}

/** 서버 판정 목록(없으면 전부 미획득)을 표시용 배지 12개로 바꾼다. */
export function mergeBadges(server) {
  const earned = new Map((server || []).map((b) => [b.key, b.earned]))
  return BADGE_META.map((m) => ({
    ...m,
    earned: m.key === 'sign' ? signExplored() : earned.get(m.key) === true,
    percent: null,
  }))
}
