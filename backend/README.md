# 두린은행 계좌·거래 API

`docs/기획서.md` 스키마(`docs/sql/00~07`, 표 61개 + 보기 1개)를 PostgreSQL 에 올리고, 계좌·거래 데이터를 읽는 API.
데이터는 지어내지 않고 `data/dummy`(더미)와 `scripts/seed_scenarios.py`(더미에 없는 기능의 시나리오 시드)를 쓴다.

```
[내 PC] Docker ─▶ PostgreSQL 17 컨테이너 midproject-postgres (localhost:5433, app/app)
                    ├─ midproject       개발용: docs/sql + 더미 + 시나리오 시드
                    └─ midproject_test  테스트용: pytest 가 실행할 때마다 같은 방법으로 새로 만듦
        FastAPI 앱 ── SQLAlchemy 2 + psycopg 3 ── postgresql+psycopg://app:app@localhost:5433/midproject
```

## 1. DB 띄우기 (Docker)
```bash
docker compose up -d --wait                # 첫 기동 때 docs/sql 로 표 61개 + 보기 1개를 만든다(데이터 없음)
```
- 첫 기동(빈 볼륨) 때 `db/init/` 을 실행한다: `01_test_db.sql` 이 테스트 DB `midproject_test` 를 만들고,
  `02_schema.sh` 가 `../docs/sql/00~07` 을 `midproject` 에 만든다.
- `../docs/sql` 을 고친 뒤에는 `docker compose down -v` → `docker compose up -d --wait` 로 다시 만든다(볼륨의 데이터도 지워짐).
  그 다음 아래 2번(데이터)과 3번(모델 다시 만들기)을 한다.
- 포트가 5433 인 이유: 이 PC 에 설치된 PostgreSQL 17 서비스가 이미 5432 를 쓰고 있다.
- DB 안을 직접 보려면 `docker exec -it midproject-postgres psql -U app -d midproject`
  (CODEF 이름 칸은 `SELECT "resAccount" FROM accounts;` 처럼 따옴표로 감싼다 — 기획서 C-5).

## 2. 데이터 넣기 (저장소 맨 위 폴더에서)
```bash
backend/.venv/Scripts/python scripts/load_dummy.py > dummy.sql                # data/dummy → INSERT SQL
docker exec -i midproject-postgres psql -U app -d midproject -v ON_ERROR_STOP=1 < dummy.sql
backend/.venv/Scripts/python scripts/seed_scenarios.py > seed_scenarios.sql    # 로그인 해시·이체 한도·타행·예약 등
docker exec -i midproject-postgres psql -U app -d midproject -v ON_ERROR_STOP=1 < seed_scenarios.sql
```
- 순서: 더미 먼저, 시나리오 시드 나중(시드가 더미의 회원·계좌·카드를 가리킨다). 둘 다 여러 번 넣어도 결과가 같다.
- 시나리오 시드는 예약 시각 등을 "지금" 기준으로 만든다. 다시 맞추려면 `seed_scenarios.py --reset`.
- 만든 `.sql` 파일은 커밋하지 않는다.
- 카드 혜택·실적 구간·연회비는 `data/dummy/cards/card_benefits.json`(실제 카드 참고, 출처 `docs/domain-rules.md` 7장)에서 같이 들어간다.
  INSERT 가 `ON CONFLICT DO NOTHING` 이라 **이미 있는 행은 바뀌지 않는다** — 혜택 파일의 연회비·요약을 고쳤으면 개발 DB 의
  `card_products`·`user_cards.annual_fee_amount` 는 직접 UPDATE 하거나 DB 를 다시 만든다(테스트 DB 는 매번 새로 만들어 상관없음).

### 2-1. 챗봇 RAG 벡터 (`data/rag` md → `rag_parents`·`rag_chunks`, `docs/sql/08_rag.sql`)
```bash
backend/.venv/Scripts/python scripts/rag_ingest.py --save                        # .env 에 GEMINI_API_KEY 필요
backend/.venv/Scripts/python scripts/rag_ingest.py --query "정기예금 중도해지 이율"   # 저장 확인 (--mode vector|bm25|hybrid, 기본 hybrid)
```
- 이미지가 `pgvector/pgvector:pg17` 이다. 예전 `postgres:17` 볼륨이면 `docker compose up -d` 만 다시 하고 `08_rag.sql` 을 위 2번처럼 넣는다.
- 청킹 방식 비교는 `--experiment <이름>` 으로 나란히 저장한다. 같은 글의 벡터는 재사용한다.

## 3. 모델 (`app/models/`)
`docs/sql` 이 원본이고, 모델은 `scripts/gen_models.py` 가 DB 를 읽어 만든다 — **손으로 고치지 않는다**.
```bash
backend/.venv/Scripts/python scripts/gen_models.py      # docs/sql 을 고치고 DB 를 다시 만든 뒤
```
| 모듈 | 원본 | 표 |
|---|---|---|
| `users.py` | `01_users.sql` | 회원·인증 10 (`sessions` 표의 클래스 이름은 `AuthSession` — `sqlalchemy.orm.Session` 과 겹치지 않게) |
| `accounts.py` | `02_accounts.sql` | 계좌 5 |
| `transactions.py` | `03_transactions.sql` | 거래 7 + 보기 `AccountBalanceView` |
| `deposit_products.py` | `04_deposite_products.sql` | 예금·적금 상품 6 |
| `card_products.py` | `05_card_products.sql` | 카드 상품·발급·보유 19 (약관 `Terms`·동의, 혜택 통합 한도 `CardBenefitLimitGroup` 포함) |
| `card_usage.py` | `06_card_usage.sql` | 카드 이용·청구·분석·포인트 13 |
| `notifications.py` | `07_notifications.sql` | 알림 1 |

