# 테이블 관계도 (ERD)

2026-11-04 · 기준: `docs/기획서.md` — Part 1 6.3·Part 2 8.4(컬럼 사전), Part 3 6장, Part 4·5(카드·거래), Part 6 C-5(이름 규칙). 카드 테이블의 칸은 팀 브랜치 `docs/schema.sql`을 C-5 규칙으로 바꾼 이름입니다.

**읽는 법**

- 테이블이 약 60개라 한 장에 그리지 않고 **파트별 그림 6장 + 전체 연결 그림 1장**으로 나눴습니다. 다른 파트 테이블은 그림 안에서 칸 없이 이름만 나옵니다.
- `PK` = 그 테이블의 고유 번호, `FK` = 다른 테이블을 가리키는 칸. 선 끝 모양: `||` 꼭 1개, `o|` 0 또는 1개, `o{` 0개 이상.
- ID는 문자열(`user_001` 등), 금액은 원 단위 정수, 시각은 `+09:00`, 우리가 만든 빈 칸은 `null`입니다(C-5). 카드 테이블과 일부 거래 테이블(`scheduled_transfers`)은 주요 칸만 적었습니다. 전체 칸은 `docs/기획서.md`의 각 Part에 있습니다.
- 그림에는 **실제 참조(FK)만** 그렸습니다. "카드 대금 → 거래 원장 기록"처럼 API로 이어지는 연결은 맨 아래 표에 있습니다.

---

## 0. 전체 연결 (파트 사이 주요 관계)

```mermaid
erDiagram
    users ||--o{ accounts : "소유"
    accounts ||--|| account_balances : "잔액(거래 파트)"
    accounts ||--o{ transactions : "원장"
    accounts ||--o{ transfers : "출금 계좌"
    users ||--o{ step_up_challenges : "본인 확인"
    step_up_challenges |o--o{ transfers : "이체 확인"
    step_up_challenges |o--o{ card_applications : "발급 확인"
    users ||--o{ subscriptions : "가입"
    products ||--o{ subscriptions : "상품"
    accounts ||--o{ subscriptions : "출금 계좌"
    users ||--o{ user_cards : "보유"
    accounts |o--o{ user_cards : "결제·출금 계좌"
    card_products ||--o{ user_cards : "카드 상품"
    card_products |o--o{ terms : "카드 약관"
    users ||--o{ user_consents : "동의"
    terms ||--o{ user_consents : "약관"
    users ||--o{ notifications : "받음"
    accounts |o--o{ notifications : "계좌 알림"
    user_cards |o--o{ notifications : "카드 알림"
    accounts ||--o{ point_cashouts : "포인트 입금 계좌"
```

---

## 1. 회원·인증 (기획서 Part 1 6장)

