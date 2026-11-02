import { lazy } from 'react'

const MAX_REC_MS = 60000   // 녹음 한 번의 상한(끄는 걸 잊어도 메모리·업로드가 끝없이 커지지 않게)

// 녹음 뒤 지연 측정용 표시(개발자 도구 Performance, docs/scorer-stream-latency-2026-10.md 10절). 'speak:stop'부터 잰다
function speakMark(name, start = false) {
  try {
    if (typeof performance === 'undefined' || !performance.mark) return
    performance.mark(name)
    if (!start) performance.measure(`${name}-since-stop`, 'speak:stop', name)
  } catch { /* 'speak:stop' 표시가 없으면 건너뛴다 */ }
}

// 혀 위치 성도 단면(E-6) — 모음 결과를 열 때만 받는다(그림 코드와 윤곽 자료 모두 지연 로드)
const VocalTractVTL = lazy(() => import('../VocalTractVTL'))

/**
 * 말하기 연습 (발화 피드백) — 발화 레슨(핸드오프 §4-04). /learn/speaking 과 /review/speaking/session 이 같이 쓴다.
 * Figma: 말하기 전 175:21 · 녹음 중 175:49 · 결과 176:21 · 자세히 보기 182:21 · 결과(아쉬움) 186:21,
 *        모바일 236:34 · 237:34(lg 미만). 루트에 data-track="speak"를 달아 트랙색(버튼·진행률·단어 카드)이 분홍이 된다.
 *  1) 말하는 동안 볼륨·톤(피치)·파형 실시간 (Web Audio) — 귀 대신 눈.
 *  2) 녹음을 서버로 → Whisper 전사 + 기존 음운 채점 + Claude 코칭.
 * 점수·음소 칩 색은 lib/scoreTone(§3.2: 70 이상 초록 · 45~69 주황 · 45 미만 빨강).
 * 발성·운율 단계(지표 모드)는 Figma 프레임이 없어 결과 상세에 목소리 곡선·지표를 그대로 둔다.
 */

// Figma 발화 화면 에셋 — public/ui (닫기는 독화 레슨과 같은 91:12 Close)
const IC = {
  close: '/ui/lp-91-12-close.svg',
  mic: '/ui/speak-mic.svg',
  recording: '/ui/speak-recording.svg',   // 96×96(펄스 링 포함) — 72 슬롯에 -16.67%씩 넘친다(175:79)
  doka: '/ui/lp-303-32-doka.svg',         // 코칭 "DOKA의 한마디"(303:32)
}
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // DOKA SVG 그림자 여백(Figma inset)
// 레슨 시작 전 트랙 로딩(§4-10 223:50)을 최소 이만큼은 보인다 — 데이터가 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000
// 결과 바 버튼(176:71 / 모바일 237:80) — 데스크톱 28/15·16px, lg 미만은 반반 폭 r13·15px
const RESULT_BTN = 'btn-bar flex-1 max-lg:rounded-13 max-lg:px-0 max-lg:text-[15px] lg:flex-none lg:px-7 lg:text-[16px]'

// 캔버스·SVG에 쓸 토큰 색 — 루트(data-track="speak") 기준으로 CSS 변수를 읽는다.
const cssVar = (el, name) => (el ? getComputedStyle(el).getPropertyValue(name).trim() : '') || 'gray'

// /api/viseme 실패 안내(아바타만 멈추고 녹음·채점은 된다). 다음 문항에서 받으면 이 안내만 지운다.
const VISEME_ERR = '입모양 자료를 가져오지 못해 아바타가 움직이지 않아요. 녹음과 채점은 그대로 할 수 있어요.'

// 지표 모드 점수 이름: 서버가 드릴마다 다른 것을 잰다(backend/speak_curriculum.py _score_prosody).
// 발성(voicing)은 길이 60% + 크기 40%라 '길이·크기'로 따로 붙인다.
const PROSODY_SCORE_LABEL = { long: '길이', rise: '억양', fall: '억양', soft: '작게 말하기', loud: '크게 말하기' }

// AudioContext.close()는 이미 닫히는 중이면 거부된 약속을 돌려준다 → 삼켜서 처리되지 않은 거부를 막는다
const closeContext = (ac) => {
  if (!ac || ac.state === 'closed') return
  try { Promise.resolve(ac.close()).catch(() => {}) } catch { /* noop */ }
}

export { MAX_REC_MS, speakMark, VocalTractVTL, IC, OVERFLOW, INTRO_MS, RESULT_BTN, cssVar, VISEME_ERR, PROSODY_SCORE_LABEL, closeContext }
