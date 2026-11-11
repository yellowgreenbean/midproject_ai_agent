import { test } from 'node:test'
import assert from 'node:assert/strict'
import { defaultMonths, digitsOnly, monthOptions, ymd, defaultPaymentType } from '../src/productRules.ts'

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

test('만기까지 지난 비율과 남은 날', async () => {
  const { daysLeft, savingsProgress } = await import('../src/productRules.ts')
  const mid = new Date(2026, 6, 2).getTime() // 2026-01-01 ~ 2027-01-01 의 한가운데쯤
  assert.equal(savingsProgress('20260101', '20270101', mid), 50)
  assert.equal(savingsProgress('20260101', '20270101', new Date(2025, 0, 1).getTime()), 0)
  assert.equal(savingsProgress('20260101', '20270101', new Date(2028, 0, 1).getTime()), 100)
  assert.equal(daysLeft('20261110', new Date(2026, 10, 6, 23, 59)), 4)
  assert.equal(daysLeft('20261106', new Date(2026, 10, 6, 9)), 0)
})

test('납입 방식: 한 가지뿐이면 그것, 둘 다 되면 사용자가 고르게 비워 둔다', () => {
  assert.equal(defaultPaymentType(['FREE']), 'FREE')
  assert.equal(defaultPaymentType(['FIXED']), 'FIXED')
  assert.equal(defaultPaymentType(['FIXED', 'FREE']), null)
  assert.equal(defaultPaymentType([]), null) // 예금
})
