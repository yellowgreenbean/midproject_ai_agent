"""Idempotency-Key 헤더 — 같은 키로 다시 온 요청은 새로 처리하지 않고 처음 결과를 돌려준다(Part 5 16장).

라우터는 `idempotency_key: IdempotencyKey` 로 받기만 한다.
"""

from typing import Annotated

from fastapi import Header

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]
