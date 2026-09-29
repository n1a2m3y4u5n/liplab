// 1단계 '같은지 다른지'(AX) 문항(docs/mastery-ewma.md 11절, A0(2)). 아바타가 받침 없는 음절 둘을 차례로 말하고 학습자는 '같아요'·
// '달라요' 큰 버튼 가운데 하나를 누른다(글을 읽지 않는다). 레슨 7~12번 가운데 2자리에 나오고(입 안쪽 짝 1, 보이는 짝 1), 답은 시행
// 기록과 XP에만 남고 1단계 숙달에는 들어가지 않는다(사전 등록 설계 A1은 거짓 숙달이 늘어 탈락, A0(2)는 사후 탐색 뒤 시드 1에서 확인).
// 짝 규칙·정답·제외는 backend/curriculum.py ax_pair와 같다. 서버가 정답을 다시 정하므로 여기 정답은 화면 설명용이다.
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS } from './visemeShapes.js'
import { TALKERS, DEFAULT_TALKER, scaleShape } from './talkers.js'
import { VISEME_PLAIN } from './visemeLabels.js'

// 자리별 [입모양 무리(null = 첫소리 없음), 엔진 프레임 길이 ms](engine.DURATION_MAP)
export const AX_ONSETS = {
  'ㅇ': [null, 0], 'ㅂ': [1, 110], 'ㅁ': [1, 120], 'ㅍ': [1, 150],
  'ㄷ': [6, 110], 'ㄴ': [6, 120], 'ㅅ': [6, 110], 'ㅌ': [6, 150],
  'ㄱ': [7, 110], 'ㅋ': [7, 150], 'ㅎ': [8, 150], 'ㅈ': [10, 110], 'ㅊ': [10, 150],
}
export const AX_VOWELS = {
  'ㅏ': [2, 180], 'ㅐ': [2, 150], 'ㅣ': [3, 150], 'ㅔ': [3, 150],
  'ㅗ': [4, 180], 'ㅜ': [4, 180], 'ㅓ': [5, 150], 'ㅡ': [5, 150],
}
export const AX_CONSONANT_CONTEXT = ['ㅏ', 'ㅣ', 'ㅗ']   // 자음 짝의 공통 모음
export const AX_VOWEL_CONTEXT = ['ㅇ', 'ㅂ']            // 모음 짝의 공통 초성
export const AX_INSIDE = new Set([6, 7, 8, 10])
// 같은 부류인데 한 화자라도 이 거리 이상이면 '같음'으로 내지 않는다(visemeOptions.MIN_SHAPE_DISTANCE와 같은 값)
export const AX_SAME_MAX_DIST = 0.2
// 다른 부류인데 한 화자라도 이 거리 미만이면 '다름'으로 내지 않는다(차례로 보는 두 모양이라 동시 비교보다 여유를 둔다)
export const AX_DIFF_MIN_DIST = 0.3
export const AX_SAME_MAX_MS_DIFF = 10
// 위 거리 기준으로 뺀 무리 짝(null = 첫소리 없음). backend/curriculum.py AX_EXCLUDED_GROUP_PAIRS와 같아야 한다(test_viseme_ax)
export const AX_EXCLUDED_GROUP_PAIRS = [[6, 10], [7, 10], [8, 10], [null, 6], [null, 7], [null, 8], [null, 10], [2, 5]]

const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'.split('')
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'.split('')
const compose = (o, v) => String.fromCharCode(0xac00 + CHO.indexOf(o) * 588 + JUNG.indexOf(v) * 28)
const split = (syl) => {
  if (typeof syl !== 'string' || syl.length !== 1) return null
  const c = syl.charCodeAt(0) - 0xac00
  if (c < 0 || c > 11171 || c % 28) return null
  return [CHO[Math.floor(c / 588)], JUNG[Math.floor((c % 588) / 28)]]
}
const cls = (g) => (g == null ? 'none' : AX_INSIDE.has(g) ? 'inside' : String(g))
const pairKey = (a, b) => [a, b].map((g) => (g == null ? 'n' : g)).sort().join('|')
const EXCLUDED = new Set(AX_EXCLUDED_GROUP_PAIRS.map(([a, b]) => pairKey(a, b)))

const vec = (shape) => ACTIVE_MORPH_KEYS.map((k) => shape[k] || 0)
/** 두 무리(null = 중립 입모양 15) 입모양 거리의 [최소, 최대]. 기본 화자와 가상 화자 6명(talkers.test.mjs와 같은 공간). */
export function groupDistanceRange(ga, gb) {
  const ds = [DEFAULT_TALKER, ...TALKERS].map((t) => {
    const A = vec(scaleShape(VISEME_BLENDSHAPES[ga ?? 15], t, ga ?? 15))
    const B = vec(scaleShape(VISEME_BLENDSHAPES[gb ?? 15], t, gb ?? 15))
    return Math.hypot(...A.map((x, i) => x - B[i]))
  })
  return [Math.min(...ds), Math.max(...ds)]
}

/** 거리 기준으로 애매한 무리 짝인가(같은 부류인데 멀거나, 다른 부류인데 가까움). */
export function ambiguousGroups(ga, gb) {
  if (ga === gb) return false
  const [lo, hi] = groupDistanceRange(ga, gb)
  return cls(ga) === cls(gb) ? hi >= AX_SAME_MAX_DIST : lo < AX_DIFF_MIN_DIST
}

