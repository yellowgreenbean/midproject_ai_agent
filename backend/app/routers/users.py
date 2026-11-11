"""내 정보 조회 — 기획서 Part 1 7장 GET /users/me (AUTH-F07 의 조회 부분만 먼저).

화면이 새로고침한 뒤 "지금 누가 로그인했는지·가입 마무리가 필요한지(status)"를 알 때 쓴다.
가입 마무리 중(PENDING_VERIFICATION)도 볼 수 있다(Part 1 7.3 「가입 마무리 화면만」).
수정(PATCH /users/me)은 2차 AUTH-F07 에서 만든다.
"""

from datetime import date

from fastapi import APIRouter

from app.deps import LoginUser
from app.common.naming import KstDatetime
from app.schemas import ORM

router = APIRouter(tags=["users"])


class MeOut(ORM):
    id: str
    username: str
    name: str
    email: str | None
    email_verified_at: KstDatetime | None
    birth_date: date  # YYYY-MM-DD (C-5 「회원 정보는 YYYY-MM-DD」)
    gender: str
    payday: int | None
    status: str
    created_at: KstDatetime


@router.get("/users/me", response_model=MeOut)
def get_me(user: LoginUser):
    return user
