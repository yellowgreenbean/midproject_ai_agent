"""이체 결과·예약·한도 API — 기획서 Part 5 16장.

    POST   /transfers                                   이체 실행 (본인 확인 TRANSFER, Idempotency-Key 필수)   TRX-F01·F08
    GET    /transfers(/{transferId})                    이체 결과 (상태·기간·출금 계좌 조건)                       TRX-F02
    GET    /transfers/{transferId}/receipt              이체확인증 (성공한 이체만)                                TRX-F06
    POST   /scheduled-transfers                         예약 송금(ONCE)·자동이체(MONTHLY) 등록 (본인 확인 SCHEDULED_TRANSFER) TRX-F10·F11
    PATCH  /scheduled-transfers/{scheduledTransferId}   예약 변경 (본인 확인 SCHEDULED_TRANSFER, 실행 10분 전까지)
    DELETE /scheduled-transfers/{scheduledTransferId}   예약 송금 취소·자동이체 해지 (본인 확인 SCHEDULED_TRANSFER)
    GET    /accounts/{accountId}/transfer-limits        이체 한도와 오늘 남은 한도                                TRX-F07
    PATCH  /accounts/{accountId}/transfer-limits        한도 변경 (올릴 때만 본인 확인 TRANSFER)                  TRX-F13

이체 실행 순서 (Part 5 4·9·11·14장)
  1. 같은 Idempotency-Key 로 이미 처리했으면 그 결과를 그대로 돌려준다(버튼 두 번 → 한 번만)
  2. 입력 검사(은행·자릿수·금액) → 받는 계좌 찾기(transfer_targets.find_target) → 같은 계좌 막기
  3. 본인 확인 번호 사용 · RESTRICTED 회원은 본인 명의 계좌로만(Part 1 7.3)
  4. run_transfer: 잔액 행을 계좌 id 순서로 잠그고 상태·한도·잔액 확인
     → 걸리면 FAILED + 사유로 기록(원장 없음). 통과하면 SUCCESS + 원장(두린은행: 출금·입금 / 다른 은행: 출금만)
  다른 은행은 시험용 예금주 「임처리」면 PENDING(10분 뒤 app/jobs.py 가 확정), 「오실패」면 FAILED (11장).
  예약 실행(app/jobs.py run_scheduled_transfers)도 4번 run_transfer 를 그대로 쓴다(14장 「같은 락 규칙」).
"""

import calendar
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.common import ledger
from app.common.ownership import get_owned_account_or_404, get_owned_or_404
from app.common.idempotency import IdempotencyKey
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, account_not_found, not_found
from app.models import Account, ScheduledTransfer, Transfer, TransferLimit, User
from app.common.step_up import consume_step_up
from app.routers.transfer_targets import find_target
from app.rules import (
    AUTO_TRANSFER_HOUR,
    DEFAULT_DAILY_LIMIT,
    DEFAULT_PER_TRANSFER_LIMIT,
    EXTERNAL_FAIL_HOLDER,
    EXTERNAL_PENDING_HOLDER,
    KST,
    LAST_DAY_OF_MONTH,
    LIMIT_COUNTED_TRANSFER_STATUSES,
    MAX_DAILY_LIMIT,
    MAX_PER_TRANSFER_LIMIT,
    OUR_BANK,
    SCHEDULE_MAX_AHEAD,
    SCHEDULE_MIN_AHEAD,
    SCHEDULE_STEP_MINUTES,
    TRANSFER_FAILURE_MESSAGES,
    TRANSFER_NAME_MAX,
    now_kst,
)
from app.common.naming import KstDatetime, Money
from app.schemas import ScheduledTransferOut, TransferLimitOut, TransferOut
from app.security import new_id

router = APIRouter(tags=["transfers"])

TransferStatus = Literal[Transfer.STATUS_VALUES]  # type: ignore[valid-type]  # PENDING / SUCCESS / FAILED
TransferId = Annotated[str, Path(alias="transferId")]
ScheduledId = Annotated[str, Path(alias="scheduledTransferId")]


