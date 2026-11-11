"""두린 챗봇 — LangGraph 로 직접 그린 Tool 호출 반복 (docs/기획서.md Part 3 5장 「추천 처리 구조」).

    START → llm ─(Tool 을 부르면)→ tools ─(가입 준비 끝)→ confirm ─(interrupt: 확인 질문)→ (다음 요청에서 이어 감)
             ↑                       │                       ├─ 네     → 가입 화면 링크 → END
             └──────(그 밖)──────────┘                       ├─ 아니요 → 취소 → END
             └───────────────────────────────────────────────┴─ 다른 말 → llm (새 요청으로)
            llm ─(글로 답하면)→ END

- llm: Gemini 가 대화와 Tool 결과를 보고 답하거나 Tool 을 부른다.
- tools: Tool 을 실행한다. 회원(user_id)과 DB 는 Tool 인자가 아니라 config 로 받는다 — LLM 이 남의 user_id 를 넣을 수 없다.
  Tool 은 기존 API 함수(계좌·거래·이체·상품)를 그대로 부르므로 본인 확인·오류 코드도 API 와 같다.
- 인증 게이트: 로그인 상태에 따라 그래프를 따로 쓴다. 손님은 문서·상품 검색만, 회원은 내 정보 조회와 가입 준비까지.
  LLM 에 묶는 Tool 목록(bind_tools)과 실행하는 ToolNode 를 둘 다 바꾼다 — 손님의 LLM 은 회원 Tool 이 있는지도 모르고,
  이름을 지어 불러도 ToolNode 에 없어 실행되지 않는다.
- 상태(ChatState): 메시지 + 가입 준비 값(직전 상품·금액·기간). prepare_subscription 이 이번에 들은 값만 받아 이전 값과 합친다.
  값 검증(판매 중·금액·기간·출금 계좌)은 LLM 이 아니라 상품 API 의 검사 함수(app/routers/products.py estimate)가 한다.
- 실행 전 확인: 가입 준비가 끝나면 confirm 노드가 interrupt 로 멈추고 DB 값으로 만든 요약을 묻는다.
  '네' 일 때만 가입 화면(#/products/<id>/subscribe?금액·기간) 링크를 준다. 실제 가입과 본인 확인(step-up, 비밀번호)은 그 화면이 한다.
  챗봇은 돈이 움직이는 작업(송금·가입·해지)을 직접 실행하지 않는다.
- 멈춘 대화를 이어 가려고 회원 그래프는 InMemorySaver 에 대화(thread)마다 상태를 둔다. thread 키는 '<user_id>:<thread_id>' 라서
  남의 thread_id 를 보내도 그 사람 상태를 읽지 못한다. 서버를 다시 켜면 사라진다 — 그때는 화면이 보낸 history 로 다시 시작한다.
- 화면 링크: LLM 이 답 끝에 [[#/경로]] 를 적으면 split_links 가 실제 있는 화면만 골라 links 로 뺀다.
  가입 화면 링크는 confirm 노드의 '네' 답에서만 살린다 — LLM 이 확인 없이 적어도 버린다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from typing import Annotated, Literal

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode
from langgraph.types import Command, interrupt
from sqlalchemy.orm import Session

from app import rag
from app.config import settings
from app.errors import ApiError
from app.models import Product, User
from app.routers import products
from app.routers.accounts import list_accounts
from app.routers.favorites import list_favorite_accounts
from app.routers.subscriptions import list_my_subscriptions
from app.routers.transactions import list_transactions
from app.routers.transfers import list_transfers
from app.rules import now_kst
from app.schemas import TransferOut

# frontend/src/App.tsx 의 PAGES · TITLES 와 같은 화면 (로그인 전 화면은 손님 안내용 /login 만)
SCREENS = {
    "/login": "로그인", "/home": "홈", "/products": "금융상품", "/my/savings": "내 가입 상품", "/accounts": "내 계좌", "/accounts/new": "계좌 개설",
    "/notifications": "알림", "/transfer": "송금", "/transfers": "이체 결과", "/scheduled-transfers": "예약·자동이체",
    "/transactions": "거래내역", "/settings": "마이페이지", "/settings/profile": "내 정보", "/settings/password": "비밀번호 변경",
    "/settings/pin": "간편 비밀번호", "/settings/terms": "약관 및 동의 내역", "/settings/withdraw": "회원 탈퇴",
    "/settings/limits": "이체 한도", "/cards": "내 카드", "/cards/apply": "카드 신청",
    "/cards/points": "카드 포인트",
}
SUBSCRIBE_SCREEN = re.compile(r"/products/[\w-]+/subscribe")  # 확인('네')을 받은 답에서만 링크로 살린다
DETAIL_SCREENS = [
    (re.compile(r"/accounts/[\w-]+"), "계좌 상세"), (re.compile(r"/my/savings/[\w-]+"), "가입 상품 상세"),
    (re.compile(r"/products/[\w-]+"), "상품 상세"), (SUBSCRIBE_SCREEN, "상품 가입"),
    (re.compile(r"/transfers/[\w-]+"), "이체 결과"), (re.compile(r"/cards/[\w-]+"), "카드 상세"),
    (re.compile(r"/card-bills/[\w-]+"), "카드 청구서"),
]
# Gemini 가 [[#accounts]] 처럼 / 를 빼먹기도 한다(2026-11-10 실측). ?amount=…&months=… 는 가입 화면 입력칸을 미리 채운다
LINK = re.compile(r"\[\[#?/?([\w/-]+)(\?[\w=&]+)?\]\]")

PROMPT = """너는 두린은행 모바일 앱의 상담 챗봇 '두린 AI'다. 오늘은 {today}(한국 시간)이다.
- {who}
- 해요체로 짧고 정확하게 답한다.
- 사용자의 계좌·잔액·가입 상품·거래내역·이체 내역은 반드시 Tool 로 조회한 값만 말한다. 지어내지 않는다.
- 예금·적금 상품의 id·금리·가입 조건(금액·기간)은 search_products·product_detail 로 조회한 값만 말한다.
- 약관·상품 설명·수수료·제도 질문은 search_documents 로 찾은 문서에 근거해 답하고 끝에 (출처: 문서 제목) 을 붙인다.
  문서에 근거가 없으면 '확인할 수 없어요'라고 답한다. 실제 적용 금리·가입 가능 여부는 상품 화면에서 확인하라고 안내한다.
