"""2. 계좌 — docs/sql/02_accounts.sql 의 표 5개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import FALSE, NOW, TRUE, TS, Base, one_of


class Account(Base):
    """계좌 (잔액은 account_balances 에 있음)"""

    __tablename__ = "accounts"
    ACCOUNT_TYPE_VALUES = ("CHECKING", "SAVINGS")
    LIFECYCLE_STATUS_VALUES = ("ACTIVE", "SUSPENDED", "CLOSED")
    __table_args__ = (
        one_of("account_type", ACCOUNT_TYPE_VALUES, "ck_accounts_account_type"),
        one_of("lifecycle_status", LIFECYCLE_STATUS_VALUES, "ck_accounts_lifecycle_status"),
        UniqueConstraint("resAccount", name="uk_accounts_res_account"),
        Index("idx_accounts_user_status", "user_id", "lifecycle_status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    resAccount: Mapped[str] = mapped_column(String(20))  # 계좌번호(숫자만)
    resAccountDisplay: Mapped[str] = mapped_column(String(30))  # 예: 110-00-000001
    resAccountName: Mapped[str] = mapped_column(String(100))  # 상품명
    account_type: Mapped[str] = mapped_column(String(30))
    lifecycle_status: Mapped[str] = mapped_column(String(30), server_default="ACTIVE")
    resAccountNickName: Mapped[str | None] = mapped_column(String(50))
    is_favorite: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)
    resAccountStartDate: Mapped[str] = mapped_column(CHAR(8))  # YYYYMMDD
    closed_at: Mapped[str | None] = mapped_column(CHAR(8))  # YYYYMMDD, 해지 전 NULL
    version: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 낙관적 잠금

    # 낙관적 잠금: UPDATE 때마다 version 을 1 올리고, 그 사이 다른 요청이 고쳤으면 실패한다.
    __mapper_args__ = {"version_id_col": version}


class AccountActivityLog(Base):
    """계좌 관리 기록"""

    __tablename__ = "account_activity_logs"
    __table_args__ = (
        Index("idx_account_activity_logs_account", "account_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))
    actor_id: Mapped[str] = mapped_column(String(40))  # 행동한 사람(회원 또는 시스템)
    action: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    metadata_: Mapped[Any | None] = mapped_column("metadata", JSONB)


class NotificationPreference(Base):
    """계좌별 알림 설정"""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        Index("idx_notification_preferences_account", "account_id"),
    )

    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)
    deposit_enabled: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)
    withdrawal_enabled: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)
    minimum_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    channel: Mapped[str] = mapped_column(String(20), server_default="PUSH")


class AccountInactivity(Base):
    """장기 미사용 (계좌 1 : 0..1)"""

    __tablename__ = "account_inactivity"

    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"), primary_key=True)
    last_activity_at: Mapped[datetime] = mapped_column(TS)
    inactivity_flag: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)
    flagged_at: Mapped[datetime | None] = mapped_column(TS)


class DocumentIssuanceLog(Base):
    """증명서 발급 기록"""

    __tablename__ = "document_issuance_logs"
    __table_args__ = (
        Index("idx_document_issuance_logs_account", "account_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))
    document_type: Mapped[str] = mapped_column(String(50))
    requested_by: Mapped[str] = mapped_column(String(40))
    issued_at: Mapped[datetime | None] = mapped_column(TS)
    status: Mapped[str] = mapped_column(String(20))
