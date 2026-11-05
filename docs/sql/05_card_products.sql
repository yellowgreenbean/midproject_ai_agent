-- ---------------------------------------------------------------------
-- 5. 카드 — 상품·발급·보유 (파트 A 1-2·1-3·1-7)
-- ---------------------------------------------------------------------

-- 카드사
CREATE TABLE card_companies (
  id               VARCHAR(40)   NOT NULL,
  code             VARCHAR(10)   NOT NULL COMMENT '예: SHINHAN, HYUNDAI, TOSSBANK',
  name             VARCHAR(30)   NOT NULL,
  logo_url         VARCHAR(255)  NULL,
  customer_center  VARCHAR(20)   NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_card_companies_code (code)
) COMMENT='카드사';

-- 업종/혜택 카테고리 (가맹점 분류와 혜택 대상 분류에 공통 사용)
CREATE TABLE categories (
  id         VARCHAR(40)  NOT NULL,
  parent_id  VARCHAR(40)  NULL     COMMENT '상위 분류 (예: 교통 > 대중교통)',
  code       VARCHAR(30)  NOT NULL COMMENT '예: TRANSPORT, CONVENIENCE, TELECOM',
  name       VARCHAR(30)  NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_categories_code (code),
  CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories (id)
) COMMENT='업종/혜택 카테고리';

-- 카드 상품
CREATE TABLE card_products (
  id                   VARCHAR(40)   NOT NULL,
  card_company_id      VARCHAR(40)   NOT NULL,
  name                 VARCHAR(100)  NOT NULL,
  card_type            ENUM('CREDIT','CHECK') NOT NULL,
  brand                ENUM('VISA','MASTER','AMEX','JCB','UNIONPAY','LOCAL') NOT NULL,
  annual_fee_domestic  INT           NOT NULL DEFAULT 0 COMMENT '국내전용 연회비',
  annual_fee_overseas  INT           NOT NULL DEFAULT 0 COMMENT '해외겸용 연회비',
  min_age              TINYINT       NOT NULL DEFAULT 19 COMMENT '발급 가능 최소 나이',
  image_url            VARCHAR(255)  NULL,
  summary              VARCHAR(255)  NULL     COMMENT '한 줄 혜택 요약',
  is_active            BOOLEAN       NOT NULL DEFAULT TRUE COMMENT 'FALSE = 단종 (보유는 가능, 신규 발급 불가)',
  released_at          DATE          NULL,
  created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_card_products_company (card_company_id),
  KEY idx_card_products_type_active (card_type, is_active),
  CONSTRAINT fk_card_products_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id)
) COMMENT='카드 상품';

-- 전월 실적 구간
CREATE TABLE card_performance_tiers (
  id               VARCHAR(40)  NOT NULL,
  card_product_id  VARCHAR(40)  NOT NULL,
  tier_level       TINYINT      NOT NULL COMMENT '1부터, 클수록 높은 구간',
  min_spend        BIGINT       NOT NULL COMMENT '구간 진입 전월 실적(이상)',
  max_spend        BIGINT       NULL     COMMENT '구간 상한(미만), NULL = 상한 없음',
  PRIMARY KEY (id),
  UNIQUE KEY uk_tiers_product_level (card_product_id, tier_level),
  CONSTRAINT fk_tiers_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
) COMMENT='전월 실적 구간';

-- 카드 혜택 규칙
CREATE TABLE card_benefits (
  id                    VARCHAR(40)    NOT NULL,
  card_product_id       VARCHAR(40)    NOT NULL,
  tier_id               VARCHAR(40)    NULL     COMMENT 'NULL = 실적 조건 없음',
  category_id           VARCHAR(40)    NOT NULL,
  benefit_type          ENUM('DISCOUNT','CASHBACK','POINT','MILEAGE','FEE_WAIVER') NOT NULL,
  value_type            ENUM('PERCENT','FIXED') NOT NULL,
  benefit_value         DECIMAL(10,2)  NOT NULL COMMENT 'PERCENT면 %, FIXED면 원',
  min_payment_amount    INT            NULL     COMMENT '건당 최소 결제 금액',
  monthly_limit_amount  INT            NULL     COMMENT '월 혜택 한도(원)',
  monthly_limit_count   INT            NULL     COMMENT '월 적용 횟수 한도',
  is_instant            BOOLEAN        NOT NULL DEFAULT FALSE COMMENT '즉시 캐시백 여부',
  description           VARCHAR(255)   NULL,
  PRIMARY KEY (id),
  KEY idx_benefits_product (card_product_id),
  KEY idx_benefits_category (category_id),
  CONSTRAINT fk_benefits_product  FOREIGN KEY (card_product_id) REFERENCES card_products (id),
  CONSTRAINT fk_benefits_tier     FOREIGN KEY (tier_id)         REFERENCES card_performance_tiers (id),
  CONSTRAINT fk_benefits_category FOREIGN KEY (category_id)     REFERENCES categories (id)
) COMMENT='카드 혜택 규칙';

