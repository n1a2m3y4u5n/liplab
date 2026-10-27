import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const sw = readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8')

test('이름이 그대로인 자산은 네트워크 우선이고 해시 자산만 캐시 우선이다', () => {
  const plain = sw.indexOf("!url.pathname.startsWith('/assets/')")
  const swr = sw.indexOf('caches.match(req).then((cached)')
  assert.ok(plain > 0 && swr > plain)
  assert.match(sw.slice(plain, swr), /fetch\(req\)\.then/)
})

test('서비스워커 캐시 이름이 v5에서 올라갔다', () => {
  assert.doesNotMatch(sw, /const CACHE = 'liplab-v5'/)
})

test('녹음 화면은 마이크 끊김과 시간 상한으로 마무리한다', () => {
  const src = readFileSync(new URL('../pages/SpeakingPractice.jsx', import.meta.url), 'utf8')
  assert.match(src, /addEventListener\('ended', endNow\)/)
  assert.match(src, /MAX_REC_MS/)
})
