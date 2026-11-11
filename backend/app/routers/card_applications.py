"""카드 신청 · 배송 조회 — 기획서 Part 4 1-2 (CARD-F05 체크카드 발급·배송 조회).

    GET  /card-products                          신청할 수 있는 카드 (판매 중, 1-2 ①)
    GET  /card-applications                      내 신청·배송 조회 (최근 신청부터, 상태 이력 포함)
    POST /card-applications                      체크카드 신청 (본인 확인 CARD_APPLICATION) → 바로 승인(APPROVED, 발급 준비 중)
    POST /card-applications/{applicationId}/cancel     신청 취소 — 배송 시작 전(APPLIED·REVIEWING·APPROVED)만 (1-2 「신청 취소」)
    POST /card-applications/{applicationId}/ship       시연용 [배송 시작] APPROVED → SHIPPING, 운송장 번호를 붙인다
    POST /card-applications/{applicationId}/deliver    시연용 [배송 완료] SHIPPING → DELIVERED (1차는 실제 배송 없음, 1-2 ⑥)
    POST /card-applications/{applicationId}/activate   받은 카드 등록 DELIVERED → ACTIVATED + user_cards · user_card_settings (1-2 ⑦)

체크카드는 심사가 없어 신청 요청 하나에서 APPLIED → APPROVED 까지 넘긴다(「우리 서비스 체크카드」). 배송 시작은 따로 —
승인 단계에서 멈춰야 취소할 틈이 있다(사용자 결정 2026-11-10). 취소는 본인 확인 없이 화면 확인 창만(돈이 오가지 않고 다시 신청할 수 있음).
신용카드 발급(모의 심사·한도, 1-7)은 2차 — 화면(CardApplyPage)도 고를 수 없게 보여 준다.
화면 응답 모양: frontend/src/api.ts getCardProducts · CardApplicationRaw
"""

import calendar
import hashlib
import secrets
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.card_benefits import benefits_for
from app.common.idempotency import IdempotencyKey
from app.deps import DB, CurrentLogin, CurrentUserId
from app.errors import ApiError, not_found
from app.models import (
    Account,
    ApplicationStatusHistory,
    ApplicationTermAgreement,
    CardApplication,
    CardCompany,
    CardProduct,
    Notification,
    Terms,
    User,
    UserCard,
    UserCardSetting,
    UserCardStatusHistory,
    UserConsent,
)
from app.common.step_up import consume_step_up
from app.routers.cards import BenefitOut
from app.rules import next_year, now_kst
from app.common.naming import KstDatetime, Money
from app.security import new_id

router = APIRouter(tags=["cards"])
ApplicationId = Annotated[str, Path(alias="applicationId")]

CANCELABLE = ("APPLIED", "REVIEWING", "APPROVED")  # 배송 시작 전
IN_FLIGHT = CANCELABLE + ("SHIPPING", "DELIVERED")  # 아직 카드가 안 생긴 신청 — 같은 카드를 또 신청하지 못하게
HELD = ("ACTIVE", "SUSPENDED")  # 분실·만료·해지한 카드는 다시 신청할 수 있다
CARD_VALID_YEARS = 5  # 유효기간 — 등록한 달부터 5년 뒤 그달 말일
STEP_ORDER = {s: i for i, s in enumerate(CardApplication.STATUS_VALUES)}  # 같은 초에 넘어간 이력을 단계 순서로


class TermOut(BaseModel):
    id: str
    title: str
    required: bool


class CardProductOut(BaseModel):
    id: str
    name: str
    company_name: str
    card_type: str
    annual_fee: Money
    min_age: int
    benefits: list[BenefitOut]
    terms: list[TermOut]


class StepOut(BaseModel):
    status: str
    changed_at: KstDatetime


class ApplicationOut(BaseModel):
    id: str
    card_product_id: str
    product_name: str
    card_type: str
    status: str
    applied_at: KstDatetime
    linked_account_number: str | None
    delivery_address: str | None
    tracking_no: str | None
    user_card_id: str | None
    history: list[StepOut]


class ApplyIn(BaseModel):
    card_product_id: str = Field(max_length=40)
    linked_account_id: str = Field(max_length=40)
    delivery_address: str = Field(max_length=255)
    agreed_term_ids: list[str] = Field(default_factory=list, max_length=20)
    step_up_challenge_id: str | None = Field(default=None, max_length=40)


def _terms(db, product_id: str) -> list[Terms]:
    # 카드 상품 약관만 — 공통 약관(card_product_id NULL)은 가입 때 이미 받은 서비스 약관이다
    return list(db.scalars(select(Terms).where(Terms.card_product_id == product_id).order_by(Terms.required.desc(), Terms.id)))


