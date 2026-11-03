// 저장소(localStorage)를 막은 브라우저(사생활 모드·차단 설정)에서 읽기·쓰기가 던지지 않게 한다(T5).
export function lsGet(key, storage = globalThis.localStorage) {
  try { return storage?.getItem(key) ?? null } catch { return null }
}
export function lsSet(key, value, storage = globalThis.localStorage) {
  try { storage?.setItem(key, value); return true } catch { return false }
}
