from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import and_, or_, select

from app.crud import get_owned_account_or_404, not_found
from app.deps import DB, CurrentUserId
from app.models import Account, AccountBalance, AccountBalanceView, Transaction, TransferLimit
from app.schemas import (
    AccountBalanceViewOut,
    AccountOut,
    AccountWithBalanceOut,
    TransactionOut,
    TransactionPage,
    TransferLimitOut,
)

router = APIRouter(tags=["accounts"])


def _with_balance(account: Account, balance: AccountBalance) -> AccountWithBalanceOut:
    """JOIN 한 두 행(계좌 + 잔액)을 응답 하나로 합친다."""
    base = AccountOut.model_validate(account).model_dump()
    return AccountWithBalanceOut(**base, currency=balance.currency, balance=balance.balance)


# [FK 목록] 내 계좌 전체 + 잔액 (1:1 JOIN)
@router.get("/me/accounts", response_model=list[AccountWithBalanceOut])
def list_my_accounts(db: DB, user_id: CurrentUserId):
    # SELECT a.*, b.* FROM accounts a JOIN account_balances b ON b.account_id = a.id
    # WHERE a.user_id = :user_id ORDER BY a.is_favorite DESC, a.id
    rows = db.execute(
        select(Account, AccountBalance)
        .join(AccountBalance, AccountBalance.account_id == Account.id)
        .where(Account.user_id == user_id)
        .order_by(Account.is_favorite.desc(), Account.id)
    ).all()
    return [_with_balance(a, b) for a, b in rows]


# [PK 단건 + JOIN] 계좌 하나
@router.get("/accounts/{account_id}", response_model=AccountWithBalanceOut)
def get_account(account_id: str, db: DB, user_id: CurrentUserId):
    row = db.execute(
        select(Account, AccountBalance)
        .join(AccountBalance, AccountBalance.account_id == Account.id)
        .where(Account.id == account_id, Account.user_id == user_id)
    ).first()
    if row is None:
        raise not_found("계좌")
    return _with_balance(*row)


# [1:1, PK=FK] 잔액 — 계좌 파트용 보기(view) account_balance_view 로 읽는다
@router.get("/accounts/{account_id}/balance", response_model=AccountBalanceViewOut)
def get_balance(account_id: str, db: DB, user_id: CurrentUserId):
    get_owned_account_or_404(db, account_id, user_id)
    view = db.get(AccountBalanceView, account_id)  # SELECT * FROM account_balance_view WHERE account_id = ?
    if view is None:
        raise not_found("잔액")
    return view


# [1:1, PK=FK] 이체 한도
@router.get("/accounts/{account_id}/transfer-limit", response_model=TransferLimitOut)
def get_transfer_limit(account_id: str, db: DB, user_id: CurrentUserId):
    get_owned_account_or_404(db, account_id, user_id)
    limit = db.get(TransferLimit, account_id)
    if limit is None:
        raise not_found("이체 한도")
    return limit


# [FK 목록 + 커서 페이징] 계좌의 거래 내역, 최신순
@router.get("/accounts/{account_id}/transactions", response_model=TransactionPage)
def list_transactions(
    account_id: str,
    db: DB,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(description="이전 응답의 next_cursor")] = None,
):
    get_owned_account_or_404(db, account_id, user_id)

    stmt = select(Transaction).where(Transaction.account_id == account_id)

    if cursor:
        # 커서 = 이전 페이지의 마지막 거래 id. 그 거래보다 "더 옛날" 것만 가져온다.
        last = db.scalar(
            select(Transaction).where(Transaction.id == cursor, Transaction.account_id == account_id)
        )
        if last is None:
            raise not_found("커서")
        stmt = stmt.where(
            or_(
                Transaction.created_at < last.created_at,
                and_(Transaction.created_at == last.created_at, Transaction.id < last.id),
            )
        )

    # 한 개 더 읽어서 다음 페이지가 있는지 본다.
    rows = db.scalars(
        stmt.order_by(Transaction.created_at.desc(), Transaction.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    return TransactionPage(
        items=[TransactionOut.model_validate(t) for t in items],
        next_cursor=items[-1].id if has_more else None,
    )
