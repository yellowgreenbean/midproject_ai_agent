"""API 응답 모양. 칸 이름은 ERD 1.md 와 같다."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

KST = timezone(timedelta(hours=9))


def _to_kst_iso(v: datetime) -> str:
    # DB 에는 한국 시각이 시간대 없이 저장돼 있으므로 +09:00 을 붙여 내보낸다.
    if v.tzinfo is None:
        v = v.replace(tzinfo=KST)
    return v.astimezone(KST).isoformat()


KstDatetime = Annotated[datetime, PlainSerializer(_to_kst_iso, return_type=str)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AccountOut(ORM):
    id: str
    user_id: str
    resAccount: str
    resAccountDisplay: str
    resAccountName: str
    account_type: str
    lifecycle_status: str
    resAccountNickName: str | None
    is_favorite: bool
    resAccountStartDate: str
    closed_at: str | None
    version: int


class AccountWithBalanceOut(AccountOut):
    """accounts JOIN account_balances 결과."""

    currency: str
    balance: int


class AccountBalanceViewOut(ORM):
    account_id: str
    resAccountCurrency: str
    resAccountBalance: int
    balance_as_of: str


class TransferLimitOut(ORM):
    account_id: str
    per_transfer_limit: int
    daily_limit: int
    updated_at: KstDatetime


class TransactionOut(ORM):
    id: str
    account_id: str
    type: str
    amount: int
    fee: int
    balance_after: int
    transfer_id: str | None
    counterpart_bank: str | None
    counterpart_account_no: str | None
    display_name: str | None
    created_at: KstDatetime


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None  # 다음 페이지를 부를 때 ?cursor= 에 넣는 값. 마지막 페이지면 null


class TransferOut(ORM):
    id: str
    user_id: str
    from_account_id: str
    to_bank: str
    to_account_no: str
    to_holder_name: str
    amount: int
    fee: int
    my_display_name: str | None
    their_display_name: str | None
    status: str
    failure_reason: str | None
    channel: str
    scheduled_transfer_id: str | None
    step_up_challenge_id: str | None
    idempotency_key: str
    requested_at: KstDatetime
    completed_at: KstDatetime | None


class ScheduledTransferOut(ORM):
    id: str
    user_id: str
    from_account_id: str
    to_bank: str
    to_account_no: str
    to_holder_name: str
    amount: int
    type: str
    execute_at: KstDatetime | None
    day_of_month: int | None
    start_ym: str | None
    end_ym: str | None
    next_run_at: KstDatetime | None
    status: str
    step_up_challenge_id: str | None
    created_at: KstDatetime


class FavoriteAccountOut(ORM):
    id: str
    user_id: str
    bank: str
    account_no: str
    holder_name: str
    nickname: str | None
    sort_order: int


class ExternalAccountLookupOut(ORM):
    bank: str
    account_no: str
    holder_name: str
