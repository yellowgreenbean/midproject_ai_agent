import { test } from 'node:test'
import assert from 'node:assert/strict'
import { byCategory, expiry, groupByPaymentDate, md, performanceText, recentMonths } from '../src/cardRules.ts'
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

test('실적 한 줄 — 못 넘음 · 구간 안 · 가장 높은 구간 · 분기', () => {
  const p = (spent: number, tierLevel: number | null, tierMinSpend: number, nextMinSpend: number | null, period: 'MONTH' | 'QUARTER' = 'MONTH') =>
    performanceText({ period, spent, tierLevel, tierMinSpend, nextMinSpend })
  assert.equal(p(21300, null, 300000, 300000), '지난달 21,300원 썼어요. 300,000원 이상 쓰면 혜택을 받아요')
  assert.equal(p(450000, 1, 300000, 600000), '지난달 450,000원 써서 1구간 혜택을 받는 중 · 150,000원 더 쓰면 다음 구간이에요')
  assert.equal(p(1500000, 3, 1200000, null), '지난달 1,500,000원 써서 3구간 혜택을 받는 중 · 가장 높은 구간이에요')
  assert.match(p(0, null, 3000000, 3000000, 'QUARTER'), /^지난 분기 0원 썼어요/)
})
