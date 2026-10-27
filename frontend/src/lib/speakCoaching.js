// 코칭만 다시 조회한다. 점수와 단계 진행도는 다시 제출하지 않는다.
export async function loadCoachingResult({ id, request, isCurrent, update }) {
  const apply = (patch) => {
    if (isCurrent()) update((a) => a && !a.error && a.coaching_id === id ? { ...a, ...patch } : a)
  }
  apply({ coaching_pending: true, coaching_error: null, coaching_retry: false })
  let patch
  try {
    const text = (await request(id))?.coaching
    patch = typeof text === 'string' && text.trim()
      ? { coaching: text, coaching_error: null, coaching_retry: false }
      : { coaching: null, coaching_error: '코칭 없음', coaching_retry: false }
  } catch (e) {
    const status = e?.response?.status
    const retry = !status || [408, 429, 502, 503, 504].includes(status)
    const message = status === 404
      ? '코칭 만료'
      : retry ? '수신 지연' : '코칭 실패'
    patch = { coaching: null, coaching_error: message, coaching_retry: retry }
  }
  apply({ ...patch, coaching_pending: false })
}
