"""app/models 가 docs/sql 로 만든 DB 와 같은지 검사한다.

docs/sql 을 고치고 모델을 다시 만들지 않으면(scripts/gen_models.py) 여기서 실패한다.
비교: 표 목록, 칸 순서·타입·NULL·기본값, 기본 키, 외래 키(대상·ON DELETE), UNIQUE, 인덱스, CHECK 이름과 허용 값.
"""

import re

import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.db import engine
from app.models import Base, ViewBase

PG = postgresql.dialect()
TABLES = sorted(Base.metadata.tables)


@pytest.fixture(scope="module")
def insp():
    return inspect(engine)


def _type(t) -> str:
    return t.compile(dialect=PG)


def _db_default(d: str | None) -> str | None:
    """'ACTIVE'::character varying → 'ACTIVE'"""
    return None if d is None else re.sub(r"::[\w ]+$", "", d)


def _model_default(col) -> str | None:
    sd = col.server_default
    if sd is None:
        return None
    arg = sd.arg
    return f"'{arg}'" if isinstance(arg, str) else str(arg.text)


def _in_values(sqltext: str) -> list[str] | None:
    """CHECK (칸 IN (...)) 의 허용 값. 다른 모양의 CHECK 이면 None."""
    if "= ANY" not in sqltext:
        return None
    return re.findall(r"'([^']*)'::", sqltext)


def test_same_tables(insp):
    # rag_* (docs/sql/08_rag.sql) 는 모델 없이 scripts/rag_ingest.py 가 SQL 로 직접 다룬다
    assert TABLES == sorted(t for t in insp.get_table_names() if not t.startswith("rag_"))
    assert len(TABLES) == 60


@pytest.mark.parametrize("name", TABLES)
def test_table_matches_db(insp, name):
    table = Base.metadata.tables[name]

    db_cols = insp.get_columns(name)
    assert [c.name for c in table.columns] == [c["name"] for c in db_cols], "칸 이름·순서"
    for dbc in db_cols:
        col = table.columns[dbc["name"]]
        assert _type(col.type) == _type(dbc["type"]), f"{dbc['name']} 타입"
        assert col.nullable == dbc["nullable"], f"{dbc['name']} NULL 허용"
        assert _model_default(col) == _db_default(dbc["default"]), f"{dbc['name']} 기본값"

    assert [c.name for c in table.primary_key.columns] == insp.get_pk_constraint(name)["constrained_columns"]

    model_fks = {
        (fk.parent.name, fk.target_fullname, fk.ondelete) for fk in table.foreign_keys
    }
    db_fks = {
        (fk["constrained_columns"][0], f"{fk['referred_table']}.{fk['referred_columns'][0]}",
         fk["options"].get("ondelete"))
        for fk in insp.get_foreign_keys(name)
    }
    assert model_fks == db_fks, "외래 키"

    model_uqs = {
        (c.name, tuple(col.name for col in c.columns))
        for c in table.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    db_uqs = {(u["name"], tuple(u["column_names"])) for u in insp.get_unique_constraints(name)}
    assert model_uqs == db_uqs, "UNIQUE"

    model_idx = {(i.name, tuple(c.name for c in i.columns)) for i in table.indexes}
    db_idx = {
        (i["name"], tuple(i["column_names"]))
        for i in insp.get_indexes(name)
        if not i.get("duplicates_constraint")
    }
    assert model_idx == db_idx, "인덱스"

    model_cks = {
        c.name: re.findall(r"'([^']*)'", str(c.sqltext)) if " IN (" in str(c.sqltext) else None
        for c in table.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    db_cks = {c["name"]: _in_values(c["sqltext"]) for c in insp.get_check_constraints(name)}
    assert model_cks == db_cks, "CHECK 이름·허용 값"


def test_view_matches_db(insp):
    view = ViewBase.metadata.tables["account_balance_view"]
    assert "account_balance_view" in insp.get_view_names()
    db_cols = insp.get_columns("account_balance_view")
    assert [c.name for c in view.columns] == [c["name"] for c in db_cols]
