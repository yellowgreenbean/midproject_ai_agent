"""이체 대상 계좌 확인 — 기획서 Part 5 16장 GET /transfer-targets/verify, 11장 「타행 이체(가상 타행)」.

- 두린은행(우리 서비스) 계좌: accounts."resAccount" 로 찾고, 예금주는 그 계좌 주인의 이름
- 다른 은행: 시드 external_accounts 의 (bank, account_no) 로 찾는다(실제 타행 연동 없음)
- 계좌번호 자릿수는 고른 은행 기준으로만 검사한다(두린은행·신한은행 앞자리가 같은 110 이라 앞자리로 가리지 않음)
"""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.deps import DB, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, ExternalAccount, Transfer, User
from app.rules import BANK_ACCOUNT_DIGITS, OUR_BANK
from app.schemas import TransferTargetOut

router = APIRouter(tags=["transfer-targets"])


@router.get("/transfer-targets/verify", response_model=TransferTargetOut)
def verify_transfer_target(
    db: DB,
    user_id: CurrentUserId,
    bank: Annotated[str, Query(description="받는 은행 (Part 5 11장 목록)")],
    account_no: Annotated[str, Query(description="숫자만")],
):
    digits = BANK_ACCOUNT_DIGITS.get(bank)
    if digits is None:
        raise ApiError(400, "UNSUPPORTED_BANK", "보낼 수 없는 은행이에요.")
    if not (account_no.isascii() and account_no.isdigit()) or len(account_no) != digits:
        raise ApiError(400, "INVALID_ACCOUNT_NUMBER", "계좌번호 자릿수를 확인해 주세요.")

    target_not_found = not_found("TRANSFER_TARGET_NOT_FOUND", "계좌번호를 다시 확인해 주세요.")
    if bank == OUR_BANK:
        row = db.execute(
            select(Account, User.name)
            .join(User, User.id == Account.user_id)
            .where(Account.resAccount == account_no)
        ).first()
        if row is None:
            raise target_not_found
        account, holder = row
        return TransferTargetOut(
            bank=bank,
            account_no=account_no,
            holder_name=holder,
            account_status=account.lifecycle_status,
            is_mine=account.user_id == user_id,
        )

    ext = db.scalar(
        select(ExternalAccount).where(ExternalAccount.bank == bank, ExternalAccount.account_no == account_no)
    )
    if ext is None:
        raise target_not_found
    my_name = db.scalar(select(User.name).where(User.id == user_id))
    return TransferTargetOut(  # 가상 타행은 회원 id 가 없어 예금주 이름이 같으면 본인 명의로 본다(탈퇴 정리용 본인 계좌, 시드)
        bank=bank, account_no=account_no, holder_name=ext.holder_name, account_status="ACTIVE",
        is_mine=ext.holder_name == my_name,
    )


class RecentTargetOut(BaseModel):
    id: None = None  # 화면 SavedTarget — 최근 보낸 계좌는 id 가 없다(자주 쓰는 계좌만 있음)
    account_no: str
    account_display: str
    holder_name: str
    nickname: None = None


# Part 5 6장 간편 송금 「최근 보낸 계좌」 — 성공한 이체의 받는 계좌, 같은 계좌는 한 번, 최근 20개
@router.get("/transfer-targets/recent", response_model=list[RecentTargetOut])
def recent_transfer_targets(db: DB, user_id: CurrentUserId):
    # shortcut: 두린은행 계좌만 — 화면의 간편 송금 목록에 은행 칸이 없어서. 화면에 은행을 붙이면 타행도 넣는다
    rows = db.execute(
        select(Transfer.to_account_no, Transfer.to_holder_name, func.max(Transfer.requested_at).label("last"))
        .where(Transfer.user_id == user_id, Transfer.status == "SUCCESS", Transfer.to_bank == OUR_BANK)
        .group_by(Transfer.to_account_no, Transfer.to_holder_name).order_by(func.max(Transfer.requested_at).desc())
        .limit(20)).all()
    return [RecentTargetOut(account_no=no, account_display=no, holder_name=name) for no, name, _ in rows]
