"""Part 5 거래 — 이번에 더한 기능. 새로 가입한 회원이 직접 연 계좌로 시험한다(시드를 바꾸지 않게).

TRX-F01 재확인 경고 · F02 목록 조건 · F04+ACCT-F06 입출금 알림 · F05 자주 쓰는 계좌 · F06 이체확인증
F09·F14 다른 은행 내역 · F10·F11 예약 송금·자동이체(실행 배치) · F12 잔액 채우기 제안 칸 · F13 한도 변경
"""

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import codef, jobs
from app.main import app
from app.rules import KST, now_kst
from tests.conftest import as_user
from tests.test_signup import sql
from tests.test_withdrawal import PW, new_member

PENDING_EXT = ("신한은행", "110999999011")  # 시드 예금주 「임처리」 — PENDING 으로 남는 시험 계좌 (11장)


@pytest.fixture
def browser():
    with TestClient(app) as c:
        yield c


def step_up(browser, action: str) -> str:
    r = browser.post("/auth/step-up", json={"action": action, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()["step_up_challenge_id"]


def open_funded(browser, balance: int = 0) -> tuple[str, str]:
    """(계좌 id, 계좌번호). 잔액은 거래 파트가 넣었다고 보고 SQL 로 채운다."""
    r = browser.post("/accounts", json={"account_type": "CHECKING", "consents": ["required_terms"],
                                        "step_up_challenge_id": step_up(browser, "ACCOUNT_OPEN")},
                     headers={"Idempotency-Key": uuid.uuid4().hex})
    acc = r.json()
    sql("UPDATE account_balances SET balance = :b WHERE account_id = :a", b=balance, a=acc["id"])
    return acc["id"], acc["resAccount"]


def send(browser, src: str, bank: str, no: str, amount: int):
    return browser.post("/transfers", headers={"Idempotency-Key": uuid.uuid4().hex}, json={
        "from_account_id": src, "to_bank": bank, "to_account_no": no, "amount": str(amount),
        "step_up_challenge_id": step_up(browser, "TRANSFER")})


def verify(browser, src: str, bank: str, no: str, amount: int | None = None):
    params = {"bank": bank, "account_no": no, "from_account_id": src, **({"amount": amount} if amount else {})}
    return browser.get("/transfer-targets/verify", params=params)


def code(r) -> str:
    return r.json()["error"]["code"]


# --- TRX-F01 재확인 경고 (4·9장) -----------------------------------------------------------------
def test_recheck_warnings(browser):
    new_member(browser)
    src, _ = open_funded(browser, 5_000_000)
    _, dst_no = open_funded(browser)
    assert verify(browser, src, "두린은행", dst_no, 1_000_000).json()["warnings"] == ["FIRST_LARGE"]  # 처음 + 100만 이상
    assert verify(browser, src, "두린은행", dst_no, 999_999).json()["warnings"] == []
    assert send(browser, src, "두린은행", dst_no, 10_000).json()["status"] == "SUCCESS"
    w = verify(browser, src, "두린은행", dst_no, 10_000).json()["warnings"]
    assert w == ["RECENT_SAME"]  # 10분 안 같은 분·같은 금액
    assert verify(browser, src, "두린은행", dst_no, 100_000).json()["warnings"] == ["LARGE_VS_USUAL"]  # 평균 1만의 10배

    assert send(browser, src, *PENDING_EXT, 7_000).json()["status"] == "PENDING"
    r = verify(browser, src, *PENDING_EXT).json()  # 금액 없이도 처리중 건은 알려 준다
    assert r["warnings"] == ["PENDING_SAME"] and r["pending_transfer"]["amount"] == "7000"

    r = verify(browser, src, "두린은행", sql('SELECT "resAccount" FROM accounts WHERE id = :a', a=src).scalar())
    assert r.status_code == 400 and code(r) == "SAME_ACCOUNT"


# --- TRX-F02 목록 조건 · F06 이체확인증 · F04 알림 ---------------------------------------------------
def test_transfer_list_filters_receipt_and_notifications(browser):
    uid = new_member(browser)
    src, _ = open_funded(browser, 100_000)
    other, dst_no = open_funded(browser)
    ok = send(browser, src, "두린은행", dst_no, 30_000).json()
    failed = send(browser, src, "두린은행", dst_no, 900_000).json()  # 잔액 부족
    assert failed["status"] == "FAILED"

    assert {t["id"] for t in browser.get("/transfers", params={"account_id": src}).json()} == {failed["id"], ok["id"]}
    assert browser.get("/transfers", params={"account_id": other}).json() == []
    today = now_kst().date()
    assert len(browser.get("/transfers", params={"start_date": str(today), "end_date": str(today)}).json()) == 2
    assert browser.get("/transfers", params={"start_date": str(today + timedelta(days=1))}).json() == []
    assert code(browser.get("/transfers", params={"start_date": "2026-02-02", "end_date": "2026-01-01"})) == "INVALID_PERIOD"

    rc = browser.get(f"/transfers/{ok['id']}/receipt").json()
    assert (rc["amount"], rc["fee"], rc["status"]) == ("30000", "0", "SUCCESS")
    assert rc["to_account"] == dst_no[:3] + "*" * 8 + dst_no[-3:]  # 일부 가림
    assert code(browser.get(f"/transfers/{failed['id']}/receipt")) == "RECEIPT_NOT_AVAILABLE"

    # 성공한 이체 1건 → 출금·입금 알림 각 1건 (같은 회원의 두 계좌), 실패한 이체는 원장이 없어 알림 없음
    titles = sorted(n["title"] for n in browser.get("/notifications").json() if n["type"] == "TRANSACTION")
    assert titles == ["입금 30,000원", "출금 30,000원"]
    assert browser.post("/notifications/read-all").status_code == 204
    assert all(n["read"] for n in browser.get("/notifications").json())
    assert sql("SELECT count(*) FROM notifications WHERE user_id = :u AND read_at IS NULL", u=uid).scalar() == 0


def test_notification_settings_filter_alerts(browser):
    new_member(browser)
    src, _ = open_funded(browser, 100_000)
    dst, dst_no = open_funded(browser)
    assert browser.get(f"/accounts/{dst}").json()["notifications_enabled"] is True  # 행이 있어도 기본은 켬
    r = browser.patch(f"/accounts/{dst}/notification-settings", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    browser.patch(f"/accounts/{src}/notification-settings", json={"minimum_amount": 50_000})
    send(browser, src, "두린은행", dst_no, 10_000)  # 받는 계좌는 끔, 보내는 계좌는 5만 원 미만이라 안 옴
    assert [n for n in browser.get("/notifications").json() if n["type"] == "TRANSACTION"] == []
    assert browser.get(f"/accounts/{dst}").json()["notifications_enabled"] is False


# --- TRX-F05 자주 쓰는 계좌 ------------------------------------------------------------------------
def test_favorite_accounts_crud(browser):
    new_member(browser)
    _, a_no = open_funded(browser)
    _, b_no = open_funded(browser)
    first = browser.post("/favorite-accounts", json={"bank": "두린은행", "account_no": a_no})
    assert first.status_code == 201 and first.json()["account_display"].replace("-", "") == a_no
    assert browser.post("/favorite-accounts", json={"bank": "두린은행", "account_no": a_no}).json()["id"] == first.json()["id"]
    second = browser.post("/favorite-accounts", json={"bank": "신한은행", "account_no": "110000000001", "nickname": "가람"}).json()
    assert second["holder_name"] == "김가람" and second["nickname"] == "가람"
    assert code(browser.post("/favorite-accounts", json={"bank": "두린은행", "account_no": "11099999999999"})) == \
        "TRANSFER_TARGET_NOT_FOUND"

    out = browser.patch(f"/favorite-accounts/{second['id']}", json={"sort_order": 0, "nickname": "친구"}).json()
    assert [(f["id"], f["sort_order"], f["nickname"]) for f in out] == [(second["id"], 0, "친구"), (first.json()["id"], 1, None)]
    out = browser.delete(f"/favorite-accounts/{second['id']}").json()
    assert [f["id"] for f in out] == [first.json()["id"]]
    assert browser.delete("/favorite-accounts/fav_001").status_code == 404  # 남의 것
    _ = b_no


# --- TRX-F13 한도 변경 -----------------------------------------------------------------------------
def test_transfer_limit_change(browser):
    new_member(browser)
    acc, _ = open_funded(browser)
    url = f"/accounts/{acc}/transfer-limits"
    r = browser.patch(url, json={"per_transfer_limit": 1_000_000, "daily_limit": 2_000_000})  # 내리기 — 본인 확인 없이
    assert r.status_code == 200 and (r.json()["per_transfer_limit"], r.json()["is_default"]) == ("1000000", False)
    assert code(browser.patch(url, json={"per_transfer_limit": 3_000_000, "daily_limit": 3_000_000})) == "STEP_UP_REQUIRED"
    r = browser.patch(url, json={"per_transfer_limit": 100_000_000, "daily_limit": 500_000_000,
                                 "step_up_challenge_id": step_up(browser, "TRANSFER")})
    assert r.status_code == 200 and r.json()["daily_limit"] == "500000000"
    assert code(browser.patch(url, json={"per_transfer_limit": 10_000, "daily_limit": 500_010_000})) == "LIMIT_TOO_HIGH"
    assert code(browser.patch(url, json={"per_transfer_limit": 50_000, "daily_limit": 40_000})) == "INVALID_LIMIT"
    assert code(browser.patch(url, json={"per_transfer_limit": 15_500, "daily_limit": 40_000})) == "INVALID_LIMIT"  # 1만 원 단위


# --- TRX-F10·F11 예약 송금·자동이체 ----------------------------------------------------------------
def at(minutes: int) -> str:
    t = now_kst() + timedelta(minutes=minutes)
    t = t.replace(minute=t.minute - t.minute % 10, second=0, microsecond=0) + timedelta(minutes=10)  # 10분 단위로 올림
    return t.replace(tzinfo=KST).isoformat()


def schedule(browser, src, no, amount, **extra):
    return browser.post("/scheduled-transfers", json={
        "from_account_id": src, "to_bank": "두린은행", "to_account_no": no, "amount": str(amount),
        "step_up_challenge_id": step_up(browser, "SCHEDULED_TRANSFER"), **extra})


def make_due(sid: str) -> None:
    sql("UPDATE scheduled_transfers SET next_run_at = now() - interval '1 minute', "
        "execute_at = CASE WHEN type = 'ONCE' THEN now() - interval '1 minute' END WHERE id = :s", s=sid)


def run_one(sid: str, now: datetime | None = None) -> str | None:
    """배치가 이 예약 한 건을 실행한다. 배치 전체(run_scheduled_transfers)를 돌리면 시드의 「곧 실행」 예약(sch_002)까지
    실행돼 뒤의 탈퇴 테스트가 깨질 수 있어서 한 건씩."""
    from app.common.db import SessionLocal

    with SessionLocal() as db:
        type_ = db.get(jobs.ScheduledTransfer, sid).type
        return jobs._run_one_scheduled(db, sid, type_, now or now_kst())


def test_scheduled_once_register_validate_change_run(browser):
    uid = new_member(browser)
    src, _ = open_funded(browser, 50_000)
    dst, dst_no = open_funded(browser)
    bad = schedule(browser, src, dst_no, 10_000, type="ONCE", execute_at=(now_kst() + timedelta(minutes=3)).isoformat())
    assert bad.status_code == 422 and code(bad) == "INVALID_SCHEDULE"
    r = schedule(browser, src, dst_no, 10_000, type="ONCE", execute_at=at(30), their_display_name="선물")
    assert r.status_code == 201 and r.json()["status"] == "SCHEDULED"
    sid = r.json()["id"]
    r = browser.patch(f"/scheduled-transfers/{sid}", json={"amount": "20000",
                                                          "step_up_challenge_id": step_up(browser, "SCHEDULED_TRANSFER")})
    assert r.json()["amount"] == "20000"

    make_due(sid)
    r = browser.patch(f"/scheduled-transfers/{sid}", json={"amount": "1", "step_up_challenge_id": step_up(browser, "SCHEDULED_TRANSFER")})
    assert code(r) == "SCHEDULE_LOCKED"  # 실행 10분 전부터는 못 바꿈
    tid = run_one(sid)
    assert tid and run_one(sid) is None  # 두 번 돌려도 한 번만 (SCHEDULED → PROCESSING 을 먼저 차지한 쪽만)
    t = browser.get(f"/transfers/{tid}").json()
    assert (t["status"], t["channel"], t["scheduled_transfer_id"], t["amount"]) == ("SUCCESS", "SCHEDULED", sid, "20000")
    assert browser.get(f"/scheduled-transfers/{sid}").json()["status"] == "SUCCESS"
    assert sql("SELECT balance FROM account_balances WHERE account_id = :a", a=dst).scalar() == 20_000
    assert sql("SELECT display_name FROM transactions WHERE transfer_id = :t AND type = 'TRANSFER_IN'", t=tid).scalar() == "선물"
    assert sql("SELECT count(*) FROM notifications WHERE user_id = :u AND type = 'TRANSACTION'", u=uid).scalar() == 2


def test_scheduled_failure_makes_alert(browser):
    uid = new_member(browser)
    src, _ = open_funded(browser, 0)  # 등록은 잔액이 모자라도 된다(8장)
    _, dst_no = open_funded(browser)
    sid = schedule(browser, src, dst_no, 10_000, type="ONCE", execute_at=at(30)).json()["id"]
    make_due(sid)
    tid = run_one(sid)
    assert browser.get(f"/transfers/{tid}").json()["failure_reason"] == "INSUFFICIENT_BALANCE"
    assert browser.get(f"/scheduled-transfers/{sid}").json()["status"] == "FAILED"
    n = sql("SELECT title, body FROM notifications WHERE user_id = :u AND event_id = :t", u=uid, t=tid).one()
    assert n.title == "예약 송금을 보내지 못했어요" and "잔액이 부족해" in n.body


def test_monthly_auto_transfer(browser):
    new_member(browser)
    src, _ = open_funded(browser, 100_000)
    _, dst_no = open_funded(browser)
    assert code(schedule(browser, src, dst_no, 1_000, type="MONTHLY", day_of_month=30)) == "INVALID_SCHEDULE"  # 29~31 → 말일
    ym = now_kst().strftime("%Y%m")
    r = schedule(browser, src, dst_no, 1_000, type="MONTHLY", day_of_month=99, end_ym=ym)
    if r.status_code == 422:  # 이번 달 말일 06:00 이 10분 안으로 지났으면 종료 월 안에 보낼 날이 없다
        pytest.skip("말일 아침이라 이번 달 회차가 없음")
    s = r.json()
    assert (s["status"], s["type"]) == ("ACTIVE", "MONTHLY")
    run = datetime.fromisoformat(s["next_run_at"])
    assert (run.hour, run.minute) == (6, 0)
    tid = run_one(s["id"], run.replace(tzinfo=None))  # 그 실행 시각에 배치가 돈다고 보고
    assert tid and run_one(s["id"], run.replace(tzinfo=None)) is None  # 끝난 자동이체는 다시 안 돈다
    assert browser.get(f"/transfers/{tid}").json()["channel"] == "AUTO"
    after = browser.get(f"/scheduled-transfers/{s['id']}").json()
    assert (after["status"], after["next_run_at"]) == ("SUCCESS", None)  # 종료 월까지 다 보냄


# --- TRX-F12 잔액 채우기 제안 칸 -----------------------------------------------------------------------
def test_card_bills_carry_shortfall(client):
    for b in client.get("/card-bills", headers=as_user("user_001")).json():
        assert b["low_balance"] == (int(b["shortfall"]) > 0)
        assert b["account_id"] is None or b["account_id"].startswith("acc_")


# --- TRX-F09·F14 다른 은행 내역 ---------------------------------------------------------------------
def test_external_transfers_dummy_only_for_linked_user(client):
    q = {"organization": "0020", "withdrawAccountNo": "1002440000000", "startDate": "20250101", "endDate": "20250102"}
    r = client.get("/external-transfers", headers=as_user("user_001"), params=q).json()
    assert len(r["items"]) == 30
    assert {i["status"] for i in r["items"]} == {"SUCCESS", "FAILED", "PENDING"}
    assert r["items"][0]["requested_at"] >= r["items"][-1]["requested_at"]  # 최신순
    assert client.get("/external-transfers", headers=as_user("user_002"), params=q).status_code == 404


def test_external_deposit_calls_codef(client, monkeypatch):
    q = {"organization": "0004", "startDate": "20190101", "endDate": "20191231"}
    url = "/external-deposit-accounts/54780300000000/transactions"
    monkeypatch.setattr(codef, "request", lambda path, body: {"result": {"code": "CF-00000"},
                                                             "data": {"resAccountName": "적금", "resTrHistoryList": []}})
    assert client.get(url, headers=as_user("user_001"), params=q).json()["resAccountName"] == "적금"

    def down(*_):
        raise ConnectionError("샌드박스 꺼짐")
    monkeypatch.setattr(codef, "request", down)
    assert code(client.get(url, headers=as_user("user_001"), params=q)) == "EXTERNAL_UNAVAILABLE"
    assert client.get(url, headers=as_user("user_003"), params=q).status_code == 404
