"""내 예금·적금 가입 조회 · 적금 추가 납입 · 중도 해지 — 기획서 Part 3 PROD-F09·F10·F12, 7장 API.

    GET  /users/me/subscriptions                      내 가입 목록 (화면 「내 가입 상품」)
    GET  /users/me/subscriptions/{subscriptionId}     상세 + 납입 기록 + 이번 회차에 더 넣을 수 있는 돈
    POST /subscriptions/{subscriptionId}/payments     적금 추가 납입 (본인 확인 SUBSCRIPTION)
    POST /subscriptions/{subscriptionId}/terminate    중도 해지 (본인 확인 SUBSCRIPTION)

추가 납입 (PROD-F12, 사용자 결정 2026-11-10): 회차 = 가입일부터 한 달씩 자른 기간(app/savings.py current_period).
  정액적립식(FIXED) — 가입 때 정한 월 납입액만, 회차마다 한 번. 놓친 회차는 건너뛴다(나중에 몰아서 못 낸다).
  자유적립식(FREE)  — 회차 합계가 상품 월 한도(rules_json.monthly_max) 이하이면 몇 번이든.
  만기일부터는 낼 수 없다. 원장 출금(SUBSCRIPTION_PAYMENT) + 납입 기록 + 원금 누계는 함께 성공하거나 함께 실패.
  새로 돈을 넣는 일이라 회원 상태는 ACTIVE 만(Part 1 7.3). 같은 요청 두 번은 본인 확인 번호가 1회용이라 막힌다.
중도 해지 (PROD-F10): 원금을 출금 계좌로 돌려준다(모의 규칙: 중도 해지 이자 0원).
  원장 입금(SUBSCRIPTION_PAYOUT)과 계약 TERMINATED·closed_at 은 함께 성공하거나 함께 실패한다.
  거절: 중도해지 불가 상품(EARLY_TERMINATION_NOT_ALLOWED) · 진행 중이 아닌 계약 · 출금 계좌가 정상이 아님(정지 → 먼저 정지 해제).
  회원 상태: ACTIVE·RESTRICTED 가능(정리 동작, Part 1 7.3).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.common import ledger
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, Product, ProductRule, Subscription, SubscriptionPayment
from app.common.step_up import consume_step_up
from app.rules import now_kst
from app.savings import FIXED, current_period, payment_type_of, ymd
from app.common.naming import Money
from app.security import new_id

router = APIRouter(tags=["subscriptions"])
SubscriptionId = Annotated[str, Path(alias="subscriptionId")]
NO_EARLY_TERMINATION = "중도해지 불가"  # product_rules.rules_json.early_termination 값 (Part 3)


class SubscriptionOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_type: str
    payment_type: Literal["FIXED", "FREE"] | None  # 적금의 납입 방식 — 예금은 null
    account_number: str
    principal: Money
    monthly_amount: Money | None
    applied_rate: str
    start_date: str  # YYYYMMDD
    maturity_date: str
    status: str


class PaymentOut(BaseModel):
    amount: Money
    paid_at: str  # YYYYMMDDHHmmss (더미 그대로)


class SubscriptionDetailOut(SubscriptionOut):
    early_termination_allowed: bool
    account_status: str
    payments: list[PaymentOut]
    payable: bool  # 지금 추가 납입을 할 수 있는가 (진행 중 적금 · 만기 전 · 출금 계좌 정상 · 이번 회차에 남은 돈이 있음)
    monthly_max: Money | None  # 이번 회차에 넣을 수 있는 최대 — 정액은 월 납입액, 자유는 상품 월 한도(없으면 null)
    paid_this_month: Money  # 이번 회차(가입일 기준 한 달)에 넣은 돈
    next_period_start: str | None  # 다음 회차가 시작하는 날 YYYYMMDD — 적금만


def _rows(db, user_id: str, subscription_id: str | None = None):
    q = (select(Subscription, Product, Account, ProductRule.rules_json)
         .join(Product, Product.id == Subscription.product_id)
         .join(Account, Account.id == Subscription.source_account_id)
         .outerjoin(ProductRule, ProductRule.product_id == Product.id)
         .where(Subscription.user_id == user_id))
    if subscription_id is not None:
        q = q.where(Subscription.id == subscription_id)
    return db.execute(q.order_by(Subscription.id)).all()


def _summary(s: Subscription, p: Product, a: Account) -> dict:
    return dict(id=s.id, product_id=p.id, product_name=p.name, product_type=p.type,
                payment_type=payment_type_of(p.type, s.monthly_amount), account_number=a.resAccountDisplay,
                principal=s.principal or 0, monthly_amount=s.monthly_amount, applied_rate=s.applied_rate,
                start_date=s.start_date, maturity_date=s.maturity_date, status=s.status)


def _early_allowed(rules: dict | None) -> bool:
    return (rules or {}).get("early_termination") != NO_EARLY_TERMINATION


def _period_limit(s: Subscription, rules: dict | None) -> int | None:
    """이번 회차에 넣을 수 있는 최대 금액 — 정액은 월 납입액, 자유는 상품 월 한도(없으면 제한 없음 → None)."""
    if s.monthly_amount is not None:
        return s.monthly_amount
    cap = (rules or {}).get("monthly_max")
    return int(cap) if cap else None


def _payments(db, subscription_id: str) -> list[SubscriptionPayment]:
    return list(db.scalars(select(SubscriptionPayment).where(SubscriptionPayment.subscription_id == subscription_id)
                           .order_by(SubscriptionPayment.paid_at.desc(), SubscriptionPayment.id.desc())))


def _paid_in_period(payments: list[SubscriptionPayment], s: Subscription, today) -> tuple[int, str]:
    """(이번 회차에 넣은 돈, 다음 회차 시작일 YYYYMMDD)."""
    lo, hi = current_period(ymd(s.start_date), today)
    paid = sum(x.paid_amount for x in payments if lo <= ymd(x.paid_at) < hi)
    return paid, hi.strftime("%Y%m%d")


def _detail(db, user_id: str, subscription_id: str) -> SubscriptionDetailOut:
    rows = _rows(db, user_id, subscription_id)
    if not rows:
        raise not_found("SUBSCRIPTION_NOT_FOUND", "가입 상품을 찾을 수 없어요.")
    s, p, a, rules = rows[0]
    payments = _payments(db, s.id)
    savings, today = p.type == "INSTALLMENT_SAVINGS", now_kst().date()
    paid, next_start = _paid_in_period(payments, s, today) if savings else (0, None)
    limit = _period_limit(s, rules) if savings else None
    payable = (savings and s.status == "ACTIVE" and today < ymd(s.maturity_date) and a.lifecycle_status == "ACTIVE"
               and (limit is None or paid < limit))
    return SubscriptionDetailOut(
        **_summary(s, p, a), early_termination_allowed=_early_allowed(rules), account_status=a.lifecycle_status,
        payments=[PaymentOut(amount=x.paid_amount, paid_at=x.paid_at) for x in payments], payable=payable,
        monthly_max=limit, paid_this_month=paid, next_period_start=next_start)


@router.get("/users/me/subscriptions", response_model=list[SubscriptionOut])
def list_my_subscriptions(db: DB, user_id: CurrentUserId):
    return [SubscriptionOut(**_summary(s, p, a)) for s, p, a, _ in _rows(db, user_id)]


@router.get("/users/me/subscriptions/{subscriptionId}", response_model=SubscriptionDetailOut)
def get_my_subscription(subscription_id: SubscriptionId, db: DB, user_id: CurrentUserId):
    return _detail(db, user_id, subscription_id)


class StepUpBody(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


class PaymentIn(StepUpBody):
    amount: str = Field(max_length=15, description="원. 넣을 돈")


def _lock_own(db, user_id: str, subscription_id: str) -> Subscription:
    """본인 계약을 잠가서 가져온다 — 남의 계약은 있는지도 알리지 않는다(404). 같은 계약에 동시에 온 요청은 줄을 선다."""
    s = db.scalar(select(Subscription).where(Subscription.id == subscription_id, Subscription.user_id == user_id)
                  .with_for_update())
    if s is None:
        raise not_found("SUBSCRIPTION_NOT_FOUND", "가입 상품을 찾을 수 없어요.")
    return s


@router.post("/subscriptions/{subscriptionId}/payments", response_model=SubscriptionDetailOut, status_code=201)
def pay_installment(subscription_id: SubscriptionId, body: PaymentIn, login: CurrentLogin, db: DB):
    from app.routers.products import check_user  # products 가 이 파일을 import 하므로 함수 안에서 가져온다

    user_id = login.user.id
    s = _lock_own(db, user_id, subscription_id)
    consume_step_up(db, body.step_up_challenge_id, login, "SUBSCRIPTION")
    check_user(login.user)  # 새로 돈을 넣는 일 — ACTIVE 회원만
    if s.status != "ACTIVE":
        raise ApiError(409, "SUBSCRIPTION_NOT_ACTIVE", "이미 끝난 가입 상품이에요.")
    p = db.get(Product, s.product_id)
    if p.type != "INSTALLMENT_SAVINGS":
        raise ApiError(422, "NOT_INSTALLMENT_SAVINGS", "예금에는 돈을 더 넣을 수 없어요. 적금만 추가로 넣을 수 있어요.")
    now = now_kst()
    today = now.date()
    if today >= ymd(s.maturity_date):
        raise ApiError(409, "PAYMENT_PERIOD_ENDED", "만기일이 되어 더 넣을 수 없어요.")

    amount_s = body.amount
    if not (amount_s.isascii() and amount_s.isdecimal()) or int(amount_s) <= 0:
        raise ApiError(422, "AMOUNT_OUT_OF_RANGE", "넣을 돈을 숫자로 입력해 주세요.")
    amount = int(amount_s)
    rules = db.scalar(select(ProductRule.rules_json).where(ProductRule.product_id == s.product_id)) or {}
    payments = _payments(db, s.id)
    paid, next_start = _paid_in_period(payments, s, today)
    next_day = f"{int(next_start[4:6])}월 {int(next_start[6:8])}일"
    if payment_type_of(p.type, s.monthly_amount) == FIXED:
        if paid > 0:
            raise ApiError(409, "ALREADY_PAID_THIS_PERIOD", f"이번 회차는 이미 넣었어요. 다음 회차는 {next_day}부터 넣을 수 있어요.")
        if amount != s.monthly_amount:
            raise ApiError(422, "AMOUNT_OUT_OF_RANGE", f"정액적립식은 가입 때 정한 {s.monthly_amount:,}원만 넣을 수 있어요.")
    else:
        lo, unit, cap = int(rules.get("monthly_min") or 1), int(rules.get("monthly_unit") or 1), _period_limit(s, rules)
        if amount < lo or amount % unit:
            raise ApiError(422, "AMOUNT_OUT_OF_RANGE",
                           f"한 번에 {lo:,}원 이상" + (f", {unit:,}원 단위로" if unit > 1 else "") + " 넣어 주세요.")
        if cap is not None and paid + amount > cap:
            raise ApiError(422, "MONTHLY_LIMIT_EXCEEDED",
                           f"이번 회차에는 {max(cap - paid, 0):,}원까지 더 넣을 수 있어요. (회차 한도 {cap:,}원, {next_day}부터 새 회차)")

    bal = ledger.lock_balances(db, [s.source_account_id]).get(s.source_account_id)
    account = db.get(Account, s.source_account_id)
    if bal is None or account.lifecycle_status != "ACTIVE":
        raise ApiError(422, "ACCOUNT_NOT_ACTIVE", "출금 계좌가 정상이 아니에요. 계좌 정지를 먼저 풀어 주세요.")
    if bal.balance < amount:
        raise ApiError(422, "INSUFFICIENT_BALANCE", f"잔액이 부족해요. (지금 잔액 {bal.balance:,}원)")

    db.add(SubscriptionPayment(id=new_id("pay"), subscription_id=s.id, paid_amount=amount,
                               paid_at=now.strftime("%Y%m%d%H%M%S")))
    s.principal = (s.principal or 0) + amount  # principal 은 적금의 납입 누계 (Part 3 6장)
    ledger.post(db, bal, "SUBSCRIPTION_PAYMENT", amount, now, display_name=p.name[:50])
    db.commit()
    return _detail(db, user_id, s.id)


@router.post("/subscriptions/{subscriptionId}/terminate", response_model=SubscriptionDetailOut)
def terminate_subscription(subscription_id: SubscriptionId, body: StepUpBody, login: CurrentLogin, db: DB):
    user_id = login.user.id
    s = _lock_own(db, user_id, subscription_id)
    consume_step_up(db, body.step_up_challenge_id, login, "SUBSCRIPTION")
    if s.status != "ACTIVE":
        raise ApiError(409, "SUBSCRIPTION_NOT_ACTIVE", "이미 끝난 가입 상품이에요.")
    rules = db.scalar(select(ProductRule.rules_json).where(ProductRule.product_id == s.product_id))
    if not _early_allowed(rules):
        raise ApiError(409, "EARLY_TERMINATION_NOT_ALLOWED", "이 상품은 중도 해지할 수 없어요. 만기까지 기다려 주세요.")

    bal = ledger.lock_balances(db, [s.source_account_id]).get(s.source_account_id)
    account = db.get(Account, s.source_account_id)
    if bal is None or account.lifecycle_status != "ACTIVE":
        raise ApiError(409, "ACCOUNT_NOT_ACTIVE", "돈을 돌려받을 출금 계좌가 정상이 아니에요. 계좌 정지를 먼저 풀어 주세요.")

    now = now_kst()
    if s.principal:  # 모의 규칙: 중도 해지 이자 0원 — 원금만
        product_name = db.scalar(select(Product.name).where(Product.id == s.product_id))
        ledger.post(db, bal, "SUBSCRIPTION_PAYOUT", s.principal, now, display_name=product_name[:50])
    s.status, s.closed_at = "TERMINATED", now.strftime("%Y%m%d")
    db.commit()
    return _detail(db, user_id, s.id)
