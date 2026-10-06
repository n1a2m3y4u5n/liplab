#!/usr/bin/env node
// 쉬운 한국어 감사(C15)의 프론트엔드 문자열 추출기. scripts/easy_korean_audit.py가 부른다.
//
// frontend/node_modules의 @babel/parser로 JSX·JS를 구문 분석해, 한글이 든 화면 문자열만 뽑는다.
//   - JSX 글: 한 요소의 자식 글·문자열 식·안쪽 인라인 요소를 이어 붙여 한 문자열로 본다({식}은 '○'로 둔다).
//   - 문자열·템플릿 리터럴: ${식}은 '○'. 주석은 구문 분석에서 빠진다.
// 빼는 것: import 경로, 객체 키, 비교 연산(=== '...')의 값, console.*·throw·new Error 인자, className·key·id 같은
// 비표시 속성, 개발자용 화면(DevViseme·CueVideoDemo·ContentReview), 테스트 파일.
//
//   node scripts/easy_korean_extract.mjs <파일...>   → JSON 배열을 표준 출력으로
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(path.join(here, '..', 'frontend', 'package.json'))
const { parse } = require('@babel/parser')
const traverse = require('@babel/traverse').default

const HANGUL = /[가-힣]/
const NON_DISPLAY_ATTRS = new Set(['className', 'key', 'id', 'src', 'href', 'to', 'type', 'name', 'htmlFor', 'role',
  'data-testid', 'style', 'path', 'value', 'd', 'fill', 'stroke'])

function isDevCall(p) {
  // console.log(...) · throw new Error(...) · new Error(...) 안의 문자열은 개발자용이다
  let cur = p
  for (let i = 0; i < 6 && cur; i++, cur = cur.parentPath) {
    const n = cur.node
    if (n.type === 'CallExpression') {
      const c = n.callee
      if (c.type === 'MemberExpression' && c.object.type === 'Identifier' && c.object.name === 'console') return true
    }
    if (n.type === 'NewExpression' && n.callee.type === 'Identifier' && /Error$/.test(n.callee.name)) return true
    if (n.type === 'ThrowStatement') return true
  }
  return false
}

function attrName(p) {
  const par = p.parentPath
  if (par?.node.type === 'JSXAttribute') return par.node.name.name
  if (par?.node.type === 'JSXExpressionContainer' && par.parentPath?.node.type === 'JSXAttribute') return par.parentPath.node.name.name
  return null
}

function jsxText(node, consumed) {
  // 요소 안 글을 이어 붙인다. 인라인 요소(<b>·<span>·<strong> 등)는 안의 글까지, 식은 '○'.
  let out = ''
  for (const ch of node.children || []) {
    if (ch.type === 'JSXText') { out += ch.value; consumed.add(ch) }
    else if (ch.type === 'JSXExpressionContainer') {
      const e = ch.expression
      if (e.type === 'StringLiteral') { out += e.value; consumed.add(e) }
      else if (e.type === 'TemplateLiteral' && e.expressions.length === 0) { out += e.quasis.map((q) => q.value.cooked).join(''); consumed.add(e) }
      else if (e.type === 'JSXEmptyExpression') { /* 주석 */ }
      else out += '○'
    } else if (ch.type === 'JSXElement' || ch.type === 'JSXFragment') {
      const tag = ch.openingElement?.name?.name
      if (ch.type === 'JSXFragment' || /^(b|strong|em|i|span|mark|u|small|sup|sub|kbd|code|a)$/.test(tag || '')) {
        out += jsxText(ch, consumed)
      } else if (tag === 'br') out += '\n'
      else out += '\n'   // 블록 요소는 문장 경계로 본다(안쪽은 따로 뽑힌다)
    }
  }
  return out
}

function norm(s) { return s.replace(/[ \t\r]*\n[ \t\r]*/g, '\n').replace(/[ \t]+/g, ' ').replace(/\n+/g, '\n').trim() }

function extract(file) {
  const src = readFileSync(file, 'utf8')
  let ast
  try {
    ast = parse(src, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true })
  } catch (e) {
    return [{ file, error: String(e) }]
  }
  const out = []
  const consumed = new Set()
  const push = (node, kind, text, extra = {}) => {
    const t = norm(text)
    if (!HANGUL.test(t)) return
    out.push({ file, line: node.loc.start.line, kind, text: t, start: node.start, end: node.end, ...extra })
  }
  traverse(ast, {
    JSXElement(p) {
      const has = (p.node.children || []).some((c) => c.type === 'JSXText' && HANGUL.test(c.value))
      if (!has) return
      push(p.node, 'jsx', jsxText(p.node, consumed), { tag: p.node.openingElement.name.name || '' })
    },
    JSXFragment(p) {
      const has = (p.node.children || []).some((c) => c.type === 'JSXText' && HANGUL.test(c.value))
      if (!has) return
      push(p.node, 'jsx', jsxText(p.node, consumed), { tag: 'fragment' })
    },
  })
  traverse(ast, {
    StringLiteral(p) { visitLiteral(p, p.node.value) },
    TemplateLiteral(p) {
      if (p.parentPath.node.type === 'TaggedTemplateExpression') return
      visitLiteral(p, p.node.quasis.map((q, i) => q.value.cooked + (i < p.node.expressions.length ? '○' : '')).join(''))
    },
  })
  function visitLiteral(p, value) {
    if (consumed.has(p.node) || !HANGUL.test(value)) return
    const par = p.parentPath.node
    if (par.type === 'ImportDeclaration' || par.type === 'ExportNamedDeclaration') return
    if ((par.type === 'ObjectProperty' || par.type === 'ObjectMethod') && par.key === p.node && !par.computed) return
    if (par.type === 'BinaryExpression' && /^(===|!==|==|!=)$/.test(par.operator)) return
    if (par.type === 'SwitchCase') return
    if (par.type === 'TemplateLiteral') return
    if (isDevCall(p)) return
    const a = attrName(p)
    if (a && NON_DISPLAY_ATTRS.has(a)) return
    // 정규식 문자열·한 글자 자모 기호처럼 표시용이 아닌 것은 감사 쪽에서 거른다(길이·자모만인지)
    push(p.node, a ? 'attr' : 'string', value, a ? { attr: a } : {})
  }
  return out
}

const files = process.argv.slice(2)
const all = []
for (const f of files) all.push(...extract(f))
process.stdout.write(JSON.stringify(all))
