-- =====================================================================
-- 토스 카드 서비스 클론 - 스키마 (MySQL 8.0)
-- 금액 단위: 원(KRW) 정수(BIGINT). 외화 원금만 DECIMAL.
-- 테이블 우선순위: [필수] / [차별화] / [선택]  (docs/ERD.md 참고)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS toss_card
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
USE toss_card;

-- ---------------------------------------------------------------------
-- 1. 회원 / 계좌
-- ---------------------------------------------------------------------

-- [필수] 회원
CREATE TABLE users (
  user_id           BIGINT        NOT NULL AUTO_INCREMENT,
  name              VARCHAR(50)   NOT NULL,
  birth_date        DATE          NOT NULL,
  gender            ENUM('M','F') NOT NULL,
  phone             VARCHAR(20)   NOT NULL,
  email             VARCHAR(100)  NULL,
  ci                VARCHAR(100)  NOT NULL COMMENT '본인인증 연계정보(CI)',
  mydata_agreed_at  DATETIME      NULL     COMMENT '마이데이터 연동 동의 시각 (NULL = 미동의)',
  payday            TINYINT       NULL     COMMENT '월급일 (1~31), 사용 금액 예측용',
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  UNIQUE KEY uk_users_ci (ci),
  UNIQUE KEY uk_users_phone (phone)
) COMMENT='회원';

-- [필수] 계좌 (체크카드 연결, 포인트 현금화 입금처)
CREATE TABLE accounts (
  account_id             BIGINT       NOT NULL AUTO_INCREMENT,
  user_id                BIGINT       NOT NULL,
  bank_name              VARCHAR(30)  NOT NULL,
  account_number_masked  VARCHAR(30)  NOT NULL COMMENT '예: 1000-****-5678',
  balance                BIGINT       NOT NULL DEFAULT 0,
  is_primary             BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (account_id),
  KEY idx_accounts_user (user_id),
  CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES users (user_id)
) COMMENT='계좌';

-- [필수] 본인인증 결과 (발급 신청, 해지, 카드 관리 시 users.ci와 비교)
CREATE TABLE identity_verifications (
  verification_id  BIGINT        NOT NULL AUTO_INCREMENT,
  user_id          BIGINT        NOT NULL,
  purpose          ENUM('APPLICATION','TERMINATION','CARD_MANAGEMENT') NOT NULL,
  method           ENUM('MYDATA','PASS','CERT') NOT NULL,
  ci               VARCHAR(100)  NOT NULL COMMENT '인증 결과 CI',
  result           ENUM('SUCCESS','FAILED') NOT NULL,
  verified_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (verification_id),
  KEY idx_verifications_user (user_id, verified_at),
  CONSTRAINT fk_verifications_user FOREIGN KEY (user_id) REFERENCES users (user_id)
) COMMENT='본인인증';

-- ---------------------------------------------------------------------
-- 2. 카드 상품 / 혜택
-- ---------------------------------------------------------------------

-- [필수] 카드사
CREATE TABLE card_companies (
  company_id       INT          NOT NULL AUTO_INCREMENT,
  code             VARCHAR(10)  NOT NULL COMMENT '예: SHINHAN, HYUNDAI, TOSSBANK',
  name             VARCHAR(30)  NOT NULL,
  logo_url         VARCHAR(255) NULL,
  customer_center  VARCHAR(20)  NULL,
  PRIMARY KEY (company_id),
  UNIQUE KEY uk_card_companies_code (code)
) COMMENT='카드사';

-- [필수] 업종/혜택 카테고리 (가맹점 분류와 혜택 대상 분류에 공통 사용)
CREATE TABLE categories (
  category_id  INT          NOT NULL AUTO_INCREMENT,
  parent_id    INT          NULL     COMMENT '상위 카테고리 (예: 교통 > 대중교통)',
  code         VARCHAR(30)  NOT NULL COMMENT '예: TRANSPORT, CONVENIENCE, TELECOM',
  name         VARCHAR(30)  NOT NULL,
  PRIMARY KEY (category_id),
  UNIQUE KEY uk_categories_code (code),
  CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories (category_id)
) COMMENT='업종/혜택 카테고리';

-- [필수] 카드 상품
CREATE TABLE card_products (
  product_id           BIGINT        NOT NULL AUTO_INCREMENT,
  company_id           INT           NOT NULL,
  name                 VARCHAR(100)  NOT NULL,
  card_type            ENUM('CREDIT','CHECK') NOT NULL,
  brand                ENUM('VISA','MASTER','AMEX','JCB','UNIONPAY','LOCAL') NOT NULL,
  annual_fee_domestic  INT           NOT NULL DEFAULT 0 COMMENT '국내전용 연회비',
  annual_fee_overseas  INT           NOT NULL DEFAULT 0 COMMENT '해외겸용 연회비',
  min_age              TINYINT       NOT NULL DEFAULT 19 COMMENT '발급 가능 최소 나이 (유스카드 12 등)',
  image_url            VARCHAR(255)  NULL,
  summary              VARCHAR(255)  NULL     COMMENT '한 줄 혜택 요약',
  is_active            BOOLEAN       NOT NULL DEFAULT TRUE COMMENT 'FALSE = 단종 (보유는 가능, 신규 발급 불가)',
  released_at          DATE          NULL,
  created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id),
  KEY idx_card_products_company (company_id),
  KEY idx_card_products_type_active (card_type, is_active),
  CONSTRAINT fk_card_products_company FOREIGN KEY (company_id) REFERENCES card_companies (company_id)
) COMMENT='카드 상품';

