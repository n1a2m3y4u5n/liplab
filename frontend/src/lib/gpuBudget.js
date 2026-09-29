import { useSyncExternalStore } from 'react'

// GPU 메모리 예산. 3D 얼굴 한 캔버스가 GPU 메모리를 약 130MB 쓰고(텍스처 디코딩 ~98MB + 모프 버퍼),
// 여러 명 대화는 캔버스가 최대 4개라 저사양 기기에서 WebGL 컨텍스트가 끊기기 쉽다(9/29 점검).
// 약한 기기이거나 한 번이라도 컨텍스트를 잃었으면 캔버스를 여러 개 띄우는 화면은 2D로 그린다.

// 약한 기기: 메모리 4GB 이하(deviceMemory, 크롬 계열만 알려 줌) 또는 논리 코어 4개 이하.
export function isWeakDevice(nav = globalThis.navigator) {
  if (!nav) return false
  const mem = Number(nav.deviceMemory)
  const cores = Number(nav.hardwareConcurrency)
  return (mem > 0 && mem <= 4) || (cores > 0 && cores <= 4)
}

// 점검용: 주소에 ?lowgpu=1을 붙이면 약한 기기처럼 동작한다.
function forcedLow() {
  try { return new URLSearchParams(globalThis.location?.search || '').get('lowgpu') === '1' } catch { return false }
}

let lost = false
const subs = new Set()

// AvatarVRM이 webglcontextlost를 받으면 부른다. 이후 이 페이지 세션 동안 여러 캔버스 화면은 2D로 간다.
export function markContextLost() {
  if (lost) return
  lost = true
  subs.forEach((f) => f())
}

export function contextLost() { return lost }

function subscribe(f) {
  subs.add(f)
  return () => subs.delete(f)
}

// 3D 캔버스를 여러 개 띄워도 되는지. 약한 기기·컨텍스트 손실 뒤에는 true.
export function gpuConstrained() {
  return lost || forcedLow() || isWeakDevice()
}

export function useGpuConstrained() {
  return useSyncExternalStore(subscribe, gpuConstrained, () => false)
}

// 테스트용
export function _resetGpuBudget() { lost = false; subs.clear() }
