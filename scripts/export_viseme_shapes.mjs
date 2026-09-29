// 아바타 입모양 표와 선행 동시조음 규칙(frontend/src/lib)을 파드 스크립트용 JSON으로 내보낸다. 표를 파이썬에 옮겨 적지 않고
// 한 원본을 두 쪽이 같이 쓰게 하려는 것이다(docs/coarticulation-e.md). 표나 규칙을 바꾸면 다시 돌린다. 어긋나면
// frontend의 coarticulation.test.mjs가 실패한다.
//   node scripts/export_viseme_shapes.mjs          → scripts/viseme_shapes.json 을 새로 쓴다
//   node scripts/export_viseme_shapes.mjs --print  → 쓰지 않고 내용만 출력
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { buildExport } from '../frontend/src/lib/visemeShapesExport.js'

const out = JSON.stringify(buildExport(), null, 1) + '\n'
if (process.argv.includes('--print')) process.stdout.write(out)
else {
  const path = fileURLToPath(new URL('./viseme_shapes.json', import.meta.url))
  writeFileSync(path, out)
  console.log(`wrote ${path}`)
}
