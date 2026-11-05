import { test } from 'node:test'
import assert from 'node:assert/strict'
import { byCategory, expiry, groupByPaymentDate, md, recentMonths } from '../src/cardRules.ts'
import type { CardBill } from '../src/api.ts'

const tx = (category: string, amount: number, canceledAmount = 0) => ({ category, amount, canceledAmount })

test('분류별 합계는 취소를 빼고, 많이 쓴 곳이 먼저', () => {
  assert.deepEqual(byCategory([tx('카페', 5000), tx('편의점', 3000), tx('카페', 4500), tx('주유', 47400, 47400)]), [
    { category: '카페', amount: 9500 },
    { category: '편의점', amount: 3000 },
  ]) // 전부 취소된 주유는 빠진다
  assert.deepEqual(byCategory([]), [])
})

const bill = (cardId: string, paymentDate: string, status: CardBill['status'], totalAmount: number, paidAmount = 0): CardBill => ({
  id: null, cardId, cardName: cardId, billingYm: paymentDate.slice(0, 7).replace('-', ''), usageStart: '', usageEnd: '',
  paymentDate, totalAmount, paidAmount, status, accountNumber: null, lowBalance: false,
})

test('결제 캘린더 — 같은 결제일은 합치고, 낼 돈은 가까운 날부터·다 낸 것은 최근부터', () => {
  const g = groupByPaymentDate([
    bill('a', '2026-12-14', 'SCHEDULED', 0),
    bill('a', '2026-11-14', 'CONFIRMED', 86900),
    bill('b', '2026-11-14', 'CONFIRMED', 119200),
    bill('a', '2026-10-14', 'PAID', 136400, 136400),
    bill('b', '2026-09-14', 'PAID', 1000, 1000),
  ])
  assert.deepEqual(g.upcoming.map((x) => [x.date, x.due, x.bills.length]), [['2026-11-14', 206100, 2], ['2026-12-14', 0, 1]])
  assert.deepEqual(g.past.map((x) => [x.date, x.due]), [['2026-10-14', 0], ['2026-09-14', 0]])
})

test('이번 달부터 거꾸로 — 해를 넘어간다', () => {
  assert.deepEqual(recentMonths(new Date(2026, 0, 31), 3), ['202601', '202512', '202511'])
  assert.deepEqual(recentMonths(new Date(2026, 10, 5), 1), ['202611'])
})

test('날짜 모양', () => {
  assert.equal(md('2026-11-04T09:00:00+09:00'), '11월 4일')
  assert.equal(expiry('2029-03-31T23:59:59+09:00'), '03/29')
})