-- 약관 (회원 파트 1장, card_product_id NULL = 공통 약관)
CREATE TABLE terms (
  id               VARCHAR(40)   NOT NULL,
  version          VARCHAR(10)   NOT NULL,
  title            VARCHAR(100)  NOT NULL,
  required         BOOLEAN       NOT NULL DEFAULT TRUE,
  effective_at     DATETIME      NOT NULL,
  card_product_id  VARCHAR(40)   NULL     COMMENT '카드 약관이면',
  PRIMARY KEY (id),
  KEY idx_terms_card_product (card_product_id),
  CONSTRAINT fk_terms_card_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
) COMMENT='약관';

-- 약관 동의 (회원 파트 1장)
CREATE TABLE user_consents (
  id           VARCHAR(40)  NOT NULL,
  user_id      VARCHAR(40)  NOT NULL,
  terms_id     VARCHAR(40)  NOT NULL,
  version      VARCHAR(10)  NOT NULL COMMENT '동의한 약관 버전',
  agreed       BOOLEAN      NOT NULL,
  recorded_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_user_consents_user (user_id),
  KEY idx_user_consents_terms (terms_id),
  CONSTRAINT fk_user_consents_user  FOREIGN KEY (user_id)  REFERENCES users (id),
  CONSTRAINT fk_user_consents_terms FOREIGN KEY (terms_id) REFERENCES terms (id)
) COMMENT='약관 동의';

-- 발급 프로모션
CREATE TABLE promotions (
  id                   VARCHAR(40)   NOT NULL,
  card_product_id      VARCHAR(40)   NOT NULL,
  title                VARCHAR(100)  NOT NULL,
  reward_amount        INT           NOT NULL COMMENT '지급 리워드(원)',
  min_spend_condition  BIGINT        NULL     COMMENT '리워드 조건: 발급 후 N원 이상 사용',
  condition_desc       VARCHAR(500)  NULL,
  starts_at            DATETIME      NOT NULL,
  ends_at              DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY idx_promotions_product_period (card_product_id, starts_at, ends_at),
  CONSTRAINT fk_promotions_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
) COMMENT='발급 프로모션';

-- 카드 추천 결과 (6장 그림, card_applications 가 참조하므로 먼저 만듦)
CREATE TABLE card_recommendations (
  id                        VARCHAR(40)   NOT NULL,
  user_id                   VARCHAR(40)   NOT NULL,
  card_product_id           VARCHAR(40)   NOT NULL,
  analysis_start            DATE          NOT NULL COMMENT '분석한 소비 기간 시작',
  analysis_end              DATE          NOT NULL,
  expected_monthly_benefit  BIGINT        NOT NULL COMMENT '월 예상 혜택',
  annual_fee                INT           NOT NULL,
  net_annual_benefit        BIGINT        NOT NULL COMMENT '연 예상 혜택 - 연회비',
  rank_no                   TINYINT       NOT NULL,
  reason                    VARCHAR(255)  NULL,
  created_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_recommendations_user_created (user_id, created_at),
  CONSTRAINT fk_recommendations_user    FOREIGN KEY (user_id)         REFERENCES users (id),
  CONSTRAINT fk_recommendations_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
) COMMENT='카드 추천';

-- 추천 근거 (업종별)
CREATE TABLE card_recommendation_details (
  recommendation_id  VARCHAR(40)  NOT NULL,
  category_id        VARCHAR(40)  NOT NULL,
  spend_amount       BIGINT       NOT NULL COMMENT '분석 기간 월평균 지출',
  benefit_amount     BIGINT       NOT NULL COMMENT '월 예상 혜택 (한도 적용 후)',
  PRIMARY KEY (recommendation_id, category_id),
  KEY idx_rec_details_category (category_id),
  CONSTRAINT fk_rec_details_recommendation FOREIGN KEY (recommendation_id) REFERENCES card_recommendations (id),
  CONSTRAINT fk_rec_details_category       FOREIGN KEY (category_id)       REFERENCES categories (id)
) COMMENT='추천 근거';

