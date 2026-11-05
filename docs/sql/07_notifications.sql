-- ---------------------------------------------------------------------
-- 7. 알림 (계좌 파트 2장 그림 — 계좌 알림과 카드 알림 공통)
-- ---------------------------------------------------------------------

CREATE TABLE notifications (
  id            VARCHAR(40)   NOT NULL,
  user_id       VARCHAR(40)   NOT NULL,
  account_id    VARCHAR(40)   NULL     COMMENT '계좌 알림이면, 카드 알림이면 NULL',
  user_card_id  VARCHAR(40)   NULL     COMMENT '카드 알림이면',
  event_id      VARCHAR(64)   NULL     COMMENT '원인 이벤트 (예: 거래 확정)',
  type          VARCHAR(30)   NOT NULL COMMENT 'TRANSACTION / PAYMENT_DUE / MATURITY ...',
  title         VARCHAR(100)  NOT NULL,
  body          VARCHAR(500)  NOT NULL,
  status        VARCHAR(20)   NOT NULL DEFAULT 'SENT',
  read_at       DATETIME      NULL     COMMENT 'NULL = 안 읽음',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_notifications_event (event_id, user_id, type) COMMENT '같은 이벤트로 중복 알림 금지',
  KEY idx_notifications_user_created (user_id, created_at),
  KEY idx_notifications_account (account_id),
  KEY idx_notifications_card (user_card_id),
  CONSTRAINT fk_notifications_user    FOREIGN KEY (user_id)      REFERENCES users (id),
  CONSTRAINT fk_notifications_account FOREIGN KEY (account_id)   REFERENCES accounts (id),
  CONSTRAINT fk_notifications_card    FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='알림';
-- 00_common.sql 에서 끈 FK 검사를 다시 켬 (마지막 파일)
SET FOREIGN_KEY_CHECKS = 1;