-- [차별화] 전월 실적 구간 (예: 30만↑ = 1구간, 50만↑ = 2구간)
CREATE TABLE card_performance_tiers (
  tier_id     BIGINT   NOT NULL AUTO_INCREMENT,
  product_id  BIGINT   NOT NULL,
  tier_level  TINYINT  NOT NULL COMMENT '1부터 시작, 클수록 높은 구간',
  min_spend   BIGINT   NOT NULL COMMENT '구간 진입 전월 실적(이상)',
  max_spend   BIGINT   NULL     COMMENT '구간 상한(미만), NULL = 상한 없음',
  PRIMARY KEY (tier_id),
  UNIQUE KEY uk_tiers_product_level (product_id, tier_level),
  CONSTRAINT fk_tiers_product FOREIGN KEY (product_id) REFERENCES card_products (product_id)
) COMMENT='전월 실적 구간';

-- [필수] 카드 혜택 규칙 (추천 계산과 거래별 혜택 적용의 기준)
CREATE TABLE card_benefits (
  benefit_id            BIGINT         NOT NULL AUTO_INCREMENT,
  product_id            BIGINT         NOT NULL,
  tier_id               BIGINT         NULL     COMMENT 'NULL = 실적 조건 없음',
  category_id           INT            NOT NULL,
  benefit_type          ENUM('DISCOUNT','CASHBACK','POINT','MILEAGE','FEE_WAIVER') NOT NULL,
  value_type            ENUM('PERCENT','FIXED') NOT NULL,
  benefit_value         DECIMAL(10,2)  NOT NULL COMMENT 'PERCENT면 %, FIXED면 원',
  min_payment_amount    INT            NULL     COMMENT '건당 최소 결제 금액',
  monthly_limit_amount  INT            NULL     COMMENT '월 혜택 한도(원)',
  monthly_limit_count   INT            NULL     COMMENT '월 적용 횟수 한도',
  is_instant            BOOLEAN        NOT NULL DEFAULT FALSE COMMENT '즉시 캐시백 여부 (토스뱅크 체크카드)',
  description           VARCHAR(255)   NULL,
  PRIMARY KEY (benefit_id),
  KEY idx_benefits_product (product_id),
  KEY idx_benefits_category (category_id),
  CONSTRAINT fk_benefits_product  FOREIGN KEY (product_id)  REFERENCES card_products (product_id),
  CONSTRAINT fk_benefits_tier     FOREIGN KEY (tier_id)     REFERENCES card_performance_tiers (tier_id),
  CONSTRAINT fk_benefits_category FOREIGN KEY (category_id) REFERENCES categories (category_id)
) COMMENT='카드 혜택 규칙';

-- [필수] 약관 (product_id NULL = 공통 약관)
CREATE TABLE terms (
  term_id       BIGINT        NOT NULL AUTO_INCREMENT,
  product_id    BIGINT        NULL,
  title         VARCHAR(100)  NOT NULL,
  version       VARCHAR(10)   NOT NULL,
  is_required   BOOLEAN       NOT NULL DEFAULT TRUE,
  content_url   VARCHAR(255)  NOT NULL,
  effective_at  DATE          NOT NULL,
  PRIMARY KEY (term_id),
  KEY idx_terms_product (product_id),
  CONSTRAINT fk_terms_product FOREIGN KEY (product_id) REFERENCES card_products (product_id)
) COMMENT='약관';

-- [선택] 발급 프로모션 (토스 경유 발급 시 현금 리워드)
CREATE TABLE promotions (
  promotion_id         BIGINT        NOT NULL AUTO_INCREMENT,
  product_id           BIGINT        NOT NULL,
  title                VARCHAR(100)  NOT NULL,
  reward_amount        INT           NOT NULL COMMENT '지급 리워드(원)',
  min_spend_condition  BIGINT        NULL     COMMENT '리워드 조건: 발급 후 N원 이상 사용',
  condition_desc       VARCHAR(500)  NULL,
  starts_at            DATETIME      NOT NULL,
  ends_at              DATETIME      NOT NULL,
  PRIMARY KEY (promotion_id),
  KEY idx_promotions_product_period (product_id, starts_at, ends_at),
  CONSTRAINT fk_promotions_product FOREIGN KEY (product_id) REFERENCES card_products (product_id)
) COMMENT='발급 프로모션';

