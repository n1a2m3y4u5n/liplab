/**
 * 한글 자모 → 지문자(지화) 손모양 이미지 매핑.
 * 이미지 출처: "Korean manual alphabet" © Kwamikagami / Wikimedia Commons,
 *             CC BY-SA 3.0. (public/fingerspell/*.jpg 로 로컬 서빙)
 *
 * 커버: 기본 자음 14 + ㅆ, 기본 모음 14 + ㅚㅟㅢ (총 32자).
 * 미커버(이미지 없음 → 텍스트 폴백): 된소리 ㄲㄸㅃㅉ, w복합모음 ㅘㅙㅝㅞ, 겹받침 등.
 */
const JAMO_TO_ROMAN = {
  // 자음
  'ㄱ': 'g', 'ㄴ': 'n', 'ㄷ': 'd', 'ㄹ': 'r', 'ㅁ': 'm', 'ㅂ': 'b', 'ㅅ': 's',
  'ㅇ': 'ng', 'ㅈ': 'j', 'ㅊ': 'ch', 'ㅋ': 'k', 'ㅌ': 't', 'ㅍ': 'p', 'ㅎ': 'h', 'ㅆ': 'ss',
  // 모음
  'ㅏ': 'a', 'ㅐ': 'ae', 'ㅑ': 'ya', 'ㅒ': 'yae', 'ㅓ': 'eo', 'ㅔ': 'e', 'ㅕ': 'yeo', 'ㅖ': 'ye',
  'ㅗ': 'o', 'ㅛ': 'yo', 'ㅜ': 'u', 'ㅠ': 'yu', 'ㅡ': 'eu', 'ㅣ': 'i', 'ㅚ': 'oe', 'ㅟ': 'wi', 'ㅢ': 'ui',
}

/** 자모의 손모양 이미지 경로. 없으면 null(텍스트 폴백). */
export function fingerspellImage(jamo) {
  const r = JAMO_TO_ROMAN[jamo]
  return r ? `/fingerspell/${r}.jpg` : null
}