```mermaid
erDiagram
    users ||--o{ auth_identities : "로그인 수단"
    users ||--o| local_credentials : "비밀번호"
    users ||--o{ sessions : "로그인"
    users ||--o{ password_reset_tokens : "재설정"
    users ||--o| pin_credentials : "PIN"
    users ||--o{ step_up_challenges : "본인 확인"
    sessions ||--o{ step_up_challenges : "그 세션에서"
    users ||--o{ user_consents : "동의"
    terms ||--o{ user_consents : "약관"
    users ||--o{ auth_audit_logs : "기록"
    users ||--o{ withdrawal_checks : "탈퇴 점검"

    users {
        string id PK
        string username UK
        string name
        string email
        datetime email_verified_at
        date birth_date "YYYY-MM-DD"
        string gender "M / F"
        int payday "1~31, 빈 값 가능"
        string status "ACTIVE / PENDING_VERIFICATION / RESTRICTED / WITHDRAWN"
        datetime created_at
        datetime withdrawn_at
    }
    auth_identities {
        string id PK
        string user_id FK
        string provider "LOCAL / GOOGLE"
        string provider_subject
        datetime linked_at
    }
    local_credentials {
        string user_id PK, FK
        string password_hash
        datetime password_updated_at
        int failed_attempts "로그인·본인 확인 실패"
        datetime locked_until
    }
    email_verifications {
        string id PK
        string email
        string purpose
        string challenge_digest
        datetime expires_at
        int attempt_count
        datetime used_at
    }
    password_reset_tokens {
        string id PK
        string user_id FK
        string token_digest
        datetime expires_at
        datetime used_at
    }
    sessions {
        string id PK
        string user_id FK
        datetime created_at
        datetime last_seen_at
        datetime expires_at
        datetime revoked_at
    }
    terms {
        string id PK
        string version
        string title
        bool required
        string content_url "본문 위치(고친 md 경로·URL)"
        datetime effective_at
        string card_product_id FK "카드 약관이면"
    }
    user_consents {
        string id PK
        string user_id FK
        string terms_id FK
        string version
        bool agreed
        datetime recorded_at
    }
    pin_credentials {
        string user_id PK, FK
        string pin_hash
        datetime enabled_at
        datetime changed_at
        int failed_attempts
        datetime locked_until
    }
    auth_audit_logs {
        string id PK
        string user_id FK
        string event_type
        datetime occurred_at
        string outcome
        string request_id
    }
    step_up_challenges {
        string id PK
        string user_id FK
        string action "TRANSFER / SCHEDULED_TRANSFER / CARD_APPLICATION / CARD_TERMINATION / CARD_MANAGEMENT / SUBSCRIPTION / ACCOUNT_STATUS_CHANGE / WITHDRAWAL / PROFILE_CHANGE"
        string session_id FK
        datetime expires_at
        datetime consumed_at
    }
    withdrawal_checks {
        string id PK
        string user_id FK
        string status "IN_PROGRESS / COMPLETED / CANCELED"
        datetime started_at
        datetime balance_verified_at
        datetime data_review_confirmed_at
        string data_review_version
        datetime linked_services_confirmed_at
        datetime completed_at
    }
```

`email_verifications`는 가입 전 이메일로 인증하므로 회원과 선이 없습니다.

---

## 2. 계좌 (기획서 Part 2 8장)

```mermaid
erDiagram
    users ||--o{ accounts : "소유"
    accounts ||--|| account_balance_view : "잔액 읽기"
    accounts ||--o{ account_activity_logs : "관리 기록"
    users ||--o{ notification_preferences : "설정"
    accounts ||--o{ notification_preferences : "계좌별"
    users ||--o{ notifications : "받음"
    accounts |o--o{ notifications : "계좌 알림"
    accounts ||--o| account_inactivity : "장기 미사용"
    accounts ||--o{ document_issuance_logs : "증명서"

    accounts {
        string id PK
        string user_id FK
        string resAccount UK "계좌번호(숫자만)"
        string resAccountDisplay "110-00-000001"
        string resAccountName "상품명"
        string account_type "CHECKING / SAVINGS"
        string lifecycle_status "ACTIVE / SUSPENDED / CLOSED"
        string resAccountNickName
        bool is_favorite
        string resAccountStartDate "YYYYMMDD"
        string closed_at "YYYYMMDD, 해지 전 null"
        int version
    }
    account_balance_view {
        string account_id PK, FK
        string resAccountCurrency
        bigint resAccountBalance
        string balance_as_of "YYYYMMDDHHmmss"
    }
    account_activity_logs {
        string id PK
        string account_id FK
        string actor_id
        string action
        datetime occurred_at
        string metadata
    }
    notification_preferences {
        string user_id PK, FK
        string account_id PK, FK
        bool enabled
        bool deposit_enabled
        bool withdrawal_enabled
        bigint minimum_amount
        string channel
    }
    notifications {
        string id PK
        string user_id FK
        string account_id FK "카드 알림이면 빈 값"
        string user_card_id FK "카드 알림이면"
        string event_id "원인 이벤트, (event_id, user_id, type) 중복 금지"
        string type "TRANSACTION / PAYMENT_DUE / MATURITY ..."
        string title
        string body
        string status
        datetime read_at
        datetime created_at
    }
    account_inactivity {
        string account_id PK, FK
        datetime last_activity_at
        bool inactivity_flag
        datetime flagged_at
    }
    document_issuance_logs {
        string id PK
        string account_id FK
        string document_type
        string requested_by
        datetime issued_at
        string status
    }
```

