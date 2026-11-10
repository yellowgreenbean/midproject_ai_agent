SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 7. 알림 (계좌 파트 2장 그림 — 계좌 알림과 카드 알림 공통)
-- ---------------------------------------------------------------------

CREATE TABLE notifications (
  id            VARCHAR(40)   NOT NULL,
  user_id       VARCHAR(40)   NOT NULL,
  account_id    VARCHAR(40)   NULL,
  user_card_id  VARCHAR(40)   NULL,
  event_id      VARCHAR(64)   NULL,
  type          VARCHAR(30)   NOT NULL,
  title         VARCHAR(100)  NOT NULL,
  body          VARCHAR(500)  NOT NULL,
  status        VARCHAR(20)   NOT NULL DEFAULT 'SENT',
  read_at       TIMESTAMP(0)  NULL,
  created_at    TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_notifications_event UNIQUE (event_id, user_id, type),
  CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_notifications_account FOREIGN KEY (account_id) REFERENCES accounts (id),
  CONSTRAINT fk_notifications_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT ck_notifications_type CHECK (type IN ('TRANSACTION', 'PAYMENT_DUE', 'LOW_BALANCE', 'OVERDUE',
    'PERFORMANCE', 'POINT_EXPIRING', 'ANNUAL_FEE', 'UNUSED_CARD', 'APPLICATION', 'CARD_STATUS',
    'INACTIVE_ACCOUNT', 'MATURITY', 'SECURITY'))
);
COMMENT ON CONSTRAINT uk_notifications_event ON notifications IS '같은 이벤트로 중복 알림 금지';
CREATE INDEX idx_notifications_user_created ON notifications (user_id, created_at);
CREATE INDEX idx_notifications_account ON notifications (account_id);
CREATE INDEX idx_notifications_card ON notifications (user_card_id);
COMMENT ON TABLE notifications IS '알림';
COMMENT ON COLUMN notifications.account_id IS '계좌 알림이면, 카드 알림이면 NULL';
COMMENT ON COLUMN notifications.user_card_id IS '카드 알림이면';
COMMENT ON COLUMN notifications.event_id IS '원인 이벤트 (예: 거래 확정)';
COMMENT ON COLUMN notifications.type IS '알림 종류 12개 (기획서 Part 6 C-5)';
COMMENT ON COLUMN notifications.read_at IS 'NULL = 안 읽음';
