"""예약 작업으로 돌릴 일 — 사용자가 서버에 스케줄러를 만들 예정(2026-11-09). 그 전까지는 손으로 한 번씩 실행한다.

    cd backend && .venv\\Scripts\\python -m app.jobs        # 아래 세 가지를 한 번씩

    purge_withdrawn_users     탈퇴 1개월 지난 회원 가명 처리 (AUTH-F09)              — 하루 한 번
    settle_pending_transfers  10분 넘게 처리중(PENDING)인 타행 이체 확정 (Part 5 9장)  — 몇 분마다
    pay_due_card_bills        결제일이 된 확정 청구서 출금, 잔액 부족이면 연체 (CARD-F07) — 하루 한 번

스케줄러에서는 함수를 부른 뒤 db.commit() 하면 된다. 셋 다 몇 번 돌려도 결과가 같다.
"""

import calendar
from datetime import date, datetime

from sqlalchemy import delete, or_, select

from app import ledger
from app.models import Account, AuthIdentity, CardBill, CardProduct, Notification, Transfer, User, UserCard
from app.rules import PENDING_SETTLE_AFTER, WITHDRAWN_NAME, now_kst
from app.security import new_id


def one_month_before(now: datetime) -> datetime:
    """달력 기준 1개월 전 (3월 31일 → 2월 28/29일)."""
    y, m = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return now.replace(year=y, month=m, day=min(now.day, calendar.monthrange(y, m)[1]))


def purge_withdrawn_users(db, now: datetime) -> list[str]:
    """탈퇴 1개월(유예 기간, AUTH-F09 ② 「유예 기간 뒤 파기」)이 지난 회원을 가명 처리한다. 처리한 회원 id 목록을 돌려준다.

    users 행은 5년 보존하는 계좌·거래·감사 기록이 가리켜 지울 수 없으므로 개인정보만 지운다 (사용자 결정 2026-11-09):
      이름 → 「탈퇴회원」 · 이메일·이메일 인증 시각·월급일 → 비움 · 생년월일 → 그해 1월 1일 · 로그인 수단 연결 삭제
      아이디(username)는 그대로 — 다른 사람이 영원히 못 쓰게(사용자 결정)
    이미 처리한 회원(이름이 「탈퇴회원」이고 이메일이 비어 있음)은 다시 고르지 않는다 — 몇 번 돌려도 결과가 같다."""
    users = list(db.scalars(select(User).where(
        User.status == "WITHDRAWN", User.withdrawn_at <= one_month_before(now),
        or_(User.name != WITHDRAWN_NAME, User.email.is_not(None)))))
    for u in users:
        u.name, u.email, u.email_verified_at, u.payday = WITHDRAWN_NAME, None, None, None
        u.birth_date = date(u.birth_date.year, 1, 1)
        db.execute(delete(AuthIdentity).where(AuthIdentity.user_id == u.id))
    return [u.id for u in users]


def settle_pending_transfers(db, now: datetime) -> list[str]:
    """10분 넘게 PENDING 인 이체를 확정한다. 그때 잔액·계좌 상태를 다시 보고 SUCCESS(원장 출금) 또는 FAILED.
    PENDING 은 타행 시험 계좌(예금주 「임처리」)로 보낼 때만 생긴다(app/routers/transfers.py)."""
    from app.routers.transfers import post_transfer  # 라우터가 jobs 를 부르지 않으므로 순환 없음 — 원장 기록은 이체와 같은 함수

    done = []
    for t in db.scalars(select(Transfer).where(Transfer.status == "PENDING", Transfer.requested_at <= now - PENDING_SETTLE_AFTER)
                        .with_for_update(skip_locked=True)):  # 두 스케줄러가 겹쳐도 한 건은 한 번만
        bals = ledger.lock_balances(db, [t.from_account_id])
        src = db.get(Account, t.from_account_id)
        if src.lifecycle_status != "ACTIVE":
            t.status, t.failure_reason = "FAILED", "ACCOUNT_NOT_ACTIVE"
        elif bals[t.from_account_id].balance < t.amount + t.fee:
            t.status, t.failure_reason = "FAILED", "INSUFFICIENT_BALANCE"
        else:
            t.status = "SUCCESS"
            post_transfer(db, t, bals, now)
        t.completed_at = now
        done.append(t.id)
    return done


def pay_due_card_bills(db, now: datetime) -> tuple[list[str], list[str]]:
    """결제일(오늘 또는 지난)이 된 확정 청구서를 결제 계좌에서 출금한다 (CARD-F07, Part 4 1-7).
    전액이 있으면 CARD_PAYMENT + PAID, 모자라면 한 푼도 빼지 않고 OVERDUE + 알림. (출금된 id, 연체된 id)."""
    paid, overdue = [], []
    rows = db.execute(select(CardBill, UserCard, CardProduct.name).join(UserCard, UserCard.id == CardBill.user_card_id)
                      .join(CardProduct, CardProduct.id == UserCard.card_product_id)
                      .where(CardBill.status == "CONFIRMED", CardBill.payment_date <= now.date())
                      .with_for_update(of=CardBill, skip_locked=True)).all()
    for bill, card, product in rows:
        due = bill.total_amount - bill.paid_amount
        bal = ledger.lock_balances(db, [card.linked_account_id or ""]).get(card.linked_account_id)
        account = db.get(Account, card.linked_account_id) if card.linked_account_id else None
        if bal is not None and account.lifecycle_status == "ACTIVE" and bal.balance >= due:
            if due:
                ledger.post(db, bal, "CARD_PAYMENT", due, now, display_name=(card.nickname or product)[:50])
            bill.paid_amount, bill.status, bill.paid_at = bill.total_amount, "PAID", now
            paid.append(bill.id)
        else:
            bill.status = "OVERDUE"
            db.add(Notification(id=new_id("ntf"), user_id=card.user_id, user_card_id=card.id, event_id=bill.id,
                                type="OVERDUE", title=f"{card.nickname or product} 대금이 연체됐어요",
                                body=f"결제 계좌 잔액이 부족해 {due:,}원을 내지 못했어요. 카드 상세에서 「지금 결제하기」를 눌러 주세요.",
                                created_at=now))
            overdue.append(bill.id)
    return paid, overdue


if __name__ == "__main__":
    from app.db import SessionLocal

    with SessionLocal() as db:
        now = now_kst()
        purged = purge_withdrawn_users(db, now)
        settled = settle_pending_transfers(db, now)
        paid, overdue = pay_due_card_bills(db, now)
        db.commit()
    print(f"가명 처리 {len(purged)}명 · 처리중 이체 확정 {len(settled)}건 · 카드 대금 출금 {len(paid)}건 · 연체 {len(overdue)}건")