- `CHECK (칸 IN (...))` 의 허용 값은 클래스 상수로 쓴다: `Account.LIFECYCLE_STATUS_VALUES`, `Transaction.TYPE_VALUES` …
- 기본값은 DB 가 채운다(`server_default`). `accounts.version` 은 낙관적 잠금(`version_id_col`).
- `account_activity_logs.metadata` 칸은 속성 이름이 `metadata_` 다(SQLAlchemy 예약어).
- `_base.py` 만 손으로 쓴 파일이다(기반 클래스, `TS` = `TIMESTAMP(0)`, `one_of()`).

## 4. 앱 실행
```bash
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8010
```
http://localhost:8010/docs 에서 호출 (화면 `frontend/` 가 8010 을 부른다 — 아래 「화면 연결」). 먼저 `POST /auth/login` 으로 로그인하면 브라우저에 쿠키가 저장되고, 그 뒤 호출은 그 회원으로 처리된다.
시드 회원의 아이디는 `users.username`(예: `minjun_kim` = user_001), 비밀번호는 모두 `backend/.env` 의 `SEED_PASSWORD`.

**로그인 (기획서 Part 1 AUTH-F05)** — `app/routers/auth.py`, `app/deps.py`, `app/security.py`
- 서버 세션 + 쿠키 `sid`(HttpOnly·SameSite=Lax). DB `sessions.id` 에는 쿠키 원문이 아니라 해시(`ses_…`)만 둔다.
- 세션 만료: **유휴 10분**(마지막 요청 기준) · **최대 12시간**(로그인 기준, 써도 안 늘어남) → 401 `SESSION_EXPIRED`. 로그아웃하면 바로 끊긴다.
- 실패: 없는 아이디·틀린 비밀번호·탈퇴 회원 모두 401 `INVALID_CREDENTIALS` 하나(계정 존재 여부를 숨김).
  같은 아이디가 5번 연속 틀리면 1분 동안 429 `LOGIN_TOO_MANY_ATTEMPTS`(서버 메모리, 재시작하면 초기화).
- 로그인 실패는 `local_credentials.failed_attempts` 에 세지 않는다 — 기획서 6.3: 그 칸은 **본인 확인(step-up) 실패만** 센다.
- 회원 상태별 허용(Part 1 7.3): `ACTIVE`·`RESTRICTED` 사용 가능, `PENDING_VERIFICATION` 은 로그인·`/users/me` 만(나머지 403), `WITHDRAWN`·없는 회원 401.
- 상태를 바꾸는 요청(POST·PATCH·DELETE)은 CORS 허용 주소나 이 API 자신에서 온 것만 받는다(그 밖의 `Origin` 은 403, CSRF 방어).
- 개발용 `X-User-Id` 헤더: `backend/.env` 에 `AUTH_DEV_HEADER=true` 일 때만 쓰인다(기본 꺼짐). 테스트는 이 설정을 켜고 돈다.

**CORS** — 화면(프런트엔드)을 다른 포트로 띄워 이 API 를 부를 수 있게 허용한다(`app/main.py`).
- 허용 주소: `http://localhost:5173`·`http://127.0.0.1:5173`(Vite), `http://localhost:3000`·`http://127.0.0.1:3000`(Next·CRA).
  바꾸려면 `backend/.env` 에 `CORS_ORIGINS=주소1,주소2` (`app/config.py` 기본값 참고).
- 로그인 쿠키를 주고받도록 `allow_credentials=True` — 그래서 허용 주소를 `*` 로 둘 수 없다.
  화면에서는 요청마다 쿠키를 같이 보내야 한다: `fetch(url, { credentials: "include" })` / axios `withCredentials: true`.

