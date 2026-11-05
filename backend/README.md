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
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8010
```
http://localhost:8010/docs 에서 호출 (화면 `frontend/` 가 8010 을 부른다 — 아래 「화면 연결」). 먼저 `POST /auth/login` 으로 로그인하면 브라우저에 쿠키가 저장되고, 그 뒤 호출은 그 회원으로 처리된다.
시드 회원의 아이디는 `users.username`(예: `minjun_kim` = user_001), 비밀번호는 모두 `.env.example` 의 `SEED_PASSWORD`.

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
  바꾸려면 `backend/.env` 에 `CORS_ORIGINS=주소1,주소2` (`.env.example` 참고).
- 로그인 쿠키를 주고받도록 `allow_credentials=True` — 그래서 허용 주소를 `*` 로 둘 수 없다.
  화면에서는 요청마다 쿠키를 같이 보내야 한다: `fetch(url, { credentials: "include" })` / axios `withCredentials: true`.

## 5. API (기획서 경로)
| 기능 | 엔드포인트 | 기획서 | 위치 |
|---|---|---|---|
| 로그인 · 로그아웃 | `POST /auth/login`, `POST /auth/logout` | Part 1 AUTH-F05 | `routers/auth.py` |
| 내 정보 (가입 마무리 중에도 가능) | `GET /users/me` | Part 1 AUTH-F07(조회만) | `routers/users.py` |
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

아직 없는 것: 본인 확인(`POST /auth/step-up`)과, 그것이 필요한 쓰기 API(이체 실행·예약 등록·계좌 개설/설정/해지 등). 회원가입·Google 로그인.

## 5-1. 화면(frontend/) 연결
```bash
# 터미널 1: DB(1번) 를 띄운 뒤 서버
cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload --port 8010
# 터미널 2: 화면
cd frontend && npm ci && npm run dev        # http://localhost:5173
```
- 로그인: 시드 회원 아이디(예: `minjun_kim` = user_001) + `backend/.env.example` 의 `SEED_PASSWORD`.
- 서버 주소는 `frontend/src/api.ts` 의 `API` — 기본 `http://localhost:8010`, 바꾸려면 `frontend/.env.local` 에 `VITE_API_URL=...`.
- 쿠키 로그인이라 화면 주소가 `CORS_ORIGINS`(기본 5173·3000) 안에 있어야 한다. 서버는 로그인한 응답마다
  `X-Session-Expires-At`(유휴 10분·최대 12시간 중 먼저 끝나는 시각)을 보내고, 화면은 그걸로 남은 시간·「로그인 연장」 창을 띄운다.
- 모양 맞추기는 `frontend/src/api.ts` 한 곳에서 한다: 이 서버는 기획서 C-5 이름(`resAccount…`)으로, 성공 응답을 감싸지 않고 답하므로
  `call()` 이 `{ success: true, data }` 로 감싸고 함수마다 화면 모양으로 바꾼다. 서버에 없는 주소는 `NOT_IMPLEMENTED`
  「아직 서버에 없는 기능이에요.」로 보인다(홈의 추천 상품·카드 칸은 비워 두고 나머지를 보여 줌).
- 지금 이어진 화면: 로그인·로그아웃, 홈(계좌 합계), 내 계좌·계좌 상세·잔액, 거래내역, 이체 결과 목록·상세, 이체 한도 보기,
  자주 쓰는 계좌, 받는 계좌 확인, 내 정보 보기. 나머지(가입·상품·카드·알림·PIN·쓰기 기능 전부)는 서버 API 가 생기면 이어진다.

## 6. 테스트
```bash
.venv\Scripts\python -m pytest -q
```
- `tests/conftest.py` 가 `midproject_test` 를 **개발 DB 와 같은 방법**(docs/sql → load_dummy → seed_scenarios)으로 매번 새로 만든다.
  기대값은 더미·시드의 실제 값이다.
- `tests/test_models_schema.py`: 모델과 DB 의 칸·타입·NULL·기본값·키·제약·인덱스 비교(표 60개 각각). `docs/sql` 만 고치고 모델을 다시 안 만들면 여기서 실패한다.
- `tests/test_api.py`: 위 API 의 정상·실패 동작(남의 계좌 404, 회원 상태별 401/403, 자릿수 오류, 커서 페이지 등).
- `tests/test_auth.py`: 로그인·로그아웃(AUTH-F05 완료 기준, 기획서 11장 1차 QA) — 실패 시 세션 없음, 로그아웃·유휴 10분·최대 12시간 뒤 거부,
  계정 존재 숨김, 실패 속도 제한, 회원 상태별 처리, 쿠키에 HttpOnly, DB 에 쿠키 원문 없음, 다른 `Origin` 의 POST 차단.
- `tests/test_cors.py`: CORS 허용 주소·차단.
