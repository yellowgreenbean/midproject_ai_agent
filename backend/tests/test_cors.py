"""CORS — 허용한 화면 주소만 이 API 를 부를 수 있고, 쿠키(credentials)를 같이 주고받을 수 있다."""

from tests.conftest import as_user

ALLOWED = "http://localhost:5173"


def test_preflight_from_allowed_origin(client):
    # 브라우저가 실제 요청 전에 보내는 사전 확인(OPTIONS)
    r = client.options(
        "/accounts",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-User-Id",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ALLOWED  # "*" 가 아니라 그 주소 그대로
    assert r.headers["access-control-allow-credentials"] == "true"


def test_actual_request_from_allowed_origins(client):
    for origin in ("http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"):
        r = client.get("/accounts", headers=as_user("user_001") | {"Origin": origin})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == origin


def test_error_response_also_has_cors_headers(client):
    # 오류 응답에도 CORS 헤더가 붙어야 화면이 오류 내용(code·message)을 읽을 수 있다
    r = client.get("/accounts", headers={"Origin": ALLOWED})
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == ALLOWED


def test_other_origin_is_not_allowed(client):
    r = client.options(
        "/accounts",
        headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/accounts", headers=as_user("user_001") | {"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers  # 브라우저가 응답을 화면에 넘겨주지 않음
