"""CODEF 샌드박스 호출 — AGENTS.md 「실측으로 확인된 함정」 그대로.

- 토큰은 SDK 내장 샌드박스 인증으로 받는다(가입·공개키 불필요). SDK 의 request_product() 는 공개키 검사를 해서 쓰지 않고
  requests 로 직접 부른다. 요청 본문은 quote(json.dumps(...)), 응답은 unquote_plus 로 푼다.
- 실제 카드사·은행 계정, 개인 키는 쓰지 않는다(샌드박스 전용, 가짜 데이터).
"""

import json
import threading
import time
from urllib.parse import quote, unquote_plus

import requests

BASE = "https://sandbox.codef.io"
SANDBOX_CONNECTED_ID = "sandbox-test"
TOKEN_TTL = 60 * 60  # shortcut: 1시간마다 새로 받는다(토큰 자체는 더 오래 감). 401 이 나면 그때 다시 받게 바꿀 수 있다

_lock = threading.Lock()
_token: tuple[str, float] | None = None


def _get_token() -> str:
    global _token
    with _lock:
        if _token is None or time.time() - _token[1] > TOKEN_TTL:
            from easycodefpy import Codef, ServiceType

            _token = (Codef().request_token(ServiceType.SANDBOX), time.time())
        return _token[0]


def request(path: str, body: dict) -> dict:
    r = requests.post(BASE + path, headers={"Authorization": f"Bearer {_get_token()}"},
                      data=quote(json.dumps(body)), timeout=20)
    r.raise_for_status()
    return json.loads(unquote_plus(r.text))
