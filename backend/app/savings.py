"""예금·적금의 날짜·이자·납입 규칙 — 기획서 Part 3 PROD-F05·F06·F11·F12.

상품 화면(app/routers/products.py) · 가입 조회와 납입(app/routers/subscriptions.py) · 만기 배치(app/jobs.py)가
모두 이 함수를 쓴다. DB 를 읽지 않는 순수 계산만 둔다 — 그래서 서로 import 해도 순환이 생기지 않는다.

[모의 규칙]
- 이자: 단리 · 세전 · 원 미만 버림 · 기본 금리만(우대 조건 판정은 3차). 세금은 떼지 않는다(사용자 결정 2026-11-10).
- 만기일: 가입일과 같은 날짜의 N개월 뒤(그 달에 없으면 말일). 일 단위 상품은 N일 뒤.
- 적금 납입 방식(product_rules.rules_json.payment_types, 사용자 결정 2026-11-10):
    FIXED 정액적립식 — 가입 때 정한 월 납입액(subscriptions.monthly_amount)만, 회차마다 한 번. 놓친 회차는 건너뛴다.
    FREE  자유적립식 — 회차마다 상품의 월 한도(rules_json.monthly_max) 안에서 몇 번이든. monthly_amount 는 비운다.
  회차: 가입일부터 한 달씩 자른 기간. 1회차 = [가입일, 가입일+1개월), 2회차 = [가입일+1개월, 가입일+2개월) …
"""

import calendar
from datetime import date
from decimal import Decimal

FIXED, FREE = "FIXED", "FREE"
PAYMENT_TYPES = (FIXED, FREE)
PAYMENT_TYPE_LABEL = {FIXED: "정액적립식", FREE: "자유적립식"}


def maturity_date(start: date, months: int) -> date:
    """가입일과 같은 날짜의 N개월 뒤 — 그 달에 같은 날이 없으면 그 달 말일 (PROD-F05)."""
    y, m = divmod(start.month - 1 + months, 12)
    y, m = start.year + y, m + 1
    return date(y, m, min(start.day, calendar.monthrange(y, m)[1]))


def months_between(start: date, end: date) -> int:
    """start 부터 end 까지 꽉 찬 개월 수 — maturity_date(start, n) <= end 인 가장 큰 n."""
    n = max((end.year - start.year) * 12 + end.month - start.month - 1, 0)
    while maturity_date(start, n + 1) <= end:
        n += 1
    return n


def interest(rate: Decimal, deposit: bool, by_day: bool, start: date, end: date, paid: list[tuple[date, int]]) -> int:
    """[모의 규칙] 단리·세전·원 미만 버림. 적금은 납입마다 그날부터 만기까지 꽉 찬 개월로 — 매달 같은 돈이면 n(n+1)/2 와 같다."""
    r = rate / 100
    if deposit:
        total = sum(a for _, a in paid)
        return int(total * r * (end - start).days / 365) if by_day else int(total * r * months_between(start, end) / 12)
    return int(sum(a * r * months_between(d, end) for d, a in paid) / 12)


def ymd(s: str) -> date:
    """'YYYYMMDD' 또는 'YYYYMMDDHHmmss' → date."""
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def current_period(start: date, today: date) -> tuple[date, date]:
    """오늘이 든 회차 [시작일, 다음 회차 시작일). 가입일 전이면 1회차."""
    k = months_between(start, today) if today >= start else 0
    return maturity_date(start, k), maturity_date(start, k + 1)


def allowed_payment_types(product_type: str, rules_json: dict | None) -> list[str]:
    """이 상품으로 고를 수 있는 납입 방식. 예금은 빈 목록, 값이 없는 적금은 자유적립식으로 본다."""
    if product_type != "INSTALLMENT_SAVINGS":
        return []
    return [t for t in PAYMENT_TYPES if t in ((rules_json or {}).get("payment_types") or [FREE])]


def payment_type_of(product_type: str, monthly_amount: int | None) -> str | None:
    """가입 계약의 납입 방식 — 적금이고 월 납입액이 정해져 있으면 정액, 비어 있으면 자유. 예금은 None."""
    if product_type != "INSTALLMENT_SAVINGS":
        return None
    return FIXED if monthly_amount is not None else FREE


def paid_list(start: date, principal: int, payments: list[tuple[date, int]]) -> list[tuple[date, int]]:
    """만기 이자를 셀 납입 목록. 납입 기록보다 원금이 크면 모자란 만큼을 가입일에 넣은 것으로 본다 (모의 규칙 —
    더미 계약은 원금 누계만 있고 납입 기록은 일부뿐이라서. 예금은 납입 기록이 없으니 원금 전체가 가입일 납입이 된다)."""
    missing = principal - sum(a for _, a in payments)
    return ([(start, missing)] if missing > 0 else []) + payments
