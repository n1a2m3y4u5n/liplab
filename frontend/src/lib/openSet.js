// 개방형(주관식) 문항 비율(docs/curriculum-roadmap.md 1-2, P3). 폐쇄형(선다형)만으로 훈련하면 개방형 이해로 옮겨 가기 어렵다.

// 2단계: 숙달한 뒤 레슨(12문항)의 30%를 단어 입력으로 낸다(12문항이면 4문항).
export const STAGE2_TYPED_SHARE = 0.3

/** 한 레슨에서 주관식으로 낼 문항 번호(0부터) 집합. 숙달 전이면 빈 집합. skip에 든 번호(문맥 문항 등)는 고르지 않는다. */
export function typedSlots(length, mastered, rand = Math.random, skip = new Set()) {
  if (!mastered || length <= 0) return new Set()
  const want = Math.round(length * STAGE2_TYPED_SHARE)
  const free = Array.from({ length }, (_, i) => i).filter((i) => !skip.has(i))
  for (let i = free.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1))
    ;[free[i], free[j]] = [free[j], free[i]]
  }
  return new Set(free.slice(0, Math.min(want, free.length)))
}

/**
 * 3단계 문장 문항 유형 목록: 'test'(주관식) · 'test-multiple'(4지선다) · 'essay'(서술형).
 * 지금 3단계는 세 유형을 돌려 가며 내서 선다형이 약 1/3이다. 숙달 추정값(0~100, 없으면 null)이 오를수록 선다형을 줄인다.
 *   50 미만(또는 기록 없음): 지금과 같다(선다형 약 1/3)
 *   50 이상 70 미만: 선다형을 절반 정도로(문장 6개마다 1개, 최소 1개), 나머지는 주관식·서술형
 *   70 이상: 주관식·서술형만
 * 로드맵의 '50 이상 반반'을 글자대로 따르면 지금(주관식·서술형 2/3)보다 선다형이 오히려 늘어서, 선다형 몫을 줄이는 쪽으로 옮겼다.
 */
export function sentenceQuestionTypes(length, mastery = null, rand = Math.random) {
  const m = Number.isFinite(mastery) ? mastery : null
  let types
  if (m == null || m < 50) {
    types = Array.from({ length }, (_, i) => ['test', 'test-multiple', 'essay'][i % 3])
  } else {
    const nChoice = m >= 70 ? 0 : Math.min(length, Math.max(1, Math.ceil(length / 6)))
    types = Array.from({ length }, (_, i) => (i < nChoice ? 'test-multiple' : ((i - nChoice) % 2 === 0 ? 'test' : 'essay')))
  }
  for (let i = types.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1))
    ;[types[i], types[j]] = [types[j], types[i]]
  }
  return types
}
