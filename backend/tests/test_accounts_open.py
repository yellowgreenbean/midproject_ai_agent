"""ACCT-F01 계좌 개설 (POST /accounts) — 기획서 Part 2 3장 · 9.1 · 13.1.

개설 직전 본인 확인(action ACCOUNT_OPEN, PIN 이나 로그인 비밀번호)이 필요하다 — 본인 확인 번호는 로그인 세션에 묶이므로
정상 흐름은 테스트마다 /auth/register 로 새 회원(가입 = 로그인)을 만들어 시험한다. 다른 테스트의 계좌 수와도 섞이지 않는다.
상태로 막히는 경우는 시드 회원으로 본다: user_024 RESTRICTED · user_028 PENDING_VERIFICATION
"""

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import as_user
from tests.test_api import error_code
from tests.test_signup import sql
from tests.test_withdrawal import PW, new_member

BODY = {"account_type": "CHECKING", "consents": ["required_terms"]}


@pytest.fixture
def browser():
    with TestClient(app) as c:
        new_member(c)
        yield c


def step_up(browser, action: str = "ACCOUNT_OPEN", **credential) -> str:
    r = browser.post("/auth/step-up", json={"action": action, **(credential or {"password": PW})})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def open_(browser, body: dict = BODY, key: str | None = None, challenge: str | None = None):
    """본인 확인 번호를 받아 개설 요청. challenge 를 주면 그 번호로(다시 보내기·다른 action 시험)."""
    return browser.post("/accounts", json={**body, "step_up_challenge_id": challenge or step_up(browser)},
                        headers={"Idempotency-Key": key or uuid.uuid4().hex})


def user_id(browser) -> str:
    return browser.get("/users/me").json()["id"]


def account_count(uid: str) -> int:
    return sql("SELECT count(*) FROM accounts WHERE user_id = :u", u=uid).scalar()


def test_open_checking_account_appears_in_my_list(browser, client):
    r = open_(browser)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["id"].startswith("acc_")
    assert re.fullmatch(r"110\d{11}", a["resAccount"])  # 우리 은행 14자리 (rules.BANK_ACCOUNT_DIGITS)
    assert a["resAccountDisplay"].replace("-", "") == a["resAccount"]  # 화면 번호에서 숫자를 빼먹지 않는다
    assert (a["account_type"], a["lifecycle_status"], a["resAccountName"]) == ("CHECKING", "ACTIVE", "입출금통장")
    assert re.fullmatch(r"\d{8}", a["resAccountStartDate"]) and a["closed_at"] is None
    assert (a["resAccountBalance"], a["resAccountCurrency"], a["resAccountNickName"]) == ("0", "KRW", "")

    mine = browser.get("/accounts").json()
    assert [x["id"] for x in mine] == [a["id"]]  # 본인 목록에서 바로 보인다 (AC)
    assert client.get(f"/accounts/{a['id']}", headers=as_user("user_021")).status_code == 404  # 남의 계좌로 안 보인다


def test_open_savings_account_and_side_rows(browser):
    r = open_(browser, {**BODY, "account_type": "SAVINGS"})
    assert r.status_code == 201, r.text
    acc_id = r.json()["id"]
    assert r.json()["resAccountName"] == "저축예금"
    # 개설 기록(ACCT-F10 은 1차부터 기록) · 알림 기본값(ACCT-F06) · 잔액 0원(거래 파트 account_balances)
    log = sql("SELECT actor_id, metadata FROM account_activity_logs WHERE account_id = :a AND action = 'OPEN'", a=acc_id).one()
    assert log.actor_id == user_id(browser) and log.metadata["account_type"] == "SAVINGS"
    assert sql("SELECT enabled FROM notification_preferences WHERE account_id = :a", a=acc_id).scalar() is True
    assert sql("SELECT balance FROM account_balances WHERE account_id = :a", a=acc_id).scalar() == 0