`account_balance_view`는 표가 아니라 **보기(view)**입니다. 원본은 거래 파트의 `account_balances`(3번 그림)입니다.

---

## 3. 거래 (기획서 Part 5 15장)

```mermaid
erDiagram
    accounts ||--|| account_balances : "잔액"
    accounts ||--o{ transactions : "원장"
    transfers |o--o{ transactions : "이체면 출금·입금 2건"
    users ||--o{ transfers : "요청"
    accounts ||--o{ transfers : "출금 계좌"
    scheduled_transfers |o--o{ transfers : "예약 실행분"
    step_up_challenges |o--o{ transfers : "본인 확인"
    users ||--o{ scheduled_transfers : "등록"
    accounts ||--o{ scheduled_transfers : "출금 계좌"
    step_up_challenges |o--o{ scheduled_transfers : "등록 때 확인"
    users ||--o{ favorite_accounts : "자주 쓰는 계좌"
    accounts ||--o| transfer_limits : "한도"

    account_balances {
        string account_id PK, FK
        string currency "KRW"
        bigint balance
        datetime updated_at
    }
    transactions {
        string id PK "tx_0001"
        string account_id FK
        string type "TRANSFER_OUT / TRANSFER_IN / CARD_PAYMENT / POINT_CASHOUT / SUBSCRIPTION_PAYMENT / SUBSCRIPTION_PAYOUT"
        bigint amount
        bigint fee
        bigint balance_after
        string transfer_id FK "이체가 아니면 빈 값"
        string counterpart_bank
        string counterpart_account_no
        string display_name
        datetime created_at
    }
    transfers {
        string id PK "trf_0001"
        string user_id FK
        string from_account_id FK
        string to_bank
        string to_account_no
        string to_holder_name
        bigint amount
        bigint fee
        string my_display_name
        string their_display_name
        string status "PENDING / SUCCESS / FAILED"
        string failure_reason
        string channel "APP / SCHEDULED / AUTO"
        string scheduled_transfer_id FK
        string step_up_challenge_id FK
        string idempotency_key UK
        datetime requested_at
        datetime completed_at
    }
    scheduled_transfers {
        string id PK
        string user_id FK
        string from_account_id FK
        string to_bank
        string to_account_no
        string to_holder_name
        bigint amount
        string type "ONCE / MONTHLY"
        datetime execute_at
        int day_of_month "1~28, 99=말일"
        string start_ym
        string end_ym
        datetime next_run_at
        string status
        string step_up_challenge_id FK
        datetime created_at
    }
    favorite_accounts {
        string id PK
        string user_id FK
        string bank
        string account_no
        string holder_name
        string nickname
        int sort_order
    }
    transfer_limits {
        string account_id PK, FK
        bigint per_transfer_limit
        bigint daily_limit
        datetime updated_at
    }
    external_accounts {
        string id PK
        string bank
        string account_no
        string holder_name
    }
```

`external_accounts`는 가상 타행 예금주 조회용 시드(11장)라 다른 테이블과 선이 없습니다(계좌번호로 찾음). 칸은 11장 설명에서 정한 최소 칸입니다.

---

## 4. 예금·적금 상품 (기획서 Part 3 6장)

