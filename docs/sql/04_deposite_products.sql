-- ---------------------------------------------------------------------
-- 4. 예금·적금 상품 (상품 기획안 6장)
-- ---------------------------------------------------------------------

-- 상품
CREATE TABLE products (
  id           VARCHAR(40)    NOT NULL COMMENT '예: prod_001',
  bank         VARCHAR(30)    NOT NULL DEFAULT '두린은행',
  name         VARCHAR(100)   NOT NULL,
  type         ENUM('TIME_DEPOSIT','INSTALLMENT_SAVINGS') NOT NULL,
  description  VARCHAR(1000)  NULL,
  status       ENUM('ON_SALE','STOPPED') NOT NULL DEFAULT 'ON_SALE',
  source_url   VARCHAR(500)   NULL,
  verified_at  CHAR(8)        NULL     COMMENT 'YYYYMMDD',
  PRIMARY KEY (id)
) COMMENT='예금·적금 상품';

-- 기간별 금리
CREATE TABLE product_rates (
  id              VARCHAR(40)  NOT NULL,
  product_id      VARCHAR(40)  NOT NULL,
  term_min        INT          NOT NULL,
  term_max        INT          NOT NULL,
  term_unit       ENUM('MONTH','DAY') NOT NULL DEFAULT 'MONTH',
  base_rate       VARCHAR(10)  NOT NULL COMMENT '연 %',
  bonus_rate      VARCHAR(10)  NULL     COMMENT '우대 금리, 연 %',
  effective_from  CHAR(8)      NOT NULL COMMENT 'YYYYMMDD',
  PRIMARY KEY (id),
  KEY idx_product_rates_product (product_id, effective_from),
  CONSTRAINT fk_product_rates_product FOREIGN KEY (product_id) REFERENCES products (id)
) COMMENT='기간별 금리';

-- 가입 조건
CREATE TABLE product_rules (
  id            VARCHAR(40)  NOT NULL,
  product_id    VARCHAR(40)  NOT NULL,
  min_amount    BIGINT       NULL,
  max_amount    BIGINT       NULL,
  min_months    INT          NULL,
  max_months    INT          NULL,
  max_per_user  INT          NULL,
  rules_json    JSON         NULL,
  PRIMARY KEY (id),
  KEY idx_product_rules_product (product_id),
  CONSTRAINT fk_product_rules_product FOREIGN KEY (product_id) REFERENCES products (id)
) COMMENT='가입 조건';

-- RAG 문서
CREATE TABLE product_documents (
  id            VARCHAR(40)   NOT NULL,
  product_id    VARCHAR(40)   NOT NULL,
  title         VARCHAR(200)  NOT NULL,
  source_url    VARCHAR(500)  NULL,
  version_date  CHAR(8)       NULL     COMMENT 'YYYYMMDD',
  PRIMARY KEY (id),
  KEY idx_product_documents_product (product_id),
  CONSTRAINT fk_product_documents_product FOREIGN KEY (product_id) REFERENCES products (id)
) COMMENT='상품 문서';

-- 가입
CREATE TABLE subscriptions (
  id                 VARCHAR(40)   NOT NULL COMMENT '예: sub_001',
  user_id            VARCHAR(40)   NOT NULL,
  product_id         VARCHAR(40)   NOT NULL,
  source_account_id  VARCHAR(40)   NOT NULL COMMENT '출금 계좌',
  principal          BIGINT        NULL     COMMENT '예금 원금',
  monthly_amount     BIGINT        NULL     COMMENT '적금 월 납입액',
  applied_rate       VARCHAR(10)   NOT NULL COMMENT '연 %',
  start_date         CHAR(8)       NOT NULL COMMENT 'YYYYMMDD',
  maturity_date      CHAR(8)       NOT NULL COMMENT 'YYYYMMDD',
  status             ENUM('ACTIVE','MATURED','TERMINATED') NOT NULL DEFAULT 'ACTIVE',
  closed_at          CHAR(8)       NULL     COMMENT 'YYYYMMDD, 진행 중 NULL',
  idempotency_key    VARCHAR(100)  NOT NULL COMMENT '중복 가입 방지',
  PRIMARY KEY (id),
  UNIQUE KEY uk_subscriptions_idempotency_key (idempotency_key),
  KEY idx_subscriptions_user (user_id),
  KEY idx_subscriptions_product (product_id),
  KEY idx_subscriptions_account (source_account_id),
  CONSTRAINT fk_subscriptions_user    FOREIGN KEY (user_id)           REFERENCES users (id),
  CONSTRAINT fk_subscriptions_product FOREIGN KEY (product_id)        REFERENCES products (id),
  CONSTRAINT fk_subscriptions_account FOREIGN KEY (source_account_id) REFERENCES accounts (id)
) COMMENT='예금·적금 가입';

-- 적금 납입
CREATE TABLE subscription_payments (
  id               VARCHAR(40)  NOT NULL,
  subscription_id  VARCHAR(40)  NOT NULL,
  paid_amount      BIGINT       NOT NULL,
  paid_at          CHAR(14)     NOT NULL COMMENT 'YYYYMMDDHHmmss',
  PRIMARY KEY (id),
  KEY idx_subscription_payments_subscription (subscription_id, paid_at),
  CONSTRAINT fk_subscription_payments_subscription FOREIGN KEY (subscription_id) REFERENCES subscriptions (id)
) COMMENT='적금 납입';