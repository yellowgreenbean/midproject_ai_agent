"""data/rag 의 md → parent-child 청크 → Gemini 임베딩 → midproject DB 의 pgvector 표 (docs/sql/08_rag.sql).

실행 (저장소 맨 위 폴더에서, backend/.env 에 GEMINI_API_KEY 필요):
    backend/.venv/Scripts/python scripts/rag_ingest.py                          # 청킹 통계·예시만 (DB 안 건드림)
    backend/.venv/Scripts/python scripts/rag_ingest.py --save                   # 실험 'pc-1000' 으로 저장 (있으면 바꿔 씀)
    backend/.venv/Scripts/python scripts/rag_ingest.py --save --experiment pc-500   # CHILD_MAX 를 바꾼 뒤 다른 이름으로
    backend/.venv/Scripts/python scripts/rag_ingest.py --query "정기예금 중도해지 이율" --experiment pc-1000
저장: 같은 글의 벡터가 이미 DB 에 있으면(다른 실험 포함) 다시 쓰고 없는 것만 임베딩한다. child 는 100개씩 저장·커밋하므로
      중간에 끊겨도 다시 돌리면 이미 만든 벡터를 재사용해 이어 간다.

계층:
  문서 (document_id = 폴더-번호, 예: terms-001)
  └── 장 (## 제N장 — 있으면)
      └── 조항 = parent (제목 ##·### 한 구간. 약관은 조항 하나가 뜻의 단위)
          ├── child 조각 1   ← 임베딩·검색은 child 로
          └── child 조각 2   ← 찾은 뒤 LLM 에는 parent 를 넘긴다
청킹 규칙:
  - parent 가 PARENT_MAX 를 넘으면(제목 없는 상품설명서·FAQ 는 파일 전체가 한 구간) 여러 parent 로 나눈다.
  - child 는 parent 를 CHILD_MAX 안에서 문단 → 문장 경계로 자르고, 표는 행 단위로 자르며 머리글 2줄을 조각마다 다시 붙인다.
  - 조각 글 앞에 '문서 제목 > 장 > 조' 를 붙인다(본문이라 임베딩에 들어감). 같은 값은 메타데이터에도 따로 있다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAG = REPO / "data" / "rag"
EMBED_MODEL = "gemini-embedding-2"  # 지난 미니 프로젝트와 같은 모델 — 바꾸면 docs/sql/08_rag.sql 의 vector(768) 와 표 전체를 다시
EMBED_DIM = 768
BATCH = 100
PARENT_MAX = 4000
CHILD_MAX = 1000
HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
CHAPTER = re.compile(r"^(제\s*\d+\s*[장편절]|부\s*칙)")  # 부칙도 장처럼 그 아래 조를 묶는다
ARTICLE_NO = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
SENTENCE = re.compile(r"(?<=[다요음함됨.])\s+")  # 한국어 문장 끝 뒤 공백에서 자름


def split_long(block: str, limit: int) -> list[str]:
    """limit 를 넘는 블록 하나를 자른다. 표는 행 단위(머리글 반복), 글은 문장 단위."""
    if len(block) <= limit:
        return [block]
    if block.startswith("|"):
        rows = block.split("\n")
        head, body, units = rows[:2], rows[2:], []
        # 한 행이 혼자 너무 길면(칸 하나에 긴 글) 그 행만 문장 단위로 쪼갠다
        body = [p for r in body for p in (split_long(r.strip("| "), limit) if len(r) > limit else [r])]
        cur: list[str] = []
        for r in body:
            if cur and len("\n".join(head + cur + [r])) > limit:
                units.append("\n".join(head + cur))
                cur = []
            cur.append(r)
        if cur:
            units.append("\n".join(head + cur))
        return units
    out, cur = [], ""
    for s in SENTENCE.split(block):
        while len(s) > limit:  # 문장 하나가 너무 길면 그냥 자름
            out, s = out + ([cur] if cur else []) + [s[:limit]], s[limit:]
            cur = ""
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    return out + ([cur] if cur else [])


def pack(blocks: list[str], limit: int) -> list[str]:
    """블록(문단·표)을 limit 안에서 이어 붙인다."""
    out, cur = [], ""
    for b in (u for blk in blocks for u in split_long(blk, limit)):
        if cur and len(cur) + 2 + len(b) > limit:
            out.append(cur)
            cur = b
        else:
            cur = f"{cur}\n\n{b}" if cur else b
    return out + ([cur] if cur else [])


def sections(text: str, title: str):
    """제목으로 나눈 구간들: (문서 제목, 장, 조, 블록들). '# ' 은 문서 제목, 그 아래 제목 중 제N장은 장, 가장 깊은 제목은 조."""
    path: dict[int, str] = {}
    blocks: list[str] = []
    out = []

    def close():
        if blocks:
            chapter = next((h for _, h in sorted(path.items()) if CHAPTER.match(h)), "")
            deepest = path[max(path)] if path else ""
            out.append((title, chapter, "" if deepest == chapter else deepest, blocks.copy()))
            blocks.clear()

    for raw in re.split(r"\n\s*\n", text):
        b = raw.strip()
        if not b:
            continue
        if m := HEADING.match(b) if "\n" not in b else None:
            level, h = len(m.group(1)), m.group(2).strip()
            close()
            if level == 1:
                title, path = h, {}
            else:
                path = {k: v for k, v in path.items() if k < level} | {level: h}
            continue
        blocks.append(b)
    close()
    return out


def chunk_file(md: Path, document_id: str) -> list[dict]:
    text = md.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.S)  # pdf_to_md 의 앞머리(source·pages)
    source = (re.search(r"^source:\s*(.+)$", m.group(1), re.M).group(1).strip() if m else md.name)
    text = text[m.end() :] if m else text

    records, used = [], set()
    for k, (title, chapter, article, blks) in enumerate(sections(text, md.stem), start=1):
        if n := ARTICLE_NO.match(article):
            base = f"{document_id}-article-{n.group(1)}" + (f"-{n.group(2)}" if n.group(2) else "")
        else:
            base = f"{document_id}-section-{k}"
        if base in used:  # 부칙의 제1조, 한 파일에 약관 여러 개 등 같은 조 번호가 또 나옴
            base = f"{base}-{k}"
        used.add(base)
        prefix = " > ".join(p for p in (title, chapter, article) if p)
        meta = {"document_id": document_id, "title": title, "chapter": chapter, "article": article, "source": source}
        parents = pack(blks, PARENT_MAX)
        for pi, ptext in enumerate(parents, start=1):
            parent_id = base if len(parents) == 1 else f"{base}-part-{pi}"
            records.append(
                {"content": f"{prefix}\n\n{ptext}", "metadata": {**meta, "chunk_id": parent_id, "parent_id": None, "level": "parent", "chunk_index": None}}
            )
            for ci, ctext in enumerate(pack([ptext], CHILD_MAX) if len(ptext) > CHILD_MAX else [ptext], start=1):
                records.append(
                    {
                        "content": f"{prefix}\n\n{ctext}",
                        "metadata": {**meta, "chunk_id": f"{parent_id}-child-{ci}", "parent_id": parent_id, "level": "child", "chunk_index": ci},
                    }
                )
    return records


def chunk_all() -> list[dict]:
    out = []
    for folder in sorted(p for p in RAG.iterdir() if p.is_dir()):
        for i, md in enumerate(sorted(folder.glob("*.md")), start=1):
            out += chunk_file(md, f"{folder.name}-{i:03d}")
    return out


def check(records: list[dict]):
    ids = [r["metadata"]["chunk_id"] for r in records]
    assert len(ids) == len(set(ids)), "chunk_id 중복"
    parents = {r["metadata"]["chunk_id"] for r in records if r["metadata"]["level"] == "parent"}
    children = [r for r in records if r["metadata"]["level"] == "child"]
    assert all(c["metadata"]["parent_id"] in parents for c in children), "parent 없는 child"
    assert parents == {c["metadata"]["parent_id"] for c in children}, "child 없는 parent"
    assert all(len(c["content"]) <= CHILD_MAX + 300 for c in children), "child 가 너무 김"  # +300: 앞에 붙는 제목 경로


def _selftest():
    rows = "| a | b |\n| --- | --- |\n" + "\n".join(f"| {i} | {'x' * 50} |" for i in range(40))
    parts = split_long(rows, CHILD_MAX)
    assert len(parts) > 1 and all(p.startswith("| a | b |\n| --- |") and len(p) <= CHILD_MAX for p in parts), parts
    assert sum(p.count("\n") - 1 for p in parts) == 40  # 행을 잃거나 겹치지 않음
    assert all(len(p) <= CHILD_MAX for p in split_long(("가나다라마바사 합니다. " * 200).strip(), CHILD_MAX))
    s = sections("## 제1장 총칙\n\n### 제1조(목적)\n\n본문1\n\n## 부칙\n\n### 제1조(시행일)\n\n본문2", "약관")
    assert [(c, a) for _, c, a, _ in s] == [("제1장 총칙", "제1조(목적)"), ("부칙", "제1조(시행일)")], s


# ───────────────────────── 임베딩 · 저장 · 검색 ─────────────────────────
def connect():
    import psycopg
    from dotenv import dotenv_values

    env = dotenv_values(REPO / "backend" / ".env")
    url = env.get("DATABASE_URL") or "postgresql+psycopg://app:app@localhost:5433/midproject"  # backend/app/config.py 기본값
    if not env.get("GEMINI_API_KEY"):
        sys.exit("backend/.env 에 GEMINI_API_KEY 가 없습니다")
    from google import genai

    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1)), genai.Client(api_key=env["GEMINI_API_KEY"])


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


def save(records: list[dict], experiment: str):
    conn, client = connect()
    parents = [r for r in records if r["metadata"]["level"] == "parent"]
    children = [r for r in records if r["metadata"]["level"] == "child"]
    for c in children:
        c["hash"] = hashlib.sha256(c["content"].encode("utf-8")).hexdigest()
    with conn:
        cached = dict(
            conn.execute(
                "SELECT DISTINCT ON (content_hash) content_hash, embedding::text FROM rag_chunks WHERE content_hash = ANY(%s)",
                ([c["hash"] for c in children],),
            ).fetchall()
        )
        print(f"실험 {experiment}: parent {len(parents)} · child {len(children)} (벡터 재사용 {sum(c['hash'] in cached for c in children)})")
        conn.execute("DELETE FROM rag_parents WHERE experiment = %s", (experiment,))  # child 는 CASCADE
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO rag_parents (experiment, chunk_id, content, metadata) VALUES (%s, %s, %s, %s)",
                [(experiment, p["metadata"]["chunk_id"], p["content"], json.dumps(p["metadata"], ensure_ascii=False)) for p in parents],
            )
        conn.commit()
        for i in range(0, len(children), BATCH):
            batch = children[i : i + BATCH]
            todo = [c for c in batch if c["hash"] not in cached]
            if todo:
                cached.update(zip((c["hash"] for c in todo), embed(client, [c["content"] for c in todo], "RETRIEVAL_DOCUMENT")))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO rag_chunks (experiment, chunk_id, parent_id, content, content_hash, embedding, metadata)"
                    " VALUES (%s, %s, %s, %s, %s, %s::vector, %s)",
                    [
                        (experiment, c["metadata"]["chunk_id"], c["metadata"]["parent_id"], c["content"], c["hash"], cached[c["hash"]],
                         json.dumps(c["metadata"], ensure_ascii=False))
                        for c in batch
                    ],
                )
            conn.commit()
            print(f"  child {min(i + BATCH, len(children))}/{len(children)} (새로 임베딩 {len(todo)})")
        n = conn.execute("SELECT count(*) FROM rag_chunks WHERE experiment = %s", (experiment,)).fetchone()[0]
        assert n == len(children), f"저장된 child {n} ≠ {len(children)}"
    print("저장 완료")


def search(query: str, experiment: str, k: int = 4):
    """child 로 찾고, 같은 parent 는 한 번만 — 가까운 순서로 parent 글을 돌려준다."""
    conn, client = connect()
    with conn:
        rows = conn.execute(
            "SELECT c.parent_id, min(c.embedding <=> %s::vector) AS dist, p.content, p.metadata"
            " FROM rag_chunks c JOIN rag_parents p ON p.experiment = c.experiment AND p.chunk_id = c.parent_id"
            " WHERE c.experiment = %s GROUP BY c.parent_id, p.content, p.metadata ORDER BY dist LIMIT %s",
            (embed(client, [query], "RETRIEVAL_QUERY")[0], experiment, k),
        ).fetchall()
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="data/rag md → parent-child 청크 → pgvector")
    ap.add_argument("--experiment", default=f"pc-{CHILD_MAX}", help="실험 이름 (기본: pc-<CHILD_MAX>)")
    ap.add_argument("--save", action="store_true", help="임베딩해서 DB 에 저장")
    ap.add_argument("--query", help="저장된 실험에서 검색해 보기")
    args = ap.parse_args()
    if args.query:
        for parent_id, dist, content, meta in search(args.query, args.experiment):
            print(f"\n── {1 - dist:.3f}  {parent_id}  ({meta['source']})\n{content[:300]}")
        return
    _selftest()
    records = chunk_all()
    check(records)
    if args.save:
        save(records, args.experiment)
        return
    parents = [r for r in records if r["metadata"]["level"] == "parent"]
    children = [r for r in records if r["metadata"]["level"] == "child"]
    plen = sorted(len(p["content"]) for p in parents)
    print(f"문서 {len({r['metadata']['document_id'] for r in records})}개 → parent {len(parents)}개 · child {len(children)}개")
    print(f"parent 글자 수: 중앙 {plen[len(plen) // 2]} · 최대 {plen[-1]}")
    print(f"장 있음 {sum(1 for p in parents if p['metadata']['chapter'])} · 조 있음 {sum(1 for p in parents if p['metadata']['article'])}")
    for c in [r for r in children if r["metadata"]["chunk_index"] == 2][:2]:
        print(f"\n── {c['metadata']}\n{c['content'][:300]}")


if __name__ == "__main__":
    main()
