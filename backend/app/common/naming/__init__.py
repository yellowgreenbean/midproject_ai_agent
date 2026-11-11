"""API 응답 이름·형식 규칙 중 값 모양 — 기획서 Part 6 C-5.

- 금액: DB 는 원 단위 정수, API 응답은 문자열   → Money          "amount": "50000"
- 시각: ISO 8601 한국 시간                      → KstDatetime    "2026-11-03T13:24:00+09:00"
"""

from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

from app.rules import KST


def _to_kst_iso(v: datetime) -> str:
    # DB 에는 한국 시각이 시간대 없이 저장돼 있으므로 +09:00 을 붙여 내보낸다.
    if v.tzinfo is None:
        v = v.replace(tzinfo=KST)
    return v.astimezone(KST).isoformat()


KstDatetime = Annotated[datetime, PlainSerializer(_to_kst_iso, return_type=str)]
Money = Annotated[int, PlainSerializer(str, return_type=str)]