## 5. API (기획서 경로)
| 기능 | 엔드포인트 | 기획서 | 위치 |
|---|---|---|---|
| 로그인 · 로그아웃 | `POST /auth/login`, `POST /auth/logout` | Part 1 AUTH-F05 | `routers/auth.py` |
| 가입 약관 목록 | `GET /terms` | Part 1 AUTH-F10 | `routers/signup.py` |
| 약관 본문 (로그인 없이. `content_url` 의 `.md` 를 읽어 앞머리·맨 위 제목을 뺀 Markdown, `data/`·`docs/` 밖이거나 파일이 없으면 `content: null`) | `GET /terms/{terms_id}` | Part 1 AUTH-F10 | `routers/signup.py` |
| 약관 및 동의 내역 (약관마다 마지막 동의 상태 · 선택 약관만 변경, 이력은 새 행으로 쌓음. 필수 약관 변경 400 `REQUIRED_TERMS_LOCKED`) | `GET /users/me/consents`, `PATCH /users/me/consents` | Part 1 AUTH-F10 · UI08 | `routers/consents.py` |
| 아이디 중복 확인 (`available` true/false, 형식 오류 400) | `GET /auth/usernames/availability?username=` | Part 1 AUTH-F02 | `routers/signup.py` |
| 이메일 인증번호 발송(SMTP 메일, `app/mailer.py` — `.env` 의 `SMTP_*`, 비면 서버 콘솔에 번호)·확인 | `POST /auth/email-verifications`, `POST /auth/email-verifications/confirm` | Part 1 AUTH-F03 | `routers/signup.py` |
| 회원가입 (성공하면 바로 로그인 쿠키) | `POST /auth/register` | Part 1 AUTH-F01 | `routers/signup.py` |
| 본인 확인 (로그인 비밀번호 `password` 또는 간편 비밀번호 `pin` → 5분·1회·그 작업·그 세션 한정 번호. 비밀번호 5번 틀리면 영구 잠금 423 `STEP_UP_LOCKED`, PIN 5번 틀리면 10분 잠금 423 `PIN_LOCKED`) | `POST /auth/step-up` | Part 1 7장·9.3·AUTH-F12 | `routers/auth.py` (`consume_step_up()` 은 작업 API 가 부름) |
| 간편 비밀번호(PIN) 상태 · 만들기 · 바꾸기 · 다시 정하기 (본인 확인 `PIN_ENROLL`(비밀번호) · `PIN_CHANGE`(지금 PIN) · `PIN_RESET`(비밀번호) 뒤 숫자 6자리 두 번. 같은 숫자·이어지는 숫자·생년월일 금지, 바꾸기는 지금 PIN 과 같은 번호도 금지) | `GET /auth/pin`, `POST /auth/pin/enroll` · `/change` · `/reset` | Part 1 AUTH-F11·F13 | `routers/pin.py`, 금지 규칙 `rules.pin_error` |
| 탈퇴 전 3단계 점검 (① 남은 돈 ② 삭제될 데이터 ③ 연결된 서비스, 막는 항목과 이동할 화면) | `GET /users/me/withdrawal-checks`, `POST …/data-review`, `POST …/linked-services` | Part 1 AUTH-F09 | `routers/withdrawal.py` |
| 회원 탈퇴 (본인 확인 `WITHDRAWAL` → ①②③ 재검사 → 남은 계좌 일괄 해지 → `WITHDRAWN`·세션 끊기·동의 철회·즉시 삭제) | `POST /users/me/withdraw` | Part 1 AUTH-F09 | `routers/withdrawal.py`, 다른 파트 조회는 `app/internal.py` |
| 내 정보 (가입 마무리 중에도 가능) | `GET /users/me` | Part 1 AUTH-F07(조회만) | `routers/users.py` |
| **계좌 개설** (`CHECKING`·`SAVINGS`, `consents` 에 `required_terms` 필수, `Idempotency-Key` 필수, 회원 `ACTIVE` 만, 본인 확인 `ACCOUNT_OPEN`(PIN·비밀번호), 아래 「계좌 개설」) | `POST /accounts` | Part 2 ACCT-F01 | `routers/accounts.py` + `app/ledger.py` |
| 내 계좌 목록 (+잔액, 해지 계좌는 `?status=CLOSED` 로만, `?type=`) | `GET /accounts` | Part 2 ACCT-F02·F07 | `routers/accounts.py` |
| 계좌 상세 (+잔액, 해지 막힘 사유 `close_blockers`) | `GET /accounts/{accountId}` | ACCT-F02·F05 | `routers/accounts.py` |
| 잔액 (`account_balance_view`) | `GET /accounts/{accountId}/balance` | ACCT-F03 | `routers/accounts.py` |
| 거래내역 (`start_date`·`end_date`·`direction=IN/OUT`·`limit`·`cursor`) — 화면은 1·3·6개월·직접 | `GET /accounts/{accountId}/transactions` | Part 5 TRX-F03 | `routers/transactions.py` |
| 거래 상세 | `GET /transactions/{transactionId}` | Part 5 16장 | `routers/transactions.py` |
| 이체 결과 목록·상세 (`?status=`·`start_date`·`end_date`·`account_id` — 계좌 상세의 「이체 결과」) | `GET /transfers`, `GET /transfers/{transferId}` | Part 5 TRX-F02 | `routers/transfers.py` |
| 이체확인증 (성공한 이체만, 계좌번호 앞 3·뒤 3자리만) | `GET /transfers/{transferId}/receipt` | Part 5 TRX-F06 | `routers/transfers.py` |
| 예약 송금·자동이체 목록·상세 | `GET /scheduled-transfers`, `GET /scheduled-transfers/{scheduledTransferId}` | Part 5 8·16장 | `routers/transfers.py` |
| 이체 한도와 오늘 남은 한도 · 한도 변경(1만 원 단위, 상한 1회 1억·1일 5억, 올릴 때만 본인 확인 `TRANSFER`) | `GET`·`PATCH /accounts/{accountId}/transfer-limits` | Part 5 TRX-F07·F13 | `routers/transfers.py` |
| 이체 대상 확인 (예금주·상태·내 계좌 여부, `from_account_id`·`amount` 를 주면 같은 계좌 막기·재확인 경고 4종) | `GET /transfer-targets/verify?bank=&account_no=` | Part 5 4·9·11장 | `routers/transfer_targets.py` |
| 자주 쓰는 계좌 (최대 20개, 별칭·순서·삭제) | `GET`·`POST /favorite-accounts`, `PATCH`·`DELETE /favorite-accounts/{favoriteId}` | Part 5 TRX-F05 | `routers/favorites.py` |
| **이체 실행** (두린은행·가상 타행, `Idempotency-Key` 필수, 본인 확인 `TRANSFER`, 잔액·한도·상태 실패는 `FAILED` 결과) | `POST /transfers` | Part 5 4·9·11·14장 | `routers/transfers.py` + `app/ledger.py` |
| 최근 보낸 계좌 (두린은행만, 최근 10개, 숨기기는 뺌) | `GET /transfer-targets/recent` | Part 5 TRX-F05 | `routers/transfer_targets.py` |
| **예약 송금(ONCE) · 자동이체(MONTHLY) 등록** · 변경 · 취소/해지 (본인 확인 `SCHEDULED_TRANSFER`, 변경·취소는 실행 10분 전까지) | `POST /scheduled-transfers`, `PATCH`·`DELETE /scheduled-transfers/{id}` | Part 5 TRX-F10·F11 | `routers/transfers.py` + `app/jobs.py` |
| 알림 목록 · 모두 읽음 · 계좌 알림 설정(켬·입금/출금·최소 금액) | `GET /notifications`, `POST /notifications/read-all`, `GET`·`PATCH /accounts/{accountId}/notification-settings` | Part 2 ACCT-F06 | `routers/notifications.py` |
| 다른 은행 이체내역 (CODEF 더미) · 예적금 내역 (CODEF 샌드박스) — user_001 만 | `GET /external-transfers`, `GET /external-deposit-accounts/{accountNo}/transactions` | Part 5 TRX-F09·F14 | `routers/external.py` + `app/codef.py` |
| 계좌 일시정지 · 정지 해제 · 해지 (본인 확인 `ACCOUNT_STATUS_CHANGE`, 아래 「계좌 상태」) | `POST /accounts/{accountId}/suspend`·`/resume`·`/close` | Part 2 ACCT-F05 | `routers/accounts.py` + `app/internal.py` |
| 예금·적금 상품 목록(`q`·`type`·`sort=rate`)·홈 추천·상세(금리표·가입 조건·상품설명서 목록) — 로그인 없이 | `GET /products`, `GET /products/recommended`, `GET /products/{productId}` | Part 3 PROD-F01~F04 | `routers/products.py` |
| 예상 이자 (단리·세전·기본 금리, 아래 「상품」) — 로그인 없이 | `POST /products/{productId}/estimate` | Part 3 PROD-F05·F06 | `routers/products.py` |
| 가입 직전 검사 · 가입 (본인 확인 `SUBSCRIPTION`, `Idempotency-Key` 필수, 원장 `SUBSCRIPTION_PAYMENT`) | `POST /products/{productId}/validate`, `POST /subscriptions` | Part 3 PROD-F07·F08 | `routers/products.py` |
| 내 예금·적금 목록·상세 | `GET /users/me/subscriptions(/{id})` | Part 3 7장 | `routers/subscriptions.py` |
| 예금·적금 중도 해지 (원금만 출금 계좌로, 본인 확인 `SUBSCRIPTION`) | `POST /subscriptions/{id}/terminate` | Part 3 PROD-F10 | `routers/subscriptions.py` |
| 내 카드 모아보기 (해지한 카드 빼고, 신용=이번 기간 사용액·낼 돈, 체크=이번 달 쓴 돈) | `GET /cards` | Part 4 CARD-F01 (1-1-1) | `routers/cards.py` |
| 카드 상세 (혜택·지난달/분기 실적·청구서, 해지한 카드도 기록으로) | `GET /cards/{cardId}` | Part 4 CARD-F02 (1-1-2) | `routers/cards.py` + `app/card_benefits.py` |
| 카드 이용 내역 (`month=YYYYMM`·`category=업종 code`(하위 업종 포함)·`installment=LUMP_SUM/INSTALLMENT`, 최신순) | `GET /cards/{cardId}/transactions` | Part 4 CARD-F03 (1-1-3) | `routers/cards.py` |
| 결제 캘린더 (내 모든 카드 청구서 + 이번 기간, 결제 계좌 잔액 부족 `low_balance`) · 청구서 상세(든 이용 내역) | `GET /card-bills`, `GET /card-bills/{billId}` | Part 4 CARD-F04 (1-1-4) | `routers/card_bills.py` |
| 카드 해지 전 확인 · 해지 (본인 확인 `CARD_TERMINATION`) | `GET /cards/{cardId}/termination-check`, `POST /cards/{cardId}/terminate` | Part 4 CARD-F09 (1-3) | `routers/cards.py` |
| 카드 대금 지금 결제하기 (확정·연체 청구서, 해지한 카드는 이번 기간 사용액까지, 본인 확인 `CARD_MANAGEMENT`) | `POST /cards/{cardId}/payments` | Part 4 CARD-F07 (1-7) + 사용자 결정 | `routers/cards.py` |
| 챗봇 (아래 「챗봇」) | `POST /agent/chat` | Part 3 5·7장 | `routers/agent.py` + `app/agent.py` + `app/rag.py` |

