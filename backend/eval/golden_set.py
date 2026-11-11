"""golden set 읽기 — golden_agent.jsonl · golden_retrieval.jsonl 의 한 줄을 객체 하나로 (칸의 뜻은 README.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

HERE = Path(__file__).parent
AGENT_FILE = HERE / "golden_agent.jsonl"
RETRIEVAL_FILE = HERE / "golden_retrieval.jsonl"


@dataclass
class AgentCase:
    id: str
    user_id: str | None  # None = 손님
    question: str
    expect_tools: list[str]  # [] = Tool 을 부르지 않아야 함
    history: list[dict] = field(default_factory=list)
    expect_args: dict[str, dict] = field(default_factory=dict)  # {Tool 이름: {인자: 값}} — 적힌 것만 비교
    expect_links: list[str] = field(default_factory=list)
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class RetrievalCase:
    id: str
    query: str
    relevant: list[str]  # 정답 parent id (rag_parents.chunk_id)
    note: str = ""


def _read(path: Path, cls):
    """jsonl → cls 목록. 빈 줄은 건너뛰고, 깨진 JSON · 모르는 칸(오타) · 빠진 칸 · 겹치는 id 는 몇 번째 줄인지 알려 주고 멈춘다."""
    known = {f.name for f in fields(cls)}
    cases, seen = [], {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name}:{n}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{where} JSON 이 아님 — {e}") from e
        if unknown := sorted(set(row) - known):
            raise ValueError(f"{where} 모르는 칸 {unknown} (오타?)")
        try:
            case = cls(**row)
        except TypeError as e:  # 꼭 있어야 할 칸이 빠짐
            raise ValueError(f"{where} {e}") from e
        if case.id in seen:
            raise ValueError(f"{where} id '{case.id}' 가 {seen[case.id]}번째 줄과 겹침")
        seen[case.id] = n
        cases.append(case)
    return cases


def load_agent_cases(path: Path = AGENT_FILE) -> list[AgentCase]:
    """jsonl 을 한 줄씩 읽어 AgentCase 목록으로."""
    return _read(path, AgentCase)


def load_retrieval_cases(path: Path = RETRIEVAL_FILE) -> list[RetrievalCase]:
    """jsonl 을 한 줄씩 읽어 RetrievalCase 목록으로. relevant 가 비면 평가할 수 없으니 멈춘다
    (relevant id 가 rag_parents 에 실제 있는지는 rate_bm25.check_relevant_ids 가 DB 로 본다)."""
    cases = _read(path, RetrievalCase)
    if empty := [c.id for c in cases if not c.relevant]:
        raise ValueError(f"{path.name}: relevant 가 비어 있음 {empty}")
    return cases