```mermaid
erDiagram
    products ||--o{ product_rates : "기간별 금리"
    products ||--o{ product_rules : "가입 조건"
    products ||--o{ product_documents : "RAG 문서"
    products ||--o{ subscriptions : "가입"
    users ||--o{ subscriptions : "가입자"
    accounts ||--o{ subscriptions : "출금 계좌"
    subscriptions ||--o{ subscription_payments : "적금 납입"

    products {
        string id PK "prod_001"
        string bank "두린은행"
        string name
        string type "TIME_DEPOSIT / INSTALLMENT_SAVINGS"
        string description
        string status "ON_SALE / STOPPED"
        string source_url
        string verified_at "YYYYMMDD"
    }
    product_rates {
        string id PK
        string product_id FK
        int term_min
        int term_max
        string term_unit "MONTH / DAY"
        string base_rate "연 %"
        string bonus_rate
        string effective_from "YYYYMMDD"
    }
    product_rules {
        string id PK
        string product_id FK
        bigint min_amount
        bigint max_amount
        int min_months
        int max_months
        int max_per_user
        string rules_json
    }
    subscriptions {
        string id PK "sub_001"
        string user_id FK
        string product_id FK
        string source_account_id FK
        bigint principal
        bigint monthly_amount
        string applied_rate
        string start_date "YYYYMMDD"
        string maturity_date "YYYYMMDD"
        string status "ACTIVE / MATURED / TERMINATED"
        string closed_at "YYYYMMDD, 진행 중 null"
        string idempotency_key UK "중복 가입 방지"
    }
    subscription_payments {
        string id PK
        string subscription_id FK
        bigint paid_amount
        string paid_at "YYYYMMDDHHmmss"
    }
    product_documents {
        string id PK
        string product_id FK
        string title
        string source_url
        string version_date
    }
```

---

## 5. 카드 — 상품·발급·보유 (기획서 Part 4 1-2·1-3·1-7)

```mermaid
erDiagram
    card_companies ||--o{ card_products : "발급사"
    card_products ||--o{ card_performance_tiers : "실적 구간"
    card_products ||--o{ card_benefits : "혜택"
    card_performance_tiers |o--o{ card_benefits : "구간별"
    categories ||--o{ card_benefits : "대상 업종"
    card_products ||--o{ promotions : "이벤트"
    card_products |o--o{ terms : "카드 약관"
    users ||--o{ card_applications : "신청"
    card_products ||--o{ card_applications : "신청 상품"
    promotions |o--o{ card_applications : "이벤트로"
    accounts |o--o{ card_applications : "연결 계좌"
    step_up_challenges |o--o{ card_applications : "본인 확인"
    card_recommendations |o--o{ card_applications : "추천으로 신청"
    card_applications ||--o{ application_status_histories : "상태 이력"
    card_applications ||--o{ application_term_agreements : "약관 동의"
    terms ||--o{ application_term_agreements : "약관"
    users ||--o{ user_cards : "보유"
    card_products ||--o{ user_cards : "상품"
    card_applications |o--o| user_cards : "발급 결과"
    user_cards |o--o{ user_cards : "재발급 전 카드"
    accounts |o--o{ user_cards : "결제·출금 계좌"
    user_cards ||--o| user_card_settings : "설정"
    user_cards ||--o{ user_card_status_histories : "상태 이력"
    user_cards ||--o{ card_management_logs : "관리 기록"
    user_cards ||--o{ card_terminations : "해지"
    step_up_challenges |o--o{ card_terminations : "본인 확인"

    card_companies {
        string id PK
        string code
        string name
        string logo_url
    }
    card_products {
        string id PK
        string card_company_id FK
        string name
        string card_type "CREDIT / CHECK"
        int annual_fee_domestic
        int annual_fee_overseas
        int min_age
        bool is_active
    }
    card_performance_tiers {
        string id PK
        string card_product_id FK
        int tier_level
        bigint min_spend
        bigint max_spend
    }
    card_benefits {
        string id PK
        string card_product_id FK
        string tier_id FK
        string category_id FK
        string value_type
        decimal benefit_value
        int monthly_limit_amount
    }
    categories {
        string id PK
        string parent_id FK
        string code
        string name
    }
    promotions {
        string id PK
        string card_product_id FK
        string title
        int reward_amount
        datetime starts_at
        datetime ends_at
    }
    card_applications {
        string id PK
        string user_id FK
        string card_product_id FK
        string promotion_id FK
        string recommendation_id FK
        string step_up_challenge_id FK
        string status "APPLIED / REVIEWING / APPROVED / REJECTED / SHIPPING / DELIVERED / ACTIVATED / CANCELED"
        string job_type
        bigint annual_income
        string linked_account_id FK
        int payment_day
        bigint approved_credit_limit "심사 승인 한도(신용)"
        string reject_reason "AGE / NO_INCOME / DUPLICATE"
        datetime applied_at
    }
    application_status_histories {
        string id PK
        string application_id FK
        string from_status
        string to_status
        datetime changed_at
    }
    application_term_agreements {
        string application_id PK, FK
        string terms_id PK, FK
        bool agreed
        datetime agreed_at
    }
    user_cards {
        string id PK
        string user_id FK
        string card_product_id FK
        string application_id FK
        string reissued_from_id FK
        string source "TOSS_ISSUED / MYDATA"
        string card_number_masked
        string linked_account_id FK
        int payment_day
        bigint credit_limit "신용카드만"
        string status "ACTIVE / SUSPENDED / LOST / EXPIRED / TERMINATED"
        datetime issued_at
        datetime terminated_at
    }
    user_card_settings {
        string user_card_id PK, FK
        bool overseas_payment_blocked
        bool online_payment_blocked
        bigint daily_limit
        bigint monthly_limit
        bool payment_alert_enabled
    }
    user_card_status_histories {
        string id PK
        string user_card_id FK
        string from_status
        string to_status
        string reason
        datetime changed_at
    }
    card_management_logs {
        string id PK
        string user_card_id FK
        string action_type
        string before_value
        string after_value
        datetime requested_at
    }
    card_terminations {
        string id PK
        string user_card_id FK
        string step_up_challenge_id FK
        string status "REQUESTED / COMPLETED / REJECTED / CANCELED"
        string reason_code
        bigint unpaid_amount
        bigint remaining_installment_amount
        datetime completed_at
    }
```

