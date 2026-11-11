"""예약 작업 — 서버가 켜져 있으면 app/main.py 의 스케줄러가 run_minutely() 를 1분마다 부른다(사용자 결정 2026-11-10).
손으로 한 번 돌리려면:

    cd backend && .venv\\Scripts\\python -m app.jobs        # 아래 열 가지를 한 번씩

    run_scheduled_transfers   실행 시각이 된 예약 송금·자동이체 실행 (Part 5 8장, TRX-F10·F11) — 1분마다
    purge_withdrawn_users     탈퇴 1개월 지난 회원 가명 처리 (AUTH-F09)              — 하루 한 번
    settle_pending_transfers  10분 넘게 처리중(PENDING)인 타행 이체 확정 (Part 5 9장)  — 몇 분마다
    pay_due_card_bills        결제일이 된 확정 청구서 출금, 잔액 부족이면 연체 (CARD-F07) — 하루 한 번
    notify_card_payments      카드 결제일 D-3·당일 알림, 결제 계좌 잔액 부족 알림 (CARD-F04, 1-1-4) — 하루 한 번(아침)
    mature_subscriptions      만기일이 된 예금·적금에 원금+이자 지급, 출금 계좌가 정지면 알림만 (PROD-F11) — 하루 한 번
    notify_expiring_points    카드 포인트 소멸 30일 전 알림 한 번 (CARD-F12, 1-1-7)   — 하루 한 번
    expire_points             소멸일이 지난 소멸 예정 포인트를 잔액에서 뺌 (CARD-F12)   — 하루 한 번
    notify_annual_fees        연회비 청구 30일 전 알림 한 번 (CARD-F13, 1-1-8)        — 하루 한 번
    charge_annual_fees        청구일이 된 신용카드 연회비를 이용내역 한 줄로 기록, 청구일은 1년 뒤로 (CARD-F13) — 하루 한 번

열 가지 다 몇 번 돌려도 결과가 같다.
"""

import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, delete, or_, select, update

from app.common import ledger
from app.errors import ApiError
from app.models import (
    Account,
    AccountBalance,
    AuthIdentity,
    CardBill,
    CardPoint,
    CardProduct,
    CardTransaction,
    Category,
    Merchant,
    Notification,
    Product,
    ScheduledTransfer,
    Subscription,
    SubscriptionPayment,
    Transfer,
    User,
    UserCard,
    UserCardSetting,
)
from app.rules import (
    ANNUAL_FEE_ALERT_DAYS,
    PENDING_SETTLE_AFTER,
    POINT_EXPIRY_ALERT_DAYS,
    TRANSFER_FAILURE_MESSAGES,
    WITHDRAWN_NAME,
    next_year,
    now_kst,
)
from app.savings import interest, paid_list, ymd
from app.security import new_id

log = logging.getLogger(__name__)


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
        _finish_scheduled(db, t, now)
        done.append(t.id)
    return done


def _finish_scheduled(db, t: Transfer, now: datetime) -> None:
    """예약으로 실행된 이체가 끝났을 때: 예약 송금(ONCE) 상태를 이체 결과로, 실패면 알림(8장 — 성공 알림은 원장의
    거래 확정 이벤트가 만든다. 실패는 원장이 없어 여기서). 처리중(PENDING)이면 예약은 PROCESSING 으로 둔다."""
    from app.routers.notifications import notify

    if t.scheduled_transfer_id is None or t.status == "PENDING":
        return
    s = db.get(ScheduledTransfer, t.scheduled_transfer_id)
    if s.type == "ONCE":
        s.status, s.updated_at = t.status, now
    if t.status == "FAILED":
        notify(db, user_id=t.user_id, account_id=t.from_account_id, event_id=t.id,
               title="예약 송금을 보내지 못했어요" if s.type == "ONCE" else "자동이체를 보내지 못했어요",
               body=f"{t.to_holder_name}님께 {t.amount:,}원 · {TRANSFER_FAILURE_MESSAGES.get(t.failure_reason, '')}")


