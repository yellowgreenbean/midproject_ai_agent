# API 정의서 — 예금·적금 상품 · 가입 · 챗봇

> 대상: 이 API 를 부르는 화면(frontend) 개발자 · 팀원 · 리뷰어
> 범위: 2026-11-10 에 Yellow 브랜치 백엔드에 만든 / 바꾼 API 7개 — 상품 6개(`backend/app/routers/products.py`, **새로 만듦**) + 챗봇 1개(`backend/app/routers/agent.py`, **가입 확인 단계를 더함**)
> 근거: `docs/기획서.md` Part 3 「5. AI 자연어 입력과 RAG」 · 「7. API 초안」 · PROD-F01~F08. 만든 과정은 `docs/가이드북_챗봇랭그래프.md` 2부(8~14장)
> 서버 주소(개발): `http://localhost:8010` · 실제로 불러 보기: `http://localhost:8010/docs` (Swagger)

---

## 0. 한눈에 보기

| # | 메서드 · 경로 | 하는 일 | 로그인 | 화면 함수 (`frontend/src/api.ts`) |
|---|---|---|---|---|
| P1 | `GET /products` | 판매 중인 예금·적금 목록 (검색·종류·금리 순) | 필요 없음 | `getProducts` |
| P2 | `GET /products/recommended` | 홈 추천 상품 2개 | 필요 없음 | `getRecommendedProducts` |
| P3 | `GET /products/{productId}` | 상품 상세 (금리표·가입 조건·상품설명서 목록) | 필요 없음 | `getProduct` |
| P4 | `POST /products/{productId}/estimate` | 예상 이자·만기일 계산 | 필요 없음 | `estimateInterest` |
| P5 | `POST /products/{productId}/validate` | 가입 직전 검사 (출금 계좌·잔액·1인당 개수) | **필요** | `validateSubscription` |
| P6 | `POST /subscriptions` | 예금·적금 가입 (돈이 빠져나감) | **필요 + 본인 확인 + `Idempotency-Key`** | `subscribe` |
| C1 | `POST /agent/chat` | 챗봇 — 자연어 질문 · 화면 링크 · **가입 전 확인** | 선택 (손님 / 회원) | `sendChat` |

가입까지의 흐름(화면):
```
P1 목록 → P3 상세 → (금액·기간 입력) P4 예상 이자 → (출금 계좌 선택) P5 가입 검사
       → POST /auth/step-up {action: "SUBSCRIPTION", password} → step_up_challenge_id
       → P6 가입 (Idempotency-Key) → 「내 가입 상품」 GET /users/me/subscriptions
```
챗봇에서 시작하면: C1 「두린 적금 20만 원씩 12개월 가입」 → C1 확인 질문 → C1 「네」 → 링크 `#/products/prod_004/subscribe?amount=200000&months=12` → 위 흐름의 「금액·기간 입력」부터(값이 채워진 채).

---

## 1. 공통 규칙

### 1-1. 인증
| 방식 | 설명 |
|---|---|
| 로그인 쿠키 `sid` | `POST /auth/login` 이 심는다. 화면은 `fetch(..., { credentials: 'include' })` 로 보낸다 |
| `X-User-Id` 헤더 | **개발용**. 서버 설정 `AUTH_DEV_HEADER=true` 일 때만 쓰인다(기본 꺼짐). 본인 확인(step-up)은 세션에 묶이므로 이 헤더로는 P6 를 할 수 없다 |
| 응답 헤더 `X-Session-Expires-At` | 로그인한 요청의 응답에 붙는다. 세션이 끊길 시각(+09:00 ISO 8601) — 유휴 10분과 최대 12시간 중 먼저 오는 것 |

로그인이 필요한 API 의 공통 오류:
| HTTP | code | 언제 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 쿠키 없음 · 없는 세션 · 탈퇴 회원 |
| 401 | `SESSION_EXPIRED` | 세션이 시간 초과로 끊김 |
| 403 | `SIGNUP_INCOMPLETE` | 가입 마무리 중(`PENDING_VERIFICATION`) 회원 |