**계좌 개설 (`POST /accounts`, ACCT-F01)** — 한 트랜잭션에 계좌 + 잔액 0원(`ledger.open_balance`) + 알림 기본값 + 개설 기록(`account_activity_logs.action = 'OPEN'`).
- 본인 확인: 요청의 `step_up_challenge_id` 는 `POST /auth/step-up`(`ACCOUNT_OPEN`, PIN 이나 로그인 비밀번호)으로 받은 번호. 회원 상태 검사 뒤, 새로 만들 때만 쓴다 — 같은 `Idempotency-Key` 재요청은 이미 쓴 번호여도 처음 계좌를 돌려준다. 개발용 `X-User-Id` 헤더는 세션이 없어 개설할 수 없다.
- 계좌번호: `110` + 무작위 11자리 = 14자리, 화면 번호는 `110-XXXXX-XXXXXX`(숫자를 빼지 않음). 이미 있는 번호면 다시 뽑는다. 더미 계좌의 화면 번호(`110-00-000001`)는 원래 모양 그대로 둔다.
- 기본 계좌 이름(`resAccountName`): `CHECKING` 입출금통장 · `SAVINGS` 저축예금 (`app/rules.py` `ACCOUNT_PRODUCT_NAMES`, 더미와 같음).
- 중복 요청: `accounts` 에 멱등 키 칸이 없어 개설 기록의 `metadata.idempotency_key` 에 둔다(회원마다 따로). 회원 행을 `FOR UPDATE` 로 잠가 같은 키 동시 요청도 계좌 하나. 같은 키로 다시 오면 처음 계좌를, 다른 유형이면 409 `IDEMPOTENCY_KEY_REUSED`.
- 약관 동의는 `metadata.consents` 에만 남긴다 — `terms` 표에 넣으면 가입 화면(`GET /terms`, 카드 약관이 아닌 것 전부)에 섞여 나온다.
- 오류: 422 `INVALID_ACCOUNT_TYPE` · `REQUIRED_TERMS_NOT_AGREED`, 403 `USER_NOT_ACTIVE`(RESTRICTED) · `SIGNUP_INCOMPLETE`. 1인당 계좌 수 제한은 없다(기획서 Part 2 14장 「초기에는 별도 제한 없이」).

