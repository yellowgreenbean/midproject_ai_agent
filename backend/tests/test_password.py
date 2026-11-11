"""아이디 찾기 · 비밀번호 재설정 · 비밀번호 변경 — 기획서 Part 1 AUTH-F06 · AUTH-F08 완료 기준과 11장 QA.

시드 회원의 비밀번호를 바꾸면 뒤에 도는 테스트(탈퇴 등)가 로그인하지 못하므로,
테스트마다 /auth/register 로 새 회원을 만들어 그 회원으로 시험한다. 이메일도 테스트마다 달리 쓴다(재발송 60초 대기).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common.db import engine
from app.main import app
from app.security import login_throttle

PW = "firstpass123"
NEW_PW = "secondpass456"


@pytest.fixture(autouse=True)
def _fresh_throttle():
    login_throttle.clear()
    yield
    login_throttle.clear()


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def other_browser():
    return TestClient(app)


def sql(query: str, **params):
    with engine.begin() as c:
        return c.execute(text(query), params)


def mail_token(browser, email: str, purpose: str) -> str:
    r = browser.post("/auth/email-verifications", json={"email": email, "purpose": purpose})
    assert r.status_code == 201, r.text
    r = browser.post("/auth/email-verifications/confirm", json={"email": email, "code": r.json()["dev_code"],
                                                                 "purpose": purpose})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def new_user(browser, username: str, email: str) -> str:
    """가입 → 이 browser 는 바로 로그인된 상태. user_id 를 돌려준다."""
    r = browser.post("/auth/register", json={
        "username": username, "password": PW, "password_confirm": PW, "email": email,
        "email_verification_token": mail_token(browser, email, "SIGNUP"), "name": "홍길동", "birth_date": "1990-01-01",
        "gender": "F", "agreed_term_ids": ["trm_001", "trm_002", "trm_003"]})
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def login(browser, username: str, password: str):
    return browser.post("/auth/login", json={"username": username, "password": password})


def start_reset(browser, username: str, email: str):
    return browser.post("/auth/password-resets", json={
        "username": username, "email": email, "email_verification_token": mail_token(browser, email, "PASSWORD_RESET")})


def confirm_reset(browser, token: str, pw: str = NEW_PW, confirm: str | None = None):
    return browser.post("/auth/password-resets/confirm", json={
        "reset_token": token, "new_password": pw, "new_password_confirm": pw if confirm is None else confirm})


def change(browser, current: str, new: str = NEW_PW, confirm: str | None = None):
    return browser.post("/users/me/password/change", json={
        "current_password": current, "new_password": new, "new_password_confirm": new if confirm is None else confirm})


def error_code(r) -> str:
    return r.json()["error"]["code"]


def allow_resend(email: str, purpose: str) -> None:
    """60초 재발송 대기를 건너뛴다 — 보낸 시각을 61초 앞으로."""
    sql("UPDATE email_verifications SET expires_at = expires_at - INTERVAL '61 seconds' "
        "WHERE email = :e AND purpose = :p", e=email, p=purpose)


# --- 아이디 찾기 ----------------------------------------------------------------------------------
def test_username_recovery_shows_masked_username_once(browser):
    uid = new_user(browser, "findme_one", "findme.one@example.com")
    token = mail_token(browser, "Findme.One@example.com", "USERNAME_RECOVERY")  # 대소문자는 같은 이메일로

    r = browser.post("/auth/username-recovery", json={"email": "findme.one@example.com",
                                                       "email_verification_token": token})
    assert r.status_code == 200, r.text
    [found] = r.json()
    assert found["username"] == "fin*******"  # 앞 3자 + 글자 수만큼 *
    assert found["created_at"].endswith("+09:00")
    assert sql("SELECT count(*) FROM auth_audit_logs WHERE user_id = :u AND event_type = 'USERNAME_RECOVERY'",
               u=uid).scalar() == 1

    again = browser.post("/auth/username-recovery", json={"email": "findme.one@example.com",
                                                           "email_verification_token": token})
    assert again.status_code == 400 and error_code(again) == "EMAIL_NOT_VERIFIED"  # 인증 토큰은 한 번만


def test_username_recovery_unknown_email_returns_empty_list(client):
    token = mail_token(client, "nobody.here@example.com", "USERNAME_RECOVERY")  # 가입 안 한 이메일도 번호는 간다
    r = client.post("/auth/username-recovery", json={"email": "nobody.here@example.com",
                                                      "email_verification_token": token})
    assert r.status_code == 200 and r.json() == []


@pytest.mark.parametrize("status, found", [("RESTRICTED", True), ("PENDING_VERIFICATION", True), ("WITHDRAWN", False)])
def test_username_recovery_by_member_status(browser, status, found):
    email = f"status.{status.lower()}@example.com"
    uid = new_user(browser, f"st_{status.lower()[:12]}", email)
    sql("UPDATE users SET status = :s WHERE id = :u", s=status, u=uid)
    r = browser.post("/auth/username-recovery", json={
        "email": email, "email_verification_token": mail_token(browser, email, "USERNAME_RECOVERY")})
    assert r.status_code == 200
    assert len(r.json()) == (1 if found else 0)


def test_signup_mail_token_cannot_be_used_for_recovery(browser):
    token = mail_token(browser, "wrong.purpose@example.com", "SIGNUP")
    r = browser.post("/auth/username-recovery", json={"email": "wrong.purpose@example.com",
                                                       "email_verification_token": token})
    assert r.status_code == 400 and error_code(r) == "EMAIL_NOT_VERIFIED"


# --- 비밀번호 재설정 -------------------------------------------------------------------------------
def test_password_reset_replaces_password_and_logs_out_everywhere(browser):
    uid = new_user(browser, "reset_ok", "reset.ok@example.com")
    phone = other_browser()
    assert login(phone, "reset_ok", PW).status_code == 200

    r = start_reset(browser, "reset_ok", "reset.ok@example.com")
    assert r.status_code == 201, r.text
    token = r.json()["reset_token"]
    stored = sql("SELECT token_digest FROM password_reset_tokens WHERE user_id = :u", u=uid).scalar()
    assert stored != token  # DB 에는 해시만

    assert confirm_reset(browser, token).status_code == 204
    assert browser.get("/users/me").status_code == 401  # 모든 기기 로그아웃
    assert phone.get("/users/me").status_code == 401
    assert login(other_browser(), "reset_ok", PW).status_code == 401  # 이전 비밀번호로는 안 됨
    assert login(other_browser(), "reset_ok", NEW_PW).status_code == 200
    assert sql("SELECT count(*) FROM notifications WHERE user_id = :u AND type = 'SECURITY'", u=uid).scalar() == 1

    reused = confirm_reset(browser, token, "thirdpass789")
    assert reused.status_code == 400 and error_code(reused) == "RESET_TOKEN_INVALID"  # 한 번만


def test_password_reset_mismatch_keeps_mail_token_for_retry(browser):
    new_user(browser, "reset_mine", "reset.mine@example.com")
    token = mail_token(browser, "reset.mine@example.com", "PASSWORD_RESET")
    body = {"email": "reset.mine@example.com", "email_verification_token": token}

    for wrong in ("no_such_user", "minjun_kim"):  # 없는 아이디 · 남의 아이디 → 같은 안내
        r = browser.post("/auth/password-resets", json={**body, "username": wrong})
        assert r.status_code == 400 and error_code(r) == "IDENTITY_MISMATCH"
    r = browser.post("/auth/password-resets", json={**body, "username": "reset_mine"})  # 같은 메일 토큰으로 다시
    assert r.status_code == 201, r.text


def test_reset_token_expires_and_newest_one_wins(browser):
    uid = new_user(browser, "reset_ttl", "reset.ttl@example.com")
    first = start_reset(browser, "reset_ttl", "reset.ttl@example.com").json()["reset_token"]
    allow_resend("reset.ttl@example.com", "PASSWORD_RESET")
    second = start_reset(browser, "reset_ttl", "reset.ttl@example.com").json()["reset_token"]

    r = confirm_reset(browser, first)
    assert r.status_code == 400 and error_code(r) == "RESET_TOKEN_INVALID"  # 새로 받으면 이전 것은 무효

    # 6분: TIMESTAMP(0) 는 초 아래를 반올림해 저장하므로 딱 5분만 빼면 1초 안쪽으로 아직 유효할 수 있다
    sql("UPDATE password_reset_tokens SET expires_at = expires_at - INTERVAL '6 minutes' WHERE user_id = :u", u=uid)
    r = confirm_reset(browser, second)
    assert r.status_code == 400 and error_code(r) == "RESET_TOKEN_INVALID"  # 5분 지남


def test_reset_confirm_rejects_bad_new_password_but_keeps_token(browser):
    new_user(browser, "reset_rule", "reset.rule@example.com")
    token = start_reset(browser, "reset_rule", "reset.rule@example.com").json()["reset_token"]

    for pw, confirm, code in [("short1", None, "INVALID_PASSWORD"), (NEW_PW, "different1", "PASSWORD_MISMATCH"),
                              (PW, None, "SAME_AS_OLD_PASSWORD")]:
        r = confirm_reset(browser, token, pw, confirm)
        assert r.status_code == 400 and error_code(r) == code
    assert confirm_reset(browser, token).status_code == 204  # 실패해도 토큰은 5분 안에 다시 쓸 수 있다


def test_reset_does_not_unlock_step_up(browser):
    uid = new_user(browser, "reset_lock", "reset.lock@example.com")
    sql("UPDATE local_credentials SET failed_attempts = 5 WHERE user_id = :u", u=uid)
    token = start_reset(browser, "reset_lock", "reset.lock@example.com").json()["reset_token"]
    assert confirm_reset(browser, token).status_code == 204

    assert sql("SELECT failed_attempts FROM local_credentials WHERE user_id = :u", u=uid).scalar() == 5
    phone = other_browser()
    assert login(phone, "reset_lock", NEW_PW).status_code == 200  # 로그인은 되지만
    r = phone.post("/auth/step-up", json={"action": "TRANSFER", "password": NEW_PW})
    assert r.status_code == 423 and error_code(r) == "STEP_UP_LOCKED"  # 본인 확인 잠금은 그대로(영업점 방문)


# --- 비밀번호 변경 -------------------------------------------------------------------------------
def test_change_password_keeps_this_session_and_logs_out_others(browser):
    uid = new_user(browser, "change_ok", "change.ok@example.com")
    phone = other_browser()
    assert login(phone, "change_ok", PW).status_code == 200

    assert change(browser, PW).status_code == 204
    assert browser.get("/users/me").status_code == 200  # 지금 브라우저는 그대로
    assert phone.get("/users/me").status_code == 401  # 다른 기기는 로그아웃
    assert login(other_browser(), "change_ok", PW).status_code == 401
    assert login(other_browser(), "change_ok", NEW_PW).status_code == 200
    assert sql("SELECT count(*) FROM notifications WHERE user_id = :u AND type = 'SECURITY'", u=uid).scalar() == 1


def test_change_wrong_current_password_counts_toward_step_up_lock(browser):
    uid = new_user(browser, "change_bad", "change.bad@example.com")
    r = change(browser, PW, "short1")  # 새 비밀번호 형식 오류는 실패로 세지 않는다
    assert r.status_code == 400 and error_code(r) == "INVALID_PASSWORD"

    for left in (4, 3, 2, 1):
        r = change(browser, "wrongpass1")
        assert r.status_code == 400 and error_code(r) == "WRONG_PASSWORD"
        assert f"{left}번 더" in r.json()["error"]["message"]
    r = change(browser, "wrongpass1")
    assert r.status_code == 423 and error_code(r) == "STEP_UP_LOCKED"
    assert change(browser, PW).status_code == 423  # 잠긴 뒤에는 맞는 비밀번호도 안 됨
    assert sql("SELECT failed_attempts FROM local_credentials WHERE user_id = :u", u=uid).scalar() == 5


def test_change_rejects_same_or_mismatched_new_password(browser):
    new_user(browser, "change_same", "change.same@example.com")
    r = change(browser, PW, PW)
    assert r.status_code == 400 and error_code(r) == "SAME_AS_OLD_PASSWORD"
    r = change(browser, PW, NEW_PW, "different1")
    assert r.status_code == 400 and error_code(r) == "PASSWORD_MISMATCH"


def test_change_password_requires_login():
    r = other_browser().post("/users/me/password/change", json={
        "current_password": PW, "new_password": NEW_PW, "new_password_confirm": NEW_PW})
    assert r.status_code == 401
