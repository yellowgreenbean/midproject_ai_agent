"""계좌 파트 API — 기획서 Part 2 9장 (ACCT-F01 계좌 개설, ACCT-F02 계좌 조회, ACCT-F03 잔액 조회, ACCT-F07 필터).

잔액은 거래 파트의 account_balances 를 직접 읽지 않고 account_balance_view 로만 읽는다(C-5 「계좌 잔액」).
"""

import logging
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import internal
from app.common import ledger
from app.common.idempotency import IdempotencyKey
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, account_not_found
from app.models import Account, AccountActivityLog, AccountBalanceView, NotificationPreference, User
from app.common.step_up import consume_step_up
from app.routers.notifications import notifications_enabled
from app.rules import ACCOUNT_NUMBER_PREFIX, ACCOUNT_OPEN_CONSENT, ACCOUNT_PRODUCT_NAMES, BANK_ACCOUNT_DIGITS, OUR_BANK, now_kst
from app.schemas import AccountDetailOut, AccountOut, BalanceOut
from app.security import new_id

router = APIRouter(tags=["accounts"])
log = logging.getLogger(__name__)

AccountId = Annotated[str, Path(alias="accountId")]
AccountStatus = Literal[Account.LIFECYCLE_STATUS_VALUES]  # type: ignore[valid-type]  # ACTIVE / SUSPENDED / CLOSED
AccountType = Literal[Account.ACCOUNT_TYPE_VALUES]  # type: ignore[valid-type]  # CHECKING / SAVINGS


def balance_unavailable() -> ApiError:
    # 잔액 원본이 없을 때 0원 같은 값으로 둔갑시키지 않는다(ACCT-F03 처리 규칙)
    return ApiError(503, "BALANCE_UNAVAILABLE", "잔액을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")


def _account_out(account: Account, balance: AccountBalanceView | None, model=AccountOut, **extra):
    if balance is None:
        raise balance_unavailable()
    return model(
        **{f: getattr(account, f) for f in model.model_fields if hasattr(account, f)},
        resAccountCurrency=balance.resAccountCurrency,
        resAccountBalance=balance.resAccountBalance,
        balance_as_of=balance.balance_as_of,
        **extra,
    )


# ACCT-F05 해지 거절 사유 (Part 2 9.3) — 화면 문구는 frontend/src/pages/accountArt.ts BLOCKER 와 같은 뜻
CLOSE_BLOCKER_TEXT = {
    "BALANCE_REMAINING": "잔액이 남아 있어요. 다른 계좌로 옮긴 뒤 해지할 수 있어요.",
    "PENDING_TRANSFER": "처리 중인 이체나 예약·자동이체가 있어요.",
    "LINKED_SUBSCRIPTION": "이 계좌에서 돈이 빠지는 예금·적금이 있어요. 만기나 중도 해지 뒤 해지할 수 있어요.",
    "LINKED_CARD": "이 계좌에 연결된 카드가 있어요. 카드 결제 계좌를 바꾸거나 카드를 해지해 주세요.",
}


def _blocked(db, reason: str, check, account: Account) -> bool:
    """다른 파트 점검 하나. 점검이 실패하면(오류·예외) 「막힘」으로 본다 — 확인 못 한 것을 「문제없음」으로 넘기지 않는다
    (탈퇴의 「연동 파트가 응답하지 않으면 충족으로 처리하지 않는다」와 같은 원칙, 사용자 결정 2026-11-10).
    점검마다 저장점을 둔다: PostgreSQL 은 쿼리 하나가 실패하면 트랜잭션 전체를 막으므로, 실패한 점검만 되돌리고 다음 점검을 잇는다."""
    try:
        with db.begin_nested():
            return bool(check(db, account.user_id, account.id))
    except Exception:
        log.exception("계좌 해지 점검 실패 — %s 로 막음 (account_id=%s)", reason, account.id)
        return True


# (사유 코드, 담당 파트의 점검) — 기획서의 계좌 단위 내부 API 자리. 지금은 같은 서버의 함수(app/internal.py)
CLOSE_CHECKS = (
    ("PENDING_TRANSFER", lambda db, u, a: any(internal.transfer_blockers(db, u, a))),  # 거래: (처리중 이체, 예약·자동이체)
    ("LINKED_SUBSCRIPTION", lambda db, u, a: internal.subscription_blockers(db, u, a)),  # 상품
    ("LINKED_CARD", lambda db, u, a: internal.card_blockers(db, u, a)),  # 카드
)


