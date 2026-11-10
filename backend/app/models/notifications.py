"""7. 알림 — docs/sql/07_notifications.sql 의 표 1개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import NOW, TS, Base, one_of


class Notification(Base):
    """알림"""

    __tablename__ = "notifications"
    TYPE_VALUES = ("TRANSACTION", "PAYMENT_DUE", "LOW_BALANCE", "OVERDUE", "PERFORMANCE", "POINT_EXPIRING", "ANNUAL_FEE", "UNUSED_CARD", "APPLICATION", "CARD_STATUS", "INACTIVE_ACCOUNT", "MATURITY", "SECURITY")
    __table_args__ = (
        one_of("type", TYPE_VALUES, "ck_notifications_type"),
        UniqueConstraint("event_id", "user_id", "type", name="uk_notifications_event"),
        Index("idx_notifications_account", "account_id"),
        Index("idx_notifications_card", "user_card_id"),
        Index("idx_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    account_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("accounts.id"))  # 계좌 알림이면, 카드 알림이면 NULL
    user_card_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("user_cards.id"))  # 카드 알림이면
    event_id: Mapped[str | None] = mapped_column(String(64))  # 원인 이벤트 (예: 거래 확정)
    type: Mapped[str] = mapped_column(String(30))  # 알림 종류 12개 (기획서 Part 6 C-5)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), server_default="SENT")
    read_at: Mapped[datetime | None] = mapped_column(TS)  # NULL = 안 읽음
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
