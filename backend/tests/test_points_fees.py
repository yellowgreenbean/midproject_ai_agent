"""카드 포인트 조회·현금화(CARD-F12, 1-1-7) · 연회비 청구 알림(CARD-F13, 1-1-8) — routers/card_points.py · app/jobs.py.

시드: 카드가 있는 회원마다 한빛포인트(pt_<회원 번호>), user_001 은 이번 달 말 소멸 예정 1,200점.
연회비 청구 예정일은 card_002 = 30일 뒤, card_003 = 오늘, 나머지 신용카드는 2~11개월 뒤(scripts/seed_scenarios.py).
현금화는 다른 시험이 잔액을 보지 않는 user_013 으로 한다. 예약 작업은 만든 행을 지워 다른 시험에 남기지 않는다.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.db import engine
from app.jobs import charge_annual_fees, expire_points, notify_annual_fees, notify_expiring_points
from app.main import app
from app.rules import next_year, now_kst
from tests.conftest import as_user, seed_password
from tests.test_signup import sql

PW = seed_password()


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def login(browser, user_id: str):
    username = sql("SELECT username FROM users WHERE id = :u", u=user_id).scalar()
    assert browser.post("/auth/login", json={"username": username, "password": PW}).status_code == 200


def ch(browser, action: str = "POINT_CASHOUT") -> str:
    r = browser.post("/auth/step-up", json={"action": action, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def run(job, now: datetime) -> list[str]:
    with Session(engine) as db:
        out = job(db, now)
        db.commit()
        return out


def checking(user_id: str) -> str:
    return sql("""SELECT id FROM accounts WHERE user_id = :u AND account_type = 'CHECKING' AND lifecycle_status = 'ACTIVE'
                  ORDER BY id LIMIT 1""", u=user_id).scalar()


def balance(acc: str) -> int:
    return sql("SELECT balance FROM account_balances WHERE account_id = :a", a=acc).scalar()


# --- 조회 ------------------------------------------------------------------------------------------
def test_list_points_only_mine(client):
    d = client.get("/card-points", headers=as_user("user_001")).json()
    assert [p["id"] for p in d["points"]] == ["pt_001"]
    p = d["points"][0]
    assert p["point_name"] == "한빛포인트" and p["expiring_amount"] == "1200" and p["expiring_date"]
    assert int(p["balance"]) >= 1200 and d["cashouts"] == []
    assert client.get("/card-points", headers=as_user("user_020")).json() == {"points": [], "cashouts": []}  # 카드 없는 회원
    assert client.get("/card-points").status_code == 401


# --- 현금화 ----------------------------------------------------------------------------------------
def test_cashout_requires_step_up_and_valid_account(browser):
    login(browser, "user_013")
    acc, before = checking("user_013"), sql("SELECT balance FROM card_points WHERE id = 'pt_013'").scalar()
    assert before > 0
    url = "/card-points/pt_013/cashout"
    # 본인 확인 없음 · 다른 작업의 번호
    assert browser.post(url, json={"account_id": acc, "step_up_challenge_id": "nope"}).json()["error"]["code"] == "STEP_UP_REQUIRED"
    r = browser.post(url, json={"account_id": acc, "step_up_challenge_id": ch(browser, "CARD_MANAGEMENT")})
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    # 남의 포인트·없는 포인트는 같은 404
    for pid in ("pt_001", "pt_999"):
        r = browser.post(f"/card-points/{pid}/cashout", json={"account_id": acc, "step_up_challenge_id": ch(browser)})
        assert r.status_code == 404 and r.json()["error"]["code"] == "POINT_NOT_FOUND"
    # 남의 계좌 · 정지한 내 계좌는 고를 수 없다
    r = browser.post(url, json={"account_id": "acc_001", "step_up_challenge_id": ch(browser)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CASHOUT_ACCOUNT"
    sql("UPDATE accounts SET lifecycle_status = 'SUSPENDED' WHERE id = :a", a=acc)
    try:
        r = browser.post(url, json={"account_id": acc, "step_up_challenge_id": ch(browser)})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CASHOUT_ACCOUNT"
    finally:
        sql("UPDATE accounts SET lifecycle_status = 'ACTIVE' WHERE id = :a", a=acc)
    assert sql("SELECT balance FROM card_points WHERE id = 'pt_013'").scalar() == before  # 아무것도 안 바뀜
    assert sql("SELECT count(*) FROM point_cashouts").scalar() == 0


def test_cashout_all_points_to_account_once(browser):
    login(browser, "user_013")
    acc = checking("user_013")
    points, money = sql("SELECT balance FROM card_points WHERE id = 'pt_013'").scalar(), balance(acc)
    r = browser.post("/card-points/pt_013/cashout", json={"account_id": acc, "step_up_challenge_id": ch(browser)})
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["amount"], d["status"], d["account_id"], d["point_name"]) == (str(points), "COMPLETED", acc, "한빛포인트")
    assert d["completed_at"]
    # 포인트 0 · 계좌 잔액은 원장 POINT_CASHOUT 한 줄로만 늘었다
    assert sql("SELECT balance FROM card_points WHERE id = 'pt_013'").scalar() == 0
    assert balance(acc) == money + points
    tx = sql("""SELECT type, amount, balance_after, display_name FROM transactions WHERE account_id = :a
                ORDER BY created_at DESC, id DESC LIMIT 1""", a=acc).one()
    assert tuple(tx) == ("POINT_CASHOUT", points, money + points, "한빛포인트 현금화")
    listed = browser.get(f"/accounts/{acc}/transactions").json()
    first = (listed["items"] if isinstance(listed, dict) else listed)[0]
    assert first["type"] == "POINT_CASHOUT" and first["direction"] == "IN"
    # 내역에 나오고, 다시 하면 바꿀 포인트가 없다(본인 확인 번호는 쓰이지 않고 남는다)
    got = browser.get("/card-points").json()
    assert got["points"][0]["balance"] == "0" and [c["id"] for c in got["cashouts"]] == [d["id"]]
    r = browser.post("/card-points/pt_013/cashout", json={"account_id": acc, "step_up_challenge_id": ch(browser)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_POINTS"
    assert balance(acc) == money + points and sql("SELECT count(*) FROM point_cashouts").scalar() == 1


# --- 소멸 예정 알림 · 소멸 처리 ------------------------------------------------------------------------
def test_point_expiring_alert_once_and_expiry():
    saved = sql("SELECT balance, expiring_amount, expiring_date FROM card_points WHERE id = 'pt_004'").one()
    day = date(2020, 5, 31)  # 과거 날짜 — 시드 포인트(pt_001, 이번 달 말 소멸)는 건드리지 않는다
    sql("UPDATE card_points SET expiring_amount = 300, expiring_date = :d WHERE id = 'pt_004'", d=day)
    made = []
    try:
        at = lambda d: datetime.combine(d, datetime.min.time()).replace(hour=8)
        assert run(notify_expiring_points, at(day - timedelta(days=31))) == []  # 31일 전은 아직
        made = run(notify_expiring_points, at(day - timedelta(days=30)))
        assert run(notify_expiring_points, at(day - timedelta(days=7))) == []  # 한 번만
        n = sql("SELECT user_id, type, event_id, title, body FROM notifications WHERE id = ANY(:i)", i=made).one()
        assert tuple(n) == ("user_004", "POINT_EXPIRING", "pt_004_202005", "한빛포인트 300점이 곧 사라져요",
                            "5월 31일에 소멸돼요. 현금으로 바꿔 보세요.")
        assert run(expire_points, at(day)) == []  # 소멸일 당일까지는 쓸 수 있다
        assert run(expire_points, at(day + timedelta(days=1))) == ["pt_004"]
        after = sql("SELECT balance, expiring_amount, expiring_date FROM card_points WHERE id = 'pt_004'").one()
        assert tuple(after) == (saved.balance - 300, 0, None)
        assert run(expire_points, at(day + timedelta(days=2))) == []  # 다시 돌려도 또 빠지지 않는다
    finally:
        sql("DELETE FROM notifications WHERE id = ANY(:i)", i=made)
        sql("UPDATE card_points SET balance = :b, expiring_amount = :e, expiring_date = :d WHERE id = 'pt_004'",
            b=saved.balance, e=saved.expiring_amount, d=saved.expiring_date)


# --- 연회비 ----------------------------------------------------------------------------------------
def test_annual_fee_alert_30_days_before_once():
    now = now_kst()
    made = []
    try:
        made = run(notify_annual_fees, now)
        assert run(notify_annual_fees, now) == []
        rows = {r.user_card_id: r for r in sql(
            "SELECT user_card_id, user_id, type, event_id, body FROM notifications WHERE id = ANY(:i)", i=made).all()}
        # card_002 = 30일 뒤, card_003 = 오늘. 2개월 넘게 남은 카드와 체크카드(연회비 0원)는 없다
        assert set(rows) == {"card_002", "card_003"}
        due = sql("SELECT next_annual_fee_date FROM user_cards WHERE id = 'card_002'").scalar()
        assert due == now.date() + timedelta(days=30)
        n = rows["card_002"]
        assert (n.user_id, n.type, n.event_id) == ("user_001", "ANNUAL_FEE", f"card_002:AF:{due:%Y%m%d}")
        assert "22,000원" in n.body
    finally:
        sql("DELETE FROM notifications WHERE id = ANY(:i)", i=made)


def test_annual_fee_charged_as_card_transaction(client):
    """card_020(user_013, 연회비 22,000원)의 청구일을 먼 과거로 두고 그날 기준으로 돌린다 — 다른 카드는 청구일이 아니다."""
    saved = sql("SELECT next_annual_fee_date FROM user_cards WHERE id = 'card_020'").scalar()
    day = date(2020, 2, 29)
    before = client.get("/cards/card_020", headers=as_user("user_013")).json()
    sql("UPDATE user_cards SET next_annual_fee_date = :d WHERE id = 'card_020'", d=day)
    try:
        at = datetime.combine(day, datetime.min.time()).replace(hour=6)
        assert run(charge_annual_fees, at - timedelta(days=1)) == []  # 청구일 전
        assert run(charge_annual_fees, at) == ["card_020"]
        assert run(charge_annual_fees, at) == []  # 같은 해 연회비는 한 번만
        tx = sql("""SELECT t.amount, t.approval_no, t.is_performance_counted, t.status, m.name
                    FROM card_transactions t JOIN merchants m ON m.id = t.merchant_id
                    WHERE t.user_card_id = 'card_020' AND t.approval_no LIKE 'AF%'""").one()
        assert tuple(tx) == (22000, "AF20200229", False, "APPROVED", "연회비")
        assert sql("SELECT next_annual_fee_date FROM user_cards WHERE id = 'card_020'").scalar() == date(2021, 2, 28)
        # 이번 기간 사용액(다음 청구서)과 쓴 한도에 그대로 들어간다
        after = client.get("/cards/card_020", headers=as_user("user_013")).json()
        assert int(after["period_spent"]) == int(before["period_spent"]) + 22000
        assert int(after["used_amount"]) == int(before["used_amount"]) + 22000
        assert int(after["available_limit"]) == int(before["available_limit"]) - 22000
        listed = client.get("/cards/card_020/transactions", headers=as_user("user_013")).json()
        assert any(t["merchant"] == "연회비" and t["amount"] == "22000" and t["category_code"] == "ANNUAL_FEE" for t in listed)
    finally:
        sql("DELETE FROM card_transactions WHERE user_card_id = 'card_020' AND approval_no LIKE 'AF%'")
        sql("UPDATE user_cards SET next_annual_fee_date = :d WHERE id = 'card_020'", d=saved)


def test_next_year_handles_leap_day():
    assert next_year(date(2026, 11, 11)) == date(2027, 11, 11)
    assert next_year(date(2028, 2, 29)) == date(2029, 2, 28)
