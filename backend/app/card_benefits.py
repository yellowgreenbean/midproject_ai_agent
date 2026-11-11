"""카드 혜택 보여 주기 — 기획서 Part 4 1-1-2 「카드 상세」 혜택 목록 (CARD-F02).

혜택 데이터: data/dummy/cards/card_benefits.json (실제 카드 우리카드 5장의 카드고릴라 원문을 칸에 옮김, 사용자 결정 2026-11-10)
표: card_benefits · card_performance_tiers(MONTH 전월 / QUARTER 지난 분기) · card_benefit_limit_groups(통합 월 한도)

어느 구간의 혜택을 보여 주나
    혜택 행은 실적 구간마다 하나씩 있다(한도가 구간마다 다름). 카드의 「지난달(분기) 실적」으로 구간을 고르고,
    아직 첫 구간도 못 넘었으면 첫 구간 행을 보여 주되 achieved=false 로 「전월 30만 원 이상 쓰면」을 알린다.
    실적 = 그 기간 승인 금액 − 취소 금액 (is_performance_counted 인 것만, 기획서 1-1-6 과 같은 합계).
1차는 「보여 주기」만 한다 — 결제마다 혜택을 계산해 card_transactions.benefit_amount 를 채우는 일은 하지 않는다(BACKLOG).
"""

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import func, select

from app.models import CardBenefit, CardBenefitLimitGroup, CardPerformanceTier, CardTransaction, Category

TYPE_WORD = {"DISCOUNT": "할인", "CASHBACK": "캐시백", "POINT": "적립", "MILEAGE": "마일리지 적립", "FEE_WAIVER": "수수료 면제"}
DAY_WORD = {"MON": "월", "TUE": "화", "WED": "수", "THU": "목", "FRI": "금", "SAT": "토", "SUN": "일"}
CHANNEL_WORD = {"ONLINE": "온라인 결제만", "OFFLINE": "매장 결제만"}


def won(n: int) -> str:
    """금액 글자 — 1만 원 단위로 떨어지면 「30만 원」, 아니면 「5,500원」"""
    if n >= 10_000 and n % 10_000 == 0:
        return f"{n // 10_000:,}만 원"
    return f"{n:,}원"


def _num(v) -> str:
    """Decimal 5.00 → '5', 0.20 → '0.2'"""
    return format(v.normalize(), "f") if hasattr(v, "normalize") else str(v)


def _hm(t: time) -> str:
    return f"{t.hour}시" if t.minute == 0 else f"{t.hour}시 {t.minute}분"


