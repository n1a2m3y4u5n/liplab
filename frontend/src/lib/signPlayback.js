/**
 * 수어 패널 전체 재생 보조 함수(SignPanel).
 *
 * 예전에는 <video key={video_url}>라 같은 영상이 이어지면(예전 10,000 → 하나·영·영·영·영, 지금도 번호 0000이나 3.33)
 * React가 같은 요소를 그대로 두어 영상이 처음부터 다시 돌지 않고 onEnded도 다시 오지 않아 전체 재생이 멈췄다.
 * 키에 재생 차례(run)와 토큰 위치를 넣어, 토큰이 바뀔 때마다 새 요소로 처음부터 재생되게 한다.
 */

/** 무대 요소 키. 같은 영상이 연달아 나와도 위치가 달라 키가 다르고, 전체 재생을 다시 누르면(run 증가) 새로 시작한다. */
export function stageKey(run, index, token) {
  return `${run}:${index}:${token?.video_url || token?.type || ''}`
}

/** 전체 재생에서 다음 위치. 마지막이면 그 자리에 두고 done. */
export function nextIndex(index, length) {
  return index < length - 1 ? { index: index + 1, done: false } : { index, done: true }
}
