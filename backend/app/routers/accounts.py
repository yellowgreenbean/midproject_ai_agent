"""계좌 파트 조회 API — 기획서 Part 2 9장 (ACCT-F02 계좌 조회, ACCT-F03 잔액 조회, ACCT-F07 필터).

잔액은 거래 파트의 account_balances 를 직접 읽지 않고 account_balance_view 로만 읽는다(C-5 「계좌 잔액」).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from sqlalchemy import select

from app.deps import DB, CurrentUserId
from app.errors import ApiError, account_not_found
from app.models import Account, AccountBalanceView
from app.schemas import AccountOut, BalanceOut

router = APIRouter(tags=["accounts"])

AccountId = Annotated[str, Path(alias="accountId")]
AccountStatus = Literal[Account.LIFECYCLE_STATUS_VALUES]  # type: ignore[valid-type]  # ACTIVE / SUSPENDED / CLOSED
AccountType = Literal[Account.ACCOUNT_TYPE_VALUES]  # type: ignore[valid-type]  # CHECKING / SAVINGS


def balance_unavailable() -> ApiError:
    # 잔액 원본이 없을 때 0원 같은 값으로 둔갑시키지 않는다(ACCT-F03 처리 규칙)
    return ApiError(503, "BALANCE_UNAVAILABLE", "잔액을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")


def _account_out(account: Account, balance: AccountBalanceView | None) -> AccountOut:
    if balance is None:
        raise balance_unavailable()
    return AccountOut(
        **{f: getattr(account, f) for f in AccountOut.model_fields if hasattr(account, f)},
        resAccountCurrency=balance.resAccountCurrency,
        resAccountBalance=balance.resAccountBalance,
        balance_as_of=balance.balance_as_of,
    )


def _with_balance():
    # SELECT a.*, v.* FROM accounts a LEFT JOIN account_balance_view v ON v.account_id = a.id
    return select(Account, AccountBalanceView).outerjoin(
        AccountBalanceView, AccountBalanceView.account_id == Account.id
    )


# ACCT-F02 · F07: 내 계좌 목록 (+ 잔액)
@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    db: DB,
    user_id: CurrentUserId,
    status: Annotated[AccountStatus | None, Query(description="없으면 해지(CLOSED)를 뺀 계좌")] = None,
    type: Annotated[AccountType | None, Query()] = None,
):
    stmt = _with_balance().where(Account.user_id == user_id)
    if status is None:
        # 해지 계좌는 기본 목록에서 분리해 이력으로만 본다(ACCT-F02 정상 흐름 5) → ?status=CLOSED
        stmt = stmt.where(Account.lifecycle_status != "CLOSED")
    else:
        stmt = stmt.where(Account.lifecycle_status == status)
    if type is not None:
        stmt = stmt.where(Account.account_type == type)
    rows = db.execute(stmt.order_by(Account.is_favorite.desc(), Account.id)).all()
    return [_account_out(a, b) for a, b in rows]


# ACCT-F02: 계좌 상세 (+ 잔액)
@router.get("/accounts/{accountId}", response_model=AccountOut)
def get_account(account_id: AccountId, db: DB, user_id: CurrentUserId):
    row = db.execute(_with_balance().where(Account.id == account_id, Account.user_id == user_id)).first()
    if row is None:
        raise account_not_found()
    return _account_out(*row)


# ACCT-F03: 잔액만 (읽기 전용)
@router.get("/accounts/{accountId}/balance", response_model=BalanceOut)
def get_balance(account_id: AccountId, db: DB, user_id: CurrentUserId):
    row = db.execute(_with_balance().where(Account.id == account_id, Account.user_id == user_id)).first()
    if row is None:
        raise account_not_found()
    if row[1] is None:
        raise balance_unavailable()
    return row[1]
