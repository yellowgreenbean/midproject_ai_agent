-- ---------------------------------------------------------------------
-- 3. 거래 (거래·카드 기획서 파트 B 15장)
-- ---------------------------------------------------------------------

-- 잔액 (계좌 1 : 1, 잔액의 원본)
CREATE TABLE account_balances (
  account_id  VARCHAR(40)  NOT NULL,
  currency    CHAR(3)      NOT NULL DEFAULT 'KRW',
  balance     BIGINT       NOT NULL DEFAULT 0,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (account_id),
  CONSTRAINT fk_account_balances_account FOREIGN KEY (account_id) REFERENCES accounts (id),
  CONSTRAINT ck_account_balances_balance CHECK (balance >= 0)
) COMMENT='잔액';

-- 잔액 읽기용 보기 (계좌 파트, CODEF 이름으로 노출)
CREATE OR REPLACE VIEW account_balance_view AS
SELECT
  account_id,
  currency                                   AS resAccountCurrency,
  balance                                    AS resAccountBalance,
  DATE_FORMAT(updated_at, '%Y%m%d%H%i%s')    AS balance_as_of
FROM account_balances;

-- 예약 송금·자동이체 (ERD 주요 칸 + 거래 기획서 15장의 표시 이름·updated_at)
CREATE TABLE scheduled_transfers (
  id                    VARCHAR(40)   NOT NULL,
  user_id               VARCHAR(40)   NOT NULL,
  from_account_id       VARCHAR(40)   NOT NULL,
  to_bank               VARCHAR(30)   NOT NULL,
  to_account_no         VARCHAR(20)   NOT NULL,
  to_holder_name        VARCHAR(50)   NOT NULL,
  amount                BIGINT        NOT NULL,
  my_display_name       VARCHAR(50)   NULL,
  their_display_name    VARCHAR(50)   NULL,
  type                  ENUM('ONCE','MONTHLY') NOT NULL COMMENT 'ONCE = 예약 송금, MONTHLY = 자동이체',
  execute_at            DATETIME      NULL     COMMENT 'ONCE 실행 일시',
  day_of_month          TINYINT       NULL     COMMENT 'MONTHLY 지정일 1~28, 99 = 말일',
  start_ym              CHAR(6)       NULL     COMMENT 'MONTHLY 시작 연월 YYYYMM',
  end_ym                CHAR(6)       NULL     COMMENT 'MONTHLY 종료 연월, NULL = 해지할 때까지',
  next_run_at           DATETIME      NULL     COMMENT '배치 조회 기준',
  status                ENUM('SCHEDULED','PROCESSING','SUCCESS','FAILED','CANCELED','ACTIVE','PAUSED')
                                      NOT NULL DEFAULT 'SCHEDULED'
                                      COMMENT 'ONCE: SCHEDULED/PROCESSING/SUCCESS/FAILED/CANCELED, MONTHLY: ACTIVE/PAUSED/CANCELED',
  step_up_challenge_id  VARCHAR(40)   NULL     COMMENT '등록 때 본인 확인',
  created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_scheduled_transfers_user (user_id),
  KEY idx_scheduled_transfers_from_account (from_account_id),
  KEY idx_scheduled_transfers_next_run (status, next_run_at),
  CONSTRAINT fk_scheduled_transfers_user     FOREIGN KEY (user_id)              REFERENCES users (id),
  CONSTRAINT fk_scheduled_transfers_account  FOREIGN KEY (from_account_id)      REFERENCES accounts (id),
  CONSTRAINT fk_scheduled_transfers_step_up  FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id),
  CONSTRAINT ck_scheduled_transfers_day CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28 OR day_of_month = 99)
) COMMENT='예약 송금·자동이체';

