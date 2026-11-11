"""예금·적금 상품과 가입 — 기획서 Part 3 PROD-F01~F08, 7장 API. 규칙은 Serin 브랜치 backend/app/crud.py 를 옮겼다.

    GET  /products                      목록 (판매 중만, q 이름 검색 · type · sort=rate 최고 금리 순)   로그인 없이
    GET  /products/recommended          홈 추천 2개                                                      로그인 없이
    GET  /products/{productId}          상세 (금리표 · 가입 조건 · 상품설명서 목록 · 약관 목록)             로그인 없이
    GET  /products/{productId}/terms/{termId}  상품 약관 본문 (「자세히 보기」)                              로그인 없이
    POST /products/{productId}/estimate 예상 이자 (금액 · 기간)                                            로그인 없이
    POST /products/{productId}/validate 가입 직전 검사 (계좌 · 잔액 · 1인당 개수)                           로그인
    POST /subscriptions                 가입 (본인 확인 SUBSCRIPTION · Idempotency-Key 필수)               로그인

[모의 규칙] (PROD-F05·F06)
- 이자: 단리 · 세전 · 원 미만 버림. 적용 금리는 기본 금리만(우대 조건 판정은 3차).
  예금 = 원금 × 연이율 × 개월/12 (일 단위 상품은 × 일수/365). 적금 = 납입마다 납입액 × 연이율 × 만기까지 꽉 찬 개월/12.
- 만기일: 가입일과 같은 날짜의 N개월 뒤(그 달에 없으면 말일). 일 단위 상품은 N일 뒤.
- 가입할 수 없는 상품: 금리표가 없는 상품(NOT_SUBSCRIBABLE), N일 적금(TERM_UNIT_NOT_SUPPORTED)(일 단위 적금 — 매일 자동 납입이 있어야 함. 자동이체가 생기면 연다).
- 적금 납입 방식(payment_type): FIXED 정액적립식(월 납입액 고정) / FREE 자유적립식(월 한도 안에서 자유) — 상품마다 고를 수 있는 값은
  rules_json.payment_types. 둘 다 되는 상품(prod_004·prod_032)은 가입할 때 꼭 골라야 한다. 계산·규칙은 app/savings.py.
- 가입: 계약(가입 당시 적용 금리 저장) + 적금 첫 회차 납입 기록 + 원장 출금(SUBSCRIPTION_PAYMENT)이 함께 성공하거나 함께 실패.
  다음 회차부터는 가입 상세의 추가 납입(POST /subscriptions/{id}/payments, app/routers/subscriptions.py).
  이체 한도는 세지 않는다(본인 계좌 사이 — 사용자 결정 2026-11-10). 새 가입은 ACTIVE 회원만(Part 1 7.3).
"""

from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.common import ledger
from app.common.idempotency import IdempotencyKey
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, account_not_found, not_found
from app.models import Account, AccountBalance, Product, ProductDocument, ProductRate, ProductRule, Subscription, SubscriptionPayment, User
from app.common.step_up import consume_step_up
from app.routers.signup import REPO_ROOT, read_terms_body
from app.routers.subscriptions import SubscriptionOut, _summary as subscription_summary
from app.rules import now_kst
from app.savings import FIXED, FREE, PAYMENT_TYPE_LABEL, allowed_payment_types, interest, maturity_date, months_between  # noqa: F401 (시험이 여기서 가져다 쓴다)
from app.security import new_id

router = APIRouter(tags=["products"])
ProductId = Annotated[str, Path(alias="productId", max_length=40)]
ProductType = Literal["TIME_DEPOSIT", "INSTALLMENT_SAVINGS"]
PaymentType = Literal["FIXED", "FREE"]
RECOMMENDED = ["prod_003", "prod_004"]  # 홈 추천 2개 (Serin 과 같음) — 조건 기반 추천(3차)이 생기면 바꾼다
NO_EARLY_TERMINATION = "중도해지 불가"  # product_rules.rules_json.early_termination 값


# ---- 응답 (frontend/src/api.ts 의 SummaryRaw · DetailRaw · EstimateRaw · ProductRaw 와 같은 모양) ----

