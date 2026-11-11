"""평가 지표 — 순수 함수만 (DB·Gemini 를 부르지 않는다). eval_agent.py · rate_bm25.py 가 가져다 쓴다.

사례 하나마다 맞음/틀림(또는 0~1 점수)을 내고, summarize() 로 전체 비율을 낸다.
"""

from __future__ import annotations


# ---- 챗봇 (eval_agent.py) ----

def tool_match(expected: list[str], called: list[str]) -> bool:
    """기대 Tool 과 실제로 부른 Tool 이 맞는가 — **집합이 같아야** 맞음.

    - 순서는 보지 않는다(지금 golden set 에 순서가 뜻 있는 사례가 없음).
    - 같은 Tool 을 두 번 부른 것은 한 번으로 본다(LLM 이 다시 조회하는 건 틀림이 아님).
    - 기대에 없는 Tool 을 더 부르면 **틀림** — 예: 되물어야 하는데 Tool 을 먼저 부름, 계좌 질문에 문서 검색까지.
    - expected == [] 이면 called 도 [] 여야 맞음.
    """
    return set(expected) == set(called)


def args_match(expected: dict[str, dict], calls: list[dict]) -> bool:
    """expect_args 에 적힌 인자만 비교한다. calls = [{"name": ..., "args": {...}}, ...] (AIMessage.tool_calls 모양).

    같은 이름의 호출이 여러 번이면 그중 하나라도 적힌 인자가 모두 맞으면 맞음.
    값은 글자로 바꿔 비교한다 — 날짜는 LLM 이 낸 그대로("2026-10-01")라 golden set 에도 그 모양으로 적는다.
    """
    def ok(want: dict, got: dict) -> bool:
        return all(k in got and str(got[k]) == str(v) for k, v in want.items())

    return all(any(c["name"] == name and ok(want, c["args"]) for c in calls) for name, want in expected.items())


def links_match(expected: list[str], links: list[dict]) -> bool:
    """응답 links([{label, href}]) 에 기대 href 가 모두 있는가 (더 있는 것은 괜찮다)."""
    return set(expected) <= {link["href"] for link in links}


def contains_all(reply: str, words: list[str]) -> bool:
    """답 글에 words 가 모두 있는가 (must_contain)."""
    return all(w in reply for w in words)


def contains_none(reply: str, words: list[str]) -> bool:
    """답 글에 words 가 하나도 없는가 (must_not_contain) — 손님에게 계좌가 새지 않았는지 등."""
    return not any(w in reply for w in words)


# ---- 문서 검색 (rate_bm25.py) ----

def hit_at_k(relevant: list[str], ranked: list[str], k: int) -> float:
    """상위 k 개 안에 정답이 하나라도 있으면 1, 없으면 0."""
    return float(any(r in relevant for r in ranked[:k]))


def recall_at_k(relevant: list[str], ranked: list[str], k: int) -> float:
    """정답 중 상위 k 개 안에 들어온 비율 (정답이 여러 개인 사례용)."""
    return len(set(relevant) & set(ranked[:k])) / len(set(relevant))


def reciprocal_rank(relevant: list[str], ranked: list[str]) -> float:
    """첫 정답의 순위가 r 이면 1/r, 없으면 0. 사례들의 평균이 MRR."""
    return next((1 / r for r, doc in enumerate(ranked, start=1) if doc in relevant), 0.0)


# ---- 합치기 ----

def summarize(rows: list[dict]) -> dict[str, float]:
    """사례별 결과 [{지표 이름: 값, ...}, ...] → 지표별 평균.
    숫자·bool 칸만 센다(id 같은 글자 칸은 뺀다). 사례에 해당 없는 지표(None)는 그 지표의 평균에서 뺀다."""
    out: dict[str, float] = {}
    for key in dict.fromkeys(k for row in rows for k in row):  # 처음 나온 순서대로
        values = [row[key] for row in rows if isinstance(row.get(key), (bool, int, float))]
        if values:
            out[key] = sum(values) / len(values)
    return out


def _selftest() -> None:
    assert tool_match(["my_accounts"], ["my_accounts", "my_accounts"])
    assert not tool_match(["my_accounts"], ["my_accounts", "search_documents"])
    assert tool_match([], []) and not tool_match([], ["search_documents"])
    calls = [{"name": "account_transactions", "args": {"account_id": "acc_001", "direction": "IN"}},
             {"name": "account_transactions", "args": {"account_id": "acc_001", "direction": "OUT"}}]
    assert args_match({"account_transactions": {"direction": "OUT"}}, calls)
    assert not args_match({"account_transactions": {"direction": "OUT", "start_date": "2026-10-01"}}, calls)
    assert not args_match({"my_accounts": {}}, calls)
    assert links_match(["#/login"], [{"label": "로그인", "href": "#/login"}, {"label": "홈", "href": "#/home"}])
    assert hit_at_k(["b"], ["a", "b"], 1) == 0 and hit_at_k(["b"], ["a", "b"], 2) == 1
    assert recall_at_k(["a", "c"], ["a", "b", "c"], 2) == 0.5
    assert reciprocal_rank(["c"], ["a", "b", "c"]) == 1 / 3 and reciprocal_rank(["z"], ["a"]) == 0
    assert summarize([{"id": "x", "tool": True, "args": None}, {"id": "y", "tool": False, "args": True}]) == {"tool": 0.5, "args": 1.0}


if __name__ == "__main__":
    _selftest()
    print("metrics 자체 검사 통과")
