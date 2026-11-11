"""5. 카드 — 상품·발급·보유 — docs/sql/05_card_products.sql 의 표 19개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, Boolean, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import FALSE, NOW, TRUE, TM, TS, Base, one_of


class CardCompany(Base):
    """카드사"""

    __tablename__ = "card_companies"
    __table_args__ = (
        UniqueConstraint("code", name="uk_card_companies_code"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    code: Mapped[str] = mapped_column(String(10))  # 예: SHINHAN, HYUNDAI, TOSSBANK
    name: Mapped[str] = mapped_column(String(30))
    logo_url: Mapped[str | None] = mapped_column(String(255))
    customer_center: Mapped[str | None] = mapped_column(String(20))


class Category(Base):
    """업종/혜택 카테고리 (가맹점 분류와 혜택 대상 분류에 공통 사용)"""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("code", name="uk_categories_code"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("categories.id"))  # 상위 분류 (예: 교통 > 대중교통)
    code: Mapped[str] = mapped_column(String(30))  # 예: TRANSPORT, CONVENIENCE, TELECOM
    name: Mapped[str] = mapped_column(String(30))


class CardProduct(Base):
    """카드 상품"""

    __tablename__ = "card_products"
    BRAND_VALUES = ("VISA", "MASTER", "AMEX", "JCB", "UNIONPAY", "LOCAL")
    CARD_TYPE_VALUES = ("CREDIT", "CHECK")
    __table_args__ = (
        one_of("brand", BRAND_VALUES, "ck_card_products_brand"),
        one_of("card_type", CARD_TYPE_VALUES, "ck_card_products_card_type"),
        Index("idx_card_products_company", "card_company_id"),
        Index("idx_card_products_type_active", "card_type", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    card_company_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_companies.id"))
    name: Mapped[str] = mapped_column(String(100))
    card_type: Mapped[str] = mapped_column(String(30))
    brand: Mapped[str] = mapped_column(String(30))
    annual_fee_domestic: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 국내전용 연회비
    annual_fee_overseas: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 해외겸용 연회비
    min_age: Mapped[int] = mapped_column(SmallInteger, server_default=text("19"))  # 발급 가능 최소 나이
    image_url: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(String(255))  # 한 줄 혜택 요약
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)  # FALSE = 단종 (보유는 가능, 신규 발급 불가)
    released_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class CardPerformanceTier(Base):
    """전월 실적 구간 (period = QUARTER 는 분기 실적 구간, 2026-11-10 추가)"""

    __tablename__ = "card_performance_tiers"
    PERIOD_VALUES = ("MONTH", "QUARTER")
    __table_args__ = (
        one_of("period", PERIOD_VALUES, "ck_card_performance_tiers_period"),
        UniqueConstraint("card_product_id", "period", "tier_level", name="uk_tiers_product_level"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    period: Mapped[str] = mapped_column(String(10), server_default="MONTH")  # MONTH = 전월 실적, QUARTER = 지난 분기 실적
    tier_level: Mapped[int] = mapped_column(SmallInteger)  # 1부터, 클수록 높은 구간 (period 마다 따로 센다)
    min_spend: Mapped[int] = mapped_column(BigInteger)  # 구간 진입 실적(이상)
    max_spend: Mapped[int | None] = mapped_column(BigInteger)  # 구간 상한(미만), NULL = 상한 없음


class CardBenefitLimitGroup(Base):
    """혜택 통합 월 한도 — 여러 혜택이 함께 쓰는 통합 월 한도 (예: 「칼퇴 4개 업종 통합 월 4천 원」, 2026-11-10 추가)"""

    __tablename__ = "card_benefit_limit_groups"
    __table_args__ = (
        Index("idx_limit_groups_product", "card_product_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    tier_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_performance_tiers.id"))  # 이 실적 구간일 때의 한도 (구간마다 한 행), NULL = 실적 조건 없음
    name: Mapped[str] = mapped_column(String(50))
    monthly_limit_amount: Mapped[int] = mapped_column(Integer)


class CardBenefit(Base):
    """카드 혜택 규칙 (조건 칸 limit_group_id ~ daily_limit_count 는 2026-11-10 추가 — 실제 카드 혜택 조건을 담으려고)"""

    __tablename__ = "card_benefits"
    BENEFIT_TYPE_VALUES = ("DISCOUNT", "CASHBACK", "POINT", "MILEAGE", "FEE_WAIVER")
    PAYMENT_CHANNEL_VALUES = ("ONLINE", "OFFLINE")
    VALUE_TYPE_VALUES = ("PERCENT", "FIXED", "PER_LITER")
    __table_args__ = (
        one_of("benefit_type", BENEFIT_TYPE_VALUES, "ck_card_benefits_benefit_type"),
        one_of("payment_channel", PAYMENT_CHANNEL_VALUES, "ck_card_benefits_payment_channel"),
        one_of("value_type", VALUE_TYPE_VALUES, "ck_card_benefits_value_type"),
        Index("idx_benefits_category", "category_id"),
        Index("idx_benefits_product", "card_product_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    tier_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_performance_tiers.id"))  # 이 실적 구간일 때의 규칙 (한도가 구간마다 달라 구간마다 한 행), NULL = 실적 조건 없음
    category_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("categories.id"))  # NULL = 모든 가맹점. 상위 업종이면 하위 업종도 포함 (교통 → 택시)
    benefit_type: Mapped[str] = mapped_column(String(30))
    value_type: Mapped[str] = mapped_column(String(30))
    benefit_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # PERCENT면 %, FIXED면 원, PER_LITER면 리터당 원
    min_payment_amount: Mapped[int | None] = mapped_column(Integer)  # 건당 최소 결제 금액
    monthly_limit_amount: Mapped[int | None] = mapped_column(Integer)  # 이 혜택만의 월 혜택 한도(원). 통합 한도는 limit_group_id
    monthly_limit_count: Mapped[int | None] = mapped_column(Integer)  # 월 적용 횟수 한도
    is_instant: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)  # 즉시 캐시백 여부
    description: Mapped[str | None] = mapped_column(String(255))  # 칸으로 못 담은 조건 (원문 요약)
    limit_group_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_benefit_limit_groups.id"))  # 같은 그룹끼리 통합 월 한도를 함께 씀
    merchant_names: Mapped[str | None] = mapped_column(String(255))  # 이 가맹점에서만 (쉼표로 구분), NULL = 업종 전체
    payment_channel: Mapped[str | None] = mapped_column(String(10))  # ONLINE = 온라인 결제만, OFFLINE = 매장 결제만, NULL = 둘 다
    pay_methods: Mapped[str | None] = mapped_column(String(100))  # 이 간편결제로 결제할 때만 (쉼표로 구분), NULL = 결제 수단 무관
    days_of_week: Mapped[str | None] = mapped_column(String(30))  # 이 요일만 (MON~SUN 쉼표로 구분), NULL = 매일
    time_start: Mapped[time | None] = mapped_column(TM)  # 이 시각부터 (time_end 와 함께), NULL = 종일
    time_end: Mapped[time | None] = mapped_column(TM)  # 이 시각까지 (포함하지 않음)
    max_eligible_amount: Mapped[int | None] = mapped_column(Integer)  # 건당 혜택 계산에 쓰는 결제 금액 상한 (예: 5만 원까지만 10%)
    per_payment_max_benefit: Mapped[int | None] = mapped_column(Integer)  # 건당 최대 혜택 금액(원)
    daily_limit_count: Mapped[int | None] = mapped_column(SmallInteger)  # 하루 적용 횟수 한도


class Terms(Base):
    """약관 (회원 파트 1장, card_product_id NULL = 공통 약관)"""

    __tablename__ = "terms"
    __table_args__ = (
        Index("idx_terms_card_product", "card_product_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(100))
    required: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)  # 필수 약관인지, 선택 약관은 FALSE (원본 schema.sql 이름 is_required)
    content_url: Mapped[str] = mapped_column(String(255))  # 약관 본문 위치 (예: docs/terms/<약관>.md 경로나 URL). 동의 화면과 챗봇 RAG가 같은 본문을 읽음
    effective_at: Mapped[datetime] = mapped_column(TS)
    card_product_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_products.id"))  # 카드 상품 약관이면 그 카드 상품, 공통 약관은 NULL


class UserConsent(Base):
    """약관 동의 (회원 파트 1장)"""

    __tablename__ = "user_consents"
    __table_args__ = (
        Index("idx_user_consents_terms", "terms_id"),
        Index("idx_user_consents_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    terms_id: Mapped[str] = mapped_column(String(40), ForeignKey("terms.id"))
    version: Mapped[str] = mapped_column(String(10))  # 동의한 약관 버전
    agreed: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class Promotion(Base):
    """발급 프로모션"""

    __tablename__ = "promotions"
    __table_args__ = (
        Index("idx_promotions_product_period", "card_product_id", "starts_at", "ends_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    title: Mapped[str] = mapped_column(String(100))
    reward_amount: Mapped[int] = mapped_column(Integer)  # 지급 리워드(원)
    min_spend_condition: Mapped[int | None] = mapped_column(BigInteger)  # 리워드 조건: 발급 후 N원 이상 사용
    condition_desc: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(TS)
    ends_at: Mapped[datetime] = mapped_column(TS)


class CardRecommendation(Base):
    """카드 추천 결과 (6장 그림, card_applications 가 참조하므로 먼저 만듦)"""

    __tablename__ = "card_recommendations"
    __table_args__ = (
        Index("idx_recommendations_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    analysis_start: Mapped[date] = mapped_column(Date)  # 분석한 소비 기간 시작
    analysis_end: Mapped[date] = mapped_column(Date)
    expected_monthly_benefit: Mapped[int] = mapped_column(BigInteger)  # 월 예상 혜택
    annual_fee: Mapped[int] = mapped_column(Integer)
    net_annual_benefit: Mapped[int] = mapped_column(BigInteger)  # 연 예상 혜택 - 연회비
    rank_no: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class CardRecommendationDetail(Base):
    """추천 근거 (업종별)"""

    __tablename__ = "card_recommendation_details"
    __table_args__ = (
        Index("idx_rec_details_category", "category_id"),
    )

    recommendation_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_recommendations.id"), primary_key=True)
    category_id: Mapped[str] = mapped_column(String(40), ForeignKey("categories.id"), primary_key=True)
    spend_amount: Mapped[int] = mapped_column(BigInteger)  # 분석 기간 월평균 지출
    benefit_amount: Mapped[int] = mapped_column(BigInteger)  # 월 예상 혜택 (한도 적용 후)


class CardApplication(Base):
    """카드 발급 신청 — 발급 신청"""

    __tablename__ = "card_applications"
    REJECT_REASON_VALUES = ("AGE", "NO_INCOME", "DUPLICATE")
    STATUS_VALUES = ("APPLIED", "REVIEWING", "APPROVED", "REJECTED", "SHIPPING", "DELIVERED", "ACTIVATED", "CANCELED")
    __table_args__ = (
        one_of("reject_reason", REJECT_REASON_VALUES, "ck_card_applications_reject_reason"),
        one_of("status", STATUS_VALUES, "ck_card_applications_status"),
        Index("idx_applications_product_applied", "card_product_id", "applied_at"),
        Index("idx_applications_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    promotion_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("promotions.id"))
    recommendation_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_recommendations.id", ondelete="SET NULL"))  # 추천으로 신청한 경우. 탈퇴로 추천 결과를 지우면 NULL (기획서 C-6)
    step_up_challenge_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("step_up_challenges.id"))  # 신청 때 본인 확인
    status: Mapped[str] = mapped_column(String(30), server_default="APPLIED")
    job_type: Mapped[str | None] = mapped_column(String(30))  # 직장인/자영업/학생 등 (신용카드 심사용)
    annual_income: Mapped[int | None] = mapped_column(BigInteger)
    linked_account_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("accounts.id"))  # 연결 계좌
    payment_day: Mapped[int | None] = mapped_column(SmallInteger)  # 희망 결제일 (신용카드)
    approved_credit_limit: Mapped[int | None] = mapped_column(BigInteger)  # 심사 승인 한도 (신용카드)
    delivery_address: Mapped[str] = mapped_column(String(255))
    tracking_no: Mapped[str | None] = mapped_column(String(50))
    reject_reason: Mapped[str | None] = mapped_column(String(30))
    applied_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    decided_at: Mapped[datetime | None] = mapped_column(TS)  # 승인/거절 시각
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class ApplicationStatusHistory(Base):
    """발급 신청 상태 이력"""

    __tablename__ = "application_status_histories"
    __table_args__ = (
        Index("idx_app_histories_application", "application_id", "changed_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_applications.id"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    memo: Mapped[str | None] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class ApplicationTermAgreement(Base):
    """신청 약관 동의 — 신청별 약관 동의"""

    __tablename__ = "application_term_agreements"
    __table_args__ = (
        Index("idx_agreements_terms", "terms_id"),
    )

    application_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_applications.id"), primary_key=True)
    terms_id: Mapped[str] = mapped_column(String(40), ForeignKey("terms.id"), primary_key=True)
    agreed: Mapped[bool] = mapped_column(Boolean)
    agreed_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class UserCard(Base):
    """보유 카드 (토스 경유 발급 + 마이데이터 연동 카드)"""

    __tablename__ = "user_cards"
    SOURCE_VALUES = ("TOSS_ISSUED", "MYDATA")
    STATUS_VALUES = ("ACTIVE", "SUSPENDED", "LOST", "EXPIRED", "TERMINATED")
    __table_args__ = (
        one_of("source", SOURCE_VALUES, "ck_user_cards_source"),
        one_of("status", STATUS_VALUES, "ck_user_cards_status"),
        UniqueConstraint("application_id", name="uk_user_cards_application"),
        UniqueConstraint("user_id", "org_card_id", name="uk_user_cards_org"),
        Index("idx_user_cards_account", "linked_account_id"),
        Index("idx_user_cards_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    card_product_id: Mapped[str] = mapped_column(String(40), ForeignKey("card_products.id"))
    application_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("card_applications.id"))  # 토스 경유 발급인 경우 원 신청
    reissued_from_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("user_cards.id"))  # 분실/만료 재발급 시 이전 카드
    source: Mapped[str] = mapped_column(String(30))
    org_card_id: Mapped[str | None] = mapped_column(String(64))  # 마이데이터 카드사 측 card_id (동기화 upsert 키)
    nickname: Mapped[str | None] = mapped_column(String(30))
    card_number_masked: Mapped[str] = mapped_column(String(25))  # 예: 5310-****-****-1234
    last4: Mapped[str] = mapped_column(CHAR(4))
    expires_at: Mapped[date | None] = mapped_column(Date)  # 유효기간 (해당 월 말일). 더미 resValidPeriod 가 빈 값이면 NULL (기획서 C-2 #6)
    linked_account_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("accounts.id"))  # 체크카드 출금 계좌 / 신용카드 결제 계좌
    payment_day: Mapped[int | None] = mapped_column(SmallInteger)  # 결제일 1~31, 체크카드는 NULL
    credit_limit: Mapped[int | None] = mapped_column(BigInteger)  # 신용카드만
    status: Mapped[str] = mapped_column(String(30), server_default="ACTIVE")
    annual_fee_amount: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 실제 적용 연회비
    next_annual_fee_date: Mapped[date | None] = mapped_column(Date)  # 다음 연회비 청구 예정일
    last_used_at: Mapped[datetime | None] = mapped_column(TS)  # 마지막 거래 시각 (배치 갱신)
    issued_at: Mapped[datetime | None] = mapped_column(TS)  # 발급 시각. 더미 resIssueDate 가 빈 값이면 NULL (기획서 C-2 #6)
    activated_at: Mapped[datetime | None] = mapped_column(TS)
    terminated_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class UserCardSetting(Base):
    """카드 관리 설정 (1 : 0..1)"""

    __tablename__ = "user_card_settings"

    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"), primary_key=True)
    overseas_payment_blocked: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)
    online_payment_blocked: Mapped[bool] = mapped_column(Boolean, server_default=FALSE)
    daily_limit: Mapped[int | None] = mapped_column(BigInteger)
    monthly_limit: Mapped[int | None] = mapped_column(BigInteger)
    payment_alert_enabled: Mapped[bool] = mapped_column(Boolean, server_default=TRUE)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class UserCardStatusHistory(Base):
    """카드 상태 이력 — 카드 상태 변경 이력"""

    __tablename__ = "user_card_status_histories"
    __table_args__ = (
        Index("idx_card_histories_card", "user_card_id", "changed_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class CardManagementLog(Base):
    """카드 관리 기록 (결제 차단, 한도, 비밀번호, 결제·출금 계좌 바꾸기 — 비밀번호 값은 저장하지 않음)"""

    __tablename__ = "card_management_logs"
    ACTION_TYPE_VALUES = ("BLOCK_OVERSEAS", "UNBLOCK_OVERSEAS", "BLOCK_ONLINE", "UNBLOCK_ONLINE", "LIMIT_CHANGE", "PIN_CHANGE", "LINKED_ACCOUNT_CHANGE")
    RESULT_VALUES = ("SUCCESS", "FAILED")
    __table_args__ = (
        one_of("action_type", ACTION_TYPE_VALUES, "ck_card_management_logs_action_type"),
        one_of("result", RESULT_VALUES, "ck_card_management_logs_result"),
        Index("idx_mgmt_logs_card", "user_card_id", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    action_type: Mapped[str] = mapped_column(String(30))
    before_value: Mapped[str | None] = mapped_column(String(50))  # PIN_CHANGE는 값 저장 금지
    after_value: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[str] = mapped_column(String(30))
    requested_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)


class CardTermination(Base):
    """카드 해지 (해지 전 확인 정보를 스냅샷으로 저장)"""

    __tablename__ = "card_terminations"
    REASON_CODE_VALUES = ("LOW_BENEFIT", "HIGH_FEE", "NOT_USING", "SWITCH_CARD", "OTHER")
    STATUS_VALUES = ("REQUESTED", "COMPLETED", "REJECTED", "CANCELED")
    __table_args__ = (
        one_of("reason_code", REASON_CODE_VALUES, "ck_card_terminations_reason_code"),
        one_of("status", STATUS_VALUES, "ck_card_terminations_status"),
        Index("idx_terminations_card", "user_card_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_card_id: Mapped[str] = mapped_column(String(40), ForeignKey("user_cards.id"))
    step_up_challenge_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("step_up_challenges.id"))  # 해지 요청 본인 확인
    status: Mapped[str] = mapped_column(String(30), server_default="REQUESTED")
    reason_code: Mapped[str] = mapped_column(String(30))
    reason_detail: Mapped[str | None] = mapped_column(String(255))
    unpaid_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 미결제 금액
    remaining_installment_amount: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 남은 할부 원금
    linked_recurring_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 연결된 자동결제 건수
    forfeited_points: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))  # 소멸 예정 포인트
    refunded_annual_fee: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 연회비 일할 환급액
    requested_at: Mapped[datetime] = mapped_column(TS, server_default=NOW)
    completed_at: Mapped[datetime | None] = mapped_column(TS)