# 이체 결과 목록 (상태·기간·출금 계좌 조건), 최신순. account_id 는 계좌 상세의 「이체 결과」용(사용자 결정 2026-11-10)
@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    db: DB,
    user_id: CurrentUserId,
    status: Annotated[TransferStatus | None, Query()] = None,
    start_date: Annotated[date | None, Query(description="이 날짜부터 (YYYY-MM-DD)")] = None,
    end_date: Annotated[date | None, Query(description="이 날짜까지, 그날 포함 (YYYY-MM-DD)")] = None,
    account_id: Annotated[str | None, Query(description="이 출금 계좌의 이체만")] = None,
):
    if start_date and end_date and start_date > end_date:
        raise ApiError(400, "INVALID_PERIOD", "조회 시작일이 종료일보다 늦어요.")
    stmt = select(Transfer).where(Transfer.user_id == user_id)  # 남의 계좌 id 를 줘도 내 이체만 — 빈 목록
    if status is not None:
        stmt = stmt.where(Transfer.status == status)
    if start_date:
        stmt = stmt.where(Transfer.requested_at >= datetime.combine(start_date, time.min))
    if end_date:
        stmt = stmt.where(Transfer.requested_at < datetime.combine(end_date + timedelta(days=1), time.min))
    if account_id:
        stmt = stmt.where(Transfer.from_account_id == account_id)
    return db.scalars(stmt.order_by(Transfer.requested_at.desc(), Transfer.id.desc())).all()


def _owned_transfer(db, transfer_id: str, user_id: str) -> Transfer:
    return get_owned_or_404(db, Transfer, transfer_id, user_id, not_found("TRANSFER_NOT_FOUND", "이체 내역을 찾을 수 없어요."))


@router.get("/transfers/{transferId}", response_model=TransferOut)
def get_transfer(transfer_id: TransferId, db: DB, user_id: CurrentUserId):
    return _owned_transfer(db, transfer_id, user_id)


# --- 이체확인증 (TRX-F06, 10장) -------------------------------------------------------------------
class ReceiptOut(BaseModel):
    transfer_id: str
    completed_at: KstDatetime
    sender_name: str  # 보낸 분 (예금주)
    from_account: str  # 출금 계좌 (일부 가림)
    to_bank: str
    to_holder_name: str  # 받는 분 (예금주)
    to_account: str  # 입금 계좌 (일부 가림)
    amount: Money
    fee: Money
    status: str


def mask_account(no: str) -> str:
    """앞 3자리·뒤 3자리만 보인다 — 11000000000001 → 110********001"""
    return no[:3] + "*" * max(len(no) - 6, 0) + no[-3:]


@router.get("/transfers/{transferId}/receipt", response_model=ReceiptOut)
def get_transfer_receipt(transfer_id: TransferId, db: DB, user_id: CurrentUserId):
    t = _owned_transfer(db, transfer_id, user_id)
    if t.status != "SUCCESS":
        raise ApiError(409, "RECEIPT_NOT_AVAILABLE", "완료된 이체만 이체확인증을 볼 수 있어요.")
    from_no = db.scalar(select(Account.resAccount).where(Account.id == t.from_account_id))
    return ReceiptOut(transfer_id=t.id, completed_at=t.completed_at, sender_name=db.scalar(select(User.name).where(User.id == user_id)),
                      from_account=mask_account(from_no), to_bank=t.to_bank, to_holder_name=t.to_holder_name,
                      to_account=mask_account(t.to_account_no), amount=t.amount, fee=t.fee, status=t.status)


# --- 예약 목록 --------------------------------------------------------------------------------------
# 예약 송금·자동이체 목록 (취소된 예약 포함 — Part 5 10장 「이체 결과」 탭)
@router.get("/scheduled-transfers", response_model=list[ScheduledTransferOut])
def list_scheduled_transfers(db: DB, user_id: CurrentUserId):
    return db.scalars(
        select(ScheduledTransfer)
        .where(ScheduledTransfer.user_id == user_id)
        .order_by(ScheduledTransfer.created_at.desc(), ScheduledTransfer.id.desc())
    ).all()


