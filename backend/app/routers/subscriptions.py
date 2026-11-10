"""내 예금·적금 가입 조회와 중도 해지 — 기획서 Part 3 PROD-F10, 7장 API.

    GET  /users/me/subscriptions                      내 가입 목록 (화면 「내 가입 상품」)
    GET  /users/me/subscriptions/{subscriptionId}     상세 + 납입 기록
    POST /subscriptions/{subscriptionId}/terminate    중도 해지 (본인 확인 SUBSCRIPTION)

중도 해지 (PROD-F10): 원금을 출금 계좌로 돌려준다(모의 규칙: 중도 해지 이자 0원).
원장 입금(SUBSCRIPTION_PAYOUT)과 계약 TERMINATED·closed_at 은 함께 성공하거나 함께 실패한다.
거절: 중도해지 불가 상품(EARLY_TERMINATION_NOT_ALLOWED) · 진행 중이 아닌 계약 · 출금 계좌가 정상이 아님(정지 → 먼저 정지 해제).
회원 상태: ACTIVE·RESTRICTED 가능(정리 동작, Part 1 7.3).
"""

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import ledger
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, Product, ProductRule, Subscription, SubscriptionPayment
from app.routers.auth import consume_step_up
from app.rules import now_kst
from app.schemas import Money

router = APIRouter(tags=["subscriptions"])
SubscriptionId = Annotated[str, Path(alias="subscriptionId")]
NO_EARLY_TERMINATION = "중도해지 불가"  # product_rules.rules_json.early_termination 값 (Part 3)


class SubscriptionOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_type: str
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
    payable: bool  # shortcut: 추가 납입 API(POST /subscriptions/{id}/payments)가 없어 늘 false, 만들면 계산
    monthly_max: Money | None
    paid_this_month: Money


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
    return dict(id=s.id, product_id=p.id, product_name=p.name, product_type=p.type, account_number=a.resAccountDisplay,
                principal=s.principal or 0, monthly_amount=s.monthly_amount, applied_rate=s.applied_rate,
                start_date=s.start_date, maturity_date=s.maturity_date, status=s.status)


def _early_allowed(rules: dict | None) -> bool:
    return (rules or {}).get("early_termination") != NO_EARLY_TERMINATION


def _detail(db, user_id: str, subscription_id: str) -> SubscriptionDetailOut:
    rows = _rows(db, user_id, subscription_id)
    if not rows:
        raise not_found("SUBSCRIPTION_NOT_FOUND", "가입 상품을 찾을 수 없어요.")
    s, p, a, rules = rows[0]
    payments = db.scalars(select(SubscriptionPayment).where(SubscriptionPayment.subscription_id == s.id)
                          .order_by(SubscriptionPayment.paid_at.desc())).all()
    this_month = now_kst().strftime("%Y%m")
    return SubscriptionDetailOut(
        **_summary(s, p, a), early_termination_allowed=_early_allowed(rules), account_status=a.lifecycle_status,
        payments=[PaymentOut(amount=x.paid_amount, paid_at=x.paid_at) for x in payments], payable=False,
        monthly_max=None, paid_this_month=sum(x.paid_amount for x in payments if x.paid_at.startswith(this_month)))


@router.get("/users/me/subscriptions", response_model=list[SubscriptionOut])
def list_my_subscriptions(db: DB, user_id: CurrentUserId):
    return [SubscriptionOut(**_summary(s, p, a)) for s, p, a, _ in _rows(db, user_id)]


@router.get("/users/me/subscriptions/{subscriptionId}", response_model=SubscriptionDetailOut)
def get_my_subscription(subscription_id: SubscriptionId, db: DB, user_id: CurrentUserId):
    return _detail(db, user_id, subscription_id)


class StepUpBody(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


@router.post("/subscriptions/{subscriptionId}/terminate", response_model=SubscriptionDetailOut)
def terminate_subscription(subscription_id: SubscriptionId, body: StepUpBody, login: CurrentLogin, db: DB):
    user_id = login.user.id
    s = db.scalar(select(Subscription).where(Subscription.id == subscription_id, Subscription.user_id == user_id)
                  .with_for_update())
    if s is None:
        raise not_found("SUBSCRIPTION_NOT_FOUND", "가입 상품을 찾을 수 없어요.")
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
