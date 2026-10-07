/**
 * 소리 듣기(청능훈련) 트랙의 순수 계산(Web Audio 없이 테스트한다). 재생은 lib/listenAudio.js.
 *
 * 크기 원칙: 말과 소음을 합친 전체 크기를 학습자가 맞춘 '편안한 크기'에 고정하고, SNR은 둘의 비율만 바꾼다.
 * 소음이 커질수록(SNR이 낮을수록) 전체 소리가 커지는 방식은 쓰지 않는다(docs/auditory-training-evidence-2026-10.md 안전 절).
 */

// 기준 크기(dBFS RMS). 편안한 크기 조절값(gainDb, -30 ~ 0)을 더한 것이 전체 출력 크기다. 0을 넘기지 않는다.
export const REF_DBFS = -20
export const GAIN_MIN_DB = -30
export const GAIN_MAX_DB = 0

export function clampGainDb(v) {
  const x = Number(v)
  if (!Number.isFinite(x)) return -10
  return Math.min(GAIN_MAX_DB, Math.max(GAIN_MIN_DB, Math.round(x)))
}

const amp = (db) => 10 ** (db / 20)

/** 말·소음 각각의 목표 RMS(선형). snrDb가 null이면 소음 없이 말만 전체 크기로. 둘을 더한 전력은 늘 같다. */
export function mixLevels(gainDb, snrDb = null) {
  const total = amp(REF_DBFS + clampGainDb(gainDb))
  if (snrDb == null || !Number.isFinite(Number(snrDb))) return { speech: total, noise: 0 }
  const r = 10 ** (Number(snrDb) / 10)       // 말 전력 / 소음 전력
  return { speech: total * Math.sqrt(r / (1 + r)), noise: total * Math.sqrt(1 / (1 + r)) }
}

/** 소리 원본 RMS(선형)를 목표 RMS로 맞추는 이득. 원본이 무음이면 0. */
export function gainFor(targetRms, sourceRms) {
  return sourceRms > 0 ? targetRms / sourceRms : 0
}

export function rmsOf(samples) {
  const n = samples?.length || 0
  if (!n) return 0
  let sum = 0
  for (let i = 0; i < n; i += 1) sum += samples[i] * samples[i]
  return Math.sqrt(sum / n)
}

/** 소리 원본 고르기: 브라우저가 풀 수 있는 첫 형식(canPlay(type)이 '' 아님). ogg/opus를 못 푸는 Safari는 m4a로 간다. */
export function pickSource(sources, canPlay) {
  const list = Array.isArray(sources) ? sources : []
  const ok = list.filter((s) => s?.url && canPlay(s.type || ''))
  const best = ok.find((s) => canPlay(s.type) === 'probably') || ok[0]
  return best ? best.url : null
}

/**
 * 목소리 역할. 목소리가 셋 이상이면 마지막 하나는 검사에만 쓰고(훈련에서 들은 적 없는 목소리로 역치를 측정한다)
 * 나머지로 훈련한다. 둘 이하면 모두 훈련·검사에 같이 쓴다.
 */
export function voiceRoles(voices) {
  const ids = (voices || []).map((v) => (typeof v === 'string' ? v : v?.id)).filter((v) => v != null)
  if (ids.length === 0) return { train: [''], test: '' }
  if (ids.length >= 3) return { train: ids.slice(0, -1), test: ids[ids.length - 1] }
  return { train: ids, test: ids[ids.length - 1] }
}

/** 문항 k의 훈련 목소리(목소리를 돌려 가며). slot은 소리 구별의 voice_pair 칸(0·1). */
export function voiceFor(train, k, slot = 0) {
  const n = train?.length || 0
  if (!n) return ''
  return train[(k + slot) % n]
}

/**
 * 입모양 프레임을 소리 길이에 맞춘다(소리+입모양 조건). syllables([{i, t0, t1}] ms, 소리 정렬)가 있으면 음절마다 그 구간에
 * 프레임을 나눠 넣고, 없으면 전체 길이 비율로 늘이고 줄인다. 반환: 새 프레임 배열(duration_ms·transition_ms 비례 조정).
 */
