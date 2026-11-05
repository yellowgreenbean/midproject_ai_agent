# 계좌·거래 API (1단계)

`../ERD 1.md` 1·2·3장의 계좌·거래 테이블을 PostgreSQL 에 올리고, 키로 값을 읽는 GET API.

## DB (Docker)
```bash
docker compose up -d --wait                # PostgreSQL 17 (localhost:5433, app/app)
```
- 첫 기동(빈 볼륨) 때 `db/init/` 을 실행한다: `01_test_db.sql` 이 테스트 DB `midproject_test` 를 만들고, `02_schema.sh` 가 **기획서 스키마** `../docs/sql/00~07`(표 60개 + 보기 1개, `docs/기획서.md` 기준)을 `midproject` 에 만든다. 데이터는 넣지 않는다.
- `../docs/sql` 을 고친 뒤에는 `docker compose down -v` → `docker compose up -d --wait` 로 다시 만든다(볼륨의 데이터도 지워짐).
- 포트가 5433 인 이유: 이 PC 에 설치된 PostgreSQL 17 서비스가 이미 5432 를 쓰고 있다.
- DB 안을 직접 보려면 `docker exec -it midproject-postgres psql -U app -d midproject`
  (CODEF 이름 칸은 `SELECT "resAccount" FROM accounts;` 처럼 따옴표로 감싼다 — 기획서 C-5).
- 데이터는 `../data/dummy` 의 더미 데이터를 쓴다(적재 방법은 아직 없음).

## 앱 실행
```bash
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload
```

> ⚠️ `python -m app.seed` 는 쓰지 않는다. `app/models.py` 의 표 9개를 지우고 다시 만든 뒤 지어낸 값을 넣는 시드라,
> 기획서 스키마가 있는 `midproject` 와 맞지 않는다(사용자 허락 없이 시드를 실행하지 않는다).
> `app/models.py`·`app/seed.py`·테스트는 아직 예전 `ERD 1.md` 기준이고 `midproject_test` 에서만 돈다 — 기획서 스키마에 맞추는 것은 다음 단계.

http://localhost:8000/docs 에서 호출. 지금은 로그인 대신 `X-User-Id: user_001` 헤더를 쓴다(`app/deps.py`).

## 테스트
```bash
.venv\Scripts\python -m pytest -q          # midproject_test DB 를 매번 새로 시드
```

## 키 종류별 조회 패턴
| 패턴 | 엔드포인트 | 위치 |
|---|---|---|
| FK 목록 (내 것) + 1:1 JOIN | `GET /me/accounts` | `routers/accounts.py` |
| PK 단건 + JOIN | `GET /accounts/{account_id}` | `routers/accounts.py` |
| 1:1 (PK=FK), 보기 | `GET /accounts/{account_id}/balance` → `account_balance_view` | `routers/accounts.py` |
| 1:1 (PK=FK) | `GET /accounts/{account_id}/transfer-limit` | `routers/accounts.py` |
| FK 목록 + 커서 페이징 | `GET /accounts/{account_id}/transactions?limit=&cursor=` | `routers/accounts.py` |
| PK 단건, 부모로 소유권 확인 | `GET /transactions/{tx_id}` | `routers/transactions.py` |
| FK 목록 / PK 단건 | `GET /me/transfers`, `/transfers/{id}`, `/me/scheduled-transfers`, `/scheduled-transfers/{id}` | `routers/transfers.py` |
| FK 목록 | `GET /me/favorite-accounts` | `routers/favorites.py` |
| UK(복합) 조회 | `GET /external-accounts/lookup?bank=&account_no=` | `routers/external.py` |

남의 키거나 없는 키는 모두 404 (`crud.get_owned_or_404`).
