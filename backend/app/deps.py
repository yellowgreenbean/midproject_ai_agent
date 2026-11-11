"""현재 로그인한 회원 꺼내기 — 모든 보호 API 가 여기만 거친다(라우터는 회원을 직접 찾지 않음).

1. 쿠키 sid → sessions 행(id = 토큰의 해시) → 유효한지 확인 (AUTH-F05)
     끊김(revoked_at) · 최대 12시간(expires_at) · 유휴 10분(last_seen_at) 중 하나라도 걸리면 401 SESSION_EXPIRED
2. 쿠키가 없고 설정 AUTH_DEV_HEADER=true 이면 X-User-Id 헤더 (개발용)
3. 회원 상태 (Part 1 7.3)
     WITHDRAWN · 없는 회원         401
     PENDING_VERIFICATION          로그인은 되지만 가입 마무리 화면만 → CurrentUserId 는 403, LoginUser(/users/me)는 통과
     ACTIVE · RESTRICTED           통과 (RESTRICTED 가 새 금융 작업을 못 하는 것은 각 작업 API 가 막는다)
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.common.db import get_db
from app.errors import ApiError, unauthorized
from app.models import AuthSession, User
from app.rules import KST, SESSION_COOKIE, SESSION_IDLE, SESSION_TOUCH_INTERVAL, now_kst
from app.security import session_id_for

DB = Annotated[Session, Depends(get_db)]


def session_expired() -> ApiError:
    return ApiError(401, "SESSION_EXPIRED", "다시 로그인해 주세요.")


def is_session_alive(s: AuthSession, now) -> bool:
    return s.revoked_at is None and now < s.expires_at and now < s.last_seen_at + SESSION_IDLE


SESSION_EXPIRES_HEADER = "X-Session-Expires-At"


def set_session_expires_header(response: Response, s: AuthSession) -> None:
    """이 세션이 끊길 시각(유휴 10분과 최대 12시간 중 먼저 오는 것)을 화면에 알린다.
    화면(frontend SessionTimer)은 이 값으로 남은 시간·「로그인 연장」 창을 띄운다 — 판정은 언제나 서버가 한다."""
    at = min(s.expires_at, s.last_seen_at + SESSION_IDLE)
    if at.tzinfo is None:
        at = at.replace(tzinfo=KST)
    response.headers[SESSION_EXPIRES_HEADER] = at.isoformat()


@dataclass
class Login:
    user: User
    session: AuthSession | None  # 개발용 헤더로 들어오면 None


def get_login(
    request: Request,
    response: Response,
    db: DB,
    x_user_id: Annotated[str | None, Header(description="개발용 — AUTH_DEV_HEADER=true 일 때만 쓰임")] = None,
) -> Login:
    token = request.cookies.get(SESSION_COOKIE)
    session = None
    if token:
        session = db.get(AuthSession, session_id_for(token))
        if session is None:
            raise unauthorized()
        now = now_kst()
        if not is_session_alive(session, now):
            raise session_expired()
        if now - session.last_seen_at >= SESSION_TOUCH_INTERVAL:
            session.last_seen_at = now
            db.commit()
        set_session_expires_header(response, session)
        user = db.get(User, session.user_id)
    elif settings.auth_dev_header and x_user_id:
        user = db.get(User, x_user_id)
    else:
        raise unauthorized()

    if user is None or user.status == "WITHDRAWN":
        raise unauthorized()
    return Login(user=user, session=session)


def get_login_user(login: Annotated[Login, Depends(get_login)]) -> User:
    """가입 마무리 중(PENDING_VERIFICATION)도 통과 — /users/me 처럼 그 화면에 필요한 API 용."""
    return login.user


def get_current_user_id(login: Annotated[Login, Depends(get_login)]) -> str:
    """일반 보호 API 용."""
    if login.user.status == "PENDING_VERIFICATION":
        raise ApiError(403, "SIGNUP_INCOMPLETE", "가입을 마무리해 주세요.")
    return login.user.id


def get_current_login(login: Annotated[Login, Depends(get_login)]) -> Login:
    """본인 확인 번호를 쓰는 쓰기 API 용 — 세션까지 필요하다(번호가 세션에 묶임). 가입 마무리 중은 403."""
    get_current_user_id(login)
    return login


def get_optional_user_id(
    request: Request,
    response: Response,
    db: DB,
    x_user_id: Annotated[str | None, Header(description="개발용 — AUTH_DEV_HEADER=true 일 때만 쓰임")] = None,
) -> str | None:
    """로그인 없이도 쓰는 API(챗봇) 용 — 쿠키(개발용 헤더)가 없으면 None(손님).
    쿠키가 있으면 일반 보호 API 와 똑같이 검사한다: 끊긴 세션 401 · 가입 마무리 중 403 (손님으로 내려 주지 않음)."""
    if not request.cookies.get(SESSION_COOKIE) and not (settings.auth_dev_header and x_user_id):
        return None
    return get_current_user_id(get_login(request, response, db, x_user_id))


LoginUser = Annotated[User, Depends(get_login_user)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
CurrentLogin = Annotated[Login, Depends(get_current_login)]
OptionalUserId = Annotated[str | None, Depends(get_optional_user_id)]
