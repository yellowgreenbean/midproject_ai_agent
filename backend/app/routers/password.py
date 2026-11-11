"""아이디 찾기 · 비밀번호 재설정 · 비밀번호 변경 — 기획서 Part 1 AUTH-F06 · AUTH-F08, 7장 API.

화면 순서
  아이디 찾기 (frontend FindIdPage)
    POST /auth/email-verifications {purpose: USERNAME_RECOVERY} → /confirm → 이메일 인증 토큰
    POST /auth/username-recovery            가린 아이디 목록
  비밀번호 재설정 (frontend ResetPasswordPage)
    POST /auth/email-verifications {purpose: PASSWORD_RESET} → /confirm → 이메일 인증 토큰
    POST /auth/password-resets              ① 아이디 + 이메일 인증 토큰 → 재설정 토큰 (5분 · 한 번)
    POST /auth/password-resets/confirm      ② 재설정 토큰 + 새 비밀번호 → 해시 교체 · 모든 기기 로그아웃
  비밀번호 변경 (frontend PasswordChangePage, 로그인 필요)
    POST /users/me/password/change          지금 비밀번호 확인 → 해시 교체 · 다른 기기 로그아웃

정한 규칙 (사용자 결정 2026-11-10)
  - 아이디 찾기 결과는 앞 3자만 보이고 나머지는 글자 수만큼 *  (minjun_kim → min*******)
  - 탈퇴(WITHDRAWN) 회원은 찾지도 바꾸지도 않는다. ACTIVE · RESTRICTED · PENDING_VERIFICATION 은 모두 된다
  - 재설정 ①에서 아이디·이메일이 안 맞으면(없는 아이디 · 남의 아이디 · 비밀번호 없는 Google 계정) 모두 같은 안내
    IDENTITY_MISMATCH. 이메일 인증 토큰은 쓰지 않은 채로 두어 아이디만 고쳐 다시 시도할 수 있다
  - 재설정은 본인 확인 잠금(STEP_UP_LOCKED)을 풀지 않는다 — 잠금은 영업점 방문(2026-11-09 결정 유지)
  - 변경에서 지금 비밀번호를 틀리면 본인 확인과 같은 칸(local_credentials.failed_attempts)에 센다 → 5번이면 STEP_UP_LOCKED
  - 새 비밀번호: 가입 규칙(8~64자 · 영문+숫자 · 아이디 포함 금지) + 지금 비밀번호와 같으면 거부
  - 재설정 · 변경 뒤 앱 알림(notifications.type = SECURITY)을 남긴다(실제 메일 대신)
"""

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from app.deps import DB, Login, get_login
from app.errors import ApiError
from app.models import AuthSession, LocalCredential, Notification, PasswordResetToken, User
from app.routers.auth import _audit, step_up_locked
from app.routers.signup import normalize_email, password_error, take_email_proof
from app.rules import PASSWORD_RESET_TTL, RECOVERABLE_STATUSES, STEP_UP_MAX_FAILURES, USERNAME_VISIBLE, now_kst
from app.common.naming import KstDatetime
from app.security import digest, hash_password, login_throttle, new_id, verify_password

router = APIRouter(tags=["password"])


def mask_username(username: str) -> str:
    """앞 3자만 보이고 나머지는 글자 수만큼 * — 아주 짧은 아이디도 최소 한 글자는 가린다."""
    visible = min(USERNAME_VISIBLE, len(username) - 1)
    return username[:visible] + "*" * (len(username) - visible)


def check_new_password(new: str, confirm: str, username: str) -> None:
    """새 비밀번호 형식 검사 (지금 비밀번호와 같은지는 부르는 쪽이 따로 본다 — 비교 방법이 달라서)."""
    if err := password_error(new, username):
        raise ApiError(400, "INVALID_PASSWORD", err)
    if new != confirm:
        raise ApiError(400, "PASSWORD_MISMATCH", "새 비밀번호가 일치하지 않아요.")


def same_as_old() -> ApiError:
    return ApiError(400, "SAME_AS_OLD_PASSWORD", "지금 쓰는 비밀번호와 다르게 정해 주세요.")


