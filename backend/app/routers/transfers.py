"""이체 결과·예약·한도 API — 기획서 Part 5 16장.

    POST   /transfers                                   이체 실행 (본인 확인 TRANSFER, Idempotency-Key 필수)
    DELETE /scheduled-transfers/{scheduledTransferId}   예약 송금 취소·자동이체 해지 (본인 확인 SCHEDULED_TRANSFER)
    그 밖은 조회. 예약 등록·변경, 한도 변경은 아직 없다.

이체 실행 순서 (Part 5 4·9·11·14장)
  1. 같은 Idempotency-Key 로 이미 처리했으면 그 결과를 그대로 돌려준다(버튼 두 번 → 한 번만)
  2. 입력 검사(은행·자릿수·금액) → 받는 계좌 찾기(두린은행 accounts / 다른 은행 external_accounts) → 같은 계좌 막기
  3. 본인 확인 번호 사용 · RESTRICTED 회원은 본인 명의 계좌로만(Part 1 7.3)
  4. 잔액 행을 계좌 id 순서로 잠그고(ledger.lock_balances) 상태·한도·잔액 확인
     → 걸리면 FAILED + 사유로 기록(원장 없음). 통과하면 SUCCESS + 원장(두린은행: 출금·입금 / 다른 은행: 출금만)
  다른 은행은 시험용 예금주 「임처리」면 PENDING(10분 뒤 app/jobs.py 가 확정), 「오실패」면 FAILED (11장).
  타행 이체는 기획서 2차(TRX-F08)지만 회원 탈퇴 정리(남은 돈을 본인 명의 타행 계좌로)를 위해 앞당겼다(사용자 결정 2026-11-09).
"""

from datetime import datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import ledger
from app.crud import get_owned_account_or_404, get_owned_or_404
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, account_not_found, not_found
from app.models import Account, ExternalAccount, ScheduledTransfer, Transfer, TransferLimit, User
from app.routers.auth import consume_step_up
from app.rules import (
    BANK_ACCOUNT_DIGITS,
    DEFAULT_DAILY_LIMIT,
    DEFAULT_PER_TRANSFER_LIMIT,
    EXTERNAL_FAIL_HOLDER,
    EXTERNAL_PENDING_HOLDER,
    LIMIT_COUNTED_TRANSFER_STATUSES,
    OUR_BANK,
    TRANSFER_FAILURE_MESSAGES,
    TRANSFER_NAME_MAX,
    now_kst,
)
from app.schemas import Money, ScheduledTransferOut, TransferLimitOut, TransferOut
from app.security import new_id

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

    used = used_today(db, account_id)
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


def used_today(db, account_id: str) -> int:
    """오늘(한국 날짜 0시부터) 이 계좌에서 나간 이체 금액 — 예약·자동이체·처리중도 포함(Part 5 4장)."""
    today_start = datetime.combine(now_kst().date(), time.min)
    return db.scalar(select(func.coalesce(func.sum(Transfer.amount), 0)).where(
        Transfer.from_account_id == account_id, Transfer.status.in_(LIMIT_COUNTED_TRANSFER_STATUSES),
        Transfer.requested_at >= today_start))


# --- 이체 실행 ---------------------------------------------------------------------------------
class TransferIn(BaseModel):
    from_account_id: str = Field(max_length=40)
    to_bank: str = Field(max_length=30)
    to_account_no: str = Field(max_length=20)
    amount: str = Field(max_length=15)  # 금액은 문자열(C-5)
    step_up_challenge_id: str = Field(max_length=40)
    my_display_name: str | None = Field(default=None, max_length=TRANSFER_NAME_MAX)  # 내 통장에 보일 이름
    their_display_name: str | None = Field(default=None, max_length=TRANSFER_NAME_MAX)  # 받는 분 통장에 보일 이름


class TransferResultOut(TransferOut):
    """화면(송금 → 결과 화면)이 바로 그리도록 표시용 칸을 더한 이체 결과."""
    from_account_display: str
    to_account_display: str
    balance_after: Money | None  # 성공했을 때 내 계좌 잔액
    message: str | None  # 실패 안내 (Part 5 9장)


