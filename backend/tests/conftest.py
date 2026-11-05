"""테스트 DB(midproject_test)를 개발 DB 와 똑같은 방법으로 매번 새로 만든다.

    docs/sql/00~07 (기획서 스키마)  →  scripts/load_dummy.py (data/dummy)  →  scripts/seed_scenarios.py (시나리오 시드)

지어낸 테스트 전용 데이터는 쓰지 않는다. 그래서 테스트의 기대값은 data/dummy 와 시나리오 시드의 값이다.
"""

import os
import subprocess
import sys
from pathlib import Path

# app 을 import 하기 전에 테스트 DB 로 바꿔야 엔진이 테스트 DB 를 가리킨다.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://app:app@localhost:5433/midproject_test",
)

# 조회 API 테스트(test_api.py)는 회원을 개발용 X-User-Id 헤더로 정한다. 로그인 자체는 test_auth.py 가 쿠키로 시험한다.
os.environ["AUTH_DEV_HEADER"] = "true"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _script_sql(name: str) -> str:
    """scripts/<name> 이 출력하는 INSERT SQL (스크립트는 stdout 을 UTF-8 로 쓴다)."""
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / name)], capture_output=True, check=True)
    return out.stdout.decode("utf-8")


@pytest.fixture(scope="session", autouse=True)
def test_db():
    assert engine.url.database.endswith("_test"), "테스트는 테스트 DB(이름이 _test 로 끝남)에서만 돈다"
    conninfo = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        for f in sorted((ROOT / "docs" / "sql").glob("0*.sql")):
            conn.execute(f.read_text(encoding="utf-8"))
        conn.execute(_script_sql("load_dummy.py"))
        conn.execute(_script_sql("seed_scenarios.py"))
    engine.dispose()  # 위에서 바꾼 DB 기본 시간대(Asia/Seoul)를 새 접속부터 받게


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def as_user(user_id: str) -> dict:
    return {"X-User-Id": user_id}


def seed_password() -> str:
    """seed_scenarios.py 가 해시로 넣은 시험용 비밀번호 — 환경변수, 없으면 backend/.env.example (seed 와 같은 순서)."""
    if os.environ.get("SEED_PASSWORD"):
        return os.environ["SEED_PASSWORD"]
    for line in (ROOT / "backend" / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("SEED_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_PASSWORD 를 찾을 수 없음")
