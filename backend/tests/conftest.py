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
# 이메일 인증: 테스트는 메일을 받을 수 없으니 응답의 dev_code 로 번호를 받고, backend/.env 에 SMTP 를 넣어 두었어도
# 진짜 메일(…@example.com)이 나가지 않게 SMTP_HOST 를 비운다(환경변수가 .env 보다 우선)
os.environ["EMAIL_DEV_CODE"] = "true"
os.environ["SMTP_HOST"] = ""
# 서버 안 1분 스케줄러는 끈다 — 테스트가 예약 실행(app/jobs.py)을 직접 부른다
os.environ["SCHEDULER_ENABLED"] = "false"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.common.db import engine  # noqa: E402
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


def _seed_secret(name: str) -> str:
    """seed_scenarios.py 가 해시로 넣은 시험용 값 — 환경변수, 없으면 backend/.env (seed 와 같은 순서)."""
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / "backend" / ".env"
    for line in (env.read_text(encoding="utf-8").splitlines() if env.exists() else []):
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError(f"{name} 를 찾을 수 없음 — 환경변수나 backend/.env 에 넣어 주세요")


def seed_password() -> str:
    return _seed_secret("SEED_PASSWORD")


def seed_pin() -> str:
    """정상 계좌가 있는 ACTIVE 회원의 간편 비밀번호(PIN)."""
    return _seed_secret("SEED_PIN")
