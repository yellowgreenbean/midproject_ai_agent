// 카드 화면이 쓰는 작은 규칙 — 금액 판정은 서버(backend/app/routers/cards.py)가 하고, 화면은 묶고 더해 보여 주기만 한다
import type { CardBill, CardPerformance, CardTransaction } from './api'

export const CARD_TYPE_LABEL = { CHECK: '체크', CREDIT: '신용' } as const
export const CARD_STATUS_LABEL: Record<string, string> = { ACTIVE: '정상', SUSPENDED: '일시정지', LOST: '분실 신고', EXPIRED: '유효기간 지남', TERMINATED: '해지' }
export const BILL_STATUS_LABEL: Record<CardBill['status'], string> = { SCHEDULED: '쓰는 중', CONFIRMED: '결제 예정', PAID: '결제 완료', OVERDUE: '미납' }
export const APPLICATION_STEPS = [
  { status: 'APPLIED', label: '신청' },
  { status: 'APPROVED', label: '승인' },
  { status: 'SHIPPING', label: '배송 중' },
  { status: 'DELIVERED', label: '도착' },
  { status: 'ACTIVATED', label: '등록 완료' },
] as const

/** 취소를 뺀 실제로 쓴 돈 */
export const net = (t: Pick<CardTransaction, 'amount' | 'canceledAmount'>) => t.amount - t.canceledAmount

/** 가맹점 분류별 합계 — 많이 쓴 곳이 먼저. 전부 취소된 분류는 뺀다 */
export function byCategory(list: Pick<CardTransaction, 'category' | 'amount' | 'canceledAmount'>[]) {
  const sum = new Map<string, number>()
  for (const t of list) sum.set(t.category, (sum.get(t.category) ?? 0) + net(t))
  return [...sum]
    .filter(([, amount]) => amount > 0)
    .map(([category, amount]) => ({ category, amount }))
    .sort((a, b) => b.amount - a.amount || a.category.localeCompare(b.category))
}

/** 결제 캘린더 — 결제일별로 묶어 합친다. 낼 돈(결제 예정·미납·쓰는 중)은 가까운 날부터, 다 낸 것은 최근부터 */
export function groupByPaymentDate(bills: CardBill[]) {
  const groups = new Map<string, CardBill[]>()
  for (const b of bills) groups.set(b.paymentDate, [...(groups.get(b.paymentDate) ?? []), b])
  const all = [...groups].map(([date, list]) => ({
    date,
    bills: list,
    due: list.reduce((n, b) => n + b.totalAmount - b.paidAmount, 0),
    done: list.every((b) => b.status === 'PAID'),
  }))
  return {
    upcoming: all.filter((g) => !g.done).sort((a, b) => a.date.localeCompare(b.date)),
    past: all.filter((g) => g.done).sort((a, b) => b.date.localeCompare(a.date)),
  }
}

/** 금액 — productRules.won 과 같은 모양 (노드 테스트가 확장자 없는 값 import 를 못 읽어 여기 둔다) */
const won = (n: number) => `${n.toLocaleString('ko-KR')}원`

/** 실적 한 줄 — 「지난달 21,300원 썼어요. 300,000원 이상 쓰면 혜택을 받아요」 */
export function performanceText(p: CardPerformance) {
  const when = p.period === 'QUARTER' ? '지난 분기' : '지난달'
  if (p.tierLevel === null) return `${when} ${won(p.spent)} 썼어요. ${won(p.tierMinSpend)} 이상 쓰면 혜택을 받아요`
  const next = p.nextMinSpend === null ? '가장 높은 구간이에요' : `${won(p.nextMinSpend - p.spent)} 더 쓰면 다음 구간이에요`
  return `${when} ${won(p.spent)} 써서 ${p.tierLevel}구간 혜택을 받는 중 · ${next}`
}

/** 이번 달부터 거꾸로 n달 — 'YYYYMM' (이용 내역의 달 고르기) */
export function recentMonths(today: Date, n: number): string[] {
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1)
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`
  })
}

/** '2026-11-14' 또는 ISO 시각 → '11월 14일' */
export const md = (s: string) => `${Number(s.slice(5, 7))}월 ${Number(s.slice(8, 10))}일`

/** '2026-11-14' → '2026.11.14' */
export const dots = (s: string) => s.slice(0, 10).replaceAll('-', '.')

/** 유효기간 ISO 시각 → 카드에 찍히는 'MM/YY' */
export const expiry = (iso: string) => `${iso.slice(5, 7)}/${iso.slice(2, 4)}`
