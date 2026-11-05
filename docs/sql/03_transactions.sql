SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 3. 거래 (거래·카드 기획서 파트 B 15장)
-- ---------------------------------------------------------------------

-- 잔액 (계좌 1 : 1, 잔액의 원본)
CREATE TABLE account_balances (
  account_id  VARCHAR(40)   NOT NULL,
  currency    CHAR(3)       NOT NULL DEFAULT 'KRW',
  balance     BIGINT        NOT NULL DEFAULT 0,
  updated_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (account_id),
  CONSTRAINT fk_account_balances_account FOREIGN KEY (account_id) REFERENCES accounts (id),
  CONSTRAINT ck_account_balances_balance CHECK (balance >= 0)
);
CREATE TRIGGER trg_account_balances_updated_at BEFORE UPDATE ON account_balances
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
COMMENT ON TABLE account_balances IS '잔액';

-- 잔액 읽기용 보기 (계좌 파트, CODEF 이름으로 노출)
CREATE OR REPLACE VIEW account_balance_view AS
SELECT
  account_id,
  currency                                   AS resAccountCurrency,
  balance                                    AS resAccountBalance,
  to_char(updated_at, 'YYYYMMDDHH24MISS')    AS balance_as_of
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
  type                  VARCHAR(30)   NOT NULL,
  execute_at            TIMESTAMP(0)  NULL,
  day_of_month          SMALLINT      NULL,
  start_ym              CHAR(6)       NULL,
  end_ym                CHAR(6)       NULL,
  next_run_at           TIMESTAMP(0)  NULL,
  status                VARCHAR(30)   NOT NULL DEFAULT 'SCHEDULED',
  step_up_challenge_id  VARCHAR(40)   NULL,
  created_at            TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_scheduled_transfers_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_scheduled_transfers_account FOREIGN KEY (from_account_id) REFERENCES accounts (id),
  CONSTRAINT fk_scheduled_transfers_step_up FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id),
  CONSTRAINT ck_scheduled_transfers_day CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28 OR day_of_month = 99),
  CONSTRAINT ck_scheduled_transfers_type CHECK (type IN ('ONCE', 'MONTHLY')),
  CONSTRAINT ck_scheduled_transfers_status CHECK (status IN ('SCHEDULED', 'PROCESSING', 'SUCCESS', 'FAILED', 'CANCELED', 'ACTIVE', 'PAUSED'))
);
CREATE INDEX idx_scheduled_transfers_user ON scheduled_transfers (user_id);
CREATE INDEX idx_scheduled_transfers_from_account ON scheduled_transfers (from_account_id);
CREATE INDEX idx_scheduled_transfers_next_run ON scheduled_transfers (status, next_run_at);
CREATE TRIGGER trg_scheduled_transfers_updated_at BEFORE UPDATE ON scheduled_transfers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
COMMENT ON TABLE scheduled_transfers IS '예약 송금·자동이체';
COMMENT ON COLUMN scheduled_transfers.type IS 'ONCE = 예약 송금, MONTHLY = 자동이체';
COMMENT ON COLUMN scheduled_transfers.execute_at IS 'ONCE 실행 일시';
COMMENT ON COLUMN scheduled_transfers.day_of_month IS 'MONTHLY 지정일 1~28, 99 = 말일';
COMMENT ON COLUMN scheduled_transfers.start_ym IS 'MONTHLY 시작 연월 YYYYMM';
COMMENT ON COLUMN scheduled_transfers.end_ym IS 'MONTHLY 종료 연월, NULL = 해지할 때까지';
COMMENT ON COLUMN scheduled_transfers.next_run_at IS '배치 조회 기준';
COMMENT ON COLUMN scheduled_transfers.status IS 'ONCE: SCHEDULED/PROCESSING/SUCCESS/FAILED/CANCELED, MONTHLY: ACTIVE/PAUSED/CANCELED';
COMMENT ON COLUMN scheduled_transfers.step_up_challenge_id IS '등록 때 본인 확인';

