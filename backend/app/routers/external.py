from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.crud import not_found
from app.deps import DB, CurrentUserId
from app.models import ExternalAccount
from app.schemas import ExternalAccountLookupOut

router = APIRouter(tags=["external-accounts"])


# [UK 조회] PK 가 아닌 고유 조합(bank + account_no)으로 예금주를 찾는다. 송금 전 받는 사람 확인용.
@router.get("/external-accounts/lookup", response_model=ExternalAccountLookupOut)
def lookup_external_account(
    db: DB,
    _user_id: CurrentUserId,  # 로그인한 사람만 조회 가능
    bank: Annotated[str, Query(min_length=1)],
    account_no: Annotated[str, Query(pattern=r"^\d{6,20}$")],
):
    found = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.bank == bank, ExternalAccount.account_no == account_no
        )
    )
    if found is None:
        raise not_found("계좌")
    return found
