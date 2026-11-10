"""탈퇴 전 정리 기능 — 계좌 정지 해제(ACCT-F05) · 예금·적금 중도 해지(PROD-F10) · 이체 실행/타행(Part 5) ·
예약 취소·자동이체 해지(Part 5 8장) · 카드 해지(CARD-F09)·지금 결제하기(CARD-F07) · 예약 작업(app/jobs.py).

시드 회원의 상태를 바꾸므로 파일 이름을 test_withdrawal.py 뒤에 오게 했다(그 파일은 user_001 이 「막힌다」를 본다).
마지막 시험들은 시드 회원(user_001 · user_005 · user_024)을 처음부터 끝까지 정리해 실제로 탈퇴시킨다 — 이 작업의 목표.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import pay_due_card_bills, settle_pending_transfers
from app.main import app
from app.rules import WITHDRAWAL_DATA_REVIEW_VERSION
from tests.conftest import seed_password
from tests.test_signup import sql

PW = seed_password()
_key = iter(range(1, 10_000))


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def login(browser, user_id: str):
    username = sql("SELECT username FROM users WHERE id = :u", u=user_id).scalar()
    assert browser.post("/auth/login", json={"username": username, "password": PW}).status_code == 200


def ch(browser, action: str) -> str:
    r = browser.post("/auth/step-up", json={"action": action, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def balance(acc: str) -> int:
    return sql("SELECT balance FROM account_balances WHERE account_id = :a", a=acc).scalar()


def send(browser, src: str, bank: str, no: str, amount: int, key: str | None = None):
    return browser.post("/transfers", headers={"Idempotency-Key": key or f"test-key-{next(_key):05d}"}, json={
        "from_account_id": src, "to_bank": bank, "to_account_no": no, "amount": str(amount),
        "step_up_challenge_id": ch(browser, "TRANSFER")})


def own_external(user_id: str) -> tuple[str, str]:
    return sql("SELECT bank, account_no FROM external_accounts WHERE id = :i", i=f"ext_{user_id}").one()


def ext_by_holder(holder: str) -> tuple[str, str]:
    return sql("SELECT bank, account_no FROM external_accounts WHERE holder_name = :h", h=holder).one()


def empty_all(browser, user_id: str):
    """해지 안 된 계좌의 남은 돈을 본인 명의 타행 계좌로 모두 보낸다(탈퇴 ①)."""
    bank, no = own_external(user_id)
    for acc, bal in sql("""SELECT a.id, b.balance FROM accounts a JOIN account_balances b ON b.account_id = a.id
                           WHERE a.user_id = :u AND a.lifecycle_status = 'ACTIVE' AND b.balance > 0""", u=user_id).all():
        r = send(browser, acc, bank, no, bal)
        assert r.status_code == 201 and r.json()["status"] == "SUCCESS", r.text


def finish_and_withdraw(browser):
    st = browser.get("/users/me/withdrawal-checks").json()
    assert st["money_ok"] and not st["linked_items"], st
    browser.post("/users/me/withdrawal-checks/data-review", json={"version": WITHDRAWAL_DATA_REVIEW_VERSION})
    assert browser.post("/users/me/withdrawal-checks/linked-services").status_code == 200
    r = browser.post("/users/me/withdraw", json={"step_up_challenge_id": ch(browser, "WITHDRAWAL")})
    assert r.status_code == 200, r.text
    return r.json()


# --- 이체 실행 ---------------------------------------------------------------------------------
def test_transfer_inside_our_bank_writes_both_ledgers_and_is_idempotent(browser):
    login(browser, "user_001")
    to_no = sql("""SELECT "resAccount" FROM accounts WHERE id = 'acc_007'""").scalar()
    a1, a7 = balance("acc_001"), balance("acc_007")
    r = send(browser, "acc_001", "두린은행", to_no, 1000, key="same-key-0001")
    assert r.status_code == 201 and r.json()["status"] == "SUCCESS" and r.json()["balance_after"] == str(a1 - 1000)
    again = send(browser, "acc_001", "두린은행", to_no, 1000, key="same-key-0001")  # 버튼 두 번
    assert again.json()["id"] == r.json()["id"]
    assert (balance("acc_001"), balance("acc_007")) == (a1 - 1000, a7 + 1000)
    rows = sql("SELECT account_id, type, balance_after FROM transactions WHERE transfer_id = :t ORDER BY type",
               t=r.json()["id"]).all()
    assert rows == [("acc_007", "TRANSFER_IN", a7 + 1000), ("acc_001", "TRANSFER_OUT", a1 - 1000)]


@pytest.mark.parametrize("acc, amount, reason", [
    ("acc_001", 99_000_000, "LIMIT_EXCEEDED"),       # 1회 500만 원 넘음
    ("acc_002", 4_000_000, "INSUFFICIENT_BALANCE"),  # 잔액 874,890원
])
def test_business_failures_are_recorded_as_failed_without_ledger(browser, acc, amount, reason):
    login(browser, "user_001")
    before = balance(acc)
    bank, no = ext_by_holder("김가람")
    r = send(browser, acc, bank, no, amount)
    assert r.status_code == 201 and (r.json()["status"], r.json()["failure_reason"]) == ("FAILED", reason)
    assert r.json()["message"] and balance(acc) == before
    assert sql("SELECT count(*) FROM transactions WHERE transfer_id = :t", t=r.json()["id"]).scalar() == 0


def test_transfer_input_errors(browser):
    login(browser, "user_001")
    no = sql("""SELECT "resAccount" FROM accounts WHERE id = 'acc_001'""").scalar()
    assert send(browser, "acc_001", "두린은행", no, 100).json()["error"]["code"] == "SAME_ACCOUNT"
    assert send(browser, "acc_001", "두린은행", "11099999999999", 100).json()["error"]["code"] == "TRANSFER_TARGET_NOT_FOUND"
    assert send(browser, "acc_001", "신한은행", "123", 100).json()["error"]["code"] == "INVALID_ACCOUNT_NUMBER"
    assert send(browser, "acc_002", "두린은행", no, 0).json()["error"]["code"] == "INVALID_AMOUNT"


def test_external_pending_then_settled_and_failing_bank(browser):
    login(browser, "user_001")
    bank, no = ext_by_holder("임처리")
    before = balance("acc_002")
    r = send(browser, "acc_002", bank, no, 5000)
    assert r.json()["status"] == "PENDING" and balance("acc_002") == before  # 원장 없음
    with Session(engine) as db:
        assert r.json()["id"] not in settle_pending_transfers(db, datetime.now())  # 아직 10분 안 됨
        assert r.json()["id"] in settle_pending_transfers(db, datetime.now() + timedelta(minutes=11))
        db.commit()
    assert sql("SELECT status FROM transfers WHERE id = :t", t=r.json()["id"]).scalar() == "SUCCESS"
    assert balance("acc_002") == before - 5000

    bank, no = ext_by_holder("오실패")
    r = send(browser, "acc_002", bank, no, 5000)
    assert (r.json()["status"], r.json()["failure_reason"]) == ("FAILED", "INVALID_ACCOUNT")


def test_recent_targets_lists_our_bank_successes(browser):
    login(browser, "user_001")
    no = sql("""SELECT "resAccount" FROM accounts WHERE id = 'acc_007'""").scalar()
    assert any(t["account_no"] == no for t in browser.get("/transfer-targets/recent").json())


def test_restricted_member_can_only_send_to_own_account(browser):
    login(browser, "user_024")
    bank, no = ext_by_holder("김가람")
    assert send(browser, "acc_030", bank, no, 1000).json()["error"]["code"] == "RESTRICTED_TRANSFER"
    bank, no = own_external("user_024")
    assert browser.get("/transfer-targets/verify", params={"bank": bank, "account_no": no}).json()["is_mine"] is True
    assert send(browser, "acc_030", bank, no, 1000).json()["status"] == "SUCCESS"


# --- 예약 송금 취소 · 자동이체 해지 -------------------------------------------------------------------
def test_cancel_scheduled_needs_step_up_and_respects_10_minute_lock(browser):
    login(browser, "user_001")
    r = browser.request("DELETE", "/scheduled-transfers/sch_006", json={"step_up_challenge_id": ch(browser, "TRANSFER")})
    assert r.json()["error"]["code"] == "STEP_UP_REQUIRED"  # 다른 작업의 번호
    r = browser.request("DELETE", "/scheduled-transfers/sch_006", json={"step_up_challenge_id": ch(browser, "SCHEDULED_TRANSFER")})
    assert r.status_code == 200 and r.json()["status"] == "CANCELED"
    r = browser.request("DELETE", "/scheduled-transfers/sch_004", json={"step_up_challenge_id": ch(browser, "SCHEDULED_TRANSFER")})
    assert r.json()["error"]["code"] == "SCHEDULED_TRANSFER_NOT_CANCELABLE"  # 이미 취소됨
    sql("UPDATE scheduled_transfers SET execute_at = now() + interval '5 minutes' WHERE id = 'sch_002'")
    r = browser.request("DELETE", "/scheduled-transfers/sch_002", json={"step_up_challenge_id": ch(browser, "SCHEDULED_TRANSFER")})
    assert r.json()["error"]["code"] == "SCHEDULE_LOCKED"


# --- 카드 --------------------------------------------------------------------------------------
def test_credit_card_must_be_paid_before_termination(browser):
    login(browser, "user_003")
    cards = {c["id"]: c for c in browser.get("/cards").json()}
    assert cards["card_006"]["unpaid_amount"] == "32600" and cards["card_006"]["card_type"] == "CREDIT"
    check = browser.get("/cards/card_006/termination-check").json()
    assert (check["can_terminate"], check["blockers"]) == (False, ["UNPAID_BILL"])
    r = browser.post("/cards/card_006/terminate", json={"reason_code": "NOT_USING", "step_up_challenge_id": ch(browser, "CARD_TERMINATION")})
    assert r.json()["error"]["code"] == "CARD_UNPAID_BILL"

    before = balance("acc_009")
    r = browser.post("/cards/card_006/payments", json={"step_up_challenge_id": ch(browser, "CARD_MANAGEMENT")})
    assert r.status_code == 200 and r.json()["unpaid_amount"] == "0"
    assert balance("acc_009") == before - 32600
    assert sql("SELECT count(*) FROM transactions WHERE account_id = 'acc_009' AND type = 'CARD_PAYMENT' AND amount = 32600").scalar() == 1
    r = browser.post("/cards/card_006/terminate", json={"reason_code": "NOT_USING", "step_up_challenge_id": ch(browser, "CARD_TERMINATION")})
    assert r.status_code == 200
    assert sql("SELECT status FROM user_cards WHERE id = 'card_006'").scalar() == "TERMINATED"
    assert "card_006" not in {c["id"] for c in browser.get("/cards").json()}  # 목록에서 빠지고
    assert browser.get("/cards/card_006").json()["status"] == "TERMINATED"  # 상세는 기록으로 남음


def test_terminated_card_with_leftover_usage_blocks_withdrawal_until_paid(browser):
    """Q5: 해지한 카드의 이번 기간 사용액도 낼 때까지 탈퇴 ③이 막힌다. 잔액이 모자라면 낼 수 없어 탈퇴도 못 한다."""
    login(browser, "user_003")  # 위 시험에서 card_006 을 해지함
    sql("""INSERT INTO card_transactions (id, user_card_id, merchant_id, approval_no, transacted_at, amount)
           VALUES ('ctx_left1', 'card_006', 'mer_001', 'T0000001', now(), 15000)""")
    linked = browser.get("/users/me/withdrawal-checks").json()["linked_items"]
    assert any("15,000원" in i["detail"] and i["href"] == "#/cards/card_006" for i in linked)

    keep = balance("acc_009")
    sql("UPDATE account_balances SET balance = 100 WHERE account_id = 'acc_009'")
    r = browser.post("/cards/card_006/payments", json={"step_up_challenge_id": ch(browser, "CARD_MANAGEMENT")})
    assert r.json()["error"]["code"] == "INSUFFICIENT_BALANCE" and balance("acc_009") == 100
    sql("UPDATE account_balances SET balance = :b WHERE account_id = 'acc_009'", b=keep)

    r = browser.post("/cards/card_006/payments", json={"step_up_challenge_id": ch(browser, "CARD_MANAGEMENT")})
    assert r.status_code == 200 and balance("acc_009") == keep - 15000
    assert sql("SELECT status, total_amount FROM card_bills WHERE user_card_id = 'card_006' ORDER BY billing_ym DESC LIMIT 1").one() == ("PAID", 15000)
    linked = browser.get("/users/me/withdrawal-checks").json()["linked_items"]
    assert not any(i["href"] == "#/cards/card_006" for i in linked)


def test_due_bills_job_pays_or_marks_overdue():
    sql("UPDATE card_bills SET payment_date = CURRENT_DATE WHERE user_card_id IN ('card_008', 'card_010') AND status = 'CONFIRMED'")
    poor = sql("SELECT linked_account_id FROM user_cards WHERE id = 'card_010'").scalar()
    sql("UPDATE account_balances SET balance = 0 WHERE account_id = :a", a=poor)
    with Session(engine) as db:
        paid, overdue = pay_due_card_bills(db, datetime.now())
        db.commit()
    assert sql("SELECT status FROM card_bills WHERE user_card_id = 'card_008' AND billing_ym = '202611'").scalar() == "PAID"
    assert sql("SELECT status FROM card_bills WHERE user_card_id = 'card_010' AND billing_ym = '202611'").scalar() == "OVERDUE"
    assert sql("SELECT count(*) FROM notifications WHERE user_card_id = 'card_010' AND type = 'OVERDUE'").scalar() == 1


# --- 계좌 정지 해제 · 중도 해지 → 탈퇴 (user_005: 정지 계좌에 돈 + 적금) ---------------------------------------
def test_user_005_suspended_account_and_savings_to_withdrawal(browser):
    login(browser, "user_005")
    r = browser.post("/subscriptions/sub_005/terminate", json={"step_up_challenge_id": ch(browser, "SUBSCRIPTION")})
    assert r.json()["error"]["code"] == "ACCOUNT_NOT_ACTIVE"  # 출금 계좌 정지 → 정지 해제 먼저 (기획서 Part 3 시험 표)
    assert sql("SELECT status FROM subscriptions WHERE id = 'sub_005'").scalar() == "ACTIVE"

    r = browser.post("/accounts/acc_011/resume", json={"step_up_challenge_id": ch(browser, "ACCOUNT_STATUS_CHANGE")})
    assert r.status_code == 200 and r.json()["lifecycle_status"] == "ACTIVE"
    assert browser.post("/accounts/acc_011/resume", json={"step_up_challenge_id": ch(browser, "ACCOUNT_STATUS_CHANGE")}).status_code == 409

    before = balance("acc_011")
    r = browser.post("/subscriptions/sub_005/terminate", json={"step_up_challenge_id": ch(browser, "SUBSCRIPTION")})
    assert r.status_code == 200 and r.json()["status"] == "TERMINATED"
    assert balance("acc_011") == before + 2_400_000  # 원금만 (중도 해지 이자 0원)
    assert sql("SELECT type FROM transactions WHERE account_id = 'acc_011' ORDER BY created_at DESC, id DESC LIMIT 1").scalar() == "SUBSCRIPTION_PAYOUT"

    empty_all(browser, "user_005")
    assert finish_and_withdraw(browser)["status"] == "WITHDRAWN"


def test_user_024_restricted_member_withdraws(browser):
    login(browser, "user_024")
    empty_all(browser, "user_024")
    assert finish_and_withdraw(browser)["closed_account_ids"] == ["acc_030"]


def test_user_001_everything_cleaned_up_then_withdraws(browser):
    """잔액 2계좌 · 적금 · 예약 3 · 자동이체 2 · 카드 3장(신용 2장은 확정 청구서) → 전부 정리 → 탈퇴."""
    login(browser, "user_001")
    for card in ("card_002", "card_003"):
        r = browser.post(f"/cards/{card}/payments", json={"step_up_challenge_id": ch(browser, "CARD_MANAGEMENT")})
        assert r.status_code == 200, r.text
    for card in ("card_001", "card_002", "card_003"):
        r = browser.post(f"/cards/{card}/terminate", json={"reason_code": "OTHER", "reason_detail": "탈퇴",
                                                           "step_up_challenge_id": ch(browser, "CARD_TERMINATION")})
        assert r.status_code == 200, r.text
    sql("UPDATE scheduled_transfers SET execute_at = now() - interval '1 hour' WHERE user_id = 'user_001' AND status = 'SCHEDULED'")
    for s in sql("SELECT id FROM scheduled_transfers WHERE user_id = 'user_001' AND status IN ('SCHEDULED','ACTIVE','PAUSED')").scalars():
        r = browser.request("DELETE", f"/scheduled-transfers/{s}", json={"step_up_challenge_id": ch(browser, "SCHEDULED_TRANSFER")})
        assert r.status_code == 200, r.text
    assert browser.post("/subscriptions/sub_001/terminate", json={"step_up_challenge_id": ch(browser, "SUBSCRIPTION")}).status_code == 200
    empty_all(browser, "user_001")

    out = finish_and_withdraw(browser)
    assert out["status"] == "WITHDRAWN" and "acc_004" in out["closed_account_ids"]  # 잔액 0원 정지 계좌도 함께 해지
