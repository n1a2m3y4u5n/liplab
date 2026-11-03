// 로컬 서버 전용 브라우저 회귀: node scripts/test_tab_load.mjs
import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
const { chromium, webkit } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE || 'D:/work/hq/projects/liplab/out/e2e-tools/node_modules/playwright/index.mjs'))
const base = process.env.E2E_BASE || 'http://127.0.0.1:14174'
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
for (const [name, engine] of [['chromium', chromium], ['webkit', webkit]]) {
  const browser = await engine.launch()
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' })
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
    // 수어 사용법 안내는 문장을 드래그해 수어 패널을 열 때만 뜬다(처음 방문 대기열에서 빠졌다). 첫 방문 안내는 듣기 안내 하나다
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
    await page.getByRole('dialog', { name: '소리 듣기 안내', exact: true }).waitFor()
    await page.keyboard.press('Escape')
    await page.getByRole('dialog').waitFor({ state: 'detached' })
    console.log(`${name}: lesson-frame queue and Escape dismissal OK`)
    const cases = [
      ['/records?view=wrong', ['/api/review/due'], '문장 목록'],
      ['/records?view=wrong', ['/api/review-sentences'], '문장 목록'],
      ['/records?view=saved', ['/api/bookmarks'], '문장 목록'],
      ['/records?view=wrong', ['/api/listen/review'], '문장 목록'],
      ['/today', ['/api/tasks'], '오늘의 과제'],
      ['/records', ['/api/analysis/overview'], '학습 시간 변화'],
      ['/records', ['/api/calendar'], '학습 시간 변화'],
      ['/listen/today', ['/api/listen/today'], '오늘'],
      ['/records?view=wrong', ['/api/'], '문장 목록'],
      ['/today', ['/api/'], '오늘의 과제'],
      ['/records', ['/api/'], '학습 시간 변화'],
    ]
    for (const [path, endpoints, ready] of cases) {
      console.log(`${name}: checking ${path} ${endpoints.join()}`)
      const fail = (route) => endpoints.some((s) => new URL(route.request().url()).pathname.startsWith(s)) ? route.abort() : route.continue()
      await page.route('**/api/**', fail)
      await page.goto(base + path)
      const retry = page.getByRole('button', { name: ['/listen/today','/today'].includes(path) ? '다시 가져오기' : '다시 시도', exact: true }).first()
      await retry.waitFor({ timeout: 10000 }).catch(async (e) => { console.log('Failure state:', (await page.locator('body').innerText()).slice(0, 1500)); throw e })
      assert.equal(await page.getByText('복습할 것이 없어요. 잘하고 있어요!', { exact: true }).count(), 0)
      await page.unroute('**/api/**', fail)
      await retry.click()
      await retry.waitFor({ state: 'detached' })
      await page.getByText(ready, { exact: false }).first().waitFor()
      console.log(`${name}: ${path} ${endpoints.join()} failure + recovery OK`)
    }
    // 입모양 API 실패 → 안내와 다시 받기(배치검사는 문항을 내지 않고 재시도 화면에 머문다), 복구 뒤 문항이 나온다
    {
      const failViseme = (route) => new URL(route.request().url()).pathname.startsWith('/api/viseme') ? route.abort() : route.continue()
      await page.route('**/api/**', failViseme)
      await page.goto(base + '/learn/placement')
      const alert = page.getByText('입모양을 불러오지 못했어요', { exact: false }).first()
      await alert.waitFor({ timeout: 15000 }).catch(async (e) => { console.log('Failure state:', (await page.locator('body').innerText()).slice(0, 1500)); throw e })
      await page.unroute('**/api/**', failViseme)
      await page.getByRole('button', { name: '다시 시도', exact: true }).click()
      await alert.waitFor({ state: 'detached', timeout: 15000 })
      console.log(`${name}: placement viseme failure + retry OK`)
    }
    // 단어 레슨: 답 기록을 보내지 못하면 다음 문항으로 조용히 넘어가지 않고 안내(다시 보내기·건너뛰기)를 보인다. 폰 헤더의 접근성 Aa 버튼도 열린다
    {
      await page.goto(base + '/learn/word')
      await page.getByRole('button', { name: '접근성 설정', exact: true }).first().waitFor({ timeout: 15000 })
      const failSubmit = (route) => new URL(route.request().url()).pathname.includes('/word-answer') ? route.abort() : route.continue()
      await page.route('**/api/**', failSubmit)
      const choice = page.locator('button').filter({ hasText: /^[1-4]?\s*[가-힣]+$/ }).first()
      await choice.waitFor({ timeout: 15000 })
      await choice.click()
      await page.getByRole('button', { name: '확인', exact: true }).click()
      await page.getByText('기록을 보내지 못했어요').waitFor({ timeout: 10000 })
      await page.unroute('**/api/**', failSubmit)
      await page.getByRole('button', { name: '다시 보내기', exact: true }).click()
      await page.getByText('기록을 보내지 못했어요').waitFor({ state: 'detached', timeout: 10000 })
      await page.getByRole('button', { name: '접근성 설정', exact: true }).first().click()
      await page.getByRole('dialog', { name: '접근성 설정' }).waitFor()
      console.log(`${name}: word submit failure + resend, header Aa OK`)
    }
    assert.deepEqual(errors, [])
    await context.close()
  } finally { await browser.close() }
}
