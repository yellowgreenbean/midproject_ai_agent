"""키로 한 건 찾기 + 내 것인지 확인하는 공통 함수.

남의 것이거나 없으면 똑같이 404 를 준다. 403 을 주면 "그 키는 있다"는 정보가 새어 나간다(Part 2 ACCT-F02).
"""

from typing import TypeVar

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.errors import ApiError, account_not_found
from app.models import Account, Base

M = TypeVar("M", bound=Base)


def get_owned_or_404(db: Session, model: type[M], pk: str, user_id: str, error: ApiError) -> M:
    """SELECT * FROM <table> WHERE <pk> = :pk AND user_id = :user_id"""
    pk_col = inspect(model).primary_key[0]
    obj = db.scalar(select(model).where(pk_col == pk, model.user_id == user_id))
    if obj is None:
        raise error
    return obj


def get_owned_account_or_404(db: Session, account_id: str, user_id: str) -> Account:
    """계좌에 딸린 표(잔액·거래·한도)를 읽기 전에 부모 계좌가 내 것인지 먼저 확인한다."""
    return get_owned_or_404(db, Account, account_id, user_id, account_not_found())
