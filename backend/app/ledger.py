"""잔액을 바꾸는 모든 일의 공통 순서 — 기획서 Part 5 14장 「데이터 정합성」.

    1. lock_balances(): 관련 계좌의 잔액 행을 계좌 id 가 작은 것부터 FOR UPDATE 로 잠근다(데드락 방지)
    2. 잠근 채로 잔액·상태를 확인한다(부르는 쪽)
    3. post(): 원장(transactions)에 한 줄 쓰고 잔액을 바꾼다 — 같은 트랜잭션, 커밋은 부르는 쪽

이체(TRANSFER_OUT/IN) · 예금·적금 중도 해지(SUBSCRIPTION_PAYOUT) · 카드 대금(CARD_PAYMENT)이 모두 이걸 쓴다.
다른 파트는 잔액(account_balances)을 직접 고치지 않는다(Part 5 2장).
"""

from datetime import datetime

from sqlalchemy import select

from app.models import AccountBalance, Transaction
from app.rules import INCOMING_TYPES
from app.security import new_id


def lock_balances(db, account_ids) -> dict[str, AccountBalance]:
    ids = sorted(set(account_ids))
    rows = db.scalars(select(AccountBalance).where(AccountBalance.account_id.in_(ids))
                      .order_by(AccountBalance.account_id).with_for_update())
    return {b.account_id: b for b in rows}


def post(db, bal: AccountBalance, type: str, amount: int, now: datetime, **fields) -> Transaction:
    """원장 한 줄 + 잔액 변경. 출금이면 잔액이 모자라지 않은지 부르는 쪽이 먼저 확인한다(여기선 음수만 막음)."""
    bal.balance += amount if type in INCOMING_TYPES else -(amount + fields.get("fee", 0))
    if bal.balance < 0:
        raise ValueError("잔액이 음수가 될 수 없음")  # 부르는 쪽 확인이 빠졌다는 뜻 — 트랜잭션째 실패시킨다
    bal.updated_at = now
    tx = Transaction(id=new_id("tx"), account_id=bal.account_id, type=type, amount=amount,
                     balance_after=bal.balance, created_at=now, **fields)
    db.add(tx)
    return tx