class ProductSummaryOut(BaseModel):
    id: str
    name: str
    type: ProductType
    description: str | None
    base_rate: str | None  # 금리표의 가장 높은 기본 금리
    max_rate: str | None  # 기본 + 우대 최대
    term_label: str  # 예: 12개월 · 1~36개월 · 30~365일
    early_termination_allowed: bool


class RateOut(BaseModel):
    term_min: int
    term_max: int
    term_unit: Literal["MONTH", "DAY"]
    base_rate: str
    bonus_rate: str | None


class DocumentOut(BaseModel):
    id: str
    title: str
    source: str | None  # RAG 문서 이름(예: prod_004.pdf) — 챗봇 출처와 같은 값. 파일은 내려주지 않는다


class ProductTermOut(BaseModel):
    id: Literal["rider", "type", "basic"]
    title: str


class ProductTermDetailOut(ProductTermOut):
    source: str | None  # 본문 파일 앞머리의 source: (원본 PDF 이름)
    content: str | None  # Markdown 본문(앞머리·맨 위 # 제목 뺌)


class ProductDetailOut(ProductSummaryOut):
    verified_at: str | None
    rates: list[RateOut]
    min_amount: str | None  # 예금은 넣는 금액, 적금은 월 납입액
    max_amount: str | None
    amount_unit: str | None
    min_months: int | None
    max_months: int | None
    selectable_months: list[int] | None
    max_per_user: int | None
    min_days: int | None
    max_days: int | None
    eligibility: str | None
    notes: list[str]
    subscribable: bool
    payment_types: list[PaymentType]  # 적금의 납입 방식 — 예금은 빈 목록
    documents: list[DocumentOut]
    terms: list[ProductTermOut]  # 이 상품에 적용되는 약관 — 본문은 GET /products/{productId}/terms/{id}


class RecommendedOut(BaseModel):
    id: str
    name: str
    description: str
    max_rate: str
    term_label: str
    icon: Literal["safe", "coins"]


class EstimateIn(BaseModel):
    amount: str = Field(max_length=15, description="원. 예금은 넣는 금액, 적금은 월 납입액")
    months: int = Field(0, ge=0, le=600)
    days: int | None = Field(None, ge=0, le=3650, description="일 단위 상품(표지어음·CD)의 기간")


class EstimateOut(BaseModel):
    rate: str  # 적용 금리 (기본 금리)
    interest: str
    principal_total: str
    maturity_amount: str
    maturity_date: str  # YYYYMMDD
    first_payment: str  # 가입할 때 출금되는 돈 (예금 전액 · 적금 첫 회차)


class ValidateIn(EstimateIn):
    account_id: str = Field(max_length=40)
    payment_type: PaymentType | None = Field(None, description="적금만. 상품이 한 가지 방식뿐이면 비워도 된다")


class SubscribeIn(ValidateIn):
    product_id: str = Field(max_length=40)
    step_up_challenge_id: str = Field(max_length=40)


# ---- 조회 ----

def _rule(db, product_id: str) -> tuple[ProductRule | None, dict]:
    r = db.scalar(select(ProductRule).where(ProductRule.product_id == product_id))
    return r, (r.rules_json if r and r.rules_json else {})


def _rates(db, product_id: str) -> list[ProductRate]:
    return list(db.scalars(select(ProductRate).where(ProductRate.product_id == product_id)
                           .order_by(ProductRate.term_unit, ProductRate.term_min)))


def _rate_total(r: ProductRate) -> Decimal:
    return Decimal(r.base_rate) + Decimal(r.bonus_rate or 0)


def _day_unit(rates: list[ProductRate]) -> bool:
    return bool(rates) and rates[0].term_unit == "DAY"


def day_unit(db, product_id: str) -> bool:
    """일 단위 상품(표지어음·CD — 기간을 일수로 고름)인가. 챗봇의 가입 준비가 어떤 기간을 물을지 정할 때 쓴다."""
    return _day_unit(_rates(db, product_id))


def _subscribable(p: Product, rates: list[ProductRate]) -> bool:
    return bool(rates) and not (_day_unit(rates) and p.type == "INSTALLMENT_SAVINGS")


def _s(n: int | None) -> str | None:
    return None if n is None else str(n)


