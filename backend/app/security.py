"""비밀번호 확인, 세션 번호, 로그인 실패 속도 제한.

- 비밀번호: Argon2id (Part 1 8.1 「안전한 전용 해시」). 해시에 매개변수가 같이 들어 있어 seed 가 만든 해시도 그대로 확인된다.
- 세션 번호: 쿠키에는 무작위 토큰 원문, DB(sessions.id)에는 그 해시만 둔다 —
  DB 가 새어도 쿠키를 만들 수 없게(6.1 「원문을 DB 에 보관하지 않도록」과 같은 취지).
"""

import base64
import hashlib
import secrets
import threading
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.rules import LOGIN_THROTTLE_FAILURES, LOGIN_THROTTLE_WAIT, now_kst

_ph = PasswordHasher()
# 없는 아이디일 때도 해시 확인을 한 번 해서, 응답 시간으로 계정이 있는지 알 수 없게 한다
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """해시 매개변수가 바뀌었으면 로그인 성공 때 새 매개변수로 다시 해시한다."""
    return _ph.check_needs_rehash(password_hash)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def new_session_token() -> str:
    """쿠키에 넣을 세션 토큰 (256비트 무작위)."""
    return secrets.token_urlsafe(32)


def session_id_for(token: str) -> str:
    """토큰 → sessions.id. 'ses_' + SHA-256 의 base64url 앞 36자 = 40자 (VARCHAR(40), C-5 「ID 앞에 종류 표시」)."""
    digest = base64.urlsafe_b64encode(hashlib.sha256(token.encode()).digest()).decode()
    return "ses_" + digest[:36]


def new_id(prefix: str) -> str:
    """앱이 새로 만드는 행의 id (예: aud_3f9c…). 더미처럼 일련번호를 쓰면 동시 요청에서 겹칠 수 있어 무작위로 만든다."""
    return f"{prefix}_{secrets.token_hex(10)}"


class LoginThrottle:
    """아이디별 로그인 연속 실패를 서버 메모리에서 센다. 5번 틀리면 1분 동안 로그인 시도를 받지 않는다.

    DB 를 쓰지 않으므로 서버를 다시 켜면 초기화되고, 서버 프로세스가 여럿이면 각자 센다(학습용 한계).
    없는 아이디도 똑같이 세서, 막히는지 여부로 계정이 있는지 알 수 없게 한다.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._fails: dict[str, int] = {}
        self._blocked_until: dict[str, datetime] = {}

    def blocked_until(self, username: str) -> datetime | None:
        with self._lock:
            until = self._blocked_until.get(username)
            if until is None:
                return None
            if now_kst() >= until:
                del self._blocked_until[username]
                return None
            return until

    def record_failure(self, username: str) -> None:
        with self._lock:
            n = self._fails.get(username, 0) + 1
            if n >= LOGIN_THROTTLE_FAILURES:
                self._blocked_until[username] = now_kst() + LOGIN_THROTTLE_WAIT
                n = 0
            self._fails[username] = n

    def reset(self, username: str) -> None:
        with self._lock:
            self._fails.pop(username, None)
            self._blocked_until.pop(username, None)

    def clear(self) -> None:
        """테스트용: 전부 비운다."""
        with self._lock:
            self._fails.clear()
            self._blocked_until.clear()


login_throttle = LoginThrottle()
