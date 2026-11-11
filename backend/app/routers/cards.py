"""내 카드 조회 · 해지 · 대금 결제 — 기획서 Part 4 1-1 카드 목록 조회(CARD-F01~F04) · F09(해지, 1-3) · F07(대금 결제, 1-7).

    GET  /cards                              내 카드 모아보기 (해지한 카드 빼고, 1-1-1)
    GET  /cards/{cardId}                     상세 + 혜택 + 청구서 (해지한 카드도 기록으로 볼 수 있음, 1-1-2)
    GET  /cards/{cardId}/transactions        이용 내역 (달·업종·일시불/할부로 거르기, 1-1-3)
    GET  /card-bills · /card-bills/{billId}  결제 캘린더 · 청구서 상세 — routers/card_bills.py (1-1-4)
    GET  /cards/{cardId}/termination-check   해지 전 확인 (1-3 표)
    POST /cards/{cardId}/terminate           해지 (본인 확인 CARD_TERMINATION) — 확정·연체 청구서가 있으면 거절
    POST /cards/{cardId}/payments            지금 결제하기 (본인 확인 CARD_MANAGEMENT)
    PATCH /cards/{cardId}/linked-account     결제·출금 계좌 바꾸기 (본인 확인 CARD_MANAGEMENT, CARD-F08 1-2 「카드 관리」)

로그인한 회원의 카드만 — 모든 조회는 user_cards.user_id = 로그인 회원으로 거른다. 남의 카드·없는 카드는 똑같이 404
CARD_NOT_FOUND (계좌 ACCOUNT_NOT_FOUND 와 같은 규칙, tests/test_cards.py).

카드 돈 계산 (신용카드만 — 체크카드는 쓸 때 바로 계좌에서 빠져 낼 돈이 없다)
    쓴 돈   = card_transactions 의 (amount − canceled_amount) 합
    청구된 돈 = card_bills.total_amount 합,  낸 돈 = card_bills.paid_amount 합
    이번 기간 사용액(아직 청구서 없음) = 쓴 돈 − 청구된 돈
    체크카드의 「이번 기간」은 이번 달 1일~오늘 쓴 돈(취소 뺌)이다 — 낼 돈이 아니라 목록에 보여 줄 금액 (사용자 결정 2026-11-10)
    아직 낼 돈 = 쓴 돈 − 낸 돈   ← 회원 탈퇴 ③이 이게 0원인지 본다 (사용자 결정 2026-11-09, Q5)

지금 결제하기 (사용자 결정 2026-11-09, Q4·Q5): 기획서는 연체(OVERDUE)만 「지금 결제하기」였지만
확정(CONFIRMED) 청구서도 결제일 전에 낼 수 있게 했다. 해지한 카드는 이번 기간 사용액까지 미리 낸다(더 쓸 수 없으므로 금액이 확정).
결제 계좌 잔액이 모자라면 한 푼도 빼지 않고 거절한다(전액 아니면 출금 안 함, 1-7).
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.common import ledger
from app.card_benefits import benefits_for, spent_between
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, not_found
from app.models import (
    Account,
    AccountBalance,
    BillingCycleRule,
    CardBill,
    CardBillItem,
    CardCompany,
    CardManagementLog,
    CardPoint,
    CardProduct,
    CardTermination,
    CardTransaction,
    Category,
    Merchant,
    Notification,
    RecurringPayment,
    UserCard,
    UserCardStatusHistory,
)
from app.common.step_up import consume_step_up
from app.rules import now_kst
from app.common.naming import KstDatetime, Money
from app.security import new_id

router = APIRouter(tags=["cards"])
CardId = Annotated[str, Path(alias="cardId")]
UNPAID_BILL = ("CONFIRMED", "OVERDUE")  # 해지를 막는 청구서 (1-3)


def card_not_found() -> ApiError:
    return not_found("CARD_NOT_FOUND", "카드를 찾을 수 없어요.")


# --- 계산 -------------------------------------------------------------------------------------
def _add_month(y: int, m: int, k: int) -> tuple[int, int]:
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1


def _day(ym: tuple[int, int], d: int) -> date:
    return date(*ym, min(d, calendar.monthrange(*ym)[1]))  # 99 = 말일, 31일이 없는 달은 말일


def current_period(db, company_id: str, payment_day: int | None, today: date) -> tuple[date, date, date | None]:
    """오늘이 속한 이용 기간과 그 결제일 (billing_cycle_rules, 1-4). 규칙이 없으면(체크카드 등) 이번 달."""
    rule = payment_day and db.scalar(select(BillingCycleRule).where(
        BillingCycleRule.card_company_id == company_id, BillingCycleRule.payment_day == payment_day))
    if rule:
        for k in range(3):  # 이번 달 ~ 두 달 뒤 결제분 중 오늘이 들어 있는 기간
            pay = _add_month(today.year, today.month, k)
            start = _day(_add_month(*pay, rule.start_month_offset), rule.start_day)
            end = _day(_add_month(*pay, rule.end_month_offset), rule.end_day)
            if start <= today <= end:
                return start, end, _day(pay, payment_day)
    return today.replace(day=1), _day((today.year, today.month), 31), None


@dataclass
class CardMoney:
    charged: int
    billed: int
    paid: int
    unpaid_confirmed: int  # 확정·연체 청구서 중 안 낸 돈 (해지를 막음)

    @property
    def unbilled(self) -> int:  # 이번 기간 사용액(청구서가 아직 없는 돈)
        return max(self.charged - self.billed, 0)

    @property
    def owed(self) -> int:  # 아직 낼 돈 전부
        return max(self.charged - self.paid, 0)


def card_money(db, card: UserCard, card_type: str) -> CardMoney:
    if card_type != "CREDIT":
        return CardMoney(charged=0, billed=0, paid=0, unpaid_confirmed=0)
    charged = db.scalar(select(func.coalesce(func.sum(CardTransaction.amount - CardTransaction.canceled_amount), 0))
                        .where(CardTransaction.user_card_id == card.id))
    billed, paid, unpaid = db.execute(select(
        func.coalesce(func.sum(CardBill.total_amount), 0), func.coalesce(func.sum(CardBill.paid_amount), 0),
        func.coalesce(func.sum(CardBill.total_amount - CardBill.paid_amount).filter(CardBill.status.in_(UNPAID_BILL)), 0),
    ).where(CardBill.user_card_id == card.id)).one()
    return CardMoney(charged=charged, billed=billed, paid=paid, unpaid_confirmed=unpaid)


# --- 응답 모양 (화면 frontend/src/api.ts CardRaw · CardDetailRaw · TerminationRaw) -----------------------
class CardOut(BaseModel):
    id: str
    name: str
    product_name: str
    product_summary: str | None  # 한 줄 혜택 요약 (card_products.summary)
    company_name: str
    card_type: str
    number: str
    last4: str
    status: str
    credit_limit: Money | None
    available_limit: Money | None
    linked_account_id: str | None
    linked_account_number: str | None
    linked_account_name: str | None
    period_start: date
    period_end: date
    period_spent: Money
    unpaid_amount: Money
    next_payment_date: date | None


class BillOut(BaseModel):
    id: str | None  # 이번 기간(아직 저장 안 된 청구서)은 null
    card_id: str
    card_name: str
    billing_ym: str
    usage_start: date
    usage_end: date
    payment_date: date
    total_amount: Money
    paid_amount: Money
    status: str
    account_number: str | None
    low_balance: bool
    # 잔액 채우기 제안 (Part 5 TRX-F12, 사용자 결정 2026-11-10) — 결제 계좌와 그 결제일까지 모자란 돈
    account_id: str | None = None
    shortfall: Money = 0


class LimitGroupOut(BaseModel):
    name: str
    monthly_limit: Money


class BenefitOut(BaseModel):
    """혜택 한 줄 (app/card_benefits.py). title 「카페 55% 할인」, conditions 「스타벅스·폴바셋에서만」…"""
    id: str
    category: str
    benefit_type: str
    value_type: str
    value: str
    title: str
    conditions: list[str]
    monthly_limit: Money | None  # 이 혜택만의 월 한도
    limit_group: LimitGroupOut | None  # 여러 혜택이 함께 쓰는 통합 월 한도
    achieved: bool  # 지난달(분기) 실적으로 지금 받을 수 있는지


class PerformanceOut(BaseModel):
    """실적 — period MONTH 는 지난달, QUARTER 는 지난 분기"""
    period: str
    spent: Money
    tier_level: int | None  # 넘은 구간 (못 넘었으면 null)
    tier_min_spend: Money  # 보여 주는 혜택의 구간 하한
    next_min_spend: Money | None  # 다음 구간 하한 (가장 높은 구간이면 null)


class CardDetailOut(CardOut):
    issued_at: datetime
    expires_at: date | None
    payment_day: int | None
    annual_fee: Money
    next_annual_fee_date: date | None
    used_amount: Money | None
    benefits: list[BenefitOut]
    performance: list[PerformanceOut]
    bills: list[BillOut]
    payment_day_locked: bool


def _load(db, user_id: str, card_id: str | None = None, include_terminated: bool = True):
    q = (select(UserCard, CardProduct, CardCompany.name, Account)
         .join(CardProduct, CardProduct.id == UserCard.card_product_id)
         .join(CardCompany, CardCompany.id == CardProduct.card_company_id)
         .outerjoin(Account, Account.id == UserCard.linked_account_id)
         .where(UserCard.user_id == user_id, UserCard.source == "TOSS_ISSUED"))
    if card_id is not None:
        q = q.where(UserCard.id == card_id)
    if not include_terminated:
        q = q.where(UserCard.status != "TERMINATED")
    return db.execute(q.order_by(UserCard.id)).all()


def _card_out(db, c: UserCard, p: CardProduct, company: str, a: Account | None, today: date) -> dict:
    m = card_money(db, c, p.card_type)
    start, end, pay_date = current_period(db, p.card_company_id, c.payment_day, today)
    next_due = db.scalar(select(func.min(CardBill.payment_date)).where(
        CardBill.user_card_id == c.id, CardBill.status.in_(UNPAID_BILL)))
    # 신용: 이번 기간 사용액(청구 전) / 체크: 이번 달 1일~오늘 쓴 돈 (체크는 낼 돈이 없어 card_money 가 0)
    if p.card_type == "CREDIT":
        spent = m.unbilled
    else:
        spent = spent_between(db, c.id, start, today + timedelta(days=1), counted_only=False)
    return dict(
        id=c.id, name=c.nickname or p.name, product_name=p.name, product_summary=p.summary, company_name=company,
        card_type=p.card_type,
        number=c.card_number_masked, last4=c.last4 or c.card_number_masked[-4:], status=c.status,
        credit_limit=c.credit_limit, available_limit=None if c.credit_limit is None else max(c.credit_limit - m.owed, 0),
        linked_account_id=c.linked_account_id, linked_account_number=a.resAccountDisplay if a else None,
        linked_account_name=(a.resAccountNickName or a.resAccountName) if a else None,
        period_start=start, period_end=end, period_spent=spent, unpaid_amount=m.unpaid_confirmed,
        next_payment_date=next_due or (pay_date if m.unbilled else None))


@router.get("/cards", response_model=list[CardOut])
def list_cards(db: DB, user_id: CurrentUserId):
    today = now_kst().date()
    return [CardOut(**_card_out(db, *row, today)) for row in _load(db, user_id, include_terminated=False)]


def _schedule_bill(db, c: UserCard, p: CardProduct, base: dict, today: date) -> BillOut | None:
    """이번 기간 — 쓰는 중(SCHEDULED)이라 아직 저장 전인 청구서. 신용카드에 이번 기간 사용액이 있을 때만"""
    if p.card_type != "CREDIT" or not base["period_spent"] or not c.payment_day:
        return None
    pay = current_period(db, p.card_company_id, c.payment_day, today)[2] or base["period_end"]
    return BillOut(id=None, card_id=c.id, card_name=base["name"], billing_ym=pay.strftime("%Y%m"),
                   usage_start=base["period_start"], usage_end=base["period_end"], payment_date=pay,
                   total_amount=base["period_spent"], paid_amount=0, status="SCHEDULED",
                   account_number=base["linked_account_number"], low_balance=False)


def mark_low_balance(db, bills: list[BillOut], account_of: dict[str, str | None]) -> None:
    """결제 계좌 잔액 < 그 결제일까지 낼 돈이면 low_balance (1-1-4 「잔액 부족 경고」).
    같은 계좌에서 빠질 청구서(카드 여러 장)를 결제일 순으로 쌓아 더한다 — 앞 청구서가 먼저 잔액을 쓴다."""
    due = sorted((b for b in bills if b.status != "PAID" and b.total_amount > b.paid_amount),
                 key=lambda b: (b.payment_date, b.card_id))
    accounts = {account_of[b.card_id] for b in due} - {None}
    balance = dict(db.execute(select(AccountBalance.account_id, AccountBalance.balance)
                              .where(AccountBalance.account_id.in_(accounts))).all()) if accounts else {}
    for b in bills:
        b.account_id = account_of[b.card_id]
    running: dict[str, int] = {}
    for b in due:
        acc = account_of[b.card_id]
        if acc is None:
            continue
        running[acc] = running.get(acc, 0) + b.total_amount - b.paid_amount
        b.shortfall = max(running[acc] - balance.get(acc, 0), 0)
        b.low_balance = b.shortfall > 0


def bills_of_user(db, user_id: str, today: date) -> list[BillOut]:
    """내 모든 카드의 청구서(해지한 카드 것도 — 낼 돈이 남을 수 있음) + 이번 기간 청구서, 잔액 부족 표시까지"""
    out, account_of = [], {}
    for c, p, company, a in _load(db, user_id):
        base = _card_out(db, c, p, company, a, today)
        account_of[c.id] = c.linked_account_id
        sched = _schedule_bill(db, c, p, base, today)
        if sched is not None:
            out.append(sched)
        out += [BillOut(id=b.id, card_id=c.id, card_name=base["name"], billing_ym=b.billing_ym,
                        usage_start=b.usage_start, usage_end=b.usage_end, payment_date=b.payment_date,
                        total_amount=b.total_amount, paid_amount=b.paid_amount, status=b.status,
                        account_number=base["linked_account_number"], low_balance=False)
                for b in db.scalars(select(CardBill).where(CardBill.user_card_id == c.id)
                                    .order_by(CardBill.billing_ym.desc()))]
    mark_low_balance(db, out, account_of)
    return out


def payment_day_locked(db, card_id: str, today: date) -> bool:
    """확정 청구서(CONFIRMED)의 결제일 당일 — 그날 출금과 겹치지 않게 결제 계좌를 못 바꾼다(1-2 「카드 관리」)."""
    return db.scalar(select(CardBill.id).where(CardBill.user_card_id == card_id, CardBill.status == "CONFIRMED",
                                               CardBill.payment_date == today).limit(1)) is not None


def _detail(db, user_id: str, card_id: str) -> CardDetailOut:
    rows = _load(db, user_id, card_id)
    if not rows:
        raise card_not_found()
    c, p, company, a = rows[0]
    today = now_kst().date()
    base = _card_out(db, c, p, company, a, today)
    bills = [b for b in bills_of_user(db, user_id, today) if b.card_id == c.id]  # 잔액 부족은 다른 카드 청구서까지 보고 정함
    benefits, standing = benefits_for(db, c.id, p.id, today)
    performance = [PerformanceOut(period=st.period, spent=st.spent, tier_level=st.tier.tier_level if st.achieved else None,
                                  tier_min_spend=st.tier.min_spend,
                                  next_min_spend=st.next_tier.min_spend if st.next_tier else None)
                   for st in standing.values()]
    m = card_money(db, c, p.card_type)
    return CardDetailOut(
        **base, issued_at=c.issued_at or c.created_at, expires_at=c.expires_at, payment_day=c.payment_day,
        annual_fee=c.annual_fee_amount, next_annual_fee_date=c.next_annual_fee_date,
        used_amount=m.owed if c.credit_limit is not None else None, benefits=benefits, performance=performance,
        bills=bills, payment_day_locked=payment_day_locked(db, c.id, today))


@router.get("/cards/{cardId}", response_model=CardDetailOut)
def get_card(card_id: CardId, db: DB, user_id: CurrentUserId):
    return _detail(db, user_id, card_id)


# --- 이용 내역 (CARD-F03, 1-1-3) ------------------------------------------------------------------
class CardTransactionOut(BaseModel):
    id: str
    approval_no: str
    transacted_at: KstDatetime
    merchant: str
    category: str
    category_code: str
    amount: Money
    canceled_amount: Money
    status: str
    installment_months: int  # 0 = 일시불
    is_overseas: bool


def card_transaction_rows(db, where) -> list[CardTransactionOut]:
    rows = db.execute(select(CardTransaction, Merchant.name, Category.name, Category.code)
                      .join(Merchant, Merchant.id == CardTransaction.merchant_id)
                      .join(Category, Category.id == Merchant.category_id)
                      .where(*where)
                      .order_by(CardTransaction.transacted_at.desc(), CardTransaction.id.desc())).all()
    return [CardTransactionOut(id=t.id, approval_no=t.approval_no, transacted_at=t.transacted_at, merchant=m,
                               category=cat, category_code=code, amount=t.amount, canceled_amount=t.canceled_amount,
                               status=t.status, installment_months=t.installment_months, is_overseas=t.is_overseas)
            for t, m, cat, code in rows]


@router.get("/cards/{cardId}/transactions", response_model=list[CardTransactionOut])
def list_card_transactions(
    card_id: CardId,
    db: DB,
    user_id: CurrentUserId,
    month: Annotated[str | None, Query(pattern=r"^\d{4}(0[1-9]|1[0-2])$", description="이 달만 (YYYYMM)")] = None,
    category: Annotated[str | None, Query(max_length=30, description="업종 code (예: CAFE) — 하위 업종 포함")] = None,
    installment: Annotated[Literal["LUMP_SUM", "INSTALLMENT"] | None, Query(description="일시불만 / 할부만")] = None,
):
    """최신순. 해지한 카드도 기록으로 볼 수 있다(상세와 같음). 기획서 필터: 기간·카드·업종·일시불/할부"""
    _owned(db, user_id, card_id)
    where = [CardTransaction.user_card_id == card_id]
    if month:
        y, m = int(month[:4]), int(month[4:])
        start = datetime(y, m, 1)
        where += [CardTransaction.transacted_at >= start,
                  CardTransaction.transacted_at < datetime(y + m // 12, m % 12 + 1, 1)]
    if category:
        cat = db.scalar(select(Category).where(Category.code == category))
        if cat is None:
            raise ApiError(400, "INVALID_CATEGORY", "없는 업종이에요.")
        children = select(Category.id).where(Category.parent_id == cat.id)
        where.append(Merchant.category_id.in_(select(Category.id).where(Category.id == cat.id).union(children)))
    if installment == "LUMP_SUM":
        where.append(CardTransaction.installment_months <= 1)
    elif installment == "INSTALLMENT":
        where.append(CardTransaction.installment_months > 1)
    return card_transaction_rows(db, where)


# --- 해지 (CARD-F09, 1-3) ---------------------------------------------------------------------
class TerminationOut(BaseModel):
    can_terminate: bool
    blockers: list[str]
    unpaid_amount: Money
    period_spent: Money
    next_payment_date: date | None
    remaining_installment_amount: Money
    recurring_merchants: list[str]
    forfeited_points: Money
    refunded_annual_fee: Money


def termination_check(db, c: UserCard, p: CardProduct, today: date) -> TerminationOut:
    m = card_money(db, c, p.card_type)
    # 남은 할부 = 할부 거래(2개월 이상)의 원금 − 이미 낸(PAID) 청구서에 들어간 회차 원금.
    # (청구서 항목 전체를 더하면 일시불까지 「할부」로 세므로 할부 거래만 본다 — 2026-11-10 청구서 항목을 채우며 바로잡음)
    installment_tx = select(CardTransaction.id).where(CardTransaction.user_card_id == c.id,
                                                       CardTransaction.installment_months > 1)
    principal = db.scalar(select(func.coalesce(func.sum(CardTransaction.amount - CardTransaction.canceled_amount), 0))
                          .where(CardTransaction.id.in_(installment_tx)))
    paid_installments = db.scalar(select(func.coalesce(func.sum(CardBillItem.principal_amount), 0))
                                  .join(CardBill, CardBill.id == CardBillItem.bill_id)
                                  .where(CardBillItem.card_transaction_id.in_(installment_tx), CardBill.status == "PAID"))
    remaining_installment = principal - paid_installments
    merchants = list(db.scalars(select(Merchant.name).join(RecurringPayment, RecurringPayment.merchant_id == Merchant.id)
                                .where(RecurringPayment.user_card_id == c.id, RecurringPayment.is_active.is_(True))))
    others = db.scalar(select(func.count()).select_from(UserCard).join(CardProduct, CardProduct.id == UserCard.card_product_id)
                       .where(UserCard.user_id == c.user_id, UserCard.id != c.id, UserCard.status != "TERMINATED",
                              CardProduct.card_company_id == p.card_company_id))
    points = 0 if others else db.scalar(select(func.coalesce(func.sum(CardPoint.balance), 0)).where(
        CardPoint.user_id == c.user_id, CardPoint.card_company_id == p.card_company_id))
    blockers = (["ALREADY_TERMINATED"] if c.status == "TERMINATED" else []) + (["UNPAID_BILL"] if m.unpaid_confirmed else [])
    _, _, pay_date = current_period(db, p.card_company_id, c.payment_day, today)
    return TerminationOut(
        can_terminate=not blockers, blockers=blockers, unpaid_amount=m.unpaid_confirmed, period_spent=m.unbilled,
        next_payment_date=pay_date if m.unbilled else None, remaining_installment_amount=remaining_installment,
        recurring_merchants=merchants, forfeited_points=points,
        refunded_annual_fee=0)  # shortcut: 연회비 환급은 원장에 입금 유형이 없어 0원, 환급 입금을 만들면 1-3 식으로 계산


def _owned(db, user_id: str, card_id: str, lock: bool = False) -> tuple[UserCard, CardProduct]:
    q = (select(UserCard, CardProduct).join(CardProduct, CardProduct.id == UserCard.card_product_id)
         .where(UserCard.id == card_id, UserCard.user_id == user_id, UserCard.source == "TOSS_ISSUED"))
    row = db.execute(q.with_for_update(of=UserCard) if lock else q).first()
    if row is None:
        raise card_not_found()
    return row


@router.get("/cards/{cardId}/termination-check", response_model=TerminationOut)
def get_termination_check(card_id: CardId, db: DB, user_id: CurrentUserId):
    return termination_check(db, *_owned(db, user_id, card_id), now_kst().date())


class TerminateIn(BaseModel):
    reason_code: Literal[CardTermination.REASON_CODE_VALUES]
    reason_detail: str | None = Field(default=None, max_length=100)
    step_up_challenge_id: str = Field(max_length=40)


@router.post("/cards/{cardId}/terminate", response_model=TerminationOut)
def terminate_card(card_id: CardId, body: TerminateIn, login: CurrentLogin, db: DB):
    c, p = _owned(db, login.user.id, card_id, lock=True)
    consume_step_up(db, body.step_up_challenge_id, login, "CARD_TERMINATION")
    now = now_kst()
    check = termination_check(db, c, p, now.date())
    if not check.can_terminate:
        if "ALREADY_TERMINATED" in check.blockers:
            raise ApiError(409, "CARD_ALREADY_TERMINATED", "이미 해지한 카드예요.")
        raise ApiError(409, "CARD_UNPAID_BILL", "아직 내지 않은 카드 대금이 있어요. 「지금 결제하기」로 먼저 내 주세요.")

    db.add(CardTermination(
        id=new_id("ctm"), user_card_id=c.id, step_up_challenge_id=body.step_up_challenge_id, status="COMPLETED",
        reason_code=body.reason_code, reason_detail=body.reason_detail, unpaid_amount=check.unpaid_amount,
        remaining_installment_amount=check.remaining_installment_amount,
        linked_recurring_count=len(check.recurring_merchants), forfeited_points=check.forfeited_points,
        refunded_annual_fee=0, requested_at=now, completed_at=now))
    db.add(UserCardStatusHistory(id=new_id("csh"), user_card_id=c.id, from_status=c.status, to_status="TERMINATED",
                                 reason=body.reason_code, changed_at=now))
    c.status, c.terminated_at = "TERMINATED", now
    db.execute(update(RecurringPayment).where(RecurringPayment.user_card_id == c.id).values(is_active=False))
    if check.forfeited_points:  # 같은 카드사의 남은 카드가 없으면 포인트 소멸 (1-3)
        db.execute(update(CardPoint).where(CardPoint.user_id == c.user_id, CardPoint.card_company_id == p.card_company_id)
                   .values(balance=0, expiring_amount=0))
    db.add(Notification(id=new_id("ntf"), user_id=c.user_id, user_card_id=c.id, type="CARD_STATUS",
                        title=f"{c.nickname or p.name} 카드를 해지했어요", body="해지한 카드는 다시 쓸 수 없어요.",
                        created_at=now))
    db.commit()
    return check


# --- 지금 결제하기 (CARD-F07 + 사용자 결정 Q4·Q5) ----------------------------------------------------
class PayIn(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


@router.post("/cards/{cardId}/payments", response_model=CardDetailOut)
def pay_card(card_id: CardId, body: PayIn, login: CurrentLogin, db: DB):
    """확정·연체 청구서를 지금 낸다. 해지한 카드면 이번 기간 사용액도 청구서를 만들어 함께 낸다."""
    c, p = _owned(db, login.user.id, card_id, lock=True)
    consume_step_up(db, body.step_up_challenge_id, login, "CARD_MANAGEMENT")
    if p.card_type != "CREDIT":
        raise ApiError(409, "NOTHING_TO_PAY", "체크카드는 쓸 때 바로 계좌에서 빠져나가 낼 대금이 없어요.")
    now = now_kst()
    bills = list(db.scalars(select(CardBill).where(CardBill.user_card_id == c.id, CardBill.status.in_(UNPAID_BILL))
                            .with_for_update()))
    m = card_money(db, c, p.card_type)
    extra = m.unbilled if c.status == "TERMINATED" else 0  # 쓰는 중인 카드의 이번 기간은 아직 금액이 바뀔 수 있어 결제일에
    total = sum(b.total_amount - b.paid_amount for b in bills) + extra
    if total <= 0:
        raise ApiError(409, "NOTHING_TO_PAY", "지금 낼 카드 대금이 없어요.")

    bal = ledger.lock_balances(db, [c.linked_account_id or ""]).get(c.linked_account_id)
    account = db.get(Account, c.linked_account_id) if c.linked_account_id else None
    if bal is None or account.lifecycle_status != "ACTIVE":
        raise ApiError(409, "ACCOUNT_NOT_ACTIVE", "결제 계좌가 정상이 아니에요. 계좌 정지를 먼저 풀어 주세요.")
    if bal.balance < total:
        raise ApiError(409, "INSUFFICIENT_BALANCE", f"결제 계좌 잔액이 부족해요. {total - bal.balance:,}원을 더 채워 주세요.")

    ledger.post(db, bal, "CARD_PAYMENT", total, now, display_name=(c.nickname or p.name)[:50])
    for b in bills:
        b.paid_amount, b.status, b.paid_at = b.total_amount, "PAID", now
    if extra:
        _close_final_period(db, c, p, extra, now)
    db.commit()
    return _detail(db, login.user.id, c.id)


# --- 결제·출금 계좌 바꾸기 (CARD-F08 1차 — 계좌를 해지하려면 카드를 먼저 옮겨야 함, Part 2 ACCT-F05) -----------------
class LinkedAccountIn(BaseModel):
    account_id: str = Field(max_length=40)
    step_up_challenge_id: str | None = Field(default=None, max_length=40)


@router.patch("/cards/{cardId}/linked-account", response_model=CardDetailOut)
def change_linked_account(card_id: CardId, body: LinkedAccountIn, login: CurrentLogin, db: DB):
    """새 계좌는 본인의 정상(ACTIVE) 입출금(CHECKING) 계좌이고 지금과 달라야 한다. 변경 전후는 card_management_logs."""
    user_id = login.user.id
    c, p = _owned(db, user_id, card_id, lock=True)  # 카드 행을 잠가 결제 배치·다른 변경과 겹치지 않게
    if c.status == "TERMINATED":
        raise ApiError(409, "CARD_TERMINATED", "해지한 카드는 계좌를 바꿀 수 없어요.")
    a = db.get(Account, body.account_id)
    if a is None or a.user_id != user_id or a.account_type != "CHECKING" or a.lifecycle_status != "ACTIVE":
        raise ApiError(422, "INVALID_LINKED_ACCOUNT", "내 정상 입출금 계좌만 고를 수 있어요.")
    if a.id == c.linked_account_id:
        raise ApiError(409, "SAME_ACCOUNT", "지금 연결된 계좌예요. 다른 계좌를 골라 주세요.")
    if payment_day_locked(db, c.id, now_kst().date()):
        raise ApiError(409, "PAYMENT_DAY_LOCKED", "오늘은 이 카드의 결제일이라 결제 계좌를 바꿀 수 없어요. 내일 다시 시도해 주세요.")
    consume_step_up(db, body.step_up_challenge_id, login, "CARD_MANAGEMENT")
    db.add(CardManagementLog(id=new_id("cml"), user_card_id=c.id, action_type="LINKED_ACCOUNT_CHANGE",
                             before_value=c.linked_account_id, after_value=a.id, result="SUCCESS", requested_at=now_kst()))
    c.linked_account_id = a.id
    db.commit()
    return _detail(db, user_id, c.id)


def _close_final_period(db, c: UserCard, p: CardProduct, amount: int, now: datetime) -> None:
    """해지한 카드의 마지막 이용분을 청구서로 만들고 바로 결제 완료로 둔다(청구서에 안 묶인 이용 내역을 항목으로)."""
    start, end, pay = current_period(db, p.card_company_id, c.payment_day, now.date())
    ym = (pay or end).strftime("%Y%m")
    if db.scalar(select(CardBill.id).where(CardBill.user_card_id == c.id, CardBill.billing_ym == ym)):
        # shortcut: 같은 달 청구서가 이미 있으면 합치지 않고 거절 — 결제일 일괄 출금(app/jobs.py)이 먼저 만든 경우뿐
        raise ApiError(409, "BILL_ALREADY_EXISTS", "이번 기간 청구서가 이미 있어요. 결제일 뒤에 다시 시도해 주세요.")
    bill = CardBill(id=new_id("bill"), user_card_id=c.id, billing_ym=ym, usage_start=start, usage_end=end,
                    payment_date=pay or end, total_amount=amount, paid_amount=amount, status="PAID",
                    confirmed_at=now, paid_at=now)
    db.add(bill)
    db.flush()  # 항목이 가리킬 청구서를 먼저 넣는다(모델에 relationship 이 없음)
    billed = select(CardBillItem.card_transaction_id)
    for t in db.scalars(select(CardTransaction).where(CardTransaction.user_card_id == c.id,
                                                      CardTransaction.id.not_in(billed),
                                                      CardTransaction.amount > CardTransaction.canceled_amount)):
        db.add(CardBillItem(id=new_id("cbi"), bill_id=bill.id, card_transaction_id=t.id, installment_seq=1,
                            principal_amount=t.amount - t.canceled_amount, fee_amount=0))
