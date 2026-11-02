// 저메모리 기기에서는 보조 모델을 생략하고 기존 비모델 경로를 쓴다.
export function canLoadOptionalModel() {
  if (typeof WebAssembly !== 'object' || typeof WebAssembly.instantiate !== 'function') return false
  const memory = globalThis.navigator?.deviceMemory
  return !(Number.isFinite(memory) && memory <= 2)
}

export function configureWasm(ort) {
  ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/'
  // Safari와 교차 출처 격리 없는 환경도 SharedArrayBuffer 없이 실행한다.
  ort.env.wasm.numThreads = 1
  ort.env.logLevel = 'error'
}
