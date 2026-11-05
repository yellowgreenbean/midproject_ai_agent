# 두린은행 계좌·거래 API

`docs/기획서.md` 스키마(`docs/sql/00~07`, 표 60개 + 보기 1개)를 PostgreSQL 에 올리고, 계좌·거래 데이터를 읽는 API.
데이터는 지어내지 않고 `data/dummy`(더미)와 `scripts/seed_scenarios.py`(더미에 없는 기능의 시나리오 시드)를 쓴다.

```
[내 PC] Docker ─▶ PostgreSQL 17 컨테이너 midproject-postgres (localhost:5433, app/app)
                    ├─ midproject       개발용: docs/sql + 더미 + 시나리오 시드
                    └─ midproject_test  테스트용: pytest 가 실행할 때마다 같은 방법으로 새로 만듦
        FastAPI 앱 ── SQLAlchemy 2 + psycopg 3 ── postgresql+psycopg://app:app@localhost:5433/midproject
```

## 1. DB 띄우기 (Docker)
```bash
docker compose up -d --wait                # 첫 기동 때 docs/sql 로 표 60개 + 보기 1개를 만든다(데이터 없음)
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
| `card_products.py` | `05_card_products.sql` | 카드 상품·발급·보유 18 (약관 `Terms`·동의 포함) |
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
.venv\Scripts\python -m uvicorn app.main:app --reload
```
http://localhost:8000/docs 에서 호출. **로그인은 아직 없다** — 지금은 `X-User-Id: user_001` 헤더로 회원을 정한다(`app/deps.py`).
회원 상태별 허용(기획서 Part 1 7.3): `ACTIVE`·`RESTRICTED` 조회 가능, `PENDING_VERIFICATION` 403, `WITHDRAWN`·없는 회원 401.

**CORS** — 화면(프런트엔드)을 다른 포트로 띄워 이 API 를 부를 수 있게 허용한다(`app/main.py`).
- 허용 주소: `http://localhost:5173`·`http://127.0.0.1:5173`(Vite), `http://localhost:3000`·`http://127.0.0.1:3000`(Next·CRA).
  바꾸려면 `backend/.env` 에 `CORS_ORIGINS=주소1,주소2` (`.env.example` 참고).
- 로그인 쿠키를 주고받도록 `allow_credentials=True` — 그래서 허용 주소를 `*` 로 둘 수 없다.
  화면에서는 요청마다 쿠키를 같이 보내야 한다: `fetch(url, { credentials: "include" })` / axios `withCredentials: true`.

## 5. API (기획서 경로)
| 기능 | 엔드포인트 | 기획서 | 위치 |
|---|---|---|---|
| 내 계좌 목록 (+잔액, 해지 계좌는 `?status=CLOSED` 로만, `?type=`) | `GET /accounts` | Part 2 ACCT-F02·F07 | `routers/accounts.py` |
| 계좌 상세 (+잔액) | `GET /accounts/{accountId}` | ACCT-F02 | `routers/accounts.py` |
| 잔액 (`account_balance_view`) | `GET /accounts/{accountId}/balance` | ACCT-F03 | `routers/accounts.py` |
| 거래내역 (`start_date`·`end_date`·`direction=IN/OUT`·`limit`·`cursor`) | `GET /accounts/{accountId}/transactions` | Part 5 10장 | `routers/transactions.py` |
| 거래 상세 | `GET /transactions/{transactionId}` | Part 5 16장 | `routers/transactions.py` |
| 이체 결과 목록·상세 (`?status=`) | `GET /transfers`, `GET /transfers/{transferId}` | Part 5 16장 | `routers/transfers.py` |
| 예약 송금·자동이체 목록·상세 | `GET /scheduled-transfers`, `GET /scheduled-transfers/{scheduledTransferId}` | Part 5 8·16장 | `routers/transfers.py` |
| 이체 한도와 오늘 남은 한도 | `GET /accounts/{accountId}/transfer-limits` | Part 5 4·16장 | `routers/transfers.py` |
| 이체 대상 확인 (예금주·상태·내 계좌 여부) | `GET /transfer-targets/verify?bank=&account_no=` | Part 5 11·16장 | `routers/transfer_targets.py` |
| 자주 쓰는 계좌 | `GET /favorite-accounts` | Part 5 16장 | `routers/favorites.py` |

응답 형식 (기획서 C-5): 금액은 **문자열**(`"resAccountBalance": "1250000"`), 시각은 `+09:00` ISO 8601,
CODEF `res…` 빈 칸은 `""`, 우리가 만든 빈 칸은 `null`. 거래에는 `direction`(`IN`/`OUT`, Part 5 3장)이 붙는다.

오류 형식 (기획서 Part 1 7.1): `{"success": false, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "계좌를 찾을 수 없어요."}}`
— 남의 것과 없는 것은 똑같이 404(존재 여부를 숨김, Part 2 ACCT-F02). 기획서 업무 규칙 값(기본 한도, 은행별 자릿수 등)은 `app/rules.py`.

아직 없는 것: 쓰기 API(이체 실행·예약 등록·계좌 개설/설정/해지 등)는 본인 확인(`step_up_challenges`)이 필요해 로그인 구현 뒤에 만든다.

## 6. 테스트
```bash
.venv\Scripts\python -m pytest -q
```
- `tests/conftest.py` 가 `midproject_test` 를 **개발 DB 와 같은 방법**(docs/sql → load_dummy → seed_scenarios)으로 매번 새로 만든다.
  기대값은 더미·시드의 실제 값이다.
- `tests/test_models_schema.py`: 모델과 DB 의 칸·타입·NULL·기본값·키·제약·인덱스 비교(표 60개 각각). `docs/sql` 만 고치고 모델을 다시 안 만들면 여기서 실패한다.
- `tests/test_api.py`: 위 API 의 정상·실패 동작(남의 계좌 404, 회원 상태별 401/403, 자릿수 오류, 커서 페이지 등).
