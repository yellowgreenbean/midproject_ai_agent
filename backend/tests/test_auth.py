"""로그인 / 로그아웃 — 기획서 Part 1 AUTH-F05 완료 기준과 11장 1차 QA.

시드 회원 (scripts/seed_scenarios.py, 비밀번호는 모두 SEED_PASSWORD)
  user_001 minjun_kim ACTIVE · user_024 RESTRICTED · user_028 PENDING_VERIFICATION
  user_029 WITHDRAWN(로그인 수단 없음) · user_027 local_credentials.failed_attempts = 5 (본인 확인 잠금 시나리오)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.main import app
from app.security import login_throttle
from tests.conftest import seed_password

PW = seed_password()


@pytest.fixture(autouse=True)
def _fresh_throttle():
    login_throttle.clear()
    yield
    login_throttle.clear()


@pytest.fixture
def browser():
    """쿠키를 따로 가진 새 브라우저. 세션 쿠키가 다른 테스트로 새지 않게 테스트마다 새로 만든다."""
    with TestClient(app) as c:
        yield c


def username_of(user_id: str) -> str:
    with engine.connect() as c:
        return c.scalar(text("SELECT username FROM users WHERE id = :u"), {"u": user_id})


def login(browser, user_id: str, password: str = PW):
    return browser.post("/auth/login", json={"username": username_of(user_id), "password": password})


def sql(query: str, **params):
    with engine.begin() as c:
        return c.execute(text(query), params)


def count_sessions(user_id: str) -> int:
    return sql("SELECT count(*) FROM sessions WHERE user_id = :u", u=user_id).scalar()


# --- 로그인 성공 ------------------------------------------------------------------
def test_login_sets_httponly_session_cookie_and_protects_apis(browser):
    r = login(browser, "user_001")
    assert r.status_code == 200
    assert r.json() == {"user_id": "user_001", "status": "ACTIVE"}

    cookie = r.headers["set-cookie"]
    assert cookie.startswith("sid=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie  # 12시간

    # 헤더 없이 쿠키만으로 보호 API 사용
    assert [a["id"] for a in browser.get("/accounts").json()] == ["acc_001", "acc_002", "acc_004"]
    assert browser.get("/users/me").json()["username"] == "minjun_kim"


def test_session_row_stores_hash_not_token_and_lasts_12_hours(browser):
    r = login(browser, "user_002")
    token = r.cookies["sid"]
    row = sql(
        "SELECT id, expires_at - created_at AS span, revoked_at FROM sessions "
        "WHERE user_id = 'user_002' ORDER BY created_at DESC LIMIT 1"
    ).one()
    assert row.id.startswith("ses_") and len(row.id) == 40
    assert token not in row.id  # DB 에는 쿠키 원문이 없다
    assert row.span.total_seconds() == 12 * 3600
    assert row.revoked_at is None


def test_login_writes_audit_log(browser):
    login(browser, "user_003")
    login(browser, "user_003", "wrong-password")
    rows = sql(
        "SELECT event_type, outcome FROM auth_audit_logs WHERE user_id = 'user_003' ORDER BY occurred_at, id"
    ).all()
    assert ("LOGIN", "SUCCESS") in rows and ("LOGIN", "FAILURE") in rows


# --- 로그인 실패 (계정 존재 여부를 숨김) ----------------------------------------------
def test_wrong_password_creates_no_session(browser):
    before = count_sessions("user_005")
    r = login(browser, "user_005", "wrong-password")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "sid" not in r.cookies
    assert count_sessions("user_005") == before  # 11장: 로그인 실패 시 세션이 생성되지 않는다
    assert PW not in r.text and "wrong-password" not in r.text  # 비밀번호 원문이 응답에 없다


def test_unknown_username_and_withdrawn_user_look_the_same(browser):
    wrong_pw = login(browser, "user_005", "wrong-password").json()
    unknown = browser.post("/auth/login", json={"username": "no_such_user", "password": PW}).json()
    withdrawn = login(browser, "user_029").json()  # 탈퇴 회원: 로그인 수단이 지워져 있음
    assert wrong_pw == unknown == withdrawn


def test_login_failure_is_not_counted_in_failed_attempts(browser):
    # 6.3 표: local_credentials.failed_attempts 는 본인 확인(step-up) 실패만 센다
    before = sql("SELECT failed_attempts FROM local_credentials WHERE user_id = 'user_006'").scalar()
    login(browser, "user_006", "wrong-password")
    after = sql("SELECT failed_attempts FROM local_credentials WHERE user_id = 'user_006'").scalar()
    assert after == before


def test_step_up_lock_does_not_block_login(browser):
    # user_027 은 본인 확인 실패 5회(영구 잠금 — 시간 잠금이 아니라 locked_until 은 비어 있음) 시나리오
    row = sql("SELECT failed_attempts, locked_until FROM local_credentials WHERE user_id = 'user_027'").one()
    assert (row.failed_attempts, row.locked_until) == (5, None)
    # 그래도 로그인과 조회는 된다(중요 작업만 막힘)
    assert login(browser, "user_027").status_code == 200
    assert browser.get("/accounts").status_code == 200


def test_too_many_failures_wait_a_minute_per_username(browser):
    for _ in range(5):
        assert login(browser, "user_008", "wrong-password").status_code == 401
    r = login(browser, "user_008")  # 맞는 비밀번호여도 1분 동안은 받지 않음
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "LOGIN_TOO_MANY_ATTEMPTS"
    assert login(browser, "user_009").status_code == 200  # 다른 아이디는 영향 없음
    # 없는 아이디도 똑같이 막힌다(막히는지로 계정 존재를 알 수 없게)
    for _ in range(5):
        browser.post("/auth/login", json={"username": "ghost_user", "password": "x"})
    assert browser.post("/auth/login", json={"username": "ghost_user", "password": "x"}).status_code == 429


# --- 회원 상태 (Part 1 7.3) --------------------------------------------------------
def test_pending_verification_can_log_in_but_only_see_me(browser):
    r = login(browser, "user_028")
    assert r.json()["status"] == "PENDING_VERIFICATION"
    assert browser.get("/users/me").status_code == 200  # 가입 마무리 화면용
    assert browser.get("/accounts").json()["error"]["code"] == "SIGNUP_INCOMPLETE"


def test_restricted_user_can_log_in(browser):
    assert login(browser, "user_024").json() == {"user_id": "user_024", "status": "RESTRICTED"}


# --- 로그아웃 ----------------------------------------------------------------------
def test_logout_revokes_session_and_old_cookie_stops_working(browser):
    login(browser, "user_010")
    token = browser.cookies["sid"]
    r = browser.post("/auth/logout")
    assert r.status_code == 204
    assert 'sid=""' in r.headers["set-cookie"]  # 쿠키 지움

    # 로그아웃 후 기존 세션으로 보호 API 접근 불가 (AUTH-F05 완료 기준)
    r = browser.get("/accounts", cookies={"sid": token})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SESSION_EXPIRED"
    assert browser.post("/auth/logout").status_code == 204  # 다시 눌러도 같음
    assert sql("SELECT count(*) FROM auth_audit_logs WHERE user_id = 'user_010' AND event_type = 'LOGOUT'").scalar() == 1


def test_relogin_in_same_browser_revokes_previous_session(browser):
    login(browser, "user_011")
    first = browser.cookies["sid"]
    login(browser, "user_011")
    assert browser.get("/accounts", cookies={"sid": first}).status_code == 401


# --- 세션 만료 (유휴 10분, 최대 12시간) ------------------------------------------------
def _latest_session_set(user_id: str, assignment: str):
    sql(f"UPDATE sessions SET {assignment} WHERE id = "
        "(SELECT id FROM sessions WHERE user_id = :u ORDER BY created_at DESC LIMIT 1)", u=user_id)


def test_idle_over_10_minutes_expires(browser):
    login(browser, "user_012")
    _latest_session_set("user_012", "last_seen_at = now() - interval '9 minutes'")
    assert browser.get("/accounts").status_code == 200  # 9분: 살아 있고, last_seen_at 이 갱신된다
    assert sql("SELECT max(last_seen_at) > now() - interval '1 minute' FROM sessions WHERE user_id = 'user_012'").scalar()

    _latest_session_set("user_012", "last_seen_at = now() - interval '10 minutes 1 second'")
    r = browser.get("/accounts")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SESSION_EXPIRED"


def test_max_12_hours_expires_even_if_active(browser):
    login(browser, "user_013")
    _latest_session_set("user_013", "expires_at = now() - interval '1 second', last_seen_at = now()")
    assert browser.get("/accounts").json()["error"]["code"] == "SESSION_EXPIRED"


def test_made_up_cookie_is_401(browser):
    r = browser.get("/accounts", cookies={"sid": "made-up-token"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


# --- 개발용 헤더 · CSRF ----------------------------------------------------------------
def test_dev_header_is_ignored_when_setting_is_off(browser, monkeypatch):
    monkeypatch.setattr(settings, "auth_dev_header", False)
    assert browser.get("/accounts", headers={"X-User-Id": "user_001"}).status_code == 401


def test_post_from_unknown_origin_is_blocked(browser):
    body = {"username": username_of("user_014"), "password": PW}
    r = browser.post("/auth/login", json=body, headers={"Origin": "http://evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert browser.post("/auth/login", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert browser.post("/auth/login", json=body, headers={"Origin": "http://testserver"}).status_code == 200  # 같은 출처
