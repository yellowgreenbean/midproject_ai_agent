SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 4. 예금·적금 상품 (상품 기획안 6장)
-- ---------------------------------------------------------------------

-- 상품
CREATE TABLE products (
  id           VARCHAR(40)    NOT NULL,
  bank         VARCHAR(30)    NOT NULL DEFAULT '두린은행',
  name         VARCHAR(100)   NOT NULL,
  type         VARCHAR(30)    NOT NULL,
  description  VARCHAR(1000)  NULL,
  status       VARCHAR(30)    NOT NULL DEFAULT 'ON_SALE',
  source_url   VARCHAR(500)   NULL,
  verified_at  CHAR(8)        NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_products_type CHECK (type IN ('TIME_DEPOSIT', 'INSTALLMENT_SAVINGS')),
  CONSTRAINT ck_products_status CHECK (status IN ('ON_SALE', 'STOPPED'))
);
COMMENT ON TABLE products IS '예금·적금 상품';
COMMENT ON COLUMN products.id IS '예: prod_001';
COMMENT ON COLUMN products.verified_at IS 'YYYYMMDD';

-- 기간별 금리
CREATE TABLE product_rates (
  id              VARCHAR(40)  NOT NULL,
  product_id      VARCHAR(40)  NOT NULL,
  term_min        INT          NOT NULL,
  term_max        INT          NOT NULL,
  term_unit       VARCHAR(30)  NOT NULL DEFAULT 'MONTH',
  base_rate       VARCHAR(10)  NOT NULL,
  bonus_rate      VARCHAR(10)  NULL,
  effective_from  CHAR(8)      NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_product_rates_product FOREIGN KEY (product_id) REFERENCES products (id),
  CONSTRAINT ck_product_rates_term_unit CHECK (term_unit IN ('MONTH', 'DAY'))
);
CREATE INDEX idx_product_rates_product ON product_rates (product_id, effective_from);
COMMENT ON TABLE product_rates IS '기간별 금리';
COMMENT ON COLUMN product_rates.base_rate IS '연 %';
COMMENT ON COLUMN product_rates.bonus_rate IS '우대 금리, 연 %';
COMMENT ON COLUMN product_rates.effective_from IS 'YYYYMMDD';

-- 가입 조건
CREATE TABLE product_rules (
  id            VARCHAR(40)  NOT NULL,
  product_id    VARCHAR(40)  NOT NULL,
  min_amount    BIGINT       NULL,
  max_amount    BIGINT       NULL,
  min_months    INT          NULL,
  max_months    INT          NULL,
  max_per_user  INT          NULL,
  rules_json    JSONB        NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_product_rules_product FOREIGN KEY (product_id) REFERENCES products (id)
);
CREATE INDEX idx_product_rules_product ON product_rules (product_id);
COMMENT ON TABLE product_rules IS '가입 조건';

-- RAG 문서
CREATE TABLE product_documents (
  id            VARCHAR(40)   NOT NULL,
  product_id    VARCHAR(40)   NOT NULL,
  title         VARCHAR(200)  NOT NULL,
  source_url    VARCHAR(500)  NULL,
  version_date  CHAR(8)       NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_product_documents_product FOREIGN KEY (product_id) REFERENCES products (id)
);
CREATE INDEX idx_product_documents_product ON product_documents (product_id);
COMMENT ON TABLE product_documents IS '상품 문서';
COMMENT ON COLUMN product_documents.version_date IS 'YYYYMMDD';

-- 가입
CREATE TABLE subscriptions (
  id                 VARCHAR(40)   NOT NULL,
  user_id            VARCHAR(40)   NOT NULL,
  product_id         VARCHAR(40)   NOT NULL,
  source_account_id  VARCHAR(40)   NOT NULL,
  principal          BIGINT        NULL,
  monthly_amount     BIGINT        NULL,
  applied_rate       VARCHAR(10)   NOT NULL,
  start_date         CHAR(8)       NOT NULL,
  maturity_date      CHAR(8)       NOT NULL,
  status             VARCHAR(30)   NOT NULL DEFAULT 'ACTIVE',
  closed_at          CHAR(8)       NULL,
  idempotency_key    VARCHAR(100)  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_subscriptions_idempotency_key UNIQUE (idempotency_key),
  CONSTRAINT fk_subscriptions_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_subscriptions_product FOREIGN KEY (product_id) REFERENCES products (id),
  CONSTRAINT fk_subscriptions_account FOREIGN KEY (source_account_id) REFERENCES accounts (id),
  CONSTRAINT ck_subscriptions_status CHECK (status IN ('ACTIVE', 'MATURED', 'TERMINATED'))
);
CREATE INDEX idx_subscriptions_user ON subscriptions (user_id);
CREATE INDEX idx_subscriptions_product ON subscriptions (product_id);
CREATE INDEX idx_subscriptions_account ON subscriptions (source_account_id);
COMMENT ON TABLE subscriptions IS '예금·적금 가입';
COMMENT ON COLUMN subscriptions.id IS '예: sub_001';
COMMENT ON COLUMN subscriptions.source_account_id IS '출금 계좌';
COMMENT ON COLUMN subscriptions.principal IS '예금 원금';
COMMENT ON COLUMN subscriptions.monthly_amount IS '적금 월 납입액';
COMMENT ON COLUMN subscriptions.applied_rate IS '연 %';
COMMENT ON COLUMN subscriptions.start_date IS 'YYYYMMDD';
COMMENT ON COLUMN subscriptions.maturity_date IS 'YYYYMMDD';
COMMENT ON COLUMN subscriptions.closed_at IS 'YYYYMMDD, 진행 중 NULL';
COMMENT ON COLUMN subscriptions.idempotency_key IS '중복 가입 방지';

-- 적금 납입
CREATE TABLE subscription_payments (
  id               VARCHAR(40)  NOT NULL,
  subscription_id  VARCHAR(40)  NOT NULL,
  paid_amount      BIGINT       NOT NULL,
  paid_at          CHAR(14)     NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_subscription_payments_subscription FOREIGN KEY (subscription_id) REFERENCES subscriptions (id)
);
CREATE INDEX idx_subscription_payments_subscription ON subscription_payments (subscription_id, paid_at);
COMMENT ON TABLE subscription_payments IS '적금 납입';
COMMENT ON COLUMN subscription_payments.paid_at IS 'YYYYMMDDHHmmss';
