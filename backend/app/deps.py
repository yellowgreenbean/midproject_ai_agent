from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

DB = Annotated[Session, Depends(get_db)]


def get_current_user_id(
    db: DB,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """현재 사용자.

    임시로 X-User-Id 헤더를 믿는다. 회원·인증 파트가 들어오면 세션 쿠키에서
    user_id 를 꺼내도록 이 함수만 바꾸면 된다(라우터는 그대로).
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user = db.get(User, x_user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user.id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
