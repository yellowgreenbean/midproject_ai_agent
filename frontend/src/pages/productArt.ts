// 상품 종류 → 그림·이름 (홈과 같은 3D 그림)
import type { ProductType } from '../api'
import acctDeposit from '../assets/acct-deposit.png'
import acctInstallment from '../assets/acct-installment.png'

export const PRODUCT_ART: Record<ProductType, string> = { TIME_DEPOSIT: acctDeposit, INSTALLMENT_SAVINGS: acctInstallment }
export const STATUS_LABEL: Record<string, string> = { ACTIVE: '진행 중', MATURED: '만기 지급 완료', TERMINATED: '중도 해지' }
export const TYPE_LABEL: Record<ProductType, string> = { TIME_DEPOSIT: '정기예금', INSTALLMENT_SAVINGS: '적금' }
// 종류별 색 결 (HomePage.css 의 .product-card.is-deposit / .is-installment)
export const TYPE_CLASS: Record<ProductType, string> = { TIME_DEPOSIT: 'is-deposit', INSTALLMENT_SAVINGS: 'is-installment' }
