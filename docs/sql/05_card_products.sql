SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 5. 카드 — 상품·발급·보유 (파트 A 1-2·1-3·1-7)
-- ---------------------------------------------------------------------

-- 카드사
CREATE TABLE card_companies (
  id               VARCHAR(40)   NOT NULL,
  code             VARCHAR(10)   NOT NULL,
  name             VARCHAR(30)   NOT NULL,
  logo_url         VARCHAR(255)  NULL,
  customer_center  VARCHAR(20)   NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_card_companies_code UNIQUE (code)
);
COMMENT ON TABLE card_companies IS '카드사';
COMMENT ON COLUMN card_companies.code IS '예: SHINHAN, HYUNDAI, TOSSBANK';

-- 업종/혜택 카테고리 (가맹점 분류와 혜택 대상 분류에 공통 사용)
CREATE TABLE categories (
  id         VARCHAR(40)  NOT NULL,
  parent_id  VARCHAR(40)  NULL,
  code       VARCHAR(30)  NOT NULL,
  name       VARCHAR(30)  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_categories_code UNIQUE (code),
  CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories (id)
);
COMMENT ON TABLE categories IS '업종/혜택 카테고리';
COMMENT ON COLUMN categories.parent_id IS '상위 분류 (예: 교통 > 대중교통)';
COMMENT ON COLUMN categories.code IS '예: TRANSPORT, CONVENIENCE, TELECOM';

-- 카드 상품
CREATE TABLE card_products (
  id                   VARCHAR(40)   NOT NULL,
  card_company_id      VARCHAR(40)   NOT NULL,
  name                 VARCHAR(100)  NOT NULL,
  card_type            VARCHAR(30)   NOT NULL,
  brand                VARCHAR(30)   NOT NULL,
  annual_fee_domestic  INT           NOT NULL DEFAULT 0,
  annual_fee_overseas  INT           NOT NULL DEFAULT 0,
  min_age              SMALLINT      NOT NULL DEFAULT 19,
  image_url            VARCHAR(255)  NULL,
  summary              VARCHAR(255)  NULL,
  is_active            BOOLEAN       NOT NULL DEFAULT TRUE,
  released_at          DATE          NULL,
  created_at           TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_card_products_company FOREIGN KEY (card_company_id) REFERENCES card_companies (id),
  CONSTRAINT ck_card_products_card_type CHECK (card_type IN ('CREDIT', 'CHECK')),
  CONSTRAINT ck_card_products_brand CHECK (brand IN ('VISA', 'MASTER', 'AMEX', 'JCB', 'UNIONPAY', 'LOCAL'))
);
CREATE INDEX idx_card_products_company ON card_products (card_company_id);
CREATE INDEX idx_card_products_type_active ON card_products (card_type, is_active);
COMMENT ON TABLE card_products IS '카드 상품';
COMMENT ON COLUMN card_products.annual_fee_domestic IS '국내전용 연회비';
COMMENT ON COLUMN card_products.annual_fee_overseas IS '해외겸용 연회비';
COMMENT ON COLUMN card_products.min_age IS '발급 가능 최소 나이';
COMMENT ON COLUMN card_products.summary IS '한 줄 혜택 요약';
COMMENT ON COLUMN card_products.is_active IS 'FALSE = 단종 (보유는 가능, 신규 발급 불가)';

-- 전월 실적 구간
CREATE TABLE card_performance_tiers (
  id               VARCHAR(40)  NOT NULL,
  card_product_id  VARCHAR(40)  NOT NULL,
  tier_level       SMALLINT     NOT NULL,
  min_spend        BIGINT       NOT NULL,
  max_spend        BIGINT       NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_tiers_product_level UNIQUE (card_product_id, tier_level),
  CONSTRAINT fk_tiers_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
);
COMMENT ON TABLE card_performance_tiers IS '전월 실적 구간';
COMMENT ON COLUMN card_performance_tiers.tier_level IS '1부터, 클수록 높은 구간';
COMMENT ON COLUMN card_performance_tiers.min_spend IS '구간 진입 전월 실적(이상)';
COMMENT ON COLUMN card_performance_tiers.max_spend IS '구간 상한(미만), NULL = 상한 없음';

