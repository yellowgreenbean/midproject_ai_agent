-- ---------------------------------------------------------------------
-- 1. 회원·인증 (회원·계좌 기획서 6장)
--    terms, user_consents 는 card_products 를 참조하므로 5장 뒤에 만듦
-- ---------------------------------------------------------------------

-- 회원
CREATE TABLE users (
  id                 VARCHAR(40)   NOT NULL COMMENT '예: user_001',
  username           VARCHAR(50)   NOT NULL COMMENT '로그인 아이디',
  name               VARCHAR(50)   NOT NULL,
  email              VARCHAR(100)  NULL,
  email_verified_at  DATETIME      NULL     COMMENT 'NULL = 미인증',
  birth_date         DATE          NOT NULL COMMENT 'YYYY-MM-DD',
  gender             ENUM('M','F') NOT NULL,
  payday             TINYINT       NULL     COMMENT '월급일 1~31, 빈 값 가능',
  status             ENUM('ACTIVE','PENDING_VERIFICATION','RESTRICTED','WITHDRAWN')
                                   NOT NULL DEFAULT 'PENDING_VERIFICATION',
  created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  withdrawn_at       DATETIME      NULL     COMMENT 'NULL = 미탈퇴',
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username),
  CONSTRAINT ck_users_payday CHECK (payday IS NULL OR payday BETWEEN 1 AND 31)
) COMMENT='회원';

-- 로그인 수단 (LOCAL / GOOGLE)
CREATE TABLE auth_identities (
  id                VARCHAR(40)   NOT NULL,
  user_id           VARCHAR(40)   NOT NULL,
  provider          ENUM('LOCAL','GOOGLE') NOT NULL,
  provider_subject  VARCHAR(255)  NOT NULL COMMENT '공급자 쪽 사용자 식별값',
  linked_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_auth_identities_provider (provider, provider_subject),
  KEY idx_auth_identities_user (user_id),
  CONSTRAINT fk_auth_identities_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='로그인 수단';

-- 비밀번호 (회원 1 : 0..1)
CREATE TABLE local_credentials (
  user_id              VARCHAR(40)   NOT NULL,
  password_hash        VARCHAR(255)  NOT NULL,
  password_updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  failed_attempts      INT           NOT NULL DEFAULT 0 COMMENT '로그인·본인 확인 실패 횟수',
  locked_until         DATETIME      NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_local_credentials_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='비밀번호';

-- 이메일 인증 (가입 전이라 회원과 연결 없음)
CREATE TABLE email_verifications (
  id                VARCHAR(40)   NOT NULL,
  email             VARCHAR(100)  NOT NULL,
  purpose           VARCHAR(30)   NOT NULL,
  challenge_digest  VARCHAR(255)  NOT NULL,
  expires_at        DATETIME      NOT NULL,
  attempt_count     INT           NOT NULL DEFAULT 0,
  used_at           DATETIME      NULL,
  PRIMARY KEY (id),
  KEY idx_email_verifications_email (email, purpose)
) COMMENT='이메일 인증';

-- 비밀번호 재설정 토큰
CREATE TABLE password_reset_tokens (
  id            VARCHAR(40)   NOT NULL,
  user_id       VARCHAR(40)   NOT NULL,
  token_digest  VARCHAR(255)  NOT NULL,
  expires_at    DATETIME      NOT NULL,
  used_at       DATETIME      NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_password_reset_tokens_digest (token_digest),
  KEY idx_password_reset_tokens_user (user_id),
  CONSTRAINT fk_password_reset_tokens_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='비밀번호 재설정';

-- 로그인 세션
CREATE TABLE sessions (
  id            VARCHAR(40)  NOT NULL,
  user_id       VARCHAR(40)  NOT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at    DATETIME     NOT NULL,
  revoked_at    DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_sessions_user (user_id),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='세션';

-- PIN (회원 1 : 0..1)
CREATE TABLE pin_credentials (
  user_id          VARCHAR(40)   NOT NULL,
  pin_hash         VARCHAR(255)  NOT NULL,
  enabled_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  changed_at       DATETIME      NULL,
  failed_attempts  INT           NOT NULL DEFAULT 0,
  locked_until     DATETIME      NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_pin_credentials_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='PIN';

-- 인증 감사 기록
CREATE TABLE auth_audit_logs (
  id           VARCHAR(40)  NOT NULL,
  user_id      VARCHAR(40)  NOT NULL,
  event_type   VARCHAR(50)  NOT NULL,
  occurred_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  outcome      VARCHAR(30)  NOT NULL,
  request_id   VARCHAR(64)  NULL,
  PRIMARY KEY (id),
  KEY idx_auth_audit_logs_user (user_id, occurred_at),
  CONSTRAINT fk_auth_audit_logs_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='인증 기록';

-- 본인 확인 (이체·예약 이체·카드 신청/해지/관리·가입·계좌 상태 변경·탈퇴·정보 변경)
CREATE TABLE step_up_challenges (
  id           VARCHAR(40)  NOT NULL,
  user_id      VARCHAR(40)  NOT NULL,
  action       ENUM('TRANSFER','SCHEDULED_TRANSFER','CARD_APPLICATION','CARD_TERMINATION',
                    'CARD_MANAGEMENT','SUBSCRIPTION','ACCOUNT_STATUS_CHANGE','WITHDRAWAL',
                    'PROFILE_CHANGE') NOT NULL,
  session_id   VARCHAR(40)  NOT NULL COMMENT '그 세션에서 받은 확인',
  expires_at   DATETIME     NOT NULL,
  consumed_at  DATETIME     NULL     COMMENT 'NULL = 아직 사용 안 함',
  PRIMARY KEY (id),
  KEY idx_step_up_user (user_id),
  KEY idx_step_up_session (session_id),
  CONSTRAINT fk_step_up_user    FOREIGN KEY (user_id)    REFERENCES users (id),
  CONSTRAINT fk_step_up_session FOREIGN KEY (session_id) REFERENCES sessions (id)
) COMMENT='본인 확인';

-- 탈퇴 점검
CREATE TABLE withdrawal_checks (
  id                            VARCHAR(40)  NOT NULL,
  user_id                       VARCHAR(40)  NOT NULL,
  status                        ENUM('IN_PROGRESS','COMPLETED','CANCELED') NOT NULL DEFAULT 'IN_PROGRESS',
  started_at                    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  balance_verified_at           DATETIME     NULL,
  data_review_confirmed_at      DATETIME     NULL,
  data_review_version           VARCHAR(20)  NULL,
  linked_services_confirmed_at  DATETIME     NULL,
  completed_at                  DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_withdrawal_checks_user (user_id),
  CONSTRAINT fk_withdrawal_checks_user FOREIGN KEY (user_id) REFERENCES users (id)
) COMMENT='탈퇴 점검';