**계좌 상태 (ACCT-F05)** — 일시정지 `ACTIVE → SUSPENDED` · 정지 해제 `SUSPENDED → ACTIVE` · 해지 `ACTIVE → CLOSED`. 셋 다 계좌 행을 잠그고 본인 확인 뒤 활동 기록(`SUSPEND`·`RESUME`·`CLOSE`, `metadata.from_status`)을 남긴다.
- 그 밖의 전이는 409: 이미 정지 `ACCOUNT_ALREADY_SUSPENDED`, 정지 아님 `ACCOUNT_NOT_SUSPENDED`, 정지 계좌 해지·해지 계좌 정지/재해지 `INVALID_STATUS_TRANSITION`.
- 해지 조건(잔액 행도 잠근 채 검사): 잔액 0 · 그 계좌에서 나가는 처리중 이체·예약 송금·자동이체(활성·일시정지) 없음 · 그 계좌가 출금 계좌인 진행 중 예금·적금 없음 · 그 계좌에 연결된 우리 발급 카드 없음(해지했어도 낼 대금이 남으면 막음).
  기준은 회원 탈퇴 점검과 같은 함수(`app/internal.py` 의 `*_blockers(…, account_id)`)다. 막히면 409 `ACCOUNT_CLOSE_NOT_ALLOWED` + `error.reasons`(`BALANCE_REMAINING`·`PENDING_TRANSFER`·`LINKED_SUBSCRIPTION`·`LINKED_CARD`).
- 점검이 실패하면(예외·쿼리 오류) **그 점검의 사유로 막는다**(사용자 결정 2026-11-10) — 카드 점검 실패면 `LINKED_CARD`. 서버 로그에 `계좌 해지 점검 실패` 로 남아 진짜 카드와 구별할 수 있다.
  점검마다 저장점(`begin_nested`)을 둬서, 쿼리 하나가 실패해도 나머지 점검과 계좌 상세는 그대로 돈다.
- 잠그는 순서는 잔액 행 → 계좌 행. 이체·탈퇴 일괄 해지·중도 해지가 모두 잔액 행을 먼저 잠그므로, 순서를 맞춰 서로 기다리다 멈추지(데드락) 않게 했다.
- 해지는 삭제가 아니다: `closed_at` 을 쓰고 즐겨찾기만 푼다. 별명·거래 기록은 남는다.
- 이체(`POST /transfers`)는 잔액 행을 잠근 뒤 계좌 상태를 다시 읽는다 — 해지·정지와 동시에 온 이체가 잠그기 전 상태를 믿고 돈을 넣지 않게.

**거래 (Part 5, 사용자 결정 2026-11-10)** — `routers/transfers.py` · `transfer_targets.py` · `favorites.py` · `notifications.py` · `external.py`, `app/jobs.py`
- 받는 계좌 찾기는 `transfer_targets.find_target()` 하나 — 이체·예약·자주 쓰는 계좌 등록이 같이 쓴다.
- 재확인 경고(4·9장, 기획서 예시 값 그대로 `app/rules.py`): 처음 보내는 분 100만 원 이상 `FIRST_LARGE` · 이전 평균의 10배 이상 `LARGE_VS_USUAL` ·
  10분 안 같은 금액 `RECENT_SAME` · 같은 분께 처리중 이체 `PENDING_SAME`(금액·시각 함께).
- 예약 등록: 회원 `ACTIVE` 만, 두 계좌 정상, 1원 이상·1회 한도 이하(잔액·1일 한도는 실행 때). ONCE 는 10분 단위·10분 뒤~1년 안,
  MONTHLY 는 1~28일 또는 99(말일)·시작 월은 이번 달부터.
- 입출금 알림(TRX-F04 → ACCT-F06): `ledger.post()` 가 원장 한 줄마다 `notifications.on_transaction_confirmed()` 를 같은 트랜잭션에서 부른다.
  계좌 알림 설정(끔·입금/출금·최소 금액)을 보고, 알림을 못 만들어도 거래는 그대로(로그만). 설정 행이 없으면 전부 켬.
- 잔액 채우기 제안(TRX-F12): `GET /card-bills` 에 `account_id`(결제 계좌)·`shortfall`(모자란 돈). 화면은 `#/transfer?toAccount=…&amount=…&at=결제일 전날 18:00`.
- 다른 은행 내역은 회원 ↔ 다른 은행 계좌 연결 표가 없어 `external.LINKED` 에 user_001 만 적어 둠(shortcut). F14 는 샌드박스가 조건과 상관없이 같은 견본을 준다.
  `pip install -r requirements.txt` 에 `easycodefpy`·`requests` 가 들어갔다.

**챗봇 (`POST /agent/chat`)** — LangGraph 로 `llm → tools → llm …` 과 가입 확인(`tools → confirm`)을 직접 그렸다(`app/agent.py`).
- 인증 게이트: 로그인 없이도 쓴다. **손님은 문서·상품 검색 Tool 만**, 회원은 아래 조회 Tool 과 가입 준비까지 — LLM 에 묶는 Tool 목록과 실행하는 ToolNode 를 둘 다 바꾼다.
  쿠키가 있는데 끊긴 세션은 손님이 아니라 401, 가입 마무리 중은 403(다른 보호 API 와 같음). `user_id` 는 LLM 인자가 아니라 세션 → 그래프 config.