def _summary(p: Product, rates: list[ProductRate], rule: ProductRule | None, rj: dict) -> ProductSummaryOut:
    best = max(rates, key=_rate_total, default=None)
    unit = "일" if _day_unit(rates) else "개월"
    lo = rule.min_months if rule and rule.min_months else min((r.term_min for r in rates), default=None)
    hi = rule.max_months if rule and rule.max_months else max((r.term_max for r in rates), default=None)
    term = "" if lo is None else f"{lo}{unit} 이상" if hi is None else f"{lo}{unit}" if lo == hi else f"{lo}~{hi}{unit}"
    return ProductSummaryOut(
        id=p.id, name=p.name, type=p.type, description=p.description,
        base_rate=max((r.base_rate for r in rates), key=Decimal, default=None),
        max_rate=None if best is None else f"{_rate_total(best):.2f}",
        term_label=term, early_termination_allowed=rj.get("early_termination") != NO_EARLY_TERMINATION,
    )


def get_product_or_404(db, product_id: str) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise not_found("PRODUCT_NOT_FOUND", "상품을 찾을 수 없어요.")
    return p


def product_terms(p: Product) -> list[tuple[str, str, str]]:
    """이 상품에 적용되는 약관 (id, 제목, 본문 파일) — 먼저 적용되는 순서: 상품 특약 → 예금 종류 약관 → 예금거래기본약관.
    특약은 data/rag/riders/<상품 id>.md 가 있는 상품만(prod_009·011·013 은 없음). 특약 제1조가 나머지 둘을 따르라고 한다.
    거치식예금약관은 양도성예금증서·표지어음에도 적용된다(같은 약관 제1조 ③). 본문은 챗봇 RAG 와 같은 파일."""
    out = []
    rider = f"data/rag/riders/{p.id}.md"
    if (REPO_ROOT / rider).is_file():
        out.append(("rider", f"{p.name} 특약", rider))
    out.append(("type", "거치식예금 약관", "data/rag/terms/time_deposit_terms.md") if p.type == "TIME_DEPOSIT"
               else ("type", "적립식예금 약관", "data/rag/terms/installment_savings_terms.md"))
    out.append(("basic", "예금거래기본약관", "data/rag/terms/deposit_basic_terms.md"))
    return out


@router.get("/products", response_model=list[ProductSummaryOut])
def list_products(db: DB, q: Annotated[str | None, Query(max_length=40)] = None, type: ProductType | None = None,
                  sort: Literal["rate"] | None = None):
    stmt = select(Product).where(Product.status == "ON_SALE").order_by(Product.id)
    if type:
        stmt = stmt.where(Product.type == type)
    if q and q.strip():
        stmt = stmt.where(Product.name.contains(q.strip(), autoescape=True))
    out = [_summary(p, _rates(db, p.id), *_rule(db, p.id)) for p in db.scalars(stmt)]
    if sort == "rate":  # 최고 금리 높은 순, 금리표가 빈 상품은 맨 뒤
        out.sort(key=lambda s: Decimal(s.max_rate) if s.max_rate else Decimal(-1), reverse=True)
    return out


@router.get("/products/recommended", response_model=list[RecommendedOut])
def recommended_products(db: DB):
    out = []
    for p in db.scalars(select(Product).where(Product.id.in_(RECOMMENDED), Product.status == "ON_SALE").order_by(Product.id)):
        s = _summary(p, _rates(db, p.id), *_rule(db, p.id))
        out.append(RecommendedOut(id=p.id, name=p.name, description=p.description or "", max_rate=s.max_rate or "-",
                                  term_label=s.term_label, icon="safe" if p.type == "TIME_DEPOSIT" else "coins"))
    return out


