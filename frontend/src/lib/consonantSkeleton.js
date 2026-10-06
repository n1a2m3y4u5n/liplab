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

// 받침까지 보이는 자음 골격: 모음 자리를 '_'로 둔다(바록 → ㅂ_ㄹ_ㄱ). 뜻 없는 말 짝 맞추기(C10)가 시행 전에 보여 준다.
// 첫소리 ㅇ은 소리가 없어 적지 않는다. 서버 backend/nonsense_words.py skeleton과 같은 규칙(nonsensePairing.test.mjs가 확인).
const JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ',
  'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

/** 낱말의 자음 골격 문자열(한글 음절이 아닌 글자는 뺀다). */
export function consonantFrame(word) {
  return Array.from(word || '').map((ch) => {
    const c = ch.charCodeAt(0)
    if (c < 0xac00 || c > 0xd7a3) return ''
    const k = c - 0xac00
    const cho = CHO[Math.floor(k / 588)]
    return (cho === 'ㅇ' ? '' : cho) + '_' + JONG[k % 28]
  }).join('')
}
