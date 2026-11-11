"""모델 공통 — 기반 클래스와 docs/sql 의 공통 규칙(00_common.sql)을 SQLAlchemy 로 옮긴 것.

이 파일만 손으로 쓴다. 나머지 모델 파일은 scripts/gen_models.py 가 만든다.
"""

from sqlalchemy import CheckConstraint, text
from sqlalchemy.dialects.postgresql import TIME, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """표 61개."""


class ViewBase(DeclarativeBase):
    """보기(view). 표가 아니므로 Base 와 나눠 둔다."""


# 시각: TIMESTAMP(0), 시간대 없이 한국 시각으로 저장 (DB 기본 시간대 Asia/Seoul)
TS = TIMESTAMP(precision=0)
# 하루 중 시각(혜택의 「저녁 6~11시」 등): TIME(0)
TM = TIME(precision=0)

# 기본값(server_default) — DB 가 채운다
NOW = text("CURRENT_TIMESTAMP")
TRUE = text("true")
FALSE = text("false")


def one_of(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """MySQL ENUM 대신 쓰는 CHECK (칸 IN ('A', 'B')) — 00_common.sql 「ENUM → VARCHAR(30) + CHECK」."""
    listed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({listed})", name=name)
