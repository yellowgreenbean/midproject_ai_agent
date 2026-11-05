SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 2. 계좌 (회원·계좌 기획서 8장)
--    notifications 는 user_cards 를 참조하므로 맨 뒤(7장)에 만듦
--    account_balance_view 는 3장의 account_balances 위에 만듦
-- ---------------------------------------------------------------------

-- 계좌 (잔액은 account_balances 에 있음)
CREATE TABLE accounts (
  id                     VARCHAR(40)   NOT NULL,
  user_id                VARCHAR(40)   NOT NULL,
  "resAccount"           VARCHAR(20)   NOT NULL,
  "resAccountDisplay"    VARCHAR(30)   NOT NULL,
  "resAccountName"       VARCHAR(100)  NOT NULL,
  account_type           VARCHAR(30)   NOT NULL,
  lifecycle_status       VARCHAR(30)   NOT NULL DEFAULT 'ACTIVE',
  "resAccountNickName"   VARCHAR(50)   NULL,
  is_favorite            BOOLEAN       NOT NULL DEFAULT FALSE,
  "resAccountStartDate"  CHAR(8)       NOT NULL,
  closed_at              CHAR(8)       NULL,
  version                INT           NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  CONSTRAINT uk_accounts_res_account UNIQUE ("resAccount"),
  CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT ck_accounts_account_type CHECK (account_type IN ('CHECKING', 'SAVINGS')),
  CONSTRAINT ck_accounts_lifecycle_status CHECK (lifecycle_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);
CREATE INDEX idx_accounts_user_status ON accounts (user_id, lifecycle_status);
COMMENT ON TABLE accounts IS '계좌';
COMMENT ON COLUMN accounts."resAccount" IS '계좌번호(숫자만)';
COMMENT ON COLUMN accounts."resAccountDisplay" IS '예: 110-00-000001';
COMMENT ON COLUMN accounts."resAccountName" IS '상품명';
COMMENT ON COLUMN accounts."resAccountStartDate" IS 'YYYYMMDD';
COMMENT ON COLUMN accounts.closed_at IS 'YYYYMMDD, 해지 전 NULL';
COMMENT ON COLUMN accounts.version IS '낙관적 잠금';

-- 계좌 관리 기록
CREATE TABLE account_activity_logs (
  id           VARCHAR(40)   NOT NULL,
  account_id   VARCHAR(40)   NOT NULL,
  actor_id     VARCHAR(40)   NOT NULL,
  action       VARCHAR(50)   NOT NULL,
  occurred_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata     JSONB         NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_account_activity_logs_account FOREIGN KEY (account_id) REFERENCES accounts (id)
);
CREATE INDEX idx_account_activity_logs_account ON account_activity_logs (account_id, occurred_at);
COMMENT ON TABLE account_activity_logs IS '계좌 관리 기록';
COMMENT ON COLUMN account_activity_logs.actor_id IS '행동한 사람(회원 또는 시스템)';

-- 계좌별 알림 설정
CREATE TABLE notification_preferences (
  user_id             VARCHAR(40)  NOT NULL,
  account_id          VARCHAR(40)  NOT NULL,
  enabled             BOOLEAN      NOT NULL DEFAULT TRUE,
  deposit_enabled     BOOLEAN      NOT NULL DEFAULT TRUE,
  withdrawal_enabled  BOOLEAN      NOT NULL DEFAULT TRUE,
  minimum_amount      BIGINT       NOT NULL DEFAULT 0,
  channel             VARCHAR(20)  NOT NULL DEFAULT 'PUSH',
  PRIMARY KEY (user_id, account_id),
  CONSTRAINT fk_notification_preferences_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_notification_preferences_account FOREIGN KEY (account_id) REFERENCES accounts (id)
);
CREATE INDEX idx_notification_preferences_account ON notification_preferences (account_id);
COMMENT ON TABLE notification_preferences IS '알림 설정';

-- 장기 미사용 (계좌 1 : 0..1)
CREATE TABLE account_inactivity (
  account_id        VARCHAR(40)   NOT NULL,
  last_activity_at  TIMESTAMP(0)  NOT NULL,
  inactivity_flag   BOOLEAN       NOT NULL DEFAULT FALSE,
  flagged_at        TIMESTAMP(0)  NULL,
  PRIMARY KEY (account_id),
  CONSTRAINT fk_account_inactivity_account FOREIGN KEY (account_id) REFERENCES accounts (id)
);
COMMENT ON TABLE account_inactivity IS '장기 미사용';

-- 증명서 발급 기록
CREATE TABLE document_issuance_logs (
  id             VARCHAR(40)   NOT NULL,
  account_id     VARCHAR(40)   NOT NULL,
  document_type  VARCHAR(50)   NOT NULL,
  requested_by   VARCHAR(40)   NOT NULL,
  issued_at      TIMESTAMP(0)  NULL,
  status         VARCHAR(20)   NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_document_issuance_logs_account FOREIGN KEY (account_id) REFERENCES accounts (id)
);
CREATE INDEX idx_document_issuance_logs_account ON document_issuance_logs (account_id);
COMMENT ON TABLE document_issuance_logs IS '증명서 발급';
