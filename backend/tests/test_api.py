from tests.conftest import as_user

U1 = as_user("user_001")
U2 = as_user("user_002")


# --- 인증 -----------------------------------------------------------------
def test_no_user_header_is_401(client):
    assert client.get("/me/accounts").status_code == 401


def test_unknown_user_is_401(client):
    assert client.get("/me/accounts", headers=as_user("user_999")).status_code == 401


# --- FK 목록 + 1:1 JOIN ------------------------------------------------------
def test_my_accounts_only_mine_with_balance(client):
    r = client.get("/me/accounts", headers=U1)
    assert r.status_code == 200
    body = r.json()
    assert [a["id"] for a in body] == ["acc_001", "acc_002"]  # 즐겨찾기 먼저
    assert body[0]["balance"] == 1_054_500
    assert body[0]["resAccountDisplay"] == "110-00-000001"


# --- PK 단건 + 소유권 ---------------------------------------------------------
def test_get_account_by_pk(client):
    r = client.get("/accounts/acc_001", headers=U1)
    assert r.status_code == 200
    assert r.json()["resAccount"] == "11000000001"
    assert r.json()["currency"] == "KRW"


def test_other_users_account_is_404(client):
    # acc_003 은 user_002 것. 있는 키라도 남의 것이면 없는 것과 똑같이 404
    assert client.get("/accounts/acc_003", headers=U1).status_code == 404


def test_missing_account_is_404(client):
    assert client.get("/accounts/acc_999", headers=U1).status_code == 404


# --- 1:1 (PK=FK) ------------------------------------------------------------
def test_balance_from_view(client):
    r = client.get("/accounts/acc_001/balance", headers=U1)
    assert r.status_code == 200
    assert r.json() == {
        "account_id": "acc_001",
        "resAccountCurrency": "KRW",
        "resAccountBalance": 1_054_500,
        "balance_as_of": "20261025090000",
    }


def test_other_users_balance_is_404(client):
    assert client.get("/accounts/acc_003/balance", headers=U1).status_code == 404


def test_transfer_limit(client):
    r = client.get("/accounts/acc_003/transfer-limit", headers=U2)
    assert r.status_code == 200
    assert r.json()["per_transfer_limit"] == 500_000
    assert r.json()["updated_at"].endswith("+09:00")


# --- FK 목록 + 커서 페이징 ------------------------------------------------------
def test_transactions_cursor_paging(client):
    url = "/accounts/acc_001/transactions"
    seen, cursor = [], None
    for _ in range(5):
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get(url, headers=U1, params=params).json()
        seen.append([t["id"] for t in page["items"]])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [["tx_0006", "tx_0005"], ["tx_0004", "tx_0002"], ["tx_0001"]]


def test_transactions_time_has_kst_offset(client):
    item = client.get("/accounts/acc_001/transactions", headers=U1).json()["items"][0]
    assert item["created_at"] == "2026-10-25T09:00:00+09:00"


def test_other_users_transactions_is_404(client):
    assert client.get("/accounts/acc_003/transactions", headers=U1).status_code == 404


def test_bad_cursor_is_404(client):
    # 다른 계좌의 거래 id 를 커서로 넣어도 안 된다
    r = client.get("/accounts/acc_001/transactions", headers=U1, params={"cursor": "tx_0003"})
    assert r.status_code == 404


# --- PK 단건, 자식 → 부모 소유권 ----------------------------------------------------
def test_transaction_owned_through_account(client):
    assert client.get("/transactions/tx_0003", headers=U2).status_code == 200
    assert client.get("/transactions/tx_0003", headers=U1).status_code == 404


# --- 이체 ------------------------------------------------------------------
def test_my_transfers(client):
    ids = [t["id"] for t in client.get("/me/transfers", headers=U1).json()]
    assert ids == ["trf_0005", "trf_0004", "trf_0003", "trf_0002", "trf_0001"]
    assert client.get("/me/transfers", headers=U2).json() == []


def test_transfer_by_pk(client):
    r = client.get("/transfers/trf_0004", headers=U1)
    assert r.status_code == 200
    assert r.json()["scheduled_transfer_id"] == "sch_001"
    assert client.get("/transfers/trf_0004", headers=U2).status_code == 404


def test_scheduled_transfers(client):
    ids = [s["id"] for s in client.get("/me/scheduled-transfers", headers=U1).json()]
    assert ids == ["sch_002", "sch_001"]
    assert client.get("/scheduled-transfers/sch_001", headers=U2).status_code == 404


# --- 자주 쓰는 계좌 ------------------------------------------------------------
def test_favorite_accounts_sorted(client):
    body = client.get("/me/favorite-accounts", headers=U1).json()
    assert [f["id"] for f in body] == ["fav_001", "fav_002"]


# --- UK 조회 ---------------------------------------------------------------
def test_external_lookup_by_unique_key(client):
    r = client.get(
        "/external-accounts/lookup",
        headers=U1,
        params={"bank": "국민은행", "account_no": "12345678901234"},
    )
    assert r.status_code == 200
    assert r.json() == {"bank": "국민은행", "account_no": "12345678901234", "holder_name": "홍길동"}


def test_external_lookup_not_found(client):
    r = client.get(
        "/external-accounts/lookup",
        headers=U1,
        params={"bank": "국민은행", "account_no": "99999999"},
    )
    assert r.status_code == 404


def test_external_lookup_rejects_non_digits(client):
    r = client.get(
        "/external-accounts/lookup", headers=U1, params={"bank": "국민은행", "account_no": "12-34"}
    )
    assert r.status_code == 422
