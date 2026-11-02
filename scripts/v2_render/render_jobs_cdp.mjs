// render_jobs.py와 같은 작업·결과 형식의 Windows용 실행기. Playwright 파이썬 패키지 없이 설치된 Chrome을 CDP로 직접 돌린다(Node 22 이상 내장 WebSocket).
//   node render_jobs_cdp.mjs --harness DIR --jobs a.json [--jobs b.json] --tables t.json --out DIR --workers 4 --gl d3d11 [--port 5196] [--bench]
// 환경변수: CHROME(chrome.exe 경로), FFMPEG. 표식: RJ_GL, RJ_OK id n 초, RJ_FAIL id 오류, RJ_DONE ok fail skip, RJ_BENCH
// 작업 번호 % 작업자 수로 나눠 가지고, 이미 있는 결과는 건너뛴다. 카메라·크기·시계는 render_jobs.py 기본값 그대로다.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'

const GL_ARGS = {
  swiftshader: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  d3d11: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--enable-gpu-rasterization'],
}
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.glb': 'model/gltf-binary', '.css': 'text/css', '.json': 'application/json' }

function parseArgs(argv) {
  const a = { jobs: [], workers: 4, gl: 'd3d11', port: 5196, tables: '', out: 'renders', bench: false, only: '' }
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i]
    if (k === '--bench') a.bench = true
    else if (k === '--jobs') a.jobs.push(argv[++i])
    else if (k === '--workers' || k === '--port') a[k.slice(2)] = Number(argv[++i])
    else a[k.slice(2)] = argv[++i]
  }
  return a
}

function serve(root, port) {
  const srv = http.createServer((req, res) => {
    const p = path.join(root, decodeURIComponent(new URL(req.url, 'http://x').pathname))
    fs.readFile(p, (err, buf) => {
      if (err) { res.writeHead(404); res.end(); return }
      res.writeHead(200, { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' })
      res.end(buf)
    })
  })
  return new Promise((ok) => srv.listen(port, '127.0.0.1', () => ok(srv)))
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class Page {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.wait = new Map()
    ws.addEventListener('message', (e) => {
      const m = JSON.parse(e.data)
      const w = m.id && this.wait.get(m.id)
      if (w) { this.wait.delete(m.id); m.error ? w.no(new Error(JSON.stringify(m.error).slice(0, 300))) : w.ok(m.result) }
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((ok, no) => { this.wait.set(id, { ok, no }); this.ws.send(JSON.stringify({ id, method, params })) })
  }
  async evaluate(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })
    if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception?.description || r.exceptionDetails.text || '').slice(0, 300))
    return r.result.value
  }
}

async function openBrowser(a, wid) {
  const dport = a.port + 100 + wid
  const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'rjcdp-'))
  const proc = spawn(process.env.CHROME, ['--headless=new', `--remote-debugging-port=${dport}`, `--user-data-dir=${prof}`, '--no-first-run', '--no-sandbox',
    '--disable-dev-shm-usage', '--window-size=700,400', ...GL_ARGS[a.gl], 'about:blank'], { stdio: 'ignore' })
  let target = null
  for (let i = 0; i < 100 && !target; i++) {
    await sleep(200)
    try { target = (await (await fetch(`http://127.0.0.1:${dport}/json`)).json()).find((t) => t.type === 'page') } catch { /* 아직 뜨는 중 */ }
  }
  if (!target) { proc.kill(); throw new Error('chrome 시작 실패') }
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((ok, no) => { ws.addEventListener('open', ok); ws.addEventListener('error', no) })
  const pg = new Page(ws)
  await pg.send('Runtime.enable'); await pg.send('Page.enable')
  await pg.send('Page.navigate', { url: `http://127.0.0.1:${a.port}/index.html` })
  for (let i = 0; i < 300; i++) {
    await sleep(200)
    if (await pg.evaluate('window.__v2ready === true').catch(() => false)) break
    if (i === 299) throw new Error('하네스 준비 시간 초과')
  }
  const info = await pg.evaluate(`window.__v2.init(${JSON.stringify({ w: 640, h: 360, fov: 16, camPos: [0, 1.66, 1.8], target: [0, 1.66, 0], glb: null })})`)
  return { pg, info, close: () => { try { ws.close() } catch { /* 무시 */ } proc.kill(); setTimeout(() => fs.rmSync(prof, { recursive: true, force: true, maxRetries: 3 }), 1500) } }
}

