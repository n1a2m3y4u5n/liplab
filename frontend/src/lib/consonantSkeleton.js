// 자음 골격: 음절마다 첫소리 자음(초성)만 보이고 모음·받침은 가린다.
// 3단계 힌트 2(예전 '첫 글자')와 자음 피드백(계획 C9·C10)이 같이 쓴다. 서버 backend/sentence_feedback.py skeleton과 같은 규칙:
// 한글 음절은 초성(첫소리 ㅇ은 'ㅇ'), 숫자·영문은 그대로, 문장 부호는 뺀다.
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'.split('')
const PUNCT = /[^\p{L}\p{N}]/u

export function onsetOf(ch) {
  const c = ch.charCodeAt(0)
  if (c >= 0xac00 && c <= 0xd7a3) return CHO[Math.floor((c - 0xac00) / 588)]
  return ch
}

/** 낱말 하나의 자음 골격(글자 목록). */
export function wordSkeleton(word) {
  return Array.from(word || '').filter((ch) => !PUNCT.test(ch)).map(onsetOf)
}

/** 문장을 낱말마다 자음 골격으로. 빈 낱말(부호만)은 뺀다. */
export function sentenceSkeleton(sentence) {
  return String(sentence || '').split(/\s+/).map(wordSkeleton).filter((w) => w.length > 0)
}
