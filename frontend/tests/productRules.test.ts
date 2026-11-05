import { test } from 'node:test'
import assert from 'node:assert/strict'
import { defaultMonths, digitsOnly, monthOptions, ymd } from '../src/productRules.ts'

const rate = (termMin: number, termMax: number) => ({ termMin, termMax, termUnit: 'MONTH' as const, baseRate: '3.00', bonusRate: null })

test('정해진 기간이 있으면 그것만 고른다', () => {
  assert.deepEqual(monthOptions({ selectableMonths: [3, 6, 9], minMonths: 3, maxMonths: 9, rates: [] }), [3, 6, 9])
})

test('최소~최대 기간, 최대가 없으면 금리표 끝까지', () => {
  assert.deepEqual(monthOptions({ selectableMonths: null, minMonths: 1, maxMonths: 3, rates: [rate(1, 36)] }), [1, 2, 3])
  assert.deepEqual(monthOptions({ selectableMonths: null, minMonths: 12, maxMonths: null, rates: [rate(12, 14)] }), [12, 13, 14])
  assert.deepEqual(monthOptions({ selectableMonths: null, minMonths: null, maxMonths: null, rates: [] }), []) // 금리표 없음
})

test('기본 기간과 표시 모양', () => {
  assert.equal(defaultMonths([6, 12, 24]), 12)
  assert.equal(defaultMonths([3, 6]), 3)
  assert.equal(ymd('20271105'), '2027.11.05')
  assert.equal(digitsOnly('1,000,000원'), '1000000')
  assert.equal(digitsOnly('007'), '7')
})