def run_scheduled_transfers(db, now: datetime) -> list[str]:
    """실행 시각이 된 예약 송금(ONCE)·자동이체(MONTHLY)를 일반 이체와 같은 규칙(run_transfer)으로 실행한다(Part 5 8·14장).
    한 건마다 커밋한다 — 한 건이 실패해도 다른 예약은 돈다. 만든 이체 id 목록을 돌려준다.
    - 중복 실행 막기: ONCE 는 SCHEDULED → PROCESSING 으로 먼저 바꾸고 바뀐 행이 1개일 때만,
      MONTHLY 는 회차마다 멱등성 키 SCH-{예약ID}-{실행일 yyyyMMdd}(transfers.idempotency_key UNIQUE)
    - 본인 확인은 등록 때 받았으므로 다시 받지 않는다. 그 번호를 transfers.step_up_challenge_id 에 그대로 쓴다
    - 자동이체: 지정일 06:00, 실패해도 재시도·정지 없이 다음 달로(사용자 결정 2026-11-10). 종료 월을 넘기면 SUCCESS(끝남)"""
    made = []
    due = db.execute(select(ScheduledTransfer.id, ScheduledTransfer.type).where(
        ScheduledTransfer.next_run_at <= now,
        or_(and_(ScheduledTransfer.type == "ONCE", ScheduledTransfer.status == "SCHEDULED"),
            and_(ScheduledTransfer.type == "MONTHLY", ScheduledTransfer.status == "ACTIVE")))
        .order_by(ScheduledTransfer.next_run_at)).all()
    db.rollback()  # 위 조회의 트랜잭션을 닫고 한 건씩 새로
    for sid, type_ in due:
        try:
            if tid := _run_one_scheduled(db, sid, type_, now):
                made.append(tid)
        except Exception:  # 이 건은 롤백돼 그대로(SCHEDULED·ACTIVE) 남고 다음 분에 다시 시도된다
            db.rollback()
            log.exception("예약 실행 실패 (scheduled_transfer_id=%s)", sid)
    return made


def _run_one_scheduled(db, sid: str, type_: str, now: datetime) -> str | None:
    from app.routers.transfer_targets import find_target
    from app.routers.transfers import next_monthly_run, run_transfer

    if type_ == "ONCE":
        claimed = db.execute(update(ScheduledTransfer).where(ScheduledTransfer.id == sid, ScheduledTransfer.status == "SCHEDULED")
                             .values(status="PROCESSING", updated_at=now)).rowcount
        s = db.get(ScheduledTransfer, sid) if claimed == 1 else None
    else:
        s = db.scalar(select(ScheduledTransfer).where(ScheduledTransfer.id == sid, ScheduledTransfer.status == "ACTIVE",
                                                      ScheduledTransfer.next_run_at <= now).with_for_update(skip_locked=True))
    if s is None:  # 다른 실행기가 먼저 가져갔다
        db.rollback()
        return None
    run_at, tid = s.next_run_at, None
    key = f"SCH-{s.id}-{run_at:%Y%m%d}"
    if db.scalar(select(Transfer.id).where(Transfer.idempotency_key == key)) is None:
        user, src = db.get(User, s.user_id), db.get(Account, s.from_account_id)
        try:
            dst, holder, mine = find_target(db, s.user_id, s.to_bank, s.to_account_no)
            # 등록 뒤 이용 제한(RESTRICTED)된 회원은 본인 명의로만 (Part 1 7.3)
            failure = None if user.status == "ACTIVE" or (user.status == "RESTRICTED" and mine) else "ACCOUNT_NOT_ACTIVE"
        except ApiError:  # 받는 계좌가 사라졌다
            dst, holder, failure = None, s.to_holder_name, "INVALID_ACCOUNT"
        t, _ = run_transfer(db, user=user, src=src, dst=dst, holder=holder, to_bank=s.to_bank,
                            to_account_no=s.to_account_no, amount=s.amount, my_name=s.my_display_name,
                            their_name=s.their_display_name, channel="SCHEDULED" if s.type == "ONCE" else "AUTO",
                            step_up_id=s.step_up_challenge_id, key=key, now=now, scheduled_id=s.id, failure=failure)
        _finish_scheduled(db, t, now)
        tid = t.id
    if s.type == "MONTHLY":
        s.next_run_at = next_monthly_run(run_at, s.day_of_month, s.start_ym, s.end_ym)
        if s.next_run_at is None:
            s.status = "SUCCESS"  # 종료 월까지 다 보냄
        s.updated_at = now
    db.commit()
    return tid