### 1-2. 요청 출처 검사 (CSRF)
`POST` 요청의 `Origin` 헤더가 허용 목록(`CORS_ORIGINS`, 개발 기본 `localhost`·`127.0.0.1` 의 5173·3000 포트)도 아니고 API 자신도 아니면 **403 `ORIGIN_NOT_ALLOWED`**. `Origin` 이 없는 요청(curl·테스트)은 통과한다. 허용하는 요청 헤더: `Content-Type` · `Idempotency-Key` · `X-User-Id`.

### 1-3. 값의 모양
| 종류 | 모양 | 예 |
|---|---|---|
| 금액 (요청·응답) | **숫자만 든 문자열**, 원 단위 | `"200000"` |
| 금리 | 연 %, 소수 둘째 자리 문자열 | `"3.20"` |
| 날짜 | `YYYYMMDD` 문자열 | `"20271110"` |
| 우리가 만든 빈 칸 | `null` | `"min_amount": null` |
| 상품 종류 `type` | `TIME_DEPOSIT`(정기예금) · `INSTALLMENT_SAVINGS`(적금) | |
| 기간 단위 `term_unit` | `MONTH`(개월) · `DAY`(일 — 표지어음·CD 같은 일 단위 상품) | |
성공 응답은 **감싸지 않고 본문 그대로** 온다.

### 1-4. 오류 응답
```json
{"success": false, "error": {"code": "AMOUNT_OUT_OF_RANGE", "message": "예치금을 다시 확인해 주세요. (1,000,000원 이상)"}}
```
- `message` 는 **화면에 그대로 보여 줄 수 있는 문장**이다(해요체). 화면은 분기에 `code` 를 쓴다.
- 요청 모양이 틀리면(필수 칸 없음 · 타입 · 길이) **422 `VALIDATION_ERROR`** 이고 `details` 가 붙는다:
  ```json
  {"success": false, "error": {"code": "VALIDATION_ERROR", "message": "요청 값을 확인해 주세요.",
                               "details": [{"field": "amount", "reason": "String should have at most 15 characters"}]}}
  ```
- 없는 것과 남의 것은 **똑같이 404** — 존재 여부를 알리지 않는다(예: 남의 계좌도 `ACCOUNT_NOT_FOUND`).

### 1-5. [모의 규칙] 이자 · 만기 (P4·P5·P6·C1 공통, 기획서 PROD-F05·F06)
| 항목 | 규칙 |
|---|---|
| 이자 | **단리 · 세전 · 원 미만 버림**. 적용 금리는 **기본 금리만**(우대 조건 판정은 3차) |
| 정기예금 | 원금 × 연이율 × 개월/12 · 일 단위 상품: 원금 × 연이율 × 일수/365 |
| 적금 | 매달 같은 금액을 낸다고 보고, 납입마다 납입액 × 연이율 × (그날부터 만기까지 꽉 찬 개월)/12 의 합 |
| 만기일 | 가입일(오늘, 한국 시간)과 같은 날짜의 N개월 뒤 — 그 달에 같은 날이 없으면 말일(1/31 + 1개월 = 2/28). 일 단위 상품은 N일 뒤 |
| 금액 범위 | 정기예금: 상세의 `min_amount`~`max_amount`(넣는 금액), `amount_unit` 단위 · 적금: 같은 칸이 **월 납입액** 범위·단위 |
| 기간 범위 | 개월: `min_months`~`max_months`, `selectable_months` 가 있으면 그중에서만 · 일: `min_days`~`max_days` · 그 기간을 덮는 금리 구간이 있어야 함 |
| 가입할 수 없는 상품 | 금리표가 없는 상품(prod_010·014·031·032) · N일 적금(일 단위 적금 prod_024~026 — 매일 자동 납입 필요) → 상세 `subscribable: false` |

---

## 2. 상품 API

### P1. `GET /products` — 상품 목록
판매 중(`ON_SALE`)인 상품만 돌려준다.

**Query**
| 이름 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `q` | string | | 40자 이하 | 상품 이름 일부. 글자 그대로 찾는다(`%`·`_` 도 글자) |
| `type` | string | | `TIME_DEPOSIT` / `INSTALLMENT_SAVINGS` | 종류 |
| `sort` | string | | `rate` | 최고 금리 높은 순(금리표가 없는 상품은 맨 뒤). 없으면 상품 id 순 |

