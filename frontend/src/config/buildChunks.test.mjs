// 빌드 청크 설정(vite.config.js manualChunks) 검사. 실행: node --test
// 엔트리가 정적으로 가져오는 React 계열 경로가 벤더 청크에 빠지면 그 런타임이 index 청크에 들어가, 앱 코드가 바뀔 때마다
// 바뀌지 않은 React를 다시 받는다('react-dom'만 적었을 때 react-dom/client·scheduler가 엔트리 gzip 93KB 중 58KB였다).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import config from '../../vite.config.js'

const vendor = config.build.rollupOptions.output.manualChunks['react-vendor']

// 파일의 정적 import 가운데 React 계열 패키지 경로(react, react-dom/…, react-router-dom)
function reactImports(rel) {
  const src = readFileSync(new URL(rel, import.meta.url), 'utf8')
  return [...src.matchAll(/^import\s[^'"]*['"]([^'"]+)['"]/gm)].map((m) => m[1])
    .filter((s) => /^react(-dom|-router-dom)?(\/|$)/.test(s))
}

test('main.jsx·App.jsx가 가져오는 React 계열 경로는 모두 react-vendor에 적혀 있다', () => {
  const specs = [...new Set([...reactImports('../main.jsx'), ...reactImports('../App.jsx')])]
  assert.ok(specs.includes('react-dom/client'), String(specs))
  for (const s of specs) assert.ok(vendor.includes(s), `${s} 이(가) react-vendor에 없음: ${vendor}`)
})
