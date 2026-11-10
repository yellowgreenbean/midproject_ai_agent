"""카드 목록 조회 — 기획서 Part 4 1-1 (CARD-F01~F04). 먼저 「로그인한 회원의 카드만 보인다」를 고정한다.

로그인은 진짜 쿠키(POST /auth/login)로 한다 — 개발용 X-User-Id 헤더는 쓰지 않는다.
더미 (data/dummy/cards/cards.json → user_cards)
  user_001: card_001 체크 · card_002 신용 · card_003 신용     user_002: card_004 체크
  user_003: card_005 체크 · card_006 신용                     user_005: 카드 없음
  user_028: PENDING_VERIFICATION (가입 마무리 중)
남의 카드는 계좌(test_api.py test_other_users_account_is_404)와 같이 「없는 카드」와 똑같은 404 — 있는지조차 알려 주지 않는다.
"""

import pytest
from fastapi.testclient import TestClient

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


# --- 로그인 확인 ---------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/cards", "/cards/card_001"])
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