def run_minutely(now: datetime | None = None) -> None:
    """서버 안 스케줄러가 1분마다 부른다(app/main.py, 사용자 결정 2026-11-10). 작업마다 따로 커밋해 하나가 실패해도 나머지는 돈다.
    카드 알림·출금과 가명 처리는 하루 한 번이면 되지만 몇 번 돌려도 결과가 같아 같이 돌린다."""
    from app.common.db import SessionLocal

    now = now or now_kst()
    for job in (run_scheduled_transfers, settle_pending_transfers, notify_card_payments, pay_due_card_bills,
                purge_withdrawn_users, mature_subscriptions, notify_expiring_points, expire_points,
                notify_annual_fees, charge_annual_fees):
        with SessionLocal() as db:
            try:
                job(db, now)
                db.commit()
            except Exception:
                log.exception("예약 작업 실패: %s", job.__name__)


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


def mature_subscriptions(db, now: datetime) -> tuple[list[str], list[str]]:
    """만기일(오늘 또는 지난)이 된 진행 중(ACTIVE) 예금·적금을 끝낸다 (PROD-F11, Part 3 4장). (지급한 id, 미룬 id).

    - 지급: 원금 + 이자(가입 때 금리 applied_rate, app/savings.py 의 [모의 규칙] — 단리·세전)를 출금 계좌로 입금
      (SUBSCRIPTION_PAYOUT) + 계약 MATURED · closed_at 오늘 + MATURITY 알림. 셋은 같은 트랜잭션.
    - 적금 이자는 실제 납입 기록마다 「납입일부터 만기일까지 꽉 찬 개월」로 센다 — 놓친 회차만큼 이자가 줄어든다.
    - 출금 계좌가 정지(SUSPENDED)면 입금할 수 없으니 건너뛰고 알림만 한 번 보낸다. 정지가 풀리면 다음 실행에서 지급한다.
    - 같은 알림은 한 번만: event_id 는 지급이면 계약 id, 미룸이면 계약 id + ':HOLD' (notifications 의 UNIQUE).
    """
    from app.routers.products import day_unit  # 상품 라우터가 모델을 많이 끌어오므로 쓸 때 가져온다

    today = now.date()
    paid, held = [], []
    rows = db.execute(select(Subscription, Product).join(Product, Product.id == Subscription.product_id)
                      .where(Subscription.status == "ACTIVE", Subscription.maturity_date <= today.strftime("%Y%m%d"))
                      .order_by(Subscription.id).with_for_update(of=Subscription, skip_locked=True)).all()
    for s, p in rows:
        bal = ledger.lock_balances(db, [s.source_account_id]).get(s.source_account_id)
        account = db.get(Account, s.source_account_id)
        if bal is None or account.lifecycle_status != "ACTIVE":
            event = f"{s.id}:HOLD"
            if db.scalar(select(Notification.id).where(Notification.event_id == event, Notification.user_id == s.user_id,
                                                       Notification.type == "MATURITY")) is None:
                db.add(Notification(id=new_id("ntf"), user_id=s.user_id, account_id=s.source_account_id, event_id=event,
                                    type="MATURITY", title=f"{p.name} 만기 금액을 아직 못 보냈어요",
                                    body=f"출금 계좌 {account.resAccountDisplay}가 정지되어 있어요. 정지를 풀면 바로 보내 드려요.",
                                    created_at=now))
            held.append(s.id)
            continue
        start, end = ymd(s.start_date), ymd(s.maturity_date)
        records = [(ymd(x.paid_at), x.paid_amount) for x in db.scalars(
            select(SubscriptionPayment).where(SubscriptionPayment.subscription_id == s.id))]
        principal = s.principal or 0
        i = interest(Decimal(s.applied_rate), p.type == "TIME_DEPOSIT", day_unit(db, p.id), start, end,
                     paid_list(start, principal, records))
        if principal + i:
            ledger.post(db, bal, "SUBSCRIPTION_PAYOUT", principal + i, now, display_name=p.name[:50])
        s.status, s.closed_at = "MATURED", today.strftime("%Y%m%d")
        db.add(Notification(id=new_id("ntf"), user_id=s.user_id, account_id=s.source_account_id, event_id=s.id,
                            type="MATURITY", title=f"{p.name} 만기 금액을 보냈어요",
                            body=f"원금 {principal:,}원 + 이자 {i:,}원(세전) = {principal + i:,}원을 {account.resAccountDisplay}로 보냈어요.",
                            created_at=now))
        paid.append(s.id)
    return paid, held