def _scheduled_not_found() -> ApiError:
    return not_found("SCHEDULED_TRANSFER_NOT_FOUND", "예약 이체를 찾을 수 없어요.")


@router.get("/scheduled-transfers/{scheduledTransferId}", response_model=ScheduledTransferOut)
def get_scheduled_transfer(scheduled_transfer_id: ScheduledId, db: DB, user_id: CurrentUserId):
    return get_owned_or_404(db, ScheduledTransfer, scheduled_transfer_id, user_id, _scheduled_not_found())


# --- 한도 (TRX-F07 확인 · TRX-F13 변경) ------------------------------------------------------------
def _limits(db, account_id: str) -> tuple[int, int, TransferLimit | None]:
    limit = db.get(TransferLimit, account_id)
    if limit is None:  # 행이 없으면 기획서 기본값(계좌 1 : 0..1)
        return DEFAULT_PER_TRANSFER_LIMIT, DEFAULT_DAILY_LIMIT, None
    return limit.per_transfer_limit, limit.daily_limit, limit


@router.get("/accounts/{accountId}/transfer-limits", response_model=TransferLimitOut)
def get_transfer_limits(account_id: Annotated[str, Path(alias="accountId")], db: DB, user_id: CurrentUserId):
    get_owned_account_or_404(db, account_id, user_id)
    per, daily, limit = _limits(db, account_id)
    used = used_today(db, account_id)
    return TransferLimitOut(account_id=account_id, per_transfer_limit=per, daily_limit=daily, used_today=used,
                            remaining_today=max(daily - used, 0), is_default=limit is None,
                            updated_at=limit.updated_at if limit else None)


def used_today(db, account_id: str) -> int:
    """오늘(한국 날짜 0시부터) 이 계좌에서 나간 이체 금액 — 예약·자동이체·처리중도 포함(Part 5 4장)."""
    today_start = datetime.combine(now_kst().date(), time.min)
    return db.scalar(select(func.coalesce(func.sum(Transfer.amount), 0)).where(
        Transfer.from_account_id == account_id, Transfer.status.in_(LIMIT_COUNTED_TRANSFER_STATUSES),
        Transfer.requested_at >= today_start))


class LimitIn(BaseModel):
    per_transfer_limit: int = Field(ge=1)
    daily_limit: int = Field(ge=1)
    step_up_challenge_id: str | None = Field(default=None, max_length=40)  # 올릴 때만 필요


@router.patch("/accounts/{accountId}/transfer-limits", response_model=TransferLimitOut)
def update_transfer_limits(account_id: Annotated[str, Path(alias="accountId")], body: LimitIn, login: CurrentLogin, db: DB):
    account = get_owned_account_or_404(db, account_id, login.user.id)
    if account.lifecycle_status == "CLOSED":
        raise ApiError(409, "INVALID_STATUS_TRANSITION", "해지한 계좌는 한도를 바꿀 수 없어요.")
    if body.per_transfer_limit > MAX_PER_TRANSFER_LIMIT or body.daily_limit > MAX_DAILY_LIMIT:
        raise ApiError(422, "LIMIT_TOO_HIGH", f"1회 {MAX_PER_TRANSFER_LIMIT // 10**8}억 원, 1일 {MAX_DAILY_LIMIT // 10**8}억 원까지 정할 수 있어요.")
    if body.per_transfer_limit % 10_000 or body.daily_limit % 10_000:  # 화면(TransferLimitsPage) 안내와 같은 단위
        raise ApiError(422, "INVALID_LIMIT", "한도는 1만 원 단위로 정해 주세요.")
    if body.per_transfer_limit > body.daily_limit:
        raise ApiError(422, "INVALID_LIMIT", "1회 한도는 1일 한도보다 클 수 없어요.")
    per, daily, limit = _limits(db, account_id)
    if body.per_transfer_limit > per or body.daily_limit > daily:  # 내리기는 바로, 올리기는 본인 확인 (화면 규칙과 같음)
        consume_step_up(db, body.step_up_challenge_id, login, "TRANSFER")
    if limit is None:
        limit = TransferLimit(account_id=account_id)
        db.add(limit)
    limit.per_transfer_limit, limit.daily_limit, limit.updated_at = body.per_transfer_limit, body.daily_limit, now_kst()
    db.commit()
    return get_transfer_limits(account_id, db, login.user.id)


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


