-- =====================================================================
-- 두린은행 계좌·거래·상품·카드 서비스 - 스키마 (MySQL 8.0)
-- 기준: ERD.md (2026-11-04, 파트별 그림 1~6) — 표 60개 + 보기(view) 1개
--
-- 파일 구성 (번호 순서대로 실행)
--   00_common.sql             DB 생성, 세션 설정, 공통 규칙   ← 이 파일
--   01_users.sql              1. 회원·인증
--   02_accounts.sql           2. 계좌
--   03_transactions.sql       3. 거래 (account_balances, account_balance_view 포함)
--   04_deposite_products.sql  4. 예금·적금 상품
--   05_card_products.sql      5. 카드 — 상품·발급·보유 (categories, terms, user_consents 포함)
--   06_card_usage.sql         6. 카드 — 이용·청구·분석·포인트
--   07_notifications.sql      7. 알림 (끝에서 FK 검사를 다시 켬)
--
-- 실행 방법
--   Git Bash:  cat docs/sql/0*.sql | mysql -u root -p
--   PowerShell 5.1 에서 Get-Content ... | mysql 로 넘기면 한글(COMMENT, DEFAULT '두린은행')이 ? 로 깨지므로 쓰지 않는다.
--   Docker: /docker-entrypoint-initdb.d 에 이 폴더를 붙이면 파일 이름 순서로 실행된다 (파일마다 세션이 따로).
--
-- FK 순서: 모든 FK는 앞 번호 파일(또는 같은 파일의 앞쪽) 표만 가리킨다 (2026-11-05 확인, 참조 91개).
--   그래서 번호 순서로 실행하면 FK 검사를 켜 둔 채로도 만들어진다.
--   아래 SET FOREIGN_KEY_CHECKS = 0 은 한 세션으로 이어서 실행할 때의 안전장치일 뿐이다.
--   도메인을 넘는 FK: 04 subscriptions → 01 users, 02 accounts / 07 notifications → 05 user_cards
--
-- 공통 규칙 (ERD "읽는 법", 이름 규칙 C-5)
--   - ID는 문자열 (예: user_001, tx_0001, trf_0001, prod_001, sub_001) → VARCHAR(40), AUTO_INCREMENT 없음
--   - PK 칸 이름은 id, 다른 테이블을 가리키는 칸은 <테이블 단수>_id (card_product_id, card_company_id, terms_id ...)
--   - 금액은 원 단위 정수 BIGINT
--   - 시각은 +09:00 (세션 time_zone 고정), 우리가 만든 빈 칸은 NULL
--   - ERD에서 문자열로 둔 날짜(YYYYMMDD, YYYYMMDDHHmmss, YYYYMM)는 CHAR로 그대로 저장
--   - 카드 테이블과 scheduled_transfers는 ERD에 주요 칸만 있으므로,
--     기획서·이전 schema.sql의 나머지 칸을 C-5 이름으로 바꿔 함께 둠
-- =====================================================================

CREATE DATABASE IF NOT EXISTS toss_card
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
USE toss_card;

SET NAMES utf8mb4;
SET time_zone = '+09:00';

-- 07_notifications.sql 끝에서 다시 1로 켬
SET FOREIGN_KEY_CHECKS = 0;
