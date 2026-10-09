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

/**
 * 활성 음성 레벨(ITU-T P.56 방법 B, Kabal 1999 설명과 VOICEBOX v_activlev를 따름). 앞뒤·사이 무음을 빼고 말소리가 있는 구간만으로
 * 크기를 구한다. 반환은 선형 RMS 등가값(전체 RMS와 같은 단위). HINT·Matrix 검사도 무음을 뺀 말소리 레벨로 SNR을 정한다.
 *  - 포락선: |x|를 시간 상수 0.03초 지수 평활 두 번, 유지 시간 0.2초
 *  - 문턱 c_j = 2^j(j = -15 … -1, 표본 크기 −1 ~ 1 기준), 문턱마다 A_j = (전체 에너지 / 활성 표본 수)의 dB와 문턱 레벨 C_j의
 *    차이가 15.9 dB가 되는 지점을 로그 축에서 선형 보간
 *  A_j의 분자는 신호 전체의 제곱합이다(G.191 sv-p56의 sqr_sum, v_activlev의 sxx). 예전에는 활성 표본의 제곱합만 써서 비활성 구간
 *  에너지(숨소리·잔잡음)만큼 낮게 나왔다(서버 음성 150개에서 평균 −0.19 dB, 최대 −0.91 dB, docs/review/listen-code-review-2026-10.md).
 *  활성 구간이 거의 없거나 교차점이 없으면 전체 RMS를 돌려준다.
 */
export function activeLevel(samples, sampleRate) {
  const n = samples?.length || 0
  if (!n || !(sampleRate > 0)) return 0
  const g = Math.exp(-1 / (sampleRate * 0.03))
  const hang = Math.ceil(0.2 * sampleRate)
  const J = 15
  const thr = Array.from({ length: J }, (_, k) => 2 ** (k - J))   // 2^-15 … 2^-1
  const count = new Float64Array(J)
  const last = new Float64Array(J).fill(-Infinity)   // 마지막으로 문턱을 넘은 표본 번호
  let p = 0
  let q = 0
  let total = 0
  for (let i = 0; i < n; i += 1) {
    const x = samples[i]
    total += x * x
    p = g * p + (1 - g) * Math.abs(x)
    q = g * q + (1 - g) * p
    for (let j = 0; j < J; j += 1) {
      if (q >= thr[j]) last[j] = i
      else if (i - last[j] > hang) continue
      count[j] += 1
    }
  }
  if (total === 0) return 0
  const plain = Math.sqrt(total / n)
  const M = 15.9
  let prev = null
  for (let j = 0; j < J; j += 1) {
    if (count[j] < sampleRate * 0.05) break   // 활성 구간 50ms 미만은 믿지 않는다
    const A = 10 * Math.log10(total / count[j])
    const C = 20 * Math.log10(thr[j])
    const d = A - C
    if (d <= M) {
      if (!prev) return Math.sqrt(total / count[j])
      const t = (prev.d - M) / (prev.d - d)          // 차이 축에서 M이 되는 비율
      return 10 ** ((prev.A + t * (A - prev.A)) / 20)
    }
    prev = { A, d }
  }
  return plain
}

/**
 * 개수 상한이 있는 캐시(가장 오래 안 쓴 것부터 버린다). 소리 듣기는 회기 하나에 문항마다 새 글을 받아 풀어 두므로(48 kHz 모노 2초면
 * 약 380 KB) 상한이 없으면 긴 회기에서 수백 개가 쌓여 저사양 폰의 메모리를 넘는다. get은 쓴 것으로 친다.
 */