def parse_amount(text: str) -> int:
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise ApiError(400, "INVALID_AMOUNT", "1원 이상 입력해 주세요.")
    return int(text)


def _my_account(db, account_id: str, user_id: str) -> Account:
    src = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    if src is None:
        raise account_not_found()
    return src


@router.post("/transfers", response_model=TransferResultOut, status_code=201)
def create_transfer(body: TransferIn, login: CurrentLogin, db: DB,
                    idempotency_key: IdempotencyKey):
    user = login.user
    # 1. 멱등성 — 같은 키면 처음 결과 (shortcut: 같은 키가 동시에 오면 둘째는 DB 고유 제약에 걸려 500, 돈은 한 번만 나감)
    prev = db.scalar(select(Transfer).where(Transfer.idempotency_key == idempotency_key))
    if prev is not None:
        if prev.user_id != user.id:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 쓴 요청 번호예요. 다시 시도해 주세요.")
        return _result(db, prev)

    # 2. 입력 · 받는 계좌
    amount = parse_amount(body.amount)
    dst, holder, mine = find_target(db, user.id, body.to_bank, body.to_account_no)
    src = _my_account(db, body.from_account_id, user.id)
    if dst is not None and dst.id == src.id:
        raise ApiError(400, "SAME_ACCOUNT", "같은 계좌로는 이체할 수 없어요.")

    # 3. 본인 확인 · 회원 상태
    consume_step_up(db, body.step_up_challenge_id, login, "TRANSFER")
    if user.status == "RESTRICTED" and not mine:
        raise ApiError(403, "RESTRICTED_TRANSFER", "이용이 제한된 회원은 본인 명의 계좌로만 보낼 수 있어요.")

    # 4. 잠그고 확인 → 기록
    t, balance_after = run_transfer(db, user=user, src=src, dst=dst, holder=holder, to_bank=body.to_bank,
                                    to_account_no=body.to_account_no, amount=amount, my_name=body.my_display_name,
                                    their_name=body.their_display_name, channel="APP",
                                    step_up_id=body.step_up_challenge_id, key=idempotency_key, now=now_kst())
    db.commit()
    return _result(db, t, balance_after)


def run_transfer(db, *, user: User, src: Account, dst: Account | None, holder: str, to_bank: str, to_account_no: str,
                 amount: int, my_name: str | None, their_name: str | None, channel: str, step_up_id: str | None,
                 key: str, now: datetime, scheduled_id: str | None = None,
                 failure: str | None = None) -> tuple[Transfer, int | None]:
    """잠그고 확인 → 이체 행 + (성공이면) 원장. 커밋은 부르는 쪽. failure 를 주면 확인 없이 그 사유로 실패시킨다.
    (이체 행, 성공했을 때 내 계좌 잔액)을 돌려준다."""
    bals = ledger.lock_balances(db, [src.id] + ([dst.id] if dst else []))
    for a in (src, dst):  # 위에서 읽은 상태는 잠그기 전 값 — 그 사이 정지·해지됐을 수 있어 잠근 뒤 다시 읽는다(계좌 해지와 겹칠 때)
        if a is not None:
            db.refresh(a)
    per, daily, _ = _limits(db, src.id)
    if failure:
        pass
    elif src.lifecycle_status != "ACTIVE" or (dst is not None and dst.lifecycle_status != "ACTIVE"):
        failure = "ACCOUNT_NOT_ACTIVE"
    elif amount > per or used_today(db, src.id) + amount > daily:
        failure = "LIMIT_EXCEEDED"
    elif bals[src.id].balance < amount:  # 수수료 0원 (Part 5 4장 기본안 — 타행도 0원)
        failure = "INSUFFICIENT_BALANCE"
    elif dst is None and holder == EXTERNAL_FAIL_HOLDER:
        failure = "INVALID_ACCOUNT"
    status = "FAILED" if failure else "PENDING" if (dst is None and holder == EXTERNAL_PENDING_HOLDER) else "SUCCESS"
    t = Transfer(id=new_id("trf"), user_id=user.id, from_account_id=src.id, to_bank=to_bank,
                 to_account_no=to_account_no, to_holder_name=holder, amount=amount, fee=0,
                 my_display_name=my_name or holder, their_display_name=their_name or user.name,
                 status=status, failure_reason=failure, channel=channel, scheduled_transfer_id=scheduled_id,
                 step_up_challenge_id=step_up_id, idempotency_key=key, requested_at=now,
                 completed_at=None if status == "PENDING" else now)
    db.add(t)
    db.flush()  # 원장이 가리킬 이체 행을 먼저 넣는다(모델에 relationship 이 없음)
    if status == "SUCCESS":
        post_transfer(db, t, bals, now, dst)
    return t, bals[src.id].balance if status == "SUCCESS" else None