- 요청 `{message, context?}` → 응답 `{reply, links, suggestions, context}`. 빈 `message` 는 인사(LLM 안 부름).
  화면은 응답 `context`(`history` 최근 20개 + 회원 대화 번호 `thread_id`)를 다음 요청에 그대로 돌려보낸다.
  회원 대화는 서버 메모리(`InMemorySaver`, thread 키 `<user_id>:<thread_id>`)에도 남아 상태(직전 상품·금액·기간)와 확인 대기를 이어 간다.
  서버를 다시 켜면 사라지고, 그때는 `history` 로 새로 시작한다(확인 대기도 사라짐 — 다시 말하면 다시 묻는다).
- Tool: 문서 검색(RAG, 벡터+BM25 를 RRF 로) · 예금·적금 상품 목록·상세 · 가입 준비 · 내 계좌·잔액 · 내 예금·적금 · 계좌 거래내역 · 이체 내역.
  Tool 은 기존 API 함수(계좌·거래·이체·상품)를 그대로 불러 **로그인한 본인 것만** 읽는다(남의 계좌는 `ACCOUNT_NOT_FOUND` 를 LLM 에 돌려줌).
  송금·가입·해지는 하지 않는다.
- **가입 실행 전 확인**: `prepare_subscription` 이 이번에 들은 값만 받아 이전 상품·금액·기간과 합치고, 회원 상태·판매 중·금액·기간·정상 입출금 계좌·1인당 개수를
  **상품 API 의 검사 함수**(`routers/products.py` `estimate`·`check_user`·`check_limit`)로 본다
  (빠지면 `MISSING`, 틀리면 `AMOUNT_OUT_OF_RANGE`·`TERM_OUT_OF_RANGE`·`NOT_SUBSCRIBABLE`·`NO_SOURCE_ACCOUNT` 등 → LLM 이 되묻거나 그대로 전함).
  다 맞으면 `confirm` 노드가 `interrupt` 로 멈추고 DB 값과 예상 이자 계산으로 만든 요약(금리·만기일·세전 이자·만기 금액)을 묻는다(`suggestions: ["네", "아니요"]`).
  '네' → 가입 화면 링크 `#/products/<id>/subscribe?amount=…&months=…`(일 단위 상품은 `days=`) — 출금 계좌 선택과 본인 확인(step-up)은 그 화면에서.
  '아니요' → 취소. 그 밖의 말 → LLM 이 새 요청으로 받는다(상태는 유지). 가입 화면 링크는 '네' 답에서만 살린다(LLM 이 직접 적으면 버림).
- `backend/.env`: `GEMINI_API_KEY`(없으면 챗봇만 503 `CHAT_UNAVAILABLE`), `CHAT_MODEL`(기본 `gemini-2.5-flash`), `RAG_EXPERIMENT`(기본 `pc-1000`, 위 2-1).
- 서버를 켠 뒤 첫 문서 검색은 BM25 인덱스를 만드느라 10초 넘게 걸린다. `rag_ingest.py --save` 로 다시 채우면 서버를 다시 켠다.

**상품 (`routers/products.py`)** — 규칙은 Serin 브랜치 `backend/app/crud.py` 를 옮겼다(사용자 결정 2026-11-10). 상품·금리·조건은 `data/dummy/products/products.json` 이 원본.
- [모의 규칙] 이자는 단리·세전·원 미만 버림, **기본 금리만**(우대 판정은 3차). 예금 = 원금 × 연이율 × 개월/12(일 단위 × 일수/365),
  적금 = 납입마다 납입액 × 연이율 × 만기까지 꽉 찬 개월/12. 만기일은 같은 날짜의 N개월 뒤(없으면 말일).
- 가입 불가: 금리표 없는 상품(`NOT_SUBSCRIBABLE`, prod_010·014·031·032) · N일 적금(`TERM_UNIT_NOT_SUPPORTED`, 매일 자동 납입이 필요).
- 가입은 `ACTIVE` 회원만, 출금 계좌는 본인 정상 입출금 계좌, 잔액 ≥ 첫 납입액, 1인당 개수(`max_per_user`). 이체 한도는 세지 않는다(본인 계좌 사이, 사용자 결정 2026-11-10).
  계약(가입 당시 적용 금리 저장) · 적금 첫 회차 납입 기록 · 원장 출금이 한 트랜잭션. 같은 `Idempotency-Key`(회원별)로 다시 오면 처음 결과, 내용이 다르면 409.
- 상품설명서 연결(`product_documents`)은 `scripts/load_dummy.py` 가 `data/rag/products/*.md` 파일 이름에서 만든다. 상세 응답에 제목·RAG 문서 이름만 주고 파일은 내려주지 않는다
  (원본 문서에 실제 은행 이름이 있어서, 사용자 결정 2026-11-10). 이미 만든 개발 DB 에는 `load_dummy.py` 를 다시 넣으면 더해진다(ON CONFLICT DO NOTHING).

응답 형식 (기획서 C-5): 금액은 **문자열**(`"resAccountBalance": "1250000"`), 시각은 `+09:00` ISO 8601,
CODEF `res…` 빈 칸은 `""`, 우리가 만든 빈 칸은 `null`. 거래에는 `direction`(`IN`/`OUT`, Part 5 3장)이 붙는다.

오류 형식 (기획서 Part 1 7.1): `{"success": false, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "계좌를 찾을 수 없어요."}}`
— 남의 것과 없는 것은 똑같이 404(존재 여부를 숨김, Part 2 ACCT-F02). 기획서 업무 규칙 값(기본 한도, 은행별 자릿수 등)은 `app/rules.py`.