-- 이체 요청과 결과
CREATE TABLE transfers (
  id                     VARCHAR(40)   NOT NULL COMMENT '예: trf_0001',
  user_id                VARCHAR(40)   NOT NULL,
  from_account_id        VARCHAR(40)   NOT NULL,
  to_bank                VARCHAR(30)   NOT NULL,
  to_account_no          VARCHAR(20)   NOT NULL,
  to_holder_name         VARCHAR(50)   NOT NULL,
  amount                 BIGINT        NOT NULL,
  fee                    BIGINT        NOT NULL DEFAULT 0,
  my_display_name        VARCHAR(50)   NULL,
  their_display_name     VARCHAR(50)   NULL,
  status                 ENUM('PENDING','SUCCESS','FAILED') NOT NULL DEFAULT 'PENDING',
  failure_reason         VARCHAR(50)   NULL     COMMENT '실패 사유 코드',
  channel                ENUM('APP','SCHEDULED','AUTO') NOT NULL DEFAULT 'APP',
  scheduled_transfer_id  VARCHAR(40)   NULL     COMMENT '예약·자동이체로 실행된 경우',
  step_up_challenge_id   VARCHAR(40)   NULL     COMMENT '본인 확인',
  idempotency_key        VARCHAR(100)  NOT NULL COMMENT '중복 요청 방지',
  requested_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at           DATETIME      NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_transfers_idempotency_key (idempotency_key),
  KEY idx_transfers_user (user_id, requested_at),
  KEY idx_transfers_from_account (from_account_id, requested_at),
  KEY idx_transfers_scheduled (scheduled_transfer_id),
  CONSTRAINT fk_transfers_user       FOREIGN KEY (user_id)               REFERENCES users (id),
  CONSTRAINT fk_transfers_account    FOREIGN KEY (from_account_id)       REFERENCES accounts (id),
  CONSTRAINT fk_transfers_scheduled  FOREIGN KEY (scheduled_transfer_id) REFERENCES scheduled_transfers (id),
  CONSTRAINT fk_transfers_step_up    FOREIGN KEY (step_up_challenge_id)  REFERENCES step_up_challenges (id),
  CONSTRAINT ck_transfers_amount CHECK (amount > 0)
) COMMENT='이체';

-- 거래 원장 (성공한 건만, 이체면 출금·입금 2건)
CREATE TABLE transactions (
  id                      VARCHAR(40)   NOT NULL COMMENT '예: tx_0001',
  account_id              VARCHAR(40)   NOT NULL,
  type                    ENUM('TRANSFER_OUT','TRANSFER_IN','CARD_PAYMENT','POINT_CASHOUT',
                               'SUBSCRIPTION_PAYMENT','SUBSCRIPTION_PAYOUT') NOT NULL,
  amount                  BIGINT        NOT NULL COMMENT '항상 양수, +/-는 type으로 결정',
  fee                     BIGINT        NOT NULL DEFAULT 0,
  balance_after           BIGINT        NOT NULL,
  transfer_id             VARCHAR(40)   NULL     COMMENT '이체가 아니면 NULL',
  counterpart_bank        VARCHAR(30)   NULL,
  counterpart_account_no  VARCHAR(20)   NULL,
  display_name            VARCHAR(50)   NULL     COMMENT '이 통장에 표시되는 이름',
  created_at              DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_transactions_account_time (account_id, created_at),
  KEY idx_transactions_transfer (transfer_id),
  CONSTRAINT fk_transactions_account  FOREIGN KEY (account_id)  REFERENCES accounts (id),
  CONSTRAINT fk_transactions_transfer FOREIGN KEY (transfer_id) REFERENCES transfers (id),
  CONSTRAINT ck_transactions_amount CHECK (amount > 0)
) COMMENT='거래 원장';

-- 자주 쓰는 계좌
CREATE TABLE favorite_accounts (
  id           VARCHAR(40)  NOT NULL,
  user_id      VARCHAR(40)  NOT NULL,
  bank         VARCHAR(30)  NOT NULL,
  account_no   VARCHAR(20)  NOT NULL,
  holder_name  VARCHAR(50)  NOT NULL,
  nickname     VARCHAR(50)  NULL,
  sort_order   INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_favorite_accounts (user_id, bank, account_no),
  CONSTRAINT fk_favorite_accounts_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='자주 쓰는 계좌';

-- 이체 한도 (계좌 1 : 0..1)
CREATE TABLE transfer_limits (
  account_id          VARCHAR(40)  NOT NULL,
  per_transfer_limit  BIGINT       NOT NULL,
  daily_limit         BIGINT       NOT NULL,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (account_id),
  CONSTRAINT fk_transfer_limits_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) COMMENT='이체 한도';

-- 가상 타행 예금주 조회용 시드 (다른 테이블과 연결 없음, 계좌번호로 찾음)
CREATE TABLE external_accounts (
  id           VARCHAR(40)  NOT NULL,
  bank         VARCHAR(30)  NOT NULL,
  account_no   VARCHAR(20)  NOT NULL,
  holder_name  VARCHAR(50)  NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_external_accounts (bank, account_no)
) COMMENT='타행 계좌(시드)';