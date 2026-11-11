"""약관 및 동의 내역 — 기획서 Part 1 AUTH-F10 AC(어떤 버전에 언제 동의했는지 · 선택 동의 변경 이력 유지)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.common.db import engine
from app.main import app
from tests.test_signup import body, verified_token


@pytest.fixture
def member():
    """가입 직후 로그인된 브라우저 (필수만 동의, 마케팅 trm_004 는 동의 안 함)."""
    name = f"cns_{uuid.uuid4().hex[:8]}"  # 테스트 DB 는 세션 동안 하나라 테스트마다 다른 회원
    with TestClient(app) as b:
        token = verified_token(b, f"{name}@example.com")
        r = b.post("/auth/register", json=body(name, f"{name}@example.com", token))
        assert r.status_code == 201, r.text
        yield b, r.json()["user_id"]


def history(uid: str, terms_id: str) -> list[bool]:
    with engine.begin() as c:
        return list(c.execute(text("SELECT agreed FROM user_consents WHERE user_id = :u AND terms_id = :t "
                                   "ORDER BY recorded_at, id"), {"u": uid, "t": terms_id}).scalars())


def test_lists_signup_consents_with_version_and_time(member):
    b, _ = member
    r = b.get("/users/me/consents")
    assert r.status_code == 200, r.text
    got = {c["terms_id"]: c for c in r.json()}
    assert list(got) == ["trm_001", "trm_002", "trm_003", "trm_004"]
    assert got["trm_001"]["title"] == "서비스 이용약관" and got["trm_001"]["required"] is True
    assert all(got[t]["agreed"] for t in ("trm_001", "trm_002", "trm_003"))
    assert got["trm_004"]["agreed"] is False and got["trm_004"]["recorded_at"] is not None
    assert got["trm_001"]["version"]


def test_optional_toggle_keeps_history(member):
    b, uid = member
    r = b.patch("/users/me/consents", json={"terms_id": "trm_004", "agreed": True})
    assert r.status_code == 200 and {c["terms_id"]: c["agreed"] for c in r.json()}["trm_004"] is True
    b.patch("/users/me/consents", json={"terms_id": "trm_004", "agreed": True})  # 같은 값 → 행 안 늘림
    b.patch("/users/me/consents", json={"terms_id": "trm_004", "agreed": False})
    assert history(uid, "trm_004") == [False, True, False]


@pytest.mark.parametrize("terms_id, status, code", [
    ("trm_001", 400, "REQUIRED_TERMS_LOCKED"),
    ("trm_999", 404, "TERMS_NOT_FOUND"),
])
def test_cannot_change_required_or_unknown_terms(member, terms_id, status, code):
    b, uid = member
    r = b.patch("/users/me/consents", json={"terms_id": terms_id, "agreed": False})
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert history(uid, "trm_001") == [True]


def test_requires_login():
    with TestClient(app) as anon:
        assert anon.get("/users/me/consents").status_code == 401