def _result(db, t: Transfer, balance_after: int | None = None) -> TransferResultOut:
    from_display = db.scalar(select(Account.resAccountDisplay).where(Account.id == t.from_account_id))
    return TransferResultOut(**TransferOut.model_validate(t).model_dump(), from_account_display=from_display,
                             to_account_display=t.to_account_no, balance_after=balance_after,
                             message=TRANSFER_FAILURE_MESSAGES.get(t.failure_reason or ""))


@router.post("/transfers", response_model=TransferResultOut, status_code=201)
def create_transfer(body: TransferIn, login: CurrentLogin, db: DB,
                    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]):
    user = login.user
    # 1. 멱등성 — 같은 키면 처음 결과 (shortcut: 같은 키가 동시에 오면 둘째는 DB 고유 제약에 걸려 500, 돈은 한 번만 나감)
    prev = db.scalar(select(Transfer).where(Transfer.idempotency_key == idempotency_key))
    if prev is not None:
        if prev.user_id != user.id:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 쓴 요청 번호예요. 다시 시도해 주세요.")
        return _result(db, prev)

    # 2. 입력 · 받는 계좌
    if not (body.amount.isascii() and body.amount.isdigit()) or int(body.amount) < 1:
        raise ApiError(400, "INVALID_AMOUNT", "1원 이상 입력해 주세요.")
    amount = int(body.amount)
    digits = BANK_ACCOUNT_DIGITS.get(body.to_bank)
    if digits is None:
        raise ApiError(400, "UNSUPPORTED_BANK", "보낼 수 없는 은행이에요.")
    if not (body.to_account_no.isascii() and body.to_account_no.isdigit()) or len(body.to_account_no) != digits:
        raise ApiError(400, "INVALID_ACCOUNT_NUMBER", "계좌번호 자릿수를 확인해 주세요.")
    src = db.scalar(select(Account).where(Account.id == body.from_account_id, Account.user_id == user.id))
    if src is None:
        raise account_not_found()
    dst = None
    if body.to_bank == OUR_BANK:
        dst = db.scalar(select(Account).where(Account.resAccount == body.to_account_no))
        holder = dst and db.scalar(select(User.name).where(User.id == dst.user_id))
        mine = dst is not None and dst.user_id == user.id
    else:
        ext = db.scalar(select(ExternalAccount).where(ExternalAccount.bank == body.to_bank,
                                                      ExternalAccount.account_no == body.to_account_no))
        holder = ext and ext.holder_name
        mine = holder == user.name  # 가상 타행은 회원 id 가 없어 예금주 이름으로 본인 명의를 가린다
    if not holder:
        raise not_found("TRANSFER_TARGET_NOT_FOUND", "계좌번호를 다시 확인해 주세요.")
    if dst is not None and dst.id == src.id:
        raise ApiError(400, "SAME_ACCOUNT", "같은 계좌로는 이체할 수 없어요.")

    # 3. 본인 확인 · 회원 상태
    consume_step_up(db, body.step_up_challenge_id, login, "TRANSFER")
    if user.status == "RESTRICTED" and not mine:
        raise ApiError(403, "RESTRICTED_TRANSFER", "이용이 제한된 회원은 본인 명의 계좌로만 보낼 수 있어요.")

    # 4. 잠그고 확인 → 기록
    now = now_kst()
    bals = ledger.lock_balances(db, [src.id] + ([dst.id] if dst else []))
    limit = db.get(TransferLimit, src.id)
    per = limit.per_transfer_limit if limit else DEFAULT_PER_TRANSFER_LIMIT
    daily = limit.daily_limit if limit else DEFAULT_DAILY_LIMIT
    if src.lifecycle_status != "ACTIVE" or (dst is not None and dst.lifecycle_status != "ACTIVE"):
        failure = "ACCOUNT_NOT_ACTIVE"
    elif amount > per or used_today(db, src.id) + amount > daily:
        failure = "LIMIT_EXCEEDED"
    elif bals[src.id].balance < amount:  # 수수료 0원 (Part 5 4장 기본안 — 타행도 0원)
        failure = "INSUFFICIENT_BALANCE"
    elif dst is None and holder == EXTERNAL_FAIL_HOLDER:
        failure = "INVALID_ACCOUNT"
    else:
        failure = None
    status = "FAILED" if failure else "PENDING" if (dst is None and holder == EXTERNAL_PENDING_HOLDER) else "SUCCESS"
    t = Transfer(id=new_id("trf"), user_id=user.id, from_account_id=src.id, to_bank=body.to_bank,
                 to_account_no=body.to_account_no, to_holder_name=holder, amount=amount, fee=0,
                 my_display_name=body.my_display_name or holder, their_display_name=body.their_display_name or user.name,
                 status=status, failure_reason=failure, channel="APP", step_up_challenge_id=body.step_up_challenge_id,
                 idempotency_key=idempotency_key, requested_at=now, completed_at=None if status == "PENDING" else now)
    db.add(t)
    db.flush()  # 원장이 가리킬 이체 행을 먼저 넣는다(모델에 relationship 이 없음)
    if status == "SUCCESS":
        post_transfer(db, t, bals, now, dst)
    db.commit()
    return _result(db, t, bals[src.id].balance if status == "SUCCESS" else None)