@router.get("/products/{productId}", response_model=ProductDetailOut)
def product_detail(product_id: ProductId, db: DB):
    p = get_product_or_404(db, product_id)
    rates, (rule, rj) = _rates(db, p.id), _rule(db, p.id)
    deposit = p.type == "TIME_DEPOSIT"
    notes = [str(rj[k]) for k in ("interest_payment", "bonus_condition", "bonus_note", "term_note", "tax_free", "channel") if rj.get(k)]
    docs = db.scalars(select(ProductDocument).where(ProductDocument.product_id == p.id).order_by(ProductDocument.id))
    return ProductDetailOut(
        **_summary(p, rates, rule, rj).model_dump(), verified_at=p.verified_at,
        rates=[RateOut(term_min=r.term_min, term_max=r.term_max, term_unit=r.term_unit, base_rate=r.base_rate,
                       bonus_rate=r.bonus_rate) for r in rates],
        min_amount=_s(rule.min_amount if rule else None) if deposit else rj.get("monthly_min"),
        max_amount=_s(rule.max_amount if rule else None) if deposit else rj.get("monthly_max"),
        amount_unit=rj.get("amount_unit") if deposit else rj.get("monthly_unit"),
        min_months=rule.min_months if rule else None, max_months=rule.max_months if rule else None,
        selectable_months=rj.get("selectable_terms_months"), max_per_user=rule.max_per_user if rule else None,
        min_days=rj.get("term_days_min"), max_days=rj.get("term_days_max"),
        eligibility=rj.get("eligibility"), notes=notes, subscribable=_subscribable(p, rates),
        payment_types=allowed_payment_types(p.type, rj),
        documents=[DocumentOut(id=d.id, title=d.title, source=d.source_url) for d in docs],
        terms=[ProductTermOut(id=i, title=t) for i, t, _ in product_terms(p)],
    )


@router.get("/products/{productId}/terms/{termId}", response_model=ProductTermDetailOut)
def product_term(product_id: ProductId, term_id: Annotated[str, Path(alias="termId", max_length=20)], db: DB):
    """상품 약관 본문 — 상품 상세·가입 확인 화면의 「자세히 보기」. 공개 정보라 로그인 없이(가입 약관 GET /terms/{id} 와 같음)."""
    p = get_product_or_404(db, product_id)
    found = next((t for t in product_terms(p) if t[0] == term_id), None)
    if found is None:
        raise not_found("TERMS_NOT_FOUND", "약관을 찾을 수 없어요.")
    content, source = read_terms_body(found[2])
    return ProductTermDetailOut(id=found[0], title=found[1], source=source, content=content)


# ---- 예상 이자 (PROD-F05·F06) ----

def estimate(db, product_id: str, amount_s: str, months: int, days: int | None = None) -> EstimateOut:
    """금액·기간 검사 + 예상 이자. 챗봇의 가입 준비(app/agent.py)도 이 함수로 검사한다 — 규칙을 한 곳에만 둔다."""
    p = get_product_or_404(db, product_id)
    if p.status != "ON_SALE":
        raise ApiError(409, "PRODUCT_NOT_ON_SALE", "판매가 끝난 상품이에요.")
    rates, (rule, rj) = _rates(db, p.id), _rule(db, p.id)
    if not rates:  # 금리표가 빈 상품(prod_010·014·031·032) — 상세의 subscribable=false 와 같은 판정
        raise ApiError(422, "NOT_SUBSCRIBABLE", "금리표가 없어 지금은 앱에서 가입할 수 없는 상품이에요.")
    if not _subscribable(p, rates):
        raise ApiError(422, "TERM_UNIT_NOT_SUPPORTED", "N일 적금은 매일 자동 납입이 필요해 아직 앱에서 가입할 수 없어요.")
    if not (amount_s.isascii() and amount_s.isdecimal()) or int(amount_s) <= 0:
        raise ApiError(422, "AMOUNT_OUT_OF_RANGE", "금액을 숫자로 입력해 주세요.")
    amount, deposit, by_day = int(amount_s), p.type == "TIME_DEPOSIT", _day_unit(rates)

    if by_day:  # 표지어음·CD — 기간을 일수로 고른다
        lo, hi, term = rj.get("term_days_min"), rj.get("term_days_max"), days or 0
        if term < 1 or (lo and term < lo) or (hi and term > hi):
            raise ApiError(422, "TERM_OUT_OF_RANGE", f"가입 기간은 {lo or 1}~{hi}일 중에서 골라 주세요.")
    else:
        (lo, hi), term = (rule.min_months, rule.max_months) if rule else (None, None), months
        picks = rj.get("selectable_terms_months")
        if term < 1 or (lo and term < lo) or (hi and term > hi) or (picks and term not in picks):
            allowed = (", ".join(f"{m}개월" for m in picks) if picks else f"{hi}개월" if hi and lo == hi
                       else f"{lo or 1}~{hi}개월" if hi else f"{lo or 1}개월 이상")
            raise ApiError(422, "TERM_OUT_OF_RANGE", f"가입 기간은 {allowed} 중에서 골라 주세요.")
    rate = next((r for r in rates if r.term_min <= term <= r.term_max), None)
    if rate is None:
        raise ApiError(422, "RATE_NOT_FOUND", "이 기간에 맞는 금리가 없어 계산할 수 없어요.")

    a_min = rule.min_amount if deposit and rule else int(rj.get("monthly_min") or 0) or None
    a_max = rule.max_amount if deposit and rule else int(rj["monthly_max"]) if rj.get("monthly_max") else None
    unit = int(rj.get("amount_unit" if deposit else "monthly_unit") or 1)
    what = "예치금" if deposit else "월 납입액"
    if (a_min and amount < a_min) or (a_max and amount > a_max) or amount % unit:
        rng = f"{a_min or 1:,}원 이상" + (f" {a_max:,}원 이하" if a_max else "") + (f", {unit:,}원 단위" if unit > 1 else "")
        raise ApiError(422, "AMOUNT_OUT_OF_RANGE", f"{what}을 다시 확인해 주세요. ({rng})")

    today = now_kst().date()
    end = today + timedelta(days=term) if by_day else maturity_date(today, term)
    principal = amount if deposit else amount * term
    paid = [(today, amount)] if deposit else [(maturity_date(today, k), amount) for k in range(term)]
    i = interest(Decimal(rate.base_rate), deposit, by_day, today, end, paid)
    return EstimateOut(rate=rate.base_rate, interest=str(i), principal_total=str(principal),
                       maturity_amount=str(principal + i), maturity_date=end.strftime("%Y%m%d"), first_payment=str(amount))


