import test from 'node:test'
import assert from 'node:assert/strict'
import { pxToRem } from '../../postcss-font-rem.js'

test('글자 크기 px는 16px 기준 rem으로 바뀐다(기본 화면 크기 유지)', () => {
  assert.equal(pxToRem('13px'), '0.8125rem')
  assert.equal(pxToRem('16px'), '1rem')
  assert.equal(pxToRem('12.5px'), '0.78125rem')
  assert.equal(pxToRem('clamp(14px, 2vw, 20px)'), 'clamp(0.875rem, 2vw, 1.25rem)')
})

test('12px 미만은 12px(0.75rem)로 올린다', () => {
  assert.equal(pxToRem('10px'), '0.75rem')
  assert.equal(pxToRem('11.5px'), '0.75rem')
  assert.equal(pxToRem('8px'), '0.75rem')
})

test('px가 아닌 값은 그대로 둔다', () => {
  assert.equal(pxToRem('0.875rem'), '0.875rem')
  assert.equal(pxToRem('inherit'), 'inherit')
})
