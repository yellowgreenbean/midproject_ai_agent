SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 1. 회원·인증 (회원·계좌 기획서 6장)
--    terms, user_consents 는 card_products 를 참조하므로 5장 뒤에 만듦
-- ---------------------------------------------------------------------

-- 회원
CREATE TABLE users (
  id                 VARCHAR(40)   NOT NULL,
  username           VARCHAR(50)   NOT NULL,
  name               VARCHAR(50)   NOT NULL,
  email              VARCHAR(100)  NULL,
  email_verified_at  TIMESTAMP(0)  NULL,
  birth_date         DATE          NOT NULL,
  gender             VARCHAR(30)   NOT NULL,
  payday             SMALLINT      NULL,
  status             VARCHAR(30)   NOT NULL DEFAULT 'PENDING_VERIFICATION',
  created_at         TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  withdrawn_at       TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_users_username UNIQUE (username),
  CONSTRAINT ck_users_payday CHECK (payday IS NULL OR payday BETWEEN 1 AND 31),
  CONSTRAINT ck_users_gender CHECK (gender IN ('M', 'F')),
  CONSTRAINT ck_users_status CHECK (status IN ('ACTIVE', 'PENDING_VERIFICATION', 'RESTRICTED', 'WITHDRAWN'))
);
COMMENT ON TABLE users IS '회원';
COMMENT ON COLUMN users.id IS '예: user_001';
COMMENT ON COLUMN users.username IS '로그인 아이디';
COMMENT ON COLUMN users.email_verified_at IS 'NULL = 미인증';
COMMENT ON COLUMN users.birth_date IS 'YYYY-MM-DD';
COMMENT ON COLUMN users.payday IS '월급일 1~31, 빈 값 가능';
COMMENT ON COLUMN users.withdrawn_at IS 'NULL = 미탈퇴';

-- 로그인 수단 (LOCAL / GOOGLE)
CREATE TABLE auth_identities (
  id                VARCHAR(40)   NOT NULL,
  user_id           VARCHAR(40)   NOT NULL,
  provider          VARCHAR(30)   NOT NULL,
  provider_subject  VARCHAR(255)  NOT NULL,
  linked_at         TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_auth_identities_provider UNIQUE (provider, provider_subject),
  CONSTRAINT fk_auth_identities_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT ck_auth_identities_provider CHECK (provider IN ('LOCAL', 'GOOGLE'))
);
CREATE INDEX idx_auth_identities_user ON auth_identities (user_id);
COMMENT ON TABLE auth_identities IS '로그인 수단';
COMMENT ON COLUMN auth_identities.provider_subject IS '공급자 쪽 사용자 식별값';

-- 비밀번호 (회원 1 : 0..1)
CREATE TABLE local_credentials (
  user_id              VARCHAR(40)   NOT NULL,
  password_hash        VARCHAR(255)  NOT NULL,
  password_updated_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  failed_attempts      INT           NOT NULL DEFAULT 0,
  locked_until         TIMESTAMP(0)  NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_local_credentials_user FOREIGN KEY (user_id) REFERENCES users (id)
);
COMMENT ON TABLE local_credentials IS '비밀번호';
COMMENT ON COLUMN local_credentials.failed_attempts IS '로그인·본인 확인 실패 횟수';