@router.post("/products/{productId}/estimate", response_model=EstimateOut)
def post_estimate(product_id: ProductId, body: EstimateIn, db: DB):
    return estimate(db, product_id, body.amount, body.months, body.days)


# ---- 가입 검사 · 가입 (PROD-F07·F08) ----

def source_account(db, user_id: str, account_id: str) -> Account:
    a = db.get(Account, account_id)
    if a is None or a.user_id != user_id:  # 남의 계좌는 있는지도 알리지 않는다
        raise account_not_found()
    if a.account_type != "CHECKING":
        raise ApiError(422, "INVALID_ACCOUNT_TYPE", "입출금 계좌에서만 가입할 수 있어요.")
    if a.lifecycle_status != "ACTIVE":
        raise ApiError(422, "ACCOUNT_NOT_ACTIVE", "정지되었거나 해지된 계좌예요. 다른 입출금 계좌를 골라 주세요.")
    return a


def check_user(user: User) -> None:
    if user.status != "ACTIVE":  # RESTRICTED 는 정리 동작만 (Part 1 7.3)
        raise ApiError(403, "USER_NOT_ACTIVE", "지금 계정 상태에서는 가입할 수 없어요.")


def check_limit(db, user_id: str, product_id: str) -> None:
    rule, _ = _rule(db, product_id)
    if rule and rule.max_per_user:
        mine = db.scalar(select(func.count()).select_from(Subscription).where(
            Subscription.user_id == user_id, Subscription.product_id == product_id, Subscription.status == "ACTIVE"))
        if mine >= rule.max_per_user:
            raise ApiError(409, "SUBSCRIPTION_LIMIT_EXCEEDED", f"이 상품은 1인당 {rule.max_per_user}개까지 가입할 수 있어요.")


def payment_type(db, product_id: str, chosen: str | None) -> str | None:
    """적금의 납입 방식을 정한다. 예금은 None. 한 가지 방식뿐인 상품은 비워도 그것으로, 둘 다 되면 꼭 골라야 한다."""
    p = db.get(Product, product_id)
    allowed = allowed_payment_types(p.type, _rule(db, product_id)[1])
    if not allowed:
        return None
    if chosen is None:
        if len(allowed) > 1:
            raise ApiError(422, "PAYMENT_TYPE_REQUIRED", "정액적립식과 자유적립식 중 납입 방식을 골라 주세요.")
        return allowed[0]
    if chosen not in allowed:
        raise ApiError(422, "PAYMENT_TYPE_NOT_ALLOWED", f"이 상품은 {PAYMENT_TYPE_LABEL[allowed[0]]}만 가입할 수 있어요.")
    return chosen