**응답 200** — `ProductSummary[]`
| 칸 | 타입 | 설명 |
|---|---|---|
| `id` | string | 상품 id (예: `prod_004`) |
| `name` | string | 상품 이름 |
| `type` | string | `TIME_DEPOSIT` / `INSTALLMENT_SAVINGS` |
| `description` | string \| null | 한 줄 설명 |
| `base_rate` | string \| null | 금리표의 가장 높은 **기본** 금리. 금리표가 없으면 `null` |
| `max_rate` | string \| null | 기본 + 우대 최대 금리의 가장 높은 값 |
| `term_label` | string | 가입 기간 표시 — `12개월` · `1~36개월` · `30~365일` · `3개월 이상` · 금리표가 없으면 `""` |
| `early_termination_allowed` | boolean | 중도 해지할 수 있는가 |
```json
[
  {"id": "prod_020", "name": "두린 두근두근 행운적금", "type": "INSTALLMENT_SAVINGS",
   "description": "매달 행운카드를 열어 당첨되면 우대금리를 받는 6개월 적금",
   "base_rate": "3.00", "max_rate": "13.00", "term_label": "6개월", "early_termination_allowed": true}
]
```
**오류**: 422 `VALIDATION_ERROR` (`q` 40자 초과 · `type`/`sort` 값이 목록 밖)

---

### P2. `GET /products/recommended` — 홈 추천 상품
지금은 고정 2개(`prod_003`·`prod_004`). 조건 기반 추천(3차)이 생기면 바뀐다.

**응답 200** — `RecommendedProduct[]`
| 칸 | 타입 | 설명 |
|---|---|---|
| `id` · `name` | string | |
| `description` | string | 설명(없으면 `""`) |
| `max_rate` | string | 최고 금리(금리표가 없으면 `"-"`) |
| `term_label` | string | P1 과 같음 |
| `icon` | string | `safe`(정기예금) / `coins`(적금) — 화면 아이콘 이름 |
```json
[
  {"id": "prod_003", "name": "두린플러스 예금", "description": "기간도 금액도 내맘대로 예금(만기 1~36개월 선택, 기간별 금리)",
   "max_rate": "3.60", "term_label": "1~36개월", "icon": "safe"},
  {"id": "prod_004", "name": "두린 적금", "description": "실명의 개인 1인 1계좌 적금",
   "max_rate": "3.40", "term_label": "12개월", "icon": "coins"}
]
```

---

### P3. `GET /products/{productId}` — 상품 상세
판매가 끝난 상품도 조회는 된다(가입은 P4 에서 막힘).

**Path**: `productId` string, 40자 이하