-- ---------------------------------------------------------------------
-- 3. 발급 신청 / 보유 카드 / 해지
-- ---------------------------------------------------------------------

-- [필수] 발급 신청
CREATE TABLE card_applications (
  application_id       BIGINT        NOT NULL AUTO_INCREMENT,
  user_id              BIGINT        NOT NULL,
  product_id           BIGINT        NOT NULL,
  promotion_id         BIGINT        NULL,
  recommendation_id    BIGINT        NULL     COMMENT '추천을 통해 신청한 경우 (FK는 card_recommendations 생성 후 추가)',
  verification_id      BIGINT        NULL     COMMENT '신청 시 본인인증',
  status              ENUM('APPLIED','REVIEWING','APPROVED','REJECTED',
                            'SHIPPING','DELIVERED','ACTIVATED','CANCELED')
                                     NOT NULL DEFAULT 'APPLIED',
  job_type             VARCHAR(30)   NULL     COMMENT '직장인/자영업/학생 등 (신용카드 심사용)',
  annual_income        BIGINT        NULL,
  linked_account_id    BIGINT        NULL     COMMENT '체크카드 결제 계좌',
  payment_day          TINYINT       NULL     COMMENT '희망 결제일 (신용카드)',
  delivery_address     VARCHAR(255)  NOT NULL,
  tracking_no          VARCHAR(50)   NULL,
  reject_reason        VARCHAR(255)  NULL,
  applied_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at           DATETIME      NULL     COMMENT '승인/거절 시각',
  updated_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (application_id),
  KEY idx_applications_user (user_id),
  KEY idx_applications_product_applied (product_id, applied_at) COMMENT '발급 순위 집계용',
  CONSTRAINT fk_applications_user      FOREIGN KEY (user_id)           REFERENCES users (user_id),
  CONSTRAINT fk_applications_product   FOREIGN KEY (product_id)        REFERENCES card_products (product_id),
  CONSTRAINT fk_applications_promotion FOREIGN KEY (promotion_id)      REFERENCES promotions (promotion_id),
  CONSTRAINT fk_applications_account   FOREIGN KEY (linked_account_id) REFERENCES accounts (account_id),
  CONSTRAINT fk_applications_verification FOREIGN KEY (verification_id) REFERENCES identity_verifications (verification_id)
) COMMENT='카드 발급 신청';

-- [필수] 발급 신청 상태 이력
CREATE TABLE application_status_histories (
  history_id      BIGINT        NOT NULL AUTO_INCREMENT,
  application_id  BIGINT        NOT NULL,
  from_status     VARCHAR(20)   NULL,
  to_status       VARCHAR(20)   NOT NULL,
  memo            VARCHAR(255)  NULL,
  changed_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (history_id),
  KEY idx_app_histories_application (application_id, changed_at),
  CONSTRAINT fk_app_histories_application FOREIGN KEY (application_id) REFERENCES card_applications (application_id)
) COMMENT='발급 신청 상태 이력';

-- [필수] 신청별 약관 동의
CREATE TABLE application_term_agreements (
  application_id  BIGINT    NOT NULL,
  term_id         BIGINT    NOT NULL,
  agreed          BOOLEAN   NOT NULL,
  agreed_at       DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (application_id, term_id),
  CONSTRAINT fk_agreements_application FOREIGN KEY (application_id) REFERENCES card_applications (application_id),
  CONSTRAINT fk_agreements_term        FOREIGN KEY (term_id)        REFERENCES terms (term_id)
) COMMENT='약관 동의';

-- [필수] 보유 카드 (토스 경유 발급 + 마이데이터 연동 카드 모두)
CREATE TABLE user_cards (
  user_card_id        BIGINT       NOT NULL AUTO_INCREMENT,
  user_id             BIGINT       NOT NULL,
  product_id          BIGINT       NOT NULL,
  application_id      BIGINT       NULL     COMMENT '토스 경유 발급인 경우 원 신청',
  reissued_from_id    BIGINT       NULL     COMMENT '분실/만료 재발급 시 이전 카드',
  source              ENUM('TOSS_ISSUED','MYDATA') NOT NULL,
  org_card_id         VARCHAR(64)  NULL     COMMENT '마이데이터 카드사 측 card_id (동기화 upsert 키)',
  nickname           VARCHAR(30)  NULL,
  card_number_masked  VARCHAR(25)  NOT NULL COMMENT '예: 5310-****-****-1234',
  last4               CHAR(4)      NOT NULL,
  expires_at          DATE         NOT NULL COMMENT '유효기간 (해당 월 말일)',
  linked_account_id   BIGINT       NULL     COMMENT '체크카드 출금 계좌 / 신용카드 결제 계좌',
  payment_day         TINYINT      NULL     COMMENT '결제일 (1~31). 체크카드는 NULL',
  status              ENUM('ACTIVE','SUSPENDED','LOST','EXPIRED','TERMINATED') NOT NULL DEFAULT 'ACTIVE',
  annual_fee_amount   INT          NOT NULL DEFAULT 0 COMMENT '실제 적용 연회비 (국내전용/해외겸용 중)',
  next_annual_fee_date DATE        NULL     COMMENT '다음 연회비 청구 예정일',
  last_used_at        DATETIME     NULL     COMMENT '마지막 거래 시각 (배치 갱신, 미사용 카드 안내용)',
  issued_at           DATETIME     NOT NULL,
  activated_at        DATETIME     NULL,
  terminated_at       DATETIME     NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_card_id),
  UNIQUE KEY uk_user_cards_application (application_id),
  UNIQUE KEY uk_user_cards_org (user_id, org_card_id),
  KEY idx_user_cards_user_status (user_id, status),
  CONSTRAINT fk_user_cards_user        FOREIGN KEY (user_id)           REFERENCES users (user_id),
  CONSTRAINT fk_user_cards_product     FOREIGN KEY (product_id)        REFERENCES card_products (product_id),
  CONSTRAINT fk_user_cards_application FOREIGN KEY (application_id)    REFERENCES card_applications (application_id),
  CONSTRAINT fk_user_cards_reissued    FOREIGN KEY (reissued_from_id)  REFERENCES user_cards (user_card_id),
  CONSTRAINT fk_user_cards_account     FOREIGN KEY (linked_account_id) REFERENCES accounts (account_id)
) COMMENT='보유 카드';