-- 발급 신청
CREATE TABLE card_applications (
  id                     VARCHAR(40)   NOT NULL,
  user_id                VARCHAR(40)   NOT NULL,
  card_product_id        VARCHAR(40)   NOT NULL,
  promotion_id           VARCHAR(40)   NULL,
  recommendation_id      VARCHAR(40)   NULL     COMMENT '추천으로 신청한 경우',
  step_up_challenge_id   VARCHAR(40)   NULL     COMMENT '신청 때 본인 확인',
  status                 ENUM('APPLIED','REVIEWING','APPROVED','REJECTED',
                              'SHIPPING','DELIVERED','ACTIVATED','CANCELED')
                                       NOT NULL DEFAULT 'APPLIED',
  job_type               VARCHAR(30)   NULL     COMMENT '직장인/자영업/학생 등 (신용카드 심사용)',
  annual_income          BIGINT        NULL,
  linked_account_id      VARCHAR(40)   NULL     COMMENT '연결 계좌',
  payment_day            TINYINT       NULL     COMMENT '희망 결제일 (신용카드)',
  approved_credit_limit  BIGINT        NULL     COMMENT '심사 승인 한도 (신용카드)',
  delivery_address       VARCHAR(255)  NOT NULL,
  tracking_no            VARCHAR(50)   NULL,
  reject_reason          ENUM('AGE','NO_INCOME','DUPLICATE') NULL,
  applied_at             DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at             DATETIME      NULL     COMMENT '승인/거절 시각',
  updated_at             DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_applications_user (user_id),
  KEY idx_applications_product_applied (card_product_id, applied_at) COMMENT '발급 순위 집계용',
  CONSTRAINT fk_applications_user           FOREIGN KEY (user_id)              REFERENCES users (id),
  CONSTRAINT fk_applications_product        FOREIGN KEY (card_product_id)      REFERENCES card_products (id),
  CONSTRAINT fk_applications_promotion      FOREIGN KEY (promotion_id)         REFERENCES promotions (id),
  CONSTRAINT fk_applications_recommendation FOREIGN KEY (recommendation_id)    REFERENCES card_recommendations (id),
  CONSTRAINT fk_applications_step_up        FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id),
  CONSTRAINT fk_applications_account        FOREIGN KEY (linked_account_id)    REFERENCES accounts (id)
) COMMENT='카드 발급 신청';

-- 발급 신청 상태 이력
CREATE TABLE application_status_histories (
  id              VARCHAR(40)   NOT NULL,
  application_id  VARCHAR(40)   NOT NULL,
  from_status     VARCHAR(20)   NULL,
  to_status       VARCHAR(20)   NOT NULL,
  memo            VARCHAR(255)  NULL,
  changed_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_app_histories_application (application_id, changed_at),
  CONSTRAINT fk_app_histories_application FOREIGN KEY (application_id) REFERENCES card_applications (id)
) COMMENT='발급 신청 상태 이력';

-- 신청별 약관 동의
CREATE TABLE application_term_agreements (
  application_id  VARCHAR(40)  NOT NULL,
  terms_id        VARCHAR(40)  NOT NULL,
  agreed          BOOLEAN      NOT NULL,
  agreed_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (application_id, terms_id),
  KEY idx_agreements_terms (terms_id),
  CONSTRAINT fk_agreements_application FOREIGN KEY (application_id) REFERENCES card_applications (id),
  CONSTRAINT fk_agreements_terms       FOREIGN KEY (terms_id)       REFERENCES terms (id)
) COMMENT='신청 약관 동의';

-- 보유 카드 (토스 경유 발급 + 마이데이터 연동 카드)
CREATE TABLE user_cards (
  id                    VARCHAR(40)  NOT NULL,
  user_id               VARCHAR(40)  NOT NULL,
  card_product_id       VARCHAR(40)  NOT NULL,
  application_id        VARCHAR(40)  NULL     COMMENT '토스 경유 발급인 경우 원 신청',
  reissued_from_id      VARCHAR(40)  NULL     COMMENT '분실/만료 재발급 시 이전 카드',
  source                ENUM('TOSS_ISSUED','MYDATA') NOT NULL,
  org_card_id           VARCHAR(64)  NULL     COMMENT '마이데이터 카드사 측 card_id (동기화 upsert 키)',
  nickname              VARCHAR(30)  NULL,
  card_number_masked    VARCHAR(25)  NOT NULL COMMENT '예: 5310-****-****-1234',
  last4                 CHAR(4)      NOT NULL,
  expires_at            DATE         NOT NULL COMMENT '유효기간 (해당 월 말일)',
  linked_account_id     VARCHAR(40)  NULL     COMMENT '체크카드 출금 계좌 / 신용카드 결제 계좌',
  payment_day           TINYINT      NULL     COMMENT '결제일 1~31, 체크카드는 NULL',
  credit_limit          BIGINT       NULL     COMMENT '신용카드만',
  status                ENUM('ACTIVE','SUSPENDED','LOST','EXPIRED','TERMINATED') NOT NULL DEFAULT 'ACTIVE',
  annual_fee_amount     INT          NOT NULL DEFAULT 0 COMMENT '실제 적용 연회비',
  next_annual_fee_date  DATE         NULL     COMMENT '다음 연회비 청구 예정일',
  last_used_at          DATETIME     NULL     COMMENT '마지막 거래 시각 (배치 갱신)',
  issued_at             DATETIME     NOT NULL,
  activated_at          DATETIME     NULL,
  terminated_at         DATETIME     NULL,
  created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_cards_application (application_id),
  UNIQUE KEY uk_user_cards_org (user_id, org_card_id),
  KEY idx_user_cards_user_status (user_id, status),
  KEY idx_user_cards_account (linked_account_id),
  CONSTRAINT fk_user_cards_user        FOREIGN KEY (user_id)           REFERENCES users (id),
  CONSTRAINT fk_user_cards_product     FOREIGN KEY (card_product_id)   REFERENCES card_products (id),
  CONSTRAINT fk_user_cards_application FOREIGN KEY (application_id)    REFERENCES card_applications (id),
  CONSTRAINT fk_user_cards_reissued    FOREIGN KEY (reissued_from_id)  REFERENCES user_cards (id),
  CONSTRAINT fk_user_cards_account     FOREIGN KEY (linked_account_id) REFERENCES accounts (id)
) COMMENT='보유 카드';

