from fastapi import APIRouter
from sqlalchemy import select

from app.crud import get_owned_or_404
from app.deps import DB, CurrentUserId
from app.models import ScheduledTransfer, Transfer
from app.schemas import ScheduledTransferOut, TransferOut

router = APIRouter(tags=["transfers"])


# [FK 목록] 내가 요청한 이체, 최신순
@router.get("/me/transfers", response_model=list[TransferOut])
def list_my_transfers(db: DB, user_id: CurrentUserId):
    return db.scalars(
        select(Transfer)
        .where(Transfer.user_id == user_id)
        .order_by(Transfer.requested_at.desc(), Transfer.id.desc())
    ).all()


# [PK 단건] 이체 하나
@router.get("/transfers/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: str, db: DB, user_id: CurrentUserId):
    return get_owned_or_404(db, Transfer, transfer_id, user_id, "이체")


# [FK 목록] 내 예약 이체
@router.get("/me/scheduled-transfers", response_model=list[ScheduledTransferOut])
def list_my_scheduled_transfers(db: DB, user_id: CurrentUserId):
    return db.scalars(
        select(ScheduledTransfer)
        .where(ScheduledTransfer.user_id == user_id)
        .order_by(ScheduledTransfer.created_at.desc(), ScheduledTransfer.id.desc())
    ).all()


# [PK 단건] 예약 이체 하나
@router.get("/scheduled-transfers/{scheduled_transfer_id}", response_model=ScheduledTransferOut)
def get_scheduled_transfer(scheduled_transfer_id: str, db: DB, user_id: CurrentUserId):
    return get_owned_or_404(db, ScheduledTransfer, scheduled_transfer_id, user_id, "예약 이체")