async function runJob(pg, j, tables) {
  if (j.kind !== 'text') throw new Error('text 작업만 지원')
  const tbl = j.table ? tables?.[j.table] : null
  if (j.table && !tbl) throw new Error('table ' + j.table)
  let v3 = j.v3 || null
  if (v3 && v3 !== 'app') { v3 = tables?.[v3]; if (!v3) throw new Error('v3 table ' + j.v3) }
  const r = await pg.evaluate(`window.__v2.renderText(${JSON.stringify({ frames: j.frames, talker: j.talker, seed: 0, speed: j.speed, leadMs: j.leadMs ?? 400, tailMs: j.tailMs ?? 400, table: tbl, v3, amp: j.amp ?? null })})`)
  const sched = { id: j.id, schedule: r.schedule, speech: r.speech, fps: r.fps, talker: j.talker, speed: j.speed, table: j.table ?? null, v3: j.v3 ?? null, amp: j.amp ?? null, n_images: r.images.length }
  return { images: r.images, sched }
}

function writeMp4(images, file) {
  const tmp = file + '.part.mp4'
  return new Promise((ok, no) => {
    const p = spawn(process.env.FFMPEG || 'ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', '30', '-i', '-', '-c:v', 'libx264',
      '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30', tmp], { stdio: ['pipe', 'ignore', 'inherit'] })
    p.on('close', (c) => { if (c !== 0) return no(new Error('ffmpeg 실패')); fs.renameSync(tmp, file); ok() })
    for (const im of images) p.stdin.write(Buffer.from(im.split(',', 2)[1], 'base64'))
    p.stdin.end()
  })
}

async function worker(wid, a, jobs, tables, tot) {
  let b = await openBrowser(a, wid)
  if (wid === 0) console.log('RJ_GL', JSON.stringify(b.info))
  for (let k = 0; k < jobs.length; k++) {
    if (k % a.workers !== wid) continue
    const j = jobs[k]
    const mp4 = path.join(a.out, j.id + '.mp4'), sj = path.join(a.out, j.id + '.sched.json')
    if (fs.existsSync(mp4) && fs.existsSync(sj)) { tot.skip++; continue }
    const t0 = Date.now()
    try {
      const { images, sched } = await runJob(b.pg, j, tables)
      await writeMp4(images, mp4)
      fs.writeFileSync(sj + '.tmp', JSON.stringify(sched)); fs.renameSync(sj + '.tmp', sj)
      tot.ok++
      console.log(`RJ_OK ${j.id} ${images.length} ${((Date.now() - t0) / 1000).toFixed(1)}`)
    } catch (e) {
      tot.fail++
      console.log(`RJ_FAIL ${j.id} ${String(e.message).slice(0, 200)}`)
      b.close(); b = await openBrowser(a, wid)
    }
  }
  b.close()
}

async function main() {
  const a = parseArgs(process.argv.slice(2))
  if (!process.env.CHROME) throw new Error('CHROME 환경변수가 없다')
  const tables = a.tables ? JSON.parse(fs.readFileSync(a.tables, 'utf8')) : null
  fs.mkdirSync(a.out, { recursive: true })
  let jobs = a.jobs.flatMap((p) => JSON.parse(fs.readFileSync(p, 'utf8')))
  jobs = [...new Map(jobs.map((j) => [j.id, j])).values()]   // 두 겹에 같은 문장이 있으면 v1 작업 id가 겹친다
  if (a.only) { const pre = a.only.split(','); jobs = jobs.filter((j) => pre.some((x) => j.id.startsWith(x))) }
  const srv = await serve(path.resolve(a.harness), a.port)
  if (a.bench) {
    const b = await openBrowser(a, 0)
    const t0 = Date.now()
    const { images } = await runJob(b.pg, jobs[0], tables)
    const dt = (Date.now() - t0) / 1000
    await writeMp4(images, path.join(a.out, `_bench_${a.gl}.mp4`))
    console.log('RJ_BENCH', a.gl, JSON.stringify(b.info), `frames=${images.length} sec=${dt.toFixed(1)} fps=${(images.length / dt).toFixed(1)}`)
    b.close(); srv.close(); process.exit(0)
  }
  const tot = { ok: 0, fail: 0, skip: 0 }
  await Promise.all(Array.from({ length: a.workers }, (_, w) => worker(w, a, jobs, tables, tot).catch((e) => console.log(`RJ_WORKER_FAIL ${w} ${String(e.message).slice(0, 300)}`))))
  console.log(`RJ_DONE ok=${tot.ok} fail=${tot.fail} skip=${tot.skip}`)
  srv.close(); process.exit(0)
}

main().catch((e) => { console.error(e); process.exit(1) })
