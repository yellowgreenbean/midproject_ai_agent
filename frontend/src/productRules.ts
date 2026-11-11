// 상품 화면이 쓰는 작은 규칙 — 서버(backend/app/routers/products.py estimate)가 최종 판정하고, 화면은 고를 수 있는 값만 보여 준다
import type { PaymentType, ProductDetail } from './api'

/** 고를 수 있는 가입 기간(개월). 정해진 기간이 있으면 그것만, 없으면 최소~최대(최대가 없으면 금리표 끝까지) */
export function monthOptions(p: Pick<ProductDetail, 'selectableMonths' | 'minMonths' | 'maxMonths' | 'rates'>): number[] {
  if (p.selectableMonths?.length) return p.selectableMonths
  const lo = p.minMonths ?? Math.min(...p.rates.map((r) => r.termMin))
  const hi = p.maxMonths ?? Math.max(...p.rates.map((r) => r.termMax))
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi < lo) return []
  return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
}

/** 일 단위 상품(표지어음·CD)인가 — 기간을 일수로 입력한다 */
export const isDayUnit = (p: Pick<ProductDetail, 'rates'>) => p.rates[0]?.termUnit === 'DAY'

/** 기본 기간 — 12개월을 고를 수 있으면 12, 아니면 첫 값 */
export const defaultMonths = (options: number[]) => (options.includes(12) ? 12 : (options[0] ?? 0))

/** 적금 납입 방식 이름과 한 줄 설명 (backend/app/savings.py 와 같은 규칙) */
export const PAYMENT_TYPE_LABEL: Record<PaymentType, string> = { FIXED: '정액적립식', FREE: '자유적립식' }
export const PAYMENT_TYPE_HINT: Record<PaymentType, string> = {
  FIXED: '매달 같은 금액을 한 번씩 넣어요',
  FREE: '한 달 한도 안에서 원할 때 자유롭게 넣어요',
}

/** 처음 고른 납입 방식 — 한 가지뿐이면 그것, 둘 다 되면 사용자가 직접 고르게 비워 둔다 */
export const defaultPaymentType = (types: PaymentType[]): PaymentType | null => (types.length === 1 ? types[0] : null)

export const won = (n: number) => `${n.toLocaleString('ko-KR')}원`

/** 20271105 → 2027.11.05 */
export const ymd = (s: string) => `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`

/** 숫자만 남긴 금액 — 입력칸의 "1,000,000원" 같은 글자를 정리 */
export const digitsOnly = (s: string) => s.replace(/\D/g, '').replace(/^0+(?=\d)/, '')

const ymdDate = (s: string) => new Date(Number(s.slice(0, 4)), Number(s.slice(4, 6)) - 1, Number(s.slice(6, 8)))

/** 가입일 → 만기일 중 지난 비율(0~100). start·maturity 는 'YYYYMMDD' */
export function savingsProgress(start: string, maturity: string, now = Date.now()) {
  const a = ymdDate(start).getTime()
  const b = ymdDate(maturity).getTime()
  return b > a ? Math.min(100, Math.max(0, Math.round(((now - a) / (b - a)) * 100))) : 100
}

/** 만기까지 남은 날 (오늘이 만기면 0, 지났으면 음수) */
export function daysLeft(maturity: string, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  return Math.round((ymdDate(maturity).getTime() - today) / 86_400_000)
}