---

## 6. 카드 — 이용·청구·분석·포인트 (기획서 Part 4 1-1·1-4~1-6)

```mermaid
erDiagram
    user_cards ||--o{ card_transactions : "승인 내역"
    merchants ||--o{ card_transactions : "가맹점"
    card_benefits |o--o{ card_transactions : "적용 혜택"
    categories ||--o{ merchants : "업종"
    categories |o--o{ categories : "상위 분류"
    card_companies ||--o{ billing_cycle_rules : "결제일 규칙"
    user_cards ||--o{ card_bills : "청구서"
    card_bills ||--o{ card_bill_items : "청구 항목"
    card_transactions ||--o{ card_bill_items : "할부 회차"
    users ||--o{ recurring_payments : "고정지출"
    user_cards ||--o{ recurring_payments : "결제 카드"
    merchants ||--o{ recurring_payments : "가맹점"
    user_cards ||--o{ spending_forecasts : "예측"
    user_cards ||--o{ daily_card_spending : "일별 집계"
    users ||--o{ card_recommendations : "추천"
    card_products ||--o{ card_recommendations : "추천 상품"
    card_recommendations ||--o{ card_recommendation_details : "업종별"
    categories ||--o{ card_recommendation_details : "업종"
    card_products ||--o{ card_issuance_rankings : "순위"
    users ||--o{ card_points : "포인트"
    card_companies ||--o{ card_points : "카드사별"
    card_points ||--o{ point_cashouts : "현금화"
    accounts ||--o{ point_cashouts : "입금 계좌"
    users ||--o{ mydata_consents : "연동 동의"
    card_companies ||--o{ mydata_consents : "카드사"
    mydata_consents ||--o{ mydata_sync_logs : "동기화 기록"

    card_transactions {
        string id PK
        string user_card_id FK
        string merchant_id FK
        string approval_no
        datetime transacted_at
        bigint amount
        int installment_months "0=일시불"
        string status "APPROVED / PARTIAL_CANCELED / CANCELED"
        bigint canceled_amount
        string applied_benefit_id FK
        bool is_performance_counted
    }
    merchants {
        string id PK
        string category_id FK
        string name
        string business_no
    }
    billing_cycle_rules {
        string card_company_id PK, FK
        int payment_day PK
        int start_month_offset
        int start_day
        int end_month_offset
        int end_day
    }
    card_bills {
        string id PK
        string user_card_id FK
        string billing_ym "YYYYMM"
        date usage_start
        date usage_end
        date payment_date
        bigint total_amount
        bigint paid_amount
        string status "SCHEDULED / CONFIRMED / PAID / OVERDUE"
    }
    card_bill_items {
        string id PK
        string bill_id FK
        string card_transaction_id FK
        int installment_seq
        bigint principal_amount
        bigint fee_amount "1차 무이자 0"
    }
    recurring_payments {
        string id PK
        string user_id FK
        string user_card_id FK
        string merchant_id FK
        bigint expected_amount
        int expected_day
        string detected_by "AUTO / USER"
        bool is_active
    }
    spending_forecasts {
        string id PK
        string user_card_id FK
        string billing_ym
        bigint predicted_total
        string model_type "MOVING_AVG / LINEAR / ML"
    }
    daily_card_spending {
        string user_card_id PK, FK
        date spend_date PK
        bigint total_amount
        int tx_count
    }
    card_recommendations {
        string id PK
        string user_id FK
        string card_product_id FK
        bigint net_annual_benefit
        int rank_no
    }
    card_recommendation_details {
        string recommendation_id PK, FK
        string category_id PK, FK
        bigint spend_amount
        bigint benefit_amount
    }
    card_issuance_rankings {
        string id PK
        string period_type
        date period_start
        string segment_age
        string segment_gender
        string card_product_id FK
        int rank_no
        int issue_count
    }
    card_points {
        string id PK
        string user_id FK
        string card_company_id FK
        string point_name
        bigint balance
        bigint expiring_amount
    }
    point_cashouts {
        string id PK
        string card_point_id FK
        string account_id FK
        bigint amount
        string status
        datetime completed_at
    }
    mydata_consents {
        string id PK
        string user_id FK
        string card_company_id FK
        string scope
        string status
        datetime expires_at
    }
    mydata_sync_logs {
        string id PK
        string mydata_consent_id FK
        string api_type
        string result
        datetime started_at
    }
```