export function createLru(max) {
  const m = new Map()
  const cap = Math.max(1, Math.floor(max) || 1)
  return {
    get(k) {
      if (!m.has(k)) return undefined
      const v = m.get(k)
      m.delete(k)
      m.set(k, v)
      return v
    },
    has: (k) => m.has(k),
    set(k, v) {
      m.delete(k)
      m.set(k, v)
      while (m.size > cap) m.delete(m.keys().next().value)
      return v
    },
    delete: (k) => m.delete(k),
    get size() { return m.size },
  }
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

const baseIndex = (n, k, slot, mode, block) => {
  const i = mode === 'blocked' ? (block || 0) + slot : (k || 0) + slot
  return ((i % n) + n) % n
}

/**
 * 문항 k의 훈련 목소리. slot은 소리 구별의 voice_pair 칸(0·1). mode 'blocked'면 묶음(block) 하나를 한 목소리로 내고(서툰 단계),
 * 'mixed'면 문항마다 돌린다. 서버 단계 응답의 voice_mode·voice_block을 넘긴다.
 * avoid는 문항의 avoid_voices(그 문항을 구별되게 내지 못한 목소리, docs/listen-voice-contrast-2026-10.md). 고른 목소리가 그 안에
 * 있으면 다음 목소리로 넘어가고(묶음 모드에서도 그 문항만), 모두 걸리면 원래 목소리를 쓴다.
 */
export function voiceFor(train, k, slot = 0, mode = 'mixed', block = 0, avoid = null) {
  const n = train?.length || 0
  if (!n) return ''
  const base = baseIndex(n, k, slot, mode, block)
  const skip = new Set(avoid || [])
  if (skip.size) {
    for (let j = 0; j < n; j += 1) {
      const v = train[(base + j) % n]
      if (!skip.has(v)) return v
    }
  }
  return train[base]
}

/**
 * 소리 구별 문항의 두 목소리 [첫 소리, 둘째 소리]. pair는 voice_pair. 두 칸이 다른 문항은 피할 목소리를 건너뛴 결과가 같은 목소리로
 * 겹치면 둘째 칸을 피할 목소리가 아닌 다른 목소리로 한 번 더 옮긴다(그런 목소리가 없으면 겹친 채로 둔다: 피하는 것이 먼저다).
 */
/** 짝을 구별되게 낼 수 있는 훈련 목소리(avoid_voices를 뺀 것). 모두 걸리면 전부를 돌려준다(소리 교실 목소리 칩·여러 목소리 듣기). */
export function usableVoices(train, avoid = null) {
  const list = train || []
  const skip = new Set(avoid || [])
  const ok = list.filter((v) => !skip.has(v))
  return ok.length ? ok : list
}

export function axVoices(train, k, pair, mode = 'mixed', block = 0, avoid = null) {
  const s0 = pair?.[0] || 0
  const s1 = pair?.[1] || 0
  const v1 = voiceFor(train, k, s0, mode, block, avoid)
  let v2 = voiceFor(train, k, s1, mode, block, avoid)
  const n = train?.length || 0
  if (s0 !== s1 && v2 === v1 && n > 1) {
    const skip = new Set(avoid || [])
    const base = baseIndex(n, k, s1, mode, block)
    for (let j = 1; j < n; j += 1) {
      const v = train[(base + j) % n]
      if (v !== v1 && !skip.has(v)) { v2 = v; break }
    }
  }
  return [v1, v2]
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

/**
 * 말과 소음의 크기 차이(SNR)를 학습자에게 보이는 말로. 연습 화면이라 dB 숫자는 숨기고 '조금'(5 dB 이하)·'훨씬'(6 dB 이상)으로 말한다
 * (docs/easy-korean-rebase-2026-10.md 8절). 숫자가 필요한 검사 결과는 listenView.fmtDb로 따로 보인다.
 */
export function snrLabel(db) {
  if (db == null || !Number.isFinite(Number(db))) return ''
  const v = Math.round(Number(db))
  if (v === 0) return '말과 소음이 같은 크기예요'
  const how = Math.abs(v) <= 5 ? '조금' : '훨씬'
  return v > 0 ? `말이 소음보다 ${how} 커요` : `소음이 말보다 ${how} 커요`
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
    return { gainDb: clampGainDb(s.gainDb), device: s.device || 'unknown', route: s.route || 'speaker', at: s.at || null,
      ...(s.sim === 'ci' ? { sim: 'ci' } : {}) }
  } catch { return null }
}

export function writeSettings(s, storage) {
  try {
    (storage || globalThis.localStorage)?.setItem(SETTINGS_KEY, JSON.stringify({ ...s, gainDb: clampGainDb(s.gainDb) }))
    return true
  } catch { return false }
}
