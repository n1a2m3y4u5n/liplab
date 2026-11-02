import test from 'node:test'
import assert from 'node:assert/strict'
import { canLoadOptionalModel, configureWasm } from './modelCapability.js'

test('WASM 미지원 및 알려진 저메모리 기기는 보조 모델을 생략한다', () => {
  const wasm = globalThis.WebAssembly
  const nav = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  try {
    globalThis.WebAssembly = undefined
    assert.equal(canLoadOptionalModel(), false)
    globalThis.WebAssembly = wasm
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { deviceMemory: 2 } })
    assert.equal(canLoadOptionalModel(), false)
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {} })
    assert.equal(canLoadOptionalModel(), true)
  } finally {
    globalThis.WebAssembly = wasm
    if (nav) Object.defineProperty(globalThis, 'navigator', nav)
    else delete globalThis.navigator
  }
})

test('WASM은 SharedArrayBuffer 없는 Safari에서도 단일 스레드로 실행한다', () => {
  const ort = { env: { wasm: {} } }
  configureWasm(ort)
  assert.equal(ort.env.wasm.numThreads, 1)
})