-- 카드 혜택 규칙
CREATE TABLE card_benefits (
  id                    VARCHAR(40)    NOT NULL,
  card_product_id       VARCHAR(40)    NOT NULL,
  tier_id               VARCHAR(40)    NULL,
  category_id           VARCHAR(40)    NOT NULL,
  benefit_type          VARCHAR(30)    NOT NULL,
  value_type            VARCHAR(30)    NOT NULL,
  benefit_value         DECIMAL(10,2)  NOT NULL,
  min_payment_amount    INT            NULL,
  monthly_limit_amount  INT            NULL,
  monthly_limit_count   INT            NULL,
  is_instant            BOOLEAN        NOT NULL DEFAULT FALSE,
  description           VARCHAR(255)   NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_benefits_product FOREIGN KEY (card_product_id) REFERENCES card_products (id),
  CONSTRAINT fk_benefits_tier FOREIGN KEY (tier_id) REFERENCES card_performance_tiers (id),
  CONSTRAINT fk_benefits_category FOREIGN KEY (category_id) REFERENCES categories (id),
  CONSTRAINT ck_card_benefits_benefit_type CHECK (benefit_type IN ('DISCOUNT', 'CASHBACK', 'POINT', 'MILEAGE', 'FEE_WAIVER')),
  CONSTRAINT ck_card_benefits_value_type CHECK (value_type IN ('PERCENT', 'FIXED'))
);
CREATE INDEX idx_benefits_product ON card_benefits (card_product_id);
CREATE INDEX idx_benefits_category ON card_benefits (category_id);
COMMENT ON TABLE card_benefits IS '카드 혜택 규칙';
COMMENT ON COLUMN card_benefits.tier_id IS 'NULL = 실적 조건 없음';
COMMENT ON COLUMN card_benefits.benefit_value IS 'PERCENT면 %, FIXED면 원';
COMMENT ON COLUMN card_benefits.min_payment_amount IS '건당 최소 결제 금액';
COMMENT ON COLUMN card_benefits.monthly_limit_amount IS '월 혜택 한도(원)';
COMMENT ON COLUMN card_benefits.monthly_limit_count IS '월 적용 횟수 한도';
COMMENT ON COLUMN card_benefits.is_instant IS '즉시 캐시백 여부';

-- 약관 (회원 파트 1장, card_product_id NULL = 공통 약관)
CREATE TABLE terms (
  id               VARCHAR(40)   NOT NULL,
  version          VARCHAR(10)   NOT NULL,
  title            VARCHAR(100)  NOT NULL,
  required         BOOLEAN       NOT NULL DEFAULT TRUE,
  effective_at     TIMESTAMP(0)  NOT NULL,
  card_product_id  VARCHAR(40)   NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_terms_card_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
);
CREATE INDEX idx_terms_card_product ON terms (card_product_id);
COMMENT ON TABLE terms IS '약관';
COMMENT ON COLUMN terms.card_product_id IS '카드 약관이면';

-- 약관 동의 (회원 파트 1장)
CREATE TABLE user_consents (
  id           VARCHAR(40)   NOT NULL,
  user_id      VARCHAR(40)   NOT NULL,
  terms_id     VARCHAR(40)   NOT NULL,
  version      VARCHAR(10)   NOT NULL,
  agreed       BOOLEAN       NOT NULL,
  recorded_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_user_consents_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_user_consents_terms FOREIGN KEY (terms_id) REFERENCES terms (id)
);
CREATE INDEX idx_user_consents_user ON user_consents (user_id);
CREATE INDEX idx_user_consents_terms ON user_consents (terms_id);
COMMENT ON TABLE user_consents IS '약관 동의';
COMMENT ON COLUMN user_consents.version IS '동의한 약관 버전';

