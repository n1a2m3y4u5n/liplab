// 1단계 인지퀴즈·입모양 복습 보기의 쉬운 이름(docs/mastery-ewma.md 11.2절). 예전 보기는 무리 이름과 음소 목록('양순음(ㅂ, ㅃ, ㅍ, ㅁ)',
// 평균 16.3자)이라 이름표를 외우고 글을 읽어야 했다. 지금은 겉으로 보이는 입모양을 쉬운 말로 적고 대표 음절을 붙인다.
// 전문 이름(양순음 등)과 음소 목록은 학습 자료 화면(VisemeLiteracy LearnPanel)에 그대로 둔다.
// 입 안쪽 무리(6·7·8·10)는 퀴즈 보기로 나오지 않지만 학습 자료 칩에 같은 이름을 쓰려고 함께 둔다.
export const VISEME_PLAIN = {
  1: { look: '입술 닫힘', ex: ['바', '마'] },
  2: { look: '입 크게 벌림', ex: ['아'] },
  3: { look: '입 옆으로 당김', ex: ['이'] },
  4: { look: '입술 둥글게', ex: ['오', '우'] },
  5: { look: '입 조금 벌림', ex: ['어', '으'] },
  6: { look: '혀끝 소리', ex: ['다', '나'] },
  7: { look: '혀 뒤 소리', ex: ['가'] },
  8: { look: '숨소리', ex: ['하'] },
  9: { look: '오므렸다 벌림', ex: ['와'] },
  10: { look: '입술 살짝 내밂', ex: ['자'] },
}

/** 입모양 무리 번호 → 보기 이름('입술 닫힘 (바·마)'). 모르는 번호면 빈 문자열. */
export function plainVisemeLabel(visemeId) {
  const p = VISEME_PLAIN[visemeId]
  return p ? `${p.look} (${p.ex.join('·')})` : ''
}

/** 레슨 객체({viseme_id, name}) → 보기 이름. 쉬운 이름이 없는 무리는 서버 이름을 그대로 쓴다. */
export function lessonPlainLabel(lesson) {
  return plainVisemeLabel(lesson?.viseme_id) || lesson?.name || ''
}
