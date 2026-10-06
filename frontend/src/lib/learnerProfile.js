// 학습자 정보 기반 기본값(커리큘럼 계획 2-6, 종합 계획 C6).
// 배치 전에 선택 질문 세 개(청력 손실 시기, 보청기·인공와우, 수어 사용)를 묻고, 답에 따라 화면 기본값을 정한다.
// 건강 정보는 민감정보라 서버 저장에는 별도 동의가 필요하다. 그래서 답은 이 기기의 localStorage에만 두고 서버로 보내지 않는다.
// 공용 기기에서 다른 계정에 섞이지 않게 계정마다 다른 키에 둔다. 저장소가 막혀 있으면 이 창에서만 기억한다.

export const ONSET_OPTIONS = [
  { value: 'early', label: '태어날 때나 어릴 때' },   // 선천·아동기
  { value: 'adult', label: '어른이 된 뒤' },          // 성인기
]
export const DEVICE_OPTIONS = [
  { value: 'hearing_aid', label: '보청기' },
  { value: 'cochlear_implant', label: '인공와우' },
  { value: 'none', label: '없음' },
]
export const SIGN_OPTIONS = [
  { value: 'yes', label: '써요' },
  { value: 'no', label: '안 써요' },
]

const ONSETS = new Set(ONSET_OPTIONS.map((o) => o.value))
const DEVICES = new Set(DEVICE_OPTIONS.map((o) => o.value))
const SIGNS = new Set(SIGN_OPTIONS.map((o) => o.value))

/** 저장·입력값을 알려진 값만 남긴 모양으로. 모르는 값·빈 답은 null(답하지 않음). '없음'은 다른 기기와 함께 고를 수 없다. */
export function normalizeAnswers(raw) {
  const r = raw && typeof raw === 'object' ? raw : {}
  const onset = ONSETS.has(r.onset) ? r.onset : null
  let devices = Array.isArray(r.devices) ? [...new Set(r.devices.filter((d) => DEVICES.has(d)))] : []
  if (devices.includes('none') && devices.length > 1) devices = devices.filter((d) => d !== 'none')
  devices.sort((a, b) => DEVICE_OPTIONS.findIndex((o) => o.value === a) - DEVICE_OPTIONS.findIndex((o) => o.value === b))
  const sign = SIGNS.has(r.sign) ? r.sign : null
  return { onset, devices, sign }
}

/** 기기 고르기 토글. '없음'을 고르면 다른 기기를 지우고, 기기를 고르면 '없음'을 지운다. */
export function toggleDevice(devices, value) {
  const cur = Array.isArray(devices) ? devices : []
  if (cur.includes(value)) return cur.filter((d) => d !== value)
  if (value === 'none') return ['none']
  return [...cur.filter((d) => d !== 'none'), value]
}

/** 답하지 않았을 때의 기본값(지금 앱 동작 그대로). */
export const BASE_DEFAULTS = Object.freeze({
  readingLoad: 'standard',   // 'reduced'면 읽기 부담을 줄인 보기(계획 3-4, 그림 보기 자료가 생기면 쓴다)
  shortHints: false,         // 안내·피드백을 첫 문장만 먼저 보이고 '더 보기'로 펼친다
  signView: false,           // 단어 레슨에서 수어 뜻을 바로 펼쳐 보인다
  speakFocus: [],            // 말하기에서 먼저 권할 영역('prosody' 운율 조절, 'fricative' ㅅ·ㅈ·ㅊ·ㅎ 소리)
  soundCondition: false,     // 소리 조건(계획 3-2)을 권할지. 소리 조건이 아직 없어 저장만 한다
})

/**
 * 답 → 기본값(계획 2-6의 설계 그대로, 순수 함수).
 *  - 선천·아동기 손실: 읽기 부담을 줄인 보기와 짧은 힌트
 *  - 성인기 손실: 말하기는 운율과 마찰음부터 추천(1-5)
 *  - 보청기·인공와우: 소리 조건 추천(3-2)
 *  - 수어 사용: 수어 보기 켜기
 * 답하지 않은 질문은 기본값을 바꾸지 않는다.
 */
export function learnerDefaults(answers) {
  const a = normalizeAnswers(answers)
  const early = a.onset === 'early'
  return {
    readingLoad: early ? 'reduced' : 'standard',
    shortHints: early,
    signView: a.sign === 'yes',
    speakFocus: a.onset === 'adult' ? ['prosody', 'fricative'] : [],
    soundCondition: a.devices.some((d) => d === 'hearing_aid' || d === 'cochlear_implant'),
  }
}

/** 하나라도 답했는가. */
export function hasAnswers(answers) {
  const a = normalizeAnswers(answers)
  return a.onset != null || a.devices.length > 0 || a.sign != null
}

/** 기본값을 사람이 읽는 줄로(온보딩 확인·프로필). 바뀐 것만. */
export function describeDefaults(d) {
  const out = []
  if (d.shortHints) out.push('설명은 첫 문장만 먼저 보여요. 더 읽으려면 \'더 보기\'를 눌러요.')
  if (d.readingLoad === 'reduced') out.push('글을 덜 읽는 그림 보기는 준비되면 먼저 켜 둘게요.')
  if (d.signView) out.push('단어를 틀리면 수어 뜻을 바로 펼쳐 보여요.')
  if (d.speakFocus.length) out.push('말하기는 운율 조절(크기·길이·높낮이)과 ㅅ·ㅈ·ㅊ·ㅎ 소리부터 연습해 보세요.')
  if (d.soundCondition) out.push('소리를 함께 듣는 연습이 생기면 먼저 권해 드릴게요.')
  return out
}

/** 첫 문장과 나머지(짧은 힌트). 문장 끝(. ! ?) 뒤 공백에서 한 번만 자른다. 한 문장이면 rest는 ''. */
export function splitFirstSentence(text) {
  const t = String(text ?? '').trim()
  const m = t.match(/^(.+?[.!?])\s+(\S[\s\S]*)$/)
  return m ? { first: m[1], rest: m[2] } : { first: t, rest: '' }
}

// ── 기기 저장(계정마다 키) ─────────────────────────────────────────────────
const KEY_PREFIX = 'liplab_learner_info:'
const memory = new Map()

export function storageKey(userKey) {
  return KEY_PREFIX + String(userKey ?? 'guest')
}

/** 저장된 답(정규화). 없으면 null. storage를 넘기면 그것을 쓴다(테스트용). */
export function loadAnswers(userKey, storage = globalThis.localStorage) {
  const k = storageKey(userKey)
  try {
    const raw = storage?.getItem(k)
    if (raw) return normalizeAnswers(JSON.parse(raw))
  } catch { /* 저장소 차단·깨진 값 */ }
  return memory.has(k) ? normalizeAnswers(memory.get(k)) : null
}

export function saveAnswers(userKey, answers, storage = globalThis.localStorage) {
  const k = storageKey(userKey)
  const a = normalizeAnswers(answers)
  memory.set(k, a)
  try { storage?.setItem(k, JSON.stringify(a)) } catch { /* 이 창에서만 기억 */ }
  return a
}

export function clearAnswers(userKey, storage = globalThis.localStorage) {
  const k = storageKey(userKey)
  memory.delete(k)
  try { storage?.removeItem(k) } catch { /* noop */ }
}
