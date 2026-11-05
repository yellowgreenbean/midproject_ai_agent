import os

# app 을 import 하기 전에 테스트 DB 로 바꿔야 엔진이 테스트 DB 를 가리킨다.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://app:app@localhost:5433/midproject_test",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    assert engine.url.database == "midproject_test", "테스트는 테스트 DB 에서만 돈다"
    seed.main(engine)


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def as_user(user_id: str) -> dict:
    return {"X-User-Id": user_id}
