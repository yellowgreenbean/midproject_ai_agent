"""챗봇 평가 — golden_agent.jsonl 의 질문을 실제 Gemini 그래프로 돌려 metrics 로 채점한다.

실행 (backend/ 에서):
    PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python -m eval.eval_agent
    PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python -m eval.eval_agent --only acct-001   # 사례 하나만

주의: 질문마다 Gemini 를 1~3번 부른다.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import time
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import text

from app import agent
from app.common.db import SessionLocal
from eval import metrics
from eval.golden_set import AgentCase, load_agent_cases

CHECKS = ("tool", "args", "links", "contain", "not_contain")
BALANCE = re.compile(r"\{balance:(\w+)\}")


def resolve(db, case: AgentCase) -> AgentCase:
    """must_contain · must_not_contain 의 {balance:acc_001} 을 개발 DB 의 **지금** 잔액("1,020,000")으로 바꾼다.
    잔액은 이체·스케줄러로 바뀌므로 golden set 에 숫자를 박아 두면 답이 맞아도 틀린 것으로 나온다."""
    def balance(m: re.Match) -> str:
        v = db.scalar(text('SELECT "resAccountBalance" FROM account_balance_view WHERE account_id = :a'), {"a": m.group(1)})
        if v is None:
            raise ValueError(f"{case.id}: 잔액을 찾을 수 없는 계좌 {m.group(1)}")
        return f"{int(v):,}"

    return dataclasses.replace(case, must_contain=[BALANCE.sub(balance, w) for w in case.must_contain],
                               must_not_contain=[BALANCE.sub(balance, w) for w in case.must_not_contain])


def run_case(db, case: AgentCase) -> dict:
    """사례 하나를 돌려 {called: [Tool 이름…], calls: [{name, args}…], reply: str, links: [...]} 를 돌려준다.
    agent.answer() 는 Tool 호출을 보여 주지 않아서 같은 그래프(agent.GRAPHS)를 직접 부른다."""
    member = case.user_id is not None
    config = {"configurable": {"db": db, "user_id": case.user_id}, "recursion_limit": 12, "max_concurrency": 1}
    if member:  # 사례마다 새 thread — 같은 thread 를 쓰면 앞 사례의 상태(직전 상품·금액)가 이어진다
        config["configurable"]["thread_id"] = f"{case.user_id}:eval-{case.id}-{uuid4().hex}"
    turns = [HumanMessage(h["text"]) if h["role"] == "user" else AIMessage(h["text"]) for h in case.history]
    out = agent.GRAPHS[member].invoke({"messages": [*turns, HumanMessage(case.question)]}, config)
    calls = [{"name": c["name"], "args": c["args"]} for m in out["messages"] if isinstance(m, AIMessage) for c in m.tool_calls]
    if out.get("__interrupt__"):  # 가입 확인에서 멈춤 — 답은 확인 질문
        reply, links = out["__interrupt__"][0].value["question"], []
    else:
        last = out["messages"][-1]
        reply, links = agent.split_links(last.text, confirmed=last.name == agent.CONFIRMED)
    return {"called": [c["name"] for c in calls], "calls": calls, "reply": reply, "links": links}


def score_case(case: AgentCase, result: dict) -> dict:
    """metrics 함수로 채점. 사례에 없는 칸(예: expect_args 가 비어 있음)은 None. pass = 채점한 칸이 모두 맞음."""
    row = {
        "id": case.id,
        "tool": metrics.tool_match(case.expect_tools, result["called"]),
        "args": metrics.args_match(case.expect_args, result["calls"]) if case.expect_args else None,
        "links": metrics.links_match(case.expect_links, result["links"]) if case.expect_links else None,
        "contain": metrics.contains_all(result["reply"], case.must_contain) if case.must_contain else None,
        "not_contain": metrics.contains_none(result["reply"], case.must_not_contain) if case.must_not_contain else None,
    }
    row["pass"] = all(row[k] is not False for k in CHECKS)
    return row


def mark(v) -> str:
    return "-" if v is None else ("O" if v else "X")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="이 id 의 사례만")
    args = ap.parse_args()
    cases = [c for c in load_agent_cases() if not args.only or c.id in args.only]

    rows, failed = [], []
    with SessionLocal() as db:
        cases = [resolve(db, c) for c in cases]
        for c in cases:
            t = time.time()
            try:
                result = run_case(db, c)
                row = score_case(c, result)
            except Exception as e:  # 한 사례가 죽어도 나머지는 돈다
                result = {"called": [], "reply": f"{type(e).__name__}: {e}", "links": []}
                row = {"id": c.id, **{k: False for k in CHECKS}, "pass": False}
            db.rollback()  # Tool 은 읽기만 하지만, 다음 사례가 앞 사례의 트랜잭션을 이어받지 않게
            row["sec"] = round(time.time() - t, 1)
            rows.append(row)
            if not row["pass"]:
                failed.append((c, result))

    print(f"\n{'id':<10} {'회원':<9} " + " ".join(f"{k:>11}" for k in CHECKS) + f" {'pass':>5} {'초':>5}")
    for c, r in zip(cases, rows):
        print(f"{c.id:<10} {c.user_id or '손님':<9} " + " ".join(f"{mark(r[k]):>11}" for k in CHECKS) + f" {mark(r['pass']):>5} {r['sec']:>5}")
    s = metrics.summarize([{k: r[k] for k in (*CHECKS, "pass")} for r in rows])
    print("\n맞은 비율 (해당 사례만): " + " · ".join(f"{k} {v:.0%}" for k, v in s.items()))

    for c, result in failed:
        print(f"\n✗ {c.id} — {c.question}")
        print(f"  기대 Tool {c.expect_tools} · 부른 Tool {result['called']}")
        if c.expect_links:
            print(f"  기대 링크 {c.expect_links} · 받은 링크 {[link['href'] for link in result['links']]}")
        if c.must_contain or c.must_not_contain:
            print(f"  있어야 {c.must_contain} · 없어야 {c.must_not_contain}")
        print(f"  답: {result['reply'][:300]}")


if __name__ == "__main__":
    main()
