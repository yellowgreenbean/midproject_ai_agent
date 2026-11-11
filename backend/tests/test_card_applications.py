"""CARD-F05 체크카드 신청 · 배송 조회 · 신청 취소, CARD-F08 결제·출금 계좌 바꾸기 — 기획서 Part 4 1-2.

본인 확인 번호는 로그인 세션에 묶이므로 테스트마다 새 회원(가입 = 로그인, 만 19세 이상)을 만들고 계좌를 연 뒤 신청한다.
시드: cp_001 · cp_004 체크카드(만 19세부터), cp_002 신용카드 · user_027 만 15세 · acc_001 은 user_001 의 계좌
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import as_user
from tests.test_api import error_code
from tests.test_signup import sql
from tests.test_withdrawal import PW, new_member


@pytest.fixture
def browser():
    with TestClient(app) as c:
        new_member(c)
        yield c


def step_up(browser, action: str) -> str:
    r = browser.post("/auth/step-up", json={"action": action, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def open_account(browser) -> str:
    r = browser.post("/accounts", json={"account_type": "CHECKING", "consents": ["required_terms"],
                                        "step_up_challenge_id": step_up(browser, "ACCOUNT_OPEN")},
                     headers={"Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def apply(browser, account_id: str, product: str = "cp_001", key: str | None = None, challenge: str | None = None, **extra):
    body = {"card_product_id": product, "linked_account_id": account_id, "delivery_address": "서울시 중구 세종대로 1",
            "agreed_term_ids": [], "step_up_challenge_id": challenge or step_up(browser, "CARD_APPLICATION"), **extra}
    return browser.post("/card-applications", json=body, headers={"Idempotency-Key": key or uuid.uuid4().hex})


def test_card_products_lists_products_on_sale(client):
    r = client.get("/card-products", headers=as_user("user_001"))
    assert r.status_code == 200, r.text
    ps = {p["id"]: p for p in r.json()}
    assert {"cp_001", "cp_002", "cp_004"} <= ps.keys()
    p = ps["cp_001"]
    assert (p["card_type"], p["min_age"], p["annual_fee"]) == ("CHECK", 19, "0")
    assert p["benefits"] and isinstance(p["terms"], list)


def test_apply_deliver_activate_makes_a_usable_card(browser):
    acc = open_account(browser)
    r = apply(browser, acc)
    assert r.status_code == 201, r.text
    a = r.json()
    assert (a["status"], a["card_type"], a["user_card_id"]) == ("APPROVED", "CHECK", None)  # 체크카드는 심사 없이 바로 승인
    assert [h["status"] for h in a["history"]] == ["APPLIED", "APPROVED"]
    assert a["tracking_no"] is None and a["linked_account_number"]
    assert [x["id"] for x in browser.get("/card-applications").json()] == [a["id"]]

    for step in ("deliver", "activate"):  # 배송 시작 전에는 도착·등록으로 못 건너뛴다
        r = browser.post(f"/card-applications/{a['id']}/{step}")
        assert r.status_code == 409 and error_code(r) == "INVALID_STATUS_TRANSITION"
    r = browser.post(f"/card-applications/{a['id']}/ship")
    assert r.status_code == 200 and r.json()["status"] == "SHIPPING" and r.json()["tracking_no"].startswith("DR")
    r = browser.post(f"/card-applications/{a['id']}/cancel")  # 배송이 시작되면 취소 대신 받은 뒤 해지
    assert r.status_code == 409 and error_code(r) == "CANNOT_CANCEL"
    r = browser.post(f"/card-applications/{a['id']}/deliver")
    assert r.status_code == 200 and r.json()["status"] == "DELIVERED"
    assert browser.post(f"/card-applications/{a['id']}/deliver").status_code == 409  # 두 번 눌러도 한 번만

    r = browser.post(f"/card-applications/{a['id']}/activate")
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "ACTIVATED" and done["user_card_id"]
    assert browser.post(f"/card-applications/{a['id']}/activate").status_code == 409

    cards = browser.get("/cards").json()
    assert [(c["id"], c["linked_account_id"], c["status"]) for c in cards] == [(done["user_card_id"], acc, "ACTIVE")]
    assert browser.get(f"/cards/{done['user_card_id']}").status_code == 200
    assert sql("SELECT count(*) FROM user_card_settings WHERE user_card_id = :c", c=done["user_card_id"]).scalar() == 1
    # 이 계좌에 카드가 연결됐으니 계좌 해지가 막힌다 (ACCT-F05)
    assert "LINKED_CARD" in browser.get(f"/accounts/{acc}").json()["close_blockers"]


def test_same_key_twice_makes_one_application(browser):
    acc, key, ch = open_account(browser), uuid.uuid4().hex, step_up(browser, "CARD_APPLICATION")
    first = apply(browser, acc, key=key, challenge=ch)
    again = apply(browser, acc, key=key, challenge=ch)  # 응답을 못 받고 다시 누른 경우 — 이미 쓴 번호여도 처음 신청
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert len(browser.get("/card-applications").json()) == 1

    other = apply(browser, acc, product="cp_004", key=key, challenge=ch)
    assert other.status_code == 409 and error_code(other) == "IDEMPOTENCY_KEY_REUSED"
    dup = apply(browser, acc)  # 같은 카드를 새 키로 또 — 신청 중이라 막힌다
    assert dup.status_code == 409 and error_code(dup) == "DUPLICATE_CARD"


def test_apply_rejects_bad_requests(browser):
    acc = open_account(browser)
    cases = [
        (dict(product="cp_002"), 422, "CREDIT_NOT_SUPPORTED"),  # 신용카드 발급은 2차
        (dict(product="cp_999"), 404, "CARD_PRODUCT_NOT_FOUND"),
        (dict(account_id="acc_001"), 422, "INVALID_LINKED_ACCOUNT"),  # 남의 계좌
        (dict(delivery_address="서울"), 422, "INVALID_ADDRESS"),
        (dict(challenge="stu_nope"), 403, "STEP_UP_REQUIRED"),
        (dict(challenge=step_up(browser, "CARD_MANAGEMENT")), 403, "STEP_UP_REQUIRED"),  # 다른 작업용 번호
    ]
    for kw, status, code in cases:
        r = apply(browser, kw.pop("account_id", acc), **kw)
        assert r.status_code == status and error_code(r) == code, (kw, r.text)
    assert browser.get("/card-applications").json() == []


def test_minor_and_other_users_application(browser, client):
    r = client.post("/card-applications", headers={**as_user("user_027"), "Idempotency-Key": uuid.uuid4().hex},
                    json={"card_product_id": "cp_001", "linked_account_id": "acc_001", "delivery_address": "서울시 중구 1"})
    assert r.status_code == 422 and error_code(r) == "AGE_NOT_ELIGIBLE"  # 만 15세 — 본인 확인 전에 거절
    a = apply(browser, open_account(browser)).json()
    r = client.post(f"/card-applications/{a['id']}/deliver", headers=as_user("user_001"))
    assert r.status_code == 404 and error_code(r) == "APPLICATION_NOT_FOUND"  # 남의 신청은 없는 것과 같다


def test_cancel_before_shipping_then_apply_again(browser):
    acc = open_account(browser)
    a = apply(browser, acc).json()
    r = browser.post(f"/card-applications/{a['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CANCELED"
    assert [h["status"] for h in r.json()["history"]] == ["APPLIED", "APPROVED", "CANCELED"]
    for step in ("cancel", "ship"):  # 취소한 신청은 더 진행하지 않는다
        assert browser.post(f"/card-applications/{a['id']}/{step}").status_code == 409
    again = apply(browser, acc)  # 취소한 카드는 다시 신청할 수 있다
    assert again.status_code == 201 and again.json()["id"] != a["id"]


def issued_card(browser, acc: str) -> str:
    a = apply(browser, acc).json()
    for step in ("ship", "deliver", "activate"):
        r = browser.post(f"/card-applications/{a['id']}/{step}")
        assert r.status_code == 200, r.text
    return r.json()["user_card_id"]


def change(browser, card_id: str, account_id: str, challenge: str | None = None):
    return browser.patch(f"/cards/{card_id}/linked-account", json={
        "account_id": account_id, "step_up_challenge_id": challenge or step_up(browser, "CARD_MANAGEMENT")})


def test_change_linked_account(browser):
    first, second = open_account(browser), open_account(browser)
    card = issued_card(browser, first)
    r = change(browser, card, second)
    assert r.status_code == 200, r.text
    assert r.json()["linked_account_id"] == second
    log = sql("SELECT action_type, before_value, after_value, result FROM card_management_logs WHERE user_card_id = :c", c=card).one()
    assert tuple(log) == ("LINKED_ACCOUNT_CHANGE", first, second, "SUCCESS")
    # 카드가 떠난 계좌는 연결 카드 때문에 해지가 막히지 않는다 (ACCT-F05)
    assert "LINKED_CARD" not in browser.get(f"/accounts/{first}").json()["close_blockers"]
    assert "LINKED_CARD" in browser.get(f"/accounts/{second}").json()["close_blockers"]


def test_change_linked_account_refusals(browser):
    first, second = open_account(browser), open_account(browser)
    card = issued_card(browser, first)
    cases = [
        (first, None, 409, "SAME_ACCOUNT"),
        ("acc_001", None, 422, "INVALID_LINKED_ACCOUNT"),  # 남의 계좌
        (second, "stu_nope", 403, "STEP_UP_REQUIRED"),
        (second, step_up(browser, "CARD_APPLICATION"), 403, "STEP_UP_REQUIRED"),  # 다른 작업용 번호
    ]
    for acc, ch, status, code in cases:
        r = change(browser, card, acc, ch)
        assert r.status_code == status and error_code(r) == code, (acc, r.text)
    assert change(browser, "card_001", second).status_code == 404  # 남의 카드

    # 확정 청구서 결제일 당일에는 못 바꾼다 — 그날 출금과 겹치지 않게
    sql("""INSERT INTO card_bills (id, user_card_id, billing_ym, usage_start, usage_end, payment_date, total_amount, status)
           VALUES (:id, :c, '209901', CURRENT_DATE - 30, CURRENT_DATE - 1, CURRENT_DATE, 1000, 'CONFIRMED')""",
        id=f"bill_t{uuid.uuid4().hex[:8]}", c=card)
    try:
        assert browser.get(f"/cards/{card}").json()["payment_day_locked"] is True
        r = change(browser, card, second)
        assert r.status_code == 409 and error_code(r) == "PAYMENT_DAY_LOCKED"
        assert browser.get(f"/cards/{card}").json()["linked_account_id"] == first
    finally:  # 오늘이 결제일인 청구서가 남으면 뒤의 결제 알림 테스트(test_cards)에 D-0 알림으로 끼어든다
        sql("DELETE FROM card_bills WHERE user_card_id = :c", c=card)