-- 발급 프로모션
CREATE TABLE promotions (
  id                   VARCHAR(40)   NOT NULL,
  card_product_id      VARCHAR(40)   NOT NULL,
  title                VARCHAR(100)  NOT NULL,
  reward_amount        INT           NOT NULL,
  min_spend_condition  BIGINT        NULL,
  condition_desc       VARCHAR(500)  NULL,
  starts_at            TIMESTAMP(0)  NOT NULL,
  ends_at              TIMESTAMP(0)  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_promotions_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
);
CREATE INDEX idx_promotions_product_period ON promotions (card_product_id, starts_at, ends_at);
COMMENT ON TABLE promotions IS '발급 프로모션';
COMMENT ON COLUMN promotions.reward_amount IS '지급 리워드(원)';
COMMENT ON COLUMN promotions.min_spend_condition IS '리워드 조건: 발급 후 N원 이상 사용';

-- 카드 추천 결과 (6장 그림, card_applications 가 참조하므로 먼저 만듦)
CREATE TABLE card_recommendations (
  id                        VARCHAR(40)   NOT NULL,
  user_id                   VARCHAR(40)   NOT NULL,
  card_product_id           VARCHAR(40)   NOT NULL,
  analysis_start            DATE          NOT NULL,
  analysis_end              DATE          NOT NULL,
  expected_monthly_benefit  BIGINT        NOT NULL,
  annual_fee                INT           NOT NULL,
  net_annual_benefit        BIGINT        NOT NULL,
  rank_no                   SMALLINT      NOT NULL,
  reason                    VARCHAR(255)  NULL,
  created_at                TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_recommendations_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_recommendations_product FOREIGN KEY (card_product_id) REFERENCES card_products (id)
);
CREATE INDEX idx_recommendations_user_created ON card_recommendations (user_id, created_at);
COMMENT ON TABLE card_recommendations IS '카드 추천';
COMMENT ON COLUMN card_recommendations.analysis_start IS '분석한 소비 기간 시작';
COMMENT ON COLUMN card_recommendations.expected_monthly_benefit IS '월 예상 혜택';
COMMENT ON COLUMN card_recommendations.net_annual_benefit IS '연 예상 혜택 - 연회비';

-- 추천 근거 (업종별)
CREATE TABLE card_recommendation_details (
  recommendation_id  VARCHAR(40)  NOT NULL,
  category_id        VARCHAR(40)  NOT NULL,
  spend_amount       BIGINT       NOT NULL,
  benefit_amount     BIGINT       NOT NULL,
  PRIMARY KEY (recommendation_id, category_id),
  CONSTRAINT fk_rec_details_recommendation FOREIGN KEY (recommendation_id) REFERENCES card_recommendations (id),
  CONSTRAINT fk_rec_details_category FOREIGN KEY (category_id) REFERENCES categories (id)
);
CREATE INDEX idx_rec_details_category ON card_recommendation_details (category_id);
COMMENT ON TABLE card_recommendation_details IS '추천 근거';
COMMENT ON COLUMN card_recommendation_details.spend_amount IS '분석 기간 월평균 지출';
COMMENT ON COLUMN card_recommendation_details.benefit_amount IS '월 예상 혜택 (한도 적용 후)';

