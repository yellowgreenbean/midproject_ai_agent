"""숨은 카드 포인트 조회 · 현금화 — 기획서 Part 4 1-1-7 (CARD-F12).

    GET  /card-points                       내 카드사별 포인트(잔액·소멸 예정) + 현금화 내역(최신순)
    POST /card-points/{pointId}/cashout     전액 현금화 → 내 정상 입출금 계좌로 입금 (본인 확인 POINT_CASHOUT)

정한 것 (사용자 결정 2026-11-11)
- 금액: 그 카드사 포인트 **전액만**(1포인트 = 1원). 금액을 따로 받지 않는다.
- 포인트 출처: 마이데이터 연동(CARD-F10)이 아직 없어 DB 의 card_points(시나리오 시드) 그대로. 새로 쌓이지 않는다.
- 본인 확인(step-up, action = POINT_CASHOUT) 필수.
- 입금 계좌: 본인의 정상(ACTIVE) 입출금(CHECKING) 계좌만 — 카드 결제 계좌와 같은 규칙.
- 한 트랜잭션: point_cashouts REQUESTED → (모의 카드사 응답) COMPLETED + card_points.balance 0 + 원장 POINT_CASHOUT 입금.
  카드 파트는 계좌 잔액을 직접 바꾸지 않고 ledger.post() 로만 넣는다. 중간에 실패하면 전부 되돌아간다(본인 확인 번호도).
- 전액이라 같은 요청이 두 번 와도 두 번째는 잔액 0 → 409 NO_POINTS (포인트 행을 잠가 동시 요청도 한 번만).
- 남의 포인트·없는 포인트는 똑같이 404 POINT_NOT_FOUND.
- 소멸 예정 알림(30일 전 한 번)과 소멸 처리는 app/jobs.py 의 notify_expiring_points · expire_points.
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.common import ledger
from app.common.naming import KstDatetime, Money
from app.common.step_up import consume_step_up
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, CardCompany, CardPoint, PointCashout
from app.rules import now_kst
from app.security import new_id

router = APIRouter(tags=["cards"])


class PointOut(BaseModel):
    id: str
    company_name: str
    point_name: str
    balance: Money
    expiring_amount: Money  # 소멸 예정 포인트 (없으면 0)
    expiring_date: date | None
    synced_at: KstDatetime


class CashoutOut(BaseModel):
    id: str
    point_name: str
    amount: Money
    status: str
    account_id: str
    account_number: str
    requested_at: KstDatetime
    completed_at: KstDatetime | None


class PointsOut(BaseModel):
    points: list[PointOut]
    cashouts: list[CashoutOut]


def _name(pt: CardPoint | None, company: str | None) -> str:
    return (pt.point_name if pt else None) or (f"{company} 포인트" if company else "카드 포인트")


def _cashout_out(co: PointCashout, name: str, account: Account) -> CashoutOut:
    return CashoutOut(id=co.id, point_name=name, amount=co.amount, status=co.status, account_id=account.id,
                      account_number=account.resAccountDisplay, requested_at=co.requested_at, completed_at=co.completed_at)


@router.get("/card-points", response_model=PointsOut)
def list_card_points(db: DB, user_id: CurrentUserId):
    points = db.execute(select(CardPoint, CardCompany.name).join(CardCompany, CardCompany.id == CardPoint.card_company_id)
                        .where(CardPoint.user_id == user_id).order_by(CardPoint.id)).all()
    cashouts = db.execute(select(PointCashout, CardPoint, CardCompany.name, Account)
                          .join(Account, Account.id == PointCashout.account_id)
                          .outerjoin(CardPoint, CardPoint.id == PointCashout.card_point_id)
                          .outerjoin(CardCompany, CardCompany.id == CardPoint.card_company_id)
                          .where(Account.user_id == user_id)
                          .order_by(PointCashout.requested_at.desc(), PointCashout.id.desc()).limit(50)).all()
    return PointsOut(
        points=[PointOut(id=p.id, company_name=company, point_name=_name(p, company), balance=p.balance,
                         expiring_amount=p.expiring_amount, expiring_date=p.expiring_date, synced_at=p.synced_at)
                for p, company in points],
        cashouts=[_cashout_out(co, _name(p, company), a) for co, p, company, a in cashouts])


def request_cashout_to_card_company(point: CardPoint, amount: int, now: datetime) -> bool:
    """모의 카드사 서버에 현금화 요청 — 지금은 항상 성공. 진짜 카드사 연동(CARD-F10)이 생기면 이 안만 HTTP 호출로 바꾼다."""
    return True


class CashoutIn(BaseModel):
    account_id: str = Field(max_length=40)
    step_up_challenge_id: str = Field(max_length=40)


@router.post("/card-points/{pointId}/cashout", response_model=CashoutOut, status_code=201)
def cash_out_points(point_id: Annotated[str, Path(alias="pointId")], body: CashoutIn, login: CurrentLogin, db: DB):
    user_id = login.user.id
    owned = db.scalar(select(CardPoint.id).where(CardPoint.id == point_id, CardPoint.user_id == user_id))
    if owned is None:
        raise not_found("POINT_NOT_FOUND", "포인트를 찾을 수 없어요.")
    invalid_account = ApiError(422, "INVALID_CASHOUT_ACCOUNT", "내 정상 입출금 계좌만 고를 수 있어요.")
    if db.scalar(select(Account.id).where(Account.id == body.account_id, Account.user_id == user_id)) is None:
        raise invalid_account
    # 잠그는 순서: 잔액 행 → 포인트 행 (이체·탈퇴가 잔액 행을 먼저 잠근다). 잠근 뒤 계좌 상태·포인트 잔액을 읽는다
    bal = ledger.lock_balances(db, [body.account_id]).get(body.account_id)
    account = db.get(Account, body.account_id, populate_existing=True)
    if bal is None or account.account_type != "CHECKING" or account.lifecycle_status != "ACTIVE":
        raise invalid_account
    pt = db.scalar(select(CardPoint).where(CardPoint.id == point_id, CardPoint.user_id == user_id)
                   .with_for_update().execution_options(populate_existing=True))
    if pt is None:
        raise not_found("POINT_NOT_FOUND", "포인트를 찾을 수 없어요.")
    amount = pt.balance
    if amount <= 0:
        raise ApiError(409, "NO_POINTS", "현금으로 바꿀 포인트가 없어요.")
    consume_step_up(db, body.step_up_challenge_id, login, "POINT_CASHOUT")

    now = now_kst()
    company = db.scalar(select(CardCompany.name).where(CardCompany.id == pt.card_company_id))
    co = PointCashout(id=new_id("pco"), card_point_id=pt.id, account_id=account.id, amount=amount, status="REQUESTED",
                      requested_at=now)
    db.add(co)
    if not request_cashout_to_card_company(pt, amount, now):
        db.rollback()
        raise ApiError(502, "CASHOUT_FAILED", "카드사에서 현금화를 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.")
    co.status, co.completed_at = "COMPLETED", now
    pt.balance, pt.expiring_amount, pt.expiring_date = 0, 0, None  # 전액이라 소멸 예정분도 함께 바뀐다
    ledger.post(db, bal, "POINT_CASHOUT", amount, now, display_name=f"{_name(pt, company)} 현금화"[:50])
    db.commit()
    return _cashout_out(co, _name(pt, company), account)
