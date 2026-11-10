"""로그인 / 로그아웃 — 기획서 Part 1 AUTH-F05, 7장 API (POST /auth/login, POST /auth/logout).

로그인 순서 (AUTH-F05 정상 흐름 1~4)
  1. 실패 속도 제한 확인 (서버 메모리, 같은 아이디 5번 연속 실패 → 1분 대기)
  2. LOCAL 로그인 수단(auth_identities.provider_subject = 아이디) → 비밀번호 해시(local_credentials) 확인
     없는 아이디·틀린 비밀번호·탈퇴 회원은 모두 같은 401 INVALID_CREDENTIALS (계정 존재 여부를 숨김)
  3. 성공하면 sessions 행을 만들고 쿠키 sid(HttpOnly·SameSite=Lax)를 보낸다
로그인 실패는 local_credentials.failed_attempts 에 세지 않는다 — 6.3 표: 그 칸은 본인 확인 실패만 센다.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import settings
from app.deps import DB, Login, get_login, is_session_alive, set_session_expires_header
from app.errors import ApiError, unauthorized
from app.models import AuthAuditLog, AuthIdentity, AuthSession, LocalCredential, PinCredential, StepUpChallenge, User
from app.rules import (
    PIN_LOCK,
    PIN_MAX_FAILURES,
    SESSION_COOKIE,
    SESSION_MAX,
    STEP_UP_MAX_FAILURES,
    STEP_UP_TTL,
    now_kst,
)
from app.schemas import KstDatetime
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

    start_session(db, request, response, user.id)
    _audit(db, user.id, "LOGIN", "SUCCESS", request_id)
    db.commit()
    return LoginOut(user_id=user.id, status=user.status)


def start_session(db, request: Request, response: Response, user_id: str) -> None:
    """로그인 세션을 만들고 쿠키·만료 시각 헤더를 붙인다. 커밋은 부르는 쪽이 한다(가입도 이걸로 바로 로그인)."""
    # 이 브라우저에 예전 세션이 살아 있으면 끊는다(한 브라우저에 세션 하나)
    old_token = request.cookies.get(SESSION_COOKIE)
    now = now_kst()
    if old_token:
        old = db.get(AuthSession, session_id_for(old_token))
        if old is not None and is_session_alive(old, now):
            old.revoked_at = now

    token = new_session_token()
    session = AuthSession(id=session_id_for(token), user_id=user_id, created_at=now, last_seen_at=now,
                          expires_at=now + SESSION_MAX)
    db.add(session)
    _set_session_cookie(response, token)
    set_session_expires_header(response, session)


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


# --- 본인 확인 (Part 1 7장 POST /auth/step-up, AUTH-F12) -----------------------------------------------------
# 중요 작업(이체·카드·가입·계좌 상태 변경·탈퇴·생년월일 수정·PIN 관리) 직전에 비밀번호나 간편 비밀번호(PIN)를 다시 받고,
# 그 작업 하나에만 쓸 수 있는 번호를 준다.
#   - 번호는 5분 · 한 번만 · 받은 action 에만 · 받은 세션에서만 (step_up_challenges)
#   - 비밀번호 실패는 local_credentials.failed_attempts 에 센다(로그인 실패는 세지 않음, 6.3). 5번이면 영구 잠금 → STEP_UP_LOCKED
#     (사용자 결정 2026-11-09, 시드 user_027 과 같음. locked_until 은 시간 잠금용이라 쓰지 않는다)
#   - PIN 실패는 pin_credentials 에 센다. 5번이면 10분 잠금 → PIN_LOCKED (사용자 결정 2026-11-10, rules.PIN_LOCK)
#   - 어떤 수단을 받나 (사용자 결정 2026-11-10)
#       PIN_CHANGE                 지금 PIN 만 (「기존 PIN 인증」, AUTH-F13)
#       PIN_ENROLL · PIN_RESET     로그인 비밀번호만 (PIN 이 없거나 잊었으니 PIN 과 다른 수단, AUTH-F13 「PIN 자체가 아닌」)
#       그 밖의 작업               둘 다 — 화면은 PIN 을 만든 회원에게 PIN 키패드를 보여 준다(frontend useStepUp)
PIN_ONLY_ACTIONS = ("PIN_CHANGE",)
PASSWORD_ONLY_ACTIONS = ("PIN_ENROLL", "PIN_RESET")


def step_up_locked() -> ApiError:
    return ApiError(423, "STEP_UP_LOCKED", "본인 확인에 여러 번 실패해 잠겼어요. 신분증을 가지고 가까운 영업점을 방문해 주세요.")


def pin_locked(until) -> ApiError:
    return ApiError(423, "PIN_LOCKED", f"간편 비밀번호를 여러 번 틀려서 {until:%H:%M}까지 쓸 수 없어요. "
                                       "마이페이지 > 간편 비밀번호에서 다시 정하면 바로 풀려요.")


def pin_not_set() -> ApiError:
    return ApiError(400, "PIN_NOT_SET", "간편 비밀번호가 아직 없어요. 마이페이지 > 간편 비밀번호에서 먼저 만들어 주세요.")


class StepUpIn(BaseModel):
    action: Literal[StepUpChallenge.ACTION_VALUES]
    # 둘 중 하나만 보낸다
    password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)
    pin: str | None = Field(default=None, min_length=1, max_length=20, repr=False)


class StepUpOut(BaseModel):
    step_up_challenge_id: str
    expires_at: KstDatetime


def _check_password(db, user: User, password: str, request_id: str) -> None:
    cred = db.get(LocalCredential, user.id, with_for_update=True)  # 동시에 여러 번 틀려도 횟수가 정확하게
    if cred is None:
        raise ApiError(400, "STEP_UP_NOT_AVAILABLE", "비밀번호로 본인 확인을 할 수 없는 계정이에요.")
    if cred.failed_attempts >= STEP_UP_MAX_FAILURES:
        raise step_up_locked()
    if not verify_password(cred.password_hash, password):
        cred.failed_attempts += 1
        _audit(db, user.id, "STEP_UP", "FAILURE", request_id)
        db.commit()
        left = STEP_UP_MAX_FAILURES - cred.failed_attempts
        if left <= 0:
            raise step_up_locked()
        raise ApiError(400, "STEP_UP_FAILED", f"비밀번호가 맞지 않아요. {left}번 더 틀리면 잠겨요.")
    cred.failed_attempts = 0


def _check_pin(db, user: User, pin: str, request_id: str) -> None:
    cred = db.get(PinCredential, user.id, with_for_update=True)
    if cred is None:
        raise pin_not_set()
    now = now_kst()
    if cred.locked_until is not None:
        if now < cred.locked_until:
            raise pin_locked(cred.locked_until)
        cred.locked_until, cred.failed_attempts = None, 0  # 잠금 시간이 지났으면 다시 5번
    if not verify_password(cred.pin_hash, pin):  # 6자리가 아닌 값도 그냥 틀린 번호로 센다
        cred.failed_attempts += 1
        if cred.failed_attempts >= PIN_MAX_FAILURES:
            cred.locked_until = now + PIN_LOCK  # failed_attempts 는 5 로 남겨 둔다(왜 잠겼는지 보이게)
        _audit(db, user.id, "STEP_UP_PIN", "FAILURE", request_id)
        db.commit()
        if cred.locked_until is not None:
            raise pin_locked(cred.locked_until)
        left = PIN_MAX_FAILURES - cred.failed_attempts
        raise ApiError(400, "STEP_UP_FAILED", f"간편 비밀번호가 맞지 않아요. {left}번 더 틀리면 "
                                                  f"{PIN_LOCK.seconds // 60}분 동안 쓸 수 없어요.")
    cred.failed_attempts = 0


@router.post("/step-up", response_model=StepUpOut, status_code=201)
def step_up(body: StepUpIn, login: Annotated[Login, Depends(get_login)], db: DB):
    if login.session is None:  # 개발용 X-User-Id 헤더로는 받을 수 없다 — 번호는 세션에 묶이므로
        raise unauthorized()
    if (body.password is None) == (body.pin is None):
        raise ApiError(400, "STEP_UP_CREDENTIAL_REQUIRED", "비밀번호나 간편 비밀번호 중 하나로 확인해 주세요.")
    if body.action in PIN_ONLY_ACTIONS and body.pin is None:
        raise ApiError(400, "PIN_REQUIRED", "지금 간편 비밀번호로 확인해 주세요.")
    if body.action in PASSWORD_ONLY_ACTIONS and body.password is None:
        raise ApiError(400, "PASSWORD_REQUIRED", "로그인 비밀번호로 확인해 주세요.")

    user = login.user
    request_id = uuid.uuid4().hex
    if body.pin is not None:
        _check_pin(db, user, body.pin, request_id)
    else:
        _check_password(db, user, body.password, request_id)

    now = now_kst()
    challenge = StepUpChallenge(id=new_id("stu"), user_id=user.id, action=body.action, session_id=login.session.id,
                                expires_at=now + STEP_UP_TTL)
    db.add(challenge)
    _audit(db, user.id, "STEP_UP_PIN" if body.pin is not None else "STEP_UP", "SUCCESS", request_id)
    db.commit()
    return StepUpOut(step_up_challenge_id=challenge.id, expires_at=challenge.expires_at)


def consume_step_up(db, challenge_id: str | None, login: Login, action: str) -> None:
    """중요 작업 API 가 부른다: 번호가 이 회원·이 세션·이 action 의 것이고, 5분 안이고, 처음 쓰는 것인지 확인하고 「사용함」으로 표시.
    커밋은 작업과 같이 한다 — 작업이 실패해 롤백되면 번호도 다시 쓸 수 있다."""
    ch = db.get(StepUpChallenge, challenge_id, with_for_update=True) if challenge_id else None
    if (ch is None or login.session is None or ch.user_id != login.user.id or ch.session_id != login.session.id
            or ch.action != action or ch.consumed_at is not None or now_kst() >= ch.expires_at):
        raise ApiError(403, "STEP_UP_REQUIRED", "본인 확인을 다시 해 주세요.")
    ch.consumed_at = now_kst()