export function fitFramesToAudio(frames, durationMs, syllables = null) {
  const fs = (frames || []).filter((f) => f && Number.isFinite(f.duration_ms))
  if (!fs.length || !(durationMs > 0)) return fs
  if (Array.isArray(syllables) && syllables.length) {
    const span = new Map(syllables.map((s) => [s.i, s]))
    const byIdx = new Map()
    fs.forEach((f) => {
      if (!Number.isInteger(f.text_index) || !span.has(f.text_index)) return
      if (!byIdx.has(f.text_index)) byIdx.set(f.text_index, [])
      byIdx.get(f.text_index).push(f)
    })
    if (byIdx.size === span.size) {
      const out = []
      let t = 0
      const first = syllables[0].t0
      if (first > 40) { out.push({ viseme: 15, duration_ms: first, transition_ms: Math.min(120, first) }); t = first }
      for (const s of syllables) {
        if (s.t0 > t + 40) { out.push({ viseme: 15, duration_ms: s.t0 - t, transition_ms: 80 }); t = s.t0 }
        const group = byIdx.get(s.i)
        const sum = group.reduce((a, f) => a + f.duration_ms, 0) || 1
        const len = Math.max(40, s.t1 - t)
        group.forEach((f) => {
          const d = (f.duration_ms / sum) * len
          out.push({ ...f, duration_ms: d, transition_ms: Number.isFinite(f.transition_ms) ? Math.min(f.transition_ms, d * 0.6) : f.transition_ms })
        })
        t = s.t1
      }
      return out
    }
  }
  const sum = fs.reduce((a, f) => a + f.duration_ms, 0)
  const k = durationMs / sum
  return fs.map((f) => ({ ...f, duration_ms: f.duration_ms * k,
    transition_ms: Number.isFinite(f.transition_ms) ? f.transition_ms * k : f.transition_ms }))
}

/** SNR을 학습자에게 보이는 말로. */
export function snrLabel(db) {
  if (db == null || !Number.isFinite(Number(db))) return ''
  const v = Math.round(Number(db))
  if (v > 0) return `말이 소음보다 ${v} dB 커요`
  if (v < 0) return `소음이 말보다 ${-v} dB 커요`
  return '말과 소음이 같은 크기예요'
}

/** 낱말 대비(서버 contrast_of) → 설명 한 줄. */
export function contrastText(contrast) {
  const c = (contrast || [])[0]
  if (!c) return ''
  const where = c.slot === 'onset' ? '첫소리' : c.slot === 'vowel' ? '모음' : '받침'
  const show = (x) => (x === '-' ? '없음' : x)
  return `${c.syllable + 1}번째 음절의 ${where} ${show(c.target)}을(를) ${show(c.heard)}(으)로 들었어요`
}

// 기기·듣는 길(설정 화면). 기록에는 route만 남는다(데이터 품질용, 개인정보는 기기에만)
export const DEVICES = [
  { key: 'ha', label: '보청기' }, { key: 'ci', label: '인공와우' }, { key: 'bimodal', label: '보청기 + 인공와우' },
  { key: 'none', label: '기기 없이' }, { key: 'unknown', label: '잘 모르겠어요' },
]
export const ROUTES = [
  { key: 'stream', label: '기기로 바로(블루투스 등)' }, { key: 'earphone', label: '이어폰·헤드폰' }, { key: 'speaker', label: '스피커' },
]
const SETTINGS_KEY = 'liplab_listen_settings'

export function readSettings(storage) {
  try {
    const raw = (storage || globalThis.localStorage)?.getItem(SETTINGS_KEY)
    if (!raw) return null
    const s = JSON.parse(raw)
    if (!s || typeof s !== 'object') return null
    return { gainDb: clampGainDb(s.gainDb), device: s.device || 'unknown', route: s.route || 'speaker', at: s.at || null }
  } catch { return null }
}

export function writeSettings(s, storage) {
  try {
    (storage || globalThis.localStorage)?.setItem(SETTINGS_KEY, JSON.stringify({ ...s, gainDb: clampGainDb(s.gainDb) }))
    return true
  } catch { return false }
}
