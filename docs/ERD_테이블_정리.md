# ERD 테이블 정리 (칼럼 설명 포함)

2026-11-04 · 원본: [`ERD (1).md`](<ERD (1).md>) 1~6장 · 테이블 61개

**읽는 법**

- `PK` = 그 테이블의 고유 번호, `UK` = 중복 불가 칸, `FK→테이블` = 그 테이블을 가리키는 칸입니다.
- ID는 문자열(`user_001` 등), 금액은 원 단위 정수, 시각은 `+09:00`, 비어 있는 칸은 `null`입니다.
- 비고의 설명은 대부분 칼럼명과 ERD 원문 주석을 보고 쓴 것입니다. 원본 기획서(`회원_계좌기능_기획서.md`, `거래_카드기능_기획서.md`, `은행_상품_기획안.md`)와는 대조하지 못했습니다. `billing_cycle_rules`는 [FEATURES.md](FEATURES.md)와 맞춰 봤습니다. 확인이 필요한 칼럼은 [맨 아래](#원본-기획서와-맞춰-봐야-할-칼럼)에 모았습니다.
- 카드 테이블과 `scheduled_transfers`는 원문 ERD에도 주요 칸만 있어서, 전체 칸은 각 기획서를 봐야 합니다.

## 목차

1. [회원·인증 (12개)](#1-회원인증-12개)
2. [계좌 (7개)](#2-계좌-7개)
3. [거래 (7개)](#3-거래-7개)
4. [예금·적금 상품 (6개)](#4-예금적금-상품-6개)
5. [카드: 상품·발급·보유 (14개)](#5-카드-상품발급보유-14개)
6. [카드: 이용·청구·분석·포인트 (15개)](#6-카드-이용청구분석포인트-15개)
- [부록: merchants 테이블의 역할](#부록-merchants-테이블의-역할)

---

## 1. 회원·인증 (12개)

### users
회원 기본 정보

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 회원 고유 ID (`user_001`) |
| username | string | UK | 로그인 아이디 (중복 불가) |
| name | string | | 회원 실명 |
| email | string | | 이메일 주소 |
| email_verified_at | datetime | | 이메일 인증을 마친 시각 (미인증이면 null) |
| birth_date | date | | 생년월일 (YYYY-MM-DD) |
| gender | string | | 성별 (M / F) |
| payday | int | | 월급날 (1~31, 입력 안 하면 null) |
| status | string | | 회원 상태: ACTIVE 정상 / PENDING_VERIFICATION 인증 대기 / RESTRICTED 이용 제한 / WITHDRAWN 탈퇴 |
| created_at | datetime | | 가입 시각 |
| withdrawn_at | datetime | | 탈퇴 시각 (탈퇴 전이면 null) |

### auth_identities
회원의 로그인 수단 (자체 로그인·구글 등)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 로그인 수단 고유 ID |
| user_id | string | FK→users | 이 로그인 수단을 가진 회원 |
| provider | string | | 로그인 제공자 (LOCAL 자체 / GOOGLE 구글) |
| provider_subject | string | | 제공자 쪽 사용자 식별값 (구글 계정 고유 ID 등) |
| linked_at | datetime | | 로그인 수단을 연결한 시각 |

### local_credentials
아이디·비밀번호 로그인 정보 (회원당 0~1개)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| user_id | string | PK, FK→users | 회원 ID (회원당 1행) |
| password_hash | string | | 해시한 비밀번호 (원문 저장 안 함) |
| password_updated_at | datetime | | 비밀번호를 마지막으로 바꾼 시각 |
| failed_attempts | int | | 로그인·본인 확인에서 연속으로 실패한 횟수 |
| locked_until | datetime | | 실패가 쌓여 잠긴 경우 잠금이 풀리는 시각 |

### email_verifications
이메일 인증 요청 (가입 전 단계라 회원과 연결 없음)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 인증 요청 고유 ID |
| email | string | | 인증할 이메일 주소 |
| purpose | string | | 인증 목적 (가입, 이메일 변경 등) |
| challenge_digest | string | | 메일로 보낸 인증 코드의 해시값 |
| expires_at | datetime | | 인증 코드 만료 시각 |
| attempt_count | int | | 코드 입력 시도 횟수 |
| used_at | datetime | | 인증에 성공해 코드를 쓴 시각 (미사용이면 null) |

### password_reset_tokens
비밀번호 재설정 토큰

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 토큰 고유 ID |
| user_id | string | FK→users | 재설정을 요청한 회원 |
| token_digest | string | | 재설정 토큰의 해시값 |
| expires_at | datetime | | 토큰 만료 시각 |
| used_at | datetime | | 토큰으로 비밀번호를 바꾼 시각 (미사용이면 null) |

### sessions
로그인 세션

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 세션 고유 ID |
| user_id | string | FK→users | 로그인한 회원 |
| created_at | datetime | | 로그인(세션 생성) 시각 |
| last_seen_at | datetime | | 마지막으로 요청이 들어온 시각 |
| expires_at | datetime | | 세션 만료 시각 |
| revoked_at | datetime | | 로그아웃·강제 종료 시각 (유효하면 null) |

### terms
약관

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 약관 고유 ID |
| version | string | | 약관 버전 |
| title | string | | 약관 제목 |
| required | bool | | 필수 동의 약관인지 여부 (true 필수 / false 선택) |
| effective_at | datetime | | 약관 시행 시각 |
| card_product_id | string | FK→card_products | 카드 상품 약관이면 해당 카드 상품 (일반 약관은 null) |

### user_consents
회원의 약관 동의 기록

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 동의 기록 고유 ID |
| user_id | string | FK→users | 동의한 회원 |
| terms_id | string | FK→terms | 동의한 약관 |
| version | string | | 동의할 때 약관 버전 |
| agreed | bool | | 동의 여부 (true 동의 / false 거부·철회) |
| recorded_at | datetime | | 동의(또는 철회)를 기록한 시각 |

### pin_credentials
간편 비밀번호(PIN) (회원당 0~1개)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| user_id | string | PK, FK→users | 회원 ID (회원당 1행) |
| pin_hash | string | | 해시한 PIN |
| enabled_at | datetime | | PIN을 처음 설정한 시각 |
| changed_at | datetime | | PIN을 마지막으로 바꾼 시각 |
| failed_attempts | int | | PIN 연속 실패 횟수 |
| locked_until | datetime | | PIN 잠금이 풀리는 시각 |

### auth_audit_logs
인증 관련 감사 기록

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 기록 고유 ID |
| user_id | string | FK→users | 대상 회원 |
| event_type | string | | 이벤트 종류 (로그인, 로그아웃, 비밀번호 변경 등) |
| occurred_at | datetime | | 이벤트 발생 시각 |
| outcome | string | | 결과 (성공 / 실패 등) |
| request_id | string | | 요청 추적용 ID (로그 대조용) |

### step_up_challenges
중요한 작업 전에 하는 추가 본인 확인

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 본인 확인 고유 ID |
| user_id | string | FK→users | 본인 확인을 한 회원 |
| action | string | | 무엇을 하려고 확인했는지: TRANSFER 이체 / SCHEDULED_TRANSFER 예약 이체 / CARD_APPLICATION 카드 신청 / CARD_TERMINATION 카드 해지 / CARD_MANAGEMENT 카드 관리 / SUBSCRIPTION 상품 가입 / ACCOUNT_STATUS_CHANGE 계좌 상태 변경 / WITHDRAWAL 탈퇴 / PROFILE_CHANGE 회원정보 변경 |
| session_id | string | FK→sessions | 본인 확인을 한 로그인 세션 |
| expires_at | datetime | | 확인 결과 유효 시각 (이 시각 전에 작업해야 함) |
| consumed_at | datetime | | 확인 결과를 실제 작업에 쓴 시각 (한 번만 사용) |

### withdrawal_checks
회원 탈퇴 전 점검 진행 상황

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 탈퇴 점검 고유 ID |
| user_id | string | FK→users | 탈퇴하려는 회원 |
| status | string | | 점검 상태 (IN_PROGRESS 진행 중 / COMPLETED 완료 / CANCELED 취소) |
| started_at | datetime | | 점검 시작 시각 |
| balance_verified_at | datetime | | 남은 잔액이 없음을 확인한 시각 |
| data_review_confirmed_at | datetime | | 개인정보 처리 안내를 회원이 확인한 시각 |
| data_review_version | string | | 회원이 확인한 개인정보 처리 안내문 버전 |
| linked_services_confirmed_at | datetime | | 연결된 서비스(카드·상품 등) 정리를 확인한 시각 |
| completed_at | datetime | | 탈퇴 완료 시각 |

---

## 2. 계좌 (7개)

### accounts
회원의 계좌

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 계좌 고유 ID |
| user_id | string | FK→users | 계좌 주인 |
| resAccount | string | UK | 계좌번호 (숫자만, 중복 불가) |
| resAccountDisplay | string | | 화면용 계좌번호 (`110-00-000001`처럼 하이픈 포함) |
| resAccountName | string | | 계좌 상품명 |
| account_type | string | | 계좌 종류 (CHECKING 입출금 / SAVINGS 저축) |
| lifecycle_status | string | | 계좌 상태 (ACTIVE 정상 / SUSPENDED 정지 / CLOSED 해지) |
| resAccountNickName | string | | 회원이 붙인 계좌 별명 |
| is_favorite | bool | | 즐겨찾기 계좌 여부 |
| resAccountStartDate | string | | 계좌 개설일 (YYYYMMDD) |
| closed_at | string | | 계좌 해지일 (YYYYMMDD, 해지 전에는 null) |
| version | int | | 동시 수정 방지용 버전 번호 (낙관적 잠금) |

### account_balance_view
계좌 잔액 조회용 보기(view). 실제 표가 아니고, 원본은 3장의 `account_balances`입니다.

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| account_id | string | PK, FK→accounts | 잔액을 볼 계좌 |
| resAccountCurrency | string | | 통화 (KRW) |
| resAccountBalance | bigint | | 현재 잔액 (원) |
| balance_as_of | string | | 잔액 기준 시각 (YYYYMMDDHHmmss) |

### account_activity_logs
계좌 관리 작업 기록

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 기록 고유 ID |
| account_id | string | FK→accounts | 대상 계좌 |
| actor_id | string | | 작업한 사람 (회원 또는 관리자 ID) |
| action | string | | 작업 종류 (별명 변경, 정지, 해지 등) |
| occurred_at | datetime | | 작업 시각 |
| metadata | string | | 추가 정보 (변경 전후 값 등, JSON 문자열) |

### notification_preferences
계좌별 입출금 알림 설정 (회원+계좌 복합 PK)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| user_id | string | PK, FK→users | 설정한 회원 |
| account_id | string | PK, FK→accounts | 설정 대상 계좌 |
| enabled | bool | | 이 계좌 알림 전체를 켰는지 여부 |
| deposit_enabled | bool | | 입금 알림 받기 여부 |
| withdrawal_enabled | bool | | 출금 알림 받기 여부 |
| minimum_amount | bigint | | 이 금액 이상일 때만 알림 (원) |
| channel | string | | 알림 받는 방법 (푸시, 문자 등) |

### notifications
회원에게 보낸 알림

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 알림 고유 ID |
| user_id | string | FK→users | 알림 받는 회원 |
| account_id | string | FK→accounts | 계좌 알림이면 그 계좌 (카드 알림이면 null) |
| user_card_id | string | FK→user_cards | 카드 알림이면 그 카드 |
| event_id | string | | 알림을 만든 원인 이벤트 ID. (event_id, user_id, type) 조합은 중복 금지라 같은 알림이 두 번 가지 않음 |
| type | string | | 알림 종류 (TRANSACTION 입출금 / PAYMENT_DUE 결제 예정 / MATURITY 만기 등) |
| title | string | | 알림 제목 |
| body | string | | 알림 내용 |
| status | string | | 발송 상태 (대기·발송·실패 등) |
| read_at | datetime | | 회원이 읽은 시각 (안 읽었으면 null) |
| created_at | datetime | | 알림 생성 시각 |

### account_inactivity
장기 미사용 계좌 관리 (계좌당 0~1개)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| account_id | string | PK, FK→accounts | 대상 계좌 |
| last_activity_at | datetime | | 마지막 거래·이용 시각 |
| inactivity_flag | bool | | 장기 미사용으로 분류됐는지 여부 |
| flagged_at | datetime | | 장기 미사용으로 분류된 시각 |

### document_issuance_logs
계좌 증명서 발급 기록

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 발급 기록 고유 ID |
| account_id | string | FK→accounts | 증명서 대상 계좌 |
| document_type | string | | 증명서 종류 (통장 사본, 잔액 증명서 등) |
| requested_by | string | | 발급을 요청한 사람 ID |
| issued_at | datetime | | 발급 시각 |
| status | string | | 발급 상태 (완료·실패 등) |

---

## 3. 거래 (7개)

### account_balances
계좌 잔액 원본 (계좌와 1:1)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| account_id | string | PK, FK→accounts | 잔액 주인 계좌 |
| currency | string | | 통화 (KRW) |
| balance | bigint | | 현재 잔액 (원) |
| updated_at | datetime | | 잔액이 마지막으로 바뀐 시각 |

### transactions
거래 원장 (계좌 입출금 1건 = 1행)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 거래 고유 ID (`tx_0001`) |
| account_id | string | FK→accounts | 돈이 들어오거나 나간 계좌 |
| type | string | | 거래 종류: TRANSFER_OUT 이체 출금 / TRANSFER_IN 이체 입금 / CARD_PAYMENT 카드 결제 출금 / POINT_CASHOUT 포인트 현금화 입금 / SUBSCRIPTION_PAYMENT 예적금 납입 출금 / SUBSCRIPTION_PAYOUT 예적금 해지·만기 입금 |
| amount | bigint | | 거래 금액 (원) |
| fee | bigint | | 수수료 (원) |
| balance_after | bigint | | 거래 직후 잔액 (원) |
| transfer_id | string | FK→transfers | 이체로 생긴 거래면 그 이체 (이체 1건 → 출금·입금 2행, 이체가 아니면 null) |
| counterpart_bank | string | | 상대방 은행 |
| counterpart_account_no | string | | 상대방 계좌번호 |
| display_name | string | | 거래 내역에 보이는 이름 (받는 분·보낸 분 표시) |
| created_at | datetime | | 거래 시각 |

### transfers
이체 요청 1건

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 이체 고유 ID (`trf_0001`) |
| user_id | string | FK→users | 이체를 요청한 회원 |
| from_account_id | string | FK→accounts | 돈이 나가는 내 계좌 |
| to_bank | string | | 받는 은행 |
| to_account_no | string | | 받는 계좌번호 |
| to_holder_name | string | | 받는 분 예금주명 |
| amount | bigint | | 이체 금액 (원) |
| fee | bigint | | 이체 수수료 (원) |
| my_display_name | string | | 내 통장에 찍히는 이름 |
| their_display_name | string | | 받는 분 통장에 찍히는 이름 |
| status | string | | 처리 상태 (PENDING 처리 중 / SUCCESS 성공 / FAILED 실패) |
| failure_reason | string | | 실패 이유 (잔액 부족, 한도 초과 등) |
| channel | string | | 이체 경로 (APP 앱에서 직접 / SCHEDULED 예약 이체 / AUTO 자동 이체) |
| scheduled_transfer_id | string | FK→scheduled_transfers | 예약 이체로 실행됐으면 그 예약 |
| step_up_challenge_id | string | FK→step_up_challenges | 이체 전에 거친 본인 확인 |
| idempotency_key | string | UK | 중복 요청 방지 키 (같은 키로 두 번 와도 1번만 이체) |
| requested_at | datetime | | 이체 요청 시각 |
| completed_at | datetime | | 이체 처리가 끝난 시각 |

### scheduled_transfers
예약 이체 등록 정보 (원문에 주요 칸만 있음)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 예약 이체 고유 ID |
| user_id | string | FK→users | 예약을 등록한 회원 |
| from_account_id | string | FK→accounts | 출금 계좌 |
| to_bank | string | | 받는 은행 |
| to_account_no | string | | 받는 계좌번호 |
| to_holder_name | string | | 받는 분 예금주명 |
| amount | bigint | | 이체 금액 (원) |
| type | string | | 예약 방식 (ONCE 한 번 / MONTHLY 매달) |
| execute_at | datetime | | 한 번 예약일 때 실행 시각 |
| day_of_month | int | | 매달 예약일 때 실행일 (1~28, 99=말일) |
| start_ym | string | | 매달 예약 시작 연월 |
| end_ym | string | | 매달 예약 종료 연월 |
| next_run_at | datetime | | 다음 실행 예정 시각 |
| status | string | | 예약 상태 (진행 중·종료·해지 등) |
| step_up_challenge_id | string | FK→step_up_challenges | 예약을 등록할 때 거친 본인 확인 |
| created_at | datetime | | 예약 등록 시각 |

### favorite_accounts
자주 쓰는 받는 계좌

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 고유 ID |
| user_id | string | FK→users | 등록한 회원 |
| bank | string | | 은행 |
| account_no | string | | 계좌번호 |
| holder_name | string | | 예금주명 |
| nickname | string | | 회원이 붙인 별명 (엄마, 월세 등) |
| sort_order | int | | 목록에 보이는 순서 |

### transfer_limits
계좌별 이체 한도 (계좌당 0~1개)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| account_id | string | PK, FK→accounts | 대상 계좌 |
| per_transfer_limit | bigint | | 1회 이체 한도 (원) |
| daily_limit | bigint | | 1일 이체 한도 (원) |
| updated_at | datetime | | 한도를 마지막으로 바꾼 시각 |

### external_accounts
가상 타행 계좌 (예금주 조회용 시드 데이터라 다른 테이블과 연결 없음)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 고유 ID |
| bank | string | | 다른 은행 이름 |
| account_no | string | | 계좌번호 (이 값으로 조회) |
| holder_name | string | | 예금주명 (이체 전 받는 분 확인에 사용) |

---

## 4. 예금·적금 상품 (6개)

### products
예금·적금 상품

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 상품 고유 ID (`prod_001`) |
| bank | string | | 판매 은행 (두린은행) |
| name | string | | 상품명 |
| type | string | | 상품 종류 (TIME_DEPOSIT 정기예금 / INSTALLMENT_SAVINGS 적금) |
| description | string | | 상품 설명 |
| status | string | | 판매 상태 (ON_SALE 판매 중 / STOPPED 판매 중지) |
| source_url | string | | 상품 정보 출처 주소 |
| verified_at | string | | 출처와 대조해 확인한 날짜 (YYYYMMDD) |

### product_rates
가입 기간별 금리

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 고유 ID |
| product_id | string | FK→products | 대상 상품 |
| term_min | int | | 이 금리가 적용되는 최소 기간 |
| term_max | int | | 이 금리가 적용되는 최대 기간 |
| term_unit | string | | 기간 단위 (MONTH 개월 / DAY 일) |
| base_rate | string | | 기본 금리 (연 %) |
| bonus_rate | string | | 우대 금리 (연 %, 조건 충족 시 추가) |
| effective_from | string | | 금리 적용 시작일 (YYYYMMDD) |

### product_rules
가입 조건

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 고유 ID |
| product_id | string | FK→products | 대상 상품 |
| min_amount | bigint | | 최소 가입(납입) 금액 (원) |
| max_amount | bigint | | 최대 가입(납입) 금액 (원) |
| min_months | int | | 최소 가입 기간 (개월) |
| max_months | int | | 최대 가입 기간 (개월) |
| max_per_user | int | | 1인당 최대 가입 계좌 수 |
| rules_json | string | | 그 밖의 조건 (나이 제한 등, JSON 문자열) |

### subscriptions
회원의 예금·적금 가입

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 가입 고유 ID (`sub_001`) |
| user_id | string | FK→users | 가입한 회원 |
| product_id | string | FK→products | 가입한 상품 |
| source_account_id | string | FK→accounts | 납입금이 빠져나가는 출금 계좌 |
| principal | bigint | | 예금 원금 (원, 정기예금일 때) |
| monthly_amount | bigint | | 월 납입액 (원, 적금일 때) |
| applied_rate | string | | 가입할 때 확정된 적용 금리 (연 %) |
| start_date | string | | 가입일 (YYYYMMDD) |
| maturity_date | string | | 만기일 (YYYYMMDD) |
| status | string | | 가입 상태 (ACTIVE 진행 중 / MATURED 만기 / TERMINATED 중도 해지) |
| closed_at | string | | 만기·해지로 끝난 날짜 (YYYYMMDD, 진행 중이면 null) |
| idempotency_key | string | UK | 중복 가입 방지 키 |

### subscription_payments
적금 납입 내역

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 납입 고유 ID |
| subscription_id | string | FK→subscriptions | 대상 가입 건 |
| paid_amount | bigint | | 납입 금액 (원) |
| paid_at | string | | 납입 시각 (YYYYMMDDHHmmss) |

### product_documents
상품 설명 문서 (AI 상담(RAG) 검색용)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 문서 고유 ID |
| product_id | string | FK→products | 대상 상품 |
| title | string | | 문서 제목 (상품설명서, 약관 등) |
| source_url | string | | 문서 원본 주소 |
| version_date | string | | 문서 버전 기준일 |

---

## 5. 카드: 상품·발급·보유 (14개)

### card_companies
카드사

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 카드사 고유 ID |
| code | string | | 카드사 코드 (외부 연동용) |
| name | string | | 카드사 이름 |
| logo_url | string | | 카드사 로고 이미지 주소 |

### card_products
카드 상품

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 카드 상품 고유 ID |
| card_company_id | string | FK→card_companies | 발급 카드사 |
| name | string | | 카드 상품명 |
| card_type | string | | 카드 종류 (CREDIT 신용 / CHECK 체크) |
| annual_fee_domestic | int | | 국내 전용 연회비 (원) |
| annual_fee_overseas | int | | 해외 겸용 연회비 (원) |
| min_age | int | | 발급 가능 최소 나이 |
| is_active | bool | | 현재 발급(판매) 중인지 여부 |

### card_performance_tiers
전월 실적 구간

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 구간 고유 ID |
| card_product_id | string | FK→card_products | 대상 카드 상품 |
| tier_level | int | | 구간 단계 (1, 2, 3 …) |
| min_spend | bigint | | 이 구간의 최소 전월 실적 (원) |
| max_spend | bigint | | 이 구간의 최대 전월 실적 (원) |

### card_benefits
카드 혜택

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 혜택 고유 ID |
| card_product_id | string | FK→card_products | 대상 카드 상품 |
| tier_id | string | FK→card_performance_tiers | 이 혜택이 적용되는 실적 구간 (구간 상관없으면 null) |
| category_id | string | FK→categories | 혜택 대상 업종 (카페, 편의점 등) |
| value_type | string | | 혜택 방식 (할인율 %, 정액 할인, 적립 등) |
| benefit_value | decimal | | 혜택 크기 (value_type에 따라 % 또는 원) |
| monthly_limit_amount | int | | 월 혜택 한도 (원) |

### categories
업종 분류 (자기 자신을 참조해 계층 구조). 6장의 `merchants`, `card_recommendation_details`도 이 테이블을 참조합니다.

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 분류 고유 ID |
| parent_id | string | FK→categories | 상위 분류 (대분류면 null) |
| code | string | | 분류 코드 |
| name | string | | 분류 이름 (식비, 카페 등) |

### promotions
카드 발급 이벤트

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 이벤트 고유 ID |
| card_product_id | string | FK→card_products | 대상 카드 상품 |
| title | string | | 이벤트 제목 |
| reward_amount | int | | 이벤트 보상 금액 (원, 캐시백 등) |
| starts_at | datetime | | 이벤트 시작 시각 |
| ends_at | datetime | | 이벤트 종료 시각 |

### card_applications
카드 발급 신청

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 신청 고유 ID |
| user_id | string | FK→users | 신청한 회원 |
| card_product_id | string | FK→card_products | 신청한 카드 상품 |
| promotion_id | string | FK→promotions | 이벤트를 통해 신청했으면 그 이벤트 |
| recommendation_id | string | FK→card_recommendations | 추천을 보고 신청했으면 그 추천 |
| step_up_challenge_id | string | FK→step_up_challenges | 신청 전에 거친 본인 확인 |
| status | string | | 진행 상태: APPLIED 신청 → REVIEWING 심사 중 → APPROVED 승인 / REJECTED 거절 → SHIPPING 배송 중 → DELIVERED 배송 완료 → ACTIVATED 사용 등록, 또는 CANCELED 취소 |
| job_type | string | | 직업 구분 (심사용) |
| annual_income | bigint | | 연소득 (원, 심사용) |
| linked_account_id | string | FK→accounts | 결제 대금이 빠져나갈 연결 계좌 |
| payment_day | int | | 희망 결제일 |
| approved_credit_limit | bigint | | 심사에서 승인된 이용 한도 (원, 신용카드) |
| reject_reason | string | | 거절 이유 (AGE 나이 미달 / NO_INCOME 소득 없음 / DUPLICATE 중복 신청) |
| applied_at | datetime | | 신청 시각 |

### application_status_histories
발급 신청 상태 변경 이력

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 이력 고유 ID |
| application_id | string | FK→card_applications | 대상 신청 |
| from_status | string | | 바뀌기 전 상태 |
| to_status | string | | 바뀐 후 상태 |
| changed_at | datetime | | 상태가 바뀐 시각 |

### application_term_agreements
발급 신청 때의 약관 동의 (신청+약관 복합 PK)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| application_id | string | PK, FK→card_applications | 대상 신청 |
| terms_id | string | PK, FK→terms | 동의한 약관 |
| agreed | bool | | 동의 여부 |
| agreed_at | datetime | | 동의 시각 |

### user_cards
회원이 가진 카드

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 보유 카드 고유 ID |
| user_id | string | FK→users | 카드 주인 |
| card_product_id | string | FK→card_products | 카드 상품 |
| application_id | string | FK→card_applications | 우리 앱에서 신청해 발급됐으면 그 신청 (마이데이터 연동 카드는 null) |
| reissued_from_id | string | FK→user_cards | 재발급 카드면 이전 카드 |
| source | string | | 카드 출처 (TOSS_ISSUED 앱에서 발급 / MYDATA 마이데이터로 불러옴) |
| card_number_masked | string | | 가린 카드번호 (`1234-****-****-5678`) |
| linked_account_id | string | FK→accounts | 결제·출금 계좌 |
| payment_day | int | | 결제일 |
| credit_limit | bigint | | 이용 한도 (원, 신용카드만) |
| status | string | | 카드 상태 (ACTIVE 정상 / SUSPENDED 정지 / LOST 분실 / EXPIRED 유효기간 만료 / TERMINATED 해지) |
| issued_at | datetime | | 발급 시각 |
| terminated_at | datetime | | 해지 시각 (해지 전이면 null) |

### user_card_settings
카드별 이용 설정 (카드당 0~1개)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| user_card_id | string | PK, FK→user_cards | 대상 카드 |
| overseas_payment_blocked | bool | | 해외 결제 차단 여부 |
| online_payment_blocked | bool | | 온라인 결제 차단 여부 |
| daily_limit | bigint | | 회원이 정한 1일 사용 한도 (원) |
| monthly_limit | bigint | | 회원이 정한 월 사용 한도 (원) |
| payment_alert_enabled | bool | | 결제 알림 받기 여부 |

### user_card_status_histories
보유 카드 상태 변경 이력

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 이력 고유 ID |
| user_card_id | string | FK→user_cards | 대상 카드 |
| from_status | string | | 바뀌기 전 상태 |
| to_status | string | | 바뀐 후 상태 |
| reason | string | | 바뀐 이유 (분실 신고, 만료 등) |
| changed_at | datetime | | 상태가 바뀐 시각 |

### card_management_logs
카드 관리(설정 변경) 기록

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 기록 고유 ID |
| user_card_id | string | FK→user_cards | 대상 카드 |
| action_type | string | | 관리 작업 종류 (한도 변경, 해외 결제 차단 등) |
| before_value | string | | 바꾸기 전 값 |
| after_value | string | | 바꾼 후 값 |
| requested_at | datetime | | 요청 시각 |

### card_terminations
카드 해지 요청

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 해지 요청 고유 ID |
| user_card_id | string | FK→user_cards | 해지할 카드 |
| step_up_challenge_id | string | FK→step_up_challenges | 해지 전에 거친 본인 확인 |
| status | string | | 해지 상태 (REQUESTED 요청 / COMPLETED 완료 / REJECTED 거절 / CANCELED 취소) |
| reason_code | string | | 해지 사유 코드 |
| unpaid_amount | bigint | | 해지 시점에 남은 미결제 금액 (원) |
| remaining_installment_amount | bigint | | 해지 시점에 남은 할부 금액 (원) |
| completed_at | datetime | | 해지 완료 시각 |

---

## 6. 카드: 이용·청구·분석·포인트 (15개)

### card_transactions
카드 승인(사용) 내역

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 카드 거래 고유 ID |
| user_card_id | string | FK→user_cards | 사용한 카드 |
| merchant_id | string | FK→merchants | 결제한 가맹점 |
| approval_no | string | | 카드 승인번호 |
| transacted_at | datetime | | 결제 시각 |
| amount | bigint | | 결제 금액 (원) |
| installment_months | int | | 할부 개월 수 (0=일시불) |
| status | string | | 승인 상태 (APPROVED 승인 / PARTIAL_CANCELED 부분 취소 / CANCELED 전액 취소) |
| canceled_amount | bigint | | 취소된 금액 (원) |
| applied_benefit_id | string | FK→card_benefits | 이 결제에 적용된 혜택 |
| is_performance_counted | bool | | 전월 실적에 넣는지 여부 (세금·상품권 등은 false) |

### merchants
가맹점 ([부록](#부록-merchants-테이블의-역할) 참고)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 가맹점 고유 ID |
| category_id | string | FK→categories | 가맹점 업종 |
| name | string | | 가맹점 이름 |
| business_no | string | | 사업자등록번호 |

### billing_cycle_rules
카드사·결제일별 이용 기간 규칙 (카드사+결제일 복합 PK)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| card_company_id | string | PK, FK→card_companies | 카드사 |
| payment_day | int | PK | 결제일 |
| start_month_offset | int | | 이용 기간 시작 달: 결제월 기준 몇 달 전 (-2, -1) |
| start_day | int | | 이용 기간 시작일 |
| end_month_offset | int | | 이용 기간 끝 달: 결제월 기준 몇 달 전 |
| end_day | int | | 이용 기간 끝일 (99=말일) |

### card_bills
월별 카드 청구서

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 청구서 고유 ID |
| user_card_id | string | FK→user_cards | 대상 카드 |
| billing_ym | string | | 결제월 (YYYYMM) |
| usage_start | date | | 이 청구서에 들어가는 이용 기간 시작일 |
| usage_end | date | | 이용 기간 끝일 |
| payment_date | date | | 대금 결제일 |
| total_amount | bigint | | 청구 총액 (원) |
| paid_amount | bigint | | 실제로 결제된 금액 (원) |
| status | string | | 청구 상태 (SCHEDULED 예정 / CONFIRMED 확정 / PAID 결제 완료 / OVERDUE 연체) |

### card_bill_items
청구서 세부 항목

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 항목 고유 ID |
| bill_id | string | FK→card_bills | 소속 청구서 |
| card_transaction_id | string | FK→card_transactions | 원래 카드 거래 (할부면 회차마다 1행) |
| installment_seq | int | | 할부 회차 (일시불이면 1) |
| principal_amount | bigint | | 이번 회차 원금 (원) |
| fee_amount | bigint | | 이번 회차 할부 수수료 (원, 1차 개발은 무이자라 0) |

### recurring_payments
고정 지출 (구독료, 통신비 등 정기 결제)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 고정 지출 고유 ID |
| user_id | string | FK→users | 대상 회원 |
| user_card_id | string | FK→user_cards | 결제 카드 |
| merchant_id | string | FK→merchants | 정기 결제 가맹점 |
| expected_amount | bigint | | 예상 결제 금액 (원) |
| expected_day | int | | 예상 결제일 |
| detected_by | string | | 등록 방법 (AUTO 결제 내역에서 자동 탐지 / USER 회원이 직접 등록) |
| is_active | bool | | 지금도 유지 중인 고정 지출인지 여부 |

### spending_forecasts
청구 금액 예측

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 예측 고유 ID |
| user_card_id | string | FK→user_cards | 대상 카드 |
| billing_ym | string | | 예측할 결제월 (YYYYMM) |
| predicted_total | bigint | | 예측한 청구 총액 (원) |
| model_type | string | | 예측 방식 (MOVING_AVG 이동평균 / LINEAR 선형회귀 / ML 머신러닝) |

### daily_card_spending
카드별 일별 사용 집계 (카드+날짜 복합 PK)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| user_card_id | string | PK, FK→user_cards | 대상 카드 |
| spend_date | date | PK | 집계 날짜 |
| total_amount | bigint | | 그날 사용한 총액 (원) |
| tx_count | int | | 그날 결제 건수 |

### card_recommendations
회원에게 추천한 카드

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 추천 고유 ID |
| user_id | string | FK→users | 추천받은 회원 |
| card_product_id | string | FK→card_products | 추천한 카드 상품 |
| net_annual_benefit | bigint | | 예상 연간 순혜택 (혜택 합계 − 연회비, 원) |
| rank_no | int | | 추천 순위 |

### card_recommendation_details
추천 근거 (업종별, 추천+업종 복합 PK)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| recommendation_id | string | PK, FK→card_recommendations | 대상 추천 |
| category_id | string | PK, FK→categories | 업종 |
| spend_amount | bigint | | 이 업종에서 쓴 금액 (원) |
| benefit_amount | bigint | | 이 카드였다면 이 업종에서 받았을 혜택 (원) |

### card_issuance_rankings
카드 발급 순위 (인기 카드)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 순위 고유 ID |
| period_type | string | | 집계 단위 (주간·월간 등) |
| period_start | date | | 집계 기간 시작일 |
| segment_age | string | | 대상 연령대 (20대 등, 전체면 null) |
| segment_gender | string | | 대상 성별 (전체면 null) |
| card_product_id | string | FK→card_products | 순위에 오른 카드 상품 |
| rank_no | int | | 순위 |
| issue_count | int | | 기간 동안 발급된 수 |

### card_points
카드사별 포인트

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 포인트 고유 ID |
| user_id | string | FK→users | 포인트 주인 |
| card_company_id | string | FK→card_companies | 포인트를 준 카드사 |
| point_name | string | | 포인트 이름 (예: ○○포인트) |
| balance | bigint | | 보유 포인트 |
| expiring_amount | bigint | | 곧 소멸될 포인트 |

### point_cashouts
포인트 현금화 요청

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 현금화 고유 ID |
| card_point_id | string | FK→card_points | 현금으로 바꿀 포인트 |
| account_id | string | FK→accounts | 현금이 들어올 계좌 |
| amount | bigint | | 현금화 금액 (원) |
| status | string | | 처리 상태 (처리 중·완료·실패 등) |
| completed_at | datetime | | 입금 완료 시각 |

### mydata_consents
마이데이터 연동 동의 (카드사별)

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 동의 고유 ID |
| user_id | string | FK→users | 동의한 회원 |
| card_company_id | string | FK→card_companies | 정보를 가져올 카드사 |
| scope | string | | 가져올 정보 범위 (카드 목록, 이용 내역, 청구서 등) |
| status | string | | 동의 상태 (유효·철회·만료 등) |
| expires_at | datetime | | 동의 만료 시각 |

### mydata_sync_logs
마이데이터 동기화 기록

| 칸 | 타입 | 키 | 비고 |
|---|---|---|---|
| id | string | PK | 기록 고유 ID |
| mydata_consent_id | string | FK→mydata_consents | 근거가 된 연동 동의 |
| api_type | string | | 호출한 마이데이터 API 종류 (카드 목록, 승인 내역 등) |
| result | string | | 동기화 결과 (성공·실패 등) |
| started_at | datetime | | 동기화 시작 시각 |

---

## 부록: merchants 테이블의 역할

`merchants`는 화면에 직접 보이는 기능이 아니라 **가맹점(카드를 긁은 가게) 목록을 담는 기준 테이블**입니다. 카드 결제 한 건마다 "어디서, 어떤 업종에서 썼는지"를 알려 줍니다.

**어디에 쓰이는지** ([FEATURES.md](FEATURES.md) 기준)

1. **카드 이용 내역**: `card_transactions.merchant_id`로 연결돼 있어서 결제 목록에 가맹점 이름이 나옵니다.
2. **마이데이터 연동**: 카드사에서 받은 승인 내역에는 가맹점명과 사업자번호(`merchant_regno`)가 문자열로 들어 있습니다. 이 사업자번호를 `business_no`와 맞춰 보고 `merchant_id`를 붙입니다.
3. **고정 지출 탐지**: 같은 가맹점에서 3개월 이상 연속으로 결제했고, 금액 차이가 ±10%, 결제일 차이가 ±3일 안이면 `recurring_payments`에 `detected_by='AUTO'`로 자동 등록합니다.
4. **카드 추천·실적·혜택 계산**: 결제(`card_transactions`) → 가맹점(`merchants`) → 업종(`categories`) 순으로 따라가면 업종별 지출 합계가 나옵니다. 이 합계로 "이 카드였다면 카페에서 얼마를 할인받았을지"를 계산해 추천합니다. 업종이 정해져야 어떤 혜택(`card_benefits.category_id`)이 적용되는지도 알 수 있습니다.

즉, 결제 금액에 업종을 붙여 주는 중간 다리입니다. 이 테이블이 없으면 이용 내역에는 금액만 남고, 업종별 분석·추천·고정 지출 탐지는 할 수 없습니다.

---

## 원본 기획서와 맞춰 봐야 할 칼럼

ERD에 허용값이 없어서 이름만 보고 추측한 칼럼들입니다.

- **상태 값 목록**: `notifications.status`, `document_issuance_logs.status`, `scheduled_transfers.status`, `point_cashouts.status`, `mydata_consents.status`
- **그 밖의 값**: `email_verifications.purpose`, `card_benefits.value_type`, `card_issuance_rankings.period_type`, `notification_preferences.channel`
- **의미**: `withdrawal_checks.data_review_*` (개인정보 처리 안내를 확인한 시각과 버전으로 해석함)