def _age(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def application_not_found() -> ApiError:
    return not_found("APPLICATION_NOT_FOUND", "카드 신청을 찾을 수 없어요.")


@router.get("/card-products", response_model=list[CardProductOut])
def list_card_products(db: DB, _: CurrentUserId):
    today = now_kst().date()
    rows = db.execute(select(CardProduct, CardCompany.name).join(CardCompany, CardCompany.id == CardProduct.card_company_id)
                      .where(CardProduct.is_active).order_by(CardProduct.card_type, CardProduct.id)).all()
    # 혜택은 카드 상세와 같은 함수 — 아직 없는 카드라 실적 0원 기준(가장 낮은 구간)으로 보여 준다
    return [CardProductOut(id=p.id, name=p.name, company_name=company, card_type=p.card_type, annual_fee=p.annual_fee_domestic,
                           min_age=p.min_age, benefits=benefits_for(db, "", p.id, today)[0],
                           terms=[TermOut(id=t.id, title=t.title, required=t.required) for t in _terms(db, p.id)])
            for p, company in rows]


def _out(db, app: CardApplication) -> ApplicationOut:
    p = db.get(CardProduct, app.card_product_id)
    a = db.get(Account, app.linked_account_id) if app.linked_account_id else None
    hist = db.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id)).all()
    hist = sorted(hist, key=lambda h: (h.changed_at, STEP_ORDER.get(h.to_status, 99)))
    return ApplicationOut(id=app.id, card_product_id=p.id, product_name=p.name, card_type=p.card_type, status=app.status,
                          applied_at=app.applied_at, linked_account_number=a.resAccountDisplay if a else None,
                          delivery_address=app.delivery_address, tracking_no=app.tracking_no,
                          user_card_id=db.scalar(select(UserCard.id).where(UserCard.application_id == app.id)),
                          history=[StepOut(status=h.to_status, changed_at=h.changed_at) for h in hist])


@router.get("/card-applications", response_model=list[ApplicationOut])
def list_applications(db: DB, user_id: CurrentUserId):
    apps = db.scalars(select(CardApplication).where(CardApplication.user_id == user_id)
                      .order_by(CardApplication.applied_at.desc(), CardApplication.id.desc())).all()
    return [_out(db, a) for a in apps]


def _history(db, app_id: str, before: str | None, after: str, at, hist_id: str | None = None) -> None:
    db.add(ApplicationStatusHistory(id=hist_id or new_id("ash"), application_id=app_id, from_status=before,
                                    to_status=after, changed_at=at))


def _notify(db, user_id: str, card_id: str | None, type_: str, title: str, body: str, at) -> None:
    db.add(Notification(id=new_id("ntf"), user_id=user_id, user_card_id=card_id, type=type_, title=title, body=body, created_at=at))


