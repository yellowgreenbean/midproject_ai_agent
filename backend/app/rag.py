"""챗봇 RAG 검색 — scripts/rag_ingest.py 가 채운 rag_parents·rag_chunks(docs/sql/08_rag.sql)에서 찾는다.

child 를 벡터(pgvector 코사인 거리)와 BM25(키워드)로 각각 찾고 RRF 로 합친 뒤, 같은 parent 는 한 번만 — parent 글을 돌려준다.
벡터는 뜻이 비슷한 말("깨면 손해?" → 중도해지)을, BM25 는 정확한 낱말("제12조", 상품명)을 잘 찾는다.
"""

from __future__ import annotations

import sys
import time
from functools import cache

from rank_bm25 import BM25Okapi
from sqlalchemy import text
from sqlalchemy.orm import Session

EMBED_MODEL = "gemini-embedding-2"  # 지난 미니 프로젝트와 같은 모델 — 바꾸면 docs/sql/08_rag.sql 의 vector(768) 와 표 전체를 다시
EMBED_DIM = 768
KEEP_TAGS = ("N", "VV", "VA", "XR", "SL", "SN", "SH")  # BM25 토큰: 명사·동사/형용사 어간·어근·영문·숫자·한자 (조사·어미·기호는 버림)
SEARCH_N = 20  # 벡터·BM25 가 각각 child 를 몇 개까지 후보로 내는지
RRF_K = 60


@cache
def kiwi():
    from kiwipiepy import Kiwi

    return Kiwi()


def tokens(text_: str) -> list[str]:
    """한국어 형태소로 자른다 — 띄어쓰기로만 자르면 '이율은' 과 '이율' 이 다른 단어가 된다."""
    return [t.form for t in kiwi().tokenize(text_) if t.tag.startswith(KEEP_TAGS)]


def embed(client, texts: list[str], task: str) -> list[str]:
    """벡터를 pgvector 글자 형식('[0.1,0.2,…]')으로 돌려준다. 요청 한도(429)에 걸리면 기다렸다 다시."""
    from google.genai import errors, types

    cfg = types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM)
    for attempt in range(8):
        try:
            # 글 목록을 그대로 주면 gemini-embedding-2 는 한 콘텐츠로 합쳐 벡터 1개만 준다(2026-11-09 실측) → 글마다 Content 로 감싼다
            contents = [types.Content(parts=[types.Part(text=t)]) for t in texts]
            res = client.models.embed_content(model=EMBED_MODEL, contents=contents, config=cfg)
            assert len(res.embeddings) == len(texts), f"벡터 {len(res.embeddings)}개 ≠ 글 {len(texts)}개"
            return ["[" + ",".join(map(str, e.values)) + "]" for e in res.embeddings]
        except errors.APIError as e:
            if e.code not in (429, 500, 503) or attempt == 7:
                raise
            wait = 2**attempt * 5
            print(f"  ! Gemini {e.code} — {wait}초 뒤 다시", file=sys.stderr)
            time.sleep(wait)
    raise AssertionError("unreachable")


def bm25_rank(query: list[str], ids: list[str], index: BM25Okapi | None, n: int = SEARCH_N) -> list[str]:
    """BM25 점수가 높은 순으로 child id 를 n 개까지. 질문 낱말이 하나도 없는 child(점수 0)는 뺀다."""
    if index is None or not query:
        return []
    scores = index.get_scores(query)
    top = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)[:n]
    return [ids[i] for i in top if scores[i] > 0]


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion — 점수 단위가 다른 두 검색(BM25 점수·코사인 거리)을 순위만으로 합친다."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0) + 1 / (k + rank)
    return fused


_bm25: dict[str, tuple[list[str], list[str], BM25Okapi | None]] = {}


def bm25_index(db: Session, experiment: str):
    """(child id 들, 그 parent id 들, BM25 인덱스). 실험마다 처음 한 번 child 전부를 형태소 분석한다(수 초)."""
    # shortcut: 서버가 켜져 있는 동안 계속 쓴다 — rag_ingest.py --save 로 다시 채우면 서버를 다시 켠다
    if experiment not in _bm25:
        rows = db.execute(
            text("SELECT chunk_id, parent_id, content FROM rag_chunks WHERE experiment = :e ORDER BY chunk_id"), {"e": experiment}
        ).all()
        index = BM25Okapi([tokens(r.content) for r in rows]) if rows else None  # 빈 목록이면 BM25Okapi 가 0 으로 나눈다
        _bm25[experiment] = ([r.chunk_id for r in rows], [r.parent_id for r in rows], index)
    return _bm25[experiment]


def search(db: Session, client, query: str, experiment: str, k: int = 4, mode: str = "hybrid"):
    """child 로 찾고(vector · bm25 · hybrid = 둘을 RRF 로), 같은 parent 는 한 번만 — 점수 높은 순으로 (parent_id, 점수, 글, 메타데이터)."""
    rankings: list[list[str]] = []
    parent_of: dict[str, str] = {}
    if mode != "bm25":
        rows = db.execute(
            text("SELECT chunk_id, parent_id FROM rag_chunks WHERE experiment = :e ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"),
            {"e": experiment, "v": embed(client, [query], "RETRIEVAL_QUERY")[0], "n": SEARCH_N},
        ).all()
        parent_of.update((r.chunk_id, r.parent_id) for r in rows)
        rankings.append([r.chunk_id for r in rows])
    if mode != "vector":
        ids, parents, index = bm25_index(db, experiment)
        parent_of.update(zip(ids, parents))
        rankings.append(bm25_rank(tokens(query), ids, index))
    best: dict[str, float] = {}
    for cid, score in rrf(rankings).items():
        best[parent_of[cid]] = max(best.get(parent_of[cid], 0), score)
    top = sorted(best, key=best.get, reverse=True)[:k]
    rows = db.execute(
        text("SELECT chunk_id, content, metadata FROM rag_parents WHERE experiment = :e AND chunk_id = ANY(:ids)"), {"e": experiment, "ids": top}
    ).all()
    found = {r.chunk_id: (r.content, r.metadata) for r in rows}
    return [(pid, best[pid], *found[pid]) for pid in top]
