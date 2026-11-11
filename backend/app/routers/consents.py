"""약관 및 동의 내역 — 기획서 Part 1 AUTH-F10 정상 흐름 5(마이페이지에서 열람·선택 동의 변경) · UI08 · 7장 API.

화면(frontend/src/pages/ConsentsPage.tsx, 마이페이지 → 약관 및 동의 내역)
  GET   /users/me/consents   공통 약관(GET /terms 와 같은 4개)마다 마지막 동의 상태
  PATCH /users/me/consents   선택 약관만 켜고 끈다 → 바뀐 목록을 돌려준다

user_consents 는 이력이다: 바꿀 때 행을 고치지 않고 새 행을 더한다(AC 「선택 동의 변경 이력이 유지됨」).
지금 상태 = 약관마다 recorded_at 이 가장 늦은 행. 기록이 없는 약관(시드 회원 등)은 agreed=false · recorded_at=null.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DB, CurrentUserId
from app.errors import ApiError
from app.models import UserConsent
from app.routers.signup import common_terms
from app.rules import now_kst
from app.common.naming import KstDatetime
from app.security import new_id

router = APIRouter(prefix="/users/me", tags=["consents"])


class ConsentOut(BaseModel):
    terms_id: str
    title: str
    required: bool
    version: str  # 지금 약관 버전(동의 기록이 있으면 동의한 버전)
    agreed: bool
    recorded_at: KstDatetime | None


def latest_consents(db, user_id: str) -> dict[str, UserConsent]:
    latest: dict[str, UserConsent] = {}
    q = select(UserConsent).where(UserConsent.user_id == user_id).order_by(UserConsent.recorded_at, UserConsent.id)
    for c in db.scalars(q):
        latest[c.terms_id] = c
    return latest


def my_consents(db, user_id: str) -> list[ConsentOut]:
    latest = latest_consents(db, user_id)
    out = []
    for t in common_terms(db):
        c = latest.get(t.id)
        out.append(ConsentOut(terms_id=t.id, title=t.title, required=t.required,
                              version=c.version if c else t.version,
                              agreed=bool(c and c.agreed),
                              recorded_at=c.recorded_at if c else None))
    return out


@router.get("/consents", response_model=list[ConsentOut])
def list_my_consents(user_id: CurrentUserId, db: DB):
    return my_consents(db, user_id)


class ConsentChangeIn(BaseModel):
    terms_id: str = Field(max_length=40)
    agreed: bool


@router.patch("/consents", response_model=list[ConsentOut])
def change_my_consent(body: ConsentChangeIn, user_id: CurrentUserId, db: DB):
    term = next((t for t in common_terms(db) if t.id == body.terms_id), None)
    if term is None:
        raise ApiError(404, "TERMS_NOT_FOUND", "약관을 찾을 수 없어요.")
    if term.required:
        raise ApiError(400, "REQUIRED_TERMS_LOCKED", "필수 약관은 서비스를 쓰는 동안 철회할 수 없어요.")

    now: datetime = now_kst().replace(microsecond=0)  # DB 칸이 TIMESTAMP(0)
    last = latest_consents(db, user_id).get(term.id)
    if last is None or last.agreed != body.agreed:  # 같은 값으로 다시 누르면 이력을 늘리지 않는다
        if last is not None and now <= last.recorded_at:
            # shortcut: 초 단위 칸 + 무작위 id 라 1초 안에 두 번 바꾸면 순서를 알 수 없다 → 앞 기록보다 1초 뒤로 남긴다.
            # 실제 서비스면 recorded_at 을 TIMESTAMP(6) 으로 늘리거나 순번 칸을 둔다
            now = last.recorded_at + timedelta(seconds=1)
        db.add(UserConsent(id=new_id("cns"), user_id=user_id, terms_id=term.id, version=term.version,
                           agreed=body.agreed, recorded_at=now))
        db.commit()
    return my_consents(db, user_id)
