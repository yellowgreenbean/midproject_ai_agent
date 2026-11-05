-- ---------------------------------------------------------------------
-- 6. 카드 — 이용·청구·분석·포인트 (파트 A 1-1·1-4~1-6)
--    card_recommendations / card_recommendation_details 는 5장에 있음
-- ---------------------------------------------------------------------

-- 가맹점
CREATE TABLE merchants (
  id           VARCHAR(40)   NOT NULL,
  category_id  VARCHAR(40)   NOT NULL,
  name         VARCHAR(100)  NOT NULL,
  business_no  VARCHAR(12)   NULL COMMENT '사업자등록번호',
  PRIMARY KEY (id),
  UNIQUE KEY uk_merchants_business_no (business_no),
  KEY idx_merchants_category (category_id),
  CONSTRAINT fk_merchants_category FOREIGN KEY (category_id) REFERENCES categories (id)
) COMMENT='가맹점';

-- 카드 승인/이용 내역
CREATE TABLE card_transactions (
  id                      VARCHAR(40)    NOT NULL,
  user_card_id            VARCHAR(40)    NOT NULL,
  merchant_id             VARCHAR(40)    NOT NULL,
  approval_no             VARCHAR(20)    NOT NULL,
  transacted_at           DATETIME       NOT NULL,
  amount                  BIGINT         NOT NULL COMMENT '원화 승인 금액',
  installment_months      TINYINT        NOT NULL DEFAULT 0 COMMENT '0 = 일시불',
  is_overseas             BOOLEAN        NOT NULL DEFAULT FALSE,
  currency                CHAR(3)        NOT NULL DEFAULT 'KRW',
  foreign_amount          DECIMAL(15,2)  NULL     COMMENT '해외 결제 현지 통화 금액',
  status                  ENUM('APPROVED','PARTIAL_CANCELED','CANCELED') NOT NULL DEFAULT 'APPROVED',
  canceled_amount         BIGINT         NOT NULL DEFAULT 0,
  canceled_at             DATETIME       NULL,
  applied_benefit_id      VARCHAR(40)    NULL     COMMENT '적용된 혜택 규칙',
  benefit_amount          BIGINT         NOT NULL DEFAULT 0 COMMENT '할인/캐시백 금액',
  is_performance_counted  BOOLEAN        NOT NULL DEFAULT TRUE COMMENT 'FALSE = 실적 제외 (세금, 상품권 등)',
  created_at              DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_card_transactions_approval (user_card_id, approval_no),
  KEY idx_card_transactions_card_time (user_card_id, transacted_at),
  KEY idx_card_transactions_merchant (merchant_id),
  CONSTRAINT fk_card_transactions_card     FOREIGN KEY (user_card_id)       REFERENCES user_cards (id),
  CONSTRAINT fk_card_transactions_merchant FOREIGN KEY (merchant_id)        REFERENCES merchants (id),
  CONSTRAINT fk_card_transactions_benefit  FOREIGN KEY (applied_benefit_id) REFERENCES card_benefits (id)
) COMMENT='카드 이용 내역';

-- 결제일별 이용 기간 규칙 (예: 결제일 14일 → 전월 1일 ~ 전월 말일 = (-1, 1) ~ (-1, 99))
CREATE TABLE billing_cycle_rules (
  card_company_id     VARCHAR(40)  NOT NULL,
  payment_day         TINYINT      NOT NULL,
  start_month_offset  TINYINT      NOT NULL COMMENT '결제월 기준 이용 시작 월 (-2, -1)',
  start_day           TINYINT      NOT NULL,
  end_month_offset    TINYINT      NOT NULL COMMENT '결제월 기준 이용 끝 월 (-1, 0)',
  end_day             TINYINT      NOT NULL COMMENT '99 = 말일',
  PRIMARY KEY (card_company_id, payment_day),
  CONSTRAINT fk_cycle_rules_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id)
) COMMENT='결제일별 이용 기간 규칙';

