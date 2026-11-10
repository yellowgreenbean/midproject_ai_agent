"""회원가입 — 기획서 Part 1 AUTH-F01·F02·F03·F10 완료 기준.

테스트 DB 는 conftest.py 가 시드까지 넣어 새로 만든다. 가입 약관 4개(trm_001~003 필수, trm_004 선택)는 seed_scenarios.py.
테스트마다 다른 이메일을 써서 재발송 대기(60초)·하루 발송 제한에 서로 걸리지 않게 한다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app

REQUIRED = ["trm_001", "trm_002", "trm_003"]


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def sql(query: str, **params):
    with engine.begin() as c:
        return c.execute(text(query), params)


def verified_token(browser, email: str) -> str:
    r = browser.post("/auth/email-verifications", json={"email": email, "purpose": "SIGNUP"})
    assert r.status_code == 201, r.text
    r = browser.post("/auth/email-verifications/confirm", json={"email": email, "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def body(username: str, email: str, token: str, **over) -> dict:
    return {"username": username, "password": "goodpass123", "password_confirm": "goodpass123", "email": email,
            "email_verification_token": token, "name": "홍길동", "birth_date": "1995-05-05", "gender": "M",
            "payday": 25, "agreed_term_ids": REQUIRED, **over}


# --- 약관 · 아이디 중복 확인 ------------------------------------------------------------------------
def test_terms_lists_common_terms_required_first(client):
    r = client.get("/terms")
    assert r.status_code == 200
    assert [(t["id"], t["required"]) for t in r.json()] == [
        ("trm_001", True), ("trm_002", True), ("trm_003", True), ("trm_004", False)]


def test_username_availability_distinguishes_free_taken_and_bad_format(client):
    assert client.get("/auth/usernames/availability", params={"username": "brand_new1"}).json() == {"available": True}
    assert client.get("/auth/usernames/availability", params={"username": "minjun_kim"}).json() == {"available": False}
    r = client.get("/auth/usernames/availability", params={"username": "Bad!"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_USERNAME"


# --- 정상 가입 ----------------------------------------------------------------------------------
def test_signup_creates_user_logs_in_and_hides_password(browser):
    token = verified_token(browser, "New.User@Example.com")  # 대소문자는 소문자로 맞춰 저장
    r = browser.post("/auth/register", json=body("new_user1", "new.user@example.com", token,
                                                  agreed_term_ids=REQUIRED + ["trm_004"]))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["username"] == "new_user1" and out["status"] == "ACTIVE" and out["user_id"].startswith("user_")
    assert "goodpass123" not in r.text

    # 바로 로그인됨: 쿠키로 내 정보가 보인다
    assert "sid=" in r.headers["set-cookie"]
    me = browser.get("/users/me").json()
    assert (me["id"], me["email"], me["payday"]) == (out["user_id"], "new.user@example.com", 25)
    assert me["email_verified_at"] is not None

    uid = out["user_id"]
    pw_hash = sql("SELECT password_hash FROM local_credentials WHERE user_id = :u", u=uid).scalar()
    assert pw_hash.startswith("$argon2id$") and "goodpass123" not in pw_hash
    assert sql("SELECT provider, provider_subject FROM auth_identities WHERE user_id = :u", u=uid).one() == (
        "LOCAL", "new_user1")
    consents = dict(sql("SELECT terms_id, agreed FROM user_consents WHERE user_id = :u", u=uid).all())
    assert consents == {"trm_001": True, "trm_002": True, "trm_003": True, "trm_004": True}
    assert sql("SELECT count(*) FROM email_verifications WHERE email = 'new.user@example.com'").scalar() == 0

    # 새 브라우저에서 같은 아이디·비밀번호로 로그인된다
    with TestClient(app) as other:
        r = other.post("/auth/login", json={"username": "new_user1", "password": "goodpass123"})
        assert r.status_code == 200 and r.json()["user_id"] == uid


def test_optional_term_not_agreed_is_recorded_as_false(browser):
    token = verified_token(browser, "opt@example.com")
    uid = browser.post("/auth/register", json=body("opt_user", "opt@example.com", token)).json()["user_id"]
    assert sql("SELECT agreed FROM user_consents WHERE user_id = :u AND terms_id = 'trm_004'", u=uid).scalar() is False


# --- 가입 실패 ----------------------------------------------------------------------------------
def test_signup_rejects_taken_username_and_keeps_token_usable(browser):
    token = verified_token(browser, "dup@example.com")
    r = browser.post("/auth/register", json=body("minjun_kim", "dup@example.com", token))
    assert r.status_code == 409 and r.json()["error"]["code"] == "USERNAME_TAKEN"
    # 아이디만 바꾸면 같은 인증으로 가입할 수 있다(실패한 요청은 토큰을 쓰지 않음)
    assert browser.post("/auth/register", json=body("dup_user", "dup@example.com", token)).status_code == 201


def test_token_is_one_time_and_bound_to_its_email(browser):
    token = verified_token(browser, "once@example.com")
    r = browser.post("/auth/register", json=body("other_mail", "someone@example.com", token))
    assert r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert browser.post("/auth/register", json=body("once_user", "once@example.com", token)).status_code == 201
    r = browser.post("/auth/register", json=body("twice_user", "once@example.com", token))
    assert r.status_code == 400 and r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


def test_token_expires_30_minutes_after_verification(browser):
    token = verified_token(browser, "late@example.com")
    sql("UPDATE email_verifications SET used_at = used_at - INTERVAL '31 minutes' WHERE email = 'late@example.com'")
    r = browser.post("/auth/register", json=body("late_user", "late@example.com", token))
    assert r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


@pytest.mark.parametrize("over, code", [
    ({"agreed_term_ids": ["trm_001", "trm_002"]}, "REQUIRED_TERMS_NOT_AGREED"),
    ({"agreed_term_ids": REQUIRED + ["trm_999"]}, "INVALID_TERMS"),
    ({"password_confirm": "goodpass124"}, "PASSWORD_MISMATCH"),
    ({"password": "onlyletters", "password_confirm": "onlyletters"}, "INVALID_PASSWORD"),
    ({"password": "bad_rule1x", "password_confirm": "bad_rule1x"}, "INVALID_PASSWORD"),  # 아이디가 들어감
    ({"name": "홍"}, "INVALID_NAME"),
    ({"birth_date": "2999-01-01"}, "INVALID_BIRTH_DATE"),
])
def test_signup_revalidates_every_field_on_server(browser, over, code):
    email = f"bad{abs(hash(code + str(over))) % 10**8}@example.com"
    token = verified_token(browser, email)
    r = browser.post("/auth/register", json=body("bad_rule1", email, token, **over))
    assert r.status_code == 400 and r.json()["error"]["code"] == code
    assert sql("SELECT count(*) FROM users WHERE username = 'bad_rule1'").scalar() == 0


def test_email_already_used_by_member_is_rejected_at_send(client):
    r = client.post("/auth/email-verifications", json={"email": "Minjun.Kim@example.com", "purpose": "SIGNUP"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"


# --- 이메일 인증 규칙 --------------------------------------------------------------------------------
def test_wrong_code_five_times_locks_that_code(client):
    sent = client.post("/auth/email-verifications", json={"email": "wrong@example.com"}).json()
    wrong = "000000" if sent["dev_code"] != "000000" else "111111"
    for left in (4, 3, 2, 1):
        r = client.post("/auth/email-verifications/confirm", json={"email": "wrong@example.com", "code": wrong})
        assert r.json()["error"]["code"] == "EMAIL_CODE_MISMATCH" and f"{left}번" in r.json()["error"]["message"]
    client.post("/auth/email-verifications/confirm", json={"email": "wrong@example.com", "code": wrong})
    r = client.post("/auth/email-verifications/confirm", json={"email": "wrong@example.com", "code": sent["dev_code"]})
    assert r.status_code == 429 and r.json()["error"]["code"] == "EMAIL_VERIFICATION_LOCKED"


def test_expired_code_fails(client):
    sent = client.post("/auth/email-verifications", json={"email": "exp@example.com"}).json()
    sql("UPDATE email_verifications SET expires_at = expires_at - INTERVAL '6 minutes' WHERE email = 'exp@example.com'")
    r = client.post("/auth/email-verifications/confirm", json={"email": "exp@example.com", "code": sent["dev_code"]})
    assert r.json()["error"]["code"] == "EMAIL_VERIFICATION_EXPIRED"


def test_resend_waits_60s_and_new_code_replaces_old(client):
    first = client.post("/auth/email-verifications", json={"email": "again@example.com"}).json()
    r = client.post("/auth/email-verifications", json={"email": "again@example.com"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "EMAIL_RESEND_TOO_SOON"
    # 61초 지난 것처럼 만들고 다시 받으면, 예전 번호는 더 이상 안 맞는다
    sql("UPDATE email_verifications SET expires_at = expires_at - INTERVAL '61 seconds' WHERE email = 'again@example.com'")
    second = client.post("/auth/email-verifications", json={"email": "again@example.com"}).json()
    if first["dev_code"] != second["dev_code"]:
        r = client.post("/auth/email-verifications/confirm", json={"email": "again@example.com", "code": first["dev_code"]})
        assert r.json()["error"]["code"] == "EMAIL_CODE_MISMATCH"
    r = client.post("/auth/email-verifications/confirm", json={"email": "again@example.com", "code": second["dev_code"]})
    assert r.status_code == 200


def test_daily_send_limit(client):
    for _ in range(10):
        assert client.post("/auth/email-verifications", json={"email": "many@example.com"}).status_code == 201
        sql("UPDATE email_verifications SET expires_at = expires_at - INTERVAL '61 seconds' WHERE email = 'many@example.com'")
    r = client.post("/auth/email-verifications", json={"email": "many@example.com"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "EMAIL_SEND_LIMIT"


def test_code_is_not_stored_in_plain_text(client):
    code = client.post("/auth/email-verifications", json={"email": "plain@example.com"}).json()["dev_code"]
    stored = sql("SELECT challenge_digest FROM email_verifications WHERE email = 'plain@example.com'").scalar()
    assert code not in stored and len(stored) == 64