def close_blockers(db, account: Account, balance: int) -> list[str]:
    """지금 이 계좌의 해지를 막는 사유 코드. 기준은 회원 탈퇴 점검(app/internal.py)과 같고, 이 계좌만 본다.
    잔액은 부르는 쪽이 읽어 넘긴다 — 잔액을 못 읽으면 사유가 아니라 BALANCE_UNAVAILABLE(ACCT-F03 「둔갑시키지 않음」)."""
    if account.lifecycle_status == "CLOSED":
        return []
    reasons = ["BALANCE_REMAINING"] if balance != 0 else []
    return reasons + [reason for reason, check in CLOSE_CHECKS if _blocked(db, reason, check, account)]


def _with_balance():
    # SELECT a.*, v.* FROM accounts a LEFT JOIN account_balance_view v ON v.account_id = a.id
    return select(Account, AccountBalanceView).outerjoin(
        AccountBalanceView, AccountBalanceView.account_id == Account.id
    )


# ACCT-F02 · F07: 내 계좌 목록 (+ 잔액)
@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    db: DB,
    user_id: CurrentUserId,
    status: Annotated[AccountStatus | None, Query(description="없으면 해지(CLOSED)를 뺀 계좌")] = None,
    type: Annotated[AccountType | None, Query()] = None,
):
    stmt = _with_balance().where(Account.user_id == user_id)
    if status is None:
        # 해지 계좌는 기본 목록에서 분리해 이력으로만 본다(ACCT-F02 정상 흐름 5) → ?status=CLOSED
        stmt = stmt.where(Account.lifecycle_status != "CLOSED")
    else:
        stmt = stmt.where(Account.lifecycle_status == status)
    if type is not None:
        stmt = stmt.where(Account.account_type == type)
    rows = db.execute(stmt.order_by(Account.is_favorite.desc(), Account.id)).all()
    return [_account_out(a, b) for a, b in rows]


# ACCT-F02: 계좌 상세 (+ 잔액, 해지 막힘 사유)
@router.get("/accounts/{accountId}", response_model=AccountDetailOut)
def get_account(account_id: AccountId, db: DB, user_id: CurrentUserId):
    row = db.execute(_with_balance().where(Account.id == account_id, Account.user_id == user_id)).first()
    if row is None:
        raise account_not_found()
    account, balance = row
    blockers = close_blockers(db, account, balance.resAccountBalance) if balance is not None else []
    return _account_out(account, balance, AccountDetailOut, close_blockers=blockers,
                        notifications_enabled=notifications_enabled(db, account))


# ACCT-F03: 잔액만 (읽기 전용)
@router.get("/accounts/{accountId}/balance", response_model=BalanceOut)
def get_balance(account_id: AccountId, db: DB, user_id: CurrentUserId):
    row = db.execute(_with_balance().where(Account.id == account_id, Account.user_id == user_id)).first()
    if row is None:
        raise account_not_found()
    if row[1] is None:
        raise balance_unavailable()
    return row[1]


# ---- ACCT-F01: 계좌 개설 ----

class OpenAccountIn(BaseModel):
    # Literal 로 두면 잘못된 유형이 VALIDATION_ERROR 가 된다 — 기획서 9.3 의 INVALID_ACCOUNT_TYPE 으로 답하려고 직접 검사한다
    account_type: str = Field(max_length=30)
    consents: list[str] = Field(default_factory=list, max_length=10)
    # 개설 직전 본인 확인(PIN 이나 로그인 비밀번호, action ACCOUNT_OPEN — 사용자 결정 2026-11-10). 없으면 STEP_UP_REQUIRED
    step_up_challenge_id: str | None = Field(default=None, max_length=40)


def _new_account_number() -> tuple[str, str]:
    """(resAccount 14자리 숫자, resAccountDisplay 110-XXXXX-XXXXXX). 일련번호가 아니라 무작위 — 동시 개설에서 겹치지 않게."""
    rest = BANK_ACCOUNT_DIGITS[OUR_BANK] - len(ACCOUNT_NUMBER_PREFIX)
    number = ACCOUNT_NUMBER_PREFIX + str(secrets.randbelow(10**rest)).zfill(rest)
    return number, f"{number[:3]}-{number[3:8]}-{number[8:]}"


def _opened_with_key(db, user_id: str, key: str) -> AccountActivityLog | None:
    # 멱등 키는 accounts 에 칸이 없어 개설 기록(OPEN)의 metadata 에 둔다. 회원마다 따로 본다(다른 사람의 키와 섞이지 않게)
    return db.scalar(select(AccountActivityLog).where(
        AccountActivityLog.action == "OPEN", AccountActivityLog.actor_id == user_id,
        AccountActivityLog.metadata_["idempotency_key"].astext == key))


