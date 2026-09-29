// 지문자 손모양 매핑 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { COMPOSED, fingerspellImage, fingerspellShapes } from './fingerspell.js'

const root = fileURLToPath(new URL('../../../', import.meta.url))
const PUBLIC = `${root}frontend/public`

// 한글 음절 → 호환 자모(초성·중성·종성). 백엔드 sign_service.fingerspell과 같은 분해다.
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
const JONG = ['', ...'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ']
function jamoOf(word) {
  const out = []
  for (const ch of word) {
    const i = ch.codePointAt(0) - 0xac00
    if (i < 0 || i > 11171) { out.push(ch); continue }
    out.push(CHO[Math.floor(i / 588)], JUNG[Math.floor((i % 588) / 28)])
    if (i % 28) out.push(JONG[i % 28])
  }
  return out
}

// 단어 은행 = curriculum.WORD_BANK(코드에 적힌 단어) + approved.json 단어(curriculum._merge_approved_content와 같은 병합)
function wordBank() {
  const py = readFileSync(`${root}backend/curriculum.py`, 'utf8')
  const block = py.slice(py.indexOf('WORD_BANK: List[Dict] = ['), py.indexOf('\n]', py.indexOf('WORD_BANK: List[Dict] = [')))
  const words = [...block.matchAll(/"word": "([^"]+)"/g)].map((m) => m[1])
  const approved = JSON.parse(readFileSync(`${root}backend/data/curriculum/approved.json`, 'utf8'))
  for (const w of approved.words || []) if (w?.word && !words.includes(w.word)) words.push(w.word)
  return words
}

test('모든 자모(자음 19·모음 21·겹받침 11)가 있는 그림 파일의 손모양 조각으로 보인다', () => {
  for (const ch of new Set([...CHO, ...JUNG, ...JONG.slice(1)])) {
    const { parts } = fingerspellShapes(ch)
    assert.ok(parts.length >= 1, ch)
    for (const p of parts) {
      assert.ok(p.src, `${ch}: ${p.jamo} 그림 없음`)
      assert.ok(existsSync(PUBLIC + p.src), `${ch}: ${p.src} 파일 없음`)
    }
  }
})

test('조합 규칙: 된소리는 예사소리 거듭, w 이중모음은 두 모음, 겹받침은 두 자음. 조각은 모두 그림이 있는 기본 자모다', () => {
  assert.deepEqual(fingerspellShapes('ㄲ').parts.map((p) => p.jamo), ['ㄱ', 'ㄱ'])
  assert.deepEqual(fingerspellShapes('ㅘ').parts.map((p) => p.jamo), ['ㅗ', 'ㅏ'])
  assert.deepEqual(fingerspellShapes('ㅞ').parts.map((p) => p.jamo), ['ㅜ', 'ㅔ'])
  assert.deepEqual(fingerspellShapes('ㄺ').parts.map((p) => p.jamo), ['ㄹ', 'ㄱ'])
  for (const [ch, c] of Object.entries(COMPOSED)) {
    assert.equal(fingerspellImage(ch), null, `${ch}는 그림이 있으면 조합할 필요가 없다`)
    assert.ok(c.note, ch)
    for (const j of c.parts) assert.ok(fingerspellImage(j), `${ch}의 조각 ${j}에 그림이 없다`)
  }
  // 그림이 있는 자모는 그대로 한 조각, 숫자·기호는 텍스트 폴백
  assert.deepEqual(fingerspellShapes('ㅆ').parts, [{ jamo: 'ㅆ', src: '/fingerspell/ss.jpg' }])
  assert.deepEqual(fingerspellShapes('²').parts, [{ jamo: '²', src: null }])
  assert.equal(fingerspellShapes('A').parts[0].src, '/fingerspell/latin/A.svg')
})

test('단어 은행: 글자로만 보이던 단어가 0개가 된다(예전 매핑 47개)', () => {
  const words = wordBank()
  assert.ok(words.length >= 500, `단어 은행이 너무 작다: ${words.length}`)
  const textOld = words.filter((w) => jamoOf(w).some((j) => !fingerspellImage(j)))
  const textNew = words.filter((w) => jamoOf(w).some((j) => fingerspellShapes(j).parts.some((p) => !p.src)))
  // 예전에는 fingerspellImage만 봐서 된소리·w 이중모음·겹받침이 든 단어가 글자로 나왔다(9/29 기준 528개 중 47개)
  assert.ok(textOld.length >= 40, `예전 매핑 폴백 ${textOld.length}`)
  assert.deepEqual(textNew, [])
})
