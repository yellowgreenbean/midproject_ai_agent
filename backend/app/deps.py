from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError, unauthorized
from app.models import User

DB = Annotated[Session, Depends(get_db)]


def get_current_user_id(
    db: DB,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """현재 로그인한 회원의 id.

    임시로 X-User-Id 헤더를 믿는다. 로그인(AUTH-F05)이 들어오면 세션 쿠키에서 user_id 를 꺼내도록
    이 함수만 바꾸면 된다(라우터는 그대로). 회원 상태별 허용은 기획서 Part 1 7.3:
      ACTIVE·RESTRICTED  로그인·조회 가능 (RESTRICTED 가 새 금융 작업을 못 하는 것은 각 작업 API 가 막는다)
      PENDING_VERIFICATION  가입 마무리 화면만 → 403
      WITHDRAWN · 없는 회원  로그인 불가 → 401
    """
    if not x_user_id:
        raise unauthorized()
    user = db.get(User, x_user_id)
    if user is None or user.status == "WITHDRAWN":
        raise unauthorized()
    if user.status == "PENDING_VERIFICATION":
        raise ApiError(403, "SIGNUP_INCOMPLETE", "가입을 마무리해 주세요.")
    return user.id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