def post_transfer(db, t: Transfer, bals: dict, now: datetime, dst: Account | None = None) -> None:
    """성공한 이체의 원장: 내 계좌 출금, 두린은행이면 받는 계좌 입금도(Part 5 9장). app/jobs.py 의 PENDING 확정도 쓴다."""
    ledger.post(db, bals[t.from_account_id], "TRANSFER_OUT", t.amount, now, fee=t.fee, transfer_id=t.id,
                counterpart_bank=t.to_bank, counterpart_account_no=t.to_account_no, display_name=t.my_display_name)
    if dst is not None:
        src_no = db.scalar(select(Account.resAccount).where(Account.id == t.from_account_id))
        ledger.post(db, bals[dst.id], "TRANSFER_IN", t.amount, now, transfer_id=t.id, counterpart_bank=OUR_BANK,
                    counterpart_account_no=src_no, display_name=t.their_display_name)


# --- 예약 송금 · 자동이체 등록·변경 (TRX-F10·F11, 8장) ----------------------------------------------
def invalid_schedule(message: str) -> ApiError:
    return ApiError(422, "INVALID_SCHEDULE", message)


def next_monthly_run(after: datetime, day: int, start_ym: str, end_ym: str | None) -> datetime | None:
    """after 보다 뒤의 첫 자동이체 실행 시각(지정일 06:00, 99 = 말일). 종료 월을 넘으면 None."""
    y, m = max((int(start_ym[:4]), int(start_ym[4:])), (after.year, after.month))
    for _ in range(2):  # 이번 달 실행일이 지났으면 다음 달
        if end_ym and f"{y}{m:02d}" > end_ym:
            return None
        last = calendar.monthrange(y, m)[1]
        run = datetime(y, m, last if day == LAST_DAY_OF_MONTH else day, AUTO_TRANSFER_HOUR)
        if run > after:
            return run
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def _when(type_: str, execute_at: datetime | None, day: int | None, start_ym: str | None, end_ym: str | None,
          now: datetime) -> dict:
    """예약 시각 검사 → ScheduledTransfer 의 시각 칸들."""
    if type_ == "ONCE":
        if execute_at is None:
            raise invalid_schedule("보낼 날짜와 시각을 골라 주세요.")
        at = execute_at.astimezone(KST).replace(tzinfo=None) if execute_at.tzinfo else execute_at
        if at.minute % SCHEDULE_STEP_MINUTES or at.second or at.microsecond:
            raise invalid_schedule("시각은 10분 단위로 골라 주세요.")
        if not now + SCHEDULE_MIN_AHEAD <= at <= now + SCHEDULE_MAX_AHEAD:
            raise invalid_schedule("10분 이후부터 1년 이내로 골라 주세요.")
        return dict(execute_at=at, next_run_at=at, day_of_month=None, start_ym=None, end_ym=None)
    if day is None or not (1 <= day <= 28 or day == LAST_DAY_OF_MONTH):
        raise invalid_schedule("매월 1~28일이나 말일 중에서 골라 주세요.")  # 29~31일은 없는 달이 있어 「말일」로 (8장)
    this_ym = now.strftime("%Y%m")
    start = start_ym or this_ym
    if start < this_ym or (end_ym and end_ym < start):
        raise invalid_schedule("시작 월은 이번 달부터, 종료 월은 시작 월 이후로 골라 주세요.")
    first = next_monthly_run(now + SCHEDULE_MIN_AHEAD, day, start, end_ym)
    if first is None:
        raise invalid_schedule("종료 월까지 보낼 날이 없어요. 기간을 다시 골라 주세요.")
    return dict(execute_at=None, next_run_at=first, day_of_month=day, start_ym=start, end_ym=end_ym)


