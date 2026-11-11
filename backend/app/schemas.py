"""API 응답 모양 — 기획서 Part 6 C-5 「이름·형식 규칙」을 따른다.

- 이름: snake_case, 단 계좌·CODEF 에서 온 칸은 CODEF 이름 그대로(resAccount ...)
- 금액·시각 형식(Money · KstDatetime)은 app/common/naming
- 빈 값: 우리가 만든 칸은 null, CODEF 의 res… 칸은 빈 문자열 ""  → CodefStr
- 날짜 문자열(YYYYMMDD 등)은 DB 값 그대로
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, computed_field

from app.common.naming import KstDatetime, Money
from app.rules import INCOMING_TYPES


CodefStr = Annotated[str | None, PlainSerializer(lambda v: v or "", return_type=str)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- 계좌 (Part 2) ---------------------------------------------------------------
class BalanceOut(ORM):
    """account_balance_view 한 행 (Part 2 9.2)."""

    account_id: str
    resAccountCurrency: str
    resAccountBalance: Money
    balance_as_of: str  # YYYYMMDDHHmmss


class AccountOut(ORM):
    """accounts + account_balance_view (목록·상세 공통, Part 2 8.4)."""

    id: str
    resAccount: str
    resAccountDisplay: str
    resAccountName: str
    resAccountNickName: CodefStr
    account_type: str
    lifecycle_status: str
    is_favorite: bool
    resAccountStartDate: str  # YYYYMMDD
    closed_at: str | None  # YYYYMMDD, 해지 전 null
    version: int
    resAccountCurrency: str
    resAccountBalance: Money
    balance_as_of: str


class AccountDetailOut(AccountOut):
    """계좌 상세 = 목록 한 줄 + 지금 해지를 막는 사유 (ACCT-F05, 9.3 사유 코드). 해지한 계좌는 빈 목록.
    화면이 [계좌 해지]를 누르자마자(본인 확인 전에) 막힌 이유를 보여 주려고 상세에 같이 싣는다."""

    close_blockers: list[str]
    notifications_enabled: bool  # 입출금 알림 켬 (ACCT-F06, 설정 행이 없으면 켬)


# --- 거래 (Part 5) ---------------------------------------------------------------
class TransactionOut(ORM):
    id: str
    account_id: str
    type: str
    amount: Money  # 항상 양수, +/− 는 direction
    fee: Money
    balance_after: Money
    transfer_id: str | None
    counterpart_bank: str | None
    counterpart_account_no: str | None
    display_name: str | None
    created_at: KstDatetime

    @computed_field
    @property
    def direction(self) -> Literal["IN", "OUT"]:
        """내역의 +/− (Part 5 3장 「내역 표시」)."""
        return "IN" if self.type in INCOMING_TYPES else "OUT"


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None  # 다음 페이지를 부를 때 ?cursor= 에 넣는 값. 마지막 페이지면 null


class TransferOut(ORM):
    id: str
    from_account_id: str
    to_bank: str
    to_account_no: str
    to_holder_name: str
    amount: Money
    fee: Money
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
    from_account_id: str
    to_bank: str
    to_account_no: str
    to_holder_name: str
    amount: Money
    my_display_name: str | None
    their_display_name: str | None
    type: str
    execute_at: KstDatetime | None
    day_of_month: int | None
    start_ym: str | None
    end_ym: str | None
    next_run_at: KstDatetime | None
    status: str
    step_up_challenge_id: str | None
    created_at: KstDatetime
    updated_at: KstDatetime


class TransferLimitOut(BaseModel):
    """이체 한도와 오늘 남은 한도 (Part 5 16장 GET /accounts/{accountId}/transfer-limits)."""

    account_id: str
    per_transfer_limit: Money
    daily_limit: Money
    used_today: Money
    remaining_today: Money
    is_default: bool  # transfer_limits 행이 없어 기획서 기본값(Part 5 4장)을 쓴 경우 true
    updated_at: KstDatetime | None


class FavoriteAccountOut(ORM):
    id: str
    bank: str
    account_no: str
    holder_name: str
    nickname: str | None
    sort_order: int
    account_display: str  # 두린은행은 하이픈 넣은 번호, 타행은 번호 그대로


class TransferTargetOut(BaseModel):
    """이체 대상 계좌 확인 결과 (Part 5 16장 GET /transfer-targets/verify)."""

    bank: str
    account_no: str
    holder_name: str
    account_status: str  # 두린은행 계좌는 lifecycle_status, 가상 타행은 늘 ACTIVE
    is_mine: bool  # 내 계좌로 옮기기인지 (RESTRICTED 회원은 이것만 허용 — Part 5 4장)
