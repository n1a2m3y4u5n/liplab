// 관문: frontend/node_modules 설치본이 package-lock.json과 같은 판인지 검사한다(11/03 검토 X1).
// 어긋나면(예: junction으로 다른 worktree의 node_modules를 쓸 때) 종료 코드 1. 이미지 쪽은 `npm ci`라 lock대로 설치되므로,
// 관문도 같은 판으로 검사해야 결과를 믿을 수 있다.
//   node scripts/check_node_lock.mjs [frontend 폴더]
import fs from 'node:fs'
import path from 'node:path'

export function compareLockToInstalled(lock, readInstalledVersion) {
  const mismatches = []
  for (const [key, meta] of Object.entries(lock.packages || {})) {
    if (!key.startsWith('node_modules/') || !meta.version) continue
    if (meta.link) continue
    const installed = readInstalledVersion(key)
    if (installed === null) {
      // 선택 의존(다른 OS용 네이티브 패키지 등)은 설치되지 않는 것이 정상이다
      if (meta.optional || meta.peer) continue
      mismatches.push({ name: key.replace(/^.*node_modules\//, ''), lock: meta.version, installed: null })
    } else if (installed !== meta.version) {
      mismatches.push({ name: key.replace(/^.*node_modules\//, ''), lock: meta.version, installed })
    }
  }
  return mismatches
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'))) {
  const dir = path.resolve(process.argv[2] || 'frontend')
  const lock = JSON.parse(fs.readFileSync(path.join(dir, 'package-lock.json'), 'utf8'))
  const mismatches = compareLockToInstalled(lock, (key) => {
    try { return JSON.parse(fs.readFileSync(path.join(dir, key, 'package.json'), 'utf8')).version } catch { return null }
  })
  if (mismatches.length) {
    console.error(`node_modules가 package-lock.json과 다르다(${mismatches.length}개). frontend에서 npm ci 하세요.`)
    for (const m of mismatches.slice(0, 15)) console.error(`  ${m.name}: lock ${m.lock} / 설치 ${m.installed ?? '없음'}`)
    process.exit(1)
  }
  console.log('node_modules matches package-lock.json')
}
