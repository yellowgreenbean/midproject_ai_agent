"""다른 파트에 묻는 탈퇴 점검 — 기획서의 내부 API 자리 (Part 1 AUTH-F09 「담당 파트에 조회」, 9장 연동 표).

    기획서 경로                                               여기 함수                     담당 파트
    GET  /internal/users/{userId}/account-readiness           account_readiness()           계좌 (Part 2 10.3)
    GET  /internal/users/{userId}/transfer-blockers           transfer_blockers()           거래 (Part 5 16장)
    GET  /internal/users/{userId}/subscription-blockers       subscription_blockers()       상품 (Part 3)
    GET  /internal/users/{userId}/card-blockers               card_blockers()               카드 (Part 4 1-3)
    POST /internal/users/{userId}/accounts/close-for-withdrawal  close_for_withdrawal()     계좌 (ACCT-F05 예외 해지)

사용자 결정 2026-11-09: 지금은 서버가 하나라 HTTP 대신 같은 서버 안의 함수로 둔다.
팀원 서버가 생기면 이 파일의 함수 안만 그 API 호출로 바꾸면 된다(부르는 쪽 routers/withdrawal.py 는 그대로).
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.models import (
    Account,
    AccountActivityLog,
    AccountBalance,
    CardProduct,
    Product,
    ScheduledTransfer,
    Subscription,
    Transfer,
    UserCard,
)
from app.rules import now_kst
from app.security import new_id


@dataclass
class AccountState:
    account: Account
    balance: int  # 확정 잔액 (account_balances, 원)


def account_readiness(db, user_id: str, lock: bool = False) -> list[AccountState]:
    """해지 안 된 계좌와 잔액. lock=True 면 잔액 행을 잠가, 탈퇴 확정 중에 돈이 들어오지 못하게 한다."""
    mine = (Account.user_id == user_id, Account.lifecycle_status != "CLOSED")
    if lock:  # PostgreSQL 은 LEFT JOIN 의 빈칸 쪽을 FOR UPDATE 로 잠글 수 없어서 잔액 행만 따로 잠근다
        db.execute(select(AccountBalance.account_id).join(Account, Account.id == AccountBalance.account_id)
                   .where(*mine).with_for_update(of=AccountBalance))
    q = (select(Account, AccountBalance.balance).outerjoin(AccountBalance, AccountBalance.account_id == Account.id)
         .where(*mine).order_by(Account.id))
    return [AccountState(a, bal or 0) for a, bal in db.execute(q)]


def transfer_blockers(db, user_id: str) -> tuple[list[Transfer], list[ScheduledTransfer]]:
    """(① 처리중 이체, ③ 실행 대기 예약 송금·활성/일시정지 자동이체)."""
    pending = list(db.scalars(select(Transfer).where(Transfer.user_id == user_id, Transfer.status == "PENDING")
                              .order_by(Transfer.requested_at)))
    scheduled = list(db.scalars(select(ScheduledTransfer).where(
        ScheduledTransfer.user_id == user_id,
        ScheduledTransfer.status.in_(("SCHEDULED", "PROCESSING", "ACTIVE", "PAUSED"))).order_by(ScheduledTransfer.id)))
    return pending, scheduled


def subscription_blockers(db, user_id: str) -> list[tuple[Subscription, str]]:
    """만기·해지 전인 예금·적금 가입과 상품 이름."""
    return list(db.execute(select(Subscription, Product.name).join(Product, Product.id == Subscription.product_id)
                           .where(Subscription.user_id == user_id, Subscription.status == "ACTIVE")
                           .order_by(Subscription.id)))


def card_blockers(db, user_id: str) -> list[tuple[UserCard, str, int]]:
    """(카드, 상품 이름, 아직 낼 돈) — 해지 안 된 우리 발급 카드, 그리고 해지했어도 낼 대금이 남은 카드.
    마이데이터로 연동만 한 타사 카드(MYDATA)는 막지 않는다(Part 4 1-3).
    해지 뒤 남은 대금도 막는 것은 사용자 결정 2026-11-09(Q5): 탈퇴로 결제 계좌가 해지되면 청구할 곳이 없어지므로."""
    from app.routers.cards import card_money  # 카드 파트의 계산을 그대로 쓴다

    rows = db.execute(select(UserCard, CardProduct.name, CardProduct.card_type)
                      .join(CardProduct, CardProduct.id == UserCard.card_product_id)
                      .where(UserCard.user_id == user_id, UserCard.source == "TOSS_ISSUED").order_by(UserCard.id))
    out = []
    for card, name, card_type in rows:
        owed = card_money(db, card, card_type).owed
        if card.status != "TERMINATED" or owed:
            out.append((card, name, owed))
    return out


def close_for_withdrawal(db, user_id: str) -> list[str]:
    """남은 계좌를 모두 해지(CLOSED)하고 해지 사유 「회원 탈퇴」를 계좌 활동 기록에 남긴다. 해지한 계좌 id 목록을 돌려준다.
    잔액 0원 SUSPENDED 계좌도 정지 해제 없이 해지한다 — 이 경로에서만 쓰는 예외(ACCT-F05, 확정).
    잔액이 남은 계좌가 있으면 하나도 해지하지 않고 ValueError (부르는 쪽이 탈퇴를 중단한다)."""
    states = account_readiness(db, user_id, lock=True)
    if any(s.balance != 0 for s in states):
        raise ValueError("잔액이 남은 계좌가 있어 일괄 해지할 수 없음")
    now = now_kst()
    for s in states:
        a = s.account
        db.add(AccountActivityLog(id=new_id("aal"), account_id=a.id, actor_id="system", action="CLOSE", occurred_at=now,
                                  metadata_={"reason": "회원 탈퇴", "from_status": a.lifecycle_status}))
        a.lifecycle_status, a.closed_at = "CLOSED", now.strftime("%Y%m%d")
        a.is_favorite, a.resAccountNickName = False, None  # 계좌 별명·즐겨찾기는 즉시 삭제 대상(AUTH-F09 ②)
    return [s.account.id for s in states]
