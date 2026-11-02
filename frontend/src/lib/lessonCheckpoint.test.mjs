import test from 'node:test'
import assert from 'node:assert/strict'
import {checkpointKey,readCheckpoint,writeCheckpoint,clearCheckpoints} from './lessonCheckpoint.js'
function storage() {
  const m=new Map()
  return {get length(){return m.size},key:i=>[...m.keys()][i],getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}
}
test('reload preserves the remaining deck, Set slots, answered item and totals together',()=>{
  const s=storage(),key=checkpointKey(1,'word')
  const state={qNum:7,q:{target:'가',choices:['다','가']},result:{correct:true},tally:{n:7,correct:5},xpEarned:30,asked:new Set(['가','나']),slots:{typed:new Set([8,10])}}
  assert.equal(writeCheckpoint(key,state,s),true)
  assert.deepEqual(readCheckpoint(key,s),state)
  assert.equal(readCheckpoint(key,s).asked.has('가'),true)
  assert.equal(readCheckpoint(checkpointKey(2,'word'),s),null)
})
test('blocked, corrupt and incompatible storage does not prevent entering a lesson',()=>{
  const blocked={getItem(){throw Error('blocked')},setItem(){throw Error('quota')}}
  assert.equal(readCheckpoint('x',blocked),null);assert.equal(writeCheckpoint('x',{},blocked),false)
  const s=storage()
  for(const text of ['bad','null','[]','{"version":9,"state":{}}','{"version":1,"state":[]}']){
    s.setItem('x',text);assert.equal(readCheckpoint('x',s),null)
  }
})
test('logout/reset removes every lesson checkpoint and leaves device accessibility settings',()=>{
  const s=storage();writeCheckpoint(checkpointKey(1,'viseme'),{},s);writeCheckpoint(checkpointKey(2,'word'),{},s);s.setItem('liplab_mute','1')
  clearCheckpoints(s);assert.equal(s.length,1);assert.equal(s.getItem('liplab_mute'),'1')
})
