"""3. 거래 — docs/sql/03_transactions.sql 의 표 7개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, CheckConstraint, ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import NOW, TS, Base, ViewBase, one_of


class AccountBalance(Base):
    """잔액 (계좌 1 : 1, 잔액의 원본)"""

    __tablename__ = "account_balances"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_account_balances_balance"),
    )

    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="KRW")
    balance: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class ScheduledTransfer(Base):
    """예약 송금·자동이체 (ERD 주요 칸 + 거래 기획서 15장의 표시 이름·updated_at)"""

    __tablename__ = "scheduled_transfers"
    STATUS_VALUES = ("SCHEDULED", "PROCESSING", "SUCCESS", "FAILED", "CANCELED", "ACTIVE", "PAUSED")
    TYPE_VALUES = ("ONCE", "MONTHLY")
    __table_args__ = (
        CheckConstraint("day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28 OR day_of_month = 99", name="ck_scheduled_transfers_day"),
        one_of("status", STATUS_VALUES, "ck_scheduled_transfers_status"),
        one_of("type", TYPE_VALUES, "ck_scheduled_transfers_type"),
        Index("idx_scheduled_transfers_from_account", "from_account_id"),
        Index("idx_scheduled_transfers_next_run", "status", "next_run_at"),
        Index("idx_scheduled_transfers_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    from_account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))
    to_bank: Mapped[str] = mapped_column(String(30))
    to_account_no: Mapped[str] = mapped_column(String(20))
    to_holder_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(BigInteger)
    my_display_name: Mapped[str | None] = mapped_column(String(50))
    their_display_name: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(30))  # ONCE = 예약 송금, MONTHLY = 자동이체
    execute_at: Mapped[datetime | None] = mapped_column(TS)  # ONCE 실행 일시
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)  # MONTHLY 지정일 1~28, 99 = 말일
    start_ym: Mapped[str | None] = mapped_column(CHAR(6))  # MONTHLY 시작 연월 YYYYMM
    end_ym: Mapped[str | None] = mapped_column(CHAR(6))  # MONTHLY 종료 연월, NULL = 해지할 때까지
    next_run_at: Mapped[datetime | None] = mapped_column(TS)  # 배치 조회 기준
    status: Mapped[str] = mapped_column(String(30), server_default="SCHEDULED")  # ONCE: SCHEDULED/PROCESSING/SUCCESS/FAILED/CANCELED, MONTHLY: ACTIVE/PAUSED/CANCELED
    step_up_challenge_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("step_up_challenges.id"))  # 등록 때 본인 확인
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class Transfer(Base):
    """이체 요청과 결과"""

    __tablename__ = "transfers"
    CHANNEL_VALUES = ("APP", "SCHEDULED", "AUTO")
    STATUS_VALUES = ("PENDING", "SUCCESS", "FAILED")
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfers_amount"),
        one_of("channel", CHANNEL_VALUES, "ck_transfers_channel"),
        one_of("status", STATUS_VALUES, "ck_transfers_status"),
        UniqueConstraint("idempotency_key", name="uk_transfers_idempotency_key"),
        Index("idx_transfers_from_account", "from_account_id", "requested_at"),
        Index("idx_transfers_scheduled", "scheduled_transfer_id"),
        Index("idx_transfers_user", "user_id", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # 예: trf_0001
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    from_account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))
    to_bank: Mapped[str] = mapped_column(String(30))
    to_account_no: Mapped[str] = mapped_column(String(20))
    to_holder_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(BigInteger)
    fee: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    my_display_name: Mapped[str | None] = mapped_column(String(50))
    their_display_name: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), server_default="PENDING")
    failure_reason: Mapped[str | None] = mapped_column(String(50))  # 실패 사유 코드
    channel: Mapped[str] = mapped_column(String(30), server_default="APP")
    scheduled_transfer_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("scheduled_transfers.id"))  # 예약·자동이체로 실행된 경우
    step_up_challenge_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("step_up_challenges.id"))  # 본인 확인
    idempotency_key: Mapped[str] = mapped_column(String(100))  # 중복 요청 방지
    requested_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    completed_at: Mapped[datetime | None] = mapped_column(TS)


class Transaction(Base):
    """거래 원장 (성공한 건만, 이체면 출금·입금 2건)"""

    __tablename__ = "transactions"
    TYPE_VALUES = ("TRANSFER_OUT", "TRANSFER_IN", "CARD_PAYMENT", "POINT_CASHOUT", "SUBSCRIPTION_PAYMENT", "SUBSCRIPTION_PAYOUT")
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount"),
        one_of("type", TYPE_VALUES, "ck_transactions_type"),
        Index("idx_transactions_account_time", "account_id", "created_at"),
        Index("idx_transactions_transfer", "transfer_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # 예: tx_0001
    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))
    type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[int] = mapped_column(BigInteger)  # 항상 양수, +/-는 type으로 결정
    fee: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    balance_after: Mapped[int] = mapped_column(BigInteger)
    transfer_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("transfers.id"))  # 이체가 아니면 NULL
    counterpart_bank: Mapped[str | None] = mapped_column(String(30))
    counterpart_account_no: Mapped[str | None] = mapped_column(String(20))
    display_name: Mapped[str | None] = mapped_column(String(50))  # 이 통장에 표시되는 이름
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class FavoriteAccount(Base):
    """자주 쓰는 계좌"""

    __tablename__ = "favorite_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "bank", "account_no", name="uk_favorite_accounts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    bank: Mapped[str] = mapped_column(String(30))
    account_no: Mapped[str] = mapped_column(String(20))
    holder_name: Mapped[str] = mapped_column(String(50))
    nickname: Mapped[str | None] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class TransferLimit(Base):
    """이체 한도 (계좌 1 : 0..1)"""

    __tablename__ = "transfer_limits"

    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"), primary_key=True)
    per_transfer_limit: Mapped[int] = mapped_column(BigInteger)
    daily_limit: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class ExternalAccount(Base):
    """타행 계좌(시드) — 가상 타행 예금주 조회용 시드 (다른 테이블과 연결 없음, 계좌번호로 찾음)"""

    __tablename__ = "external_accounts"
    __table_args__ = (
        UniqueConstraint("bank", "account_no", name="uk_external_accounts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    bank: Mapped[str] = mapped_column(String(30))
    account_no: Mapped[str] = mapped_column(String(20))
    holder_name: Mapped[str] = mapped_column(String(50))


class AccountBalanceView(ViewBase):
    """잔액 읽기용 보기 account_balance_view — 계좌 파트와 다른 파트는 잔액을 이것으로만 읽는다(기획서 C-5).

    account_balances 를 CODEF 이름으로 보여 준다. 읽기 전용.
    """

    __tablename__ = "account_balance_view"

    account_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    resAccountCurrency: Mapped[str] = mapped_column(CHAR(3))  # = account_balances.currency
    resAccountBalance: Mapped[int] = mapped_column(BigInteger)  # = account_balances.balance
    balance_as_of: Mapped[str] = mapped_column(String(14))  # = account_balances.updated_at, YYYYMMDDHHmmss