-- 카드 관리 설정 (1 : 0..1)
CREATE TABLE user_card_settings (
  user_card_id              VARCHAR(40)  NOT NULL,
  overseas_payment_blocked  BOOLEAN      NOT NULL DEFAULT FALSE,
  online_payment_blocked    BOOLEAN      NOT NULL DEFAULT FALSE,
  daily_limit               BIGINT       NULL,
  monthly_limit             BIGINT       NULL,
  payment_alert_enabled     BOOLEAN      NOT NULL DEFAULT TRUE,
  updated_at                DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_card_id),
  CONSTRAINT fk_card_settings_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='카드 관리 설정';

-- 카드 상태 변경 이력
CREATE TABLE user_card_status_histories (
  id            VARCHAR(40)   NOT NULL,
  user_card_id  VARCHAR(40)   NOT NULL,
  from_status   VARCHAR(20)   NULL,
  to_status     VARCHAR(20)   NOT NULL,
  reason        VARCHAR(255)  NULL,
  changed_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_card_histories_card (user_card_id, changed_at),
  CONSTRAINT fk_card_histories_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='카드 상태 이력';

-- 카드 관리 기록 (결제 차단, 한도, 비밀번호 — 비밀번호 값은 저장하지 않음)
CREATE TABLE card_management_logs (
  id            VARCHAR(40)  NOT NULL,
  user_card_id  VARCHAR(40)  NOT NULL,
  action_type   ENUM('BLOCK_OVERSEAS','UNBLOCK_OVERSEAS','BLOCK_ONLINE','UNBLOCK_ONLINE',
                     'LIMIT_CHANGE','PIN_CHANGE') NOT NULL,
  before_value  VARCHAR(50)  NULL     COMMENT 'PIN_CHANGE는 값 저장 금지',
  after_value   VARCHAR(50)  NULL,
  result        ENUM('SUCCESS','FAILED') NOT NULL,
  requested_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_mgmt_logs_card (user_card_id, requested_at),
  CONSTRAINT fk_mgmt_logs_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
) COMMENT='카드 관리 기록';

-- 카드 해지 (해지 전 확인 정보를 스냅샷으로 저장)
CREATE TABLE card_terminations (
  id                            VARCHAR(40)   NOT NULL,
  user_card_id                  VARCHAR(40)   NOT NULL,
  step_up_challenge_id          VARCHAR(40)   NULL     COMMENT '해지 요청 본인 확인',
  status                        ENUM('REQUESTED','COMPLETED','REJECTED','CANCELED') NOT NULL DEFAULT 'REQUESTED',
  reason_code                   ENUM('LOW_BENEFIT','HIGH_FEE','NOT_USING','SWITCH_CARD','OTHER') NOT NULL,
  reason_detail                 VARCHAR(255)  NULL,
  unpaid_amount                 BIGINT        NOT NULL DEFAULT 0 COMMENT '미결제 금액',
  remaining_installment_amount  BIGINT        NOT NULL DEFAULT 0 COMMENT '남은 할부 원금',
  linked_recurring_count        INT           NOT NULL DEFAULT 0 COMMENT '연결된 자동결제 건수',
  forfeited_points              BIGINT        NOT NULL DEFAULT 0 COMMENT '소멸 예정 포인트',
  refunded_annual_fee           INT           NOT NULL DEFAULT 0 COMMENT '연회비 일할 환급액',
  requested_at                  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at                  DATETIME      NULL,
  PRIMARY KEY (id),
  KEY idx_terminations_card (user_card_id),
  CONSTRAINT fk_terminations_card    FOREIGN KEY (user_card_id)         REFERENCES user_cards (id),
  CONSTRAINT fk_terminations_step_up FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id)
) COMMENT='카드 해지';