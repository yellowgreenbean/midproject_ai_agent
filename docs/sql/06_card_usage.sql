SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 6. 카드 — 이용·청구·분석·포인트 (파트 A 1-1·1-4~1-6)
--    card_recommendations / card_recommendation_details 는 5장에 있음
-- ---------------------------------------------------------------------

-- 가맹점
CREATE TABLE merchants (
  id           VARCHAR(40)   NOT NULL,
  category_id  VARCHAR(40)   NOT NULL,
  name         VARCHAR(100)  NOT NULL,
  business_no  VARCHAR(12)   NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_merchants_business_no UNIQUE (business_no),
  CONSTRAINT fk_merchants_category FOREIGN KEY (category_id) REFERENCES categories (id)
);
CREATE INDEX idx_merchants_category ON merchants (category_id);
COMMENT ON TABLE merchants IS '가맹점';
COMMENT ON COLUMN merchants.business_no IS '사업자등록번호';

-- 카드 승인/이용 내역
CREATE TABLE card_transactions (
  id                      VARCHAR(40)    NOT NULL,
  user_card_id            VARCHAR(40)    NOT NULL,
  merchant_id             VARCHAR(40)    NOT NULL,
  approval_no             VARCHAR(20)    NOT NULL,
  transacted_at           TIMESTAMP(0)   NOT NULL,
  amount                  BIGINT         NOT NULL,
  installment_months      SMALLINT       NOT NULL DEFAULT 0,
  is_overseas             BOOLEAN        NOT NULL DEFAULT FALSE,
  currency                CHAR(3)        NOT NULL DEFAULT 'KRW',
  foreign_amount          DECIMAL(15,2)  NULL,
  status                  VARCHAR(30)    NOT NULL DEFAULT 'APPROVED',
  canceled_amount         BIGINT         NOT NULL DEFAULT 0,
  canceled_at             TIMESTAMP(0)   NULL,
  applied_benefit_id      VARCHAR(40)    NULL,
  benefit_amount          BIGINT         NOT NULL DEFAULT 0,
  is_performance_counted  BOOLEAN        NOT NULL DEFAULT TRUE,
  created_at              TIMESTAMP(0)   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_card_transactions_approval UNIQUE (user_card_id, approval_no),
  CONSTRAINT fk_card_transactions_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT fk_card_transactions_merchant FOREIGN KEY (merchant_id) REFERENCES merchants (id),
  CONSTRAINT fk_card_transactions_benefit FOREIGN KEY (applied_benefit_id) REFERENCES card_benefits (id),
  CONSTRAINT ck_card_transactions_status CHECK (status IN ('APPROVED', 'PARTIAL_CANCELED', 'CANCELED'))
);
CREATE INDEX idx_card_transactions_card_time ON card_transactions (user_card_id, transacted_at);
CREATE INDEX idx_card_transactions_merchant ON card_transactions (merchant_id);
COMMENT ON TABLE card_transactions IS '카드 이용 내역';
COMMENT ON COLUMN card_transactions.amount IS '원화 승인 금액';
COMMENT ON COLUMN card_transactions.installment_months IS '0 = 일시불';
COMMENT ON COLUMN card_transactions.foreign_amount IS '해외 결제 현지 통화 금액';
COMMENT ON COLUMN card_transactions.applied_benefit_id IS '적용된 혜택 규칙';
COMMENT ON COLUMN card_transactions.benefit_amount IS '할인/캐시백 금액';
COMMENT ON COLUMN card_transactions.is_performance_counted IS 'FALSE = 실적 제외 (세금, 상품권 등)';

-- 결제일별 이용 기간 규칙 (예: 결제일 14일 → 전월 1일 ~ 전월 말일 = (-1, 1) ~ (-1, 99))
CREATE TABLE billing_cycle_rules (
  card_company_id     VARCHAR(40)  NOT NULL,
  payment_day         SMALLINT     NOT NULL,
  start_month_offset  SMALLINT     NOT NULL,
  start_day           SMALLINT     NOT NULL,
  end_month_offset    SMALLINT     NOT NULL,
  end_day             SMALLINT     NOT NULL,
  PRIMARY KEY (card_company_id, payment_day),
  CONSTRAINT fk_cycle_rules_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id)
);
COMMENT ON TABLE billing_cycle_rules IS '결제일별 이용 기간 규칙';
COMMENT ON COLUMN billing_cycle_rules.start_month_offset IS '결제월 기준 이용 시작 월 (-2, -1)';
COMMENT ON COLUMN billing_cycle_rules.end_month_offset IS '결제월 기준 이용 끝 월 (-1, 0)';
COMMENT ON COLUMN billing_cycle_rules.end_day IS '99 = 말일';

