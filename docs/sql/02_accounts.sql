-- ---------------------------------------------------------------------
-- 2. 계좌 (회원·계좌 기획서 8장)
--    notifications 는 user_cards 를 참조하므로 맨 뒤(7장)에 만듦
--    account_balance_view 는 3장의 account_balances 위에 만듦
-- ---------------------------------------------------------------------

-- 계좌 (잔액은 account_balances 에 있음)
CREATE TABLE accounts (
  id                   VARCHAR(40)   NOT NULL,
  user_id              VARCHAR(40)   NOT NULL,
  resAccount           VARCHAR(20)   NOT NULL COMMENT '계좌번호(숫자만)',
  resAccountDisplay    VARCHAR(30)   NOT NULL COMMENT '예: 110-00-000001',
  resAccountName       VARCHAR(100)  NOT NULL COMMENT '상품명',
  account_type         ENUM('CHECKING','SAVINGS') NOT NULL,
  lifecycle_status     ENUM('ACTIVE','SUSPENDED','CLOSED') NOT NULL DEFAULT 'ACTIVE',
  resAccountNickName   VARCHAR(50)   NULL,
  is_favorite          BOOLEAN       NOT NULL DEFAULT FALSE,
  resAccountStartDate  CHAR(8)       NOT NULL COMMENT 'YYYYMMDD',
  closed_at            CHAR(8)       NULL     COMMENT 'YYYYMMDD, 해지 전 NULL',
  version              INT           NOT NULL DEFAULT 0 COMMENT '낙관적 잠금',
  PRIMARY KEY (id),
  UNIQUE KEY uk_accounts_res_account (resAccount),
  KEY idx_accounts_user (user_id),
  CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='계좌';

-- 계좌 관리 기록
CREATE TABLE account_activity_logs (
  id           VARCHAR(40)  NOT NULL,
  account_id   VARCHAR(40)  NOT NULL,
  actor_id     VARCHAR(40)  NOT NULL COMMENT '행동한 사람(회원 또는 시스템)',
  action       VARCHAR(50)  NOT NULL,
  occurred_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata     JSON         NULL,
  PRIMARY KEY (id),
  KEY idx_account_activity_logs_account (account_id, occurred_at),
  CONSTRAINT fk_account_activity_logs_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) COMMENT='계좌 관리 기록';

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
  KEY idx_notification_preferences_account (account_id),
  CONSTRAINT fk_notification_preferences_user    FOREIGN KEY (user_id)    REFERENCES users (id),
  CONSTRAINT fk_notification_preferences_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) COMMENT='알림 설정';

-- 장기 미사용 (계좌 1 : 0..1)
CREATE TABLE account_inactivity (
  account_id        VARCHAR(40)  NOT NULL,
  last_activity_at  DATETIME     NOT NULL,
  inactivity_flag   BOOLEAN      NOT NULL DEFAULT FALSE,
  flagged_at        DATETIME     NULL,
  PRIMARY KEY (account_id),
  CONSTRAINT fk_account_inactivity_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) COMMENT='장기 미사용';

-- 증명서 발급 기록
CREATE TABLE document_issuance_logs (
  id             VARCHAR(40)  NOT NULL,
  account_id     VARCHAR(40)  NOT NULL,
  document_type  VARCHAR(50)  NOT NULL,
  requested_by   VARCHAR(40)  NOT NULL,
  issued_at      DATETIME     NULL,
  status         VARCHAR(20)  NOT NULL,
  PRIMARY KEY (id),
  KEY idx_document_issuance_logs_account (account_id),
  CONSTRAINT fk_document_issuance_logs_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) COMMENT='증명서 발급';