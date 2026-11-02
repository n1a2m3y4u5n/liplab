// 이 기기의 계정별 레슨 상태. Set도 보존해 문항 순서를 다시 뽑지 않는다.
const PREFIX = 'liplab_lesson_v1:'
export const checkpointKey = (user, kind) => `${PREFIX}${user}:${kind}`
const encode = (_, value) => value instanceof Set ? { $set: [...value] } : value
const decode = (_, value) => value && Array.isArray(value.$set) ? new Set(value.$set) : value
export function readCheckpoint(key, storage) {
  try {
    storage ||= globalThis.localStorage
    const record = JSON.parse(storage.getItem(key), decode)
    return record?.version === 1 && record.state && typeof record.state === 'object' && !Array.isArray(record.state) ? record.state : null
  } catch { return null }
}
export function writeCheckpoint(key, value, storage) {
  try { (storage || globalThis.localStorage).setItem(key, JSON.stringify({ version: 1, state: value }, encode)); return true } catch { return false }
}
export function clearCheckpoints(storage) {
  try {
    storage ||= globalThis.localStorage
    for (let i = storage.length - 1; i >= 0; i--) {
      const key = storage.key(i)
      if (key?.startsWith(PREFIX)) storage.removeItem(key)
    }
  } catch { /* 저장소가 막히면 현재 레슨만 유지한다. */ }
}
