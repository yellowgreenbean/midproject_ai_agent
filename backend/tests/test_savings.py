"""적금 납입 방식 · 추가 납입 · 만기 처리 — 기획서 Part 3 PROD-F11·F12, app/savings.py · app/routers/subscriptions.py · app/jobs.py.

더미 상품: prod_015 SUPER주거래 적금(정액만) · prod_016 SUPER주거래 자유적금(자유만, 월 50만 원 이하) ·
prod_004 두린 적금(정액·자유 둘 다) · prod_005 369 정기예금. 가입은 test_products 와 같은 user_016(acc_022)으로 한다.
「다음 회차」는 시계를 돌리지 않고, 가입일과 첫 납입일을 한 달 앞으로 옮겨(SQL) 만든다.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.common.db import SessionLocal
from app.jobs import mature_subscriptions
from app.main import app
from app.rules import now_kst
from app.savings import allowed_payment_types, current_period, maturity_date, paid_list, payment_type_of
from tests.conftest import seed_password
from tests.test_products import bal, step_up, subscribe, user_016  # noqa: F401 (user_016 은 fixture)
from tests.test_signup import sql


# ---- 순수 규칙 (app/savings.py) ----

def test_current_period_is_month_from_start():
    start = date(2026, 1, 31)
    assert current_period(start, date(2026, 1, 31)) == (date(2026, 1, 31), date(2026, 2, 28))
    assert current_period(start, date(2026, 2, 27)) == (date(2026, 1, 31), date(2026, 2, 28))
    assert current_period(start, date(2026, 2, 28)) == (date(2026, 2, 28), date(2026, 3, 31))  # 말일 규칙 그대로


def test_payment_type_rules():
    assert allowed_payment_types("TIME_DEPOSIT", {"payment_types": ["FREE"]}) == []
    assert allowed_payment_types("INSTALLMENT_SAVINGS", {}) == ["FREE"]  # 값이 없으면 자유적립식
    assert allowed_payment_types("INSTALLMENT_SAVINGS", {"payment_types": ["FREE", "FIXED"]}) == ["FIXED", "FREE"]
    assert payment_type_of("INSTALLMENT_SAVINGS", 100_000) == "FIXED"
    assert payment_type_of("INSTALLMENT_SAVINGS", None) == "FREE"
    assert payment_type_of("TIME_DEPOSIT", None) is None


def test_paid_list_fills_missing_principal_on_start():
    start = date(2025, 1, 10)
    assert paid_list(start, 500, [(date(2025, 2, 10), 200)]) == [(start, 300), (date(2025, 2, 10), 200)]
    assert paid_list(start, 200, [(date(2025, 2, 10), 200)]) == [(date(2025, 2, 10), 200)]


# ---- 상품 상세 · 가입 때 납입 방식 ----

def test_detail_shows_payment_types(client):
    assert client.get("/products/prod_004").json()["payment_types"] == ["FIXED", "FREE"]
    assert client.get("/products/prod_015").json()["payment_types"] == ["FIXED"]
    assert client.get("/products/prod_016").json()["payment_types"] == ["FREE"]
    assert client.get("/products/prod_005").json()["payment_types"] == []


def test_subscribe_payment_type_required_or_allowed(user_016):
    r = subscribe(user_016, "test-pt-1", pid="prod_004", payment_type=None)
    assert r.status_code == 422 and r.json()["error"]["code"] == "PAYMENT_TYPE_REQUIRED"
    r = subscribe(user_016, "test-pt-2", pid="prod_015", months=12, payment_type="FREE")
    assert r.status_code == 422 and r.json()["error"]["code"] == "PAYMENT_TYPE_NOT_ALLOWED"


# ---- 추가 납입 ----

def pay(c, sid: str, amount: int | str, challenge: str | None = None):
    return c.post(f"/subscriptions/{sid}/payments", json={"amount": str(amount), "step_up_challenge_id": challenge or step_up(c)})


def move_to_second_period(sid: str) -> None:
    """가입일과 그동안의 납입일을 한 달 앞으로 — 오늘이 2회차가 된다(만기일은 그대로 두어 남은 기간만 줄어든다)."""
    start = sql("SELECT start_date FROM subscriptions WHERE id = :s", s=sid).scalar()
    d = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    prev = maturity_date(d, -1)  # 한 달 전 (음수 개월도 같은 말일 규칙)
    sql("UPDATE subscriptions SET start_date = :p WHERE id = :s", p=prev.strftime("%Y%m%d"), s=sid)
    sql("UPDATE subscription_payments SET paid_at = :p || substr(paid_at, 9) WHERE subscription_id = :s",
        p=prev.strftime("%Y%m%d"), s=sid)


def test_fixed_once_per_period(user_016):
    r = subscribe(user_016, "test-fixed-1", pid="prod_015", amount=50_000, months=12, payment_type=None)
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s["payment_type"], s["monthly_amount"]) == ("FIXED", "50000")
    d = user_016.get(f"/users/me/subscriptions/{s['id']}").json()
    assert (d["payable"], d["monthly_max"], d["paid_this_month"]) == (False, "50000", "50000")  # 1회차는 가입 때 냈다

    r = pay(user_016, s["id"], 50_000)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_PAID_THIS_PERIOD"

    move_to_second_period(s["id"])
    assert user_016.get(f"/users/me/subscriptions/{s['id']}").json()["payable"] is True
    r = pay(user_016, s["id"], 40_000)
    assert r.status_code == 422 and r.json()["error"]["code"] == "AMOUNT_OUT_OF_RANGE"  # 정한 금액만

    before = bal()
    r = pay(user_016, s["id"], 50_000)
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["principal"], d["paid_this_month"], d["payable"], len(d["payments"])) == ("100000", "50000", False, 2)
    assert bal() == before - 50_000
    tx = sql("SELECT type, amount FROM transactions WHERE account_id = 'acc_022' ORDER BY created_at DESC, id DESC LIMIT 1").one()
    assert tuple(tx) == ("SUBSCRIPTION_PAYMENT", 50_000)


def test_free_within_period_limit(user_016):
    r = subscribe(user_016, "test-free-1", pid="prod_016", amount=300_000, months=12, payment_type=None)
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s["payment_type"], s["monthly_amount"]) == ("FREE", None)

    assert pay(user_016, s["id"], 150_000).status_code == 201  # 같은 회차에 여러 번
    r = pay(user_016, s["id"], 50_001)
    assert r.status_code == 422 and r.json()["error"]["code"] == "MONTHLY_LIMIT_EXCEEDED"
    assert "50,000원까지" in r.json()["error"]["message"]
    d = pay(user_016, s["id"], 50_000).json()
    assert (d["principal"], d["paid_this_month"], d["monthly_max"], d["payable"]) == ("500000", "500000", "500000", False)


def test_pay_rejects_bad_amount_and_rolls_back(user_016):
    sid = sql("SELECT id FROM subscriptions WHERE idempotency_key = 'user_016:test-free-1'").scalar()
    move_to_second_period(sid)
    before = bal()
    challenge = step_up(user_016)
    for amount in ("0", "abc", "-1"):
        r = pay(user_016, sid, amount, challenge)
        assert r.status_code == 422 and r.json()["error"]["code"] == "AMOUNT_OUT_OF_RANGE"
    assert bal() == before
    assert sql("SELECT consumed_at FROM step_up_challenges WHERE id = :c", c=challenge).scalar() is None  # 실패하면 번호도 되살아난다


def test_pay_needs_step_up_and_own_contract(user_016):
    sid = sql("SELECT id FROM subscriptions WHERE idempotency_key = 'user_016:test-free-1'").scalar()
    r = pay(user_016, sid, 10_000, challenge="stu_bogus")
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    r = pay(user_016, "sub_001", 10_000)  # user_001 의 계약 — 있는지도 알리지 않는다
    assert r.status_code == 404 and r.json()["error"]["code"] == "SUBSCRIPTION_NOT_FOUND"


@pytest.fixture
def user_013():
    with TestClient(app) as c:
        username = sql("SELECT username FROM users WHERE id = 'user_013'").scalar()
        assert c.post("/auth/login", json={"username": username, "password": seed_password()}).status_code == 200
        yield c


def test_deposit_cannot_take_more(user_013):
    r = pay(user_013, "sub_008", 10_000)  # prod_003 정기예금
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOT_INSTALLMENT_SAVINGS"


# ---- 만기 처리 (PROD-F11) ----

def _insert_sub(sid, user, product, account, principal, monthly, rate, start, maturity, payments):
    sql("INSERT INTO subscriptions (id, user_id, product_id, source_account_id, principal, monthly_amount, applied_rate, "
        "start_date, maturity_date, status, closed_at, idempotency_key) VALUES (:id, :u, :p, :a, :pr, :m, :r, :st, :ma, "
        "'ACTIVE', NULL, :k)", id=sid, u=user, p=product, a=account, pr=principal, m=monthly, r=rate, st=start, ma=maturity,
        k=f"test-{sid}")
    for i, (paid_at, amount) in enumerate(payments):
        sql("INSERT INTO subscription_payments (id, subscription_id, paid_amount, paid_at) VALUES (:id, :s, :a, :t)",
            id=f"pay_{sid}_{i}", s=sid, a=amount, t=paid_at)


def test_maturity_pays_principal_and_interest():
    """정액 1만 원 × 12회 · 연 2.40% · 1년 → 이자 = 10,000 × 2.4% × (12+11+…+1)/12 = 1,560원."""
    today = now_kst().date()
    start = maturity_date(today, -12)
    end = maturity_date(start, 12)  # 오늘(또는 그 전 말일) — 만기가 된 계약
    pays = [(maturity_date(start, k).strftime("%Y%m%d") + "090000", 10_000) for k in range(12)]
    _insert_sub("sub_t_mat", "user_016", "prod_015", "acc_022", 120_000, 10_000, "2.40",
                start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), pays)
    before = bal()
    with SessionLocal() as db:
        paid, _ = mature_subscriptions(db, now_kst())
        db.commit()
    assert "sub_t_mat" in paid
    assert bal() == before + 121_560
    row = sql("SELECT status, closed_at FROM subscriptions WHERE id = 'sub_t_mat'").one()
    assert tuple(row) == ("MATURED", today.strftime("%Y%m%d"))
    assert sql("SELECT count(*) FROM notifications WHERE event_id = 'sub_t_mat' AND type = 'MATURITY'").scalar() == 1

    with SessionLocal() as db:  # 다시 돌려도 두 번 주지 않는다
        paid, _ = mature_subscriptions(db, now_kst())
        db.commit()
    assert "sub_t_mat" not in paid and bal() == before + 121_560


@pytest.fixture
def held_sub():
    """정지 계좌(acc_011, user_005)를 출금 계좌로 둔 만기 지난 계약 — 다른 시험(user_005 탈퇴)에 남지 않게 지운다."""
    y = (now_kst().date() - timedelta(days=1)).strftime("%Y%m%d")
    _insert_sub("sub_t_hold", "user_005", "prod_016", "acc_011", 100_000, None, "2.40", "20251001", y, [])
    yield "sub_t_hold"
    sql("DELETE FROM notifications WHERE event_id LIKE 'sub_t_hold%'")
    sql("DELETE FROM subscriptions WHERE id = 'sub_t_hold'")


def test_maturity_waits_for_suspended_account(held_sub):
    assert sql("SELECT lifecycle_status FROM accounts WHERE id = 'acc_011'").scalar() == "SUSPENDED"
    for _ in range(2):
        with SessionLocal() as db:
            paid, held = mature_subscriptions(db, now_kst())
            db.commit()
        assert held_sub in held and held_sub not in paid
    assert sql("SELECT status FROM subscriptions WHERE id = :s", s=held_sub).scalar() == "ACTIVE"
    assert sql("SELECT count(*) FROM notifications WHERE event_id = 'sub_t_hold:HOLD'").scalar() == 1  # 알림은 한 번만
