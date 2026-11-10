"""회원 탈퇴 — 기획서 Part 1 AUTH-F09 (탈퇴 전 필수 3단계), 7장 API, UI07.

    GET  /users/me/withdrawal-checks                    ①②③ 상태와 막는 항목 (서버가 매번 다시 본다)
    POST /users/me/withdrawal-checks/data-review        ② 삭제될 데이터 안내를 읽었다 (안내문 버전 기록)
    POST /users/me/withdrawal-checks/linked-services    ③ 연결된 서비스 안내를 읽었다 (막는 항목이 0개일 때만)
    POST /users/me/withdraw                             최종 확인: 본인 확인(WITHDRAWAL) → ①②③ 다시 검사 → 남은 계좌 일괄 해지
                                                        → WITHDRAWN · 모든 세션 끊기 · 동의 철회 · 즉시 삭제 (한 트랜잭션)

① 남은 돈: 해지 안 된 계좌 잔액이 모두 0원 · 처리중(PENDING) 이체 없음 · 진행 중 예금·적금 없음
② 데이터: 지금 버전(rules.WITHDRAWAL_DATA_REVIEW_VERSION)의 안내를 확인함 — 버전이 바뀌면 다시
③ 연결: 실행 대기 예약 송금 · 활성/일시정지 자동이체 · 해지 안 된 우리 카드 = 0개 + 안내 확인
다른 파트의 상태는 app/internal.py(기획서의 /internal API 자리)로만 묻는다.
회원 상태: ACTIVE·RESTRICTED 가능(정리 동작, 7.3), PENDING_VERIFICATION 도 가능(가입 취소, 7.3 — 계좌·카드가 없음).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from app import internal
from app.deps import DB, Login, get_login
from app.errors import ApiError
from app.models import (
    AuthSession,
    CardRecommendation,
    CardRecommendationDetail,
    CardPoint,
    DailyCardSpending,
    EmailVerification,
    FavoriteAccount,
    LocalCredential,
    MydataConsent,
    MydataSyncLog,
    Notification,
    NotificationPreference,
    PasswordResetToken,
    PinCredential,
    RecurringPayment,
    SpendingForecast,
    User,
    UserCard,
    UserCardSetting,
    UserConsent,
    WithdrawalCheck,
)
from app.routers.auth import _audit, _clear_session_cookie, consume_step_up
from app.rules import WITHDRAWAL_DATA_REVIEW_VERSION, now_kst
from app.schemas import KstDatetime
from app.security import new_id

router = APIRouter(prefix="/users/me", tags=["withdrawal"])
LoginDep = Annotated[Login, Depends(get_login)]  # PENDING_VERIFICATION 도 통과(가입 취소)


class CheckItem(BaseModel):
    """막는 항목 하나 — 화면이 그대로 목록으로 그리고, href 로 정리할 화면에 보낸다."""
    label: str
    detail: str
    href: str


class WithdrawalStatusOut(BaseModel):
    money_ok: bool
    money_items: list[CheckItem]
    data_review_version: str
    data_reviewed: bool
    linked_ok: bool
    linked_items: list[CheckItem]
    linked_confirmed: bool
    can_withdraw: bool


def won(n: int) -> str:
    return f"{n:,}원"


def money_items(db, user_id: str) -> list[CheckItem]:
    """① 남은 돈 옮기기를 막는 항목."""
    items = []
    for s in internal.account_readiness(db, user_id):
        if s.balance:
            a = s.account
            suspended = a.lifecycle_status == "SUSPENDED"
            items.append(CheckItem(
                label=f"{a.resAccountNickName or a.resAccountName} {a.resAccountDisplay}",
                detail=f"{won(s.balance)} 남아 있어요" + (" · 정지를 먼저 풀어야 옮길 수 있어요" if suspended else ""),
                href=f"#/accounts/{a.id}" if suspended else f"#/transfer?from={a.id}"))
    pending, _ = internal.transfer_blockers(db, user_id)
    items += [CheckItem(label="처리 중인 이체", detail=f"{t.to_holder_name}님께 {won(t.amount)} — 끝날 때까지 기다려 주세요",
                        href=f"#/transfers/{t.id}") for t in pending]
    items += [CheckItem(label=name, detail="만기 후 또는 중도 해지 후 탈퇴할 수 있어요", href=f"#/my/savings/{s.id}")
              for s, name in internal.subscription_blockers(db, user_id)]
    return items


def linked_items(db, user_id: str) -> list[CheckItem]:
    """③ 연결된 서비스 중 막는 항목 (토스처럼 자동·예약 이체를 먼저 정리해야 함)."""
    _, scheduled = internal.transfer_blockers(db, user_id)
    items = [CheckItem(
        label="자동이체" if s.type == "MONTHLY" else "예약 송금",
        detail=f"{s.to_holder_name}님께 " + (f"매월 {won(s.amount)}" if s.type == "MONTHLY" else won(s.amount))
               + " — 해지·취소해야 탈퇴할 수 있어요",
        href="#/scheduled-transfers") for s in scheduled]
    for c, name, owed in internal.card_blockers(db, user_id):
        if c.status == "TERMINATED":
            todo = f"남은 대금 {won(owed)}을 「지금 결제하기」로 내야"
        elif owed:
            todo = f"남은 대금 {won(owed)}을 「지금 결제하기」로 내고 카드를 해지해야"
        else:
            todo = "카드를 해지해야"
        items.append(CheckItem(label=f"{name} {c.card_number_masked}", detail=f"{todo} 탈퇴할 수 있어요",
                               href=f"#/cards/{c.id}"))
    return items


def open_check(db, user_id: str) -> WithdrawalCheck:
    """진행 중인 점검 행 (없으면 시작)."""
    row = db.scalar(select(WithdrawalCheck).where(WithdrawalCheck.user_id == user_id,
                                                  WithdrawalCheck.status == "IN_PROGRESS").limit(1))
    if row is None:
        row = WithdrawalCheck(id=new_id("wdc"), user_id=user_id, status="IN_PROGRESS", started_at=now_kst())
        db.add(row)
    return row


def evaluate(db, user_id: str) -> WithdrawalStatusOut:
    """①②③을 지금 DB 로 다시 판단한다. 화면의 「완료」 표시는 믿지 않는다(AUTH-F09 정상 흐름 7)."""
    row = open_check(db, user_id)
    money, linked = money_items(db, user_id), linked_items(db, user_id)
    if not money:
        row.balance_verified_at = now_kst()  # 서버가 잔액 0원을 확인한 시각 (사용자 주장이 아님)
    reviewed = row.data_review_confirmed_at is not None and row.data_review_version == WITHDRAWAL_DATA_REVIEW_VERSION
    confirmed = row.linked_services_confirmed_at is not None
    return WithdrawalStatusOut(
        money_ok=not money, money_items=money,
        data_review_version=WITHDRAWAL_DATA_REVIEW_VERSION, data_reviewed=reviewed,
        linked_ok=not linked and confirmed, linked_items=linked, linked_confirmed=confirmed,
        can_withdraw=not money and reviewed and not linked and confirmed)


@router.get("/withdrawal-checks", response_model=WithdrawalStatusOut)
def get_withdrawal_checks(login: LoginDep, db: DB):
    st = evaluate(db, login.user.id)
    db.commit()  # 점검 시작·잔액 확인 시각 저장
    return st


class DataReviewIn(BaseModel):
    version: str = Field(max_length=20)


@router.post("/withdrawal-checks/data-review", response_model=WithdrawalStatusOut)
def confirm_data_review(body: DataReviewIn, login: LoginDep, db: DB):
    if body.version != WITHDRAWAL_DATA_REVIEW_VERSION:
        raise ApiError(409, "DATA_REVIEW_OUTDATED", "안내 내용이 바뀌었어요. 새로고침해서 다시 읽고 확인해 주세요.")
    row = open_check(db, login.user.id)
    row.data_review_confirmed_at, row.data_review_version = now_kst(), body.version
    st = evaluate(db, login.user.id)
    db.commit()
    return st


@router.post("/withdrawal-checks/linked-services", response_model=WithdrawalStatusOut)
def confirm_linked_services(login: LoginDep, db: DB):
    if linked_items(db, login.user.id):
        raise ApiError(409, "LINKED_SERVICES_REMAIN", "자동이체·예약 송금·카드를 먼저 정리해 주세요.")
    open_check(db, login.user.id).linked_services_confirmed_at = now_kst()
    st = evaluate(db, login.user.id)
    db.commit()
    return st


class WithdrawIn(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)


class WithdrawOut(BaseModel):
    user_id: str
    status: str
    withdrawn_at: KstDatetime
    closed_account_ids: list[str]


@router.post("/withdraw", response_model=WithdrawOut)
def withdraw(body: WithdrawIn, login: LoginDep, response: Response, db: DB):
    user = db.get(User, login.user.id, with_for_update=True)  # 같은 회원의 탈퇴 요청이 동시에 와도 한 번만
    consume_step_up(db, body.step_up_challenge_id, login, "WITHDRAWAL")

    # 1. ①②③ 다시 검사. 잔액 행을 먼저 잠가 검사~해지 사이에 입금이 끼어들지 못하게 한다
    internal.account_readiness(db, user.id, lock=True)
    st = evaluate(db, user.id)
    if not st.can_withdraw:
        step = ("① 남은 돈 옮기기" if not st.money_ok else "② 삭제될 데이터 확인하기" if not st.data_reviewed
                else "③ 연결된 서비스 확인하기")
        raise ApiError(409, "WITHDRAWAL_NOT_READY", f"{step}를 먼저 마쳐 주세요.")

    # 2. 남은 계좌 일괄 해지 (계좌 파트). 실패하면 아무것도 바꾸지 않는다(롤백)
    try:
        closed = internal.close_for_withdrawal(db, user.id)
    except ValueError:
        raise ApiError(409, "WITHDRAWAL_NOT_READY", "그 사이 계좌에 돈이 들어왔어요. 남은 돈을 옮긴 뒤 다시 해 주세요.")

    # 3. 회원 상태 · 세션 · 점검 기록
    now = now_kst().replace(microsecond=0)  # DB 칸이 TIMESTAMP(0) — 응답도 저장된 값과 같게
    user.status, user.withdrawn_at = "WITHDRAWN", now
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
               .values(revoked_at=now))  # 모든 기기에서 로그아웃. 행은 본인 확인 기록이 가리켜서 지우지 않는다
    check = open_check(db, user.id)
    check.status, check.completed_at = "COMPLETED", now

    # 4. 모든 동의 철회 — 지금 동의 중인 약관마다 agreed=false 행을 더한다(이력은 남김, AUTH-F10)
    latest: dict[str, UserConsent] = {}
    for c in db.scalars(select(UserConsent).where(UserConsent.user_id == user.id).order_by(UserConsent.recorded_at)):
        latest[c.terms_id] = c
    for c in latest.values():
        if c.agreed:
            db.add(UserConsent(id=new_id("cns"), user_id=user.id, terms_id=c.terms_id, version=c.version, agreed=False,
                               recorded_at=now))

    # 5. 즉시 삭제 (AUTH-F09 ② 「즉시 삭제」, 사용자 결정 2026-11-09: 카드 파트 것도) — 자식 표부터
    purge_now(db, user.id, user.email)
    _audit(db, user.id, "WITHDRAWAL", "SUCCESS", uuid.uuid4().hex)
    db.commit()

    _clear_session_cookie(response)
    return WithdrawOut(user_id=user.id, status=user.status, withdrawn_at=now, closed_account_ids=closed)


def purge_now(db, user_id: str, email: str | None) -> None:
    """탈퇴 즉시 지우는 편의 설정·계산 결과. 돈이 오간 기록(계좌·거래·이체·카드 이용·청구·가입)은 5년 보존이라 건드리지 않는다.
    세션·본인 확인 기록은 이체·카드 기록이 외래 키로 가리켜 남긴다(세션은 위에서 끊음)."""
    my_cards = select(UserCard.id).where(UserCard.user_id == user_id)
    my_recs = select(CardRecommendation.id).where(CardRecommendation.user_id == user_id)
    my_mydata = select(MydataConsent.id).where(MydataConsent.user_id == user_id)
    for stmt in (
        # 회원·인증
        delete(LocalCredential).where(LocalCredential.user_id == user_id),
        delete(PinCredential).where(PinCredential.user_id == user_id),
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id),
        delete(EmailVerification).where(EmailVerification.email == email),
        # 계좌 · 거래 (계좌 별명·즐겨찾기는 close_for_withdrawal 이 지움)
        delete(NotificationPreference).where(NotificationPreference.user_id == user_id),
        delete(Notification).where(Notification.user_id == user_id),
        delete(FavoriteAccount).where(FavoriteAccount.user_id == user_id),
        # 카드 — 설정·별명·추천·예측·고정지출 탐지·포인트 잔액·마이데이터 연동
        delete(UserCardSetting).where(UserCardSetting.user_card_id.in_(my_cards)),
        update(UserCard).where(UserCard.user_id == user_id).values(nickname=None),
        delete(CardRecommendationDetail).where(CardRecommendationDetail.recommendation_id.in_(my_recs)),
        delete(CardRecommendation).where(CardRecommendation.user_id == user_id),  # 발급 신청은 ON DELETE SET NULL
        delete(SpendingForecast).where(SpendingForecast.user_card_id.in_(my_cards)),
        delete(DailyCardSpending).where(DailyCardSpending.user_card_id.in_(my_cards)),
        delete(RecurringPayment).where(RecurringPayment.user_id == user_id),
        delete(CardPoint).where(CardPoint.user_id == user_id),  # 현금화 기록은 ON DELETE SET NULL 로 남음
        delete(MydataSyncLog).where(MydataSyncLog.mydata_consent_id.in_(my_mydata)),
        delete(MydataConsent).where(MydataConsent.user_id == user_id),
    ):
        db.execute(stmt.execution_options(synchronize_session=False))
