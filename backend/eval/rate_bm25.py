"""문서 검색 평가 — golden_retrieval.jsonl 로 bm25 · vector · hybrid(RRF) 를 비교한다 (가이드북 1-6 을 숫자로).

실행 (backend/ 에서):
    PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python -m eval.rate_bm25 --modes bm25            # API 호출 없음
    PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python -m eval.rate_bm25 --modes bm25 vector hybrid --k 4

vector · hybrid 는 질문마다 Gemini 임베딩을 1번 부른다.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app import rag
from app.agent import gemini
from app.common.db import SessionLocal
from app.config import settings
from eval import metrics
from eval.golden_set import load_retrieval_cases

MODES = ("bm25", "vector", "hybrid")  # rag.search(mode=…) 가 받는 값


def ranked_parents(db, client, query: str, experiment: str, mode: str, k: int) -> list[str]:
    """rag.search() 결과에서 parent id 만 순위대로. bm25 는 임베딩을 안 부르므로 client 가 None 이어도 된다."""
    return [pid for pid, *_ in rag.search(db, client, query, experiment, k=k, mode=mode)]


def check_relevant_ids(db, cases, experiment: str) -> None:
    """golden set 의 relevant id 가 rag_parents 에 실제 있는지 — 없으면 어느 사례인지 알려 주고 멈춘다 (오타·실험 이름 실수 잡기)."""
    ids = sorted({r for c in cases for r in c.relevant})
    found = set(db.scalars(text("SELECT chunk_id FROM rag_parents WHERE experiment = :e AND chunk_id = ANY(:ids)"),
                           {"e": experiment, "ids": ids}))
    if missing := [(c.id, r) for c in cases for r in c.relevant if r not in found]:
        sys.exit(f"실험 '{experiment}' 의 rag_parents 에 없는 정답 id: {missing}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    ap.add_argument("--k", type=int, default=4, help="상위 몇 개까지 볼지 (챗봇 search_documents 는 4)")
    ap.add_argument("--experiment", default=None, help="RAG 실험 이름 (기본: settings.rag_experiment)")
    args = ap.parse_args()
    experiment = args.experiment or settings.rag_experiment

    cases = load_retrieval_cases()
    with SessionLocal() as db:
        check_relevant_ids(db, cases, experiment)
        client = gemini() if set(args.modes) - {"bm25"} else None
        rows: dict[str, list[dict]] = {}
        for mode in args.modes:
            for c in cases:
                ranked = ranked_parents(db, client, c.query, experiment, mode, args.k)
                rows.setdefault(mode, []).append({
                    "id": c.id, "ranked": ranked, f"hit@{args.k}": metrics.hit_at_k(c.relevant, ranked, args.k),
                    f"recall@{args.k}": metrics.recall_at_k(c.relevant, ranked, args.k), "MRR": metrics.reciprocal_rank(c.relevant, ranked),
                })

    print(f"\n실험 {experiment} · 사례 {len(cases)}개 · k={args.k}\n")
    cols = [f"hit@{args.k}", f"recall@{args.k}", "MRR"]
    print(f"{'모드':<8}" + "".join(f"{c:>11}" for c in cols))
    for mode, rs in rows.items():
        s = metrics.summarize(rs)
        print(f"{mode:<8}" + "".join(f"{s[c]:>11.3f}" for c in cols))

    print("\n사례별 첫 정답 순위 (- = 상위 k 안에 없음)")
    print(f"{'id':<12}" + "".join(f"{m:>8}" for m in rows) + "  질문")
    for i, c in enumerate(cases):
        ranks = [next((str(r) for r, pid in enumerate(rows[m][i]["ranked"], 1) if pid in c.relevant), "-") for m in rows]
        print(f"{c.id:<12}" + "".join(f"{r:>8}" for r in ranks) + f"  {c.query}")


if __name__ == "__main__":
    main()
