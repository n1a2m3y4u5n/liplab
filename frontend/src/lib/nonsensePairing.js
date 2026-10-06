// 뜻 없는 말 짝 맞추기(C10, docs/nonsense-pairing.md)의 화면 쪽 순수 규칙. 목록·블록·기준은 서버(backend/nonsense_words.py)가 정한다.
// - 블록 안 시행 순서와 도형 자리는 목록·블록마다 정해진 씨앗으로 섞는다(같은 블록을 이어 하면 같은 순서, 블록마다 자리가 바뀌어
//   자리 대신 모양을 보게 한다).
// - 하루 학습 시간은 이 기기에서 쓴 시간을 날짜별로 더해 10분(서버 today.minutes)에서 멈춘다. 서버도 하루 시행 수 상한을 둔다.

export const HINT_MS = 1500        // 골격을 먼저 보여 주는 시간(골격 보고 블록)

/** 문자열 씨앗 → 0~1 난수 함수(mulberry32). */
export function seededRandom(seed) {
  let h = 1779033703 ^ String(seed).length
  for (const ch of String(seed)) {
    h = Math.imul(h ^ ch.charCodeAt(0), 3432918353)
    h = (h << 13) | (h >>> 19)
  }
  let a = h >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function seededShuffle(items, seed) {
  const out = [...items]
  const rnd = seededRandom(seed)
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rnd() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/** 이번 블록의 시행 순서: 블록 전체 순서를 정해 두고 아직 안 본 낱말만 그 순서대로. */
export function trialOrder(words, remaining, setId, block) {
  const left = new Set(remaining)
  return seededShuffle(words, `${setId}:${block}:order`).filter((w) => left.has(w))
}

/** 도형 자리(낱말 목록, 보인 순서). 한 블록 안에서는 고정, 블록마다 바뀐다. */
export function gridOrder(words, setId, block) {
  return seededShuffle(words, `${setId}:${block}:grid`)
}

/** 한국 날짜(YYYY-MM-DD). 서버의 '오늘'(KST)과 같은 날 경계. */
export function kstDay(now = new Date()) {
  return new Date(now.getTime() + 9 * 3600 * 1000).toISOString().slice(0, 10)
}

const KEY = 'liplab.nonsense.ms.'

/** 오늘 이 기기에서 쓴 시간(ms). 저장소를 못 쓰면 0. */
export function usedToday(storage, now = new Date()) {
  try {
    const v = Number(storage?.getItem(KEY + kstDay(now)))
    return Number.isFinite(v) && v > 0 ? v : 0
  } catch {
    return 0
  }
}

/** 오늘 쓴 시간을 저장(지난 날 기록은 지운다). */
export function saveUsedToday(storage, ms, now = new Date()) {
  try {
    const key = KEY + kstDay(now)
    for (let i = (storage?.length || 0) - 1; i >= 0; i -= 1) {
      const k = storage.key(i)
      if (k && k.startsWith(KEY) && k !== key) storage.removeItem(k)
    }
    storage?.setItem(key, String(Math.max(0, Math.round(ms))))
  } catch { /* 사생활 보호 창 등: 이번 회차 안에서만 센다 */ }
}

/** 하루 시간을 다 썼는지. */
export function timeUp(usedMs, minutes) {
  return usedMs >= minutes * 60 * 1000
}

/** 블록이 끝났을 때 보일 안내 문장. */
export function blockSummary({ hint, correct, size, setDone }) {
  if (setDone) return `확인에서 ${size}개를 모두 맞혔어요. 이 목록은 끝났어요.`
  if (hint) return `골격을 보며 ${size}개 가운데 ${correct}개를 맞혔어요. 이제 골격 없이 확인해요.`
  return `골격 없이 ${size}개 가운데 ${correct}개를 맞혔어요. 다시 골격을 보며 익혀요.`
}
