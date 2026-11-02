// Local build regression; no paid API, audio playback, or user-data mutation.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE || 'D:/work/hq/projects/liplab/out/e2e-tools/node_modules/playwright/index.mjs'))
const base = process.env.E2E_BASE || 'http://127.0.0.1:18314'
assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname))
const out = process.env.IA_OUT || 'D:/work/hq/projects/liplab/out/ia-2026-11-02'
const b = await chromium.launch({args:['--mute-audio']})
const result = []
try {
 const c = await b.newContext({viewport:{width:390,height:844},serviceWorkers:'block'})
 const auth = await (await c.request.post(base+'/api/auth/demo')).json()
 await c.addInitScript(d=>{localStorage.setItem('liplab_mute','1');localStorage.setItem('liplab_sign_intro_seen','1');localStorage.setItem('liplab_listen_notice','1');if(!localStorage.getItem('liplab-storage'))localStorage.setItem('liplab-storage',JSON.stringify({state:{user:d.user,token:d.access_token,isAuthenticated:true},version:0}))},auth)
 const p=await c.newPage()
 const open=async(path)=>{await p.goto(base+path);await p.waitForTimeout(650);assert.ok(!(await p.locator('body').innerText()).includes('문제가 생겼어요'),path)}
 for(const [old,to,hash]of [['/dashboard','/today',''],['/tasks','/today','#tasks'],['/review','/today','#review'],['/review/hub','/today','#review'],['/review/today','/today','#review'],['/analysis','/records',''],['/analysis/hub','/records',''],['/analysis/overview','/records',''],['/analysis/listening','/records',''],['/sign','/learn/sign','']]){
  await open(old+'?source=legacy&track=speak');const u=new URL(p.url());assert.equal(u.pathname,to);assert.equal(u.hash,hash);assert.equal(u.searchParams.get('source'),'legacy');assert.equal(u.searchParams.get('track'),old==='/analysis/listening'?'listen':'speak');result.push({old,destination:u.pathname+u.search+u.hash})
 }
 await p.evaluate(uid=>localStorage.setItem(`liplab_last_track:${uid}`,'listen'),auth.user.id)
 await open('/practice/hub?source=legacy');assert.equal(new URL(p.url()).searchParams.get('track'),'listen');assert.equal(new URL(p.url()).searchParams.get('section'),'free')
 await open('/learn/path');assert.equal(await p.getByRole('button',{name:'입모양 읽기',exact:true}).getAttribute('aria-pressed'),'true');result.push({barePath:'read despite stored listen'})
 await p.evaluate(uid=>localStorage.setItem(`liplab_last_track:${uid}`,'listen'),auth.user.id)
 await open('/profile');await p.locator('[data-mobile-tabbar]').getByRole('button',{name:'학습',exact:true}).click();await p.waitForTimeout(400);assert.equal(new URL(p.url()).searchParams.get('track'),'listen')
 let claims=0;const order=[]
 await c.route('**/api/auth/me',r=>r.fulfill({json:{...auth.user,total_xp:claims>0?7000:auth.user.total_xp}}))
 await c.route('**/api/tasks',r=>{order.push('get');return r.fulfill({json:{daily:[],weekly:[]}})})
 await c.route('**/api/tasks/claim',async r=>{claims++;order.push('claim');await new Promise(r=>setTimeout(r,150));return r.fulfill({json:{daily:[],weekly:[],xp_gained:claims===1?77:0,total_xp:7000,current_level:5,claimed:claims===1?[{label:'입모양 읽기 1회',xp:77}]:[]}})})
 await open('/today');assert.equal(claims,1);assert.ok((await p.locator('body').innerText()).includes('경험치 +77'));await open('/records');await open('/today');assert.equal(claims,2);assert.deepEqual(order,['claim','claim']);const stored=await p.evaluate(()=>JSON.parse(localStorage.getItem('liplab-storage')).state.user.total_xp);assert.equal(stored,7000);result.push({claimTwice:claims,totalXp:stored,cacheOrder:order})
 await c.route('**/api/listen/practice/modes*',r=>r.fulfill({json:['contrast','dictation','noise_endless','scenario','conditions'].map(key=>({key,available:false,reason:'소리 확인을 먼저 해 주세요.'}))}))
 await open('/learn/path?track=listen&section=free');assert.equal(await p.getByRole('button',{name:'소리 확인 하러 가기'}).count(),1);assert.equal(await p.locator('main button:disabled').count(),5);await p.screenshot({path:out+'/locked-before-sound-check.png',fullPage:true});result.push({lockedModes:5,sharedCheckButton:1})
 for(const track of ['read','speak','listen'])for(const section of ['path','free','res']){await open(`/learn/path?track=${track}&section=${section}`);await p.screenshot({path:`${out}/after-shots/section-${track}-${section}.png`,fullPage:true})}
 await c.route('**/api/curriculum/stages*',async r=>{const res=await r.fetch();const d=await res.json();return r.fulfill({json:{...d,stages:(d.stages||[]).map(s=>({...s,status:s.stage>=2?'locked':s.status}))}})})
 await open('/learn/path?section=free');assert.equal(await p.getByRole('button',{name:/뜻 없는 말 짝 맞추기/}).count(),0)
 await open('/practice');assert.equal(new URL(p.url()).pathname,'/learn/path');result.push({stageGate:'read path unchanged',nonsenseHiddenWhenLocked:true})
 const items=fs.readFileSync(new URL('../frontend/src/components/records/ReviewItems.jsx',import.meta.url),'utf8');assert.ok(items.includes("it.track === '발화'"));assert.ok(items.includes('trackLabel(track)'));result.push({storedComparison:'발화',displayOnly:true})
 fs.writeFileSync(out+'/navigation-regressions.json',JSON.stringify(result,null,2));console.log('IA navigation regressions passed',result.length)
}finally{await b.close()}
