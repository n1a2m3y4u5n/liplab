/**
 * 자모/문자 → 지문자(지화) 손모양 이미지 매핑.
 *
 * · 한글: "Korean manual alphabet" © Kwamikagami / Wikimedia Commons, CC BY-SA 3.0
 *   (public/fingerspell/*.jpg). 커버 32자 — 기본 자음 14 + ㅆ, 기본 모음 14 + ㅚㅟㅢ.
 * · 영문(A~Z): 국제(미국식) 지문자, "Sign language A~Z" Wikimedia Commons, Public Domain
 *   (public/fingerspell/latin/*.svg). 한국수어에 라틴 지문자 표준은 없어 국제 지문자를 차용.
 *
 * 그림이 없는 된소리 ㄲㄸㅃㅉ, w 이중모음 ㅘㅙㅝㅞ, 겹받침은 COMPOSED로 있는 손모양 조각으로 나눠 보인다(fingerspellShapes).
 * 된소리는 예사소리 손모양을 거듭한다. 같은 그림 묶음의 ㅆ(ss.jpg)도 ㅅ 손모양 두 개로 그려져 있다.
 * w 이중모음은 두 모음을 이어서(ㅘ = ㅗ+ㅏ), 겹받침은 두 자음을 차례로(ㄺ = ㄹ+ㄱ) 짚는다. 없는 손모양을 새로
 * 그리지는 않는다. 숫자·기호 등은 여전히 텍스트 폴백.
 */
const JAMO_TO_ROMAN = {
  // 자음
  'ㄱ': 'g', 'ㄴ': 'n', 'ㄷ': 'd', 'ㄹ': 'r', 'ㅁ': 'm', 'ㅂ': 'b', 'ㅅ': 's',
  'ㅇ': 'ng', 'ㅈ': 'j', 'ㅊ': 'ch', 'ㅋ': 'k', 'ㅌ': 't', 'ㅍ': 'p', 'ㅎ': 'h', 'ㅆ': 'ss',
  // 모음
  'ㅏ': 'a', 'ㅐ': 'ae', 'ㅑ': 'ya', 'ㅒ': 'yae', 'ㅓ': 'eo', 'ㅔ': 'e', 'ㅕ': 'yeo', 'ㅖ': 'ye',
  'ㅗ': 'o', 'ㅛ': 'yo', 'ㅜ': 'u', 'ㅠ': 'yu', 'ㅡ': 'eu', 'ㅣ': 'i', 'ㅚ': 'oe', 'ㅟ': 'wi', 'ㅢ': 'ui',
}

/** 그림이 없는 자모 → 있는 손모양 조각과 설명. */
export const COMPOSED = {
  // 된소리: 예사소리 손모양을 거듭한다
  'ㄲ': { parts: ['ㄱ', 'ㄱ'], note: '된소리: ㄱ 손모양을 거듭' },
  'ㄸ': { parts: ['ㄷ', 'ㄷ'], note: '된소리: ㄷ 손모양을 거듭' },
  'ㅃ': { parts: ['ㅂ', 'ㅂ'], note: '된소리: ㅂ 손모양을 거듭' },
  'ㅉ': { parts: ['ㅈ', 'ㅈ'], note: '된소리: ㅈ 손모양을 거듭' },
  // w 이중모음: 두 모음을 이어서
  'ㅘ': { parts: ['ㅗ', 'ㅏ'], note: 'ㅗ에 이어 ㅏ' },
  'ㅙ': { parts: ['ㅗ', 'ㅐ'], note: 'ㅗ에 이어 ㅐ' },
  'ㅝ': { parts: ['ㅜ', 'ㅓ'], note: 'ㅜ에 이어 ㅓ' },
  'ㅞ': { parts: ['ㅜ', 'ㅔ'], note: 'ㅜ에 이어 ㅔ' },
  // 겹받침: 두 자음을 차례로
  'ㄳ': { parts: ['ㄱ', 'ㅅ'], note: '겹받침: ㄱ, ㅅ 차례로' },
  'ㄵ': { parts: ['ㄴ', 'ㅈ'], note: '겹받침: ㄴ, ㅈ 차례로' },
  'ㄶ': { parts: ['ㄴ', 'ㅎ'], note: '겹받침: ㄴ, ㅎ 차례로' },
  'ㄺ': { parts: ['ㄹ', 'ㄱ'], note: '겹받침: ㄹ, ㄱ 차례로' },
  'ㄻ': { parts: ['ㄹ', 'ㅁ'], note: '겹받침: ㄹ, ㅁ 차례로' },
  'ㄼ': { parts: ['ㄹ', 'ㅂ'], note: '겹받침: ㄹ, ㅂ 차례로' },
  'ㄽ': { parts: ['ㄹ', 'ㅅ'], note: '겹받침: ㄹ, ㅅ 차례로' },
  'ㄾ': { parts: ['ㄹ', 'ㅌ'], note: '겹받침: ㄹ, ㅌ 차례로' },
  'ㄿ': { parts: ['ㄹ', 'ㅍ'], note: '겹받침: ㄹ, ㅍ 차례로' },
  'ㅀ': { parts: ['ㄹ', 'ㅎ'], note: '겹받침: ㄹ, ㅎ 차례로' },
  'ㅄ': { parts: ['ㅂ', 'ㅅ'], note: '겹받침: ㅂ, ㅅ 차례로' },
}

/** 자모/문자의 손모양 이미지 경로. 없으면 null(텍스트 폴백). */
export function fingerspellImage(ch) {
  const r = JAMO_TO_ROMAN[ch]
  if (r) return `/fingerspell/${r}.jpg`                       // 한글 지문자
  if (/^[A-Za-z]$/.test(ch)) return `/fingerspell/latin/${ch.toUpperCase()}.svg`  // 국제(미국식) 지문자
  return null
}

/**
 * 자모 하나를 보일 손모양 조각들. 그림이 있으면 한 조각, 된소리·w 이중모음·겹받침은 COMPOSED의 조각들,
 * 그 밖(숫자·기호)은 src가 null인 한 조각(텍스트 폴백).
 * @returns {{ parts: {jamo: string, src: string|null}[], note: string }}
 */
export function fingerspellShapes(ch) {
  const src = fingerspellImage(ch)
  if (src) return { parts: [{ jamo: ch, src }], note: '' }
  const c = COMPOSED[ch]
  if (c) return { parts: c.parts.map((j) => ({ jamo: j, src: fingerspellImage(j) })), note: c.note }
  return { parts: [{ jamo: ch, src: null }], note: '' }
}
