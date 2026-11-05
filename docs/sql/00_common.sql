-- =====================================================================
-- 두린은행 계좌·거래·상품·카드 서비스 - 스키마 (PostgreSQL 17)
-- 기준: ERD.md (2026-11-04, 파트별 그림 1~6) — 표 60개 + 보기(view) 1개
-- 2026-11-05 MySQL 8.0 → PostgreSQL 로 옮김
--
-- 파일 구성 (번호 순서대로 실행)
--   00_common.sql             시간대 설정, 공통 함수, 공통 규칙   ← 이 파일
--   01_users.sql              1. 회원·인증
--   02_accounts.sql           2. 계좌
--   03_transactions.sql       3. 거래 (account_balances, account_balance_view 포함)
--   04_deposite_products.sql  4. 예금·적금 상품
--   05_card_products.sql      5. 카드 — 상품·발급·보유 (categories, terms, user_consents 포함)
--   06_card_usage.sql         6. 카드 — 이용·청구·분석·포인트
--   07_notifications.sql      7. 알림
--
-- 실행 방법 (DB toss_card 는 미리 있어야 한다 — PostgreSQL 은 파일 안에서 DB를 만들고 바로 들어갈 수 없음)
--   Docker: POSTGRES_DB=toss_card 로 띄우고 /docker-entrypoint-initdb.d 에 이 폴더를 붙이면
--           파일 이름 순서로 toss_card 안에서 실행된다 (파일마다 세션이 따로).
--   직접:   createdb -U postgres toss_card
--           for f in docs/sql/0*.sql; do psql -U postgres -d toss_card -v ON_ERROR_STOP=1 -f "$f"; done
--   파일마다 맨 위에 SET client_encoding = 'UTF8' 이 있으므로 Windows psql 에서 -f 로 실행해도 한글이 깨지지 않는다.
--   PowerShell 5.1 에서 Get-Content ... | psql 로 넘기면 한글이 ? 로 깨지므로 쓰지 않는다.
--
-- FK 순서: 모든 FK는 앞 번호 파일(또는 같은 파일의 앞쪽) 표만 가리킨다 (참조 91개).
--   PostgreSQL 에는 MySQL 의 FOREIGN_KEY_CHECKS 같은 스위치가 없으므로 이 순서가 꼭 지켜져야 한다.
--   도메인을 넘는 FK: 04 subscriptions → 01 users, 02 accounts / 07 notifications → 05 user_cards
--
-- 공통 규칙 (ERD "읽는 법", 이름 규칙 C-5)
--   - ID는 문자열 (예: user_001, tx_0001, trf_0001, prod_001, sub_001) → VARCHAR(40), 자동 번호 없음
--   - PK 칸 이름은 id, 다른 테이블을 가리키는 칸은 <테이블 단수>_id (card_product_id, card_company_id, terms_id ...)
--   - 금액은 원 단위 정수 BIGINT
--   - 시각은 Asia/Seoul(+09:00) 기준 TIMESTAMP(0) (DB 기본 시간대 고정), 우리가 만든 빈 칸은 NULL
--   - ERD에서 문자열로 둔 날짜(YYYYMMDD, YYYYMMDDHHmmss, YYYYMM)는 CHAR로 그대로 저장
--   - 카드 테이블과 scheduled_transfers는 ERD에 주요 칸만 있으므로,
--     기획서·이전 schema.sql의 나머지 칸을 C-5 이름으로 바꿔 함께 둠
--
-- MySQL 에서 옮기며 바꾼 규칙
--   - ENUM('A','B')        → VARCHAR(30) + CHECK (칸 IN ('A','B')), 제약 이름 ck_<표>_<칸>
--                            (정렬은 ENUM 선언 순서가 아니라 글자 순서가 됨)
--   - DATETIME             → TIMESTAMP(0)   (초 단위, MySQL DATETIME 과 같은 정밀도)
--   - TINYINT              → SMALLINT,  JSON → JSONB
--   - 칸/표 COMMENT        → 표 아래 COMMENT ON TABLE / COLUMN 문
--   - KEY idx_... (...)    → 표 아래 CREATE INDEX 문,  UNIQUE KEY → CONSTRAINT uk_... UNIQUE
--   - ON UPDATE CURRENT_TIMESTAMP → 아래 set_updated_at() 트리거
--   - 대소문자: 따옴표 없이 쓴 이름은 소문자로 저장된다 (resAccount → resaccount).
--     SQL 에서는 resAccount 로 써도 찾아지지만, 조회 결과의 칸 이름은 소문자로 나온다.
--   - 글자 비교: MySQL utf8mb4_0900_ai_ci 는 대소문자를 구분하지 않았지만 PostgreSQL 은 구분한다
--     (username = 'Kim' 과 'kim' 이 다름, UNIQUE 도 다른 값으로 봄).
-- =====================================================================

SET client_encoding = 'UTF8';

-- 이 DB에 새로 접속하는 모든 세션(01~07 파일, seed.sql, 앱)의 기본 시간대
DO $$
BEGIN
  EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'Asia/Seoul');
END
$$;
SET timezone = 'Asia/Seoul';

-- MySQL 의 ON UPDATE CURRENT_TIMESTAMP 대신 쓰는 트리거 함수
--   행 내용이 실제로 바뀌었고, UPDATE 문이 updated_at 을 직접 정하지 않았을 때만 지금 시각으로 바꾼다
--   (MySQL 동작과 같음). 쓰는 표: account_balances, scheduled_transfers, transfer_limits,
--   card_applications, user_card_settings
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  IF NEW IS DISTINCT FROM OLD AND NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
    NEW.updated_at := CURRENT_TIMESTAMP;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