아직 없는 것: 예약 등록·변경과 예약 실행 배치, 계좌 개설·설정·정지·해지, 카드 신청(1-2)·혜택 적용 계산(보여 주기만 함, `docs/BACKLOG.md`),
적금 추가 납입·만기 처리(PROD-F11), Google 로그인.

**예약 작업 (`app/jobs.py`)** — 서버가 켜져 있으면 서버 안 스케줄러(`app/main.py` lifespan 스레드)가 1분마다 `run_minutely()` 로 아래를 모두 돌린다
(사용자 결정 2026-11-10, 끄려면 `.env` 에 `SCHEDULER_ENABLED=false` — 테스트는 끔). 손으로 한 번: `.venv\Scripts\python -m app.jobs`
| 함수 | 하는 일 | 주기 |
|---|---|---|
| `run_scheduled_transfers` | 실행 시각이 된 예약 송금·자동이체를 일반 이체와 같은 규칙(`run_transfer`)으로 실행. ONCE 는 `SCHEDULED→PROCESSING` 을 먼저 차지한 쪽만, 자동이체는 회차 키 `SCH-{id}-{yyyyMMdd}` 로 한 번만. 실패하면 `TRANSACTION` 알림(성공 알림은 원장 이벤트가 만듦). 자동이체는 06:00, 재시도·정지 없음, 종료 월을 넘기면 `SUCCESS` | 1분마다 |
| `purge_withdrawn_users` | 탈퇴 1개월 지난 회원 가명 처리 | 하루 한 번 |
| `settle_pending_transfers` | 10분 넘게 처리중인 타행 이체를 잔액·상태를 다시 보고 SUCCESS/FAILED 로 확정 (예약으로 보낸 건이면 예약 상태·실패 알림도) | 몇 분마다 |
| `notify_card_payments` | 카드 결제일 D-3·당일 `PAYMENT_DUE` 알림, 결제 계좌 잔액이 모자라면 `LOW_BALANCE` 알림(같은 계좌 청구서를 결제일 순으로 더해 봄). 카드 설정에서 알림을 끈 카드는 건너뜀, 같은 알림은 한 번만 | 하루 한 번(아침, 출금 전) |
| `pay_due_card_bills` | 결제일이 된 확정 청구서를 결제 계좌에서 출금, 모자라면 연체(`OVERDUE`) + 알림 | 하루 한 번 |

**회원 탈퇴 전 정리 (사용자 결정 2026-11-09)** — 기존 회원도 모두 탈퇴할 수 있게 앞당겨 만든 것: 계좌 정지 해제, 적금 중도 해지, 이체(타행 포함), 예약·자동이체 취소, 카드 대금 선결제·해지.
- 남은 돈은 회원마다 시드한 **본인 명의 타행 계좌**(`external_accounts.id = ext_<회원 id>`, 예금주 = 회원 이름)로 보낸다. 이용 제한(`RESTRICTED`) 회원은 본인 명의로만 보낼 수 있다.
- 타행 시험 계좌: 예금주 「임처리」는 `PENDING` → 10분 뒤 확정, 「오실패」는 `FAILED` (`app/rules.py`).
- 탈퇴 ③은 해지 안 된 카드뿐 아니라 **해지했어도 낼 대금이 남은 카드**도 막는다(카드 계산: 쓴 돈 − 낸 돈). 결제 계좌에 돈이 모자라면 결제가 거절되어 탈퇴할 수 없다.
- 잔액을 바꾸는 일(이체·중도 해지·카드 대금)은 모두 `app/ledger.py` 로: 잔액 행을 계좌 id 순서로 잠그고 → 원장 한 줄 + 잔액 변경.

**회원 탈퇴 (AUTH-F09) 정한 것 — 사용자 결정 2026-11-09**
- 다른 파트 점검·일괄 해지는 기획서의 `/internal/...` API 대신 `app/internal.py` 함수(이름은 기획서 경로와 1:1). 팀원 서버가 생기면 그 안만 HTTP 호출로.
- 탈퇴 즉시 삭제: 비밀번호 해시·PIN·이메일 인증·재설정 토큰·알림 설정·알림·자주 쓰는 계좌·계좌 별명/즐겨찾기 + 카드 파트의 카드 설정·별명·추천·예측·고정지출 탐지·포인트·마이데이터 연동.
  세션은 끊기만(본인 확인 기록이 가리킴), 돈이 오간 기록·감사 기록·약관 동의 이력은 보존. 모든 동의는 `agreed=false` 행을 더해 철회.
- 남은 계좌는 잔액 0원일 때 모두 `CLOSED`(정지 계좌도 — `close_for_withdrawal` 예외), `account_activity_logs` 에 `CLOSE` + `{"reason": "회원 탈퇴"}`.
- 탈퇴 1개월 뒤 가명 처리: `app/jobs.py` 의 `purge_withdrawn_users()` — 이름 「탈퇴회원」, 이메일·월급일 비움, 생년월일은 그해 1월 1일, 로그인 수단 연결 삭제.
  아이디는 영원히 다시 못 쓴다. 서버 안 스케줄러가 1분마다 돌린다(아래 「예약 작업」), 손으로 한 번: `.venv\Scripts\python -m app.jobs`
- ② 안내문 버전은 `app/rules.py` 의 `WITHDRAWAL_DATA_REVIEW_VERSION` — 화면 `WithdrawPage.tsx` 의 `DATA_GROUPS` 를 바꾸면 같이 올린다.
회원가입 과정 전체(코드·DB·Docker 역할·직접 해 보기)는 `docs/가이드북_회원가입로그인.md`.

