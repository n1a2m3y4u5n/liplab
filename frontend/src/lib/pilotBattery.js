// 청인 예비 파일럿(P3) 검사 묶음 화면의 순수 함수(docs/pilot/battery.md). 문항·배정·채점·SNR 계단은 서버(backend/pilot_battery.py)가 맡고,
// 여기서는 화면에서만 필요한 계산을 둔다: 기기·렌더링 요약, 잡음 이득, 무의미 낱말 음절 조립, 재생·답 가능 여부, 반응 시간.
import { renderTimingSummary } from './frameClock.js'

export const LAYER_LABEL = {
  nonsense: '무의미 낱말 자음',
  word: '실제 얼굴 낱말',
  sentence: '개방형 문장',
  snr: 'SNR 맞추기',
  av: '소음 속 문장',
}

// 못 낸 까닭(서버 item_ready)의 화면 문구
export const MISSING_LABEL = {
  media: '영상 준비 전',
  text: '문장 미정',
  noise: '잡음 파일 준비 전',
  snr: 'SNR 미정',
}

/** 화면 크기 기준 거친 기기 분류(지문으로 쓸 만한 정보는 모으지 않는다). */
export function deviceClass(w, h, touch) {
  const short = Math.min(Number(w) || 0, Number(h) || 0)
  if (touch && short < 600) return 'phone'
  if (touch && short < 1100) return 'tablet'
  return 'desktop'
}

/** 사용자 에이전트에서 계열만(판 번호·기기 이름은 버린다). */
export function uaFamilies(ua = '') {
  const s = String(ua)
  const os = /iPhone|iPad|iPod/.test(s) ? 'ios'
    : /Android/.test(s) ? 'android'
      : /CrOS/.test(s) ? 'chromeos'
        : /Windows/.test(s) ? 'windows'
          : /Mac OS X|Macintosh/.test(s) ? 'mac'
            : /Linux/.test(s) ? 'linux' : 'other'
  const browser = /SamsungBrowser/.test(s) ? 'samsung'
    : /Edg\//.test(s) ? 'edge'
      : /Firefox\/|FxiOS/.test(s) ? 'firefox'
        : /Chrome\/|CriOS/.test(s) ? 'chrome'
          : /Safari\//.test(s) ? 'safari' : 'other'
  return { os_family: os, browser_family: browser }
}

