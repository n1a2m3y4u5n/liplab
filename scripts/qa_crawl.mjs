// 앱 전체 화면 점검(헤드리스 Chrome). 모든 경로를 데스크톱·모바일로 열어 콘솔 오류, 실패한 API 요청(4xx·5xx, 소리 준비 전 404 제외),
// 모바일 가로 넘침을 모은다. 소리 금지: Chrome --mute-audio + 앱 무음(liplab_mute).
// 준비: 백엔드(:8091)와 프론트(:5191)를 띄우고, 이 폴더 밖 임시 폴더에서 `npm i puppeteer-core` 뒤
//   NODE_PATH=<그 폴더>/node_modules node scripts/qa_crawl.mjs
// 맥에서 Chrome 복제본이 디스크를 채우던 문제 때문에 --disable-features=MacAppCodeSignClone을 꼭 둔다.
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
const BASE='http://localhost:5191', API='http://localhost:8091/api'
const routes = ['/','/about','/analysis','/analysis/activity','/analysis/eval','/analysis/history','/analysis/hub','/analysis/listening','/analysis/overview','/analysis/scores','/analysis/visemes','/dashboard','/learn/closure','/learn/conversation-multi','/learn/endless','/learn/listening?stage=0','/learn/listening?stage=3','/learn/nonsense','/learn/path','/learn/path?track=speak','/learn/path?track=listen','/learn/placement','/learn/scenario','/learn/sign','/learn/speaking?stage=0','/learn/viseme','/learn/word','/listen/classroom','/listen/practice/contrast','/listen/practice/dictation','/listen/practice/noise_endless','/listen/practice/scenario','/listen/practice/conditions','/listen/review','/listen/today','/practice/hub','/privacy','/profile','/pronounce','/review','/review/hub','/review/mistakes','/review/saved','/review/scheduled','/review/speaking','/review/today','/sign','/tasks','/terms']
const demo = await (await fetch(API+'/auth/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json()
const b = await puppeteer.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:'new',userDataDir:(process.env.TMPDIR||'/tmp')+'/liplab-qa-profile',args:['--mute-audio','--disable-features=MacAppCodeSignClone','--use-gl=swiftshader','--enable-unsafe-swiftshader']})
const out=[]
for (const kind of ['desktop','mobile']) {
  for (const r of routes) {
    const p = await b.newPage()
    await p.setViewport(kind==='desktop'?{width:1440,height:1024}:{width:375,height:812,isMobile:true,hasTouch:true})
    await p.evaluateOnNewDocument((st)=>{localStorage.setItem('liplab-storage',st);localStorage.setItem('liplab_mute','1');localStorage.setItem('liplab_sign_intro_seen','1');localStorage.setItem('liplab_listen_settings',JSON.stringify({gainDb:-15,device:'ha',route:'speaker'}))}, JSON.stringify({state:{user:demo.user,token:demo.access_token,isAuthenticated:true},version:0}))
    const errs=[], bad=[]
    p.on('console', m => { if (m.type()==='error') errs.push(m.text().slice(0,200)) })
    p.on('pageerror', e => errs.push('PAGEERROR '+String(e.message).slice(0,200)))
    p.on('response', res => { const u=res.url(); if (res.status()>=400 && u.includes('/api/') && !u.includes('/api/sound?')) bad.push(res.status()+' '+u.replace(BASE,'').slice(0,120)) })
    try { await p.goto(BASE+r,{waitUntil:'networkidle2',timeout:30000}) } catch(e) { errs.push('GOTO '+e.message.slice(0,80)) }
    await new Promise(x=>setTimeout(x,1500))
    const info = await p.evaluate(()=>({sw:document.documentElement.scrollWidth, w:window.innerWidth, path:location.pathname+location.search, text:document.body.innerText.slice(0,80).replace(/\n/g,' ')})).catch(()=>({}))
    out.push({kind, route:r, final:info.path, overflow: info.sw>info.w+1 ? `${info.sw}>${info.w}`:null, errs:[...new Set(errs)].slice(0,5), bad:[...new Set(bad)].slice(0,5)})
    await p.close()
  }
}
await b.close()
fs.writeFileSync((process.env.TMPDIR||'/tmp')+'/liplab-qa-crawl.json', JSON.stringify(out,null,1))
for (const o of out) if (o.overflow || o.errs.length || o.bad.length) console.log(o.kind, o.route, '->', o.final, o.overflow||'', JSON.stringify(o.errs), JSON.stringify(o.bad))
console.log('checked', out.length)