def _check_amount(db, account_id: str, amount: int) -> None:
    if amount > _limits(db, account_id)[0]:  # 등록 때는 1회 한도만 — 잔액·1일 한도는 실행할 때 본다(8장)
        raise ApiError(422, "LIMIT_EXCEEDED", "1회 이체 한도를 초과했어요.")


YM = Field(default=None, pattern=r"^\d{4}(0[1-9]|1[0-2])$")


class ScheduleIn(BaseModel):
    from_account_id: str = Field(max_length=40)
    to_bank: str = Field(max_length=30)
    to_account_no: str = Field(max_length=20)
    amount: str = Field(max_length=15)
    step_up_challenge_id: str = Field(max_length=40)
    type: Literal["ONCE", "MONTHLY"]
    execute_at: datetime | None = None  # ONCE: 10분 단위, 10분 뒤 ~ 1년 안
    day_of_month: int | None = None  # MONTHLY: 1~28, 99 = 말일
    start_ym: str | None = YM  # MONTHLY: YYYYMM, 없으면 이번 달
    end_ym: str | None = YM  # MONTHLY: 없으면 해지할 때까지
    my_display_name: str | None = Field(default=None, max_length=TRANSFER_NAME_MAX)
    their_display_name: str | None = Field(default=None, max_length=TRANSFER_NAME_MAX)


@router.post("/scheduled-transfers", response_model=ScheduledTransferOut, status_code=201)
def create_scheduled_transfer(body: ScheduleIn, login: CurrentLogin, db: DB):
    user, now = login.user, now_kst()
    if user.status != "ACTIVE":  # 새로 시작하는 금융 작업 (Part 1 7.3)
        raise ApiError(403, "USER_NOT_ACTIVE", "지금 계정 상태에서는 예약할 수 없어요.")
    amount = parse_amount(body.amount)
    dst, holder, _ = find_target(db, user.id, body.to_bank, body.to_account_no)
    src = _my_account(db, body.from_account_id, user.id)
    if dst is not None and dst.id == src.id:
        raise ApiError(400, "SAME_ACCOUNT", "같은 계좌로는 이체할 수 없어요.")
    if src.lifecycle_status != "ACTIVE" or (dst is not None and dst.lifecycle_status != "ACTIVE"):
        raise ApiError(422, "ACCOUNT_NOT_ACTIVE", "거래할 수 없는 계좌예요.")
    _check_amount(db, src.id, amount)
    when = _when(body.type, body.execute_at, body.day_of_month, body.start_ym, body.end_ym, now)
    consume_step_up(db, body.step_up_challenge_id, login, "SCHEDULED_TRANSFER")
    s = ScheduledTransfer(
        id=new_id("sch"), user_id=user.id, from_account_id=src.id, to_bank=body.to_bank, to_account_no=body.to_account_no,
        to_holder_name=holder, amount=amount, my_display_name=body.my_display_name or holder,
        their_display_name=body.their_display_name or user.name, type=body.type,
        status="SCHEDULED" if body.type == "ONCE" else "ACTIVE", step_up_challenge_id=body.step_up_challenge_id,
        created_at=now, updated_at=now, **when)
    db.add(s)
    db.commit()
    return s


