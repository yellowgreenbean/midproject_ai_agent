SET client_encoding = 'UTF8';

-- ---------------------------------------------------------------------
-- 8. 챗봇 RAG (data/rag 의 md → scripts/rag_ingest.py 가 채움)
--    parent = 조항 한 구간(글만), child = parent 를 자른 조각(글 + 벡터). 검색은 child, LLM 에는 parent.
--    experiment: 청킹 방식 비교용 이름(예: 'pc-1000'). 같은 표에 여러 방식을 나란히 둔다.
--    embedding 은 Gemini gemini-embedding-2, 768차원 — 모델을 바꾸면 이 표 전체를 다시 채운다.
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE rag_parents (
  experiment  VARCHAR(40)   NOT NULL,
  chunk_id    VARCHAR(200)  NOT NULL,
  content     TEXT          NOT NULL,
  metadata    JSONB         NOT NULL,
  PRIMARY KEY (experiment, chunk_id)
);
COMMENT ON TABLE rag_parents IS '챗봇 RAG parent (조항 단위 글, 벡터 없음)';
COMMENT ON COLUMN rag_parents.metadata IS 'document_id, chunk_id, parent_id(null), level, title, chapter, article, chunk_index(null), source';

CREATE TABLE rag_chunks (
  experiment    VARCHAR(40)   NOT NULL,
  chunk_id      VARCHAR(200)  NOT NULL,
  parent_id     VARCHAR(200)  NOT NULL,
  content       TEXT          NOT NULL,
  content_hash  CHAR(64)      NOT NULL,
  embedding     vector(768)   NOT NULL,
  metadata      JSONB         NOT NULL,
  PRIMARY KEY (experiment, chunk_id),
  CONSTRAINT fk_rag_chunks_parent FOREIGN KEY (experiment, parent_id) REFERENCES rag_parents (experiment, chunk_id) ON DELETE CASCADE
);
-- 같은 글은 실험이 달라도 벡터를 다시 쓰려고 찾는다 (API 호출 아끼기)
CREATE INDEX idx_rag_chunks_hash ON rag_chunks (content_hash);
COMMENT ON TABLE rag_chunks IS '챗봇 RAG child (검색 단위 조각 + 벡터)';
COMMENT ON COLUMN rag_chunks.content_hash IS 'content 의 SHA-256';
-- shortcut: 벡터 인덱스(HNSW) 없이 전부 비교한다 — 실험당 3천 개 수준이라 충분. 수만 개를 넘으면 HNSW 인덱스를 단다
