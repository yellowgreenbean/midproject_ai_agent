"""로그인 / 로그아웃 — 기획서 Part 1 AUTH-F05, 7장 API (POST /auth/login, POST /auth/logout).

로그인 순서 (AUTH-F05 정상 흐름 1~4)
  1. 실패 속도 제한 확인 (서버 메모리, 같은 아이디 5번 연속 실패 → 1분 대기)
  2. LOCAL 로그인 수단(auth_identities.provider_subject = 아이디) → 비밀번호 해시(local_credentials) 확인
     없는 아이디·틀린 비밀번호·탈퇴 회원은 모두 같은 401 INVALID_CREDENTIALS (계정 존재 여부를 숨김)
  3. 성공하면 sessions 행을 만들고 쿠키 sid(HttpOnly·SameSite=Lax)를 보낸다
로그인 실패는 local_credentials.failed_attempts 에 세지 않는다 — 6.3 표: 그 칸은 본인 확인 실패만 센다.
"""

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import settings
from app.deps import DB, is_session_alive
from app.errors import ApiError
from app.models import AuthAuditLog, AuthIdentity, AuthSession, LocalCredential, User
from app.rules import SESSION_COOKIE, SESSION_MAX, now_kst
from app.security import (
    hash_password,
    login_throttle,
    new_id,
    new_session_token,
    password_needs_rehash,
    session_id_for,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128, repr=False)  # repr=False: 로그·오류 출력에 원문이 안 남게


class LoginOut(BaseModel):
    user_id: str
    status: str  # PENDING_VERIFICATION 이면 화면은 가입 마무리로 보낸다(Part 1 7.3)


def _audit(db, user_id: str, event_type: str, outcome: str, request_id: str) -> None:
    """auth_audit_logs (Part 1 8.1 「감사」) — 자격 증명 원문은 남기지 않는다.
    event_type 값 목록은 기획서에 아직 없어(6.3 「값 목록 미정」) LOGIN / LOGOUT 을 쓴다."""
    db.add(AuthAuditLog(id=new_id("aud"), user_id=user_id, event_type=event_type, outcome=outcome,
                        request_id=request_id))


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_MAX.total_seconds()),  # 브라우저도 최대 12시간 뒤 지운다
        httponly=True,  # 화면 JS 가 읽지 못함 (탈취 방어)
        samesite="lax",  # 다른 사이트에서 보내는 POST 에는 쿠키가 안 붙음 (CSRF 방어)
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, response: Response, db: DB):
    request_id = uuid.uuid4().hex
    if login_throttle.blocked_until(body.username):
        raise ApiError(429, "LOGIN_TOO_MANY_ATTEMPTS", "로그인 시도가 많아요. 1분 뒤 다시 시도해 주세요.")

    row = db.execute(
        select(User, LocalCredential)
        .join(AuthIdentity, AuthIdentity.user_id == User.id)
        .join(LocalCredential, LocalCredential.user_id == User.id)
        .where(AuthIdentity.provider == "LOCAL", AuthIdentity.provider_subject == body.username)
    ).first()
    user, cred = row if row else (None, None)

    ok = verify_password(cred.password_hash if cred else None, body.password)  # 없는 아이디도 확인 시간은 같게
    if not ok or user.status == "WITHDRAWN":
        login_throttle.record_failure(body.username)
        if user is not None:  # 없는 아이디는 user_id 가 없어 기록할 수 없다(auth_audit_logs.user_id NOT NULL)
            _audit(db, user.id, "LOGIN", "FAILURE", request_id)
            db.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호를 확인해 주세요.")

    login_throttle.reset(body.username)
    if password_needs_rehash(cred.password_hash):
        cred.password_hash = hash_password(body.password)

    # 이 브라우저에 예전 세션이 살아 있으면 끊는다(한 브라우저에 세션 하나)
    old_token = request.cookies.get(SESSION_COOKIE)
    now = now_kst()
    if old_token:
        old = db.get(AuthSession, session_id_for(old_token))
        if old is not None and is_session_alive(old, now):
            old.revoked_at = now

    token = new_session_token()
    db.add(AuthSession(id=session_id_for(token), user_id=user.id, created_at=now, last_seen_at=now,
                       expires_at=now + SESSION_MAX))
    _audit(db, user.id, "LOGIN", "SUCCESS", request_id)
    db.commit()

    _set_session_cookie(response, token)
    return LoginOut(user_id=user.id, status=user.status)


@router.post("/logout", status_code=204)
def logout(request: Request, db: DB):
    """서버 세션을 끊고(revoked_at) 쿠키를 지운다. 이미 끊겼거나 쿠키가 없어도 204 (몇 번 눌러도 결과가 같다)."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session = db.get(AuthSession, session_id_for(token))
        if session is not None and session.revoked_at is None:
            session.revoked_at = now_kst()
            _audit(db, session.user_id, "LOGOUT", "SUCCESS", uuid.uuid4().hex)
            db.commit()
    response = Response(status_code=204)
    _clear_session_cookie(response)
    return response
