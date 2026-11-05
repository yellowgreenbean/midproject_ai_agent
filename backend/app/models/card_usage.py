"""6. 카드 — 이용·청구·분석·포인트 — docs/sql/06_card_usage.sql 의 표 13개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, Boolean, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import FALSE, NOW, TRUE, TS, Base, one_of


class Merchant(Base):
    """가맹점"""

    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("business_no", name="uk_merchants_business_no"),
        Index("idx_merchants_category", "category_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    category_id: Mapped[str] = mapped_column(String(40), ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(100))
    business_no: Mapped[str | None] = mapped_column(String(12))  # 사업자등록번호


class CardTransaction(Base):
    """카드 이용 내역 — 카드 승인/이용 내역"""

    __tablename__ = "card_transactions"
    STATUS_VALUES = ("APPROVED", "PARTIAL_CANCELED", "CANCELED")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_card_transactions_status"),
        UniqueConstraint("user_card_id", "approval_no", name="uk_card_transactions_approval"),
        Index("idx_card_transactions_card_time", "user_card_id", "transacted_at"),
        Index("idx_card_transactions_merchant", "merchant_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    merchant_id: Mapped[str] = mapped_column(String(40), ForeignKey("merchants.id"))
    approval_no: Mapped[str] = mapped_column(String(20))
    transacted_at: Mapped[datetime] = mapped_column(TS)
    amount: Mapped[int] = mapped_column(BigInteger)  # 원화 승인 금액
    installment_months: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))  # 0 = 일시불
    is_overseas: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="KRW")
    foreign_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))  # 해외 결제 현지 통화 금액
    status: Mapped[str] = mapped_column(String(30), server_default="APPROVED")
    canceled_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    canceled_at: Mapped[datetime | None] = mapped_column(TS)
    applied_benefit_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_benefits.id"))  # 적용된 혜택 규칙
    benefit_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 할인/캐시백 금액
    is_performance_counted: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)  # FALSE = 실적 제외 (세금, 상품권 등)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class BillingCycleRule(Base):
    """결제일별 이용 기간 규칙 (예: 결제일 14일 → 전월 1일 ~ 전월 말일 = (-1, 1) ~ (-1, 99))"""

    __tablename__ = "billing_cycle_rules"

    card_company_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_companies.id"), primary_key=True)
    payment_day: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    start_month_offset: Mapped[int] = mapped_column(SmallInteger)  # 결제월 기준 이용 시작 월 (-2, -1)
    start_day: Mapped[int] = mapped_column(SmallInteger)
    end_month_offset: Mapped[int] = mapped_column(SmallInteger)  # 결제월 기준 이용 끝 월 (-1, 0)
    end_day: Mapped[int] = mapped_column(SmallInteger)  # 99 = 말일


class CardBill(Base):
    """카드 청구서 — 월별 청구서 (결제일 기준)"""

    __tablename__ = "card_bills"
    STATUS_VALUES = ("SCHEDULED", "CONFIRMED", "PAID", "OVERDUE")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_card_bills_status"),
        UniqueConstraint("user_card_id", "billing_ym", name="uk_bills_card_ym"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    billing_ym: Mapped[str] = mapped_column(CHAR(6))  # 결제 연월 YYYYMM
    usage_start: Mapped[date] = mapped_column(Date)  # 이용 기간 시작
    usage_end: Mapped[date] = mapped_column(Date)  # 이용 기간 끝
    payment_date: Mapped[date] = mapped_column(Date)  # 실제 결제(출금)일
    total_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    paid_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(30), server_default="SCHEDULED")  # SCHEDULED = 이용 기간 진행 중 / CONFIRMED = 청구 확정
    confirmed_at: Mapped[datetime | None] = mapped_column(TS)
    paid_at: Mapped[datetime | None] = mapped_column(TS)


class CardBillItem(Base):
    """청구 항목 (할부는 회차별로 여러 청구서에 나뉨)"""

    __tablename__ = "card_bill_items"
    __table_args__ = (
        UniqueConstraint("card_transaction_id", "installment_seq", name="uk_bill_items_tx_seq"),
        Index("idx_bill_items_bill", "bill_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    bill_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_bills.id"))
    card_transaction_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_transactions.id"))
    installment_seq: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))  # 할부 회차 (일시불 = 1)
    principal_amount: Mapped[int] = mapped_column(BigInteger)  # 이번 회차 원금
    fee_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 할부 수수료 (1차 무이자 0)


class RecurringPayment(Base):
    """고정지출 (자동 탐지 또는 사용자 등록)"""

    __tablename__ = "recurring_payments"
    DETECTED_BY_VALUES = ("AUTO", "USER")
    PAY_CYCLE_VALUES = ("MONTHLY", "YEARLY")
    __table_args__ = (
        one_of("detected_by", DETECTED_BY_VALUES, "ck_recurring_payments_detected_by"),
        one_of("pay_cycle", PAY_CYCLE_VALUES, "ck_recurring_payments_pay_cycle"),
        UniqueConstraint("user_card_id", "merchant_id", "pay_cycle", name="uk_recurring_card_merchant"),
        Index("idx_recurring_merchant", "merchant_id"),
        Index("idx_recurring_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    merchant_id: Mapped[str] = mapped_column(String(40), ForeignKey("merchants.id"))
    pay_cycle: Mapped[str] = mapped_column(String(30), server_default="MONTHLY")
    expected_amount: Mapped[int] = mapped_column(BigInteger)
    expected_day: Mapped[int] = mapped_column(SmallInteger)  # 예상 결제일 (일)
    last_paid_at: Mapped[date | None] = mapped_column(Date)
    detected_by: Mapped[str] = mapped_column(String(30), server_default="AUTO")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class SpendingForecast(Base):
    """사용 금액 예측 (일 배치 스냅샷)

    predicted_total = spent_to_date + confirmed_installment + fixed_expected + variable_expected
    """

    __tablename__ = "spending_forecasts"
    MODEL_TYPE_VALUES = ("MOVING_AVG", "LINEAR", "ML")
    __table_args__ = (
        one_of("model_type", MODEL_TYPE_VALUES, "ck_spending_forecasts_model_type"),
        UniqueConstraint("user_card_id", "billing_ym", "base_date", "model_type", name="uk_forecasts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    billing_ym: Mapped[str] = mapped_column(CHAR(6))  # 예측 대상 결제 연월
    base_date: Mapped[date] = mapped_column(Date)  # 예측 기준일
    spent_to_date: Mapped[int] = mapped_column(BigInteger)  # 기준일까지 이용 기간 내 일시불 사용액
    confirmed_installment: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 이미 확정된 이전 할부 회차분
    fixed_expected: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 남은 기간 고정지출 예정액
    variable_expected: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 남은 기간 변동지출 추정액
    predicted_total: Mapped[int] = mapped_column(BigInteger)
    model_type: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class DailyCardSpending(Base):
    """일별 사용액 집계 (시계열 예측 학습 데이터, 일 배치)"""

    __tablename__ = "daily_card_spending"

    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"), primary_key=True)
    spend_date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    fixed_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # recurring_payments 매칭분
    tx_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 1=월 ~ 7=일
    days_from_payday: Mapped[int | None] = mapped_column(SmallInteger)  # users.payday 기준 경과일
    is_holiday: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)


class CardIssuanceRanking(Base):
    """발급 순위 스냅샷"""

    __tablename__ = "card_issuance_rankings"
    CARD_TYPE_VALUES = ("ALL", "CREDIT", "CHECK")
    PERIOD_TYPE_VALUES = ("DAILY", "WEEKLY", "MONTHLY")
    SEGMENT_GENDER_VALUES = ("ALL", "M", "F")
    __table_args__ = (
        one_of("card_type", CARD_TYPE_VALUES, "ck_card_issuance_rankings_card_type"),
        one_of("period_type", PERIOD_TYPE_VALUES, "ck_card_issuance_rankings_period_type"),
        one_of("segment_gender", SEGMENT_GENDER_VALUES, "ck_card_issuance_rankings_segment_gender"),
        UniqueConstraint("period_type", "period_start", "segment_age", "segment_gender", "card_type", "rank_no", name="uk_rankings"),
        Index("idx_rankings_product", "card_product_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    period_type: Mapped[str] = mapped_column(String(30))
    period_start: Mapped[date] = mapped_column(Date)
    segment_age: Mapped[str] = mapped_column(String(10), server_default="ALL")  # ALL, 10s, 20s, 30s ...
    segment_gender: Mapped[str] = mapped_column(String(30), server_default="ALL")
    card_type: Mapped[str] = mapped_column(String(30), server_default="ALL")
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    rank_no: Mapped[int] = mapped_column(SmallInteger)
    issue_count: Mapped[int] = mapped_column(Integer)
    prev_rank_no: Mapped[int | None] = mapped_column(SmallInteger)  # 직전 기간 순위 (NULL = 신규 진입)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class CardPoint(Base):
    """카드 포인트 — 카드사별 포인트 잔액 (마이데이터 동기화)"""

    __tablename__ = "card_points"
    __table_args__ = (
        UniqueConstraint("user_id", "card_company_id", name="uk_card_points_user_company"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    card_company_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_companies.id"))
    point_name: Mapped[str | None] = mapped_column(String(30))  # 예: 마이신한포인트
    balance: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    expiring_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 소멸 예정 포인트
    expiring_date: Mapped[date | None] = mapped_column(Date)
    synced_at: Mapped[datetime] = mapped_column(TS)


class PointCashout(Base):
    """포인트 현금화 (카드사 단위로 1건, 입금은 transactions 의 POINT_CASHOUT 으로 기록)"""

    __tablename__ = "point_cashouts"
    STATUS_VALUES = ("REQUESTED", "COMPLETED", "FAILED")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_point_cashouts_status"),
        Index("idx_cashouts_account", "account_id"),
        Index("idx_cashouts_point", "card_point_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    card_point_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_points.id", ondelete="SET NULL"))  # 현금화한 포인트. 탈퇴로 card_points 를 지우면 NULL (기록은 보존, 기획서 C-6)
    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id"))  # 입금 계좌
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(30), server_default="REQUESTED")
    requested_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    completed_at: Mapped[datetime | None] = mapped_column(TS)


class MydataConsent(Base):
    """카드사별 마이데이터 연동 동의와 토큰"""

    __tablename__ = "mydata_consents"
    STATUS_VALUES = ("ACTIVE", "EXPIRED", "REVOKED")
    __table_args__ = (
        one_of("status", STATUS_VALUES, "ck_mydata_consents_status"),
        UniqueConstraint("user_id", "card_company_id", name="uk_consents_user_company"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    card_company_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_companies.id"))
    access_token_enc: Mapped[str] = mapped_column(String(512))  # 암호화 저장
    refresh_token_enc: Mapped[str | None] = mapped_column(String(512))
    scope: Mapped[str] = mapped_column(String(255))  # 예: card.list card.approval card.bill card.point
    status: Mapped[str] = mapped_column(String(30), server_default="ACTIVE")
    consented_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    expires_at: Mapped[datetime] = mapped_column(TS)
    last_synced_at: Mapped[datetime | None] = mapped_column(TS)


class MydataSyncLog(Base):
    """마이데이터 동기화 기록"""

    __tablename__ = "mydata_sync_logs"
    API_TYPE_VALUES = ("CARDS", "APPROVALS", "BILLS", "POINTS")
    RESULT_VALUES = ("SUCCESS", "FAILED")
    __table_args__ = (
        one_of("api_type", API_TYPE_VALUES, "ck_mydata_sync_logs_api_type"),
        one_of("result", RESULT_VALUES, "ck_mydata_sync_logs_result"),
        Index("idx_sync_logs_consent", "mydata_consent_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    mydata_consent_id: Mapped[str] = mapped_column(String(40), ForeignKey("mydata_consents.id"))
    api_type: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(TS)
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    result: Mapped[str | None] = mapped_column(String(30))
    fetched_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(String(500))