-- 월별 청구서 (결제일 기준)
CREATE TABLE card_bills (
  id            VARCHAR(40)   NOT NULL,
  user_card_id  VARCHAR(40)   NOT NULL,
  billing_ym    CHAR(6)       NOT NULL,
  usage_start   DATE          NOT NULL,
  usage_end     DATE          NOT NULL,
  payment_date  DATE          NOT NULL,
  total_amount  BIGINT        NOT NULL DEFAULT 0,
  paid_amount   BIGINT        NOT NULL DEFAULT 0,
  status        VARCHAR(30)   NOT NULL DEFAULT 'SCHEDULED',
  confirmed_at  TIMESTAMP(0)  NULL,
  paid_at       TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_bills_card_ym UNIQUE (user_card_id, billing_ym),
  CONSTRAINT fk_bills_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT ck_card_bills_status CHECK (status IN ('SCHEDULED', 'CONFIRMED', 'PAID', 'OVERDUE'))
);
COMMENT ON TABLE card_bills IS '카드 청구서';
COMMENT ON COLUMN card_bills.billing_ym IS '결제 연월 YYYYMM';
COMMENT ON COLUMN card_bills.usage_start IS '이용 기간 시작';
COMMENT ON COLUMN card_bills.usage_end IS '이용 기간 끝';
COMMENT ON COLUMN card_bills.payment_date IS '실제 결제(출금)일';
COMMENT ON COLUMN card_bills.status IS 'SCHEDULED = 이용 기간 진행 중 / CONFIRMED = 청구 확정';

-- 청구 항목 (할부는 회차별로 여러 청구서에 나뉨)
CREATE TABLE card_bill_items (
  id                   VARCHAR(40)  NOT NULL,
  bill_id              VARCHAR(40)  NOT NULL,
  card_transaction_id  VARCHAR(40)  NOT NULL,
  installment_seq      SMALLINT     NOT NULL DEFAULT 1,
  principal_amount     BIGINT       NOT NULL,
  fee_amount           BIGINT       NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  CONSTRAINT uk_bill_items_tx_seq UNIQUE (card_transaction_id, installment_seq),
  CONSTRAINT fk_bill_items_bill FOREIGN KEY (bill_id) REFERENCES card_bills (id),
  CONSTRAINT fk_bill_items_transaction FOREIGN KEY (card_transaction_id) REFERENCES card_transactions (id)
);
CREATE INDEX idx_bill_items_bill ON card_bill_items (bill_id);
COMMENT ON TABLE card_bill_items IS '청구 항목';
COMMENT ON COLUMN card_bill_items.installment_seq IS '할부 회차 (일시불 = 1)';
COMMENT ON COLUMN card_bill_items.principal_amount IS '이번 회차 원금';
COMMENT ON COLUMN card_bill_items.fee_amount IS '할부 수수료 (1차 무이자 0)';

-- 고정지출 (자동 탐지 또는 사용자 등록)
CREATE TABLE recurring_payments (
  id               VARCHAR(40)   NOT NULL,
  user_id          VARCHAR(40)   NOT NULL,
  user_card_id     VARCHAR(40)   NOT NULL,
  merchant_id      VARCHAR(40)   NOT NULL,
  pay_cycle        VARCHAR(30)   NOT NULL DEFAULT 'MONTHLY',
  expected_amount  BIGINT        NOT NULL,
  expected_day     SMALLINT      NOT NULL,
  last_paid_at     DATE          NULL,
  detected_by      VARCHAR(30)   NOT NULL DEFAULT 'AUTO',
  is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_recurring_card_merchant UNIQUE (user_card_id, merchant_id, pay_cycle),
  CONSTRAINT fk_recurring_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_recurring_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT fk_recurring_merchant FOREIGN KEY (merchant_id) REFERENCES merchants (id),
  CONSTRAINT ck_recurring_payments_pay_cycle CHECK (pay_cycle IN ('MONTHLY', 'YEARLY')),
  CONSTRAINT ck_recurring_payments_detected_by CHECK (detected_by IN ('AUTO', 'USER'))
);
CREATE INDEX idx_recurring_user ON recurring_payments (user_id);
CREATE INDEX idx_recurring_merchant ON recurring_payments (merchant_id);
COMMENT ON TABLE recurring_payments IS '고정지출';
COMMENT ON COLUMN recurring_payments.expected_day IS '예상 결제일 (일)';

