/**
 * 자모/문자 → 지문자(지화) 손모양 이미지 매핑.
 *
 * · 한글: "Korean manual alphabet" © Kwamikagami / Wikimedia Commons, CC BY-SA 3.0
 *   (public/fingerspell/*.jpg). 커버 32자 — 기본 자음 14 + ㅆ, 기본 모음 14 + ㅚㅟㅢ.
 * · 영문(A~Z): 국제(미국식) 지문자, "Sign language A~Z" Wikimedia Commons, Public Domain
 *   (public/fingerspell/latin/*.svg). 한국수어에 라틴 지문자 표준은 없어 국제 지문자를 차용.
 *
 * 미커버(→ 텍스트 폴백): 된소리 ㄲㄸㅃㅉ, w복합모음 ㅘㅙㅝㅞ, 겹받침, 숫자·기호 등.
 */
const JAMO_TO_ROMAN = {
  // 자음
  'ㄱ': 'g', 'ㄴ': 'n', 'ㄷ': 'd', 'ㄹ': 'r', 'ㅁ': 'm', 'ㅂ': 'b', 'ㅅ': 's',
  'ㅇ': 'ng', 'ㅈ': 'j', 'ㅊ': 'ch', 'ㅋ': 'k', 'ㅌ': 't', 'ㅍ': 'p', 'ㅎ': 'h', 'ㅆ': 'ss',
  // 모음
  'ㅏ': 'a', 'ㅐ': 'ae', 'ㅑ': 'ya', 'ㅒ': 'yae', 'ㅓ': 'eo', 'ㅔ': 'e', 'ㅕ': 'yeo', 'ㅖ': 'ye',
  'ㅗ': 'o', 'ㅛ': 'yo', 'ㅜ': 'u', 'ㅠ': 'yu', 'ㅡ': 'eu', 'ㅣ': 'i', 'ㅚ': 'oe', 'ㅟ': 'wi', 'ㅢ': 'ui',
}

/** 자모/문자의 손모양 이미지 경로. 없으면 null(텍스트 폴백). */
export function fingerspellImage(ch) {
  const r = JAMO_TO_ROMAN[ch]
  if (r) return `/fingerspell/${r}.jpg`                       // 한글 지문자
  if (/^[A-Za-z]$/.test(ch)) return `/fingerspell/latin/${ch.toUpperCase()}.svg`  // 국제(미국식) 지문자
  return null
}