-- 이메일 인증 (가입 전이라 회원과 연결 없음)
CREATE TABLE email_verifications (
  id                VARCHAR(40)   NOT NULL,
  email             VARCHAR(100)  NOT NULL,
  purpose           VARCHAR(30)   NOT NULL,
  challenge_digest  VARCHAR(255)  NOT NULL,
  expires_at        TIMESTAMP(0)  NOT NULL,
  attempt_count     INT           NOT NULL DEFAULT 0,
  used_at           TIMESTAMP(0)  NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_email_verifications_email ON email_verifications (email, purpose);
COMMENT ON TABLE email_verifications IS '이메일 인증';

-- 비밀번호 재설정 토큰
CREATE TABLE password_reset_tokens (
  id            VARCHAR(40)   NOT NULL,
  user_id       VARCHAR(40)   NOT NULL,
  token_digest  VARCHAR(255)  NOT NULL,
  expires_at    TIMESTAMP(0)  NOT NULL,
  used_at       TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_password_reset_tokens_digest UNIQUE (token_digest),
  CONSTRAINT fk_password_reset_tokens_user FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE INDEX idx_password_reset_tokens_user ON password_reset_tokens (user_id);
COMMENT ON TABLE password_reset_tokens IS '비밀번호 재설정';

-- 로그인 세션
CREATE TABLE sessions (
  id            VARCHAR(40)   NOT NULL,
  user_id       VARCHAR(40)   NOT NULL,
  created_at    TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at    TIMESTAMP(0)  NOT NULL,
  revoked_at    TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
COMMENT ON TABLE sessions IS '세션';

-- PIN (회원 1 : 0..1)
CREATE TABLE pin_credentials (
  user_id          VARCHAR(40)   NOT NULL,
  pin_hash         VARCHAR(255)  NOT NULL,
  enabled_at       TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  changed_at       TIMESTAMP(0)  NULL,
  failed_attempts  INT           NOT NULL DEFAULT 0,
  locked_until     TIMESTAMP(0)  NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_pin_credentials_user FOREIGN KEY (user_id) REFERENCES users (id)
);
COMMENT ON TABLE pin_credentials IS 'PIN';

-- 인증 감사 기록
CREATE TABLE auth_audit_logs (
  id           VARCHAR(40)   NOT NULL,
  user_id      VARCHAR(40)   NOT NULL,
  event_type   VARCHAR(50)   NOT NULL,
  occurred_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  outcome      VARCHAR(30)   NOT NULL,
  request_id   VARCHAR(64)   NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_auth_audit_logs_user FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE INDEX idx_auth_audit_logs_user ON auth_audit_logs (user_id, occurred_at);
COMMENT ON TABLE auth_audit_logs IS '인증 기록';

-- 본인 확인 (이체·예약 이체·카드 신청/해지/관리·가입·계좌 상태 변경·탈퇴·정보 변경·PIN 등록/변경/재설정)
CREATE TABLE step_up_challenges (
  id           VARCHAR(40)   NOT NULL,
  user_id      VARCHAR(40)   NOT NULL,
  action       VARCHAR(30)   NOT NULL,
  session_id   VARCHAR(40)   NOT NULL,
  expires_at   TIMESTAMP(0)  NOT NULL,
  consumed_at  TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_step_up_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_step_up_session FOREIGN KEY (session_id) REFERENCES sessions (id),
  CONSTRAINT ck_step_up_challenges_action CHECK (action IN ('TRANSFER', 'SCHEDULED_TRANSFER', 'CARD_APPLICATION', 'CARD_TERMINATION', 'CARD_MANAGEMENT', 'SUBSCRIPTION', 'ACCOUNT_STATUS_CHANGE', 'WITHDRAWAL', 'PROFILE_CHANGE', 'PIN_ENROLL', 'PIN_CHANGE', 'PIN_RESET'))
);
CREATE INDEX idx_step_up_user ON step_up_challenges (user_id);
CREATE INDEX idx_step_up_session ON step_up_challenges (session_id);
COMMENT ON TABLE step_up_challenges IS '본인 확인';
COMMENT ON COLUMN step_up_challenges.session_id IS '그 세션에서 받은 확인';
COMMENT ON COLUMN step_up_challenges.consumed_at IS 'NULL = 아직 사용 안 함';

-- 탈퇴 점검
CREATE TABLE withdrawal_checks (
  id                            VARCHAR(40)   NOT NULL,
  user_id                       VARCHAR(40)   NOT NULL,
  status                        VARCHAR(30)   NOT NULL DEFAULT 'IN_PROGRESS',
  started_at                    TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  balance_verified_at           TIMESTAMP(0)  NULL,
  data_review_confirmed_at      TIMESTAMP(0)  NULL,
  data_review_version           VARCHAR(20)   NULL,
  linked_services_confirmed_at  TIMESTAMP(0)  NULL,
  completed_at                  TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_withdrawal_checks_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT ck_withdrawal_checks_status CHECK (status IN ('IN_PROGRESS', 'COMPLETED', 'CANCELED'))
);
CREATE INDEX idx_withdrawal_checks_user ON withdrawal_checks (user_id);
COMMENT ON TABLE withdrawal_checks IS '탈퇴 점검';
