/**
 * 분석 탭 '문장 점수 주 평균 추세' 카드(참고, 기계 전사 기준). 서버 GET /api/analysis/overview의 speak_trend
 * ({weeks: [{start, n, mean}], min_n, n})를 그래프용 값으로 바꾼다(backend/analytics.speak_sentence_weekly).
 *
 * 주마다 말하기 문장 단계 점수의 평균이다. 화자 단위로 보면 이 평균이 기계 전사 오류율과 같은 방향으로 움직였다는 근거(S20,
 * docs/speak-intelligibility-index-2026-10.md 10.4절)로 보이기만 하고, 합격·숙달 판정에는 쓰지 않는다. 문장이 min_n(5)개보다
 * 적은 주는 서버가 평균을 비워 보내므로 점을 두지 않는다. 화면에 '명료도'라는 말은 쓰지 않는다(사람 받아쓰기 라벨이 아직 없다).
 */
export const SPEAK_TREND_MIN_N = 5

/**
 * 반환: {show, enough, weeks: [{accuracy(0~1 | null), n}], shown(평균이 있는 주 수), minN, last(마지막 주 평균 | null), lastN}.
 * 예전 서버(speak_trend 없음)면 show false. 기록이 없거나 평균이 있는 주가 1주뿐이면 show는 true이고 enough가 false(카드는 짧은 빈 상태).
 */
export function speakTrendView(ov) {
  const t = ov?.speak_trend
  const weeks = Array.isArray(t?.weeks) ? t.weeks : []
  if (!weeks.length) return { show: false, enough: false, weeks: [], shown: 0, minN: SPEAK_TREND_MIN_N, last: null, lastN: 0 }
  const minN = Number(t.min_n) || SPEAK_TREND_MIN_N
  const pts = weeks.map((w) => {
    const n = Number(w?.n) || 0
    const m = w?.mean == null || n < minN ? null : Math.max(0, Math.min(100, Number(w.mean)))
    return { accuracy: m == null || !Number.isFinite(m) ? null : m / 100, n }
  })
  const lastW = pts[pts.length - 1]
  const shown = pts.filter((p) => p.accuracy != null).length
  return {
    show: true, enough: shown >= 2, weeks: pts, shown, minN,
    last: lastW.accuracy == null ? null : Math.round(lastW.accuracy * 100), lastN: lastW.n,
  }
}
