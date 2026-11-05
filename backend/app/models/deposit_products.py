"""4. 예금·적금 상품 — docs/sql/04_deposite_products.sql 의 표 6개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from typing import Any

from sqlalchemy import CHAR, BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, one_of


class Product(Base):
    """예금·적금 상품 — 상품"""

    __tablename__ = "products"
    STATUS_VALUES = ("ON_SALE", "STOPPED")
    TYPE_VALUES = ("TIME_DEPOSIT", "INSTALLMENT_SAVINGS")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_products_status"),
        one_of("type", TYPE_VALUES, "ck_products_type"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # 예: prod_001
    bank: Mapped[str] = mapped_column(String(30), server_default="두린은행")
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), server_default="ON_SALE")
    source_url: Mapped[str | None] = mapped_column(String(500))
    verified_at: Mapped[str | None] = mapped_column(CHAR(8))  # YYYYMMDD


class ProductRate(Base):
    """기간별 금리"""

    __tablename__ = "product_rates"
    TERM_UNIT_VALUES = ("MONTH", "DAY")
    __table_args__ = (
        one_of("term_unit", TERM_UNIT_VALUES, "ck_product_rates_term_unit"),
        Index("idx_product_rates_product", "product_id", "effective_from"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"))
    term_min: Mapped[int] = mapped_column(Integer)
    term_max: Mapped[int] = mapped_column(Integer)
    term_unit: Mapped[str] = mapped_column(String(30), server_default="MONTH")
    base_rate: Mapped[str] = mapped_column(String(10))  # 연 %
    bonus_rate: Mapped[str | None] = mapped_column(String(10))  # 우대 금리, 연 %
    effective_from: Mapped[str] = mapped_column(CHAR(8))  # YYYYMMDD


class ProductRule(Base):
    """가입 조건"""

    __tablename__ = "product_rules"
    __table_args__ = (
        Index("idx_product_rules_product", "product_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"))
    min_amount: Mapped[int | None] = mapped_column(BigInteger)
    max_amount: Mapped[int | None] = mapped_column(BigInteger)
    min_months: Mapped[int | None] = mapped_column(Integer)
    max_months: Mapped[int | None] = mapped_column(Integer)
    max_per_user: Mapped[int | None] = mapped_column(Integer)
    rules_json: Mapped[Any | None] = mapped_column(JSONB)


class ProductDocument(Base):
    """상품 문서 — RAG 문서"""

    __tablename__ = "product_documents"
    __table_args__ = (
        Index("idx_product_documents_product", "product_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"))
    title: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    version_date: Mapped[str | None] = mapped_column(CHAR(8))  # YYYYMMDD


class Subscription(Base):
    """예금·적금 가입 — 가입"""

    __tablename__ = "subscriptions"
    STATUS_VALUES = ("ACTIVE", "MATURED", "TERMINATED")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_subscriptions_status"),
        UniqueConstraint("idempotency_key", name="uk_subscriptions_idempotency_key"),
        Index("idx_subscriptions_account", "source_account_id"),
        Index("idx_subscriptions_product", "product_id"),
        Index("idx_subscriptions_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # 예: sub_001
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"))
    source_account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))  # 출금 계좌
    principal: Mapped[int | None] = mapped_column(BigInteger)  # 예금은 예치금, 적금은 지금까지 납입한 누계
    monthly_amount: Mapped[int | None] = mapped_column(BigInteger)  # 적금 월 납입액. 예금과 자유적금은 NULL
    applied_rate: Mapped[str] = mapped_column(String(10))  # 연 %
    start_date: Mapped[str] = mapped_column(CHAR(8))  # YYYYMMDD
    maturity_date: Mapped[str] = mapped_column(CHAR(8))  # YYYYMMDD
    status: Mapped[str] = mapped_column(String(30), server_default="ACTIVE")
    closed_at: Mapped[str | None] = mapped_column(CHAR(8))  # YYYYMMDD, 진행 중 NULL
    idempotency_key: Mapped[str] = mapped_column(String(100))  # 중복 가입 방지


class SubscriptionPayment(Base):
    """적금 납입"""

    __tablename__ = "subscription_payments"
    __table_args__ = (
        Index("idx_subscription_payments_subscription", "subscription_id", "paid_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(40), ForeignKey("subscriptions.id"))
    paid_amount: Mapped[int] = mapped_column(BigInteger)
    paid_at: Mapped[str] = mapped_column(CHAR(14))  # YYYYMMDDHHmmss
