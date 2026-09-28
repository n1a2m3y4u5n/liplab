// 발성·운율(지표 모드) 결과 문구. 합격 판정은 서버(backend/speak_curriculum.py)가 드릴마다 다른 기준으로 한다.
// 예전에는 결과 바 부제가 드릴과 상관없이 크기 40 기준의 안내라, '작게' 합격(크기 12~45) 중 12~39(정수 34개 중 28개)가
// '잘했어요!'와 '목소리가 작아요… 더 크게'를 함께 받았다. 또 응답 전에는 크기만 보고 '잘했어요!'를 먼저 띄워, '크게' 50이나
// 짧게 끊긴 '길게'는 서버 불합격으로 뒤집혔다.

export const SOFT_BAND = [12, 45]   // 운율 '작게' 합격 구간(서버 _score_prosody와 같다)

/** 크기(0~100) → 녹음 루프 RMS. SpeakingPractice computeSummary의 크기 = (유성 평균 RMS − 0.01) / 0.13 × 100의 역(40 → 0.062). */
export const loudnessRms = (loudness) => 0.01 + (loudness / 100) * 0.13

/** 크기 안내 한 문장과 적정 여부. '작게' 연습은 목표 구간(12~45)으로 보고, 다른 연습은 예전 그대로(40 미만이면 '더 크게'). */
export function volumeFeedback(loudness, peak, drill) {
  if (peak < 0.008) {
    return { volMsg: '마이크 소리가 거의 안 잡혔어요. 권한/연결을 확인하고 가까이서 말해보세요.', volOk: false, micIssue: true }
  }
  if (drill === 'soft') {
    const [lo, hi] = SOFT_BAND
    if (loudness > hi) return { volMsg: `조금 컸어요(크기 ${loudness}/100). 더 작게, 속삭이듯 말해 보세요.`, volOk: false, micIssue: false }
    if (loudness < lo) return { volMsg: `소리가 거의 없어요(크기 ${loudness}/100). 살짝만 소리 내 보세요.`, volOk: false, micIssue: false }
    return { volMsg: `작게 잘 냈어요(크기 ${loudness}/100).`, volOk: true, micIssue: false }
  }
  if (loudness < 40) return { volMsg: `목소리가 작아요(크기 ${loudness}/100). 배에 힘을 주고 더 크게 말해보세요.`, volOk: false, micIssue: false }
  if (loudness > 92) return { volMsg: `조금 컸어요(크기 ${loudness}/100). 편하게 낮춰도 괜찮아요.`, volOk: true, micIssue: false }
  return { volMsg: `볼륨 적당해요(크기 ${loudness}/100). 좋아요!`, volOk: true, micIssue: false }
}

/** 지표 모드 결과 바 {good, title, sub}. 서버 판정이 오면 그 합격 여부와 note를 쓰고, 오는 중이면 판정하지 않는다(good null).
 * 서버 결과가 없을 때(요청을 보내지 않았거나 실패)만 화면에서 잰 값(localGood·volMsg)으로 보인다. */
export function metricVerdict({ assessment, assessing, summary, localGood }) {
  if (assessment && !assessment.error) {
    const good = assessment.passed ?? (assessment.score >= 65)
    return { good, title: good ? '잘했어요!' : '조금 더 연습해요',
      sub: assessment.note || (good ? '잘 전달됐어요' : '소리가 잘 전달되지 않았어요') }
  }
  if (assessing) return { good: null, title: '분석 중…', sub: '목소리를 분석하고 있어요' }
  if (!summary) return { good: null, title: '', sub: '' }
  const good = !!localGood
  return { good, title: good ? '잘했어요!' : '조금 더 연습해요',
    sub: good || summary.volOk === false ? summary.volMsg : '소리가 잘 전달되지 않았어요' }
}

/** 목소리 곡선 그래프 아래 크기 안내. 적정이면 null. '작게' 연습은 목표 구간 기준이라 '더 크게'를 내지 않는다. */
export function volumeCurveNote(summary, drill) {
  if (!summary || summary.micIssue || summary.volOk !== false) return null
  if (drill === 'soft') {
    return summary.loudness > SOFT_BAND[1]
      ? '크기 곡선이 목표 구간 위로 올라갔어요 → 더 작게, 속삭이듯.'
      : '크기 곡선이 목표 구간 아래예요 → 살짝만 소리 내 보세요.'
  }
  return '크기 곡선이 적정선 아래로 자주 내려갔어요 → 배에 힘을 주고 더 크게.'
}
