"""청구 예정 금액 · 결제 캘린더 · 청구서 상세 — 기획서 Part 4 1-1-4 (CARD-F04).

    GET /card-bills            내 모든 카드의 청구서 (결제 캘린더 — 화면이 payment_date 로 묶는다)
    GET /card-bills/{billId}   청구서 하나 + 그 안에 든 이용 내역(card_bill_items)

- 이번 기간(쓰는 중, SCHEDULED) 청구서는 아직 저장 전이라 id 가 null 이고 목록에만 나온다(상세 없음).
- low_balance: 결제 계좌 잔액이 그 결제일까지 낼 돈보다 적으면 true (같은 계좌의 앞선 청구서까지 더해 봄).
- 남의 청구서·없는 청구서는 똑같이 404 BILL_NOT_FOUND.
- 결제일 알림(D-3·당일, 잔액 부족)은 app/jobs.py notify_card_payments 가 만든다.
"""

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DB, CurrentUserId
from app.errors import not_found
from app.models import CardBill, CardBillItem, CardTransaction, UserCard
from app.routers.cards import BillOut, CardTransactionOut, bills_of_user, card_transaction_rows
from app.rules import now_kst
from app.common.naming import Money

router = APIRouter(tags=["cards"])


class BillItemOut(BaseModel):
    transaction: CardTransactionOut
    installment_seq: int
    principal_amount: Money


class BillDetailOut(BillOut):
    items: list[BillItemOut]


@router.get("/card-bills", response_model=list[BillOut])
def list_card_bills(db: DB, user_id: CurrentUserId):
    bills = bills_of_user(db, user_id, now_kst().date())
    return sorted(bills, key=lambda b: (b.payment_date, b.card_id))


@router.get("/card-bills/{billId}", response_model=BillDetailOut)
def get_card_bill(bill_id: Annotated[str, Path(alias="billId")], db: DB, user_id: CurrentUserId):
    owned = db.scalar(select(CardBill.id).join(UserCard, UserCard.id == CardBill.user_card_id)
                      .where(CardBill.id == bill_id, UserCard.user_id == user_id, UserCard.source == "TOSS_ISSUED"))
    bill = next((b for b in bills_of_user(db, user_id, now_kst().date()) if b.id == bill_id), None) if owned else None
    if bill is None:
        raise not_found("BILL_NOT_FOUND", "청구서를 찾을 수 없어요.")
    items = db.execute(select(CardBillItem).where(CardBillItem.bill_id == bill_id)).scalars().all()
    tx = {t.id: t for t in card_transaction_rows(db, [CardTransaction.id.in_([i.card_transaction_id for i in items])])}
    return BillDetailOut(
        **dict(bill),
        items=[BillItemOut(transaction=tx[i.card_transaction_id], installment_seq=i.installment_seq,
                           principal_amount=i.principal_amount)
               for i in sorted(items, key=lambda i: tx[i.card_transaction_id].transacted_at, reverse=True)])
