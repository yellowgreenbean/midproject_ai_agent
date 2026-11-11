"""ACCT-F05 계좌 상태 관리 — 일시정지(suspend) · 정지 해제(resume) · 해지(close). 기획서 Part 2 3장 · 7.3 · 9.3 · 13.2.

정상 흐름은 새로 가입한 회원이 직접 연 계좌로 시험한다(시드를 바꾸지 않게).
해지 거절 사유는 시드 acc_001(user_001)로 본다: 잔액 1,250,000원 · 예약·자동이체 · 진행 중 적금 · 연결 카드가 모두 걸려 있다.
거절된 해지는 롤백되므로 acc_001 은 그대로 남는다.
"""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import internal
from app.main import app
from app.rules import KST
from tests.conftest import as_user, seed_password
from tests.test_api import error_code
from tests.test_signup import sql
from tests.test_withdrawal import PW, new_member

ALL_BLOCKERS = ["BALANCE_REMAINING", "PENDING_TRANSFER", "LINKED_SUBSCRIPTION", "LINKED_CARD"]


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def step_up(browser, password: str = PW, action: str = "ACCOUNT_STATUS_CHANGE") -> str:
    r = browser.post("/auth/step-up", json={"action": action, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def change(browser, acc_id: str, op: str, password: str = PW, action: str = "ACCOUNT_STATUS_CHANGE"):
    return browser.post(f"/accounts/{acc_id}/{op}", json={"step_up_challenge_id": step_up(browser, password, action)})


def open_account(browser) -> str:
    r = browser.post("/accounts", json={"account_type": "CHECKING", "consents": ["required_terms"],
                                        "step_up_challenge_id": step_up(browser, action="ACCOUNT_OPEN")},
                     headers={"Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def actions(acc_id: str) -> list[str]:
    # occurred_at 은 초 단위라 한 테스트 안의 기록은 시각이 같을 수 있다 — 순서 말고 무엇이 몇 번 남았는지만 본다
    return sorted(sql("SELECT action FROM account_activity_logs WHERE account_id = :a", a=acc_id).scalars())


def test_suspend_resume_close_scenario(browser):
    """시나리오 A·B: 개설 → 일시정지 → 해제 → 해지 (완료 기준 1)."""
    uid = new_member(browser)
    acc = open_account(browser)
    assert browser.get(f"/accounts/{acc}").json()["close_blockers"] == []  # 잔액 0원, 연결된 것 없음

    r = change(browser, acc, "suspend")
    assert r.status_code == 200, r.text
    assert (r.json()["lifecycle_status"], r.json()["close_blockers"]) == ("SUSPENDED", [])
    r = change(browser, acc, "suspend")  # 이미 정지
    assert r.status_code == 409 and error_code(r) == "ACCOUNT_ALREADY_SUSPENDED"
    r = change(browser, acc, "close")  # 사용자 해지는 정지 해제가 먼저 (확정)
    assert r.status_code == 409 and error_code(r) == "INVALID_STATUS_TRANSITION"

    r = change(browser, acc, "resume")
    assert r.status_code == 200 and r.json()["lifecycle_status"] == "ACTIVE"

    r = change(browser, acc, "close")
    assert r.status_code == 200, r.text
    today = datetime.now(KST).strftime("%Y%m%d")
    assert (r.json()["lifecycle_status"], r.json()["closed_at"], r.json()["is_favorite"]) == ("CLOSED", today, False)
    assert acc not in {a["id"] for a in browser.get("/accounts").json()}  # 기본 목록에서 빠지고
    assert acc in {a["id"] for a in browser.get("/accounts?status=CLOSED").json()}  # 해지 이력으로 남는다(삭제 아님)

    for op, code in [("close", "INVALID_STATUS_TRANSITION"), ("suspend", "INVALID_STATUS_TRANSITION"),
                     ("resume", "ACCOUNT_NOT_SUSPENDED")]:  # 해지 계좌는 재해지·재활성화 불가
        r = change(browser, acc, op)
        assert r.status_code == 409 and error_code(r) == code, op

    assert actions(acc) == sorted(["OPEN", "SUSPEND", "RESUME", "CLOSE"])  # 실패한 요청은 기록되지 않는다
    log = sql("SELECT actor_id, metadata FROM account_activity_logs WHERE account_id = :a AND action = 'CLOSE'", a=acc).one()
    assert log.actor_id == uid and log.metadata["from_status"] == "ACTIVE"


def test_status_change_needs_step_up_for_that_action(browser):
    new_member(browser)
    acc = open_account(browser)
    r = browser.post(f"/accounts/{acc}/suspend", json={"step_up_challenge_id": "stu_nope"})
    assert r.status_code == 403 and error_code(r) == "STEP_UP_REQUIRED"
    r = change(browser, acc, "suspend", action="TRANSFER")  # 다른 작업용 번호
    assert r.status_code == 403 and error_code(r) == "STEP_UP_REQUIRED"
    challenge = step_up(browser)
    assert browser.post(f"/accounts/{acc}/suspend", json={"step_up_challenge_id": challenge}).status_code == 200
    r = browser.post(f"/accounts/{acc}/resume", json={"step_up_challenge_id": challenge})  # 한 번 쓴 번호
    assert r.status_code == 403 and error_code(r) == "STEP_UP_REQUIRED"
    assert actions(acc) == sorted(["OPEN", "SUSPEND"])


def test_dev_header_cannot_change_status(client):
    # 본인 확인 번호는 로그인 세션에 묶인다 — 세션 없는 개발용 헤더로는 상태를 못 바꾼다
    r = client.post("/accounts/acc_002/suspend", json={"step_up_challenge_id": "stu_x"}, headers=as_user("user_001"))
    assert r.status_code == 403 and error_code(r) == "STEP_UP_REQUIRED"


def test_other_users_account_is_404(browser):
    new_member(browser)
    for op in ("suspend", "resume", "close"):
        r = change(browser, "acc_001", op)
        assert r.status_code == 404 and error_code(r) == "ACCOUNT_NOT_FOUND", op
    assert sql("SELECT lifecycle_status FROM accounts WHERE id = 'acc_001'").scalar() == "ACTIVE"


def test_detail_shows_close_blockers(client):
    assert client.get("/accounts/acc_001", headers=as_user("user_001")).json()["close_blockers"] == ALL_BLOCKERS
    # 해지 계좌는 막힘 사유가 없다
    assert client.get("/accounts/acc_006", headers=as_user("user_001")).json()["close_blockers"] == []


def test_close_refused_with_all_reasons_and_nothing_changes(browser):
    username = sql("SELECT username FROM users WHERE id = 'user_001'").scalar()
    assert browser.post("/auth/login", json={"username": username, "password": seed_password()}).status_code == 200
    r = change(browser, "acc_001", "close", password=seed_password())
    assert r.status_code == 409
    err = r.json()["error"]
    assert (err["code"], err["reasons"]) == ("ACCOUNT_CLOSE_NOT_ALLOWED", ALL_BLOCKERS)
    assert "잔액이 남아 있어요" in err["message"]
    assert sql("SELECT lifecycle_status, closed_at FROM accounts WHERE id = 'acc_001'").one() == ("ACTIVE", None)
    assert "CLOSE" not in actions("acc_001")


def test_close_refused_by_balance_only(browser):
    new_member(browser)
    acc = open_account(browser)
    sql("UPDATE account_balances SET balance = 1000 WHERE account_id = :a", a=acc)  # 거래 파트가 넣은 돈이라고 보고
    assert browser.get(f"/accounts/{acc}").json()["close_blockers"] == ["BALANCE_REMAINING"]
    r = change(browser, acc, "close")
    assert r.status_code == 409 and r.json()["error"]["reasons"] == ["BALANCE_REMAINING"]
    sql("UPDATE account_balances SET balance = 0 WHERE account_id = :a", a=acc)  # 돈을 옮긴 뒤에는
    assert change(browser, acc, "close").json()["lifecycle_status"] == "CLOSED"


def _python_error(*_):
    raise RuntimeError("카드 파트 응답 없음")  # 다른 파트 서버가 생기면: 타임아웃·5xx·연결 실패 자리


def _db_error(db, *_):
    db.execute(text("SELECT 1/0"))  # 쿼리 오류 — PostgreSQL 은 이 뒤의 쿼리를 모두 거부한다(저장점이 없으면)


def test_failed_check_blocks_as_that_reason(browser, monkeypatch):
    """점검이 실패하면 「문제없음」이 아니라 그 점검의 사유로 막는다(사용자 결정 2026-11-10)."""
    new_member(browser)
    acc = open_account(browser)
    monkeypatch.setattr(internal, "card_blockers", _python_error)
    assert browser.get(f"/accounts/{acc}").json()["close_blockers"] == ["LINKED_CARD"]  # 상세는 열린다
    r = change(browser, acc, "close")
    assert r.status_code == 409
    assert (r.json()["error"]["reasons"], r.json()["error"]["message"]) == (
        ["LINKED_CARD"], "이 계좌에 연결된 카드가 있어요. 카드 결제 계좌를 바꾸거나 카드를 해지해 주세요.")
    assert sql("SELECT lifecycle_status FROM accounts WHERE id = :a", a=acc).scalar() == "ACTIVE"

    monkeypatch.undo()  # 점검이 다시 되면 해지된다
    assert change(browser, acc, "close").json()["lifecycle_status"] == "CLOSED"


def test_failed_db_query_in_one_check_does_not_break_the_others(browser, monkeypatch):
    new_member(browser)
    acc = open_account(browser)
    sql("UPDATE account_balances SET balance = 1000 WHERE account_id = :a", a=acc)
    monkeypatch.setattr(internal, "transfer_blockers", _db_error)  # 첫 점검이 쿼리 오류
    # 저장점 덕에 뒤의 점검(상품·카드)도 정상으로 돌고, 계좌 상세·잔액도 그대로 나온다
    r = browser.get(f"/accounts/{acc}")
    assert r.status_code == 200 and r.json()["close_blockers"] == ["BALANCE_REMAINING", "PENDING_TRANSFER"]
    r = change(browser, acc, "close")
    assert r.status_code == 409 and r.json()["error"]["reasons"] == ["BALANCE_REMAINING", "PENDING_TRANSFER"]


def test_suspended_account_blocks_transfers(browser):
    """정지 계좌는 입금·출금 모두 막는다(확정, 10.3) — 거래 파트가 새 상태를 본다(ACCT-F05 일시정지 6)."""
    new_member(browser)
    src, dst = open_account(browser), open_account(browser)
    sql("UPDATE account_balances SET balance = 50000 WHERE account_id = :a", a=src)
    to_no = sql('SELECT "resAccount" FROM accounts WHERE id = :a', a=dst).scalar()
    assert change(browser, dst, "suspend").status_code == 200

    r = browser.post("/transfers", headers={"Idempotency-Key": uuid.uuid4().hex}, json={
        "from_account_id": src, "to_bank": "두린은행", "to_account_no": to_no, "amount": "10000",
        "step_up_challenge_id": step_up(browser, action="TRANSFER")})
    assert r.status_code == 201 and (r.json()["status"], r.json()["failure_reason"]) == ("FAILED", "ACCOUNT_NOT_ACTIVE")
    assert sql("SELECT balance FROM account_balances WHERE account_id = :a", a=src).scalar() == 50000