---

## 그림에 없는 연결 (API로 이어짐, FK 아님)

| 어디서 | 어디로 | 무엇을 | 근거 |
|---|---|---|---|
| 카드 대금 결제·체크카드 결제 (`card_bills`, `card_transactions`) | `transactions` | `CARD_PAYMENT` 출금 기록 | Part 5 3장·Part 4 1-7 |
| 포인트 현금화 (`point_cashouts`) | `transactions` | `POINT_CASHOUT` 입금 기록 | 1-1-7 |
| 예금·적금 가입·납입 (`subscriptions`, `subscription_payments`) | `transactions` | `SUBSCRIPTION_PAYMENT` 출금 기록 | Part 3 PROD-F08 |
| 중도 해지·만기 (`subscriptions`) | `transactions` | `SUBSCRIPTION_PAYOUT` 입금 기록 | PROD-F10·F11 |
| `transactions` | `notifications` | 거래 확정 이벤트 → 입출금 알림 (`event_id`) | Part 2 10장 |
| 회원 탈퇴 점검 (`withdrawal_checks`) | 계좌·거래·카드·상품 | 남은 잔액(`account-readiness`), 처리중·예약 이체(`transfer-blockers`), 해지 안 된 카드(`card-blockers`), 진행 중 예금·적금(`subscription-blockers`) — 모두 `/internal/users/{userId}/…` | AUTH-F09 |
| 계좌 해지 점검 (`accounts`) | 거래·카드·상품 | 처리중·예약 이체, 연결된 카드(`linked-cards`), 이 계좌가 출금 계좌인 계약 — 모두 `/internal/accounts/{accountId}/…` | ACCT-F05 |