**응답 200** — `ProductDetail` = P1 의 모든 칸 +
| 칸 | 타입 | 설명 |
|---|---|---|
| `verified_at` | string \| null | 상품 정보를 확인한 날 `YYYYMMDD` |
| `rates` | object[] | 금리표 — `{term_min, term_max, term_unit, base_rate, bonus_rate}`. `term_min`·`term_max` 는 양 끝 포함, `bonus_rate` 는 우대 금리 최대치(없으면 `null`) |
| `min_amount` · `max_amount` | string \| null | 정기예금: 넣는 금액 범위 · 적금: **월 납입액** 범위. 없으면 제한 없음 |
| `amount_unit` | string \| null | 금액 단위(예: `"1000"` = 천 원 단위). 없으면 1원 |
| `min_months` · `max_months` | integer \| null | 가입 기간(개월) 범위 |
| `selectable_months` | integer[] \| null | 고를 수 있는 기간이 정해진 상품만(예: `[3, 6, 9]`) |
| `max_per_user` | integer \| null | 1인당 가입할 수 있는 개수(진행 중 계약 기준) |
| `min_days` · `max_days` | integer \| null | 일 단위 상품의 기간(일) 범위 |
| `eligibility` | string \| null | 가입 대상 |
| `notes` | string[] | 안내 문구 — 이자 지급 방식 · 우대 조건 · 기간 안내 · 비과세 · 가입 채널 |
| `subscribable` | boolean | 앱에서 가입할 수 있는가 (1-5 「가입할 수 없는 상품」이면 `false`) |
| `documents` | object[] | **새 칸** — 상품설명서 목록 `{id, title, source}`. `source` 는 챗봇 문서 검색의 출처 이름과 같은 값. **파일은 내려주지 않는다**(원본에 실제 은행 이름이 있어서). 설명서가 없는 상품은 `[]` |
```json
{
  "id": "prod_004", "name": "두린 적금", "type": "INSTALLMENT_SAVINGS", "description": "실명의 개인 1인 1계좌 적금",
  "base_rate": "3.20", "max_rate": "3.40", "term_label": "12개월", "early_termination_allowed": true,
  "verified_at": "20261104",
  "rates": [{"term_min": 12, "term_max": 12, "term_unit": "MONTH", "base_rate": "3.20", "bonus_rate": "0.20"}],
  "min_amount": null, "max_amount": "500000", "amount_unit": null,
  "min_months": 12, "max_months": 12, "selectable_months": null, "max_per_user": 1, "min_days": null, "max_days": null,
  "eligibility": "실명의 개인",
  "notes": ["만기일시지급식", "최대 연 0.2%p: 두린통장/두린꿈통장에서 출금해 가입 0.1%p + …", "비과세종합저축 가입 가능(본인 한도 내)"],
  "subscribable": true,
  "documents": [{"id": "doc_prod_004", "title": "두린 적금 상품설명서", "source": "prod_004.pdf"}]
}
```
**오류**
| HTTP | code | 언제 |
|---|---|---|
| 404 | `PRODUCT_NOT_FOUND` | 없는 상품 |
| 422 | `VALIDATION_ERROR` | `productId` 40자 초과 |

> `documents` 는 `scripts/load_dummy.py` 가 `data/rag/products/*.md` 파일 이름으로 만든다. 2026-11-10 이전에 만든 개발 DB 에는 비어 있으니 `load_dummy.py` 를 한 번 다시 넣는다(`docs/가이드북_챗봇랭그래프.md` 13-1).

---

### P4. `POST /products/{productId}/estimate` — 예상 이자
금액·기간이 이 상품에 맞는지 검사하고, 맞으면 예상 이자를 계산한다. 규칙은 1-5. 챗봇의 가입 확인(C1)과 P5·P6 도 **이 계산을 그대로** 쓴다.

**Path**: `productId` string, 40자 이하

**Body**
| 칸 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `amount` | string | ✅ | 15자 이하, 숫자만(아니면 `AMOUNT_OUT_OF_RANGE`) | 정기예금: 넣는 금액 · 적금: **월 납입액** (원) |
| `months` | integer | | 0~600, 기본 0 | 가입 기간(개월). 일 단위 상품이면 무시 |
| `days` | integer \| null | | 0~3650 | 일 단위 상품(`rates[].term_unit == "DAY"`)의 기간(일) |
```json
{"amount": "200000", "months": 12}
{"amount": "10000000", "months": 0, "days": 90}
```

**응답 200** — `Estimate`
| 칸 | 타입 | 설명 |
|---|---|---|
| `rate` | string | 적용 금리 = 그 기간 금리 구간의 **기본** 금리 |
| `interest` | string | 세전 이자 |
| `principal_total` | string | 만기까지 넣는 원금 합계 (예금 = 금액, 적금 = 월 납입액 × 개월) |
| `maturity_amount` | string | 원금 합계 + 이자 |
| `maturity_date` | string | 만기일 `YYYYMMDD` (오늘 가입 기준) |
| `first_payment` | string | 가입할 때 출금되는 돈 (예금 = 전액, 적금 = 첫 회차) |
```json
{"rate": "3.20", "interest": "41600", "principal_total": "2400000", "maturity_amount": "2441600",
 "maturity_date": "20271110", "first_payment": "200000"}
```
계산 예 (테스트로 고정): prod_005 1,000,000원 6개월 연 3.75% → `18750` · prod_004 월 100,000원 12개월 연 3.20% → `20800` · prod_012 10,000,000원 90일 연 2.05% → `50547`