PAYMENT_ALERT_DAYS = (3, 0)  # 결제일 D-3 · 당일 (기획서 1-1-4)


def notify_card_payments(db, now: datetime) -> list[str]:
    """결제일이 3일 뒤·오늘인 확정 청구서마다 PAYMENT_DUE 알림, 결제 계좌 잔액이 모자라면 LOW_BALANCE 알림도 (1-1-4).

    - 알림 끔(user_card_settings.payment_alert_enabled = false)이면 건너뛴다. 설정 행이 없으면 켜진 것(기본값 TRUE).
    - 잔액 부족: 같은 결제 계좌에서 빠질 안 낸 청구서(확정·연체)를 결제일 순으로 쌓아, 그 청구서까지의 합 > 잔액이면.
    - 같은 알림은 한 번만: (event_id, user_id, type) 이 겹치면 만들지 않는다(표의 UNIQUE). event_id 는 D-3 이면 청구서 id
      (시나리오 시드의 「결제 예정」 알림과 같은 규칙), 당일이면 청구서 id + ':D-0'.
    만든 알림 id 목록을 돌려준다."""
    today = now.date()
    rows = db.execute(
        select(CardBill, UserCard, CardProduct.name, Account.resAccountDisplay, UserCardSetting.payment_alert_enabled)
        .join(UserCard, UserCard.id == CardBill.user_card_id)
        .join(CardProduct, CardProduct.id == UserCard.card_product_id)
        .join(User, User.id == UserCard.user_id)
        .outerjoin(Account, Account.id == UserCard.linked_account_id)
        .outerjoin(UserCardSetting, UserCardSetting.user_card_id == UserCard.id)
        .where(CardBill.status.in_(("CONFIRMED", "OVERDUE")), User.status != "WITHDRAWN")
        .order_by(CardBill.payment_date, CardBill.user_card_id)).all()
    balance = dict(db.execute(select(AccountBalance.account_id, AccountBalance.balance)).all())
    running: dict[str, int] = {}
    made = []

    def add(user_id, card_id, event_id, type_, title, body):
        exists = db.scalar(select(Notification.id).where(Notification.event_id == event_id,
                                                         Notification.user_id == user_id, Notification.type == type_))
        if exists is None:
            n = Notification(id=new_id("ntf"), user_id=user_id, user_card_id=card_id, event_id=event_id, type=type_,
                             title=title, body=body, created_at=now)
            db.add(n)
            made.append(n.id)

    for bill, card, product, account_no, enabled in rows:
        due = bill.total_amount - bill.paid_amount
        acc = card.linked_account_id
        if acc:
            running[acc] = running.get(acc, 0) + due  # 이 청구서까지 이 계좌에서 빠질 돈
        days = (bill.payment_date - today).days
        if bill.status != "CONFIRMED" or days not in PAYMENT_ALERT_DAYS or enabled is False or due <= 0:
            continue
        name = f"{card.nickname or product}({card.last4})"
        event = bill.id if days else f"{bill.id}:D-0"
        when = "오늘" if days == 0 else f"{bill.payment_date.month}월 {bill.payment_date.day}일"
        add(card.user_id, card.id, event, "PAYMENT_DUE", f"{when} 카드 대금 결제 예정",
            f"{name} {due:,}원 · 결제 계좌 {account_no or '없음'}")
        short = running.get(acc, due) - balance.get(acc, 0) if acc else due
        if short > 0:
            add(card.user_id, card.id, event, "LOW_BALANCE", "카드 대금 낼 잔액이 모자라요",
                f"{when} {name} 대금이 빠져나가요. 결제 계좌에 {short:,}원을 더 채워 주세요.")
    return made


def _notify_once(db, made: list[str], *, user_id: str, card_id: str | None, event_id: str, type_: str, title: str, body: str,
                 now: datetime) -> None:
    """(event_id, user_id, type) 이 이미 있으면 만들지 않는다 — notifications 의 UNIQUE 와 같은 기준."""
    if db.scalar(select(Notification.id).where(Notification.event_id == event_id, Notification.user_id == user_id,
                                               Notification.type == type_)) is None:
        n = Notification(id=new_id("ntf"), user_id=user_id, user_card_id=card_id, event_id=event_id, type=type_,
                         title=title, body=body, created_at=now)
        db.add(n)
        made.append(n.id)


