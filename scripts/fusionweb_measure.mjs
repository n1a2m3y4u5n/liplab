import { createRequire } from 'node:module'
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('playwright')
const out = process.argv[2]
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--mute-audio'] })
try {
  const page = await browser.newPage()
  // 앱/API/얼굴 모델 요청 없이, 같은 Vite 원점의 빈 문서에서 합성 캔버스만 사용한다.
  await page.route('**/fusion-bench', (route) => route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>synthetic benchmark</title>' }))
  await page.goto('http://127.0.0.1:5187/fusion-bench')
  const timing = await page.evaluate(async () => {
    const { landmarkLips80, LIPS_IDX } = await import('/src/lib/lipFusion.js')
    const { grabRoiFrame } = await import('/src/lib/lipreadRoiModel.js')
    const source = document.createElement('canvas')
    source.width = source.videoWidth = 640
    source.height = source.videoHeight = 360
    source.currentTime = 0
    const ctx = source.getContext('2d')
    const image = ctx.createImageData(640, 360)
    for (let i = 0; i < image.data.length; i++) image.data[i] = (i * 31) % 256
    ctx.putImageData(image, 0, 0)
    const landmarks = Array.from({ length: 478 }, () => ({ x: .5, y: .5, z: 0 }))
    LIPS_IDX.forEach((idx, i) => { landmarks[idx] = { x: .5 + .08 * Math.cos(i * .31), y: .65 + .03 * Math.sin(i * .31), z: 0 } })
    landmarks[33] = { x: .3, y: .3 }; landmarks[263] = { x: .7, y: .35 }
    const holder = {}
    let sink = 0
    const run = (fusion, count) => {
      const start = performance.now()
      for (let i = 0; i < count; i++) {
        source.currentTime = i / 30
        const frame = grabRoiFrame(source, landmarks, holder)
        if (fusion) frame.lips = landmarkLips80(landmarks, 640, 360)
        sink += frame.gray[0] + (frame.lips?.[0] || 0)
      }
      return (performance.now() - start) / count
    }
    run(false, 100); run(true, 100)
    const pairs = []
    for (let i = 0; i < 20; i++) {
      let off, on
      if (i % 2) { on = run(true, 100); off = run(false, 100) }
      else { off = run(false, 100); on = run(true, 100) }
      pairs.push({ off, on, delta: on - off })
    }
    const median = (a) => { a.sort((a,b) => a-b); return (a[9]+a[10])/2 }
    return { unit: 'ms/frame', pairs, off_median: median(pairs.map((p) => p.off)),
      on_median: median(pairs.map((p) => p.on)), paired_delta_median: median(pairs.map((p) => p.delta)),
      sink, synthetic: '640x360 canvas; fixed 478 landmarks; no face detection/inference/camera',
      warmup_frames_each: 100, pairs_count: 20, frames_per_batch: 100, userAgent: navigator.userAgent }
  })
  const bundles = {}
  for (const mode of ['off','on']) {
    const root = join(out, `build-${mode}`)
    const html = readFileSync(join(root, 'index.html'), 'utf8')
    const entryFiles = [...html.matchAll(/(?:src|href)="(\/assets\/[^\"]+\.(?:js|css))"/g)].map((m) => m[1].slice(1))
    // 첫 문서의 entry + modulepreload + CSS: 지연 로딩 청크는 제외.
    const entries = [...new Set(entryFiles)].map((file) => { const data = readFileSync(join(root,file)); return { file, bytes:data.length, gzip:gzipSync(data).length } })
    const js = readdirSync(join(root,'assets')).filter((f) => f.endsWith('.js'))
    const lip = js.filter((f) => f.startsWith('LipReadCheck-')).map((file) => { const data = readFileSync(join(root,'assets',file)); return { file, bytes:data.length, gzip:gzipSync(data).length } })
    bundles[mode] = { entries, initial_bytes:entries.reduce((s,f) => s+f.bytes,0), initial_gzip:entries.reduce((s,f) => s+f.gzip,0), lipread_lazy:lip,
      all_js_bytes:js.reduce((s,f) => s+statSync(join(root,'assets',f)).size,0) }
  }
  const result = { browser: await browser.version(), timing, bundles,
    initial_delta_bytes:bundles.on.initial_bytes-bundles.off.initial_bytes,
    initial_delta_gzip:bundles.on.initial_gzip-bundles.off.initial_gzip,
    limitation:'Synthetic extraction overhead only, not end-to-end latency; physical camera unverified. Models are absent from these measurements.' }
  writeFileSync(join(out,'measurement.json'),JSON.stringify(result,null,2))
  console.log(JSON.stringify({ browser:result.browser, off_ms:timing.off_median, on_ms:timing.on_median, delta_ms:timing.paired_delta_median,
    initial_delta_bytes:result.initial_delta_bytes, initial_delta_gzip:result.initial_delta_gzip }))
} finally { await browser.close() }
