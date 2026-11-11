"""카드 목록 조회 — 기획서 Part 4 1-1 (CARD-F01~F04). 먼저 「로그인한 회원의 카드만 보인다」를 고정한다.

로그인은 진짜 쿠키(POST /auth/login)로 한다 — 개발용 X-User-Id 헤더는 쓰지 않는다.
더미 (data/dummy/cards/cards.json → user_cards)
  user_001: card_001 체크 · card_002 신용 · card_003 신용     user_002: card_004 체크
  user_003: card_005 체크 · card_006 신용                     user_005: 카드 없음
  user_028: PENDING_VERIFICATION (가입 마무리 중)
남의 카드는 계좌(test_api.py test_other_users_account_is_404)와 같이 「없는 카드」와 똑같은 404 — 있는지조차 알려 주지 않는다.

혜택(data/dummy/cards/card_benefits.json): card_001 = 한빛체크카드(EVERYDAY CHECK 참고, 구간 30만·60만),
card_002 = 한빛신용카드(카드의정석2 참고, 전월 50만 + 분기 300·600·900만), card_003 = 할인카드(D4 참고, 30만).
더미의 10월 실적은 모든 카드가 30만 원 미만이라, 구간에 드는 경우는 시험 안에서 승인을 잠깐 넣었다 지운다.
잔액·알림·승인처럼 시험이 바꾼 값은 끝에 되돌린다 — 뒤 시험 파일(test_withdrawal*)이 더미 그대로를 가정한다.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.db import engine
from app.jobs import notify_card_payments
from app.main import app
from tests.test_auth import login, sql


@pytest.fixture
def browser():
    """쿠키를 따로 가진 새 브라우저(테스트마다 새로)."""
    with TestClient(app) as c:
        yield c


def logged_in(browser, user_id: str):
    assert login(browser, user_id).status_code == 200
    return browser


def owner_of(card_id: str) -> str:
    return sql("SELECT user_id FROM user_cards WHERE id = :c", c=card_id).scalar()


@contextmanager
def extra_approval(card_id: str, amount: int, at: str, merchant_id: str = "mer_001"):
    """시험 동안만 있는 승인 1건 (끝나면 지운다)"""
    sql("""INSERT INTO card_transactions (id, user_card_id, merchant_id, approval_no, transacted_at, amount)
           VALUES ('ctx_test1', :c, :m, 'T9999999', :at, :amt)""", c=card_id, m=merchant_id, at=at, amt=amount)
    try:
        yield
    finally:
        sql("DELETE FROM card_transactions WHERE id = 'ctx_test1'")


def last_month_spent(card_id: str) -> int:
    return sql("""SELECT COALESCE(SUM(amount - canceled_amount), 0) FROM card_transactions WHERE user_card_id = :c
                  AND transacted_at >= date_trunc('month', now()) - interval '1 month'
                  AND transacted_at < date_trunc('month', now())""", c=card_id).scalar()


@contextmanager
def balance_of_acc_001(amount: int):
    before = sql("SELECT balance FROM account_balances WHERE account_id = 'acc_001'").scalar()
    sql("UPDATE account_balances SET balance = :b WHERE account_id = 'acc_001'", b=amount)
    try:
        yield
    finally:
        sql("UPDATE account_balances SET balance = :b WHERE account_id = 'acc_001'", b=before)


# --- 로그인 확인 ---------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/cards", "/cards/card_001", "/cards/card_001/transactions", "/card-bills"])
def test_cards_need_login(browser, path):
    r = browser.get(path)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"  # 화면(api.ts)은 이것을 UNAUTHENTICATED 로 묶어 손님 화면을 띄운다


def test_dev_header_alone_is_not_login_when_cookie_is_wrong(browser):
    """쿠키가 있으면 쿠키가 우선 — 엉터리 쿠키에 남의 X-User-Id 를 붙여도 들어갈 수 없다."""
    browser.cookies.set("sid", "not-a-real-session")
    assert browser.get("/cards", headers={"X-User-Id": "user_001"}).status_code == 401


def test_signup_incomplete_user_cannot_see_cards(browser):
    logged_in(browser, "user_028")
    r = browser.get("/cards")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SIGNUP_INCOMPLETE"


# --- 내 카드만 -----------------------------------------------------------------------
def test_list_has_exactly_my_cards(browser):
    cards = logged_in(browser, "user_001").get("/cards").json()
    assert [c["id"] for c in cards] == ["card_001", "card_002", "card_003"]
    assert all(owner_of(c["id"]) == "user_001" for c in cards)


def test_list_changes_with_who_is_logged_in(browser):
    assert [c["id"] for c in logged_in(browser, "user_003").get("/cards").json()] == ["card_005", "card_006"]
    browser.post("/auth/logout")
    assert browser.get("/cards").status_code == 401  # 로그아웃하면 바로 못 봄
    assert [c["id"] for c in logged_in(browser, "user_002").get("/cards").json()] == ["card_004"]


def test_user_without_cards_gets_empty_list(browser):
    r = logged_in(browser, "user_005").get("/cards")
    assert r.status_code == 200 and r.json() == []


def test_my_card_detail(browser):
    r = logged_in(browser, "user_001").get("/cards/card_002")
    assert r.status_code == 200
    assert r.json()["id"] == "card_002" and r.json()["card_type"] == "CREDIT"


@pytest.mark.parametrize("path", ["/cards/card_004", "/cards/card_006", "/cards/card_006/termination-check"])
def test_other_users_card_is_same_404_as_missing_card(browser, path):
    logged_in(browser, "user_001")
    assert owner_of(path.split("/")[2]) != "user_001"
    other, missing = browser.get(path), browser.get("/cards/card_999")
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()  # 「남의 것」과 「없는 것」이 응답으로 구별되지 않는다
    assert other.json()["error"]["code"] == "CARD_NOT_FOUND"


# --- 1-1-1 모아보기 ------------------------------------------------------------------------
def test_list_shows_product_summary_and_check_card_spends_this_month(browser):
    logged_in(browser, "user_001")
    cards = {c["id"]: c for c in browser.get("/cards").json()}
    assert cards["card_001"]["product_summary"].startswith("어디서나 0.2% 적립")
    assert cards["card_001"]["period_spent"] == "0"  # 더미는 9·10월뿐 — 이번 달은 아직 안 씀
    with extra_approval("card_001", 12_300, datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
        check = next(c for c in browser.get("/cards").json() if c["id"] == "card_001")
        assert check["period_spent"] == "12300"  # 체크카드: 이번 달 1일~오늘 쓴 돈
        assert check["unpaid_amount"] == "0"  # 낼 돈은 없다
    credit = cards["card_002"]
    assert credit["unpaid_amount"] == "86900" and credit["next_payment_date"].endswith("-14")


# --- 1-1-2 상세: 혜택 ----------------------------------------------------------------------
def test_benefits_show_first_tier_as_locked_when_last_month_is_short(browser):
    d = logged_in(browser, "user_001").get("/cards/card_001").json()
    assert d["performance"] == [{"period": "MONTH", "spent": str(last_month_spent("card_001")), "tier_level": None,
                                 "tier_min_spend": "300000", "next_min_spend": "300000"}]
    base, *extra = d["benefits"]
    assert base["title"] == "모든 가맹점 0.2% 적립" and base["achieved"] is True  # 실적 조건 없는 기본 적립
    assert [b["title"] for b in extra] == ["모든 가맹점 0.5% 적립", "카페 1% 적립", "마트 1% 적립", "교통 1% 적립", "주유 1% 적립"]
    assert all(b["achieved"] is False for b in extra)
    cafe = extra[1]
    assert cafe["conditions"][:3] == ["전월 30만 원 이상 썼을 때", "스타벅스·폴바셋·투썸플레이스·매머드커피에서만", "한 번에 1만 원 이상 결제"]
    assert cafe["monthly_limit"] == "3000"
    assert cafe["limit_group"] == {"name": "추가·특별 적립 통합", "monthly_limit": "10000"}
    assert d["annual_fee"] == "0"


def test_benefits_follow_the_tier_reached_last_month(browser):
    logged_in(browser, "user_001")
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m-15 12:00:00")
    need = 650_000 - last_month_spent("card_001")  # 2구간(60만 원 이상)
    with extra_approval("card_001", need, last_month):
        d = browser.get("/cards/card_001").json()
    assert d["performance"] == [{"period": "MONTH", "spent": "650000", "tier_level": 2,
                                 "tier_min_spend": "600000", "next_min_spend": None}]
    assert all(b["achieved"] for b in d["benefits"])
    cafe = next(b for b in d["benefits"] if b["title"] == "카페 1% 적립")
    assert cafe["monthly_limit"] == "6000" and cafe["limit_group"]["monthly_limit"] == "20000"  # 2구간 한도
    assert cafe["conditions"][0] == "전월 60만 원 이상 썼을 때"


def test_credit_card_benefits_have_quarter_tier_and_fees(browser):
    d = logged_in(browser, "user_001").get("/cards/card_002").json()  # 한빛신용카드
    assert {p["period"] for p in d["performance"]} == {"MONTH", "QUARTER"}
    assert [b["title"] for b in d["benefits"]] == ["모든 가맹점 1.2% 할인", "모든 가맹점 5,000원 할인"]  # 분기는 첫 구간 금액
    assert d["benefits"][1]["conditions"][0] == "지난 분기 300만 원 이상 썼을 때"
    assert d["annual_fee"] == "22000"  # VISA(해외겸용) 연회비
    movie = next(b for b in browser.get("/cards/card_003").json()["benefits"] if b["category"] == "영화")
    assert movie["title"] == "영화 5,500원 할인"


# --- 1-1-3 이용 내역 -----------------------------------------------------------------------
def test_card_transactions_by_month_newest_first(browser):
    logged_in(browser, "user_001")
    rows = browser.get("/cards/card_002/transactions", params={"month": "202610"}).json()
    expected = sql("""SELECT count(*) FROM card_transactions WHERE user_card_id = 'card_002'
                      AND transacted_at >= '2026-10-01' AND transacted_at < '2026-11-01'""").scalar()
    assert len(rows) == expected > 0
    assert [r["transacted_at"] for r in rows] == sorted((r["transacted_at"] for r in rows), reverse=True)
    assert rows[0]["transacted_at"].endswith("+09:00") and rows[0]["category_code"]
    all_rows = browser.get("/cards/card_002/transactions").json()
    assert len(all_rows) == sql("SELECT count(*) FROM card_transactions WHERE user_card_id = 'card_002'").scalar()


def test_card_transactions_filters(browser):
    logged_in(browser, "user_001")
    cafe = browser.get("/cards/card_002/transactions", params={"category": "CAFE"}).json()
    assert cafe and {r["category_code"] for r in cafe} == {"CAFE"}
    assert browser.get("/cards/card_002/transactions", params={"installment": "INSTALLMENT"}).json() == []  # 더미는 전부 일시불
    r = browser.get("/cards/card_002/transactions", params={"category": "NOPE"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_CATEGORY"
    assert browser.get("/cards/card_002/transactions", params={"month": "202613"}).status_code == 422
    other = browser.get("/cards/card_006/transactions")  # user_003 카드
    assert other.status_code == 404 and other.json()["error"]["code"] == "CARD_NOT_FOUND"


def test_parent_category_includes_children(browser):
    """교통(TRANSPORT)으로 거르면 하위 업종(택시 등)도 나온다 — 혜택 업종을 더하며 생긴 상하 관계"""
    logged_in(browser, "user_001")
    sql("""INSERT INTO merchants (id, category_id, name)
           VALUES ('mer_test', (SELECT id FROM categories WHERE code = 'TAXI'), '시험 택시')""")
    try:
        with extra_approval("card_002", 8_000, "2026-10-20 23:00:00", merchant_id="mer_test"):
            rows = browser.get("/cards/card_002/transactions", params={"category": "TRANSPORT"}).json()
            assert [(r["id"], r["category_code"], r["category"]) for r in rows] == [("ctx_test1", "TAXI", "택시")]
            assert browser.get("/cards/card_002/transactions", params={"category": "PUBLIC_TRANSIT"}).json() == []
    finally:
        sql("DELETE FROM merchants WHERE id = 'mer_test'")


# --- 1-1-4 청구서 · 결제 캘린더 · 잔액 부족 · 결제일 알림 ------------------------------------------------
def test_card_bills_calendar_has_only_my_bills(browser):
    bills = logged_in(browser, "user_001").get("/card-bills").json()
    assert {b["card_id"] for b in bills} == {"card_002", "card_003"}  # 체크카드는 청구서가 없다
    assert [b["payment_date"] for b in bills] == sorted(b["payment_date"] for b in bills)
    assert not any(b["low_balance"] for b in bills)


def test_low_balance_adds_up_bills_from_the_same_account(browser):
    """card_002(86,900)·card_003(119,200)은 둘 다 acc_001 에서 같은 날 빠진다. 잔액 10만 원이면 앞 청구서는 되고 뒤는 모자람"""
    logged_in(browser, "user_001")
    with balance_of_acc_001(100_000):
        due = {b["card_id"]: b["low_balance"] for b in browser.get("/card-bills").json() if b["status"] == "CONFIRMED"}
        assert due == {"card_002": False, "card_003": True}
        assert browser.get("/card-bills/bill_card_003_202611").json()["low_balance"] is True
        assert browser.get("/cards/card_003").json()["bills"][0]["low_balance"] is True  # 상세도 같은 판정


def test_bill_detail_items_add_up_and_others_bill_is_404(browser):
    logged_in(browser, "user_001")
    b = browser.get("/card-bills/bill_card_002_202611").json()
    assert sum(int(i["principal_amount"]) for i in b["items"]) == int(b["total_amount"]) == 86_900
    assert all(b["usage_start"] <= i["transaction"]["transacted_at"][:10] <= b["usage_end"] for i in b["items"])
    other, missing = browser.get("/card-bills/bill_card_006_202611"), browser.get("/card-bills/bill_nope")
    assert other.status_code == missing.status_code == 404 and other.json() == missing.json()


def test_termination_check_counts_only_installments_as_remaining(browser):
    """청구서 항목이 생겨도 일시불은 「남은 할부」가 아니다 (더미는 전부 일시불)"""
    check = logged_in(browser, "user_001").get("/cards/card_002/termination-check").json()
    assert check["remaining_installment_amount"] == "0" and check["unpaid_amount"] == "86900"


def run_alerts(at: datetime) -> list[str]:
    with Session(engine) as db:
        made = notify_card_payments(db, at)
        db.commit()
    return made


def test_payment_alerts_d3_and_low_balance_once():
    pay_day = sql("SELECT payment_date FROM card_bills WHERE id = 'bill_card_002_202611'").scalar()
    d3 = datetime.combine(pay_day - timedelta(days=3), datetime.min.time()).replace(hour=8)
    made, again, d0 = [], [], []
    try:
        with balance_of_acc_001(100_000):
            made = run_alerts(d3)
            again = run_alerts(d3)  # 두 번 돌려도 같은 알림은 한 번
            assert made and again == []
            rows = sql("""SELECT user_card_id, type, event_id, body FROM notifications WHERE id = ANY(:ids)
                          ORDER BY user_card_id, type""", ids=made).all()
            mine = [(r.user_card_id, r.type) for r in rows if r.user_card_id in ("card_002", "card_003")]
            # card_002 의 D-3 결제 예정은 시나리오 시드가 이미 넣어 둠(event_id = 청구서 id) → 새로 안 만든다
            assert mine == [("card_003", "LOW_BALANCE"), ("card_003", "PAYMENT_DUE")]
            assert all(r.event_id.startswith("bill_") and ":" not in r.event_id for r in rows)  # D-3 은 청구서 id
            low = next(r for r in rows if r.type == "LOW_BALANCE")
            assert "106,100원" in low.body  # 86,900 + 119,200 − 100,000
            d0 = run_alerts(d3 + timedelta(days=3))  # 결제일 당일 → ':D-0' 으로 따로 한 번 더
            ends = sql("SELECT event_id FROM notifications WHERE id = ANY(:ids)", ids=d0).scalars().all()
            assert ends and all(e.endswith(":D-0") for e in ends)
    finally:
        sql("DELETE FROM notifications WHERE id = ANY(:ids)", ids=made + again + d0)


def test_payment_alert_respects_card_setting():
    pay_day = sql("SELECT payment_date FROM card_bills WHERE id = 'bill_card_003_202611'").scalar()
    sql("INSERT INTO user_card_settings (user_card_id, payment_alert_enabled) VALUES ('card_003', FALSE)")
    made = []
    try:
        made = run_alerts(datetime.combine(pay_day, datetime.min.time()).replace(hour=8))
        cards = set(sql("SELECT user_card_id FROM notifications WHERE id = ANY(:ids)", ids=made).scalars().all())
        assert "card_003" not in cards and "card_002" in cards
    finally:
        sql("DELETE FROM notifications WHERE id = ANY(:ids)", ids=made)
        sql("DELETE FROM user_card_settings WHERE user_card_id = 'card_003'")
