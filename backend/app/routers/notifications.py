"""알림 — 기획서 Part 2 ACCT-F06 입출금 알림(기본) · ACCT-F12 설정 칸, Part 5 TRX-F04 거래 확정 이벤트.

    GET   /notifications                                   내 알림 최근 100개 (모든 종류)
    POST  /notifications/read-all                          모두 읽음 (화면 「알림」, 사용자 결정 2026-11-10 — 기획서 9장에 없던 주소)
    GET   /accounts/{accountId}/notification-settings      계좌 알림 설정 (행이 없으면 기본값: 전부 켬, 최소 금액 0)
    PATCH /accounts/{accountId}/notification-settings      켜기·끄기 · 입금/출금 · 최소 금액 (해지 계좌는 409)

거래 확정 이벤트: 거래 파트 원장(app/ledger.post)이 한 줄 기록할 때마다 on_transaction_confirmed() 를 부른다.
지금은 서버가 하나라 메시지 큐 대신 같은 트랜잭션 안의 함수 호출이다 — 거래가 롤백되면 알림도 같이 사라져
「확정 전 알림」이 생기지 않는다(ACCT-F06 처리 규칙). 알림을 못 만들어도 거래는 그대로 둔다(로그만).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.common.ownership import get_owned_account_or_404
from app.deps import DB, CurrentUserId
from app.errors import ApiError
from app.models import Account, Notification, NotificationPreference, Transaction
from app.rules import INCOMING_TYPES, now_kst
from app.common.naming import KstDatetime, Money
from app.security import new_id

router = APIRouter(tags=["notifications"])
log = logging.getLogger(__name__)
AccountId = Annotated[str, Path(alias="accountId")]

TYPE_LABEL = {  # Part 5 3장 거래 유형 → 알림 제목
    "TRANSFER_IN": "입금", "TRANSFER_OUT": "출금", "CARD_PAYMENT": "카드 출금", "POINT_CASHOUT": "포인트 입금",
    "SUBSCRIPTION_PAYMENT": "예금·적금 납입", "SUBSCRIPTION_PAYOUT": "예금·적금 지급",
}


def notify(db, *, user_id: str, account_id: str | None, event_id: str, title: str, body: str) -> None:
    """TRANSACTION 알림 한 건. (event_id, user_id, type) 이 겹치면 만들지 않는다(같은 이벤트 두 번 → 한 번)."""
    if db.scalar(select(Notification.id).where(Notification.event_id == event_id, Notification.user_id == user_id,
                                               Notification.type == "TRANSACTION")) is None:
        db.add(Notification(id=new_id("ntf"), user_id=user_id, account_id=account_id, event_id=event_id,
                            type="TRANSACTION", title=title, body=body, created_at=now_kst()))


def on_transaction_confirmed(db, tx: Transaction) -> None:
    """거래 확정 이벤트 수신 → 계좌 알림 설정(켬·입금/출금·최소 금액)을 보고 알림을 만든다(ACCT-F06·F12 평가 흐름)."""
    try:
        account = db.get(Account, tx.account_id)
        pref = db.get(NotificationPreference, (account.user_id, account.id))  # 없으면 기본값 = 전부 켬
        incoming = tx.type in INCOMING_TYPES
        if pref is not None and (not pref.enabled or tx.amount < pref.minimum_amount
                                 or not (pref.deposit_enabled if incoming else pref.withdrawal_enabled)):
            return
        name = account.resAccountNickName or account.resAccountName
        notify(db, user_id=account.user_id, account_id=account.id, event_id=tx.id,
               title=f"{TYPE_LABEL.get(tx.type, tx.type)} {tx.amount:,}원",
               body=f"{name}(…{account.resAccount[-4:]}) · {tx.display_name or ''} · 잔액 {tx.balance_after:,}원")
    except Exception:  # 알림 실패가 거래를 되돌리면 안 된다(ACCT-F06 예외/오류)
        log.exception("입출금 알림을 만들지 못함 (transaction_id=%s)", tx.id)


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: str
    account_id: str | None
    user_card_id: str | None  # 카드 알림이면 그 카드 (연회비 알림 → 카드 상세)
    event_id: str | None  # 원인 (거래 id · 이체 id · 청구서 id — 화면이 이동할 곳을 고른다)
    created_at: KstDatetime
    read: bool


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: DB, user_id: CurrentUserId):
    rows = db.scalars(select(Notification).where(Notification.user_id == user_id)
                      .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(100))
    return [NotificationOut(id=n.id, type=n.type, title=n.title, body=n.body, account_id=n.account_id, user_card_id=n.user_card_id,
                            event_id=n.event_id,
                            created_at=n.created_at, read=n.read_at is not None) for n in rows]


@router.post("/notifications/read-all", status_code=204)
def read_all_notifications(db: DB, user_id: CurrentUserId):
    db.execute(update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
               .values(read_at=now_kst()))
    db.commit()


class SettingsOut(BaseModel):
    account_id: str
    enabled: bool
    deposit_enabled: bool
    withdrawal_enabled: bool
    minimum_amount: Money


class SettingsIn(BaseModel):
    enabled: bool | None = None
    deposit_enabled: bool | None = None
    withdrawal_enabled: bool | None = None
    minimum_amount: int | None = Field(default=None, ge=0)


def _settings(db, account: Account) -> SettingsOut:
    p = db.get(NotificationPreference, (account.user_id, account.id))
    return SettingsOut(account_id=account.id, enabled=p.enabled if p else True,
                       deposit_enabled=p.deposit_enabled if p else True,
                       withdrawal_enabled=p.withdrawal_enabled if p else True, minimum_amount=p.minimum_amount if p else 0)


def notifications_enabled(db, account: Account) -> bool:
    """계좌 상세 화면의 「입출금 알림」 스위치."""
    return _settings(db, account).enabled


@router.get("/accounts/{accountId}/notification-settings", response_model=SettingsOut)
def get_notification_settings(account_id: AccountId, db: DB, user_id: CurrentUserId):
    return _settings(db, get_owned_account_or_404(db, account_id, user_id))


@router.patch("/accounts/{accountId}/notification-settings", response_model=SettingsOut)
def update_notification_settings(account_id: AccountId, body: SettingsIn, db: DB, user_id: CurrentUserId):
    account = get_owned_account_or_404(db, account_id, user_id)
    if account.lifecycle_status == "CLOSED":  # ACCT-F04 「CLOSED 계좌에 대한 설정 변경은 불허」
        raise ApiError(409, "INVALID_STATUS_TRANSITION", "해지한 계좌는 알림 설정을 바꿀 수 없어요.")
    p = db.get(NotificationPreference, (user_id, account_id))
    if p is None:
        p = NotificationPreference(user_id=user_id, account_id=account_id, enabled=True, deposit_enabled=True,
                                   withdrawal_enabled=True, minimum_amount=0)
        db.add(p)
    for field in body.model_fields_set:
        if getattr(body, field) is not None:
            setattr(p, field, getattr(body, field))
    db.commit()
    return _settings(db, account)
