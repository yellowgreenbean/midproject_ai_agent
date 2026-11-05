// 계좌 종류 → 그림·이름, 상태·해지 막힘 사유 → 화면 문장 (홈과 같은 3D 통장 그림)
import type { CloseBlocker } from '../api'
import acctChecking from '../assets/acct-checking.png'
import acctSavings from '../assets/acct-savings.png'

export const ACCOUNT_ART: Record<string, string> = { CHECKING: acctChecking, SAVINGS: acctSavings }
export const ACCOUNT_TYPE_LABEL: Record<string, string> = { CHECKING: '입출금통장', SAVINGS: '저축예금' }
export const ACCOUNT_STATUS_LABEL: Record<string, string> = { ACTIVE: '정상', SUSPENDED: '일시정지', CLOSED: '해지' }

/** 해지 막힘 사유 — 무엇을 하면 풀리는지와 그 화면 */
export const BLOCKER: Record<CloseBlocker, { text: string; href?: string; link?: string }> = {
  BALANCE_REMAINING: { text: '잔액이 남아 있어요. 다른 계좌로 옮긴 뒤 해지할 수 있어요.', href: '#/transfer', link: '송금하기' },
  PENDING_TRANSFER: { text: '처리 중인 이체나 예약·자동이체가 있어요.' },
  LINKED_SUBSCRIPTION: { text: '이 계좌에서 돈이 빠지는 예금·적금이 있어요. 만기나 중도 해지 뒤 해지할 수 있어요.', href: '#/my/savings', link: '내 가입 상품' },
  LINKED_CARD: { text: '이 계좌에 연결된 카드가 있어요. 카드 결제 계좌를 바꾸거나 카드를 해지해 주세요.', href: '#/cards', link: '카드 관리' },
}

/** 20261105093000 → 2026.11.05 09:30 */
export const stamp = (s: string) => `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)} ${s.slice(8, 10)}:${s.slice(10, 12)}`