def test_open_needs_step_up_for_account_open(browser, client):
    uid = user_id(browser)
    no_challenge = browser.post("/accounts", json=BODY, headers={"Idempotency-Key": uuid.uuid4().hex})
    other_action = open_(browser, challenge=step_up(browser, "ACCOUNT_STATUS_CHANGE"))  # 다른 작업용 번호
    for r in (no_challenge, other_action):
        assert r.status_code == 403 and error_code(r) == "STEP_UP_REQUIRED", r.text

    used = step_up(browser)
    assert open_(browser, challenge=used).status_code == 201
    again = open_(browser, challenge=used)  # 한 번 쓴 번호로 두 번째 계좌(새 키)는 못 만든다
    assert again.status_code == 403 and error_code(again) == "STEP_UP_REQUIRED"
    assert account_count(uid) == 1

    # 개발용 X-User-Id 헤더는 세션이 없어 본인 확인을 받을 수 없다 → 개설도 안 된다
    r = client.post("/accounts", json=BODY, headers={**as_user("user_020"), "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 403 and error_code(r) == "STEP_UP_REQUIRED"


def test_open_with_pin(browser):
    pin = "135790"
    r = browser.post("/auth/pin/enroll", json={"step_up_challenge_id": step_up(browser, "PIN_ENROLL"), "pin": pin, "pin_confirm": pin})
    assert r.status_code == 201, r.text
    assert open_(browser, challenge=step_up(browser, pin=pin)).status_code == 201

    wrong = browser.post("/auth/step-up", json={"action": "ACCOUNT_OPEN", "pin": "246802"})
    assert wrong.status_code == 400 and error_code(wrong) == "STEP_UP_FAILED"  # 틀리면 번호가 안 나와 개설 단계로 못 간다


def test_same_key_twice_makes_one_account(browser):
    key, ch = uuid.uuid4().hex, step_up(browser)
    first = open_(browser, key=key, challenge=ch)
    again = open_(browser, key=key, challenge=ch)  # 응답을 못 받고 다시 누른 경우 — 이미 쓴 번호여도 처음 계좌를 돌려준다
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert account_count(user_id(browser)) == 1

    other = open_(browser, {**BODY, "account_type": "SAVINGS"}, key=key, challenge=ch)  # 같은 키에 다른 내용
    assert other.status_code == 409 and error_code(other) == "IDEMPOTENCY_KEY_REUSED"


def test_same_key_from_another_user_is_a_separate_request(browser):
    key = uuid.uuid4().hex
    with TestClient(app) as other:
        new_member(other)
        a, b = open_(browser, key=key), open_(other, key=key)
        assert a.status_code == b.status_code == 201
        assert a.json()["id"] != b.json()["id"] and b.json()["id"] in {x["id"] for x in other.get("/accounts").json()}


def test_concurrent_same_key_makes_one_account(browser):
    n, key, ch = 8, uuid.uuid4().hex, step_up(browser)
    # 같은 로그인 세션(쿠키)으로 클라이언트를 먼저 만들고 한꺼번에 출발시킨다
    clients, start = [TestClient(app, cookies=browser.cookies) for _ in range(n)], Barrier(n)

    def send(c):
        start.wait()
        return open_(c, key=key, challenge=ch)

    with ThreadPoolExecutor(n) as pool:
        rs = list(pool.map(send, clients))
    assert {r.status_code for r in rs} == {201}, [r.text for r in rs]
    assert len({r.json()["id"] for r in rs}) == 1
    assert account_count(user_id(browser)) == 1


def test_open_rejects_bad_input(browser):
    cases = [
        ({"account_type": "TIME_DEPOSIT", "consents": ["required_terms"]}, "INVALID_ACCOUNT_TYPE"),  # 예금은 상품 가입으로
        ({"account_type": "CHECKING", "consents": []}, "REQUIRED_TERMS_NOT_AGREED"),
        ({"account_type": "CHECKING"}, "REQUIRED_TERMS_NOT_AGREED"),
    ]
    for body, code in cases:
        r = open_(browser, body)
        assert r.status_code == 422 and error_code(r) == code, body
    r = browser.post("/accounts", json={**BODY, "step_up_challenge_id": step_up(browser)})  # Idempotency-Key 없음
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_open_needs_login_and_active_member(client):
    assert client.post("/accounts", json=BODY, headers={"Idempotency-Key": uuid.uuid4().hex}).status_code == 401
    # 상태 검사는 본인 확인보다 먼저 — 어차피 못 만드는 회원에게 PIN 을 받지 않는다
    r = client.post("/accounts", json=BODY, headers={**as_user("user_024"), "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 403 and error_code(r) == "USER_NOT_ACTIVE"  # RESTRICTED: 새 금융 작업 불가 (Part 1 7.3)
    r = client.post("/accounts", json=BODY, headers={**as_user("user_028"), "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 403 and error_code(r) == "SIGNUP_INCOMPLETE"  # 가입 마무리 중
    assert sql("SELECT count(*) FROM accounts WHERE user_id IN ('user_024', 'user_028') AND lifecycle_status = 'ACTIVE'"
               " AND \"resAccountStartDate\" = to_char(now(), 'YYYYMMDD')").scalar() == 0