-- 사용 금액 예측 (일 배치 스냅샷)
-- predicted_total = spent_to_date + confirmed_installment + fixed_expected + variable_expected
CREATE TABLE spending_forecasts (
  id                     VARCHAR(40)   NOT NULL,
  user_card_id           VARCHAR(40)   NOT NULL,
  billing_ym             CHAR(6)       NOT NULL,
  base_date              DATE          NOT NULL,
  spent_to_date          BIGINT        NOT NULL,
  confirmed_installment  BIGINT        NOT NULL DEFAULT 0,
  fixed_expected         BIGINT        NOT NULL DEFAULT 0,
  variable_expected      BIGINT        NOT NULL DEFAULT 0,
  predicted_total        BIGINT        NOT NULL,
  model_type             VARCHAR(30)   NOT NULL,
  created_at             TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_forecasts UNIQUE (user_card_id, billing_ym, base_date, model_type),
  CONSTRAINT fk_forecasts_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT ck_spending_forecasts_model_type CHECK (model_type IN ('MOVING_AVG', 'LINEAR', 'ML'))
);
COMMENT ON TABLE spending_forecasts IS '사용 금액 예측';
COMMENT ON COLUMN spending_forecasts.billing_ym IS '예측 대상 결제 연월';
COMMENT ON COLUMN spending_forecasts.base_date IS '예측 기준일';
COMMENT ON COLUMN spending_forecasts.spent_to_date IS '기준일까지 이용 기간 내 일시불 사용액';
COMMENT ON COLUMN spending_forecasts.confirmed_installment IS '이미 확정된 이전 할부 회차분';
COMMENT ON COLUMN spending_forecasts.fixed_expected IS '남은 기간 고정지출 예정액';
COMMENT ON COLUMN spending_forecasts.variable_expected IS '남은 기간 변동지출 추정액';

-- 일별 사용액 집계 (시계열 예측 학습 데이터, 일 배치)
CREATE TABLE daily_card_spending (
  user_card_id      VARCHAR(40)  NOT NULL,
  spend_date        DATE         NOT NULL,
  total_amount      BIGINT       NOT NULL DEFAULT 0,
  fixed_amount      BIGINT       NOT NULL DEFAULT 0,
  tx_count          INT          NOT NULL DEFAULT 0,
  weekday           SMALLINT     NOT NULL,
  days_from_payday  SMALLINT     NULL,
  is_holiday        BOOLEAN      NOT NULL DEFAULT FALSE,
  PRIMARY KEY (user_card_id, spend_date),
  CONSTRAINT fk_daily_spending_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
);
COMMENT ON TABLE daily_card_spending IS '일별 사용액 집계';
COMMENT ON COLUMN daily_card_spending.fixed_amount IS 'recurring_payments 매칭분';
COMMENT ON COLUMN daily_card_spending.weekday IS '1=월 ~ 7=일';
COMMENT ON COLUMN daily_card_spending.days_from_payday IS 'users.payday 기준 경과일';

-- 발급 순위 스냅샷
CREATE TABLE card_issuance_rankings (
  id               VARCHAR(40)   NOT NULL,
  period_type      VARCHAR(30)   NOT NULL,
  period_start     DATE          NOT NULL,
  segment_age      VARCHAR(10)   NOT NULL DEFAULT 'ALL',
  segment_gender   VARCHAR(30)   NOT NULL DEFAULT 'ALL',
  card_type        VARCHAR(30)   NOT NULL DEFAULT 'ALL',
  card_product_id  VARCHAR(40)   NOT NULL,
  rank_no          SMALLINT      NOT NULL,
  issue_count      INT           NOT NULL,
  prev_rank_no     SMALLINT      NULL,
  created_at       TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_rankings UNIQUE (period_type, period_start, segment_age, segment_gender, card_type, rank_no),
  CONSTRAINT fk_rankings_product FOREIGN KEY (card_product_id) REFERENCES card_products (id),
  CONSTRAINT ck_card_issuance_rankings_period_type CHECK (period_type IN ('DAILY', 'WEEKLY', 'MONTHLY')),
  CONSTRAINT ck_card_issuance_rankings_segment_gender CHECK (segment_gender IN ('ALL', 'M', 'F')),
  CONSTRAINT ck_card_issuance_rankings_card_type CHECK (card_type IN ('ALL', 'CREDIT', 'CHECK'))
);
CREATE INDEX idx_rankings_product ON card_issuance_rankings (card_product_id);
COMMENT ON TABLE card_issuance_rankings IS '발급 순위';
COMMENT ON COLUMN card_issuance_rankings.segment_age IS 'ALL, 10s, 20s, 30s ...';
COMMENT ON COLUMN card_issuance_rankings.prev_rank_no IS '직전 기간 순위 (NULL = 신규 진입)';