**오류** (위에서부터 차례로 검사)
| HTTP | code | 언제 | message 예 |
|---|---|---|---|
| 404 | `PRODUCT_NOT_FOUND` | 없는 상품 | 상품을 찾을 수 없어요. |
| 409 | `PRODUCT_NOT_ON_SALE` | 판매 중지 상품 | 판매가 끝난 상품이에요. |
| 422 | `NOT_SUBSCRIBABLE` | 금리표가 없는 상품 | 금리표가 없어 지금은 앱에서 가입할 수 없는 상품이에요. |
| 422 | `TERM_UNIT_NOT_SUPPORTED` | N일 적금 | N일 적금은 매일 자동 납입이 필요해 아직 앱에서 가입할 수 없어요. |
| 422 | `AMOUNT_OUT_OF_RANGE` | 숫자가 아님(전각 숫자 포함) · 0 이하 | 금액을 숫자로 입력해 주세요. |
| 422 | `TERM_OUT_OF_RANGE` | 기간이 범위·선택지 밖 | 가입 기간은 3개월, 6개월, 9개월 중에서 골라 주세요. |
| 422 | `RATE_NOT_FOUND` | 그 기간을 덮는 금리 구간이 없음 | 이 기간에 맞는 금리가 없어 계산할 수 없어요. |
| 422 | `AMOUNT_OUT_OF_RANGE` | 금액이 범위 밖 · 단위가 안 맞음 | 예치금을 다시 확인해 주세요. (1,000,000원 이상) · 월 납입액을 다시 확인해 주세요. (1원 이상 500,000원 이하) |
| 422 | `VALIDATION_ERROR` | 요청 모양이 틀림 | 요청 값을 확인해 주세요. |

---

### P5. `POST /products/{productId}/validate` — 가입 직전 검사
가입 화면의 [확인] 단계. **P6 가 하는 검사와 똑같다**(돈은 움직이지 않음). 본인 확인 번호는 받지 않는다.

**인증**: 로그인 필요 (1-1)

**Body** = P4 의 칸 +
| 칸 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `account_id` | string | ✅ | 40자 이하 | 출금 계좌 id |
```json
{"account_id": "acc_001", "amount": "100000", "months": 12}
```

**응답 200** — `Estimate` (P4 와 같은 모양)

**오류** (차례로 검사) — 1-1 의 공통 오류 +
| HTTP | code | 언제 |
|---|---|---|
| 403 | `USER_NOT_ACTIVE` | 회원 상태가 `ACTIVE` 가 아님(이용 제한 `RESTRICTED` 는 정리 동작만 가능) — 「지금 계정 상태에서는 가입할 수 없어요.」 |
| (P4 의 오류 전부) | | 상품·금액·기간 |
| 404 | `ACCOUNT_NOT_FOUND` | 없는 계좌 · **남의 계좌** |
| 422 | `INVALID_ACCOUNT_TYPE` | 입출금 계좌(`CHECKING`)가 아님 — 「입출금 계좌에서만 가입할 수 있어요.」 |
| 422 | `ACCOUNT_NOT_ACTIVE` | 정지·해지된 계좌 |
| 422 | `INSUFFICIENT_BALANCE` | 잔액 < `first_payment` — 「잔액이 부족해요. (지금 잔액 1,250,000원)」 |
| 409 | `SUBSCRIPTION_LIMIT_EXCEEDED` | 이 상품을 이미 `max_per_user` 개 진행 중 — 「이 상품은 1인당 1개까지 가입할 수 있어요.」 |

---

### P6. `POST /subscriptions` — 가입
계약 생성 · (적금) 첫 회차 납입 기록 · 출금 계좌 원장 출금(`SUBSCRIPTION_PAYMENT`)이 **함께 성공하거나 함께 실패**한다. 이체 한도에는 세지 않는다(본인 계좌 사이).

**인증**: 로그인 쿠키(세션) 필요 + **본인 확인** — 먼저 `POST /auth/step-up` `{"action": "SUBSCRIPTION", "password": "…"}` 으로 받은 `step_up_challenge_id`(이 회원 · 이 세션 · `SUBSCRIPTION` 한정, 5분, 한 번만).