@router.post("/accounts", response_model=AccountDetailOut, status_code=201)
def open_account(body: OpenAccountIn, login: CurrentLogin, db: DB,
                 idempotency_key: IdempotencyKey):
    user_id = login.user.id
    if body.account_type not in ACCOUNT_PRODUCT_NAMES:
        raise ApiError(422, "INVALID_ACCOUNT_TYPE", "계좌 유형을 다시 선택해 주세요.")
    if ACCOUNT_OPEN_CONSENT not in body.consents:
        raise ApiError(422, "REQUIRED_TERMS_NOT_AGREED", "필수 약관에 동의해 주세요.")

    # 회원 행을 잠가 같은 회원의 개설 요청을 한 줄로 세운다 — 같은 키로 동시에 온 두 요청이 둘 다 「처음」으로 보이지 않게
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if done := _opened_with_key(db, user_id, idempotency_key):
        if done.metadata_.get("account_type") != body.account_type:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 다른 내용으로 보낸 요청 번호예요. 처음부터 다시 만들어 주세요.")
        return get_account(done.account_id, db, user_id)  # 응답을 못 받고 다시 눌러도 처음 만든 계좌를 보여 준다
    if user.status != "ACTIVE":  # RESTRICTED 는 정리 동작만 (Part 1 7.3)
        raise ApiError(403, "USER_NOT_ACTIVE", "지금 계정 상태에서는 계좌를 만들 수 없어요.")
    # 같은 키의 재요청(위)은 이미 쓴 번호로도 처음 계좌를 돌려주고, 새로 만들 때만 번호를 쓴다
    consume_step_up(db, body.step_up_challenge_id, login, "ACCOUNT_OPEN")

    for _ in range(5):  # 이미 있는 번호가 나오면 다시 뽑는다 (14자리 무작위라 거의 없음)
        number, display = _new_account_number()
        if db.scalar(select(Account.id).where(Account.resAccount == number)) is None:
            break
    else:
        raise ApiError(503, "ACCOUNT_NUMBER_UNAVAILABLE", "계좌번호를 만들지 못했어요. 잠시 후 다시 시도해 주세요.")

    now = now_kst()
    account = Account(id=new_id("acc"), user_id=user_id, resAccount=number, resAccountDisplay=display,
                      resAccountName=ACCOUNT_PRODUCT_NAMES[body.account_type], account_type=body.account_type,
                      lifecycle_status="ACTIVE", resAccountNickName=None, is_favorite=False,
                      resAccountStartDate=now.strftime("%Y%m%d"), closed_at=None)
    db.add(account)
    db.flush()  # 모델에 relationship 이 없어 계좌를 먼저 넣는다(아래 행들이 외래 키로 가리킴)
    ledger.open_balance(db, account.id, now)
    db.add(NotificationPreference(user_id=user_id, account_id=account.id))  # 알림 기본값(전부 켬) — 시드와 같다
    db.add(AccountActivityLog(id=new_id("aal"), account_id=account.id, actor_id=user_id, action="OPEN", occurred_at=now,
                              metadata_={"account_type": body.account_type, "idempotency_key": idempotency_key,
                                         "consents": [ACCOUNT_OPEN_CONSENT]}))
    try:
        db.commit()
    except IntegrityError:  # 다른 요청이 같은 계좌번호를 막 가져갔다 — 아무것도 남지 않았으니 같은 키로 다시 보내면 된다
        db.rollback()
        raise ApiError(409, "CONFLICT_RETRY", "다른 요청과 겹쳤어요. 잠시 후 다시 시도해 주세요.")
    return get_account(account.id, db, user_id)


class StepUpBody(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


# ---- ACCT-F05: 계좌 상태 관리 — 셋 다 본인 확인(ACCOUNT_STATUS_CHANGE)이 필요하고, 바뀐 상태를 활동 기록에 남긴다 ----
#   일시정지 ACTIVE → SUSPENDED · 정지 해제 SUSPENDED → ACTIVE · 해지 ACTIVE → CLOSED (SUSPENDED 는 정지 해제 뒤에)
# 회원 상태: 셋 다 정리·보호 동작이라 RESTRICTED 도 된다(Part 1 7.3). 본인 확인 번호는 요청이 실패하면 롤백돼 다시 쓸 수 있다.

def _lock_mine(db, account_id: str, user_id: str) -> Account:
    # 상태 변경끼리 겹치지 않게 계좌 행을 잠근다. 남의 계좌는 없는 계좌와 같은 404.
    # populate_existing: 같은 요청에서 먼저 읽어 둔 계좌라도 잠근 뒤의 값으로 다시 채운다
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user_id)
                        .with_for_update().execution_options(populate_existing=True))
    if account is None:
        raise account_not_found()
    return account


