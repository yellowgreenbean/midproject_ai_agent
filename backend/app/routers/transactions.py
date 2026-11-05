from fastapi import APIRouter
from sqlalchemy import select

from app.crud import not_found
from app.deps import DB, CurrentUserId
from app.models import Account, Transaction
from app.schemas import TransactionOut

router = APIRouter(tags=["transactions"])


# [PK 단건, 자식 → 부모 소유권] transactions 에는 user_id 가 없으므로 accounts 를 JOIN 해 확인한다.
@router.get("/transactions/{tx_id}", response_model=TransactionOut)
def get_transaction(tx_id: str, db: DB, user_id: CurrentUserId):
    # SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id
    # WHERE t.id = :tx_id AND a.user_id = :user_id
    tx = db.scalar(
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.id == tx_id, Account.user_id == user_id)
    )
    if tx is None:
        raise not_found("거래")
    return tx