-- [선택] 카드 관리 설정 (1:1) - 해외/온라인 결제 차단, 한도
CREATE TABLE user_card_settings (
  user_card_id              BIGINT    NOT NULL,
  overseas_payment_blocked  BOOLEAN   NOT NULL DEFAULT FALSE,
  online_payment_blocked    BOOLEAN   NOT NULL DEFAULT FALSE,
  daily_limit               BIGINT    NULL,
  monthly_limit             BIGINT    NULL,
  payment_alert_enabled     BOOLEAN   NOT NULL DEFAULT TRUE,
  updated_at                DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_card_id),
  CONSTRAINT fk_card_settings_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='카드 관리 설정';

-- [선택] 카드 상태 변경 이력 (일시정지, 분실신고, 해지 등)
CREATE TABLE user_card_status_histories (
  history_id    BIGINT        NOT NULL AUTO_INCREMENT,
  user_card_id  BIGINT        NOT NULL,
  from_status   VARCHAR(20)   NULL,
  to_status     VARCHAR(20)   NOT NULL,
  reason        VARCHAR(255)  NULL,
  changed_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (history_id),
  KEY idx_card_histories_card (user_card_id, changed_at),
  CONSTRAINT fk_card_histories_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='카드 상태 이력';

-- [선택] 카드 관리 이력 (상태 외 설정 변경: 결제 차단, 한도, 비밀번호)
-- 비밀번호는 Mock 카드사 서버로 전달만 하고 값은 저장하지 않음
CREATE TABLE card_management_logs (
  log_id        BIGINT       NOT NULL AUTO_INCREMENT,
  user_card_id  BIGINT       NOT NULL,
  action_type   ENUM('BLOCK_OVERSEAS','UNBLOCK_OVERSEAS','BLOCK_ONLINE','UNBLOCK_ONLINE',
                     'LIMIT_CHANGE','PIN_CHANGE') NOT NULL,
  before_value  VARCHAR(50)  NULL COMMENT 'PIN_CHANGE는 값 저장 금지',
  after_value   VARCHAR(50)  NULL,
  result        ENUM('SUCCESS','FAILED') NOT NULL,
  requested_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (log_id),
  KEY idx_mgmt_logs_card (user_card_id, requested_at),
  CONSTRAINT fk_mgmt_logs_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='카드 관리 이력';

-- [필수] 해지 신청 (해지 전 확인 정보를 스냅샷으로 저장)
CREATE TABLE card_terminations (
  termination_id                BIGINT        NOT NULL AUTO_INCREMENT,
  user_card_id                  BIGINT        NOT NULL,
  verification_id               BIGINT        NULL     COMMENT '해지 요청자 본인인증 (카드 소유자 ci와 일치해야 함)',
  status                        ENUM('REQUESTED','COMPLETED','REJECTED','WITHDRAWN') NOT NULL DEFAULT 'REQUESTED',
  reason_code                   ENUM('LOW_BENEFIT','HIGH_FEE','NOT_USING','SWITCH_CARD','OTHER') NOT NULL,
  reason_detail                 VARCHAR(255)  NULL,
  unpaid_amount                 BIGINT        NOT NULL DEFAULT 0 COMMENT '미결제 금액',
  remaining_installment_amount  BIGINT        NOT NULL DEFAULT 0 COMMENT '남은 할부 원금',
  linked_recurring_count        INT           NOT NULL DEFAULT 0 COMMENT '연결된 자동결제 건수',
  forfeited_points              BIGINT        NOT NULL DEFAULT 0 COMMENT '소멸 예정 포인트',
  refunded_annual_fee           INT           NOT NULL DEFAULT 0 COMMENT '연회비 일할 환급액',
  requested_at                  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at                  DATETIME      NULL,
  PRIMARY KEY (termination_id),
  KEY idx_terminations_card (user_card_id),
  CONSTRAINT fk_terminations_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id),
  CONSTRAINT fk_terminations_verification FOREIGN KEY (verification_id) REFERENCES identity_verifications (verification_id)
) COMMENT='카드 해지';

-- ---------------------------------------------------------------------
-- 4. 이용 내역 / 청구
-- ---------------------------------------------------------------------

-- [필수] 가맹점
CREATE TABLE merchants (
  merchant_id  BIGINT        NOT NULL AUTO_INCREMENT,
  category_id  INT           NOT NULL,
  name         VARCHAR(100)  NOT NULL,
  business_no  VARCHAR(12)   NULL COMMENT '사업자등록번호',
  PRIMARY KEY (merchant_id),
  UNIQUE KEY uk_merchants_business_no (business_no),
  KEY idx_merchants_category (category_id),
  CONSTRAINT fk_merchants_category FOREIGN KEY (category_id) REFERENCES categories (category_id)
) COMMENT='가맹점';

-- [필수] 카드 승인/이용 내역
CREATE TABLE card_transactions (
  transaction_id          BIGINT         NOT NULL AUTO_INCREMENT,
  user_card_id            BIGINT         NOT NULL,
  merchant_id             BIGINT         NOT NULL,
  approval_no             VARCHAR(20)    NOT NULL,
  transacted_at           DATETIME       NOT NULL,
  amount                  BIGINT         NOT NULL COMMENT '원화 승인 금액',
  installment_months      TINYINT        NOT NULL DEFAULT 0 COMMENT '0 = 일시불',
  is_overseas             BOOLEAN        NOT NULL DEFAULT FALSE,
  currency                CHAR(3)        NOT NULL DEFAULT 'KRW',
  foreign_amount          DECIMAL(15,2)  NULL     COMMENT '해외 결제 현지 통화 금액',
  status                  ENUM('APPROVED','PARTIAL_CANCELED','CANCELED') NOT NULL DEFAULT 'APPROVED',
  canceled_amount         BIGINT         NOT NULL DEFAULT 0,
  canceled_at             DATETIME       NULL,
  applied_benefit_id      BIGINT         NULL     COMMENT '적용된 혜택 규칙',
  benefit_amount          BIGINT         NOT NULL DEFAULT 0 COMMENT '할인/캐시백 금액',
  is_performance_counted  BOOLEAN        NOT NULL DEFAULT TRUE COMMENT 'FALSE = 실적 제외 (세금, 상품권 등)',
  created_at              DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (transaction_id),
  UNIQUE KEY uk_transactions_card_approval (user_card_id, approval_no),
  KEY idx_transactions_card_time (user_card_id, transacted_at),
  KEY idx_transactions_merchant (merchant_id),
  CONSTRAINT fk_transactions_card     FOREIGN KEY (user_card_id)       REFERENCES user_cards (user_card_id),
  CONSTRAINT fk_transactions_merchant FOREIGN KEY (merchant_id)        REFERENCES merchants (merchant_id),
  CONSTRAINT fk_transactions_benefit  FOREIGN KEY (applied_benefit_id) REFERENCES card_benefits (benefit_id)
) COMMENT='카드 이용 내역';

-- [필수] 결제일별 이용 기간 규칙 (카드사마다 다름. card_bills의 usage_start/usage_end 생성 기준)
-- 예: 결제일 14일 → 전월 1일 ~ 전월 말일 = (-1, 1) ~ (-1, 99)
CREATE TABLE billing_cycle_rules (
  company_id          INT      NOT NULL,
  payment_day         TINYINT  NOT NULL,
  start_month_offset  TINYINT  NOT NULL COMMENT '결제월 기준 이용 시작 월 (-2, -1)',
  start_day           TINYINT  NOT NULL,
  end_month_offset    TINYINT  NOT NULL COMMENT '결제월 기준 이용 끝 월 (-1, 0)',
  end_day             TINYINT  NOT NULL COMMENT '99 = 말일',
  PRIMARY KEY (company_id, payment_day),
  CONSTRAINT fk_cycle_rules_company FOREIGN KEY (company_id) REFERENCES card_companies (company_id)
) COMMENT='결제일별 이용 기간 규칙';

-- [필수] 월별 청구서 (결제일 기준). 이용 기간(usage_start~usage_end)이 결제일과 다름에 주의
CREATE TABLE card_bills (
  bill_id       BIGINT    NOT NULL AUTO_INCREMENT,
  user_card_id  BIGINT    NOT NULL,
  billing_ym    CHAR(6)   NOT NULL COMMENT '결제 연월 YYYYMM',
  usage_start   DATE      NOT NULL COMMENT '이용 기간 시작',
  usage_end     DATE      NOT NULL COMMENT '이용 기간 끝',
  payment_date  DATE      NOT NULL COMMENT '실제 결제(출금)일',
  total_amount  BIGINT    NOT NULL DEFAULT 0,
  paid_amount   BIGINT    NOT NULL DEFAULT 0,
  status        ENUM('SCHEDULED','CONFIRMED','PAID','OVERDUE') NOT NULL DEFAULT 'SCHEDULED'
                COMMENT 'SCHEDULED = 이용 기간 진행 중 / CONFIRMED = 청구 확정',
  confirmed_at  DATETIME  NULL,
  paid_at       DATETIME  NULL,
  PRIMARY KEY (bill_id),
  UNIQUE KEY uk_bills_card_ym (user_card_id, billing_ym),
  CONSTRAINT fk_bills_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='카드 청구서';

-- [필수] 청구 항목 - 할부는 회차별로 여러 청구서에 나뉘어 들어감
CREATE TABLE card_bill_items (
  bill_item_id      BIGINT   NOT NULL AUTO_INCREMENT,
  bill_id           BIGINT   NOT NULL,
  transaction_id    BIGINT   NOT NULL,
  installment_seq   TINYINT  NOT NULL DEFAULT 1 COMMENT '할부 회차 (일시불 = 1)',
  principal_amount  BIGINT   NOT NULL COMMENT '이번 회차 원금',
  fee_amount        BIGINT   NOT NULL DEFAULT 0 COMMENT '할부 수수료',
  PRIMARY KEY (bill_item_id),
  UNIQUE KEY uk_bill_items_tx_seq (transaction_id, installment_seq),
  KEY idx_bill_items_bill (bill_id),
  CONSTRAINT fk_bill_items_bill        FOREIGN KEY (bill_id)        REFERENCES card_bills (bill_id),
  CONSTRAINT fk_bill_items_transaction FOREIGN KEY (transaction_id) REFERENCES card_transactions (transaction_id)
) COMMENT='청구 항목';

-- ---------------------------------------------------------------------
-- 5. 소비 분석 / 사용 금액 예측
-- ---------------------------------------------------------------------

-- [차별화] 고정지출(정기결제) - 자동 탐지 또는 사용자 등록
CREATE TABLE recurring_payments (
  recurring_id     BIGINT    NOT NULL AUTO_INCREMENT,
  user_id          BIGINT    NOT NULL,
  user_card_id     BIGINT    NOT NULL,
  merchant_id      BIGINT    NOT NULL,
  pay_cycle        ENUM('MONTHLY','YEARLY') NOT NULL DEFAULT 'MONTHLY',
  expected_amount  BIGINT    NOT NULL,
  expected_day     TINYINT   NOT NULL COMMENT '예상 결제일 (일)',
  last_paid_at     DATE      NULL,
  detected_by      ENUM('AUTO','USER') NOT NULL DEFAULT 'AUTO',
  is_active        BOOLEAN   NOT NULL DEFAULT TRUE,
  created_at       DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (recurring_id),
  UNIQUE KEY uk_recurring_card_merchant (user_card_id, merchant_id, pay_cycle),
  KEY idx_recurring_user (user_id),
  CONSTRAINT fk_recurring_user     FOREIGN KEY (user_id)      REFERENCES users (user_id),
  CONSTRAINT fk_recurring_card     FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id),
  CONSTRAINT fk_recurring_merchant FOREIGN KEY (merchant_id)  REFERENCES merchants (merchant_id)
) COMMENT='고정지출';

-- [차별화] 사용 금액 예측 결과 (일 배치 스냅샷)
-- predicted_total = spent_to_date + confirmed_installment + fixed_expected + variable_expected
CREATE TABLE spending_forecasts (
  forecast_id            BIGINT    NOT NULL AUTO_INCREMENT,
  user_card_id           BIGINT    NOT NULL,
  billing_ym             CHAR(6)   NOT NULL COMMENT '예측 대상 결제 연월',
  base_date              DATE      NOT NULL COMMENT '예측 기준일',
  spent_to_date          BIGINT    NOT NULL COMMENT '기준일까지 이용 기간 내 일시불 사용액',
  confirmed_installment  BIGINT    NOT NULL DEFAULT 0 COMMENT '이미 확정된 이전 할부 회차분',
  fixed_expected         BIGINT    NOT NULL DEFAULT 0 COMMENT '남은 기간 고정지출 예정액',
  variable_expected      BIGINT    NOT NULL DEFAULT 0 COMMENT '남은 기간 변동지출 추정액',
  predicted_total        BIGINT    NOT NULL,
  model_type             ENUM('LINEAR','MOVING_AVG','FIXED_SPLIT','ML') NOT NULL,
  created_at             DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (forecast_id),
  UNIQUE KEY uk_forecasts (user_card_id, billing_ym, base_date, model_type),
  CONSTRAINT fk_forecasts_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='사용 금액 예측';

-- [선택] 일별 사용액 집계 (요일/월급일 패턴 시계열 예측의 학습 데이터, 일 배치)
CREATE TABLE daily_card_spending (
  user_card_id      BIGINT   NOT NULL,
  spend_date        DATE     NOT NULL,
  total_amount      BIGINT   NOT NULL DEFAULT 0,
  fixed_amount      BIGINT   NOT NULL DEFAULT 0 COMMENT 'recurring_payments 매칭분',
  tx_count          INT      NOT NULL DEFAULT 0,
  weekday           TINYINT  NOT NULL COMMENT '1=월 ~ 7=일',
  days_from_payday  TINYINT  NULL     COMMENT 'users.payday 기준 경과일',
  is_holiday        BOOLEAN  NOT NULL DEFAULT FALSE,
  PRIMARY KEY (user_card_id, spend_date),
  CONSTRAINT fk_daily_spending_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='일별 사용액 집계';

-- ---------------------------------------------------------------------
-- 6. 추천 / 발급 순위
-- ---------------------------------------------------------------------

-- [차별화] 카드 추천 결과 (배치로 계산 후 저장)
CREATE TABLE card_recommendations (
  recommendation_id         BIGINT        NOT NULL AUTO_INCREMENT,
  user_id                   BIGINT        NOT NULL,
  product_id                BIGINT        NOT NULL,
  analysis_start            DATE          NOT NULL COMMENT '분석한 소비 기간 시작',
  analysis_end              DATE          NOT NULL,
  expected_monthly_benefit  BIGINT        NOT NULL COMMENT '월 예상 혜택',
  annual_fee                INT           NOT NULL,
  net_annual_benefit        BIGINT        NOT NULL COMMENT '연 예상 혜택 - 연회비',
  rank_no                   TINYINT       NOT NULL,
  reason                    VARCHAR(255)  NULL     COMMENT '예: 최근 3개월 편의점 지출이 많아요',
  created_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (recommendation_id),
  KEY idx_recommendations_user_created (user_id, created_at),
  CONSTRAINT fk_recommendations_user    FOREIGN KEY (user_id)    REFERENCES users (user_id),
  CONSTRAINT fk_recommendations_product FOREIGN KEY (product_id) REFERENCES card_products (product_id)
) COMMENT='카드 추천';

-- [차별화] 추천 근거 - 카테고리별 지출과 예상 혜택
CREATE TABLE card_recommendation_details (
  recommendation_id  BIGINT  NOT NULL,
  category_id        INT     NOT NULL,
  spend_amount       BIGINT  NOT NULL COMMENT '분석 기간 월평균 지출',
  benefit_amount     BIGINT  NOT NULL COMMENT '월 예상 혜택 (한도 적용 후)',
  PRIMARY KEY (recommendation_id, category_id),
  CONSTRAINT fk_rec_details_recommendation FOREIGN KEY (recommendation_id) REFERENCES card_recommendations (recommendation_id),
  CONSTRAINT fk_rec_details_category       FOREIGN KEY (category_id)       REFERENCES categories (category_id)
) COMMENT='추천 근거';

-- card_applications가 card_recommendations보다 먼저 생성되므로 FK는 여기서 추가
ALTER TABLE card_applications
  ADD CONSTRAINT fk_applications_recommendation
  FOREIGN KEY (recommendation_id) REFERENCES card_recommendations (recommendation_id);

-- [선택] 발급 순위 스냅샷 (card_applications 집계 결과)
CREATE TABLE card_issuance_rankings (
  ranking_id      BIGINT       NOT NULL AUTO_INCREMENT,
  period_type     ENUM('DAILY','WEEKLY','MONTHLY') NOT NULL,
  period_start    DATE         NOT NULL,
  segment_age     VARCHAR(10)  NOT NULL DEFAULT 'ALL' COMMENT 'ALL, 10s, 20s, 30s ...',
  segment_gender  ENUM('ALL','M','F') NOT NULL DEFAULT 'ALL',
  card_type       ENUM('ALL','CREDIT','CHECK') NOT NULL DEFAULT 'ALL',
  product_id      BIGINT       NOT NULL,
  rank_no         SMALLINT     NOT NULL,
  issue_count     INT          NOT NULL,
  prev_rank_no    SMALLINT     NULL COMMENT '직전 기간 순위 (NULL = 신규 진입)',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ranking_id),
  UNIQUE KEY uk_rankings (period_type, period_start, segment_age, segment_gender, card_type, rank_no),
  KEY idx_rankings_product (product_id),
  CONSTRAINT fk_rankings_product FOREIGN KEY (product_id) REFERENCES card_products (product_id)
) COMMENT='발급 순위';

-- ---------------------------------------------------------------------
-- 7. 포인트 / 알림
-- ---------------------------------------------------------------------

-- [선택] 카드사별 포인트 잔액 (마이데이터 동기화)
CREATE TABLE card_points (
  card_point_id    BIGINT    NOT NULL AUTO_INCREMENT,
  user_id          BIGINT    NOT NULL,
  company_id       INT       NOT NULL,
  point_name       VARCHAR(30) NULL    COMMENT '예: 마이신한포인트',
  balance          BIGINT    NOT NULL DEFAULT 0,
  expiring_amount  BIGINT    NOT NULL DEFAULT 0 COMMENT '소멸 예정 포인트',
  expiring_date    DATE      NULL,
  synced_at        DATETIME  NOT NULL,
  PRIMARY KEY (card_point_id),
  UNIQUE KEY uk_card_points_user_company (user_id, company_id),
  CONSTRAINT fk_card_points_user    FOREIGN KEY (user_id)    REFERENCES users (user_id),
  CONSTRAINT fk_card_points_company FOREIGN KEY (company_id) REFERENCES card_companies (company_id)
) COMMENT='카드 포인트';

-- [선택] 포인트 현금화 (카드사 단위로 1건)
CREATE TABLE point_cashouts (
  cashout_id     BIGINT    NOT NULL AUTO_INCREMENT,
  card_point_id  BIGINT    NOT NULL,
  account_id     BIGINT    NOT NULL COMMENT '입금 계좌',
  amount         BIGINT    NOT NULL,
  status         ENUM('REQUESTED','COMPLETED','FAILED') NOT NULL DEFAULT 'REQUESTED',
  requested_at   DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at   DATETIME  NULL,
  PRIMARY KEY (cashout_id),
  KEY idx_cashouts_point (card_point_id),
  CONSTRAINT fk_cashouts_point   FOREIGN KEY (card_point_id) REFERENCES card_points (card_point_id),
  CONSTRAINT fk_cashouts_account FOREIGN KEY (account_id)    REFERENCES accounts (account_id)
) COMMENT='포인트 현금화';

-- [선택] 알림 (결제일, 잔액 부족, 실적 달성, 연회비, 미사용 카드, 발급 진행, 카드 상태, 포인트 소멸)
CREATE TABLE notifications (
  notification_id  BIGINT        NOT NULL AUTO_INCREMENT,
  user_id          BIGINT        NOT NULL,
  user_card_id     BIGINT        NULL,
  type             ENUM('PAYMENT_DUE','LOW_BALANCE','PERFORMANCE','ANNUAL_FEE','UNUSED_CARD',
                        'APPLICATION','CARD_STATUS','TRANSACTION','POINT_EXPIRING') NOT NULL,
  title            VARCHAR(100)  NOT NULL,
  body             VARCHAR(500)  NOT NULL,
  is_read          BOOLEAN       NOT NULL DEFAULT FALSE,
  sent_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (notification_id),
  KEY idx_notifications_user_sent (user_id, sent_at),
  CONSTRAINT fk_notifications_user FOREIGN KEY (user_id)      REFERENCES users (user_id),
  CONSTRAINT fk_notifications_card FOREIGN KEY (user_card_id) REFERENCES user_cards (user_card_id)
) COMMENT='알림';

-- ---------------------------------------------------------------------
-- 8. 마이데이터 연동 (Mock 카드사 API)
-- ---------------------------------------------------------------------

-- [필수] 카드사별 마이데이터 연동 동의와 토큰
CREATE TABLE mydata_consents (
  consent_id         BIGINT        NOT NULL AUTO_INCREMENT,
  user_id            BIGINT        NOT NULL,
  company_id         INT           NOT NULL,
  access_token_enc   VARCHAR(512)  NOT NULL COMMENT '암호화 저장',
  refresh_token_enc  VARCHAR(512)  NULL,
  scope              VARCHAR(255)  NOT NULL COMMENT '예: card.list card.approval card.bill card.point',
  status             ENUM('ACTIVE','EXPIRED','REVOKED') NOT NULL DEFAULT 'ACTIVE',
  consented_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at         DATETIME      NOT NULL,
  last_synced_at     DATETIME      NULL,
  PRIMARY KEY (consent_id),
  UNIQUE KEY uk_consents_user_company (user_id, company_id),
  CONSTRAINT fk_consents_user    FOREIGN KEY (user_id)    REFERENCES users (user_id),
  CONSTRAINT fk_consents_company FOREIGN KEY (company_id) REFERENCES card_companies (company_id)
) COMMENT='마이데이터 연동 동의';

-- [선택] 동기화 이력 (API별 호출 결과, 실패 원인 추적)
CREATE TABLE mydata_sync_logs (
  sync_id        BIGINT        NOT NULL AUTO_INCREMENT,
  consent_id     BIGINT        NOT NULL,
  api_type       ENUM('CARDS','APPROVALS','BILLS','POINTS') NOT NULL,
  started_at     DATETIME      NOT NULL,
  finished_at    DATETIME      NULL,
  result         ENUM('SUCCESS','FAILED') NULL,
  fetched_count  INT           NOT NULL DEFAULT 0,
  error_message  VARCHAR(500)  NULL,
  PRIMARY KEY (sync_id),
  KEY idx_sync_logs_consent (consent_id, started_at),
  CONSTRAINT fk_sync_logs_consent FOREIGN KEY (consent_id) REFERENCES mydata_consents (consent_id)
) COMMENT='마이데이터 동기화 이력';