class SchedulePatch(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)
    amount: str | None = Field(default=None, max_length=15)
    execute_at: datetime | None = None  # ONCE
    day_of_month: int | None = None  # MONTHLY
    end_ym: str | None = YM  # MONTHLY — null 을 보내면 「해지할 때까지」
    my_display_name: str | None = Field(default=None, max_length=TRANSFER_NAME_MAX)
    their_display_name: str | None = Field(default=None, max_length=TRANSFER_NAME_MAX)


def _locked_owned_schedule(db, scheduled_id: str, user_id: str) -> ScheduledTransfer:
    s = db.scalar(select(ScheduledTransfer).where(ScheduledTransfer.id == scheduled_id,
                                                  ScheduledTransfer.user_id == user_id).with_for_update())
    if s is None:
        raise _scheduled_not_found()
    return s


def _check_not_soon(s: ScheduledTransfer, now: datetime, what: str) -> None:
    # 8장 「실행 10분 전까지 변경·취소」. 멈춘 자동이체(PAUSED)는 실행되지 않으니 언제든
    if s.status != "PAUSED" and s.next_run_at is not None and now >= s.next_run_at - SCHEDULE_MIN_AHEAD:
        raise ApiError(409, "SCHEDULE_LOCKED", f"곧 실행되는 예약은 {what} 수 없어요.")


@router.patch("/scheduled-transfers/{scheduledTransferId}", response_model=ScheduledTransferOut)
def update_scheduled_transfer(scheduled_transfer_id: ScheduledId, body: SchedulePatch, login: CurrentLogin, db: DB):
    s, now = _locked_owned_schedule(db, scheduled_transfer_id, login.user.id), now_kst()
    consume_step_up(db, body.step_up_challenge_id, login, "SCHEDULED_TRANSFER")
    if s.status not in ("SCHEDULED", "ACTIVE", "PAUSED"):
        raise ApiError(409, "SCHEDULED_TRANSFER_NOT_EDITABLE", "이미 실행됐거나 끝난 예약이에요.")
    _check_not_soon(s, now, "바꿀")
    if body.amount is not None:
        s.amount = parse_amount(body.amount)
        _check_amount(db, s.from_account_id, s.amount)
    if s.type == "ONCE" and body.execute_at is not None:
        for k, v in _when("ONCE", body.execute_at, None, None, None, now).items():
            setattr(s, k, v)
    if s.type == "MONTHLY" and {"day_of_month", "end_ym"} & body.model_fields_set:
        end = body.end_ym if "end_ym" in body.model_fields_set else s.end_ym
        start = max(s.start_ym, now.strftime("%Y%m"))  # 이미 돌던 자동이체는 이번 달부터 다시 센다
        when = _when("MONTHLY", None, body.day_of_month or s.day_of_month, start, end, now)
        s.day_of_month, s.end_ym, s.next_run_at = when["day_of_month"], when["end_ym"], when["next_run_at"]
    if body.my_display_name is not None:  # 빈 문자열이면 기본값(예금주 실명)으로
        s.my_display_name = body.my_display_name or s.to_holder_name
    if body.their_display_name is not None:
        s.their_display_name = body.their_display_name or login.user.name
    s.updated_at = now
    db.commit()
    return s


# --- 예약 송금 취소 · 자동이체 해지 (Part 5 8장, 사용자 결정 2026-11-09: 둘 다 본인 확인) ------------------------
class StepUpBody(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


@router.delete("/scheduled-transfers/{scheduledTransferId}", response_model=ScheduledTransferOut)
def cancel_scheduled_transfer(scheduled_transfer_id: ScheduledId, body: StepUpBody, login: CurrentLogin, db: DB):
    s, now = _locked_owned_schedule(db, scheduled_transfer_id, login.user.id), now_kst()
    consume_step_up(db, body.step_up_challenge_id, login, "SCHEDULED_TRANSFER")
    if s.status not in ("SCHEDULED", "ACTIVE", "PAUSED"):
        raise ApiError(409, "SCHEDULED_TRANSFER_NOT_CANCELABLE", "이미 실행됐거나 끝난 예약이에요.")
    _check_not_soon(s, now, "취소할")
    s.status, s.updated_at = "CANCELED", now
    db.commit()
    return s