# --- 실적 -------------------------------------------------------------------------------------
def _month_start(d: date, back: int = 0) -> date:
    m = d.year * 12 + d.month - 1 - back
    return date(m // 12, m % 12 + 1, 1)


def previous_periods(today: date) -> dict[str, tuple[date, date]]:
    """지난달·지난 분기의 [시작, 끝) — 실적을 셀 기간"""
    q_start = _month_start(today, (today.month - 1) % 3)  # 이번 분기 첫날
    return {"MONTH": (_month_start(today, 1), _month_start(today)),
            "QUARTER": (_month_start(q_start, 3), q_start)}


def spent_between(db, card_id: str, start: date, end: date, counted_only: bool = True) -> int:
    """[start, end) 동안 이 카드로 쓴 돈 — 승인 − 취소. counted_only 면 실적 제외(세금·상품권 등)도 뺀다"""
    q = select(func.coalesce(func.sum(CardTransaction.amount - CardTransaction.canceled_amount), 0)).where(
        CardTransaction.user_card_id == card_id,
        CardTransaction.transacted_at >= datetime.combine(start, time.min),
        CardTransaction.transacted_at < datetime.combine(end, time.min))
    if counted_only:
        q = q.where(CardTransaction.is_performance_counted.is_(True))
    return db.scalar(q)


@dataclass
class Standing:
    """한 기간(MONTH/QUARTER)의 실적과 지금 해당하는 구간"""
    period: str
    spent: int
    tier: CardPerformanceTier | None  # 보여 줄 구간 — 못 넘었으면 첫 구간
    achieved: bool
    next_tier: CardPerformanceTier | None  # 한 단계 위 구간 (없으면 None)


def standings(db, card_id: str, product_id: str, today: date) -> dict[str, Standing]:
    tiers = db.scalars(select(CardPerformanceTier).where(CardPerformanceTier.card_product_id == product_id)
                       .order_by(CardPerformanceTier.period, CardPerformanceTier.tier_level)).all()
    out = {}
    for period, (start, end) in previous_periods(today).items():
        mine = [t for t in tiers if t.period == period]
        if not mine:
            continue
        spent = spent_between(db, card_id, start, end)
        reached = [t for t in mine if spent >= t.min_spend]
        tier = reached[-1] if reached else mine[0]
        nxt = next((t for t in mine if t.tier_level == tier.tier_level + 1), None) if reached else mine[0]
        out[period] = Standing(period, spent, tier, bool(reached), nxt)
    return out


# --- 혜택 한 줄 -------------------------------------------------------------------------------
def title_of(b: CardBenefit, category: str) -> str:
    """「카페 55% 할인」 · 「주유 리터당 60원 할인」 · 「모든 가맹점 0.2% 적립」 · 「영화 5,500원 할인」"""
    v = _num(b.benefit_value)
    amount = {"PERCENT": f"{v}%", "FIXED": f"{int(b.benefit_value):,}원", "PER_LITER": f"리터당 {v}원"}[b.value_type]
    return f"{category} {amount} {TYPE_WORD[b.benefit_type]}"


def conditions_of(b: CardBenefit, tier: CardPerformanceTier | None) -> list[str]:
    """칸에 담긴 조건을 사람 말로 (화면·챗봇이 그대로 보여 줌). 순서: 실적 → 어디서 → 언제 → 얼마나"""
    c = []
    if tier is not None:
        c.append(("지난 분기" if tier.period == "QUARTER" else "전월") + f" {won(tier.min_spend)} 이상 썼을 때")
    if b.merchant_names:
        c.append("·".join(b.merchant_names.split(",")) + "에서만")
    if b.payment_channel:
        c.append(CHANNEL_WORD[b.payment_channel])
    if b.pay_methods:
        c.append("·".join(b.pay_methods.split(",")) + "로 결제할 때")
    if b.days_of_week:
        c.append("·".join(DAY_WORD[d] for d in b.days_of_week.split(",")) + "요일만")
    if b.time_start and b.time_end:
        c.append(f"{_hm(b.time_start)}~{_hm(b.time_end)} 결제만")
    if b.min_payment_amount:
        c.append(f"한 번에 {won(b.min_payment_amount)} 이상 결제")
    if b.max_eligible_amount:
        c.append(f"결제 {won(b.max_eligible_amount)}까지만 계산")
    if b.per_payment_max_benefit:
        c.append(f"한 번에 최대 {won(b.per_payment_max_benefit)}")
    if b.daily_limit_count:
        c.append(f"하루 {b.daily_limit_count}회")
    if b.monthly_limit_count:
        c.append(f"한 달 {b.monthly_limit_count}회")
    if b.description:
        c.append(b.description)
    return c


def benefits_for(db, card_id: str, product_id: str, today: date) -> tuple[list[dict], dict[str, Standing]]:
    """카드 상세에 보여 줄 혜택 (지금 구간의 행만) + 기간별 실적"""
    st = standings(db, card_id, product_id, today)
    shown_tiers = {s.tier.id for s in st.values()}
    rows = db.execute(
        select(CardBenefit, Category.name, CardBenefitLimitGroup, CardPerformanceTier)
        .outerjoin(Category, Category.id == CardBenefit.category_id)
        .outerjoin(CardBenefitLimitGroup, CardBenefitLimitGroup.id == CardBenefit.limit_group_id)
        .outerjoin(CardPerformanceTier, CardPerformanceTier.id == CardBenefit.tier_id)
        .where(CardBenefit.card_product_id == product_id)
        .order_by(CardBenefit.id)).all()
    out = []
    for b, category, group, tier in rows:
        if tier is not None and tier.id not in shown_tiers:
            continue
        name = category or "모든 가맹점"
        out.append(dict(
            id=b.id, category=name, benefit_type=b.benefit_type, value_type=b.value_type,
            value=_num(b.benefit_value), title=title_of(b, name), conditions=conditions_of(b, tier),
            monthly_limit=b.monthly_limit_amount,
            limit_group=None if group is None else {"name": group.name, "monthly_limit": group.monthly_limit_amount},
            achieved=True if tier is None else st[tier.period].achieved,
        ))
    return out, st
