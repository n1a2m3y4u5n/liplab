// 사용법 가이드 사진을 실제 앱(3D 아바타)으로 다시 찍는다. 로컬 프론트 :5191 + 잠금 켠 백엔드 :8091(LIPLAB_UNLOCK_ALL=0, AI 문항 끔).
// 결과는 ./out/<파일명> (기존 public/ui 파일과 같은 픽셀 크기). 사용: node capture.mjs [이름 일부]
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = 'http://localhost:5191'
const only = process.argv[2]
fs.mkdirSync('out', { recursive: true })

const SHOTS = [
  { file: 'lp-338-274-guide-overview.png', w: 1532, h: 808, dpr: 1, path: '/learn/path', wait: 3500 },
  { file: 'lp-345-147-guide-learn.png', w: 446, h: 560, dpr: 2, path: '/learn/path', wait: 3500 },
  { file: 'lp-346-77-guide-practice.png', w: 446, h: 560, dpr: 2, path: '/practice/hub', wait: 2500 },
  { file: 'lp-346-516-guide-review.png', w: 446, h: 560, dpr: 2, path: '/review', wait: 2500 },
  { file: 'lp-347-294-guide-profile.png', w: 446, h: 560, dpr: 2, path: '/profile', wait: 2500 },
  { file: 'lp-347-79-guide-analysis.png', w: 446, h: 560, dpr: 2, path: '/analysis', wait: 3000 },
  { file: 'lp-346-291-guide-task.png', w: 470, h: 407, dpr: 2, path: '/tasks', wait: 2500 },
  { file: 'lp-348-81-guide-read-q.png', w: 375, h: 564, dpr: 476 / 375, path: '/learn/word', wait: 5000, kind: 'readQ' },
  // { file: 'lp-348-135-guide-read-wrong.png', w: 375, h: 564, dpr: 476 / 375, path: '/learn/word', wait: 5000, kind: 'readWrong' },
  { file: 'lp-348-233-guide-speak-before.png', w: 375, h: 564, dpr: 476 / 375, path: '/learn/speaking?stage=4', wait: 5000 },
  // { file: 'lp-348-268-guide-speak-result.png', w: 375, h: 564, dpr: 476 / 375, path: '/learn/speaking?stage=4', wait: 5000, kind: 'speakResult' },
]

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
})

async function login(page) {
  await page.goto(`${BASE}/login`)
  await page.getByRole('button', { name: /둘러보기/ }).click()
  await page.waitForURL(/learn|onboarding/, { timeout: 20000 })
  await page.waitForTimeout(1500)
}

for (const s of SHOTS) {
  if (only && !s.file.includes(only)) continue
  const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: s.dpr, locale: 'ko-KR',
    timezoneId: 'Asia/Seoul', permissions: ['microphone', 'camera'] })
  await ctx.addInitScript(() => { try { localStorage.setItem('liplab_sign_intro_seen', '1') } catch { /* noop */ } ; document.addEventListener('DOMContentLoaded', () => { const st = document.createElement('style'); st.textContent = '[aria-label="접근성 설정 열기"]{display:none!important}'; document.head.appendChild(st) }) })
  const page = await ctx.newPage()
  try {
    await login(page)
    if (s.kind === 'speakResult') {
      await page.route('**/api/speak/assess', (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify({
        score: 84, passed: true, note: '', transcript: null, assessment_method: 'dgop', coaching: '입술을 붙였다 떼는 ㅂ이 또렷해요. 받침까지 끝까지 닫아 보세요.',
        dgop: { score: 84, raw_score: 12.3, phones: [
          { token: 'o:ㅂ', label: 'ㅂ', dgop: 0.82, aligned: true, scorable: true, score: 88 },
          { token: 'n:ㅏ', label: 'ㅏ', dgop: 0.9, aligned: true, scorable: true, score: 92 },
          { token: 'o:ㄷ', label: 'ㄷ', dgop: 0.61, aligned: true, scorable: true, score: 63 },
          { token: 'n:ㅏ', label: 'ㅏ', dgop: 0.86, aligned: true, scorable: true, score: 90 }] },
        stage_progress: null,
      }) }))
    }
    if (s.kind === 'readWrong') {
      page.on('response', async (r) => {
        if (!r.url().includes('/api/curriculum/words')) return
        try {
          const j = await r.json()
          const items = j.items || j.words || j.questions || []
          const q = items[0] || {}
          globalThis.__firstAnswer = q.word || q.answer || q.target
          console.log('answer', globalThis.__firstAnswer, Object.keys(j).join(','), Object.keys(q).join(','))
        } catch { /* noop */ }
      })
    }
    await page.goto(`${BASE}${s.path}`)
    await page.waitForTimeout(s.wait)
    if (s.kind === 'readWrong') {
      const opts = page.locator('[aria-pressed]')
      const n = await opts.count()
      const answer = globalThis.__firstAnswer
      let pick = 1
      for (let i = 0; i < n; i++) {
        const t = (await opts.nth(i).innerText()).replace(/^\d+\s*/, '').trim()
        if (answer && t !== answer) { pick = i; break }
      }
      if (n > 1) { await opts.nth(pick).click(); await page.waitForTimeout(300) }
      const ok = page.getByRole('button', { name: /^확인$/ })
      if (await ok.count()) { await ok.first().click(); await page.waitForTimeout(2500) }
    }
    if (s.kind === 'speakResult') {
      const rec = page.getByRole('button', { name: '눌러서 말하기' })
      await rec.click()
      await page.waitForTimeout(9000)
      for (let i = 0; i < 10 && !(await page.getByText(/잘했어요|아쉬워요|점/).count()); i++) await page.waitForTimeout(1000)
    }
    await page.screenshot({ path: `out/${s.file}` })
    console.log('ok', s.file)
  } catch (e) {
    console.log('FAIL', s.file, e.message.split('\n')[0])
    await page.screenshot({ path: `out/FAIL-${s.file}` }).catch(() => {})
  }
  await ctx.close()
}
await browser.close()
