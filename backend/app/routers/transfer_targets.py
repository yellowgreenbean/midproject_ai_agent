"""이체 대상 계좌 확인 — 기획서 Part 5 16장 GET /transfer-targets/verify, 11장 「타행 이체(가상 타행)」.

- 두린은행(우리 서비스) 계좌: accounts."resAccount" 로 찾고, 예금주는 그 계좌 주인의 이름
- 다른 은행: 시드 external_accounts 의 (bank, account_no) 로 찾는다(실제 타행 연동 없음)
- 계좌번호 자릿수는 고른 은행 기준으로만 검사한다(두린은행·신한은행 앞자리가 같은 110 이라 앞자리로 가리지 않음)
- amount 를 주면 재확인 화면의 금액 오입력 경고(4장)를, 같은 받는 분에게 처리중 이체가 있으면 그 건(9장)을 같이 준다
"""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.common.ownership import get_owned_account_or_404
from app.deps import DB, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, ExternalAccount, Transfer, User
from app.rules import (
    BANK_ACCOUNT_DIGITS,
    OUR_BANK,
    RECENT_TARGETS_MAX,
    WARN_FIRST_LARGE,
    WARN_RECENT_SAME,
    WARN_USUAL_MULTIPLE,
    now_kst,
)
from app.common.naming import KstDatetime, Money
from app.schemas import TransferTargetOut

router = APIRouter(tags=["transfer-targets"])


def find_target(db, user_id: str, bank: str, account_no: str) -> tuple[Account | None, str, bool]:
    """(두린은행 계좌 또는 None(타행), 예금주, 내 계좌인지). 이체·예약·자주 쓰는 계좌 등록이 같이 쓴다."""
    digits = BANK_ACCOUNT_DIGITS.get(bank)
    if digits is None:
        raise ApiError(400, "UNSUPPORTED_BANK", "보낼 수 없는 은행이에요.")
    if not (account_no.isascii() and account_no.isdigit()) or len(account_no) != digits:
        raise ApiError(400, "INVALID_ACCOUNT_NUMBER", "계좌번호 자릿수를 확인해 주세요.")
    target_not_found = not_found("TRANSFER_TARGET_NOT_FOUND", "계좌번호를 다시 확인해 주세요.")
    if bank == OUR_BANK:
        row = db.execute(select(Account, User.name).join(User, User.id == Account.user_id)
                         .where(Account.resAccount == account_no)).first()
        if row is None:
            raise target_not_found
        return row[0], row[1], row[0].user_id == user_id
    ext = db.scalar(select(ExternalAccount).where(ExternalAccount.bank == bank, ExternalAccount.account_no == account_no))
    if ext is None:
        raise target_not_found
    # 가상 타행은 회원 id 가 없어 예금주 이름이 같으면 본인 명의로 본다(탈퇴 정리용 본인 계좌, 시드)
    return None, ext.holder_name, ext.holder_name == db.scalar(select(User.name).where(User.id == user_id))


class PendingTransferOut(BaseModel):
    amount: Money
    requested_at: KstDatetime


class VerifyOut(TransferTargetOut):
    account_display: str  # 두린은행은 하이픈 넣은 번호, 타행은 번호 그대로
    warnings: list[str]  # FIRST_LARGE · LARGE_VS_USUAL · RECENT_SAME · PENDING_SAME (4·9장)
    pending_transfer: PendingTransferOut | None  # 같은 받는 분에게 아직 처리중인 이체 (9장 — 재확인 화면에 금액·시각)


def _warnings(db, user_id: str, bank: str, account_no: str, amount: int | None) -> tuple[list[str], Transfer | None]:
    mine = (Transfer.user_id == user_id, Transfer.to_bank == bank, Transfer.to_account_no == account_no)
    pending = db.scalar(select(Transfer).where(*mine, Transfer.status == "PENDING").order_by(Transfer.requested_at.desc()))
    warnings = ["PENDING_SAME"] if pending else []
    if amount:
        count, avg = db.execute(select(func.count(), func.avg(Transfer.amount))
                                .where(*mine, Transfer.status == "SUCCESS")).one()
        if count == 0 and amount >= WARN_FIRST_LARGE:
            warnings.append("FIRST_LARGE")
        if count and amount >= avg * WARN_USUAL_MULTIPLE:
            warnings.append("LARGE_VS_USUAL")
        if db.scalar(select(Transfer.id).where(*mine, Transfer.amount == amount, Transfer.status.in_(("SUCCESS", "PENDING")),
                                               Transfer.requested_at >= now_kst() - WARN_RECENT_SAME).limit(1)):
            warnings.append("RECENT_SAME")
    return warnings, pending


@router.get("/transfer-targets/verify", response_model=VerifyOut)
def verify_transfer_target(
    db: DB,
    user_id: CurrentUserId,
    bank: Annotated[str, Query(description="받는 은행 (Part 5 11장 목록)")],
    account_no: Annotated[str, Query(description="숫자만")],
    from_account_id: Annotated[str | None, Query(description="출금 계좌 — 주면 같은 계좌로 보내는지 막는다")] = None,
    amount: Annotated[int | None, Query(ge=1, description="주면 재확인 화면 금액 경고도 계산")] = None,
):
    dst, holder, mine = find_target(db, user_id, bank, account_no)
    if from_account_id is not None:
        get_owned_account_or_404(db, from_account_id, user_id)
        if dst is not None and dst.id == from_account_id:
            raise ApiError(400, "SAME_ACCOUNT", "같은 계좌로는 이체할 수 없어요.")
    warnings, pending = _warnings(db, user_id, bank, account_no, amount)
    return VerifyOut(
        bank=bank, account_no=account_no, holder_name=holder, is_mine=mine,
        account_status=dst.lifecycle_status if dst else "ACTIVE",  # 가상 타행은 늘 정상
        account_display=dst.resAccountDisplay if dst else account_no, warnings=warnings,
        pending_transfer=PendingTransferOut(amount=pending.amount, requested_at=pending.requested_at) if pending else None,
    )


class RecentTargetOut(BaseModel):
    id: None = None  # 화면 SavedTarget — 최근 보낸 계좌는 id 가 없다(자주 쓰는 계좌만 있음)
    account_no: str
    account_display: str
    holder_name: str
    nickname: None = None


# Part 5 6장 간편 송금 「최근 보낸 계좌」 — 성공한 이체의 받는 계좌, 같은 계좌는 한 번, 최근 10개.
# 「목록에서 숨기기」는 저장할 표가 없어 뺐다(사용자 결정 2026-11-10)
@router.get("/transfer-targets/recent", response_model=list[RecentTargetOut])
def recent_transfer_targets(db: DB, user_id: CurrentUserId):
    # shortcut: 두린은행 계좌만 — 화면의 간편 송금 목록에 은행 칸이 없어서. 화면에 은행을 붙이면 타행도 넣는다
    last = func.max(Transfer.requested_at)
    rows = db.execute(
        select(Transfer.to_account_no, Transfer.to_holder_name, Account.resAccountDisplay)
        .outerjoin(Account, Account.resAccount == Transfer.to_account_no)
        .where(Transfer.user_id == user_id, Transfer.status == "SUCCESS", Transfer.to_bank == OUR_BANK)
        .group_by(Transfer.to_account_no, Transfer.to_holder_name, Account.resAccountDisplay)
        .order_by(last.desc()).limit(RECENT_TARGETS_MAX)).all()
    return [RecentTargetOut(account_no=no, account_display=disp or no, holder_name=name) for no, name, disp in rows]