-- 월별 청구서 (결제일 기준)
CREATE TABLE card_bills (
  id            VARCHAR(40)  NOT NULL,
  user_card_id  VARCHAR(40)  NOT NULL,
  billing_ym    CHAR(6)      NOT NULL COMMENT '결제 연월 YYYYMM',
  usage_start   DATE         NOT NULL COMMENT '이용 기간 시작',
  usage_end     DATE         NOT NULL COMMENT '이용 기간 끝',
  payment_date  DATE         NOT NULL COMMENT '실제 결제(출금)일',
  total_amount  BIGINT       NOT NULL DEFAULT 0,
  paid_amount   BIGINT       NOT NULL DEFAULT 0,
  status        ENUM('SCHEDULED','CONFIRMED','PAID','OVERDUE') NOT NULL DEFAULT 'SCHEDULED'
                COMMENT 'SCHEDULED = 이용 기간 진행 중 / CONFIRMED = 청구 확정',
  confirmed_at  DATETIME     NULL,
  paid_at       DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_bills_card_ym (user_card_id, billing_ym),
  CONSTRAINT fk_bills_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='카드 청구서';

-- 청구 항목 (할부는 회차별로 여러 청구서에 나뉨)
CREATE TABLE card_bill_items (
  id                   VARCHAR(40)  NOT NULL,
  bill_id              VARCHAR(40)  NOT NULL,
  card_transaction_id  VARCHAR(40)  NOT NULL,
  installment_seq      TINYINT      NOT NULL DEFAULT 1 COMMENT '할부 회차 (일시불 = 1)',
  principal_amount     BIGINT       NOT NULL COMMENT '이번 회차 원금',
  fee_amount           BIGINT       NOT NULL DEFAULT 0 COMMENT '할부 수수료 (1차 무이자 0)',
  PRIMARY KEY (id),
  UNIQUE KEY uk_bill_items_tx_seq (card_transaction_id, installment_seq),
  KEY idx_bill_items_bill (bill_id),
  CONSTRAINT fk_bill_items_bill        FOREIGN KEY (bill_id)             REFERENCES card_bills (id),
  CONSTRAINT fk_bill_items_transaction FOREIGN KEY (card_transaction_id) REFERENCES card_transactions (id)
) COMMENT='청구 항목';

-- 고정지출 (자동 탐지 또는 사용자 등록)
CREATE TABLE recurring_payments (
  id               VARCHAR(40)  NOT NULL,
  user_id          VARCHAR(40)  NOT NULL,
  user_card_id     VARCHAR(40)  NOT NULL,
  merchant_id      VARCHAR(40)  NOT NULL,
  pay_cycle        ENUM('MONTHLY','YEARLY') NOT NULL DEFAULT 'MONTHLY',
  expected_amount  BIGINT       NOT NULL,
  expected_day     TINYINT      NOT NULL COMMENT '예상 결제일 (일)',
  last_paid_at     DATE         NULL,
  detected_by      ENUM('AUTO','USER') NOT NULL DEFAULT 'AUTO',
  is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_recurring_card_merchant (user_card_id, merchant_id, pay_cycle),
  KEY idx_recurring_user (user_id),
  KEY idx_recurring_merchant (merchant_id),
  CONSTRAINT fk_recurring_user     FOREIGN KEY (user_id)      REFERENCES users (id),
  CONSTRAINT fk_recurring_card     FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT fk_recurring_merchant FOREIGN KEY (merchant_id)  REFERENCES merchants (id)
) COMMENT='고정지출';

-- 사용 금액 예측 (일 배치 스냅샷)
-- predicted_total = spent_to_date + confirmed_installment + fixed_expected + variable_expected
CREATE TABLE spending_forecasts (
  id                     VARCHAR(40)  NOT NULL,
  user_card_id           VARCHAR(40)  NOT NULL,
  billing_ym             CHAR(6)      NOT NULL COMMENT '예측 대상 결제 연월',
  base_date              DATE         NOT NULL COMMENT '예측 기준일',
  spent_to_date          BIGINT       NOT NULL COMMENT '기준일까지 이용 기간 내 일시불 사용액',
  confirmed_installment  BIGINT       NOT NULL DEFAULT 0 COMMENT '이미 확정된 이전 할부 회차분',
  fixed_expected         BIGINT       NOT NULL DEFAULT 0 COMMENT '남은 기간 고정지출 예정액',
  variable_expected      BIGINT       NOT NULL DEFAULT 0 COMMENT '남은 기간 변동지출 추정액',
  predicted_total        BIGINT       NOT NULL,
  model_type             ENUM('MOVING_AVG','LINEAR','ML') NOT NULL,
  created_at             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_forecasts (user_card_id, billing_ym, base_date, model_type),
  CONSTRAINT fk_forecasts_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='사용 금액 예측';

-- 일별 사용액 집계 (시계열 예측 학습 데이터, 일 배치)
CREATE TABLE daily_card_spending (
  user_card_id      VARCHAR(40)  NOT NULL,
  spend_date        DATE         NOT NULL,
  total_amount      BIGINT       NOT NULL DEFAULT 0,
  fixed_amount      BIGINT       NOT NULL DEFAULT 0 COMMENT 'recurring_payments 매칭분',
  tx_count          INT          NOT NULL DEFAULT 0,
  weekday           TINYINT      NOT NULL COMMENT '1=월 ~ 7=일',
  days_from_payday  TINYINT      NULL     COMMENT 'users.payday 기준 경과일',
  is_holiday        BOOLEAN      NOT NULL DEFAULT FALSE,
  PRIMARY KEY (user_card_id, spend_date),
  CONSTRAINT fk_daily_spending_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='일별 사용액 집계';

-- 발급 순위 스냅샷
CREATE TABLE card_issuance_rankings (
  id               VARCHAR(40)  NOT NULL,
  period_type      ENUM('DAILY','WEEKLY','MONTHLY') NOT NULL,
  period_start     DATE         NOT NULL,
  segment_age      VARCHAR(10)  NOT NULL DEFAULT 'ALL' COMMENT 'ALL, 10s, 20s, 30s ...',
  segment_gender   ENUM('ALL','M','F') NOT NULL DEFAULT 'ALL',
  card_type        ENUM('ALL','CREDIT','CHECK') NOT NULL DEFAULT 'ALL',
  card_product_id  VARCHAR(40)  NOT NULL,
  rank_no          SMALLINT     NOT NULL,
  issue_count      INT          NOT NULL,
  prev_rank_no     SMALLINT     NULL     COMMENT '직전 기간 순위 (NULL = 신규 진입)',
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_rankings (period_type, period_start, segment_age, segment_gender, card_type, rank_no),
  KEY idx_rankings_product (card_product_id),
  CONSTRAINT fk_rankings_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
) COMMENT='발급 순위';

-- 카드사별 포인트 잔액 (마이데이터 동기화)
CREATE TABLE card_points (
  id               VARCHAR(40)  NOT NULL,
  user_id          VARCHAR(40)  NOT NULL,
  card_company_id  VARCHAR(40)  NOT NULL,
  point_name       VARCHAR(30)  NULL     COMMENT '예: 마이신한포인트',
  balance          BIGINT       NOT NULL DEFAULT 0,
  expiring_amount  BIGINT       NOT NULL DEFAULT 0 COMMENT '소멸 예정 포인트',
  expiring_date    DATE         NULL,
  synced_at        DATETIME     NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_card_points_user_company (user_id, card_company_id),
  CONSTRAINT fk_card_points_user    FOREIGN KEY (user_id)         REFERENCES users (id),
  CONSTRAINT fk_card_points_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id)
) COMMENT='카드 포인트';

-- 포인트 현금화 (카드사 단위로 1건, 입금은 transactions 의 POINT_CASHOUT 으로 기록)
CREATE TABLE point_cashouts (
  id             VARCHAR(40)  NOT NULL,
  card_point_id  VARCHAR(40)  NOT NULL,
  account_id     VARCHAR(40)  NOT NULL COMMENT '입금 계좌',
  amount         BIGINT       NOT NULL,
  status         ENUM('REQUESTED','COMPLETED','FAILED') NOT NULL DEFAULT 'REQUESTED',
  requested_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at   DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_cashouts_point (card_point_id),
  KEY idx_cashouts_account (account_id),
  CONSTRAINT fk_cashouts_point   FOREIGN KEY (card_point_id) REFERENCES card_points (id),
  CONSTRAINT fk_cashouts_account FOREIGN KEY (account_id)    REFERENCES accounts (id)
) COMMENT='포인트 현금화';

-- 카드사별 마이데이터 연동 동의와 토큰
CREATE TABLE mydata_consents (
  id                 VARCHAR(40)   NOT NULL,
  user_id            VARCHAR(40)   NOT NULL,
  card_company_id    VARCHAR(40)   NOT NULL,
  access_token_enc   VARCHAR(512)  NOT NULL COMMENT '암호화 저장',
  refresh_token_enc  VARCHAR(512)  NULL,
  scope              VARCHAR(255)  NOT NULL COMMENT '예: card.list card.approval card.bill card.point',
  status             ENUM('ACTIVE','EXPIRED','REVOKED') NOT NULL DEFAULT 'ACTIVE',
  consented_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at         DATETIME      NOT NULL,
  last_synced_at     DATETIME      NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_consents_user_company (user_id, card_company_id),
  CONSTRAINT fk_consents_user    FOREIGN KEY (user_id)         REFERENCES users (id),
  CONSTRAINT fk_consents_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id)
) COMMENT='마이데이터 연동 동의';

-- 마이데이터 동기화 기록
CREATE TABLE mydata_sync_logs (
  id                 VARCHAR(40)   NOT NULL,
  mydata_consent_id  VARCHAR(40)   NOT NULL,
  api_type           ENUM('CARDS','APPROVALS','BILLS','POINTS') NOT NULL,
  started_at         DATETIME      NOT NULL,
  finished_at        DATETIME      NULL,
  result             ENUM('SUCCESS','FAILED') NULL,
  fetched_count      INT           NOT NULL DEFAULT 0,
  error_message      VARCHAR(500)  NULL,
  PRIMARY KEY (id),
  KEY idx_sync_logs_consent (mydata_consent_id, started_at),
  CONSTRAINT fk_sync_logs_consent FOREIGN KEY (mydata_consent_id) REFERENCES mydata_consents (id)
) COMMENT='마이데이터 동기화 기록';