-- 발급 신청
CREATE TABLE card_applications (
  id                     VARCHAR(40)   NOT NULL,
  user_id                VARCHAR(40)   NOT NULL,
  card_product_id        VARCHAR(40)   NOT NULL,
  promotion_id           VARCHAR(40)   NULL,
  recommendation_id      VARCHAR(40)   NULL,
  step_up_challenge_id   VARCHAR(40)   NULL,
  status                 VARCHAR(30)   NOT NULL DEFAULT 'APPLIED',
  job_type               VARCHAR(30)   NULL,
  annual_income          BIGINT        NULL,
  linked_account_id      VARCHAR(40)   NULL,
  payment_day            SMALLINT      NULL,
  approved_credit_limit  BIGINT        NULL,
  delivery_address       VARCHAR(255)  NOT NULL,
  tracking_no            VARCHAR(50)   NULL,
  reject_reason          VARCHAR(30)   NULL,
  applied_at             TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at             TIMESTAMP(0)  NULL,
  updated_at             TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_applications_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_applications_product FOREIGN KEY (card_product_id) REFERENCES card_products (id),
  CONSTRAINT fk_applications_promotion FOREIGN KEY (promotion_id) REFERENCES promotions (id),
  CONSTRAINT fk_applications_recommendation FOREIGN KEY (recommendation_id) REFERENCES card_recommendations (id),
  CONSTRAINT fk_applications_step_up FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id),
  CONSTRAINT fk_applications_account FOREIGN KEY (linked_account_id) REFERENCES accounts (id),
  CONSTRAINT ck_card_applications_status CHECK (status IN ('APPLIED', 'REVIEWING', 'APPROVED', 'REJECTED', 'SHIPPING', 'DELIVERED', 'ACTIVATED', 'CANCELED')),
  CONSTRAINT ck_card_applications_reject_reason CHECK (reject_reason IN ('AGE', 'NO_INCOME', 'DUPLICATE'))
);
CREATE INDEX idx_applications_user ON card_applications (user_id);
CREATE INDEX idx_applications_product_applied ON card_applications (card_product_id, applied_at);
COMMENT ON INDEX idx_applications_product_applied IS '발급 순위 집계용';
CREATE TRIGGER trg_card_applications_updated_at BEFORE UPDATE ON card_applications
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
COMMENT ON TABLE card_applications IS '카드 발급 신청';
COMMENT ON COLUMN card_applications.recommendation_id IS '추천으로 신청한 경우';
COMMENT ON COLUMN card_applications.step_up_challenge_id IS '신청 때 본인 확인';
COMMENT ON COLUMN card_applications.job_type IS '직장인/자영업/학생 등 (신용카드 심사용)';
COMMENT ON COLUMN card_applications.linked_account_id IS '연결 계좌';
COMMENT ON COLUMN card_applications.payment_day IS '희망 결제일 (신용카드)';
COMMENT ON COLUMN card_applications.approved_credit_limit IS '심사 승인 한도 (신용카드)';
COMMENT ON COLUMN card_applications.decided_at IS '승인/거절 시각';

-- 발급 신청 상태 이력
CREATE TABLE application_status_histories (
  id              VARCHAR(40)   NOT NULL,
  application_id  VARCHAR(40)   NOT NULL,
  from_status     VARCHAR(20)   NULL,
  to_status       VARCHAR(20)   NOT NULL,
  memo            VARCHAR(255)  NULL,
  changed_at      TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_app_histories_application FOREIGN KEY (application_id) REFERENCES card_applications (id)
);
CREATE INDEX idx_app_histories_application ON application_status_histories (application_id, changed_at);
COMMENT ON TABLE application_status_histories IS '발급 신청 상태 이력';

-- 신청별 약관 동의
CREATE TABLE application_term_agreements (
  application_id  VARCHAR(40)   NOT NULL,
  terms_id        VARCHAR(40)   NOT NULL,
  agreed          BOOLEAN       NOT NULL,
  agreed_at       TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (application_id, terms_id),
  CONSTRAINT fk_agreements_application FOREIGN KEY (application_id) REFERENCES card_applications (id),
  CONSTRAINT fk_agreements_terms FOREIGN KEY (terms_id) REFERENCES terms (id)
);
CREATE INDEX idx_agreements_terms ON application_term_agreements (terms_id);
COMMENT ON TABLE application_term_agreements IS '신청 약관 동의';

