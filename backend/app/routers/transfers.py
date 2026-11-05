"""이체 결과·예약·한도 조회 API — 기획서 Part 5 16장.

이체 실행(POST /transfers)·예약 등록/변경/취소·한도 변경은 본인 확인(step_up_challenges)이 필요해
로그인(AUTH-F05)과 본인 확인(POST /auth/step-up)이 생긴 뒤에 만든다.
"""

from datetime import datetime, time
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from sqlalchemy import func, select

from app.crud import get_owned_account_or_404, get_owned_or_404
from app.deps import DB, CurrentUserId
from app.errors import not_found
from app.models import ScheduledTransfer, Transfer, TransferLimit
from app.rules import (
    DEFAULT_DAILY_LIMIT,
    DEFAULT_PER_TRANSFER_LIMIT,
    LIMIT_COUNTED_TRANSFER_STATUSES,
    now_kst,
)
from app.schemas import ScheduledTransferOut, TransferLimitOut, TransferOut

router = APIRouter(tags=["transfers"])

TransferStatus = Literal[Transfer.STATUS_VALUES]  # type: ignore[valid-type]  # PENDING / SUCCESS / FAILED


# 이체 결과 목록 (상태 필터), 최신순
@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    db: DB,
    user_id: CurrentUserId,
    status: Annotated[TransferStatus | None, Query()] = None,
):
    stmt = select(Transfer).where(Transfer.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Transfer.status == status)
    return db.scalars(stmt.order_by(Transfer.requested_at.desc(), Transfer.id.desc())).all()


@router.get("/transfers/{transferId}", response_model=TransferOut)
def get_transfer(transfer_id: Annotated[str, Path(alias="transferId")], db: DB, user_id: CurrentUserId):
    return get_owned_or_404(
        db, Transfer, transfer_id, user_id, not_found("TRANSFER_NOT_FOUND", "이체 내역을 찾을 수 없어요.")
    )


# 예약 송금·자동이체 목록 (취소된 예약 포함 — Part 5 10장 「이체 결과」 탭)
@router.get("/scheduled-transfers", response_model=list[ScheduledTransferOut])
def list_scheduled_transfers(db: DB, user_id: CurrentUserId):
    return db.scalars(
        select(ScheduledTransfer)
        .where(ScheduledTransfer.user_id == user_id)
        .order_by(ScheduledTransfer.created_at.desc(), ScheduledTransfer.id.desc())
    ).all()


@router.get("/scheduled-transfers/{scheduledTransferId}", response_model=ScheduledTransferOut)
def get_scheduled_transfer(
    scheduled_transfer_id: Annotated[str, Path(alias="scheduledTransferId")], db: DB, user_id: CurrentUserId
):
    return get_owned_or_404(
        db,
        ScheduledTransfer,
        scheduled_transfer_id,
        user_id,
        not_found("SCHEDULED_TRANSFER_NOT_FOUND", "예약 이체를 찾을 수 없어요."),
    )


# 이체 한도와 오늘 남은 한도
@router.get("/accounts/{accountId}/transfer-limits", response_model=TransferLimitOut)
def get_transfer_limits(account_id: Annotated[str, Path(alias="accountId")], db: DB, user_id: CurrentUserId):
    get_owned_account_or_404(db, account_id, user_id)
    limit = db.get(TransferLimit, account_id)

    # 오늘(한국 날짜 0시부터) 이 계좌에서 나간 이체 금액 — 예약·자동이체로 실행된 것도 포함(Part 5 4장)
    today_start = datetime.combine(now_kst().date(), time.min)
    used = db.scalar(
        select(func.coalesce(func.sum(Transfer.amount), 0)).where(
            Transfer.from_account_id == account_id,
            Transfer.status.in_(LIMIT_COUNTED_TRANSFER_STATUSES),
            Transfer.requested_at >= today_start,
        )
    )
    daily = limit.daily_limit if limit else DEFAULT_DAILY_LIMIT
    return TransferLimitOut(
        account_id=account_id,
        per_transfer_limit=limit.per_transfer_limit if limit else DEFAULT_PER_TRANSFER_LIMIT,
        daily_limit=daily,
        used_today=used,
        remaining_today=max(daily - used, 0),
        is_default=limit is None,
        updated_at=limit.updated_at if limit else None,
    )
