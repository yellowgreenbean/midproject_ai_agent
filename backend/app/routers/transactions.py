"""거래내역 조회 API — 기획서 Part 5 10장 「입출금 내역 조회」, 16장 API 초안.

- 조회 조건: 기간(start_date ~ end_date), 유형(direction = IN 입금만 / OUT 출금만), 20건씩(무한스크롤 → 커서)
- 기간 기본값(1개월)은 화면이 정해서 보낸다. 서버는 기간이 없으면 전체를 준다.
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from sqlalchemy import and_, or_, select

from app.common.ownership import get_owned_account_or_404
from app.deps import DB, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, Transaction
from app.rules import INCOMING_TYPES
from app.schemas import TransactionOut, TransactionPage

router = APIRouter(tags=["transactions"])


@router.get("/accounts/{accountId}/transactions", response_model=TransactionPage)
def list_transactions(
    account_id: Annotated[str, Path(alias="accountId")],
    db: DB,
    user_id: CurrentUserId,
    start_date: Annotated[date | None, Query(description="이 날짜부터 (YYYY-MM-DD)")] = None,
    end_date: Annotated[date | None, Query(description="이 날짜까지, 그날 포함 (YYYY-MM-DD)")] = None,
    direction: Annotated[Literal["IN", "OUT"] | None, Query(description="IN 입금만 / OUT 출금만")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(description="이전 응답의 next_cursor")] = None,
):
    get_owned_account_or_404(db, account_id, user_id)
    if start_date and end_date and start_date > end_date:
        raise ApiError(400, "INVALID_PERIOD", "조회 시작일이 종료일보다 늦어요.")

    stmt = select(Transaction).where(Transaction.account_id == account_id)
    if start_date:
        stmt = stmt.where(Transaction.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        stmt = stmt.where(Transaction.created_at < datetime.combine(end_date + timedelta(days=1), time.min))
    if direction == "IN":
        stmt = stmt.where(Transaction.type.in_(INCOMING_TYPES))
    elif direction == "OUT":
        stmt = stmt.where(Transaction.type.not_in(INCOMING_TYPES))

    if cursor:
        # 커서 = 이전 페이지의 마지막 거래 id. 그 거래보다 "더 옛날" 것만 가져온다.
        last = db.scalar(
            select(Transaction).where(Transaction.id == cursor, Transaction.account_id == account_id)
        )
        if last is None:
            raise ApiError(400, "INVALID_CURSOR", "목록을 처음부터 다시 불러와 주세요.")
        stmt = stmt.where(
            or_(
                Transaction.created_at < last.created_at,
                and_(Transaction.created_at == last.created_at, Transaction.id < last.id),
            )
        )

    # 최신순. 같은 시각 거래(예: 10/14 06:00 카드대금 2건)는 id 가 큰 쪽이 나중 거래다
    # (더미 적재가 오래된 것부터 번호를 매김 — balance_after 순서와 같음).
    rows = db.scalars(
        stmt.order_by(Transaction.created_at.desc(), Transaction.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    return TransactionPage(
        items=[TransactionOut.model_validate(t) for t in items],
        next_cursor=items[-1].id if has_more else None,
    )


# 거래 상세 — transactions 에는 user_id 가 없으므로 accounts 를 JOIN 해 소유권을 확인한다.
@router.get("/transactions/{transactionId}", response_model=TransactionOut)
def get_transaction(transaction_id: Annotated[str, Path(alias="transactionId")], db: DB, user_id: CurrentUserId):
    # SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id
    # WHERE t.id = :transaction_id AND a.user_id = :user_id
    tx = db.scalar(
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.id == transaction_id, Account.user_id == user_id)
    )
    if tx is None:
        raise not_found("TRANSACTION_NOT_FOUND", "거래를 찾을 수 없어요.")
    return tx
