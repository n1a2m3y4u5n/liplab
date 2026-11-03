// 입모양(viseme) 받기의 공용 순수 로직. 실패(네트워크 오류·빈 응답)를 삼키지 않고 호출한 쪽이 안내를 보이게 한다.

/** get(text)로 입모양 프레임을 받는다. 오류이거나 비어 있으면 { ok: false }. */
export async function fetchVisemeFrames(get, text) {
  try {
    const frames = await get(text)
    if (Array.isArray(frames) && frames.length > 0) return { ok: true, frames }
  } catch { /* 아래에서 실패로 돌려준다 */ }
  return { ok: false, frames: [] }
}

/** 요청 번호표: 새 요청이 시작되면 이전 요청의 늦은 응답은 버린다. */
export function createLatest() {
  let n = 0
  return {
    next: () => ++n,
    isCurrent: (id) => id === n,
    cancel: () => { n += 1 },
  }
}

/** 한 번 더 보낼 수 있는 제출: 같은 요청을 중복 없이 '한 번만' 다시 보낸다. */
export function createResubmit() {
  let inflight = false
  return {
    /** send는 Promise를 돌려주는 함수. 이미 보내는 중이면 null. 성공하면 true, 실패하면 false. */
    async run(send) {
      if (inflight) return null
      inflight = true
      try { await send(); return true } catch { return false } finally { inflight = false }
    },
    get busy() { return inflight },
  }
}