@router.post("/card-applications", response_model=ApplicationOut, status_code=201)
def apply_card(body: ApplyIn, login: CurrentLogin, db: DB,
               idempotency_key: IdempotencyKey):
    user_id = login.user.id
    # 회원 행을 잠가 같은 회원의 신청을 한 줄로 세운다 — 같은 키 재요청·같은 카드 동시 신청이 둘 다 「처음」으로 보이지 않게
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    # 중복 방지 키 칸이 card_applications 에 없어(DB 그대로) 첫 상태 이력의 id 를 (회원, 키)에서 만든다
    first_id = "ash_" + hashlib.sha256(f"{user_id}:{idempotency_key}".encode()).hexdigest()[:32]
    if done := db.get(ApplicationStatusHistory, first_id):
        app = db.get(CardApplication, done.application_id)
        if app.card_product_id != body.card_product_id:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 다른 내용으로 보낸 요청 번호예요. 처음부터 다시 신청해 주세요.")
        return _out(db, app)  # 응답을 못 받고 다시 눌러도 처음 신청을 보여 준다
    if user.status != "ACTIVE":  # RESTRICTED 는 정리 동작만 (Part 1 7.3)
        raise ApiError(403, "USER_NOT_ACTIVE", "지금 계정 상태에서는 카드를 신청할 수 없어요.")

    p = db.get(CardProduct, body.card_product_id)
    if p is None or not p.is_active:
        raise not_found("CARD_PRODUCT_NOT_FOUND", "신청할 수 있는 카드가 아니에요.")
    if p.card_type != "CHECK":
        raise ApiError(422, "CREDIT_NOT_SUPPORTED", "신용카드 발급은 아직 준비 중이에요. 체크카드를 골라 주세요.")
    now = now_kst()
    if _age(user.birth_date, now.date()) < p.min_age:
        raise ApiError(422, "AGE_NOT_ELIGIBLE", f"이 카드는 만 {p.min_age}세부터 신청할 수 있어요.")
    held = db.scalar(select(UserCard.id).where(UserCard.user_id == user_id, UserCard.card_product_id == p.id,
                                               UserCard.status.in_(HELD)).limit(1))
    pending = db.scalar(select(CardApplication.id).where(CardApplication.user_id == user_id, CardApplication.card_product_id == p.id,
                                                         CardApplication.status.in_(IN_FLIGHT)).limit(1))
    if held or pending:
        raise ApiError(409, "DUPLICATE_CARD", "이미 가지고 있거나 신청 중인 카드예요.")
    a = db.get(Account, body.linked_account_id)
    if a is None or a.user_id != user_id or a.account_type != "CHECKING" or a.lifecycle_status != "ACTIVE":
        raise ApiError(422, "INVALID_LINKED_ACCOUNT", "출금 계좌는 내 정상 입출금 계좌만 고를 수 있어요.")
    address = body.delivery_address.strip()
    if not 5 <= len(address) <= 100:
        raise ApiError(422, "INVALID_ADDRESS", "카드를 받을 주소를 5~100자로 적어 주세요.")
    terms = _terms(db, p.id)
    if any(t.required and t.id not in body.agreed_term_ids for t in terms):
        raise ApiError(422, "REQUIRED_TERMS_NOT_AGREED", "필수 약관에 동의해 주세요.")
    consume_step_up(db, body.step_up_challenge_id, login, "CARD_APPLICATION")

    app = CardApplication(id=new_id("app"), user_id=user_id, card_product_id=p.id, step_up_challenge_id=body.step_up_challenge_id,
                          status="APPROVED", linked_account_id=a.id, delivery_address=address, applied_at=now, decided_at=now)
    db.add(app)
    db.flush()  # 모델에 relationship 이 없어 신청을 먼저 넣는다(아래 행들이 외래 키로 가리킴)
    _history(db, app.id, None, "APPLIED", now, first_id)
    _history(db, app.id, "APPLIED", "APPROVED", now)
    for t in terms:
        agreed = t.id in body.agreed_term_ids
        db.add(ApplicationTermAgreement(application_id=app.id, terms_id=t.id, agreed=agreed, agreed_at=now))
        db.add(UserConsent(id=new_id("cns"), user_id=user_id, terms_id=t.id, version=t.version, agreed=agreed, recorded_at=now))
    _notify(db, user_id, None, "APPLICATION", f"{p.name} 신청 완료",
            "카드를 만들고 있어요. 배송이 시작되면 알려 드릴게요.", now)
    try:
        db.commit()
    except IntegrityError:  # 같은 키가 다른 경로로 먼저 들어갔다 — 아무것도 남지 않았으니 다시 보내면 처음 신청을 돌려준다
        db.rollback()
        raise ApiError(409, "CONFLICT_RETRY", "다른 요청과 겹쳤어요. 잠시 후 다시 시도해 주세요.")
    return _out(db, app)


def _advance(db, user_id: str, app_id: str, before: tuple[str, ...], after: str, error: ApiError | None = None,
             **values) -> CardApplication:
    """내 신청을 before(중 지금 상태) → after 로. 지금 상태를 조건으로 한 문장에 바꾼다 — 두 번 눌러도 한 번만 넘어가게."""
    app = db.get(CardApplication, app_id)
    if app is None or app.user_id != user_id:
        raise application_not_found()
    was = app.status
    if was not in before or db.execute(update(CardApplication).where(CardApplication.id == app_id, CardApplication.status == was)
                                       .values(status=after, **values)).rowcount != 1:
        db.rollback()
        raise error or ApiError(409, "INVALID_STATUS_TRANSITION", "지금 상태에서는 할 수 없어요. 신청 상태를 다시 확인해 주세요.")
    _history(db, app_id, was, after, now_kst())
    return app


def _done(db, app: CardApplication, title: str, body: str) -> ApplicationOut:
    """신청 상태 알림을 남기고 커밋한 뒤 새 상태로 답한다."""
    p = db.get(CardProduct, app.card_product_id)
    _notify(db, app.user_id, None, "APPLICATION", title.format(name=p.name), body, now_kst())
    db.commit()
    db.refresh(app)
    return _out(db, app)


