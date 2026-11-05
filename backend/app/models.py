"""ERD 1.md 1·2·3장의 계좌·거래 테이블.

칸 이름은 ERD 1.md 그대로다(accounts 의 resAccount 같은 CODEF 이름 포함).
- ID 는 문자열(user_001, acc_001, tx_0001 ...)
- 금액은 원 단위 정수(BIGINT)
- 시각(datetime)은 한국 시각(+09:00)으로 저장하고, API 응답에서 +09:00 을 붙인다.
- DB 는 PostgreSQL. Enum 은 PostgreSQL 의 ENUM 타입(CREATE TYPE)으로 만들어진다.
- 대소문자가 섞인 칸 이름(resAccount 등)은 SQLAlchemy 가 자동으로 "resAccount" 처럼 따옴표를 붙인다.
- "YYYYMMDD" 로 적힌 칸은 ERD 대로 문자열이다.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ID = String(40)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 1. 회원 (계좌의 주인이라 함께 만든다)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("payday BETWEEN 1 AND 31", name="ck_users_payday"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    birth_date: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(Enum("M", "F", name="gender"))
    payday: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "PENDING_VERIFICATION", "RESTRICTED", "WITHDRAWN", name="user_status")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# 2. 계좌
# ---------------------------------------------------------------------------
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    resAccount: Mapped[str] = mapped_column(String(20), unique=True)  # 계좌번호(숫자만)
    resAccountDisplay: Mapped[str] = mapped_column(String(30))  # 110-00-000001
    resAccountName: Mapped[str] = mapped_column(String(100))  # 상품명
    account_type: Mapped[str] = mapped_column(Enum("CHECKING", "SAVINGS", name="account_type"))
    lifecycle_status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "SUSPENDED", "CLOSED", name="lifecycle_status")
    )
    resAccountNickName: Mapped[str | None] = mapped_column(String(50))
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    resAccountStartDate: Mapped[str] = mapped_column(String(8))  # YYYYMMDD
    closed_at: Mapped[str | None] = mapped_column(String(8))  # YYYYMMDD, 해지 전 null
    version: Mapped[int] = mapped_column(Integer, default=1)

    # version 칸으로 낙관적 잠금: 동시에 두 요청이 같은 계좌를 고치면 늦은 쪽이 실패한다.
    __mapper_args__ = {"version_id_col": version}


# ---------------------------------------------------------------------------
# 3. 거래
# ---------------------------------------------------------------------------
class AccountBalance(Base):
    """잔액 원본. accounts 와 1:1 (PK 가 곧 FK)."""

    __tablename__ = "account_balances"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), default="KRW")
    balance: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ScheduledTransfer(Base):
    __tablename__ = "scheduled_transfers"
    __table_args__ = (
        CheckConstraint(
            "day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28 OR day_of_month = 99",
            name="ck_scheduled_day_of_month",
        ),
    )

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    from_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    to_bank: Mapped[str] = mapped_column(String(50))
    to_account_no: Mapped[str] = mapped_column(String(30))
    to_holder_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(Enum("ONCE", "MONTHLY", name="scheduled_type"))
    execute_at: Mapped[datetime | None] = mapped_column(DateTime)  # ONCE 일 때
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)  # 1~28, 99=말일
    start_ym: Mapped[str | None] = mapped_column(String(6))  # YYYYMM
    end_ym: Mapped[str | None] = mapped_column(String(6))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20))
    # step_up_challenges 테이블은 회원 파트에서 만든다. 그때 FK 제약을 건다.
    step_up_challenge_id: Mapped[str | None] = mapped_column(ID)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[str] = mapped_column(ID, primary_key=True)  # trf_0001
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    from_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    to_bank: Mapped[str] = mapped_column(String(50))
    to_account_no: Mapped[str] = mapped_column(String(30))
    to_holder_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(BigInteger)
    fee: Mapped[int] = mapped_column(BigInteger, default=0)
    my_display_name: Mapped[str | None] = mapped_column(String(50))
    their_display_name: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        Enum("PENDING", "SUCCESS", "FAILED", "CANCELED", name="transfer_status")
    )
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(Enum("APP", "SCHEDULED", "AUTO", name="transfer_channel"))
    scheduled_transfer_id: Mapped[str | None] = mapped_column(
        ForeignKey("scheduled_transfers.id"), index=True
    )
    step_up_challenge_id: Mapped[str | None] = mapped_column(ID)  # FK 는 회원 파트 때
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Transaction(Base):
    """거래 원장. 이체 1건이면 출금 계좌에 TRANSFER_OUT, 받는 계좌(우리 은행)에 TRANSFER_IN."""

    __tablename__ = "transactions"
    # 계좌별 최신순 목록(커서 페이징)을 빠르게 읽기 위한 인덱스
    __table_args__ = (Index("ix_transactions_account_created", "account_id", "created_at", "id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)  # tx_0001
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    type: Mapped[str] = mapped_column(
        Enum(
            "TRANSFER_OUT",
            "TRANSFER_IN",
            "CARD_PAYMENT",
            "POINT_CASHOUT",
            "SUBSCRIPTION_PAYMENT",
            "SUBSCRIPTION_PAYOUT",
            name="transaction_type",
        )
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    fee: Mapped[int] = mapped_column(BigInteger, default=0)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    transfer_id: Mapped[str | None] = mapped_column(ForeignKey("transfers.id"), index=True)
    counterpart_bank: Mapped[str | None] = mapped_column(String(50))
    counterpart_account_no: Mapped[str | None] = mapped_column(String(30))
    display_name: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class FavoriteAccount(Base):
    __tablename__ = "favorite_accounts"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    bank: Mapped[str] = mapped_column(String(50))
    account_no: Mapped[str] = mapped_column(String(30))
    holder_name: Mapped[str] = mapped_column(String(50))
    nickname: Mapped[str | None] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TransferLimit(Base):
    """이체 한도. accounts 와 0..1:1 (PK 가 곧 FK)."""

    __tablename__ = "transfer_limits"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    per_transfer_limit: Mapped[int] = mapped_column(BigInteger)
    daily_limit: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ExternalAccount(Base):
    """가상 타행 예금주 조회용 시드. 다른 테이블과 FK 없이 (bank, account_no) 로 찾는다."""

    __tablename__ = "external_accounts"
    __table_args__ = (UniqueConstraint("bank", "account_no", name="uk_external_bank_account"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    bank: Mapped[str] = mapped_column(String(50))
    account_no: Mapped[str] = mapped_column(String(30))
    holder_name: Mapped[str] = mapped_column(String(50))


# ---------------------------------------------------------------------------
# 보기(view): account_balance_view
# 표가 아니므로 Base 와 다른 ViewBase 에 둔다 → create_all 이 표로 만들지 않는다.
# ---------------------------------------------------------------------------
class ViewBase(DeclarativeBase):
    pass


class AccountBalanceView(ViewBase):
    __tablename__ = "account_balance_view"

    account_id: Mapped[str] = mapped_column(ID, primary_key=True)
    resAccountCurrency: Mapped[str] = mapped_column(String(3))
    resAccountBalance: Mapped[int] = mapped_column(BigInteger)
    balance_as_of: Mapped[str] = mapped_column(String(14))  # YYYYMMDDHHmmss


# PostgreSQL 은 따옴표 없는 이름을 소문자로 바꾼다. 대소문자가 섞인 CODEF 이름은 "..." 로 감싼다.
CREATE_ACCOUNT_BALANCE_VIEW = text(
    """
    CREATE OR REPLACE VIEW account_balance_view AS
    SELECT account_id,
           currency AS "resAccountCurrency",
           balance  AS "resAccountBalance",
           to_char(updated_at, 'YYYYMMDDHH24MISS') AS balance_as_of
    FROM account_balances
    """
)