- {subscribe}
- 송금·중도 해지·카드 신청 같은 실행은 직접 하지 않고 해당 화면을 안내한다.
- 계좌 해지·정지 해제는 해당 계좌 상세 화면(/accounts/<계좌 id>)에서 한다. 회원 탈퇴(/settings/withdraw)와 다르다.
- 화면을 안내할 때는 답 끝에 [[#경로]] 를 적는다(예: [[#/accounts]]). 쓸 수 있는 경로: {screens}
  그리고 /accounts/<계좌 id>, /my/savings/<가입 id>, /products/<상품 id>, /transfers/<이체 id>
- 어느 계좌인지·기간 등 필요한 정보가 부족하고 Tool 로 알아낼 수 없으면 되묻는다. 이전 대화에서 말한 계좌·상품은 이어서 쓴다.
- Tool 이 '오류 코드: 메시지' 를 돌려주면 그 메시지를 그대로 전한다."""
WHO = {
    True: "지금 사용자는 로그인한 회원이다.",
    False: "지금 사용자는 로그인하지 않은 손님이다. 계좌·잔액·가입 상품·거래·이체 같은 개인 정보는 조회할 수 없으니 로그인을 안내한다([[#/login]]).",
}
SUBSCRIBE = {
    True: "예금·적금에 가입하겠다고 하면 prepare_subscription 을 부른다. 이번 말에서 새로 들은 상품·금액·기간만 넣는다(이전 값은 Tool 이 기억한다).\n"
          "  결과가 MISSING 이면 빠진 값만 묻는다. 가입은 직접 하지 않고, 가입 화면 링크도 직접 적지 않는다(확인 단계가 준다).\n"
          "- 송금·이체를 요청하면 대화에서 값을 모아 「{받는 사람 별칭}에게 {내 출금 계좌 별명}계좌로 {금액} 송금해줘」 꼴을 채운다.\n"
          "  받는 사람은 my_favorites 의 별칭(nickname, 없으면 예금주 holder_name), 출금 계좌는 my_accounts 의 별명(resAccountNickName, 없으면 "
          "계좌 이름 resAccountName)에서 찾는다. 금액·출금 계좌가 빠졌거나 별명이 여러 곳에 맞으면 되묻는다. 이전 대화에서 말한 값은 이어서 쓴다.\n"
          "  다 모이면 그 문장으로 정리해 보여 주고 답 끝에 [[#/transfer?from=<출금 계좌 id>&bank=<은행>&to=<계좌번호 account_no>&amount=<원 단위 숫자>]] 를 "
          "적는다(은행 이름은 Tool 값 그대로, 값은 Tool 로 조회한 것만).\n"
          "  받는 사람이 my_favorites 에 없으면 자주 쓰는 계좌에 없다고 알리고 bank·to 를 뺀 링크를 준다(받는 계좌는 화면에서 입력). "
          "송금은 직접 하지 않는다 — 본인 확인과 실행은 송금 화면이 한다.",
    False: "예금·적금 가입은 로그인한 뒤에 할 수 있다고 안내한다([[#/login]]). 상품 조회·설명은 손님도 할 수 있다.\n"
           "- 송금·이체도 로그인한 뒤에 할 수 있다고 안내한다([[#/login]]).",
}
MAX_TURNS = 10  # LLM 에 보내는 최근 대화(사용자 말 기준) — 회원 대화는 서버에 쌓이므로 보낼 때 자른다

# 확인 질문에 대한 답. 짧은 답만 본다 — '네 근데 금액은 30만 원으로' 같은 말은 새 요청으로 LLM 에 넘긴다
YES = re.compile(r"(네|예|응|어|ㅇㅇ|ㅇ|좋아요?|그래요?|맞아요?|확인|진행(해(줘|주세요|요)?)?|가입(할게요?|해(줘|주세요|요)?)?|yes|ok|okay)")
NO = re.compile(r"(아니(요|오)?|아뇨|ㄴㄴ|ㄴ|싫어요?|취소(해(줘|주세요|요)?)?|안\s?(할래요?|해요?)|그만(할래요?|둘래요?)?|no)")
CONFIRM_CHOICES = ["네", "아니요"]
CONFIRMED = "subscribe_confirmed"  # 확인('네')을 받은 답 메시지의 name — 이 답만 가입 화면 링크를 살린다


class ChatState(MessagesState):
    """대화 상태. 메시지에 더해 가입 준비 값(직전 상품·금액·기간)을 들고 다닌다. 아직 정하지 않은 값은 없음(None)."""

    product_id: str | None
    amount: int | None  # 원. 예금은 넣을 금액, 적금은 월 납입액
    months: int | None
    days: int | None  # 일 단위 상품(표지어음·CD)의 기간
    ready: bool  # 가입 준비가 끝나 확인을 받아야 함


def _ctx(config: RunnableConfig) -> tuple[Session, str]:
    c = config["configurable"]
    return c["db"], c["user_id"]


@cache
def gemini():
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


@tool
def search_documents(query: str, config: RunnableConfig) -> list[dict]:
    """두린은행 약관·상품설명서·특약·동의서·카드 약관·수수료·FAQ·예금자보호·법령 문서에서 질문과 관련된 조항을 찾는다."""
    db, _ = _ctx(config)
    return [
        {"source": meta["source"], "title": " > ".join(p for p in (meta["title"], meta["chapter"], meta["article"]) if p), "content": content}
        for _, _, content, meta in rag.search(db, gemini(), query, settings.rag_experiment)
    ]


# ---- 예금·적금 상품 (상품 API 함수를 그대로 부른다 — app/routers/products.py) ----

TYPE_NAME = {"TIME_DEPOSIT": "정기예금", "INSTALLMENT_SAVINGS": "적금"}


@tool
def search_products(
    config: RunnableConfig, query: str | None = None, type: Literal["TIME_DEPOSIT", "INSTALLMENT_SAVINGS"] | None = None,
) -> list[dict]:
    """판매 중인 예금·적금 상품 목록(최고 금리 높은 순) — 상품 id·이름·종류·기본/최고 금리(연 %)·가입 기간.
    이름 일부(query)나 종류(TIME_DEPOSIT 정기예금 · INSTALLMENT_SAVINGS 적금)로 거른다."""
    db, _ = _ctx(config)
    return jsonable_encoder(products.list_products(db, q=query, type=type, sort="rate"))


@tool
def product_detail(product_id: str, config: RunnableConfig) -> dict:
    """예금·적금 상품 하나의 설명·기간별 금리(연 %, 기본+우대)·가입 조건(금액·기간·1인당 개수)·가입 가능 여부·상품설명서 이름."""
    db, _ = _ctx(config)
    return jsonable_encoder(products.product_detail(product_id, db))


@dataclass
class Plan:
    """가입 준비 값을 상품 API 의 검사 함수로 본 결과. error 가 있으면 그 값은 쓰지 않는다."""

    product: Product | None = None
    day_unit: bool = False
    estimate: products.EstimateOut | None = None
    missing: list[str] = field(default_factory=list)
    error: ApiError | None = None


def _check(db: Session, user_id: str, s: dict) -> Plan:
    """회원 상태 · 판매 중 · 금액 · 기간 · 출금 계좌 · 1인당 개수. 금액·기간 규칙은 예상 이자 API(products.estimate)와 같은 함수.
    어느 계좌에서 낼지·잔액·본인 확인은 가입 화면과 POST /subscriptions 가 다시 본다."""
    if not s.get("product_id"):
        return Plan(missing=["상품"])
    try:
        p = products.get_product_or_404(db, s["product_id"])
    except ApiError as e:
        return Plan(error=e)
    plan = Plan(product=p, day_unit=products.day_unit(db, p.id))
    if not s.get("amount"):
        plan.missing.append("월 납입액" if p.type == "INSTALLMENT_SAVINGS" else "넣을 금액")
    if not (s.get("days") if plan.day_unit else s.get("months")):
        plan.missing.append("기간(일)" if plan.day_unit else "기간(개월)")
    if plan.missing:
        return plan
    try:
        products.check_user(db.get(User, user_id))
        plan.estimate = products.estimate(db, p.id, str(s["amount"]), 0 if plan.day_unit else s["months"],
                                          s["days"] if plan.day_unit else None)
        if not any(a.account_type == "CHECKING" and a.lifecycle_status == "ACTIVE" for a in list_accounts(db, user_id, None, None)):
            raise ApiError(409, "NO_SOURCE_ACCOUNT", "출금할 정상 입출금 계좌가 없어요. 먼저 계좌를 만들어 주세요. [[#/accounts/new]]")
        products.check_limit(db, user_id, p.id)
    except ApiError as e:
        plan.error = e
    return plan


# 이 오류가 나면 그 값은 기억하지 않는다(다음에 다시 묻는다)
FORGET = {"PRODUCT_NOT_FOUND": ["product_id"], "PRODUCT_NOT_ON_SALE": ["product_id"], "NOT_SUBSCRIBABLE": ["product_id"],
          "TERM_UNIT_NOT_SUPPORTED": ["product_id"], "SUBSCRIPTION_LIMIT_EXCEEDED": ["product_id"],
          "AMOUNT_OUT_OF_RANGE": ["amount"], "TERM_OUT_OF_RANGE": ["months", "days"], "RATE_NOT_FOUND": ["months", "days"]}


@tool
def prepare_subscription(
    config: RunnableConfig,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    product_id: str | None = None,
    amount: int | None = None,
    months: int | None = None,
    days: int | None = None,
) -> Command:
    """예금·적금 가입을 준비한다(가입을 실행하지는 않는다). 사용자가 가입하겠다고 하면 부른다.
    이번 말에서 새로 들은 값만 넣는다 — 빠진 값은 이전 대화에서 정한 상품·금액·기간을 그대로 쓴다.
    product_id: search_products 로 찾은 상품 id. amount: 원 단위 — 정기예금은 넣을 금액, 적금은 월 납입액.
    months: 가입 기간(개월). days: 일 단위 상품(표지어음·CD)의 기간(일).
    결과가 READY 면 확인 단계로 넘어가고, MISSING 이면 빠진 값을 사용자에게 묻는다."""
    db, user_id = _ctx(config)
    new = {"product_id": product_id, "amount": amount, "months": months, "days": days}
    slots = {k: v if v is not None else state.get(k) for k, v in new.items()}
    if product_id and product_id != state.get("product_id") and (months is None and days is None):
        slots["months"] = slots["days"] = None  # 상품을 바꾸면 이전 상품의 기간은 안 맞을 수 있다 — 다시 묻는다
    plan = _check(db, user_id, slots)
    if plan.error:
        slots |= dict.fromkeys(FORGET.get(plan.error.code, []))
        result = f"{plan.error.code}: {plan.error.message}"
    elif plan.missing:
        result = f"MISSING: {', '.join(plan.missing)}"
    else:
        result = "READY: 사용자에게 가입 내용을 확인받는 중"
    ready = plan.error is None and not plan.missing
    return Command(update={**slots, "ready": ready, "messages": [ToolMessage(result, tool_call_id=tool_call_id)]})


# ---- 회원 조회 ----

@tool
def my_accounts(config: RunnableConfig) -> list[dict]:
    """내 계좌 목록과 잔액(해지 계좌 제외). 계좌 id 는 거래내역 조회와 화면 링크에 쓴다."""
    return jsonable_encoder(list_accounts(*_ctx(config)))


@tool
def my_subscriptions(config: RunnableConfig) -> list[dict]:
    """내가 가입한 예금·적금 목록(상품명·원금·적용 금리·만기일)."""
    return jsonable_encoder(list_my_subscriptions(*_ctx(config)))


@tool
def account_transactions(
    account_id: str, config: RunnableConfig, start_date: date | None = None, end_date: date | None = None,
    direction: Literal["IN", "OUT"] | None = None,
) -> dict:
    """내 계좌 하나의 거래내역(최신순 최대 20건). 기간(YYYY-MM-DD, 양 끝 포함)과 입금(IN)·출금(OUT)으로 거를 수 있다."""
    db, user_id = _ctx(config)
    page = list_transactions(account_id=account_id, db=db, user_id=user_id, start_date=start_date, end_date=end_date,
                             direction=direction, limit=20, cursor=None)
    return jsonable_encoder(page)


@tool
def my_transfers(config: RunnableConfig) -> list[dict]:
    """내 이체(송금) 결과 최근 20건 — 받는 사람·금액·상태·실패 사유."""
    return jsonable_encoder([TransferOut.model_validate(t) for t in list_transfers(*_ctx(config))[:20]])


@tool
def my_favorites(config: RunnableConfig) -> list[dict]:
    """내 자주 쓰는 계좌(받는 사람) 목록 — 별칭 nickname·예금주 holder_name·은행 bank·계좌번호 account_no. 송금 화면 링크를 채울 때 쓴다."""
    return jsonable_encoder(list_favorite_accounts(*_ctx(config)))


TOOLS = {  # 로그인했는가 → 쓸 수 있는 Tool
    False: [search_documents, search_products, product_detail],
    True: [search_documents, search_products, product_detail, prepare_subscription,
           my_accounts, my_subscriptions, account_transactions, my_transfers, my_favorites],
}


def _tool_error(e: ApiError) -> str:
    """Tool 안에서 난 API 오류(예: 남의 계좌)는 LLM 에게 결과로 돌려준다 — 실패 사유를 지어내지 않게."""
    return f"{e.code}: {e.message}"


@cache
def model(member: bool):
    from langchain_google_genai import ChatGoogleGenerativeAI

    # v1beta: google-genai 3.0 의 기본(v1)은 함수 호출을 받지 않는다(2026-11-10 실측, 400 'Function calling is not enabled')
    return ChatGoogleGenerativeAI(
        model=settings.chat_model, google_api_key=settings.gemini_api_key, temperature=0, api_version="v1beta"
    ).bind_tools(TOOLS[member])


def recent(messages: list[AnyMessage]) -> list[AnyMessage]:
    """최근 MAX_TURNS 번의 사용자 말부터. 사용자 말에서 끊으므로 Tool 호출과 그 결과가 갈라지지 않는다."""
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    return messages[starts[-MAX_TURNS]:] if len(starts) > MAX_TURNS else messages


# ---- 노드와 분기 ----

def route(state: ChatState):
    """llm 다음: Tool 을 불렀으면 tools, 글로 답했으면 끝."""
    return "tools" if state["messages"][-1].tool_calls else END


def route_after_tools(state: ChatState):
    """tools 다음: 가입 준비가 끝났으면(prepare_subscription 이 READY) 확인 단계로, 아니면 llm 이 결과를 보고 답한다."""
    return "confirm" if state.get("ready") else "llm"


def route_after_confirm(state: ChatState):
    """confirm 다음: 확인 대신 다른 말을 했으면(마지막이 사용자 말) llm 이 새 요청으로 받는다."""
    return "llm" if isinstance(state["messages"][-1], HumanMessage) else END


def _won(n: int) -> str:
    return f"{n:,}원"


def subscribe_path(state: dict, plan: Plan) -> str:
    term = f"days={state['days']}" if plan.day_unit else f"months={state['months']}"
    return f"/products/{state['product_id']}/subscribe?amount={state['amount']}&{term}"


def _ymd(d: str) -> str:
    return f"{d[:4]}.{d[4:6]}.{d[6:]}"


def confirm_question(state: dict, plan: Plan) -> str:
    """확인 질문 — LLM 이 아니라 DB 값과 예상 이자 계산(products.estimate)으로 만든다(금액·기간·금리를 지어낼 수 없게)."""
    p, est = plan.product, plan.estimate
    money = f"매달 {_won(state['amount'])}씩" if p.type == "INSTALLMENT_SAVINGS" else f"{_won(state['amount'])}을"
    term = f"{state['days']}일" if plan.day_unit else f"{state['months']}개월"
    return (f"{p.name}({TYPE_NAME[p.type]})에 {money} {term} 동안 가입하려고 해요.\n"
            f"기본 금리 연 {est.rate}%로 만기일({_ymd(est.maturity_date)})에 세전 이자 {_won(int(est.interest))}, "
            f"만기 금액 {_won(int(est.maturity_amount))}이 예상돼요(우대 금리 제외).\n"
            "출금 계좌 선택과 본인 확인(비밀번호)은 가입 화면에서 해요. 가입 화면으로 안내할까요?")


def _short(text: str) -> str:
    return re.sub(r"[\s.!~,?]+", "", text).lower()


def confirm(state: ChatState, config: RunnableConfig):
    """실행 전 확인. interrupt 로 그래프를 멈추고 질문을 화면에 보낸다 → 다음 요청의 말(resume)을 받아 갈래를 나눈다.
    다시 이어 가면 이 노드는 처음부터 다시 돈다 — interrupt 앞은 같은 값을 내는 읽기만 한다."""
    db, user_id = _ctx(config)
    plan = _check(db, user_id, state)  # 멈춘 사이 바뀐 것(판매 중지·계좌 정지)도 여기서 다시 본다
    if plan.error or plan.missing:  # 이어 가는 사이 조건이 깨졌다
        reason = plan.error.message if plan.error else f"{', '.join(plan.missing)}이 정해지지 않았어요."
        return {"ready": False, "messages": [AIMessage(f"가입 안내를 이어 갈 수 없어요. {reason}")]}
    question = confirm_question(state, plan)
    reply = str(interrupt({"question": question}))
    asked = [AIMessage(question), HumanMessage(reply)]
    said = _short(reply)
    if YES.fullmatch(said):
        done = AIMessage(f"가입 화면으로 안내할게요. 금액과 기간은 채워 두었어요. 출금 계좌를 고르고 비밀번호로 본인 확인을 하면 가입돼요. "
                         f"[[#{subscribe_path(state, plan)}]]", name=CONFIRMED)
        return {"ready": False, "messages": [*asked, done]}
    if NO.fullmatch(said):
        return {"ready": False, "messages": [*asked, AIMessage("알겠어요, 가입 안내를 멈췄어요. 금액이나 기간을 바꾸고 싶으면 말해 주세요.")]}
    return {"ready": False, "messages": asked}  # 다른 말 → llm 이 새 요청으로 처리 (가입 값은 기억한다)


def build_graph(member: bool):
    def llm(state: ChatState):
        system = SystemMessage(PROMPT.format(today=now_kst().date().isoformat(), who=WHO[member], subscribe=SUBSCRIBE[member],
                                             screens=", ".join(SCREENS)))
        return {"messages": [model(member).invoke([system, *recent(state["messages"])])]}

    graph = StateGraph(ChatState)
    graph.add_node("llm", llm)
    graph.add_node("tools", ToolNode(TOOLS[member], handle_tool_errors=_tool_error))
    graph.add_node("confirm", confirm)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", route, ["tools", END])
    graph.add_conditional_edges("tools", route_after_tools, ["confirm", "llm"])
    graph.add_conditional_edges("confirm", route_after_confirm, ["llm", END])
    # 손님은 가입 준비 Tool 이 없어 confirm 에 닿지 않는다 → 상태를 서버에 두지 않는다(화면이 보낸 history 만 씀)
    return graph.compile(checkpointer=InMemorySaver() if member else None)


GRAPHS = {member: build_graph(member) for member in TOOLS}


def split_links(reply: str, confirmed: bool = False) -> tuple[str, list[dict]]:
    """[[#/경로]] 를 답에서 빼서 links 로. 없는 화면은 버린다. 가입 화면은 확인('네')을 받은 답(confirmed)에서만."""
    links: list[dict] = []
    for p, query in LINK.findall(reply):
        path = "/" + p
        label = SCREENS.get(path) or next((name for rx, name in DETAIL_SCREENS if rx.fullmatch(path)), None)
        if SUBSCRIBE_SCREEN.fullmatch(path) and not confirmed:
            label = None
        href = f"#{path}{query}"
        if label and all(x["href"] != href for x in links):
            links.append({"label": label, "href": href})
    return LINK.sub("", reply).strip(), links


@dataclass
class Answer:
    reply: str
    links: list[dict]
    suggestions: list[str]
    thread_id: str | None  # 회원 대화 번호 — 화면이 다음 요청의 context 에 그대로 돌려보낸다


def answer(db: Session, user_id: str | None, message: str, history: list[dict], thread_id: str | None = None) -> Answer:
    """user_id: 세션의 회원(손님이면 None). history: [{role: user|assistant, text}] — 화면이 보낸 이전 대화.
    회원은 thread_id 로 서버에 남은 대화를 이어 간다. 확인 질문에서 멈춰 있으면 이번 말이 그 답(resume)이다."""
    member = user_id is not None
    graph = GRAPHS[member]
    # max_concurrency 1: Tool 여러 개를 한 번에 부르면 ToolNode 가 스레드로 나눠 도는데, DB 세션 하나를 여러 스레드가 쓰면 안 된다
    config = {"configurable": {"db": db, "user_id": user_id}, "recursion_limit": 12, "max_concurrency": 1}
    turns = [HumanMessage(h["text"]) if h["role"] == "user" else AIMessage(h["text"]) for h in history]
    start = {"messages": [*turns, HumanMessage(message)]}
    if not member:
        thread_id, run = None, start
    else:
        thread_id = thread_id or uuid.uuid4().hex
        config["configurable"]["thread_id"] = f"{user_id}:{thread_id}"  # 남의 thread_id 를 보내도 다른 칸이 된다
        saved = graph.get_state(config)
        if saved.next:  # 확인 질문에서 멈춰 있다
            run = Command(resume=message)
        elif saved.values.get("messages"):  # 이어지는 대화 — 상태(직전 상품·금액·기간)는 서버에 있다
            run = {"messages": [HumanMessage(message)]}
        else:  # 새 대화, 또는 서버를 다시 켜서 사라진 대화 → 화면이 보낸 history 로 시작
            run = start
    out = graph.invoke(run, config)
    if out.get("__interrupt__"):
        return Answer(out["__interrupt__"][0].value["question"], [], CONFIRM_CHOICES, thread_id)
    last = out["messages"][-1]
    reply, links = split_links(last.text, confirmed=last.name == CONFIRMED)
    return Answer(reply, links, [], thread_id)