**Header**
| 이름 | 필수 | 제약 | 설명 |
|---|---|---|---|
| `Idempotency-Key` | ✅ | 8~80자 | 같은 가입 요청을 두 번 보내도 계약이 하나만 생기게 하는 번호. 화면은 최종 확인 화면에 들어올 때 한 번 만든다(UUID). 서버는 회원별로 따로 저장한다 |

**Body** = P5 의 칸 +
| 칸 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `product_id` | string | ✅ | 40자 이하 | 상품 id (이 API 는 경로에 상품 id 가 없다) |
| `step_up_challenge_id` | string | ✅ | 40자 이하 | 본인 확인 번호 |
```json
{"product_id": "prod_004", "account_id": "acc_001", "amount": "100000", "months": 12,
 "step_up_challenge_id": "stu_3f9c…"}
```

**처리 순서**
1. 같은 `Idempotency-Key` 로 이미 가입했으면 → 상품·계좌가 같으면 **처음 결과를 그대로 201**(돈은 한 번만 나감), 다르면 409 `IDEMPOTENCY_KEY_REUSED`. 이 경우 본인 확인 번호는 쓰지 않는다.
2. 본인 확인 번호를 쓴다 → 3. 출금 계좌 잔액을 잠근다 → 4. P5 와 같은 검사(잠근 잔액으로)
5. 계약 저장(`applied_rate` = 가입 당시 기본 금리) → 6. 적금이면 첫 회차 납입 기록 → 7. 원장 출금 → 8. 커밋
- 4 에서 실패하면 **아무것도 남지 않고 본인 확인 번호도 다시 쓸 수 있다**(롤백).

**응답 201** — `Subscription` (`GET /users/me/subscriptions` 의 한 줄과 같은 모양)
| 칸 | 타입 | 설명 |
|---|---|---|
| `id` | string | 가입 id (`sub_` + 무작위 20자리) |
| `product_id` · `product_name` · `product_type` | string | 상품 |
| `account_number` | string | 출금 계좌 표시 번호 |
| `principal` | string | 지금까지 넣은 원금 (가입 직후 = `first_payment`) |
| `monthly_amount` | string \| null | 적금의 월 납입액, 정기예금은 `null` |
| `applied_rate` | string | 적용 금리(가입 당시 값으로 고정 — 나중에 상품 금리가 바뀌어도 그대로) |
| `start_date` · `maturity_date` | string | `YYYYMMDD` |
| `status` | string | `ACTIVE` |
```json
{"id": "sub_9a1f0c2b7d3e4a5f6b7c", "product_id": "prod_004", "product_name": "두린 적금", "product_type": "INSTALLMENT_SAVINGS",
 "account_number": "110-00-000001", "principal": "100000", "monthly_amount": "100000", "applied_rate": "3.20",
 "start_date": "20261110", "maturity_date": "20271110", "status": "ACTIVE"}
```

**오류** — 1-1 의 공통 오류 + P5 의 오류 전부 +
| HTTP | code | 언제 |
|---|---|---|
| 422 | `VALIDATION_ERROR` | `Idempotency-Key` 헤더가 없거나 8자 미만 · 80자 초과 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 같은 키로 다른 상품·계좌 — 「이미 다른 내용으로 보낸 요청 번호예요. 처음부터 다시 가입해 주세요.」 |
| 403 | `STEP_UP_REQUIRED` | 본인 확인 번호가 없음 · 남의 것 · 다른 세션 · 다른 action · 5분 지남 · 이미 씀 — 「본인 확인을 다시 해 주세요.」 |
| 409 | `CONFLICT_RETRY` | 다른 요청과 동시에 겹침 — 잠시 뒤 다시 |

---

## 3. 챗봇 API

### C1. `POST /agent/chat` — 챗봇 (가입 전 확인 포함)
- 로그인 없이도 쓴다. **손님**은 문서 검색 · 상품 목록/상세만, **회원**은 내 계좌·가입 상품·거래·이체 조회와 **가입 준비**까지.
- 챗봇은 돈을 움직이지 않는다. 가입은 확인을 받은 뒤 **가입 화면 링크**로 넘긴다(그 화면이 P5 → 본인 확인 → P6).