def replace_password(db, user: User, cred: LocalCredential, new: str, keep_session_id: str | None,
                     notice_title: str, notice_body: str) -> None:
    """해시 교체 → 세션 끊기 → 알림. 커밋은 부르는 쪽이 감사 기록과 같이 한다(하나라도 실패하면 아무것도 안 바뀜).
    keep_session_id 가 있으면 그 세션(지금 쓰는 브라우저)만 남기고 나머지를 끊는다. 세션 행은 지우지 않는다 —
    본인 확인 기록(step_up_challenges.session_id)이 가리키므로 revoked_at 만 채운다(가이드북 9-3)."""
    now = now_kst()
    cred.password_hash = hash_password(new)
    cred.password_updated_at = now
    q = update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
    if keep_session_id is not None:
        q = q.where(AuthSession.id != keep_session_id)
    db.execute(q.values(revoked_at=now))
    login_throttle.reset(user.username)  # 예전 비밀번호로 틀린 횟수 때문에 새 비밀번호 로그인이 막히지 않게
    db.add(Notification(id=new_id("ntf"), user_id=user.id, type="SECURITY", title=notice_title, body=notice_body,
                        created_at=now))


# --- 아이디 찾기 (AUTH-F06) ------------------------------------------------------------------------
class RecoveryIn(BaseModel):
    email: str = Field(max_length=254)
    email_verification_token: str = Field(max_length=100, repr=False)


class FoundUsername(BaseModel):
    username: str  # 가린 아이디
    created_at: KstDatetime


@router.post("/auth/username-recovery", response_model=list[FoundUsername])
def recover_username(body: RecoveryIn, db: DB):
    """이메일 소유를 확인한 뒤 그 이메일로 가입한 아이디를 가려서 돌려준다. 없으면 빈 목록.
    번호 발송은 가입 여부와 상관없이 되므로(email-verifications) 「인증 전」에는 계정이 있는지 알 수 없다."""
    email = normalize_email(body.email)
    proof = take_email_proof(db, email, "USERNAME_RECOVERY", body.email_verification_token)
    users = list(db.scalars(select(User).where(func.lower(User.email) == email,
                                               User.status.in_(RECOVERABLE_STATUSES)).order_by(User.created_at)))
    db.delete(proof)  # 인증 토큰은 한 번만
    request_id = uuid.uuid4().hex
    for u in users:
        _audit(db, u.id, "USERNAME_RECOVERY", "SUCCESS", request_id)
    db.commit()
    return [FoundUsername(username=mask_username(u.username), created_at=u.created_at) for u in users]


# --- 비밀번호 재설정 (AUTH-F06) ---------------------------------------------------------------------
class ResetStartIn(BaseModel):
    username: str = Field(max_length=50)
    email: str = Field(max_length=254)
    email_verification_token: str = Field(max_length=100, repr=False)


class ResetStartOut(BaseModel):
    reset_token: str
    expires_at: KstDatetime


@router.post("/auth/password-resets", response_model=ResetStartOut, status_code=201)
def start_password_reset(body: ResetStartIn, db: DB):
    """① 아이디와 이메일이 같은 회원 것인지 확인하고 재설정 토큰을 준다. 원문은 응답에만, DB 에는 해시만."""
    email = normalize_email(body.email)
    proof = take_email_proof(db, email, "PASSWORD_RESET", body.email_verification_token)
    row = db.execute(
        select(User, LocalCredential)
        .join(LocalCredential, LocalCredential.user_id == User.id)  # 비밀번호가 없는(Google 전용) 계정은 여기서 빠진다
        .where(User.username == body.username.strip(), func.lower(User.email) == email,
               User.status.in_(RECOVERABLE_STATUSES))
    ).first()
    if row is None:  # 커밋하지 않으므로 이메일 인증 토큰은 그대로 남는다 → 아이디만 고쳐 다시
        raise ApiError(400, "IDENTITY_MISMATCH", "아이디와 이메일을 다시 확인해 주세요.")
    user = row[0]

    now = now_kst()
    # 아직 안 쓴 예전 재설정 토큰은 지운다 — 가장 최근에 받은 것 하나만 유효
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
                                                PasswordResetToken.used_at.is_(None)))
    token = secrets.token_urlsafe(32)
    reset = PasswordResetToken(id=new_id("prt"), user_id=user.id, token_digest=digest(token),
                               expires_at=now + PASSWORD_RESET_TTL)
    db.add(reset)
    db.delete(proof)
    _audit(db, user.id, "PASSWORD_RESET_REQUEST", "SUCCESS", uuid.uuid4().hex)
    db.commit()
    return ResetStartOut(reset_token=token, expires_at=reset.expires_at)


