"""API 테스트. 기대값은 data/dummy 와 scripts/seed_scenarios.py 의 값이다.

user_001 김민준: acc_001(ACTIVE·즐겨찾기·1,250,000원·거래 9) · acc_002(ACTIVE) · acc_004(SUSPENDED) · acc_006(CLOSED)
user_002 이서연: acc_007(ACTIVE·한도 30만/50만)   user_024 RESTRICTED · user_028 PENDING_VERIFICATION · user_029 WITHDRAWN
"""

from tests.conftest import as_user

U1 = as_user("user_001")
U2 = as_user("user_002")


def error_code(r) -> str:
    body = r.json()
    assert body["success"] is False
    return body["error"]["code"]


# --- 인증·회원 상태 (Part 1 7.3) ----------------------------------------------
def test_no_user_header_is_401(client):
    r = client.get("/accounts")
    assert r.status_code == 401
    assert error_code(r) == "UNAUTHORIZED"


def test_unknown_and_withdrawn_users_are_401(client):
    assert client.get("/accounts", headers=as_user("user_999")).status_code == 401
    assert client.get("/accounts", headers=as_user("user_029")).status_code == 401  # WITHDRAWN


def test_pending_verification_user_is_403(client):
    r = client.get("/accounts", headers=as_user("user_028"))
    assert r.status_code == 403
    assert error_code(r) == "SIGNUP_INCOMPLETE"


def test_restricted_user_can_still_read(client):
    r = client.get("/accounts", headers=as_user("user_024"))
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == ["acc_030"]


# --- 계좌 목록·상세·잔액 (Part 2 ACCT-F02·F03) ------------------------------------
def test_account_list_hides_closed_and_puts_favorite_first(client):
    r = client.get("/accounts", headers=U1)
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == ["acc_001", "acc_002", "acc_004"]  # acc_006(CLOSED) 빠짐


def test_account_list_status_filter_shows_closed_history(client):
    r = client.get("/accounts", headers=U1, params={"status": "CLOSED"})
    assert [a["id"] for a in r.json()] == ["acc_006"]
    assert r.json()[0]["closed_at"] is not None


def test_account_list_type_filter(client):
    r = client.get("/accounts", headers=U1, params={"type": "SAVINGS"})
    assert [a["id"] for a in r.json()] == ["acc_002"]


def test_account_list_rejects_unknown_status(client):
    r = client.get("/accounts", headers=U1, params={"status": "DELETED"})
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"


def test_account_detail_follows_c5_formats(client):
    a = client.get("/accounts/acc_001", headers=U1).json()
    assert a["resAccount"] == "11000000000001"
    assert a["resAccountBalance"] == "1250000"  # 금액은 문자열
    assert a["resAccountCurrency"] == "KRW"
    assert a["resAccountNickName"] == "생활비"
    assert a["closed_at"] is None  # 우리가 만든 빈 칸은 null


def test_empty_codef_field_is_empty_string(client):
    a = client.get("/accounts/acc_004", headers=U1).json()
    assert a["resAccountNickName"] == ""  # CODEF res… 빈 칸은 ""


def test_other_users_account_is_404(client):
    # acc_007 은 user_002 것. 있는 키라도 남의 것이면 없는 것과 똑같이 404
    r = client.get("/accounts/acc_007", headers=U1)
    assert r.status_code == 404
    assert error_code(r) == "ACCOUNT_NOT_FOUND"
    assert client.get("/accounts/acc_999", headers=U1).status_code == 404


def test_balance_from_view(client):
    r = client.get("/accounts/acc_001/balance", headers=U1)
    assert r.status_code == 200
    assert r.json() == {
        "account_id": "acc_001",
        "resAccountCurrency": "KRW",
        "resAccountBalance": "1250000",
        "balance_as_of": "20261103090000",
    }
    assert client.get("/accounts/acc_007/balance", headers=U1).status_code == 404


# --- 거래내역 (Part 5 10장) ---------------------------------------------------------
def _all_pages(client, params):
    seen, cursor = [], None
    for _ in range(20):
        page = client.get(
            "/accounts/acc_001/transactions", headers=U1, params=params | ({"cursor": cursor} if cursor else {})
        ).json()
        seen.append([t["id"] for t in page["items"]])
        cursor = page["next_cursor"]
        if cursor is None:
            return seen
    raise AssertionError("페이지가 끝나지 않음")


def test_transactions_cursor_paging_newest_first(client):
    # 10/14 06:00 같은 시각 카드대금 2건은 나중 거래(tx_0004)가 먼저
    assert _all_pages(client, {"limit": 4}) == [
        ["tx_0009", "tx_0008", "tx_0007", "tx_0006"],
        ["tx_0005", "tx_0004", "tx_0003", "tx_0002"],
        ["tx_0001"],
    ]


def test_transactions_direction_and_period_filters(client):
    incoming = _all_pages(client, {"direction": "IN"})
    assert incoming == [["tx_0006"]]  # 급여 입금 1건
    october_mid = _all_pages(client, {"start_date": "2026-10-09", "end_date": "2026-10-14"})
    assert october_mid == [["tx_0004", "tx_0003", "tx_0002"]]  # 종료일 당일 포함


