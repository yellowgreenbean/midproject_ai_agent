"""1. 회원·인증 — docs/sql/01_users.sql 의 표 10개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import NOW, TS, Base, one_of


class User(Base):
    """회원"""

    __tablename__ = "users"
    GENDER_VALUES = ("M", "F")
    STATUS_VALUES = ("ACTIVE", "PENDING_VERIFICATION", "RESTRICTED", "WITHDRAWN")
    __table_args__ = (
        one_of("gender", GENDER_VALUES, "ck_users_gender"),
        CheckConstraint("payday IS NULL OR payday BETWEEN 1 AND 31", name="ck_users_payday"),
        one_of("status", STATUS_VALUES, "ck_users_status"),
        UniqueConstraint("username", name="uk_users_username"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # 예: user_001
    username: Mapped[str] = mapped_column(String(50))  # 로그인 아이디
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None] = mapped_column(TS)  # NULL = 미인증
    birth_date: Mapped[date] = mapped_column(Date)  # YYYY-MM-DD
    gender: Mapped[str] = mapped_column(String(30))
    payday: Mapped[int | None] = mapped_column(SmallInteger)  # 월급일 1~31, 빈 값 가능
    status: Mapped[str] = mapped_column(String(30), server_default="PENDING_VERIFICATION")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    withdrawn_at: Mapped[datetime | None] = mapped_column(TS)  # NULL = 미탈퇴


class AuthIdentity(Base):
    """로그인 수단 (LOCAL / GOOGLE)"""

    __tablename__ = "auth_identities"
    PROVIDER_VALUES = ("LOCAL", "GOOGLE")
    __table_args__ = (
        one_of("provider", PROVIDER_VALUES, "ck_auth_identities_provider"),
        UniqueConstraint("provider", "provider_subject", name="uk_auth_identities_provider"),
        Index("idx_auth_identities_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(30))
    provider_subject: Mapped[str] = mapped_column(String(255))  # 공급자 쪽 사용자 식별값
    linked_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class LocalCredential(Base):
    """비밀번호 (회원 1 : 0..1)"""

    __tablename__ = "local_credentials"

    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    password_updated_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 로그인·본인 확인 실패 횟수
    locked_until: Mapped[datetime | None] = mapped_column(TS)


class EmailVerification(Base):
    """이메일 인증 (가입 전이라 회원과 연결 없음)"""

    __tablename__ = "email_verifications"
    __table_args__ = (
        Index("idx_email_verifications_email", "email", "purpose"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(30))
    challenge_digest: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(TS)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    used_at: Mapped[datetime | None] = mapped_column(TS)


class PasswordResetToken(Base):
    """비밀번호 재설정 토큰"""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uk_password_reset_tokens_digest"),
        Index("idx_password_reset_tokens_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    token_digest: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(TS)
    used_at: Mapped[datetime | None] = mapped_column(TS)


class AuthSession(Base):
    """로그인 세션"""

    __tablename__ = "sessions"
    __table_args__ = (
        Index("idx_sessions_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    last_seen_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)


class PinCredential(Base):
    """PIN (회원 1 : 0..1)"""

    __tablename__ = "pin_credentials"

    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"), primary_key=True)
    pin_hash: Mapped[str] = mapped_column(String(255))
    enabled_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    changed_at: Mapped[datetime | None] = mapped_column(TS)
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(TS)


class AuthAuditLog(Base):
    """인증 기록 — 인증 감사 기록"""

    __tablename__ = "auth_audit_logs"
    __table_args__ = (
        Index("idx_auth_audit_logs_user", "user_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    outcome: Mapped[str] = mapped_column(String(30))
    request_id: Mapped[str | None] = mapped_column(String(64))


class StepUpChallenge(Base):
    """본인 확인 (이체·예약 이체·카드 신청/해지/관리·가입·계좌 상태 변경·탈퇴·정보 변경·PIN 등록/변경/재설정)"""

    __tablename__ = "step_up_challenges"
    ACTION_VALUES = ("TRANSFER", "SCHEDULED_TRANSFER", "CARD_APPLICATION", "CARD_TERMINATION", "CARD_MANAGEMENT", "SUBSCRIPTION", "ACCOUNT_STATUS_CHANGE", "WITHDRAWAL", "PROFILE_CHANGE", "PIN_ENROLL", "PIN_CHANGE", "PIN_RESET")
    __table_args__ = (
        one_of("action", ACTION_VALUES, "ck_step_up_challenges_action"),
        Index("idx_step_up_session", "session_id"),
        Index("idx_step_up_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    session_id: Mapped[str] = mapped_column(String(40), ForeignKey("sessions.id"))  # 그 세션에서 받은 확인
    expires_at: Mapped[datetime] = mapped_column(TS)
    consumed_at: Mapped[datetime | None] = mapped_column(TS)  # NULL = 아직 사용 안 함


class WithdrawalCheck(Base):
    """탈퇴 점검"""

    __tablename__ = "withdrawal_checks"
    STATUS_VALUES = ("IN_PROGRESS", "COMPLETED", "CANCELED")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_withdrawal_checks_status"),
        Index("idx_withdrawal_checks_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), server_default="IN_PROGRESS")
    started_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    balance_verified_at: Mapped[datetime | None] = mapped_column(TS)
    data_review_confirmed_at: Mapped[datetime | None] = mapped_column(TS)
    data_review_version: Mapped[str | None] = mapped_column(String(20))
    linked_services_confirmed_at: Mapped[datetime | None] = mapped_column(TS)
    completed_at: Mapped[datetime | None] = mapped_column(TS)
