"""간편 비밀번호(PIN) 조회 · 만들기 · 바꾸기 · 다시 정하기 — 기획서 Part 1 AUTH-F11 · AUTH-F13, 7장 API.

화면 (frontend PinPage, #/settings/pin) — 셋 다 ① 본인 확인 ② 새 PIN ③ 한 번 더
  GET  /auth/pin                  PIN 을 만들었는지 · 잠겼는지 · 마지막으로 정한 때
  만들기       POST /auth/step-up {action: PIN_ENROLL, password}  → POST /auth/pin/enroll
  바꾸기       POST /auth/step-up {action: PIN_CHANGE, pin}       → POST /auth/pin/change
  다시 정하기  POST /auth/step-up {action: PIN_RESET,  password}  → POST /auth/pin/reset
  /enroll · /change · /reset 은 모두 {step_up_challenge_id, pin, pin_confirm} 을 받는다.
  (기획서 7장의 /auth/pin/reset/start · /confirm 두 단계는 「step-up(PIN_RESET) → /reset」으로 대신한다)

정한 규칙 (사용자 결정 2026-11-10)
  - PIN 은 숫자 6자리. 같은 숫자만(111111) · 이어지는 숫자(123456 · 654321) · 생년월일(YYMMDD)은 안 됨 (rules.pin_error)
  - 바꾸기에서는 지금 PIN 과 같은 번호도 안 됨. 다시 정하기에서는 보지 않는다 — 「지금 것과 같아요」가
    잊은(또는 잠긴) PIN 을 맞혀 볼 수 있는 통로가 되기 때문
  - PIN 을 5번 틀리면 10분 잠금. 다시 정하기는 로그인 비밀번호로 확인하므로 잠금을 바로 푼다
  - 바꾸기 · 다시 정하기 뒤: 아직 안 쓴 본인 확인 번호를 모두 무효로(AUTH-F13 ⑤ 「기존 인증 결과 무효화」),
    앱 알림(notifications.type = SECURITY)을 남긴다
  - 새 PIN 이 규칙에 걸리면 본인 확인 번호는 쓰지 않은 채로 남는다(커밋 안 함) → 5분 안에 새 PIN 만 다시 보내면 된다
  - PIN 원문은 저장 · 응답 · 로그에 남기지 않는다. 해시는 비밀번호와 같은 Argon2id(회원마다 솔트)
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import update

from app.deps import DB, Login, get_current_login
from app.errors import ApiError
from app.models import Notification, PinCredential, StepUpChallenge
from app.routers.auth import _audit, consume_step_up, pin_not_set
from app.rules import now_kst, pin_error
from app.schemas import KstDatetime
from app.security import hash_password, new_id, verify_password

router = APIRouter(prefix="/auth/pin", tags=["pin"])


class PinStatusOut(BaseModel):
    enabled: bool
    locked_until: KstDatetime | None  # 지금 잠겨 있을 때만. 잠금 시간이 지났으면 null
    changed_at: KstDatetime | None  # 마지막으로 정한 때 (한 번도 안 바꿨으면 만든 때)


def _status(cred: PinCredential | None, now: datetime) -> PinStatusOut:
    if cred is None:
        return PinStatusOut(enabled=False, locked_until=None, changed_at=None)
    locked = cred.locked_until if cred.locked_until is not None and now < cred.locked_until else None
    return PinStatusOut(enabled=True, locked_until=locked, changed_at=cred.changed_at or cred.enabled_at)


@router.get("", response_model=PinStatusOut)
def pin_status(login: Annotated[Login, Depends(get_current_login)], db: DB):
    return _status(db.get(PinCredential, login.user.id), now_kst())


class PinSetIn(BaseModel):
    step_up_challenge_id: str = Field(max_length=40)
    pin: str = Field(max_length=20, repr=False)  # 6자리 검사는 pin_error 가 한국어 안내로 한다
    pin_confirm: str = Field(max_length=20, repr=False)


Op = Literal["enroll", "change", "reset"]
ACTION: dict[Op, str] = {"enroll": "PIN_ENROLL", "change": "PIN_CHANGE", "reset": "PIN_RESET"}
NOTICE: dict[Op, tuple[str, str] | None] = {
    "enroll": None,
    "change": ("간편 비밀번호를 바꿨어요",
               "간편 비밀번호를 바꿨어요. 본인이 하지 않았다면 바로 마이페이지 > 간편 비밀번호에서 다시 정해 주세요."),
    "reset": ("간편 비밀번호를 다시 정했어요",
              "로그인 비밀번호로 확인하고 간편 비밀번호를 다시 정했어요. 본인이 하지 않았다면 바로 비밀번호를 바꿔 주세요."),
}


def _set_pin(op: Op, body: PinSetIn, login: Login, db) -> PinStatusOut:
    user = login.user
    consume_step_up(db, body.step_up_challenge_id, login, ACTION[op])  # 아래에서 실패하면 롤백 → 번호는 다시 쓸 수 있다
    if err := pin_error(body.pin, user.birth_date):
        raise ApiError(400, "INVALID_PIN", err)
    if body.pin != body.pin_confirm:
        raise ApiError(400, "PIN_MISMATCH", "두 번 누른 숫자가 달라요. 다시 눌러 주세요.")

    cred = db.get(PinCredential, user.id, with_for_update=True)
    if op == "enroll" and cred is not None:
        raise ApiError(409, "PIN_ALREADY_SET", "이미 간편 비밀번호가 있어요. 바꾸려면 「간편 비밀번호 바꾸기」를 이용해 주세요.")
    if op != "enroll" and cred is None:
        raise pin_not_set()
    if op == "change" and verify_password(cred.pin_hash, body.pin):
        raise ApiError(400, "SAME_AS_OLD_PIN", "지금 쓰는 간편 비밀번호와 다르게 정해 주세요.")

    now = now_kst()
    if cred is None:
        cred = PinCredential(user_id=user.id, pin_hash=hash_password(body.pin), enabled_at=now, failed_attempts=0)
        db.add(cred)
    else:
        cred.pin_hash = hash_password(body.pin)
        cred.changed_at = now
        cred.failed_attempts, cred.locked_until = 0, None  # 다시 정하기는 잠금도 푼다
        # 예전 PIN 으로 받아 두고 아직 안 쓴 본인 확인 번호는 모두 무효 (방금 쓴 번호는 consume_step_up 이 이미 표시함)
        db.execute(update(StepUpChallenge)
                   .where(StepUpChallenge.user_id == user.id, StepUpChallenge.consumed_at.is_(None))
                   .values(consumed_at=now))
    if notice := NOTICE[op]:
        db.add(Notification(id=new_id("ntf"), user_id=user.id, type="SECURITY", title=notice[0], body=notice[1],
                            created_at=now))
    _audit(db, user.id, ACTION[op], "SUCCESS", uuid.uuid4().hex)
    db.commit()
    return _status(cred, now)


@router.post("/enroll", response_model=PinStatusOut, status_code=201)
def enroll_pin(body: PinSetIn, login: Annotated[Login, Depends(get_current_login)], db: DB):
    """AUTH-F11 — 로그인 비밀번호로 본인 확인(PIN_ENROLL)한 뒤 처음 만든다."""
    return _set_pin("enroll", body, login, db)


@router.post("/change", response_model=PinStatusOut)
def change_pin(body: PinSetIn, login: Annotated[Login, Depends(get_current_login)], db: DB):
    """AUTH-F13 변경 — 지금 PIN 으로 본인 확인(PIN_CHANGE)한 뒤 새 PIN 으로 바꾼다."""
    return _set_pin("change", body, login, db)


@router.post("/reset", response_model=PinStatusOut)
def reset_pin(body: PinSetIn, login: Annotated[Login, Depends(get_current_login)], db: DB):
    """AUTH-F13 재설정 — PIN 을 잊었거나 잠겼을 때 로그인 비밀번호로 본인 확인(PIN_RESET)한 뒤 다시 정한다."""
    return _set_pin("reset", body, login, db)
