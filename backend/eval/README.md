# eval — 챗봇(`app/agent.py`)과 문서 검색(`app/rag.py`) 평가

자동 테스트(`tests/test_agent.py`)는 가짜 LLM 으로 **흐름·권한**만 고정한다.
여기서는 **실제 Gemini** 로 「질문에 맞는 Tool 을 고르는가」(의도 판단, 가이드북 15장)와
「문서 검색이 정답 조항을 찾는가」(가이드북 1-6)를 정해 둔 질문 묶음(golden set)으로 잰다.

## 파일
| 파일 | 하는 일 | 상태 |
|---|---|---|
| `golden_agent.jsonl` | 챗봇 golden set — 질문 · 로그인 여부 · 기대 Tool · 기대 링크 · 답에 있어야/없어야 할 말 | 7줄 |
| `golden_retrieval.jsonl` | 검색 golden set — 질문 · 정답 parent id(`rag_parents.chunk_id`) | 12줄 (약관·법령·안내·FAQ·카드 약관, 키워드형·구어체 섞음) |
| `golden_set.py` | 두 jsonl 을 읽어 파이썬 객체로 (깨진 줄·모르는 칸·겹치는 id·빈 relevant 는 줄 번호와 함께 멈춤) | 됨 |
| `metrics.py` | 평가 지표 함수 (Tool 일치 · 인자 · 링크 · 금지어 · hit@k · recall@k · MRR). `python -m eval.metrics` 로 자체 검사 | 됨 |
| `eval_agent.py` | `golden_agent.jsonl` 로 그래프를 돌려 지표 출력 | 됨 |
| `rate_bm25.py` | `golden_retrieval.jsonl` 로 bm25 · vector · hybrid 를 비교 | 됨 |

## 실행 (Git Bash, `backend/` 에서)
```bash
# PYTHONPATH=. 이 없으면 'No module named app', PYTHONIOENCODING 이 없으면 한글이 깨진다
PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python -m eval.rate_bm25 --modes bm25 vector hybrid --k 4
PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python -m eval.eval_agent
```
- 준비: `backend/.env` 의 `GEMINI_API_KEY`, 개발 DB(Docker) 켜 두기, RAG 실험 `pc-1000` 이 채워져 있을 것 (가이드북 6-1·6-2).
- `eval_agent` 와 `rate_bm25 --modes vector|hybrid` 는 **실제 Gemini 를 부른다** (질문마다 LLM 1~3번 / 임베딩 1번). `bm25` 만은 API 를 부르지 않는다.

## 채점 규칙 (`metrics.py`)
- `tool`: 부른 Tool **집합**이 `expect_tools` 와 같아야 맞음 — 순서·중복은 보지 않고, **더 부른 Tool 이 있으면 틀림**, `[]` 이면 하나도 안 불러야 맞음.
- `args`: 적힌 인자만, 같은 이름 호출 중 하나라도 맞으면 맞음. 값은 글자로 비교(날짜는 `"2026-10-01"` 모양으로 적는다).
- `links`: 기대 href 가 모두 있으면 맞음(더 있어도 됨). `contain`/`not_contain`: 글자 포함 여부.
- 사례에 없는 칸은 `-`(채점 안 함), `pass` = 채점한 칸이 모두 맞음. 회원 사례는 사례마다 새 thread 로 돈다.
- 잔액은 숫자 대신 `{balance:acc_001}` 로 적는다 — `eval_agent` 가 돌 때 개발 DB 의 **지금** 잔액(`"1,020,000"`)으로 바꿔 비교한다.
  이체·스케줄러로 잔액이 바뀌어도 사례가 따라간다(2026-11-10 acct-001 이 1,250,000 으로 박혀 있어 틀린 적 있음). `must_not_contain` 에도 쓸 수 있다.

## golden set 한 줄의 모양

`golden_agent.jsonl` — 한 줄에 JSON 하나
| 칸 | 뜻 | 예 |
|---|---|---|
| `id` | 사례 이름 (겹치지 않게) | `"acct-001"` |
| `user_id` | 로그인한 회원. `null` 이면 손님 그래프 | `"user_001"` |
| `history` | (선택) 앞 대화 `[{role: user\|assistant, text}]` — 후속 질문 시험용 | `[]` |
| `question` | 이번 질문 | `"내 계좌 잔액 알려줘"` |
| `expect_tools` | 불려야 할 Tool 이름. `[]` = Tool 을 부르지 않아야 함(되묻기·거절) | `["my_accounts"]` |
| `expect_args` | (선택) Tool 인자 중 꼭 맞아야 할 것만 | `{"account_transactions": {"direction": "OUT"}}` |
| `expect_links` | (선택) 응답 `links` 에 있어야 할 href | `["#/login"]` |
| `must_contain` / `must_not_contain` | (선택) 답 글에 있어야 / 없어야 할 말 | `["1,250,000"]` / `["acc_"]` |
| `note` | (선택) 메모 | |

`golden_retrieval.jsonl`
| 칸 | 뜻 | 예 |
|---|---|---|
| `id` | 사례 이름 | `"ret-001"` |
| `query` | 검색어 | `"예금거래기본약관 제12조"` |
| `relevant` | 정답 parent id 목록 (`rag_parents.chunk_id`, 실험 `pc-1000`) | `["terms-004-article-12"]` |
| `note` | (선택) | |

정답 id 찾기: `rag_ingest.py --query "…" --mode bm25` 로 후보를 보거나 DB 에서
`SELECT chunk_id, metadata->>'article' FROM rag_parents WHERE experiment='pc-1000' AND chunk_id LIKE 'terms-004-%';`

## 예시 줄의 근거
- `acct-001`·`doc-001`: 2026-11-10 실제 Gemini 로 돌려 그 Tool 을 고른 것을 확인함 (가이드북 15-3).
- `guest-001`: 3장 인증 게이트로 **기대되는** 동작 — 실제 Gemini 로는 아직 안 돌려 봄.
- `ret-001`: 가이드북 1-6 표 — bm25·hybrid 는 1등, vector 는 4위 안에 없음.