@router.post("/card-applications/{applicationId}/cancel", response_model=ApplicationOut)
def cancel(application_id: ApplicationId, db: DB, user_id: CurrentUserId):
    shipped = ApiError(409, "CANNOT_CANCEL", "배송이 시작돼 신청을 취소할 수 없어요. 카드를 받은 뒤 해지할 수 있어요.")
    app = _advance(db, user_id, application_id, CANCELABLE, "CANCELED", shipped)
    return _done(db, app, "{name} 신청을 취소했어요", "필요하면 언제든 다시 신청할 수 있어요.")


@router.post("/card-applications/{applicationId}/ship", response_model=ApplicationOut)
def ship(application_id: ApplicationId, db: DB, user_id: CurrentUserId):
    now = now_kst()
    app = _advance(db, user_id, application_id, ("APPROVED",), "SHIPPING",
                   tracking_no=f"DR{now:%Y%m%d}{secrets.randbelow(10**6):06d}")
    return _done(db, app, "{name} 배송을 시작했어요", "카드를 받으면 앱에서 등록해 주세요.")


@router.post("/card-applications/{applicationId}/deliver", response_model=ApplicationOut)
def deliver(application_id: ApplicationId, db: DB, user_id: CurrentUserId):
    app = _advance(db, user_id, application_id, ("SHIPPING",), "DELIVERED")
    return _done(db, app, "{name}가 도착했어요", "받은 카드를 앱에서 등록하면 바로 쓸 수 있어요.")


def _card_number(db, product_id: str) -> tuple[str, str]:
    """(가린 번호, 끝 4자리). 앞 4자리는 같은 상품의 기존 카드와 같게(더미: 체크 4214 · 신용 6253)."""
    prefix = (db.scalar(select(UserCard.card_number_masked).where(UserCard.card_product_id == product_id).limit(1)) or "5310")[:4]
    last4 = f"{secrets.randbelow(10**4):04d}"
    return f"{prefix}-****-****-{last4}", last4


@router.post("/card-applications/{applicationId}/activate", response_model=ApplicationOut)
def activate(application_id: ApplicationId, login: CurrentLogin, db: DB):
    user = login.user
    if user.status != "ACTIVE":
        raise ApiError(403, "USER_NOT_ACTIVE", "지금 계정 상태에서는 카드를 등록할 수 없어요.")
    app = _advance(db, user.id, application_id, ("DELIVERED",), "ACTIVATED")
    a = db.get(Account, app.linked_account_id) if app.linked_account_id else None
    if a is None or a.lifecycle_status != "ACTIVE":  # 배송 중에 출금 계좌를 정지·해지했다
        db.rollback()
        raise ApiError(409, "LINKED_ACCOUNT_NOT_ACTIVE", "출금 계좌가 정상 상태가 아니라 등록할 수 없어요. 계좌 상태를 확인해 주세요.")
    p = db.get(CardProduct, app.card_product_id)
    now = now_kst()
    number, last4 = _card_number(db, p.id)
    end_year = now.year + CARD_VALID_YEARS
    expires = date(end_year, now.month, calendar.monthrange(end_year, now.month)[1])  # 5년 뒤 이달의 말일
    card = UserCard(id=new_id("card"), user_id=user.id, card_product_id=p.id, application_id=app.id, source="TOSS_ISSUED",
                    card_number_masked=number, last4=last4, expires_at=expires, linked_account_id=a.id, status="ACTIVE",
                    annual_fee_amount=p.annual_fee_domestic, issued_at=app.decided_at, activated_at=now,
                    # 첫 해는 청구하지 않고 발급 1년 뒤부터 매년 (1-1-8, 사용자 결정 2026-11-11). 연회비 0원이면 비움
                    next_annual_fee_date=next_year(now.date()) if p.annual_fee_domestic else None)
    db.add(card)
    db.flush()
    db.add(UserCardSetting(user_card_id=card.id))
    db.add(UserCardStatusHistory(id=new_id("uch"), user_card_id=card.id, from_status=None, to_status="ACTIVE",
                                 reason="ACTIVATED", changed_at=now))
    _notify(db, user.id, card.id, "CARD_STATUS", f"{p.name}를 등록했어요", f"끝자리 {last4} 카드를 지금부터 쓸 수 있어요.", now)
    try:
        db.commit()
    except IntegrityError:  # 같은 신청으로 카드가 이미 생겼다(uk_user_cards_application)
        db.rollback()
        raise ApiError(409, "INVALID_STATUS_TRANSITION", "이미 등록한 카드예요.")
    db.refresh(app)
    return _out(db, app)