-- 카드사별 포인트 잔액 (마이데이터 동기화)
CREATE TABLE card_points (
  id               VARCHAR(40)   NOT NULL,
  user_id          VARCHAR(40)   NOT NULL,
  card_company_id  VARCHAR(40)   NOT NULL,
  point_name       VARCHAR(30)   NULL,
  balance          BIGINT        NOT NULL DEFAULT 0,
  expiring_amount  BIGINT        NOT NULL DEFAULT 0,
  expiring_date    DATE          NULL,
  synced_at        TIMESTAMP(0)  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_card_points_user_company UNIQUE (user_id, card_company_id),
  CONSTRAINT fk_card_points_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_card_points_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id)
);
COMMENT ON TABLE card_points IS '카드 포인트';
COMMENT ON COLUMN card_points.point_name IS '예: 마이신한포인트';
COMMENT ON COLUMN card_points.expiring_amount IS '소멸 예정 포인트';

-- 포인트 현금화 (카드사 단위로 1건, 입금은 transactions 의 POINT_CASHOUT 으로 기록)
CREATE TABLE point_cashouts (
  id             VARCHAR(40)   NOT NULL,
  card_point_id  VARCHAR(40)   NOT NULL,
  account_id     VARCHAR(40)   NOT NULL,
  amount         BIGINT        NOT NULL,
  status         VARCHAR(30)   NOT NULL DEFAULT 'REQUESTED',
  requested_at   TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at   TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_cashouts_point FOREIGN KEY (card_point_id) REFERENCES card_points (id),
  CONSTRAINT fk_cashouts_account FOREIGN KEY (account_id) REFERENCES accounts (id),
  CONSTRAINT ck_point_cashouts_status CHECK (status IN ('REQUESTED', 'COMPLETED', 'FAILED'))
);
CREATE INDEX idx_cashouts_point ON point_cashouts (card_point_id);
CREATE INDEX idx_cashouts_account ON point_cashouts (account_id);
COMMENT ON TABLE point_cashouts IS '포인트 현금화';
COMMENT ON COLUMN point_cashouts.account_id IS '입금 계좌';

-- 카드사별 마이데이터 연동 동의와 토큰
CREATE TABLE mydata_consents (
  id                 VARCHAR(40)   NOT NULL,
  user_id            VARCHAR(40)   NOT NULL,
  card_company_id    VARCHAR(40)   NOT NULL,
  access_token_enc   VARCHAR(512)  NOT NULL,
  refresh_token_enc  VARCHAR(512)  NULL,
  scope              VARCHAR(255)  NOT NULL,
  status             VARCHAR(30)   NOT NULL DEFAULT 'ACTIVE',
  consented_at       TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at         TIMESTAMP(0)  NOT NULL,
  last_synced_at     TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_consents_user_company UNIQUE (user_id, card_company_id),
  CONSTRAINT fk_consents_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_consents_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id),
  CONSTRAINT ck_mydata_consents_status CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED'))
);
COMMENT ON TABLE mydata_consents IS '마이데이터 연동 동의';
COMMENT ON COLUMN mydata_consents.access_token_enc IS '암호화 저장';
COMMENT ON COLUMN mydata_consents.scope IS '예: card.list card.approval card.bill card.point';

-- 마이데이터 동기화 기록
CREATE TABLE mydata_sync_logs (
  id                 VARCHAR(40)   NOT NULL,
  mydata_consent_id  VARCHAR(40)   NOT NULL,
  api_type           VARCHAR(30)   NOT NULL,
  started_at         TIMESTAMP(0)  NOT NULL,
  finished_at        TIMESTAMP(0)  NULL,
  result             VARCHAR(30)   NULL,
  fetched_count      INT           NOT NULL DEFAULT 0,
  error_message      VARCHAR(500)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_sync_logs_consent FOREIGN KEY (mydata_consent_id) REFERENCES mydata_consents (id),
  CONSTRAINT ck_mydata_sync_logs_api_type CHECK (api_type IN ('CARDS', 'APPROVALS', 'BILLS', 'POINTS')),
  CONSTRAINT ck_mydata_sync_logs_result CHECK (result IN ('SUCCESS', 'FAILED'))
);
CREATE INDEX idx_sync_logs_consent ON mydata_sync_logs (mydata_consent_id, started_at);
COMMENT ON TABLE mydata_sync_logs IS '마이데이터 동기화 기록';
