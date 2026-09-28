/**
 * 같은 요청·로드를 한 번만 하는 약속 도우미. api.js와 LipReadCheck가 쓰며, 노드 테스트에서 axios·MediaPipe 없이 확인하려고 따로 둔다.
 */

/** 같은 키로 동시에 들어온 호출을 진행 중인 약속 하나로 묶는다. 약속이 끝나면(성공·실패 모두) 바로 지워 다음 호출은 새로 보낸다.
 *  끝난 응답을 다시 쓰지 않으므로(TTL 없음) 복습·학습 초기화 직후에 오래된 값을 돌려주지 않는다. clear()는 진행 중인 약속을 모두 잊는다. */
export function createInflight() {
  const pending = new Map()
  function share(key, fetcher) {
    const hit = pending.get(key)
    if (hit) return hit
    // fetcher가 동기로 던져도 거부된 약속으로 돌려준다(부르는 쪽의 .catch가 받는다)
    const p = new Promise((resolve) => resolve(fetcher()))
      .finally(() => { if (pending.get(key) === p) pending.delete(key) })
    pending.set(key, p)
    return p
  }
  share.clear = () => pending.clear()
  share.size = () => pending.size
  return share
}

/** factory의 약속을 한 번 만들어 계속 나눈다(모듈 전역 캐시). 거부되면 비워 다음 호출에서 다시 만든다(네트워크가 잠깐 끊겼을 때 재시도). */
export function memoUntilFail(factory) {
  let cached = null
  return function get() {
    if (!cached) {
      const mine = new Promise((resolve) => resolve(factory()))
      mine.catch(() => { if (cached === mine) cached = null })
      cached = mine
    }
    return cached
  }
}
