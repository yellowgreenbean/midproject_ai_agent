"""간편 비밀번호(PIN) — 기획서 Part 1 AUTH-F11 · F12 · F13 완료 기준과 11장 3차 QA.

만들기 · 바꾸기 · 다시 정하기는 상태를 바꾸므로 테스트마다 /auth/register 로 새 회원(생년월일 1990-01-01, PIN 없음)을 만든다.
시드 회원은 PIN 으로 본인 확인만 해 본다 (scripts/seed_scenarios.py — 정상 계좌가 있는 ACTIVE 회원은 SEED_PIN,
user_019 는 PIN 5번 틀려 잠김).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common.db import engine
from app.main import app
from app.rules import pin_error
from app.security import login_throttle
from tests.conftest import seed_password, seed_pin
from tests.test_password import PW, new_user

FIRST, SECOND = "135790", "246802"


@pytest.fixture(autouse=True)
def _fresh_throttle():
    login_throttle.clear()
    yield
    login_throttle.clear()


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def sql(query: str, **params):
    with engine.begin() as c:
        return c.execute(text(query), params)


def error_code(r) -> str:
    return r.json()["error"]["code"]


def step_up(browser, action: str, **credential):
    return browser.post("/auth/step-up", json={"action": action, **credential})


def challenge(browser, action: str, **credential) -> str:
    r = step_up(browser, action, **credential)
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def set_pin(browser, op: str, ch: str, pin: str, confirm: str | None = None):
    return browser.post(f"/auth/pin/{op}", json={"step_up_challenge_id": ch, "pin": pin,
                                                "pin_confirm": pin if confirm is None else confirm})


def enrolled_user(browser, name: str, pin: str = FIRST) -> str:
    """새 회원을 만들고 PIN 까지 만든다. 이 browser 는 그 회원으로 로그인된 상태."""
    uid = new_user(browser, name, f"{name}@example.com")
    r = set_pin(browser, "enroll", challenge(browser, "PIN_ENROLL", password=PW), pin)
    assert r.status_code == 201, r.text
    return uid


def seed_login(browser, user_id: str):
    username = sql("SELECT username FROM users WHERE id = :u", u=user_id).scalar()
    r = browser.post("/auth/login", json={"username": username, "password": seed_password()})
    assert r.status_code == 200, r.text


# --- 금지 번호 (rules.pin_error = frontend pinRules.ts) -----------------------------------------
@pytest.mark.parametrize("pin, ok", [
    ("135790", True), ("112233", True), ("123457", True),
    ("12345", False), ("1234567", False), ("12a456", False), ("１２３４５６", False),  # 6자리 숫자만 (전각 숫자도 안 됨)
    ("111111", False), ("123456", False), ("654321", False), ("789012", True),  # 9 다음 0 은 「이어지는」 아님
    ("900101", False),  # 생년월일 1990-01-01
])
def test_pin_rules(pin, ok):
    assert (pin_error(pin, date(1990, 1, 1)) is None) == ok


# --- 만들기 (AUTH-F11) -----------------------------------------------------------------------
def test_enroll_with_password_then_status_shows_enabled(browser):
    uid = new_user(browser, "pin_enroll1", "pin_enroll1@example.com")
    assert browser.get("/auth/pin").json() == {"enabled": False, "locked_until": None, "changed_at": None}

    r = set_pin(browser, "enroll", challenge(browser, "PIN_ENROLL", password=PW), FIRST)
    assert r.status_code == 201, r.text
    assert r.json()["enabled"] is True and r.json()["changed_at"] is not None
    assert browser.get("/auth/pin").json()["enabled"] is True

    stored = sql("SELECT pin_hash FROM pin_credentials WHERE user_id = :u", u=uid).scalar()
    assert FIRST not in stored and stored.startswith("$argon2")  # 원문 저장 금지
    assert sql("SELECT count(*) FROM auth_audit_logs WHERE user_id = :u AND event_type = 'PIN_ENROLL'",
               u=uid).scalar() == 1


def test_enroll_needs_password_not_pin(browser):
    new_user(browser, "pin_enroll2", "pin_enroll2@example.com")
    r = step_up(browser, "PIN_ENROLL", pin=FIRST)
    assert r.status_code == 400 and error_code(r) == "PASSWORD_REQUIRED"


def test_weak_or_mismatched_pin_keeps_challenge_usable(browser):
    new_user(browser, "pin_enroll3", "pin_enroll3@example.com")
    ch = challenge(browser, "PIN_ENROLL", password=PW)
    for bad in ("111111", "123456", "900101", "12345"):
        r = set_pin(browser, "enroll", ch, bad)
        assert r.status_code == 400 and error_code(r) == "INVALID_PIN", bad
    r = set_pin(browser, "enroll", ch, FIRST, confirm=SECOND)
    assert r.status_code == 400 and error_code(r) == "PIN_MISMATCH"
    assert set_pin(browser, "enroll", ch, FIRST).status_code == 201  # 같은 번호로 5분 안에 다시
    assert error_code(set_pin(browser, "enroll", ch, SECOND)) == "STEP_UP_REQUIRED"  # 성공한 뒤에는 다시 못 씀


def test_enroll_twice_is_refused(browser):
    enrolled_user(browser, "pin_enroll4")
    r = set_pin(browser, "enroll", challenge(browser, "PIN_ENROLL", password=PW), SECOND)
    assert r.status_code == 409 and error_code(r) == "PIN_ALREADY_SET"


# --- 바꾸기 (AUTH-F13) — 지금 PIN 으로 확인 → 숫자 6자리 ---------------------------------------
def test_change_needs_current_pin(browser):
    enrolled_user(browser, "pin_change1")
    r = step_up(browser, "PIN_CHANGE", password=PW)
    assert r.status_code == 400 and error_code(r) == "PIN_REQUIRED"
    r = step_up(browser, "PIN_CHANGE", pin=SECOND)  # 틀린 PIN
    assert r.status_code == 400 and error_code(r) == "STEP_UP_FAILED" and "4번" in r.json()["error"]["message"]


def test_change_pin_replaces_old_and_notifies(browser):
    uid = enrolled_user(browser, "pin_change2")
    r = set_pin(browser, "change", challenge(browser, "PIN_CHANGE", pin=FIRST), SECOND)
    assert r.status_code == 200, r.text

    assert error_code(step_up(browser, "TRANSFER", pin=FIRST)) == "STEP_UP_FAILED"  # 예전 PIN 은 안 됨
    assert step_up(browser, "TRANSFER", pin=SECOND).status_code == 201
    row = sql("SELECT changed_at, failed_attempts FROM pin_credentials WHERE user_id = :u", u=uid).one()
    assert row.changed_at is not None and row.failed_attempts == 0
    notes = sql("SELECT title FROM notifications WHERE user_id = :u AND type = 'SECURITY'", u=uid).scalars().all()
    assert notes == ["간편 비밀번호를 바꿨어요"]


def test_change_to_same_pin_is_refused(browser):
    enrolled_user(browser, "pin_change3")
    ch = challenge(browser, "PIN_CHANGE", pin=FIRST)
    r = set_pin(browser, "change", ch, FIRST)
    assert r.status_code == 400 and error_code(r) == "SAME_AS_OLD_PIN"
    assert set_pin(browser, "change", ch, SECOND).status_code == 200  # 번호는 그대로 남아 있음


def test_change_invalidates_unused_step_up_results(browser):
    uid = enrolled_user(browser, "pin_change4")
    old = challenge(browser, "TRANSFER", pin=FIRST)  # 바꾸기 전에 받아 둔 이체용 번호
    assert set_pin(browser, "change", challenge(browser, "PIN_CHANGE", pin=FIRST), SECOND).status_code == 200
    consumed = sql("SELECT consumed_at FROM step_up_challenges WHERE id = :c AND user_id = :u", c=old, u=uid).scalar()
    assert consumed is not None


def test_challenge_only_works_for_its_own_operation(browser):
    enrolled_user(browser, "pin_change5")
    ch = challenge(browser, "PIN_CHANGE", pin=FIRST)
    assert error_code(set_pin(browser, "reset", ch, SECOND)) == "STEP_UP_REQUIRED"
    transfer = challenge(browser, "TRANSFER", pin=FIRST)
    assert error_code(set_pin(browser, "change", transfer, SECOND)) == "STEP_UP_REQUIRED"


def test_change_without_pin_is_refused(browser):
    new_user(browser, "pin_change6", "pin_change6@example.com")
    r = step_up(browser, "PIN_CHANGE", pin=FIRST)
    assert r.status_code == 400 and error_code(r) == "PIN_NOT_SET"


# --- 실패 제한 (AUTH-F12) — 5번이면 10분 잠금, 다시 정하기로 바로 풀림 --------------------------------
def test_five_wrong_pins_lock_for_10_minutes_then_reset_unlocks(browser):
    uid = enrolled_user(browser, "pin_lock1")
    for left in (4, 3, 2, 1):
        r = step_up(browser, "TRANSFER", pin=SECOND)
        assert error_code(r) == "STEP_UP_FAILED" and f"{left}번" in r.json()["error"]["message"]
    r = step_up(browser, "TRANSFER", pin=SECOND)
    assert r.status_code == 423 and error_code(r) == "PIN_LOCKED"
    assert error_code(step_up(browser, "TRANSFER", pin=FIRST)) == "PIN_LOCKED"  # 맞는 번호도 잠긴 동안은 안 됨
    minutes = sql("SELECT extract(epoch FROM locked_until - now()::timestamp) / 60 FROM pin_credentials "
                  "WHERE user_id = :u", u=uid).scalar()
    assert 9.9 < minutes < 10.1  # 앱 시계와 DB 시계가 조금 다를 수 있다
    assert browser.get("/auth/pin").json()["locked_until"] is not None
    assert step_up(browser, "TRANSFER", password=PW).status_code == 201  # 로그인 비밀번호 본인 확인은 따로

    r = set_pin(browser, "reset", challenge(browser, "PIN_RESET", password=PW), SECOND)
    assert r.status_code == 200 and r.json()["locked_until"] is None
    assert step_up(browser, "TRANSFER", pin=SECOND).status_code == 201
    titles = sql("SELECT title FROM notifications WHERE user_id = :u AND type = 'SECURITY'", u=uid).scalars().all()
    assert titles == ["간편 비밀번호를 다시 정했어요"]


def test_reset_may_reuse_forgotten_pin(browser):
    # 다시 정하기에서 「지금 것과 같아요」를 알려 주면 잊은 PIN 을 맞혀 볼 수 있어서 막지 않는다
    enrolled_user(browser, "pin_lock2")
    assert set_pin(browser, "reset", challenge(browser, "PIN_RESET", password=PW), FIRST).status_code == 200


def test_lock_expires_and_count_starts_over(browser):
    uid = enrolled_user(browser, "pin_lock3")
    sql("UPDATE pin_credentials SET failed_attempts = 5, locked_until = now()::timestamp - interval '1 minute' "
        "WHERE user_id = :u", u=uid)
    r = step_up(browser, "TRANSFER", pin=SECOND)  # 잠금이 끝났으니 다시 5번 중 첫 번째
    assert error_code(r) == "STEP_UP_FAILED" and "4번" in r.json()["error"]["message"]
    assert step_up(browser, "TRANSFER", pin=FIRST).status_code == 201
    assert sql("SELECT failed_attempts FROM pin_credentials WHERE user_id = :u", u=uid).scalar() == 0


# --- 시드 회원 · 입력 모양 -------------------------------------------------------------------------
def test_seed_user_can_step_up_with_pin_or_password(browser):
    seed_login(browser, "user_001")
    assert step_up(browser, "TRANSFER", pin=seed_pin()).status_code == 201
    assert step_up(browser, "TRANSFER", password=seed_password()).status_code == 201


def test_seed_user_019_pin_is_locked(browser):
    seed_login(browser, "user_019")
    r = step_up(browser, "TRANSFER", pin=seed_pin())
    assert r.status_code == 423 and error_code(r) == "PIN_LOCKED"


def test_step_up_needs_exactly_one_credential(browser):
    enrolled_user(browser, "pin_shape1")
    assert error_code(step_up(browser, "TRANSFER")) == "STEP_UP_CREDENTIAL_REQUIRED"
    assert error_code(step_up(browser, "TRANSFER", pin=FIRST, password=PW)) == "STEP_UP_CREDENTIAL_REQUIRED"


def test_pin_apis_need_login():
    with TestClient(app) as anon:
        assert anon.get("/auth/pin").status_code == 401
        assert set_pin(anon, "change", "stu_x", SECOND).status_code == 401
