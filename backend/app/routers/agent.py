"""POST /agent/chat — 두린 챗봇 (docs/기획서.md Part 3 5장·7장). 그래프·Tool 은 app/agent.py.

로그인 없이도 쓴다(손님은 문서 검색만 — app/agent.py 「인증 게이트」). 회원은 세션에서 꺼내 그래프 config 로만 넘긴다.
대화 맥락: 응답의 context(최근 대화 history + 회원 대화 번호 thread_id)를 화면이 다음 요청에 그대로 돌려보낸다.
회원 대화는 가입 확인(interrupt)을 이어 가려고 서버 메모리에도 남는다(app/agent.py) — 서버를 다시 켜면 history 로 다시 시작.
화면이 context 를 고쳐 보내도 Tool 은 언제나 로그인한 본인 데이터만 읽고, thread_id 는 회원별로 나뉜다.
"""

import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import agent
from app.deps import DB, OptionalUserId
from app.errors import ApiError

router = APIRouter(tags=["agent"])
log = logging.getLogger(__name__)

MAX_HISTORY = 20  # 최근 10번 주고받은 것까지 기억
GREETING = "안녕하세요, 두린 AI예요. 계좌·거래내역 조회나 상품·약관에 대해 궁금한 점을 물어보세요."
SUGGESTIONS = ["내 계좌 잔액 알려줘", "이번 달 거래내역 보여줘", "정기예금 중도해지하면 이자는 어떻게 돼?"]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class ChatContext(BaseModel):
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)
    thread_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$", description="회원 대화 번호 (손님은 없음)")


class ChatIn(BaseModel):
    message: str = Field(max_length=500, description="빈 글이면 대화 시작 인사")
    context: ChatContext | None = None


class Link(BaseModel):
    label: str
    href: str  # 화면 주소, 예: #/accounts


class ChatOut(BaseModel):
    reply: str
    links: list[Link]
    suggestions: list[str]
    context: ChatContext


@router.post("/agent/chat", response_model=ChatOut)
def chat(body: ChatIn, db: DB, user_id: OptionalUserId):
    ctx = body.context or ChatContext()
    message = body.message.strip()
    if not message:
        return ChatOut(reply=GREETING, links=[], suggestions=SUGGESTIONS, context=ctx)
    try:
        a = agent.answer(db, user_id, message, [t.model_dump() for t in ctx.history], ctx.thread_id)
    except Exception as e:  # Gemini 키 없음·한도 초과·네트워크 등 — 다른 API 는 그대로 돌게 챗봇만 실패
        log.exception("챗봇 답변 실패")
        raise ApiError(503, "CHAT_UNAVAILABLE", "지금은 답변할 수 없어요. 잠시 뒤 다시 시도해 주세요.") from e
    turns = [*ctx.history, Turn(role="user", text=message), Turn(role="assistant", text=a.reply[:4000])][-MAX_HISTORY:]
    return ChatOut(reply=a.reply, links=a.links, suggestions=a.suggestions, context=ChatContext(history=turns, thread_id=a.thread_id))
