"""본인 확인(POST /auth/step-up)과 회원 탈퇴(AUTH-F09) — 기획서 Part 1 AUTH-F09 완료 기준, 11장 1차 QA(본인 확인).

새 회원은 가입 API(tests/test_signup.py 의 도우미)로 만들고, 계좌는 테스트 안에서 SQL 로 넣는다(더미 회원은 모두 잔액·카드가 있어
탈퇴 성공 시나리오를 만들 수 없다). 막히는 시나리오는 시드 회원 user_001(잔액·자동이체·카드 있음)로 본다.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import one_month_before, purge_withdrawn_users
from app.main import app
from app.rules import WITHDRAWAL_DATA_REVIEW_VERSION
from tests.conftest import as_user, seed_password
from tests.test_signup import body, sql, verified_token

PW = "goodpass123"  # tests/test_signup.body() 의 비밀번호
_n = iter(range(1, 1000))


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def new_member(browser) -> str:
    """가입(= 바로 로그인)한 새 회원의 id."""
    n = next(_n)
    token = verified_token(browser, f"wd{n}@example.com")
    r = browser.post("/auth/register", json=body(f"wd_user{n}", f"wd{n}@example.com", token))
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def add_account(user_id: str, acc_id: str, status: str = "ACTIVE", balance: int = 0) -> None:
    no = "1109999" + acc_id[-7:].rjust(7, "0")
    sql("""INSERT INTO accounts (id, user_id, "resAccount", "resAccountDisplay", "resAccountName", account_type,
                                 lifecycle_status, "resAccountNickName", is_favorite, "resAccountStartDate")
           VALUES (:id, :u, :no, :no, '입출금통장', 'CHECKING', :st, '비상금', TRUE, '20261101')""",
        id=acc_id, u=user_id, no=no, st=status)
    sql("INSERT INTO account_balances (account_id, balance) VALUES (:id, :b)", id=acc_id, b=balance)


def step_up(browser, action: str = "WITHDRAWAL", password: str = PW):
    return browser.post("/auth/step-up", json={"action": action, "password": password})


def finish_checks(browser) -> dict:
    browser.get("/users/me/withdrawal-checks")
    browser.post("/users/me/withdrawal-checks/data-review", json={"version": WITHDRAWAL_DATA_REVIEW_VERSION})
    return browser.post("/users/me/withdrawal-checks/linked-services").json()


def withdraw(browser, challenge_id: str):
    return browser.post("/users/me/withdraw", json={"step_up_challenge_id": challenge_id})


# --- 본인 확인 ----------------------------------------------------------------------------------
def test_step_up_wrong_password_counts_and_locks_forever(browser):
    uid = new_member(browser)
    for left in (4, 3, 2, 1):
        r = step_up(browser, password="wrongpass1")
        assert r.status_code == 400 and r.json()["error"]["code"] == "STEP_UP_FAILED" and f"{left}번" in r.text
    r = step_up(browser, password="wrongpass1")
    assert r.status_code == 423 and r.json()["error"]["code"] == "STEP_UP_LOCKED"
    assert step_up(browser).status_code == 423  # 맞는 비밀번호도 거절 (영구 잠금)
    assert sql("SELECT failed_attempts FROM local_credentials WHERE user_id = :u", u=uid).scalar() == 5
    assert browser.get("/users/me").status_code == 200  # 로그인·조회는 그대로


def test_step_up_success_resets_failures(browser):
    uid = new_member(browser)
    step_up(browser, password="wrongpass1")
    r = step_up(browser)
    assert r.status_code == 201 and r.json()["step_up_challenge_id"].startswith("stu_")
    assert sql("SELECT failed_attempts FROM local_credentials WHERE user_id = :u", u=uid).scalar() == 0


def test_seed_user_027_is_step_up_locked(browser):
    username = sql("SELECT username FROM users WHERE id = 'user_027'").scalar()
    assert browser.post("/auth/login", json={"username": username, "password": seed_password()}).status_code == 200
    assert step_up(browser, password=seed_password()).json()["error"]["code"] == "STEP_UP_LOCKED"


def test_step_up_needs_a_real_session(client):
    r = client.post("/auth/step-up", json={"action": "WITHDRAWAL", "password": "x"}, headers=as_user("user_001"))
    assert r.status_code == 401


# --- 탈퇴 성공 ----------------------------------------------------------------------------------
def test_new_member_withdraws_end_to_end(browser):
    uid = new_member(browser)
    st = browser.get("/users/me/withdrawal-checks").json()
    assert (st["money_ok"], st["data_reviewed"], st["linked_ok"], st["can_withdraw"]) == (True, False, False, False)

    r = browser.post("/users/me/withdrawal-checks/data-review", json={"version": "1999-01-01"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DATA_REVIEW_OUTDATED"
    assert finish_checks(browser)["can_withdraw"] is True

    # 본인 확인 번호: 없거나 · 다른 작업 것이면 거절
    assert withdraw(browser, "stu_nope").json()["error"]["code"] == "STEP_UP_REQUIRED"
    other = step_up(browser, "TRANSFER").json()["step_up_challenge_id"]
    assert withdraw(browser, other).json()["error"]["code"] == "STEP_UP_REQUIRED"

    r = withdraw(browser, step_up(browser).json()["step_up_challenge_id"])
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["closed_account_ids"]) == ("WITHDRAWN", [])

    # 탈퇴 뒤: 보호 API·로그인 모두 막힘
    assert browser.get("/users/me").status_code == 401
    username = sql("SELECT username FROM users WHERE id = :u", u=uid).scalar()
    assert browser.post("/auth/login", json={"username": username, "password": PW}).status_code == 401

    # DB: 상태·세션·즉시 삭제·동의 철회·점검 기록·감사 기록
    assert sql("SELECT status FROM users WHERE id = :u", u=uid).scalar() == "WITHDRAWN"
    assert sql("SELECT count(*) FROM local_credentials WHERE user_id = :u", u=uid).scalar() == 0
    assert sql("SELECT count(*) FROM sessions WHERE user_id = :u AND revoked_at IS NULL", u=uid).scalar() == 0
    latest = dict(sql("""SELECT DISTINCT ON (terms_id) terms_id, agreed FROM user_consents WHERE user_id = :u
                         ORDER BY terms_id, recorded_at DESC, agreed""", u=uid).all())
    assert set(latest.values()) == {False}
    assert sql("SELECT status FROM withdrawal_checks WHERE user_id = :u", u=uid).scalar() == "COMPLETED"
    assert sql("SELECT count(*) FROM auth_audit_logs WHERE user_id = :u AND event_type = 'WITHDRAWAL'", u=uid).scalar() == 1

    # 아이디는 영원히 막히고, 이메일은 다시 가입할 수 있다
    assert browser.get("/auth/usernames/availability", params={"username": username}).json() == {"available": False}
    email = sql("SELECT email FROM users WHERE id = :u", u=uid).scalar()
    assert browser.post("/auth/email-verifications", json={"email": email}).status_code == 201


def test_zero_balance_accounts_are_closed_including_suspended(browser):
    uid = new_member(browser)
    add_account(uid, "acc_wd0001")
    add_account(uid, "acc_wd0002", status="SUSPENDED")  # 잔액 0원 정지 계좌는 정지 해제 없이 해지(확정 예외)
    sql("INSERT INTO notification_preferences (user_id, account_id) VALUES (:u, 'acc_wd0001')", u=uid)
    sql("""INSERT INTO favorite_accounts (id, user_id, bank, account_no, holder_name)
           VALUES ('fav_wd01', :u, '두린은행', '11000000000007', '이서연')""", u=uid)
    assert finish_checks(browser)["can_withdraw"] is True

    r = withdraw(browser, step_up(browser).json()["step_up_challenge_id"])
    assert r.status_code == 200 and r.json()["closed_account_ids"] == ["acc_wd0001", "acc_wd0002"]
    rows = sql("""SELECT lifecycle_status, closed_at IS NOT NULL, "resAccountNickName", is_favorite FROM accounts
                  WHERE user_id = :u ORDER BY id""", u=uid).all()
    assert rows == [("CLOSED", True, None, False)] * 2
    logs = sql("""SELECT account_id, metadata->>'reason', metadata->>'from_status' FROM account_activity_logs
                  WHERE account_id IN ('acc_wd0001', 'acc_wd0002') ORDER BY account_id""").all()
    assert logs == [("acc_wd0001", "회원 탈퇴", "ACTIVE"), ("acc_wd0002", "회원 탈퇴", "SUSPENDED")]
    assert sql("SELECT count(*) FROM notification_preferences WHERE user_id = :u", u=uid).scalar() == 0
    assert sql("SELECT count(*) FROM favorite_accounts WHERE user_id = :u", u=uid).scalar() == 0


# --- 탈퇴 막힘 ----------------------------------------------------------------------------------
def test_seed_user_with_money_autopay_and_cards_is_blocked(browser):
    r = browser.post("/auth/login", json={"username": "minjun_kim", "password": seed_password()})
    assert r.status_code == 200
    st = browser.get("/users/me/withdrawal-checks").json()
    assert st["money_ok"] is False and st["linked_ok"] is False
    assert any(i["href"] == "#/transfer?from=acc_001" and "원 남아 있어요" in i["detail"] for i in st["money_items"])
    assert {i["label"] for i in st["linked_items"]} >= {"자동이체", "예약 송금"}
    assert any(i["href"].startswith("#/cards/") for i in st["linked_items"])

    r = browser.post("/users/me/withdrawal-checks/linked-services")
    assert r.status_code == 409 and r.json()["error"]["code"] == "LINKED_SERVICES_REMAIN"
    browser.post("/users/me/withdrawal-checks/data-review", json={"version": WITHDRAWAL_DATA_REVIEW_VERSION})
    r = withdraw(browser, step_up(browser, password=seed_password()).json()["step_up_challenge_id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "WITHDRAWAL_NOT_READY" and "①" in r.text
    assert sql("SELECT status FROM users WHERE id = 'user_001'").scalar() == "ACTIVE"


def test_money_arriving_before_final_confirm_stops_withdrawal(browser):
    """화면은 「완료」여도 최종 확인 때 서버가 다시 본다. 실패하면 아무것도 안 바뀌고 본인 확인 번호도 다시 쓸 수 있다."""
    uid = new_member(browser)
    add_account(uid, "acc_wd0003")
    assert finish_checks(browser)["can_withdraw"] is True
    sql("UPDATE account_balances SET balance = 1000 WHERE account_id = 'acc_wd0003'")  # 그 사이 입금

    challenge = step_up(browser).json()["step_up_challenge_id"]
    r = withdraw(browser, challenge)
    assert r.status_code == 409 and "① 남은 돈 옮기기" in r.json()["error"]["message"]
    assert sql("SELECT status FROM users WHERE id = :u", u=uid).scalar() == "ACTIVE"
    assert sql("SELECT lifecycle_status FROM accounts WHERE id = 'acc_wd0003'").scalar() == "ACTIVE"

    sql("UPDATE account_balances SET balance = 0 WHERE account_id = 'acc_wd0003'")  # 다시 옮김
    assert withdraw(browser, challenge).status_code == 200


def test_data_review_must_be_redone_when_notice_changes(browser, monkeypatch):
    new_member(browser)
    assert finish_checks(browser)["data_reviewed"] is True
    monkeypatch.setattr("app.routers.withdrawal.WITHDRAWAL_DATA_REVIEW_VERSION", "2099-01-01")
    st = browser.get("/users/me/withdrawal-checks").json()
    assert (st["data_reviewed"], st["can_withdraw"]) == (False, False)


# --- 1개월 뒤 가명 처리 (app/jobs.py) ------------------------------------------------------------------
def test_one_month_before_handles_month_ends():
    assert one_month_before(datetime(2026, 3, 31, 9)) == datetime(2026, 2, 28, 9)
    assert one_month_before(datetime(2026, 1, 15)) == datetime(2025, 12, 15)


def test_purge_pseudonymizes_after_one_month_and_keeps_username(browser):
    uid = new_member(browser)
    finish_checks(browser)
    assert withdraw(browser, step_up(browser).json()["step_up_challenge_id"]).status_code == 200
    username = sql("SELECT username FROM users WHERE id = :u", u=uid).scalar()

    with Session(engine) as db:
        assert uid not in purge_withdrawn_users(db, datetime.now())  # 아직 유예 기간
        sql("UPDATE users SET withdrawn_at = withdrawn_at - INTERVAL '1 month 1 day' WHERE id = :u", u=uid)
        assert uid in purge_withdrawn_users(db, datetime.now())
        db.commit()
        assert uid not in purge_withdrawn_users(db, datetime.now())  # 다시 돌려도 그대로

    row = sql("SELECT username, name, email, email_verified_at, payday, birth_date FROM users WHERE id = :u", u=uid).one()
    assert (row.username, row.name, row.email, row.email_verified_at, row.payday) == (username, "탈퇴회원", None, None, None)
    assert (row.birth_date.month, row.birth_date.day, row.birth_date.year) == (1, 1, 1995)
    assert sql("SELECT count(*) FROM auth_identities WHERE user_id = :u", u=uid).scalar() == 0
    assert sql("SELECT count(*) FROM user_consents WHERE user_id = :u", u=uid).scalar() > 0  # 보존 기록은 그대로
