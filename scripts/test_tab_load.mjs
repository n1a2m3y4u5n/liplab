// 로컬 서버 전용 브라우저 회귀: node scripts/test_tab_load.mjs
import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
const { chromium, webkit } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE || 'D:/work/hq/projects/liplab/out/e2e-tools/node_modules/playwright/index.mjs'))
const base = process.env.E2E_BASE || 'http://127.0.0.1:14174'
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
for (const [name, engine] of [['chromium', chromium], ['webkit', webkit]]) {
  const browser = await engine.launch()
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const auth = await (await context.request.post(`${base}/api/auth/demo`)).json()
    assert.ok(auth.access_token)
    await context.addInitScript((auth) => {
      localStorage.setItem('liplab_mute', '1')
      localStorage.setItem('liplab_listen_settings', JSON.stringify({ gainDb: -20, at: new Date().toISOString() }))
      localStorage.setItem('liplab-storage', JSON.stringify({ state: { user: auth.user, token: auth.access_token, isAuthenticated: true }, version: 0 }))
    }, auth)
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.goto(`${base}/learn/path?track=listen`)
    await page.getByRole('dialog', { name: '수어 번역 사용법 안내' }).waitFor()
    assert.equal(await page.locator('dialog[open]').count(), 0)
    await page.getByRole('button', { name: '알겠어요' }).click()
    await page.getByRole('dialog', { name: '소리 듣기 안내', exact: true }).waitFor()
    assert.equal(await page.getByRole('dialog', { name: '수어 번역 사용법 안내' }).count(), 0)
    await page.getByRole('button', { name: '안내 닫기' }).click()
    await page.reload()
    await page.waitForTimeout(300)
    assert.equal(await page.getByRole('dialog').count(), 0)
    console.log(`${name}: first-visit queue and persisted dismissal OK`)
    await page.evaluate(() => {
      localStorage.removeItem('liplab_sign_intro_seen')
      localStorage.removeItem('liplab_listen_notice')
    })
    await page.goto(`${base}/listen/today`)
    await page.getByRole('dialog', { name: '수어 번역 사용법 안내' }).waitFor()
    assert.equal(await page.locator('dialog[open]').count(), 0)
    await page.keyboard.press('Escape')
    await page.getByRole('dialog', { name: '소리 듣기 안내', exact: true }).waitFor()
    await page.keyboard.press('Escape')
    await page.getByRole('dialog').waitFor({ state: 'detached' })
    console.log(`${name}: lesson-frame queue and Escape dismissal OK`)
    const cases = [
      ['/review', ['/api/review/due'], '복습할 것이 없어요. 잘하고 있어요!'],
      ['/review', ['/api/review-sentences'], '복습할 것이 없어요. 잘하고 있어요!'],
      ['/review', ['/api/bookmarks'], '복습할 것이 없어요. 잘하고 있어요!'],
      ['/review', ['/api/listen/review'], '복습할 것이 없어요. 잘하고 있어요!'],
      ['/tasks', ['/api/tasks'], '오늘의 과제'],
      ['/analysis', ['/api/analysis/overview'], '학습 시간 변화'],
      ['/analysis', ['/api/calendar'], '학습 시간 변화'],
      ['/listen/today', ['/api/listen/today'], '오늘'],
      ['/review', ['/api/'], '복습할 것이 없어요. 잘하고 있어요!'],
      ['/tasks', ['/api/'], '오늘의 과제'],
      ['/analysis', ['/api/'], '학습 시간 변화'],
    ]
    for (const [path, endpoints, ready] of cases) {
      const fail = (route) => endpoints.some((s) => new URL(route.request().url()).pathname.startsWith(s)) ? route.abort() : route.continue()
      await page.route('**/api/**', fail)
      await page.goto(base + path)
      const retry = page.getByRole('button', { name: path === '/listen/today' ? '다시 가져오기' : '다시 시도', exact: true })
      await retry.waitFor()
      assert.equal(await page.getByText('복습할 것이 없어요. 잘하고 있어요!', { exact: true }).count(), 0)
      await page.unroute('**/api/**', fail)
      await retry.click()
      await retry.waitFor({ state: 'detached' })
      await page.getByText(ready, { exact: false }).first().waitFor()
      console.log(`${name}: ${path} ${endpoints.join()} failure + recovery OK`)
    }
    assert.deepEqual(errors, [])
    await context.close()
  } finally { await browser.close() }
}