**인증**: 선택. 쿠키가 없으면 손님. 쿠키가 있는데 끊긴 세션이면 손님으로 바꾸지 않고 401, 가입 마무리 중이면 403(1-1).

**Body**
| 칸 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `message` | string | ✅ | 500자 이하 | 사용자의 말. **빈 글이면 대화 시작 인사**(LLM 을 부르지 않음) |
| `context` | object \| null | | | 직전 응답의 `context` 를 **그대로** 돌려보낸다. 첫 요청은 빼도 된다 |
| `context.history` | object[] | | 20개 이하 | 최근 대화 `{role: "user" \| "assistant", text: 4000자 이하}` |
| `context.thread_id` | string \| null | | 소문자 16진수 32자리 | **새 칸** — 회원 대화 번호. 서버가 만들어 준 값을 그대로 돌려보낸다 |
```json
{"message": "20만 원씩 12개월", "context": {"history": [...], "thread_id": "3f2a9c0b1d4e5f60718293a4b5c6d7e8"}}
```

**응답 200**
| 칸 | 타입 | 설명 |
|---|---|---|
| `reply` | string | 챗봇의 답 (화면 링크 표시 `[[#/…]]` 는 떼어 낸 글) |
| `links` | object[] | 화면 링크 버튼 `{label, href}`. `href` 는 화면 주소(예: `#/accounts`). 실제 있는 화면만 온다 |
| `suggestions` | string[] | 버튼으로 보여 줄 말. 인사일 때 추천 질문 3개, **가입 확인 질문일 때 `["네", "아니요"]`**, 그 밖엔 `[]` |
| `context` | object | 다음 요청에 그대로 돌려보낼 값 — `history`(최근 20개) · `thread_id`(회원은 문자열, 손님은 `null`) |

**대화 번호와 이어 가기** (회원)
| 요청의 상태 | 서버가 하는 일 |
|---|---|
| `thread_id` 없음 (첫 요청) | 새 번호를 만들어 응답 `context.thread_id` 로 준다 |
| 그 번호의 대화가 **가입 확인 질문에서 멈춰 있음** | 이번 `message` 를 확인 질문의 **답**으로 받는다 (아래 표) |
| 이어지는 대화 | 서버에 남은 대화·상태(직전 상품·금액·기간)에 새 말만 더한다 |
| 서버가 모르는 번호 (서버 재시작 등) | `context.history` 로 대화를 다시 시작한다 — 확인 대기는 사라짐 |
- 서버는 대화 번호를 **회원별로** 저장한다. 다른 회원의 `thread_id` 를 보내도 그 사람의 대화가 이어지지 않는다.
- 손님은 서버에 대화를 남기지 않는다(`thread_id` 는 항상 `null`, `history` 만 쓴다).

**가입 확인 질문에 대한 답** — 짧은 답만 승인/거절로 본다(띄어쓰기·`.!?~,` 는 무시, 영문은 대소문자 무시)
| 사용자의 말 | 결과 |
|---|---|
| 네 · 예 · 응 · 어 · ㅇㅇ · 좋아(요) · 그래(요) · 맞아(요) · 확인 · 진행(해줘·해주세요) · 가입(할게요·해줘·해주세요) · yes · ok | `reply` 안내 + `links: [{"label": "상품 가입", "href": "#/products/<id>/subscribe?amount=<원>&months=<개월>"}]` (일 단위 상품은 `days=<일>`) |
| 아니(요·오) · 아뇨 · ㄴㄴ · 싫어(요) · 취소(해줘) · 안 할래(요) · 그만(할래요·둘래요) · no | 「가입 안내를 멈췄어요」, 링크 없음 |
| 그 밖의 말 (예: 「네 근데 금액은 30만 원으로」) | 새 요청으로 처리. 상품·기간은 기억하고 있어서 바뀐 값으로 **다시 확인 질문** |
- 가입 화면 링크(`/products/<id>/subscribe…`)는 **「네」 답에서만** 나온다. 그 밖의 답에 들어 있으면 서버가 버린다.