def test_transactions_bad_period_and_cursor(client):
    r = client.get("/accounts/acc_001/transactions", headers=U1,
                   params={"start_date": "2026-10-31", "end_date": "2026-10-01"})
    assert error_code(r) == "INVALID_PERIOD"
    r = client.get("/accounts/acc_001/transactions", headers=U1, params={"cursor": "tx_9999"})
    assert error_code(r) == "INVALID_CURSOR"


def test_transaction_detail_has_sign_and_string_money(client):
    t = client.get("/transactions/tx_0006", headers=U1).json()
    assert t["type"] == "TRANSFER_IN"
    assert t["direction"] == "IN"
    assert t["amount"] == "1800000"
    assert t["balance_after"] == "2250000"
    assert t["created_at"] == "2026-10-25T09:00:00+09:00"
    assert client.get("/transactions/tx_0006", headers=U2).status_code == 404  # 남의 거래


# --- 이체·예약·한도 (Part 5 16장) ---------------------------------------------------
def test_my_transfers_newest_first_and_status_filter(client):
    r = client.get("/transfers", headers=U1)
    assert [t["id"] for t in r.json()] == ["trf_0001", "trf_0003"]
    assert r.json()[0]["amount"] == "3500000"  # 0 을 하나 더 친 실패 사례(Part 5 4장)
    assert client.get("/transfers", headers=U1, params={"status": "SUCCESS"}).json() == []


def test_transfer_detail_ownership(client):
    assert client.get("/transfers/trf_0001", headers=U1).status_code == 200
    r = client.get("/transfers/trf_0002", headers=U1)  # user_002 의 이체
    assert r.status_code == 404
    assert error_code(r) == "TRANSFER_NOT_FOUND"


def test_scheduled_transfers(client):
    items = client.get("/scheduled-transfers", headers=U1).json()
    assert len(items) == 7
    assert {s["type"] for s in items} == {"ONCE", "MONTHLY"}
    assert all("updated_at" in s and "my_display_name" in s for s in items)
    assert client.get("/scheduled-transfers/sch_001", headers=U2).status_code == 404


def test_transfer_limits_with_remaining_today(client):
    r = client.get("/accounts/acc_007/transfer-limits", headers=U2).json()
    assert r["per_transfer_limit"] == "300000"
    assert r["daily_limit"] == "500000"
    assert r["is_default"] is False
    assert int(r["used_today"]) + int(r["remaining_today"]) == 500000


def test_transfer_limits_default_when_no_row(client):
    r = client.get("/accounts/acc_006/transfer-limits", headers=U1).json()  # 해지 계좌는 한도 행이 없음
    assert r["is_default"] is True
    assert (r["per_transfer_limit"], r["daily_limit"]) == ("5000000", "10000000")
    assert r["updated_at"] is None


# --- 이체 대상 확인 (Part 5 11장) ---------------------------------------------------
def test_verify_our_bank_account(client):
    r = client.get("/transfer-targets/verify", headers=U1,
                   params={"bank": "두린은행", "account_no": "11000000000007"})
    assert r.json() == {"bank": "두린은행", "account_no": "11000000000007", "holder_name": "이서연",
                        "account_status": "ACTIVE", "is_mine": False}
    mine = client.get("/transfer-targets/verify", headers=U1,
                      params={"bank": "두린은행", "account_no": "11000000000002"}).json()
    assert mine["is_mine"] is True


def test_verify_external_account(client):
    r = client.get("/transfer-targets/verify", headers=U1, params={"bank": "신한은행", "account_no": "110000000001"})
    assert r.json()["holder_name"] == "김가람"


def test_verify_checks_digits_by_chosen_bank(client):
    # 신한은행 12자리 번호를 두린은행(14자리)으로 고르면 자릿수 오류 — 앞자리(110)로 은행을 가리지 않음
    r = client.get("/transfer-targets/verify", headers=U1, params={"bank": "두린은행", "account_no": "110000000001"})
    assert error_code(r) == "INVALID_ACCOUNT_NUMBER"
    r = client.get("/transfer-targets/verify", headers=U1, params={"bank": "없는은행", "account_no": "1234"})
    assert error_code(r) == "UNSUPPORTED_BANK"
    r = client.get("/transfer-targets/verify", headers=U1, params={"bank": "두린은행", "account_no": "11099999999999"})
    assert r.status_code == 404
    assert error_code(r) == "TRANSFER_TARGET_NOT_FOUND"


# --- 자주 쓰는 계좌 -----------------------------------------------------------------
def test_favorite_accounts_in_sort_order(client):
    r = client.get("/favorite-accounts", headers=U1)
    assert [f["id"] for f in r.json()] == ["fav_001", "fav_002", "fav_003"]


def test_unknown_route_uses_error_format(client):
    r = client.get("/nope", headers=U1)
    assert r.status_code == 404
    assert error_code(r) == "NOT_FOUND"