class ResetConfirmIn(BaseModel):
    reset_token: str = Field(max_length=100, repr=False)
    new_password: str = Field(max_length=128, repr=False)
    new_password_confirm: str = Field(max_length=128, repr=False)


def reset_token_invalid() -> ApiError:
    return ApiError(400, "RESET_TOKEN_INVALID", "재설정 시간이 지났어요. 처음부터 다시 해 주세요.")


@router.post("/auth/password-resets/confirm", status_code=204)
def confirm_password_reset(body: ResetConfirmIn, db: DB):
    """② 새 비밀번호로 바꾸고 모든 기기에서 로그아웃. 새 비밀번호가 규칙에 안 맞으면 토큰은 그대로(5분 안에 다시)."""
    reset = db.scalar(select(PasswordResetToken)
                      .where(PasswordResetToken.token_digest == digest(body.reset_token)).with_for_update())
    if reset is None or reset.used_at is not None or now_kst() >= reset.expires_at:
        raise reset_token_invalid()
    user = db.get(User, reset.user_id)
    cred = db.get(LocalCredential, reset.user_id, with_for_update=True)
    if user.status not in RECOVERABLE_STATUSES or cred is None:  # 토큰을 받은 뒤 탈퇴한 경우
        raise reset_token_invalid()
    check_new_password(body.new_password, body.new_password_confirm, user.username)
    if verify_password(cred.password_hash, body.new_password):
        raise same_as_old()

    reset.used_at = now_kst()
    # 본인 확인 잠금(failed_attempts)은 그대로 둔다 — 영업점 방문(사용자 결정 2026-11-10)
    replace_password(db, user, cred, body.new_password, keep_session_id=None,
                     notice_title="비밀번호를 다시 정했어요",
                     notice_body="이메일 인증으로 비밀번호를 다시 정해 모든 기기에서 로그아웃했어요. "
                                 "본인이 하지 않았다면 바로 비밀번호를 다시 정해 주세요.")
    _audit(db, user.id, "PASSWORD_RESET", "SUCCESS", uuid.uuid4().hex)
    db.commit()


# --- 비밀번호 변경 (AUTH-F08) -----------------------------------------------------------------------
class ChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(max_length=128, repr=False)
    new_password_confirm: str = Field(max_length=128, repr=False)


@router.post("/users/me/password/change", status_code=204)
def change_password(body: ChangeIn, login: Annotated[Login, Depends(get_login)], db: DB):
    """지금 비밀번호 확인 → 새 비밀번호로 교체 → 지금 쓰는 브라우저만 남기고 다른 기기 로그아웃."""
    user = login.user
    cred = db.get(LocalCredential, user.id, with_for_update=True)  # 동시에 여러 번 틀려도 횟수가 정확하게
    if cred is None:
        raise ApiError(400, "PASSWORD_NOT_SET", "Google로 가입한 계정은 비밀번호가 없어요. Google 로그인을 이용해 주세요.")
    if cred.failed_attempts >= STEP_UP_MAX_FAILURES:
        raise step_up_locked()
    check_new_password(body.new_password, body.new_password_confirm, user.username)  # 형식 오류는 실패로 세지 않는다

    request_id = uuid.uuid4().hex
    if not verify_password(cred.password_hash, body.current_password):
        cred.failed_attempts += 1  # 본인 확인과 같은 칸 (사용자 결정 2026-11-10)
        _audit(db, user.id, "PASSWORD_CHANGE", "FAILURE", request_id)
        db.commit()
        left = STEP_UP_MAX_FAILURES - cred.failed_attempts
        if left <= 0:
            raise step_up_locked()
        raise ApiError(400, "WRONG_PASSWORD", f"지금 비밀번호가 맞지 않아요. {left}번 더 틀리면 잠겨요.")
    cred.failed_attempts = 0
    if body.new_password == body.current_password:
        db.commit()  # 맞힌 것은 맞힌 것 — 실패 횟수 0 은 저장
        raise same_as_old()

    replace_password(db, user, cred, body.new_password,
                     keep_session_id=login.session.id if login.session else None,
                     notice_title="비밀번호를 바꿨어요",
                     notice_body="비밀번호를 바꿔 다른 기기에서 로그인돼 있던 곳은 모두 로그아웃했어요. "
                                 "본인이 하지 않았다면 바로 비밀번호를 다시 정해 주세요.")
    _audit(db, user.id, "PASSWORD_CHANGE", "SUCCESS", request_id)
    db.commit()