**예시 — 회원의 가입 흐름**
```
① 요청 {"message": "두린 적금 가입하고 싶어"}
   응답 {"reply": "매달 얼마씩, 몇 개월 동안 넣으실 건가요?", "links": [], "suggestions": [],
         "context": {"history": [...2개], "thread_id": "3f2a…"}}

② 요청 {"message": "20만 원씩 12개월", "context": <①의 context>}
   응답 {"reply": "두린 적금(적금)에 매달 200,000원씩 12개월 동안 가입하려고 해요.\n기본 금리 연 3.20%로 만기일(2027.11.10)에 세전 이자 41,600원, 만기 금액 2,441,600원이 예상돼요(우대 금리 제외).\n출금 계좌 선택과 본인 확인(비밀번호)은 가입 화면에서 해요. 가입 화면으로 안내할까요?",
         "links": [], "suggestions": ["네", "아니요"], "context": {...}}

③ 요청 {"message": "네", "context": <②의 context>}
   응답 {"reply": "가입 화면으로 안내할게요. 금액과 기간은 채워 두었어요. 출금 계좌를 고르고 비밀번호로 본인 확인을 하면 가입돼요.",
         "links": [{"label": "상품 가입", "href": "#/products/prod_004/subscribe?amount=200000&months=12"}],
         "suggestions": [], "context": {...}}
```
- ①의 되묻는 말과 일반 답은 LLM(Gemini)이 써서 매번 조금 다를 수 있다. **②의 확인 질문과 ③의 답은 서버 코드가 만든다**(금액·금리·만기일은 P4 계산값).

**가입 준비가 안 될 때** — HTTP 는 200 이고, 이유가 `reply` 글로 전해진다(확인 질문으로 가지 않음)
| 상황 | 챗봇이 전하는 내용 (P4·P5 와 같은 코드·문장) |
|---|---|
| 상품·금액·기간이 빠짐 | 빠진 것만 되묻는다 |
| 금액·기간이 범위 밖 · 가입할 수 없는 상품 · 판매 중지 · 1인당 개수 초과 · 회원 상태 | P4·P5 의 `message` (예: 「예치금을 다시 확인해 주세요. (1,000,000원 이상)」) |
| 정상 입출금 계좌가 하나도 없음 | 「출금할 정상 입출금 계좌가 없어요. 먼저 계좌를 만들어 주세요.」 + 링크 `#/accounts/new` |
| 손님이 가입을 요청 | 로그인 안내 + 링크 `#/login` |
- 어느 계좌에서 낼지와 그 계좌 잔액은 챗봇이 아니라 가입 화면(P5·P6)이 본다.

**오류**
| HTTP | code | 언제 |
|---|---|---|
| 401 | `UNAUTHORIZED` · `SESSION_EXPIRED` | 쿠키는 있는데 세션이 없거나 끊김 |
| 403 | `SIGNUP_INCOMPLETE` | 가입 마무리 중 회원 |
| 422 | `VALIDATION_ERROR` | `message` 500자 초과 · `history` 21개 이상 · `role` 이 `user`/`assistant` 가 아님 · `text` 4000자 초과 · `thread_id` 모양이 틀림 |
| 503 | `CHAT_UNAVAILABLE` | Gemini 키 없음 · 한도 초과 · 네트워크 오류 — 「지금은 답변할 수 없어요. 잠시 뒤 다시 시도해 주세요.」(다른 API 는 정상) |

**알아 둘 제약**
- 회원 대화와 확인 대기는 **서버 메모리**에 있다. 서버를 다시 켜면 사라진다(그 뒤 「네」는 새 말로 처리되어 링크가 나오지 않는다 — 다시 말하면 다시 묻는다).
- 화면 `frontend/src/api.ts` 의 `ChatContext` 타입에는 아직 `thread_id` 칸이 없다. `ChatWidget` 이 `context` 를 통째로 돌려보내므로 동작에는 문제없다.

---

## 4. 변경 이력
| 날짜 | 내용 |
|---|---|
| 2026-11-10 | 처음 작성 — P1~P6 새로 만듦(규칙은 Serin 브랜치 `backend/app/crud.py` 를 옮김, 금리표 없는 상품 `NOT_SUBSCRIBABLE` 은 더함), P3 에 `documents` 칸, C1 에 `context.thread_id` · 가입 확인(`suggestions: ["네","아니요"]`, 가입 화면 링크) |