/** WebGL을 쓸 수 있는지(아바타 3D가 2D 대체로 바뀌는지 기록용). 렌더러 문자열은 읽지 않는다. */
export function hasWebGL(doc = typeof document !== 'undefined' ? document : null) {
  try {
    const c = doc?.createElement('canvas')
    return !!(c && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch { return false }
}

/** 기기 요약: 화면·창 크기, 화소 비율, 기기 분류, OS·브라우저 계열. */
export function deviceInfo(win = typeof window !== 'undefined' ? window : null) {
  if (!win) return {}
  const sw = win.screen?.width || 0
  const sh = win.screen?.height || 0
  const touch = (win.navigator?.maxTouchPoints || 0) > 0
  return {
    screen_w: sw, screen_h: sh,
    viewport_w: win.innerWidth || 0, viewport_h: win.innerHeight || 0,
    dpr: Math.round((win.devicePixelRatio || 1) * 100) / 100,
    device_class: deviceClass(sw, sh, touch),
    ...uaFamilies(win.navigator?.userAgent || ''),
  }
}

/** 영상 재생 품질 누적(getVideoPlaybackQuality). 문항마다 더해 층 끝에 요약한다. */
export function addVideoQuality(acc, q) {
  const total = (acc?.total || 0) + (Number(q?.totalVideoFrames) || 0)
  const dropped = (acc?.dropped || 0) + (Number(q?.droppedVideoFrames) || 0)
  return { total, dropped }
}

/** 서버에 보낼 기기·렌더링 요약(backend pilot_battery.clean_render_log와 같은 키). */
export function buildRenderLog({ timing = renderTimingSummary(), video = null, device = deviceInfo(), renderMode = null, webgl = null, scope = 'layer' } = {}) {
  const out = {
    scope,
    frames: timing?.frames ?? 0,
    mean_late_ms: timing?.meanLateMs ?? 0,
    max_late_ms: timing?.maxLateMs ?? 0,
    over20_rate: timing?.over20Rate ?? 0,
    over50_rate: timing?.over50Rate ?? 0,
    ...device,
  }
  if (renderMode) out.render_mode = renderMode
  if (typeof webgl === 'boolean') out.webgl = webgl
  if (video && video.total > 0) {
    out.video_total_frames = video.total
    out.video_dropped_frames = video.dropped
    out.video_drop_rate = Math.round((video.dropped / video.total) * 10000) / 10000
  }
  return out
}

/** 잡음 이득(선형). 서버 pilot_battery.noise_gain과 같은 식: 말소리는 그대로, 잡음을 (말소리 − SNR) dB에 맞춘다. */
export function noiseGain(speechRmsDbfs, noiseRmsDbfs, snrDb) {
  return 10 ** ((speechRmsDbfs - snrDb - noiseRmsDbfs) / 20)
}

/** 표본 배열의 RMS(dBFS). 잡음 파일 크기를 브라우저에서 잰다. 무음이면 -Infinity. */
export function rmsDbfs(samples) {
  const n = samples?.length || 0
  if (!n) return -Infinity
  let sum = 0
  for (let i = 0; i < n; i += 1) sum += samples[i] * samples[i]
  const rms = Math.sqrt(sum / n)
  return rms > 0 ? 20 * Math.log10(rms) : -Infinity
}

const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
const JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ',
  'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

/** 초성·중성(·종성) → 음절. 초성이 없으면 무음 ㅇ으로 채워 모음 자리를 보인다. */
export function composeSyllable(cho, jung, jong = '') {
  const c = CHO.indexOf(cho || 'ㅇ')
  const v = JUNG.indexOf(jung)
  const t = JONG.indexOf(jong || '')
  if (c < 0 || v < 0 || t < 0) return ''
  return String.fromCharCode(0xAC00 + (c * 21 + v) * 28 + t)
}

/** 무의미 낱말 답 미리보기: 고른 자음으로 음절을 조립하고, 안 고른 자리는 '_'로 둔다(모음은 화면에 보인다).
 *  예: 모음 ㅏ·ㅗ, 아무것도 안 고름 → '_ㅏ_ㅗ_', ㅂ·ㄹ·ㄱ → '바록', ㅂ과 ㄱ만 → '바_ㅗㄱ'. */
export function nonsensePreview(vowels = [], chosen = [null, null, null]) {
  const [v1 = '', v2 = ''] = vowels
  const [c1, c2, c3] = chosen
  const s1 = c1 ? composeSyllable(c1, v1) : `_${v1}`
  const s2 = c2 ? (composeSyllable(c2, v2, c3 || '') + (c3 ? '' : '_')) : `_${v2}${c3 || '_'}`
  return s1 + s2
}

/** 문항 재생 상태 → 다시 볼 수 있는지와 답할 수 있는지. 답은 첫 재생이 끝난 뒤에만, 재생은 maxPlays번까지. */
export function playState({ plays = 0, playing = false, firstEndedAt = null, maxPlays = 2 }) {
  return {
    canPlay: !playing && plays < maxPlays,
    canAnswer: firstEndedAt != null,
    left: Math.max(0, maxPlays - plays),
  }
}

/** 반응 시간(ms, 정수). rt_ms는 첫 재생이 끝난 때부터, rt_from_onset_ms는 첫 재생이 시작한 때부터 답 확정까지. */
export function reactionTimes({ firstOnsetAt, firstEndedAt, answeredAt }) {
  const d = (a) => (Number.isFinite(a) && Number.isFinite(answeredAt) ? Math.max(0, Math.round(answeredAt - a)) : null)
  return { rt_ms: d(firstEndedAt), rt_from_onset_ms: d(firstOnsetAt) }
}

/** 층 진행: 남은 문항(준비됐고 아직 안 푼 것)과 준비 전 문항 수. 서버가 준 제시 순서를 그대로 쓴다. */
export function queueOf(items = []) {
  const ready = items.filter((it) => it.ready)
  return {
    todo: ready.filter((it) => !it.answered),
    nReady: ready.length,
    nDone: ready.filter((it) => it.answered).length,
    missing: items.filter((it) => !it.ready),
  }
}