## 5-1. 화면(frontend/) 연결
```bash
# 터미널 1: DB(1번) 를 띄운 뒤 서버
cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload --port 8010
# 터미널 2: 화면
cd frontend && npm ci && npm run dev        # http://localhost:5173
```
- 로그인: 시드 회원 아이디(예: `minjun_kim` = user_001) + `backend/.env` 의 `SEED_PASSWORD`.
- 서버 주소는 `frontend/src/api.ts` 의 `API` — 기본 `http://localhost:8010`, 바꾸려면 `frontend/.env.local` 에 `VITE_API_URL=...`.
- 쿠키 로그인이라 화면 주소가 `CORS_ORIGINS`(기본 5173·3000) 안에 있어야 한다. 서버는 로그인한 응답마다
  `X-Session-Expires-At`(유휴 10분·최대 12시간 중 먼저 끝나는 시각)을 보내고, 화면은 그걸로 남은 시간·「로그인 연장」 창을 띄운다.
- 모양 맞추기는 `frontend/src/api.ts` 한 곳에서 한다: 이 서버는 기획서 C-5 이름(`resAccount…`)으로, 성공 응답을 감싸지 않고 답하므로
  `call()` 이 `{ success: true, data }` 로 감싸고 함수마다 화면 모양으로 바꾼다. 서버에 없는 주소는 `NOT_IMPLEMENTED`
  「아직 서버에 없는 기능이에요.」로 보인다(홈의 추천 상품·카드 칸은 비워 두고 나머지를 보여 줌).
- 지금 이어진 화면: 회원가입(약관·아이디 중복 확인·이메일 인증, 인증번호는 화면에 모의 메일로 표시), 로그인·로그아웃, 홈(계좌 합계), 내 계좌·계좌 상세·잔액, 거래내역, 이체 결과 목록·상세, 이체 한도 보기,
  자주 쓰는 계좌, 받는 계좌 확인, 내 정보 보기, 회원 탈퇴(3단계 점검·비밀번호 본인 확인). 카드 조회(내 카드·상세·혜택·이용 내역·결제 캘린더·청구서, 2026-11-10). 간편 비밀번호(PIN) 만들기·바꾸기·다시 정하기와 PIN 본인 확인(2026-11-10). 나머지(상품·카드 신청·알림·쓰기 기능 전부)는 서버 API 가 생기면 이어진다.

## 6. 테스트
```bash
.venv\Scripts\python -m pytest -q
```
- `tests/conftest.py` 가 `midproject_test` 를 **개발 DB 와 같은 방법**(docs/sql → load_dummy → seed_scenarios)으로 매번 새로 만든다.
  기대값은 더미·시드의 실제 값이다.
- `tests/test_models_schema.py`: 모델과 DB 의 칸·타입·NULL·기본값·키·제약·인덱스 비교(표 61개 각각). `docs/sql` 만 고치고 모델을 다시 안 만들면 여기서 실패한다.
- `tests/test_api.py`: 위 API 의 정상·실패 동작(남의 계좌 404, 회원 상태별 401/403, 자릿수 오류, 커서 페이지 등).
- `tests/test_auth.py`: 로그인·로그아웃(AUTH-F05 완료 기준, 기획서 11장 1차 QA) — 실패 시 세션 없음, 로그아웃·유휴 10분·최대 12시간 뒤 거부,
  계정 존재 숨김, 실패 속도 제한, 회원 상태별 처리, 쿠키에 HttpOnly, DB 에 쿠키 원문 없음, 다른 `Origin` 의 POST 차단.
- `tests/test_cors.py`: CORS 허용 주소·차단.
- `tests/test_signup.py`: 회원가입(AUTH-F01~F03·F10) — 정상 가입·바로 로그인, 서버 재검사(필수 약관·비밀번호·이름·생년월일),
  아이디·이메일 중복, 인증 토큰 1회용·30분, 인증번호 5분 만료·5번 오류 잠금·60초 재발송·하루 10번, 번호 원문 미저장.
- `tests/test_cards.py`: 카드 목록 조회 1차(CARD-F01~F04) — **로그인한 회원의 카드만**(쿠키 로그인, 남의 카드·청구서는 없는 것과 같은 404,
  로그아웃 즉시 401, 가입 마무리 중 403), 체크카드 이번 달 쓴 돈, 혜택(지난달 실적 구간에 따라 한도·조건, 분기 구간), 이용 내역 거르기
  (달·업종·상위 업종·할부, 잘못된 값 400/422), 결제 캘린더·같은 계좌 청구서를 더한 잔액 부족, 청구서 항목 합계, 결제일 알림(D-3·당일·한 번만·알림 끔).
- `tests/test_withdrawal.py`: 본인 확인(실패 횟수·영구 잠금·시드 user_027 잠김·세션 필요)과 탈퇴(AUTH-F09) — 새 회원 탈퇴 전체 흐름,
  잔액 0원 계좌(정지 포함) 일괄 해지·해지 사유, 잔액·자동이체·카드가 있는 user_001 차단, 최종 확인 직전 입금 시 중단(번호 재사용 가능),
  안내문 버전이 바뀌면 ② 다시, 1개월 뒤 가명 처리(아이디 유지).
- `tests/test_withdrawal_cleanup.py`: 탈퇴 전 정리 — 이체(원장 출금·입금, 멱등성, 한도·잔액 실패, 입력 오류, 타행 처리중→확정·거절, 이용 제한 회원),
  예약 취소(본인 확인·10분 잠금), 카드(미결제면 해지 거절 → 지금 결제하기 → 해지, 해지 뒤 남은 사용액이 탈퇴를 막음·잔액 부족이면 결제 거절),
  결제일 일괄 출금·연체, 그리고 **시드 회원 user_005(정지 계좌+적금) · user_024(이용 제한) · user_001(전부)을 끝까지 정리해 실제로 탈퇴**.
  시드 회원을 바꾸므로 `test_withdrawal.py` 뒤에 돌도록 이름을 정했다.