def notify_expiring_points(db, now: datetime) -> list[str]:
    """소멸 예정 포인트가 있고 소멸일이 오늘~30일 뒤인 포인트마다 POINT_EXPIRING 알림 한 번 (1-1-7, 사용자 결정 2026-11-11).
    event_id 는 '<포인트 id>_<소멸 연월>' — 시나리오 시드의 알림(pt_001_202611)과 같은 규칙이라 겹치지 않는다. 만든 알림 id."""
    today = now.date()
    made: list[str] = []
    rows = db.execute(select(CardPoint).join(User, User.id == CardPoint.user_id)
                      .where(CardPoint.expiring_amount > 0, CardPoint.balance > 0, CardPoint.expiring_date >= today,
                             CardPoint.expiring_date <= today + timedelta(days=POINT_EXPIRY_ALERT_DAYS),
                             User.status != "WITHDRAWN").order_by(CardPoint.id)).scalars().all()
    for pt in rows:
        amount, d = min(pt.expiring_amount, pt.balance), pt.expiring_date
        _notify_once(db, made, user_id=pt.user_id, card_id=None, event_id=f"{pt.id}_{d:%Y%m}", type_="POINT_EXPIRING",
                     title=f"{pt.point_name or '카드 포인트'} {amount:,}점이 곧 사라져요",
                     body=f"{d.month}월 {d.day}일에 소멸돼요. 현금으로 바꿔 보세요.", now=now)
    return made


def expire_points(db, now: datetime) -> list[str]:
    """소멸일이 지난(어제까지였던) 소멸 예정 포인트를 잔액에서 뺀다 — 잔액보다 크면 잔액까지 (사용자 결정 2026-11-11).
    소멸 예정 칸을 비우므로 다시 돌려도 또 빠지지 않는다. 소멸시킨 포인트 id."""
    rows = db.scalars(select(CardPoint).where(CardPoint.expiring_date < now.date())
                      .order_by(CardPoint.id).with_for_update(skip_locked=True)).all()
    for pt in rows:
        pt.balance -= min(pt.expiring_amount, pt.balance)
        pt.expiring_amount, pt.expiring_date = 0, None
    return [pt.id for pt in rows]


ANNUAL_FEE_CARD_STATUS = ("ACTIVE", "SUSPENDED", "LOST")  # 해지·만료한 카드는 연회비가 없다


def _annual_fee_cards(until: date):
    """연회비가 있고 청구 예정일이 until 까지인 신용카드 (카드, 상품 이름). 체크카드는 연회비가 모두 0원이라 대상이 아니다."""
    return (select(UserCard, CardProduct.name).join(CardProduct, CardProduct.id == UserCard.card_product_id)
            .join(User, User.id == UserCard.user_id)
            .where(UserCard.source == "TOSS_ISSUED", UserCard.status.in_(ANNUAL_FEE_CARD_STATUS),
                   UserCard.annual_fee_amount > 0, UserCard.next_annual_fee_date <= until,
                   CardProduct.card_type == "CREDIT", User.status != "WITHDRAWN").order_by(UserCard.id))


def notify_annual_fees(db, now: datetime) -> list[str]:
    """연회비 청구 예정일이 30일 안으로 들어온 신용카드마다 ANNUAL_FEE 알림 한 번 (1-1-8 「D-30 알림」).
    event_id 는 '<카드 id>:AF:<청구 예정일>' 이라 해마다 한 번씩 간다. 만든 알림 id."""
    today = now.date()
    made: list[str] = []
    rows = db.execute(_annual_fee_cards(today + timedelta(days=ANNUAL_FEE_ALERT_DAYS))
                      .where(UserCard.next_annual_fee_date >= today)).all()
    for card, product in rows:
        d = card.next_annual_fee_date
        _notify_once(db, made, user_id=card.user_id, card_id=card.id, event_id=f"{card.id}:AF:{d:%Y%m%d}", type_="ANNUAL_FEE",
                     title=f"{card.nickname or product} 연회비가 곧 청구돼요",
                     body=f"{d.month}월 {d.day}일에 연회비 {card.annual_fee_amount:,}원이 이용내역에 올라가고, "
                          f"다음 카드 대금에 포함돼요.", now=now)
    return made