def validate(db, user: User, product_id: str, b: ValidateIn, balance: int | None = None) -> tuple[EstimateOut, Account, str | None]:
    """가입 화면의 [확인]과 실제 가입이 똑같이 쓴다. balance: 가입 때는 잠근 잔액을 넘긴다.
    돌려주는 값: (예상 이자, 출금 계좌, 납입 방식 — 예금은 None)."""
    check_user(user)
    est = estimate(db, product_id, b.amount, b.months, b.days)
    kind = payment_type(db, product_id, b.payment_type)
    account = source_account(db, user.id, b.account_id)
    if balance is None:
        balance = db.scalar(select(AccountBalance.balance).where(AccountBalance.account_id == account.id)) or 0
    if balance < int(est.first_payment):
        raise ApiError(422, "INSUFFICIENT_BALANCE", f"잔액이 부족해요. (지금 잔액 {balance:,}원)")
    check_limit(db, user.id, product_id)
    return est, account, kind


@router.post("/products/{productId}/validate", response_model=EstimateOut)
def post_validate(product_id: ProductId, body: ValidateIn, login: CurrentLogin, db: DB):
    return validate(db, login.user, product_id, body)[0]


def _out(db, s: Subscription) -> SubscriptionOut:
    return SubscriptionOut(**subscription_summary(s, db.get(Product, s.product_id), db.get(Account, s.source_account_id)))


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def subscribe(body: SubscribeIn, login: CurrentLogin, db: DB,
              idempotency_key: IdempotencyKey):
    user = login.user
    key = f"{user.id}:{idempotency_key}"  # 다른 사람의 키와 섞이지 않게
    if done := db.scalar(select(Subscription).where(Subscription.idempotency_key == key)):
        if (done.product_id, done.source_account_id) != (body.product_id, body.account_id):
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 다른 내용으로 보낸 요청 번호예요. 처음부터 다시 가입해 주세요.")
        return _out(db, done)  # 같은 요청이 또 오면 처음 결과 그대로
    # 본인 확인을 먼저 써서 행 잠금을 잡는다 — 동시에 온 가입 두 개가 「1인당 N개」 검사를 함께 통과하지 않게
    consume_step_up(db, body.step_up_challenge_id, login, "SUBSCRIPTION")
    bal = ledger.lock_balances(db, [body.account_id]).get(body.account_id)
    est, account, kind = validate(db, user, body.product_id, body, bal.balance if bal else 0)

    p, now = db.get(Product, body.product_id), now_kst()
    deposit, pay = p.type == "TIME_DEPOSIT", int(est.first_payment)
    sub = Subscription(
        id=new_id("sub"), user_id=user.id, product_id=p.id, source_account_id=account.id,
        # 월 납입액은 정액적립식만 적는다 — 자유적립식·예금은 비워 둔다(더미 자유적금과 같은 규칙, savings.payment_type_of)
        principal=pay, monthly_amount=pay if kind == FIXED else None, applied_rate=est.rate,
        start_date=now.strftime("%Y%m%d"), maturity_date=est.maturity_date, status="ACTIVE", closed_at=None,
        idempotency_key=key,
    )
    db.add(sub)
    db.flush()  # 납입 기록이 가리킬 계약을 먼저 넣는다
    if not deposit:  # 적금은 가입 때 1회차만 낸다 — 2회차부터는 추가 납입(POST /subscriptions/{id}/payments)
        db.add(SubscriptionPayment(id=new_id("pay"), subscription_id=sub.id, paid_amount=pay, paid_at=now.strftime("%Y%m%d%H%M%S")))
    ledger.post(db, bal, "SUBSCRIPTION_PAYMENT", pay, now, display_name=p.name[:50])
    try:
        db.commit()
    except IntegrityError:  # 같은 키의 요청 두 개가 동시에 왔다 — 먼저 끝난 쪽 결과를 돌려준다
        db.rollback()
        done = db.scalar(select(Subscription).where(Subscription.idempotency_key == key))
        if done is None:
            raise ApiError(409, "CONFLICT_RETRY", "다른 요청과 겹쳤어요. 잠시 후 다시 시도해 주세요.")
        return _out(db, done)
    return _out(db, sub)