-- 보유 카드 (토스 경유 발급 + 마이데이터 연동 카드)
CREATE TABLE user_cards (
  id                    VARCHAR(40)   NOT NULL,
  user_id               VARCHAR(40)   NOT NULL,
  card_product_id       VARCHAR(40)   NOT NULL,
  application_id        VARCHAR(40)   NULL,
  reissued_from_id      VARCHAR(40)   NULL,
  source                VARCHAR(30)   NOT NULL,
  org_card_id           VARCHAR(64)   NULL,
  nickname              VARCHAR(30)   NULL,
  card_number_masked    VARCHAR(25)   NOT NULL,
  last4                 CHAR(4)       NOT NULL,
  expires_at            DATE          NOT NULL,
  linked_account_id     VARCHAR(40)   NULL,
  payment_day           SMALLINT      NULL,
  credit_limit          BIGINT        NULL,
  status                VARCHAR(30)   NOT NULL DEFAULT 'ACTIVE',
  annual_fee_amount     INT           NOT NULL DEFAULT 0,
  next_annual_fee_date  DATE          NULL,
  last_used_at          TIMESTAMP(0)  NULL,
  issued_at             TIMESTAMP(0)  NOT NULL,
  activated_at          TIMESTAMP(0)  NULL,
  terminated_at         TIMESTAMP(0)  NULL,
  created_at            TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uk_user_cards_application UNIQUE (application_id),
  CONSTRAINT uk_user_cards_org UNIQUE (user_id, org_card_id),
  CONSTRAINT fk_user_cards_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_user_cards_product FOREIGN KEY (card_product_id) REFERENCES card_products (id),
  CONSTRAINT fk_user_cards_application FOREIGN KEY (application_id) REFERENCES card_applications (id),
  CONSTRAINT fk_user_cards_reissued FOREIGN KEY (reissued_from_id) REFERENCES user_cards (id),
  CONSTRAINT fk_user_cards_account FOREIGN KEY (linked_account_id) REFERENCES accounts (id),
  CONSTRAINT ck_user_cards_source CHECK (source IN ('TOSS_ISSUED', 'MYDATA')),
  CONSTRAINT ck_user_cards_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'LOST', 'EXPIRED', 'TERMINATED'))
);
CREATE INDEX idx_user_cards_user_status ON user_cards (user_id, status);
CREATE INDEX idx_user_cards_account ON user_cards (linked_account_id);
COMMENT ON TABLE user_cards IS '보유 카드';
COMMENT ON COLUMN user_cards.application_id IS '토스 경유 발급인 경우 원 신청';
COMMENT ON COLUMN user_cards.reissued_from_id IS '분실/만료 재발급 시 이전 카드';
COMMENT ON COLUMN user_cards.org_card_id IS '마이데이터 카드사 측 card_id (동기화 upsert 키)';
COMMENT ON COLUMN user_cards.card_number_masked IS '예: 5310-****-****-1234';
COMMENT ON COLUMN user_cards.expires_at IS '유효기간 (해당 월 말일)';
COMMENT ON COLUMN user_cards.linked_account_id IS '체크카드 출금 계좌 / 신용카드 결제 계좌';
COMMENT ON COLUMN user_cards.payment_day IS '결제일 1~31, 체크카드는 NULL';
COMMENT ON COLUMN user_cards.credit_limit IS '신용카드만';
COMMENT ON COLUMN user_cards.annual_fee_amount IS '실제 적용 연회비';
COMMENT ON COLUMN user_cards.next_annual_fee_date IS '다음 연회비 청구 예정일';
COMMENT ON COLUMN user_cards.last_used_at IS '마지막 거래 시각 (배치 갱신)';

-- 카드 관리 설정 (1 : 0..1)
CREATE TABLE user_card_settings (
  user_card_id              VARCHAR(40)   NOT NULL,
  overseas_payment_blocked  BOOLEAN       NOT NULL DEFAULT FALSE,
  online_payment_blocked    BOOLEAN       NOT NULL DEFAULT FALSE,
  daily_limit               BIGINT        NULL,
  monthly_limit             BIGINT        NULL,
  payment_alert_enabled     BOOLEAN       NOT NULL DEFAULT TRUE,
  updated_at                TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_card_id),
  CONSTRAINT fk_card_settings_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
);
CREATE TRIGGER trg_user_card_settings_updated_at BEFORE UPDATE ON user_card_settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
COMMENT ON TABLE user_card_settings IS '카드 관리 설정';