/** AX 짝 판정(backend ax_pair와 같은 규칙). 내지 않는 짝이면 null. */
export function axPair(a, b) {
  const sa = split(a)
  const sb = split(b)
  if (!sa || !sb || (sa[0] === sb[0] && sa[1] === sb[1])) return null
  const [oa, va] = sa
  const [ob, vb] = sb
  if (!(oa in AX_ONSETS) || !(ob in AX_ONSETS) || !(va in AX_VOWELS) || !(vb in AX_VOWELS)) return null
  let slot
  let A
  let B
  if (va === vb && AX_CONSONANT_CONTEXT.includes(va)) [slot, A, B] = ['onset', AX_ONSETS[oa], AX_ONSETS[ob]]
  else if (oa === ob && AX_VOWEL_CONTEXT.includes(oa)) [slot, A, B] = ['vowel', AX_VOWELS[va], AX_VOWELS[vb]]
  else return null
  const [ga, ma] = A
  const [gb, mb] = B
  if (ga !== gb && EXCLUDED.has(pairKey(ga, gb))) return null
  const same = cls(ga) === cls(gb)
  if (same && Math.abs(ma - mb) > AX_SAME_MAX_MS_DIFF) return null
  return { a, b, same, inside: AX_INSIDE.has(ga) || AX_INSIDE.has(gb), slot, groups: [ga, gb] }
}

/** 자리 규칙으로 만들 수 있는 모든 짝(제외 전). backend ax_candidates와 같은 순서. */
export function axCandidates() {
  const ons = Object.keys(AX_ONSETS)
  const vows = Object.keys(AX_VOWELS)
  const out = []
  for (const v of AX_CONSONANT_CONTEXT) {
    for (let i = 0; i < ons.length; i++) for (let j = i + 1; j < ons.length; j++) out.push([compose(ons[i], v), compose(ons[j], v)])
  }
  for (const o of AX_VOWEL_CONTEXT) {
    for (let i = 0; i < vows.length; i++) for (let j = i + 1; j < vows.length; j++) out.push([compose(o, vows[i]), compose(o, vows[j])])
  }
  return out
}

/** 낼 수 있는 짝 전체. */
export const AX_PAIRS = axCandidates().map(([a, b]) => axPair(a, b)).filter(Boolean)

const pick = (list, random) => list[Math.floor(random() * list.length)]

/** 한 레슨의 AX 문항 2개: 입 안쪽 짝 1, 보이는 짝 1. 각각 같음·다름 반반, 두 음절 순서도 무작위. 순서는 섞는다. */
export function pickAxItems(random = Math.random) {
  const one = (inside) => {
    const same = random() < 0.5
    const p = pick(AX_PAIRS.filter((x) => x.inside === inside && x.same === same), random)
    return random() < 0.5 ? p : { ...p, a: p.b, b: p.a, groups: [p.groups[1], p.groups[0]] }
  }
  const items = [one(true), one(false)]
  return random() < 0.5 ? items : [items[1], items[0]]
}

/** 레슨(n문항, 1부터 센 번호)에서 AX가 나올 번호 k개. 첫 바퀴(1~first) 뒤 번호 가운데 무작위. */
export function axSlots(n = 12, first = 6, k = 2, random = Math.random) {
  const rest = Array.from({ length: n - first }, (_, i) => first + 1 + i)
  return new Set(rest.map((q) => [random(), q]).sort((x, y) => x[0] - y[0]).slice(0, k).map(([, q]) => q))
}

// 자리 한 칸의 겉모습(설명 문구). 모음·입술은 쉬운 이름, 첫소리 없음은 입술이 닫히지 않음.
const slotLook = (g) => (g == null ? '입술 안 닫힘' : VISEME_PLAIN[g]?.look || '')

/** 결과 설명. 입 안쪽 '같음' 짝은 1단계가 가르치는 '안 보이는 소리는 같아 보인다'를 여기서 짚는다. */
export function axExplain(p) {
  if (!p) return ''
  if (p.same && p.inside) return '두 소리는 입 안에서 나서 입모양이 거의 같아요. 문맥으로 가려요.'
  if (p.same) {
    return p.slot === 'onset'
      ? '두 소리 모두 입술이 닫혀 입모양이 같아요. 문맥으로 가려요.'
      : `「${p.a}」와 「${p.b}」는 입모양이 같아요. 문맥으로 가려요.`
  }
  if (p.inside) {
    // 입 안쪽 '다름' 짝은 늘 입 안쪽 대 입술 닫힘이다(첫소리 없음·경구개 짝은 제외 목록)
    const inA = AX_INSIDE.has(p.groups[0])
    const inner = inA ? p.a : p.b
    const outer = inA ? p.b : p.a
    return `「${outer}」는 입술이 닫혀 보이고, 「${inner}」는 입 안에서 나서 입모양이 거의 없어요.`
  }
  return `입모양이 달라요. 「${p.a}」 ${slotLook(p.groups[0])}, 「${p.b}」 ${slotLook(p.groups[1])}.`
}

/** 두 음절 프레임을 이어 붙인다(사이 중립 쉼). MouthAvatar가 끝에서 잠깐 쉬고 처음부터 되풀이한다. */
export function axFrames(framesA, framesB, gapMs = 600) {
  return [...(framesA || []), { viseme: 15, duration_ms: gapMs, transition_ms: 150 }, ...(framesB || [])]
}