def post_transfer(db, t: Transfer, bals: dict, now: datetime, dst: Account | None = None) -> None:
    """성공한 이체의 원장: 내 계좌 출금, 두린은행이면 받는 계좌 입금도(Part 5 9장). app/jobs.py 의 PENDING 확정도 쓴다."""
    ledger.post(db, bals[t.from_account_id], "TRANSFER_OUT", t.amount, now, fee=t.fee, transfer_id=t.id,
                counterpart_bank=t.to_bank, counterpart_account_no=t.to_account_no, display_name=t.my_display_name)
    if dst is not None:
        src_no = db.scalar(select(Account.resAccount).where(Account.id == t.from_account_id))
        ledger.post(db, bals[dst.id], "TRANSFER_IN", t.amount, now, transfer_id=t.id, counterpart_bank=OUR_BANK,
                    counterpart_account_no=src_no, display_name=t.their_display_name)


# --- 예약 송금 취소 · 자동이체 해지 (Part 5 8장, 사용자 결정 2026-11-09: 둘 다 본인 확인) ------------------------
class StepUpBody(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


@router.delete("/scheduled-transfers/{scheduledTransferId}", response_model=ScheduledTransferOut)
def cancel_scheduled_transfer(scheduled_transfer_id: Annotated[str, Path(alias="scheduledTransferId")],
                              body: StepUpBody, login: CurrentLogin, db: DB):
    s = db.scalar(select(ScheduledTransfer).where(ScheduledTransfer.id == scheduled_transfer_id,
                                                  ScheduledTransfer.user_id == login.user.id).with_for_update())
    if s is None:
        raise not_found("SCHEDULED_TRANSFER_NOT_FOUND", "예약 이체를 찾을 수 없어요.")
    consume_step_up(db, body.step_up_challenge_id, login, "SCHEDULED_TRANSFER")
    if s.status not in ("SCHEDULED", "ACTIVE", "PAUSED"):
        raise ApiError(409, "SCHEDULED_TRANSFER_NOT_CANCELABLE", "이미 실행됐거나 끝난 예약이에요.")
    now = now_kst()
    # 8장 「실행 10분 전까지 취소」. 실행 시각이 이미 지난 예약은 취소를 허락한다 — shortcut: 예약 실행 배치가 아직 없어
    # 지난 예약이 SCHEDULED 로 남는다(그대로 두면 탈퇴 ③을 영원히 막음). 실행 배치를 만들면 이 예외를 없앤다
    if s.type == "ONCE" and s.execute_at and now < s.execute_at < now + timedelta(minutes=10):
        raise ApiError(409, "SCHEDULE_LOCKED", "곧 실행되는 예약은 취소할 수 없어요.")
    s.status, s.updated_at = "CANCELED", now
    db.commit()
    return s