ANNUAL_FEE_MERCHANT = ("mer_annual_fee", "cat_annual_fee", "ANNUAL_FEE", "연회비")  # 가맹점 id · 업종 id · 업종 code · 이름


def _annual_fee_merchant(db) -> str:
    """연회비를 이용내역에 올릴 때 쓰는 가맹점(「연회비」) — 없으면 업종과 함께 만든다."""
    merchant_id, category_id, code, name = ANNUAL_FEE_MERCHANT
    if db.get(Merchant, merchant_id) is None:
        cat = db.scalar(select(Category).where(Category.code == code))
        if cat is None:
            cat = Category(id=category_id, code=code, name=name)
            db.add(cat)
            db.flush()
        db.add(Merchant(id=merchant_id, category_id=cat.id, name=name))
        db.flush()
    return merchant_id


def charge_annual_fees(db, now: datetime) -> list[str]:
    """청구 예정일(오늘 또는 지난)이 된 신용카드의 연회비를 청구한다 (사용자 결정 2026-11-11). 청구한 카드 id.

    - 청구 = 카드 이용내역(card_transactions)에 「연회비」 한 줄. 그래서 이번 기간 사용액 → 다음 청구서에 그대로 들어가고
      한도·낼 돈 계산(쓴 돈 = 이용내역 합계)이 바뀌지 않는다. 실적에서는 뺀다(is_performance_counted = FALSE).
    - 승인번호는 'AF<청구 예정일>' — (카드, 승인번호) UNIQUE 라 같은 해 연회비가 두 번 올라가지 않는다.
    - 청구한 뒤 next_annual_fee_date 를 1년 뒤로. 한 번에 한 해만 넘긴다(여러 해 밀렸으면 다음 실행들이 이어서 청구).
    """
    charged = []
    rows = db.execute(_annual_fee_cards(now.date()).with_for_update(of=UserCard, skip_locked=True)).all()
    merchant_id = _annual_fee_merchant(db) if rows else None
    for card, _ in rows:
        d = card.next_annual_fee_date
        approval_no = f"AF{d:%Y%m%d}"
        if db.scalar(select(CardTransaction.id).where(CardTransaction.user_card_id == card.id,
                                                      CardTransaction.approval_no == approval_no)) is None:
            db.add(CardTransaction(id=new_id("ctx"), user_card_id=card.id, merchant_id=merchant_id, approval_no=approval_no,
                                   transacted_at=now, amount=card.annual_fee_amount, installment_months=0,
                                   is_overseas=False, currency="KRW", status="APPROVED", canceled_amount=0,
                                   is_performance_counted=False))
        card.next_annual_fee_date = next_year(d)
        charged.append(card.id)
    return charged


if __name__ == "__main__":
    from app.common.db import SessionLocal

    with SessionLocal() as db:
        now = now_kst()
        ran = run_scheduled_transfers(db, now)
        purged = purge_withdrawn_users(db, now)
        settled = settle_pending_transfers(db, now)
        notified = notify_card_payments(db, now)  # 출금 전에 — 오늘 결제일 알림(D-0)이 출금보다 먼저 가게
        paid, overdue = pay_due_card_bills(db, now)
        matured, held = mature_subscriptions(db, now)
        point_alerts = notify_expiring_points(db, now)  # 소멸 처리 전에 — 알림이 먼저
        expired = expire_points(db, now)
        fee_alerts = notify_annual_fees(db, now)
        fees = charge_annual_fees(db, now)
        db.commit()
    print(f"예약 실행 {len(ran)}건 · 가명 처리 {len(purged)}명 · 처리중 이체 확정 {len(settled)}건 · 카드 결제일 알림 {len(notified)}건 · "
          f"카드 대금 출금 {len(paid)}건 · 연체 {len(overdue)}건 · 만기 지급 {len(matured)}건 · 만기 미룸 {len(held)}건 · "
          f"포인트 소멸 알림 {len(point_alerts)}건 · 포인트 소멸 {len(expired)}건 · 연회비 알림 {len(fee_alerts)}건 · 연회비 청구 {len(fees)}건")