def _log(db, account: Account, actor_id: str, action: str, **metadata) -> None:
    db.add(AccountActivityLog(id=new_id("aal"), account_id=account.id, actor_id=actor_id, action=action,
                              occurred_at=now_kst(), metadata_={"from_status": account.lifecycle_status, **metadata}))


def invalid_transition(message: str) -> ApiError:
    return ApiError(409, "INVALID_STATUS_TRANSITION", message)


@router.post("/accounts/{accountId}/suspend", response_model=AccountDetailOut)
def suspend_account(account_id: AccountId, body: StepUpBody, login: CurrentLogin, db: DB):
    account = _lock_mine(db, account_id, login.user.id)
    consume_step_up(db, body.step_up_challenge_id, login, "ACCOUNT_STATUS_CHANGE")
    if account.lifecycle_status == "SUSPENDED":  # 이미 정지 — 현재 상태를 안내(ACCT-F05 예외/오류)
        raise ApiError(409, "ACCOUNT_ALREADY_SUSPENDED", "이미 일시정지된 계좌예요.")
    if account.lifecycle_status != "ACTIVE":
        raise invalid_transition("해지한 계좌는 일시정지할 수 없어요.")
    _log(db, account, login.user.id, "SUSPEND")
    account.lifecycle_status = "SUSPENDED"  # 거래 파트는 이체·납입·카드 결제 때 이 상태를 보고 입금·출금을 모두 막는다(10.3)
    db.commit()
    return get_account(account_id, db, login.user.id)


# 정지 해제는 회원 탈퇴 ①(정지 계좌의 남은 돈 옮기기)의 첫 단계이기도 하다
@router.post("/accounts/{accountId}/resume", response_model=AccountDetailOut)
def resume_account(account_id: AccountId, body: StepUpBody, login: CurrentLogin, db: DB):
    account = _lock_mine(db, account_id, login.user.id)
    consume_step_up(db, body.step_up_challenge_id, login, "ACCOUNT_STATUS_CHANGE")
    if account.lifecycle_status != "SUSPENDED":
        raise ApiError(409, "ACCOUNT_NOT_SUSPENDED", "정지된 계좌가 아니에요.")
    _log(db, account, login.user.id, "RESUME")
    account.lifecycle_status = "ACTIVE"
    db.commit()
    return get_account(account_id, db, login.user.id)


@router.post("/accounts/{accountId}/close", response_model=AccountDetailOut)
def close_account(account_id: AccountId, body: StepUpBody, login: CurrentLogin, db: DB):
    if db.scalar(select(Account.id).where(Account.id == account_id, Account.user_id == login.user.id)) is None:
        raise account_not_found()  # 남의 계좌는 잠그기 전에 거른다
    consume_step_up(db, body.step_up_challenge_id, login, "ACCOUNT_STATUS_CHANGE")
    # 잔액 행 → 계좌 행 순서로 잠근다. 잔액을 바꾸거나 계좌를 해지하는 다른 곳(이체·탈퇴 일괄 해지·중도 해지)이 모두
    # 잔액 행을 먼저 잠그므로, 순서를 맞춰야 서로 상대 잠금을 기다리다 멈추지(데드락) 않는다.
    # 둘 다 잠근 채로 검사·해지한다 — 그 사이에 이체가 돈을 넣거나 빼지 못하게(7.3 「시점/동시성 보장」)
    bal = ledger.lock_balances(db, [account_id]).get(account_id)
    account = _lock_mine(db, account_id, login.user.id)
    if account.lifecycle_status == "CLOSED":
        raise invalid_transition("이미 해지한 계좌예요.")
    if account.lifecycle_status == "SUSPENDED":  # 확정: 사용자 해지는 정지 해제가 먼저 (탈퇴 일괄 해지만 예외 — app/internal.py)
        raise invalid_transition("일시정지된 계좌는 정지를 해제한 뒤에 해지할 수 있어요.")
    if bal is None:
        raise balance_unavailable()
    if reasons := close_blockers(db, account, bal.balance):
        raise ApiError(409, "ACCOUNT_CLOSE_NOT_ALLOWED", " ".join(CLOSE_BLOCKER_TEXT[r] for r in reasons), reasons=reasons)
    _log(db, account, login.user.id, "CLOSE", reason="사용자 해지")
    # 해지 ≠ 삭제: 행과 별명·거래 기록은 남긴다. 즐겨찾기만 푼다(해지 계좌는 기본 목록에서 빠지므로)
    account.lifecycle_status, account.closed_at, account.is_favorite = "CLOSED", now_kst().strftime("%Y%m%d"), False
    db.commit()
    return get_account(account_id, db, login.user.id)
