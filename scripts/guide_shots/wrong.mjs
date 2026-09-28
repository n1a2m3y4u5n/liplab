// 오답 장면: 보기를 하나씩 골라 오답이 나올 때까지(새 세션) 다시 한다.
import { chromium } from 'playwright'
const BASE = 'http://localhost:5191'
const browser = await chromium.launch({ channel: 'chrome', args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
for (let k = 0; k < 4; k++) {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 564 }, deviceScaleFactor: 476 / 375, locale: 'ko-KR', timezoneId: 'Asia/Seoul' })
  await ctx.addInitScript(() => { try { localStorage.setItem('liplab_sign_intro_seen', '1') } catch { /* noop */ } ; document.addEventListener('DOMContentLoaded', () => { const st = document.createElement('style'); st.textContent = '[aria-label="접근성 설정 열기"]{display:none!important}'; document.head.appendChild(st) }) })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/login`)
  await page.getByRole('button', { name: /둘러보기/ }).click()
  await page.waitForURL(/learn|onboarding/, { timeout: 20000 })
  await page.goto(`${BASE}/learn/word`)
  await page.waitForTimeout(5000)
  const opts = page.locator('button').filter({ hasText: /^\s*[1-4]\s*\S/ })
  const n = await opts.count()
  const o = opts.nth(k % Math.max(1, n))
  await o.scrollIntoViewIfNeeded()
  await o.click({ force: true })
  await page.waitForTimeout(300)
  await page.getByRole('button', { name: /^확인$/ }).first().click({ force: true })
  await page.waitForTimeout(2500)
  const right = await page.getByText('정답이에요').count()
  console.log('try', k, 'options', n, 'right', right)
  if (!right) {
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: 'out/lp-348-135-guide-read-wrong.png' })
    console.log('ok wrong'); await ctx.close(); break
  }
  await ctx.close()
}
await browser.close()
