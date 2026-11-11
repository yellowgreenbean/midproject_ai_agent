"""본인 확인(step-up) 번호 소비 — 이체·가입·카드 해지·탈퇴 같은 중요 작업 API 가 부른다(Part 1 9.3).

번호 발급(`POST /auth/step-up`)은 routers/auth.py 에 있다.
"""

from app.deps import Login
from app.errors import ApiError
from app.models import StepUpChallenge
from app.rules import now_kst


def consume_step_up(db, challenge_id: str | None, login: Login, action: str) -> None:
    """번호가 이 회원·이 세션·이 action 의 것이고, 5분 안이고, 처음 쓰는 것인지 확인하고 「사용함」으로 표시.
    커밋은 작업과 같이 한다 — 작업이 실패해 롤백되면 번호도 다시 쓸 수 있다."""
    ch = db.get(StepUpChallenge, challenge_id, with_for_update=True) if challenge_id else None
    if (ch is None or login.session is None or ch.user_id != login.user.id or ch.session_id != login.session.id
            or ch.action != action or ch.consumed_at is not None or now_kst() >= ch.expires_at):
        raise ApiError(403, "STEP_UP_REQUIRED", "본인 확인을 다시 해 주세요.")
    ch.consumed_at = now_kst()