-- 이체 요청과 결과
CREATE TABLE transfers (
  id                     VARCHAR(40)   NOT NULL,
  user_id                VARCHAR(40)   NOT NULL,
  from_account_id        VARCHAR(40)   NOT NULL,
  to_bank                VARCHAR(30)   NOT NULL,
  to_account_no          VARCHAR(20)   NOT NULL,
  to_holder_name         VARCHAR(50)   NOT NULL,
  amount                 BIGINT        NOT NULL,
  fee                    BIGINT        NOT NULL DEFAULT 0,
  my_display_name        VARCHAR(50)   NULL,
  their_display_name     VARCHAR(50)   NULL,
  status                 VARCHAR(30)   NOT NULL DEFAULT 'PENDING',
  failure_reason         VARCHAR(50)   NULL,
  channel                VARCHAR(30)   NOT NULL DEFAULT 'APP',
  scheduled_transfer_id  VARCHAR(40)   NULL,
  step_up_challenge_id   VARCHAR(40)   NULL,
  idempotency_key        VARCHAR(100)  NOT NULL,
  requested_at           TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at           TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_transfers_idempotency_key UNIQUE (idempotency_key),
  CONSTRAINT fk_transfers_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_transfers_account FOREIGN KEY (from_account_id) REFERENCES accounts (id),
  CONSTRAINT fk_transfers_scheduled FOREIGN KEY (scheduled_transfer_id) REFERENCES scheduled_transfers (id),
  CONSTRAINT fk_transfers_step_up FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id),
  CONSTRAINT ck_transfers_amount CHECK (amount > 0),
  CONSTRAINT ck_transfers_status CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
  CONSTRAINT ck_transfers_channel CHECK (channel IN ('APP', 'SCHEDULED', 'AUTO'))
);
CREATE INDEX idx_transfers_user ON transfers (user_id, requested_at);
CREATE INDEX idx_transfers_from_account ON transfers (from_account_id, requested_at);
CREATE INDEX idx_transfers_scheduled ON transfers (scheduled_transfer_id);
COMMENT ON TABLE transfers IS '이체';
COMMENT ON COLUMN transfers.id IS '예: trf_0001';
COMMENT ON COLUMN transfers.failure_reason IS '실패 사유 코드';
COMMENT ON COLUMN transfers.scheduled_transfer_id IS '예약·자동이체로 실행된 경우';
COMMENT ON COLUMN transfers.step_up_challenge_id IS '본인 확인';
COMMENT ON COLUMN transfers.idempotency_key IS '중복 요청 방지';

-- 거래 원장 (성공한 건만, 이체면 출금·입금 2건)
CREATE TABLE transactions (
  id                      VARCHAR(40)   NOT NULL,
  account_id              VARCHAR(40)   NOT NULL,
  type                    VARCHAR(30)   NOT NULL,
  amount                  BIGINT        NOT NULL,
  fee                     BIGINT        NOT NULL DEFAULT 0,
  balance_after           BIGINT        NOT NULL,
  transfer_id             VARCHAR(40)   NULL,
  counterpart_bank        VARCHAR(30)   NULL,
  counterpart_account_no  VARCHAR(20)   NULL,
  display_name            VARCHAR(50)   NULL,
  created_at              TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_transactions_account FOREIGN KEY (account_id) REFERENCES accounts (id),
  CONSTRAINT fk_transactions_transfer FOREIGN KEY (transfer_id) REFERENCES transfers (id),
  CONSTRAINT ck_transactions_amount CHECK (amount > 0),
  CONSTRAINT ck_transactions_type CHECK (type IN ('TRANSFER_OUT', 'TRANSFER_IN', 'CARD_PAYMENT', 'POINT_CASHOUT', 'SUBSCRIPTION_PAYMENT', 'SUBSCRIPTION_PAYOUT'))
);
CREATE INDEX idx_transactions_account_time ON transactions (account_id, created_at);
CREATE INDEX idx_transactions_transfer ON transactions (transfer_id);
COMMENT ON TABLE transactions IS '거래 원장';
COMMENT ON COLUMN transactions.id IS '예: tx_0001';
COMMENT ON COLUMN transactions.amount IS '항상 양수, +/-는 type으로 결정';
COMMENT ON COLUMN transactions.transfer_id IS '이체가 아니면 NULL';
COMMENT ON COLUMN transactions.display_name IS '이 통장에 표시되는 이름';

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
  CONSTRAINT uk_favorite_accounts UNIQUE (user_id, bank, account_no),
  CONSTRAINT fk_favorite_accounts_user FOREIGN KEY (user_id) REFERENCES users (id)
);
COMMENT ON TABLE favorite_accounts IS '자주 쓰는 계좌';

-- 이체 한도 (계좌 1 : 0..1)
CREATE TABLE transfer_limits (
  account_id          VARCHAR(40)   NOT NULL,
  per_transfer_limit  BIGINT        NOT NULL,
  daily_limit         BIGINT        NOT NULL,
  updated_at          TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (account_id),
  CONSTRAINT fk_transfer_limits_account FOREIGN KEY (account_id) REFERENCES accounts (id)
);
CREATE TRIGGER trg_transfer_limits_updated_at BEFORE UPDATE ON transfer_limits
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
COMMENT ON TABLE transfer_limits IS '이체 한도';

-- 가상 타행 예금주 조회용 시드 (다른 테이블과 연결 없음, 계좌번호로 찾음)
CREATE TABLE external_accounts (
  id           VARCHAR(40)  NOT NULL,
  bank         VARCHAR(30)  NOT NULL,
  account_no   VARCHAR(20)  NOT NULL,
  holder_name  VARCHAR(50)  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_external_accounts UNIQUE (bank, account_no)
);
COMMENT ON TABLE external_accounts IS '타행 계좌(시드)';