-- 카드 상태 변경 이력
CREATE TABLE user_card_status_histories (
  id            VARCHAR(40)   NOT NULL,
  user_card_id  VARCHAR(40)   NOT NULL,
  from_status   VARCHAR(20)   NULL,
  to_status     VARCHAR(20)   NOT NULL,
  reason        VARCHAR(255)  NULL,
  changed_at    TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_card_histories_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id)
);
CREATE INDEX idx_card_histories_card ON user_card_status_histories (user_card_id, changed_at);
COMMENT ON TABLE user_card_status_histories IS '카드 상태 이력';

-- 카드 관리 기록 (결제 차단, 한도, 비밀번호 — 비밀번호 값은 저장하지 않음)
CREATE TABLE card_management_logs (
  id            VARCHAR(40)   NOT NULL,
  user_card_id  VARCHAR(40)   NOT NULL,
  action_type   VARCHAR(30)   NOT NULL,
  before_value  VARCHAR(50)   NULL,
  after_value   VARCHAR(50)   NULL,
  result        VARCHAR(30)   NOT NULL,
  requested_at  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_mgmt_logs_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT ck_card_management_logs_action_type CHECK (action_type IN ('BLOCK_OVERSEAS', 'UNBLOCK_OVERSEAS', 'BLOCK_ONLINE', 'UNBLOCK_ONLINE', 'LIMIT_CHANGE', 'PIN_CHANGE')),
  CONSTRAINT ck_card_management_logs_result CHECK (result IN ('SUCCESS', 'FAILED'))
);
CREATE INDEX idx_mgmt_logs_card ON card_management_logs (user_card_id, requested_at);
COMMENT ON TABLE card_management_logs IS '카드 관리 기록';
COMMENT ON COLUMN card_management_logs.before_value IS 'PIN_CHANGE는 값 저장 금지';

-- 카드 해지 (해지 전 확인 정보를 스냅샷으로 저장)
CREATE TABLE card_terminations (
  id                            VARCHAR(40)   NOT NULL,
  user_card_id                  VARCHAR(40)   NOT NULL,
  step_up_challenge_id          VARCHAR(40)   NULL,
  status                        VARCHAR(30)   NOT NULL DEFAULT 'REQUESTED',
  reason_code                   VARCHAR(30)   NOT NULL,
  reason_detail                 VARCHAR(255)  NULL,
  unpaid_amount                 BIGINT        NOT NULL DEFAULT 0,
  remaining_installment_amount  BIGINT        NOT NULL DEFAULT 0,
  linked_recurring_count        INT           NOT NULL DEFAULT 0,
  forfeited_points              BIGINT        NOT NULL DEFAULT 0,
  refunded_annual_fee           INT           NOT NULL DEFAULT 0,
  requested_at                  TIMESTAMP(0)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at                  TIMESTAMP(0)  NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_terminations_card FOREIGN KEY (user_card_id) REFERENCES user_cards (id),
  CONSTRAINT fk_terminations_step_up FOREIGN KEY (step_up_challenge_id) REFERENCES step_up_challenges (id),
  CONSTRAINT ck_card_terminations_status CHECK (status IN ('REQUESTED', 'COMPLETED', 'REJECTED', 'CANCELED')),
  CONSTRAINT ck_card_terminations_reason_code CHECK (reason_code IN ('LOW_BENEFIT', 'HIGH_FEE', 'NOT_USING', 'SWITCH_CARD', 'OTHER'))
);
CREATE INDEX idx_terminations_card ON card_terminations (user_card_id);
COMMENT ON TABLE card_terminations IS '카드 해지';
COMMENT ON COLUMN card_terminations.step_up_challenge_id IS '해지 요청 본인 확인';
COMMENT ON COLUMN card_terminations.unpaid_amount IS '미결제 금액';
COMMENT ON COLUMN card_terminations.remaining_installment_amount IS '남은 할부 원금';
COMMENT ON COLUMN card_terminations.linked_recurring_count IS '연결된 자동결제 건수';
COMMENT ON COLUMN card_terminations.forfeited_points IS '소멸 예정 포인트';
COMMENT ON COLUMN card_terminations.refunded_annual_fee IS '연회비 일할 환급액';
