// 카드 상품 이름 → 앞면 그림 (홈·카드 화면이 같이 쓴다). 목록에 없는 카드(예: 판매 종료 「할인카드」)는 종류별 기본 그림
import type { CardType } from '../api'
import cardDurinCheck from '../assets/card-durin-check.png'
import cardHanbitCheck from '../assets/card-hanbit-check.png'
import cardHanbitLife from '../assets/card-hanbit-life.png'
import cardHanbitShopping from '../assets/card-hanbit-shopping.png'
import cardHanbitCredit from '../assets/card-hanbit-credit.png'

const CARD_ART: Record<string, string> = {
  '두린 체크카드': cardDurinCheck,
  한빛체크카드: cardHanbitCheck,
  '한빛 라이프 체크': cardHanbitLife,
  '한빛 쇼핑 신용카드': cardHanbitShopping,
  한빛신용카드: cardHanbitCredit,
}
export const cardArtOf = (productName: string, type: CardType) => CARD_ART[productName] ?? (type === 'CREDIT' ? cardHanbitCredit : cardHanbitCheck)
