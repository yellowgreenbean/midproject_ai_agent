"""예금·적금 상품 API (app/routers/products.py) — 기획서 Part 3 PROD-F01~F08.

기대값은 data/dummy/products 의 값이다. prod_004 두린 적금(12개월 · 월 50만 원 이하 · 연 3.20%+0.20),
prod_005 두린 369 정기예금(3·6·9개월 · 100만 원 이상), prod_012 표지어음(일 단위 30~365일 · 1천만 원 이상),
prod_010 CD plus예금(금리표 없음), prod_024 N일 적금(일 단위 적금).
가입은 다른 시험이 쓰지 않는 user_016(acc_022, 잔액 2,992,700원)으로 한다.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.products import maturity_date, months_between
from app.rules import now_kst
from tests.conftest import as_user, seed_password
from tests.test_signup import sql

U1 = as_user("user_001")


# ---- 목록 · 상세 ----

def test_list_on_sale_and_filters(client):
    all_ = client.get("/products").json()
    assert len(all_) == 30
    rates = [float(p["max_rate"]) for p in client.get("/products?sort=rate").json() if p["max_rate"]]
    assert rates == sorted(rates, reverse=True)
    assert {p["type"] for p in client.get("/products?type=INSTALLMENT_SAVINGS").json()} == {"INSTALLMENT_SAVINGS"}
    assert [p["id"] for p in client.get("/products", params={"q": "청년"}).json()] == ["prod_018"]
    assert client.get("/products", params={"q": "%"}).json() == []  # LIKE 와일드카드가 아니라 글자로 찾는다


def test_summary_shape_matches_frontend(client):
    p = next(p for p in client.get("/products").json() if p["id"] == "prod_004")
    assert p == {"id": "prod_004", "name": "두린 적금", "type": "INSTALLMENT_SAVINGS", "description": p["description"],
                 "base_rate": "3.20", "max_rate": "3.40", "term_label": "12개월", "early_termination_allowed": True}


def test_recommended(client):
    r = client.get("/products/recommended").json()
    assert [(p["id"], p["icon"]) for p in r] == [("prod_003", "safe"), ("prod_004", "coins")]


def test_detail_with_rules_and_documents(client):
    p = client.get("/products/prod_004").json()
    assert (p["min_amount"], p["max_amount"], p["min_months"], p["max_months"]) == (None, "500000", 12, 12)
    assert p["rates"] == [{"term_min": 12, "term_max": 12, "term_unit": "MONTH", "base_rate": "3.20", "bonus_rate": "0.20"}]
    assert p["subscribable"] is True
    assert p["documents"] == [{"id": "doc_prod_004", "title": "두린 적금 상품설명서", "source": "prod_004.pdf"}]
    assert client.get("/products/prod_016").json()["documents"][0]["source"] == "prod_015_016.pdf"  # 한 설명서에 두 상품
    assert client.get("/products/prod_009").json()["documents"] == []  # 설명서 md 가 없는 상품
    assert client.get("/products/prod_005").json()["selectable_months"] == [3, 6, 9]


def test_terms_list_and_body(client):
    """상품 약관 「자세히 보기」 — 특약(있으면) → 예금 종류 약관 → 예금거래기본약관. 제목은 두린 상품명, 본문은 md 그대로
    (원본 상품명 'WON 적금' 이 보인다 — 사용자 결정 2026-11-11)."""
    terms = client.get("/products/prod_004").json()["terms"]
    assert terms == [{"id": "rider", "title": "두린 적금 특약"}, {"id": "type", "title": "적립식예금 약관"},
                     {"id": "basic", "title": "예금거래기본약관"}]
    t = client.get("/products/prod_004/terms/rider").json()  # 로그인 없이
    assert (t["title"], t["source"]) == ("두린 적금 특약", "prod_004.pdf")
    assert t["content"].startswith("## 제1조 약관의 적용") and "「WON 적금」" in t["content"]
    assert client.get("/products/prod_003").json()["terms"][1] == {"id": "type", "title": "거치식예금 약관"}
    assert "## 제1조 적용범위" in client.get("/products/prod_003/terms/type").json()["content"]
    assert [x["id"] for x in client.get("/products/prod_009").json()["terms"]] == ["type", "basic"]  # 특약 md 가 없는 상품
    for url in ("/products/prod_009/terms/rider", "/products/prod_004/terms/nope"):
        r = client.get(url)
        assert r.status_code == 404 and r.json()["error"]["code"] == "TERMS_NOT_FOUND"
    assert client.get("/products/prod_999/terms/basic").json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_every_product_term_has_a_body(client):
    for p in client.get("/products").json():
        for t in client.get(f"/products/{p['id']}").json()["terms"]:
            body = client.get(f"/products/{p['id']}/terms/{t['id']}").json()["content"]
            assert body and "## " in body, (p["id"], t["id"])


def test_not_subscribable_products(client):
    assert client.get("/products/prod_010").json()["subscribable"] is False  # 금리표 없음
    assert client.get("/products/prod_024").json()["subscribable"] is False  # N일 적금


def test_detail_404(client):
    r = client.get("/products/prod_999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


# ---- 예상 이자 (단리 · 세전 · 원 미만 버림 · 기본 금리) ----

def est(client, pid: str, amount: int | str, months: int = 0, days: int | None = None):
    body = {"amount": str(amount), "months": months, **({"days": days} if days is not None else {})}
    return client.post(f"/products/{pid}/estimate", json=body)


def test_estimate_deposit(client):
    r = est(client, "prod_005", 1_000_000, 6).json()
    assert (r["rate"], r["interest"], r["principal_total"], r["maturity_amount"], r["first_payment"]) == \
        ("3.75", "18750", "1000000", "1018750", "1000000")  # 1,000,000 × 3.75% × 6/12
    assert r["maturity_date"] == maturity_date(now_kst().date(), 6).strftime("%Y%m%d")


def test_estimate_savings(client):
    r = est(client, "prod_004", 100_000, 12).json()
    # 납입 12번 × 남은 개월 12, 11, …, 1 → 100,000 × 3.2% × 78/12
    assert (r["interest"], r["principal_total"], r["maturity_amount"], r["first_payment"]) == ("20800", "1200000", "1220800", "100000")


def test_estimate_day_unit(client):
    r = est(client, "prod_012", 10_000_000, days=90).json()
    assert (r["rate"], r["interest"]) == ("2.05", "50547")  # 10,000,000 × 2.05% × 90/365


@pytest.mark.parametrize(
    ("pid", "amount", "months", "days", "code"),
    [("prod_005", 500_000, 6, None, "AMOUNT_OUT_OF_RANGE"), ("prod_005", 1_000_000, 12, None, "TERM_OUT_OF_RANGE"),
     ("prod_004", 600_000, 12, None, "AMOUNT_OUT_OF_RANGE"), ("prod_004", "abc", 12, None, "AMOUNT_OUT_OF_RANGE"),
     ("prod_004", "１０", 12, None, "AMOUNT_OUT_OF_RANGE"),  # 전각 숫자
     ("prod_012", 10_000_000, 0, 10, "TERM_OUT_OF_RANGE"), ("prod_010", 1_000_000, 12, None, "NOT_SUBSCRIBABLE"),
     ("prod_024", 10_000, 0, 31, "TERM_UNIT_NOT_SUPPORTED")],
)
def test_estimate_rejects(client, pid, amount, months, days, code):
    r = est(client, pid, amount, months, days)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_term_message_lists_choices(client):
    assert est(client, "prod_005", 1_000_000, 12).json()["error"]["message"] == "가입 기간은 3개월, 6개월, 9개월 중에서 골라 주세요."


@pytest.mark.parametrize(("start", "months", "end"), [(date(2026, 1, 31), 1, date(2026, 2, 28)), (date(2024, 1, 31), 1, date(2024, 2, 29)),
                                                      (date(2026, 11, 10), 12, date(2027, 11, 10))])
def test_maturity_date_clamps_to_month_end(start, months, end):
    assert maturity_date(start, months) == end
    assert months_between(start, end) == months


# ---- 가입 검사 ----

def validate(client, pid: str, account: str, amount: int, months: int, headers=U1):
    body = {"account_id": account, "amount": str(amount), "months": months}
    if pid == "prod_004":  # 정액·자유 둘 다 되는 적금은 납입 방식을 골라야 한다
        body["payment_type"] = "FIXED"
    return client.post(f"/products/{pid}/validate", json=body, headers=headers)


def test_validate_needs_login(client):
    assert validate(client, "prod_004", "acc_001", 100_000, 12, headers={}).status_code == 401


@pytest.mark.parametrize(
    ("account", "amount", "status", "code"),
    [("acc_007", 100_000, 404, "ACCOUNT_NOT_FOUND"),  # user_002 계좌
     ("acc_002", 100_000, 422, "INVALID_ACCOUNT_TYPE"),  # 저축예금
     ("acc_004", 100_000, 422, "ACCOUNT_NOT_ACTIVE")],  # 정지
)
def test_validate_account_rules(client, account, amount, status, code):
    r = validate(client, "prod_004", account, amount, 12)
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_validate_balance_and_ok(client):
    r = validate(client, "prod_005", "acc_001", 900_000_000, 6)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert validate(client, "prod_004", "acc_001", 100_000, 12).json()["first_payment"] == "100000"


def test_restricted_user_cannot_subscribe(client):
    r = validate(client, "prod_004", "acc_030", 100_000, 12, headers=as_user("user_024"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "USER_NOT_ACTIVE"


# ---- 가입 (실제 로그인 세션 + 본인 확인) ----

@pytest.fixture
def user_016():
    with TestClient(app) as c:
        username = sql("SELECT username FROM users WHERE id = 'user_016'").scalar()
        assert c.post("/auth/login", json={"username": username, "password": seed_password()}).status_code == 200
        yield c


def step_up(c) -> str:
    r = c.post("/auth/step-up", json={"action": "SUBSCRIPTION", "password": seed_password()})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def subscribe(c, key: str, pid: str = "prod_004", amount: int = 100_000, months: int = 12, challenge: str | None = None,
              payment_type: str | None = "FIXED"):
    """prod_004 는 정액·자유 둘 다 되는 적금이라 납입 방식을 보낸다(기본 FIXED). 한 가지뿐인 상품·예금은 None 을 넘긴다."""
    body = {"product_id": pid, "account_id": "acc_022", "amount": str(amount), "months": months,
            "step_up_challenge_id": challenge or step_up(c), **({"payment_type": payment_type} if payment_type else {})}
    return c.post("/subscriptions", json=body, headers={"Idempotency-Key": key})


def bal() -> int:
    return sql("SELECT balance FROM account_balances WHERE account_id = 'acc_022'").scalar()


def test_subscribe_savings_end_to_end(user_016):
    before = bal()
    r = subscribe(user_016, "test-sub-savings-1")
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s["product_id"], s["principal"], s["monthly_amount"], s["applied_rate"], s["status"]) == \
        ("prod_004", "100000", "100000", "3.20", "ACTIVE")
    assert bal() == before - 100_000
    tx = sql("SELECT type, amount, balance_after, display_name FROM transactions WHERE account_id = 'acc_022' "
             "ORDER BY created_at DESC LIMIT 1").one()
    assert tuple(tx) == ("SUBSCRIPTION_PAYMENT", 100_000, before - 100_000, "두린 적금")
    assert sql("SELECT paid_amount FROM subscription_payments WHERE subscription_id = :s", s=s["id"]).scalar() == 100_000
    assert s["id"] in {x["id"] for x in user_016.get("/users/me/subscriptions").json()}

    again = subscribe(user_016, "test-sub-savings-1")  # 같은 키 → 처음 결과, 돈은 한 번만
    assert again.status_code == 201 and again.json()["id"] == s["id"] and bal() == before - 100_000


def test_subscribe_same_key_other_content_is_409(user_016):
    assert subscribe(user_016, "test-sub-key-2", pid="prod_005", amount=1_000_000, months=3, payment_type=None).status_code == 201
    r = subscribe(user_016, "test-sub-key-2", pid="prod_003", amount=100_000, months=12, payment_type=None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_subscribe_needs_step_up_and_rolls_back(user_016):
    before = bal()
    r = subscribe(user_016, "test-sub-no-stepup", challenge="stu_bogus")
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    challenge = step_up(user_016)
    r = subscribe(user_016, "test-sub-bad-amount", amount=600_000, challenge=challenge)  # 검사 실패 → 아무것도 안 남음
    assert r.status_code == 422 and bal() == before
    assert sql("SELECT consumed_at FROM step_up_challenges WHERE id = :c", c=challenge).scalar() is None  # 번호도 다시 쓸 수 있다
    assert sql("SELECT count(*) FROM subscriptions WHERE idempotency_key = 'user_016:test-sub-bad-amount'").scalar() == 0


def test_subscribe_needs_idempotency_key(user_016):
    body = {"product_id": "prod_004", "account_id": "acc_022", "amount": "100000", "months": 12, "step_up_challenge_id": "x"}
    assert user_016.post("/subscriptions", json=body).status_code == 422


def test_max_per_user(user_016):
    """prod_018 청년미래적금은 1인 1계좌 (36개월 · 월 50만 원 이하)."""
    assert subscribe(user_016, "test-sub-limit-1", pid="prod_018", amount=10_000, months=36, payment_type=None).status_code == 201
    r = subscribe(user_016, "test-sub-limit-2", pid="prod_018", amount=10_000, months=36, payment_type=None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SUBSCRIPTION_LIMIT_EXCEEDED"
