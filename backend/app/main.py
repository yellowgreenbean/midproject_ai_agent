import threading
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import errors, jobs
from app.config import settings
from app.routers import (
    accounts, agent, auth, card_applications, card_bills, card_points, cards, consents, external, favorites, notifications, password, pin, products, signup, subscriptions,
    transactions, transfer_targets, transfers, users, withdrawal,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 1분 스케줄러 (Part 5 8장 「배치가 1분마다」, 사용자 결정 2026-11-10). 서버를 끄면 같이 멈춘다.
    # shortcut: 서버 프로세스 안의 스레드 — 서버가 꺼져 있던 동안의 예약은 다시 켰을 때 밀린 것부터 실행한다
    stop = threading.Event()
    if settings.scheduler_enabled:
        def loop():
            while not stop.wait(60):
                jobs.run_minutely()
        threading.Thread(target=loop, name="scheduler", daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="두린은행 계좌·거래 API", version="0.3.0", lifespan=lifespan)
errors.install(app)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


# CSRF 방어 (Part 1 8.1 「쿠키 및 CSRF 방어」): 쿠키로 로그인하므로, 상태를 바꾸는 요청은
# 허용한 화면 주소(CORS 목록)나 이 API 자신(Swagger)에서 온 것만 받는다. Origin 이 없는 요청(curl·테스트)은 통과.
@app.middleware("http")
async def check_origin(request: Request, call_next):
    if request.method in UNSAFE_METHODS:
        origin = request.headers.get("origin")
        same_origin = origin is not None and urlsplit(origin).netloc == request.headers.get("host")
        if origin and origin not in settings.cors_origin_list and not same_origin:
            return errors.error_response(403, "ORIGIN_NOT_ALLOWED", "허용되지 않은 곳에서 온 요청이에요.")
    return await call_next(request)


# 화면(다른 포트)에서 이 API 를 부를 수 있게 허용한다. allow_credentials=True 라야 브라우저가
# 로그인 쿠키를 같이 보내고 받는다 — 이때 허용 주소는 "*" 가 아니라 정확한 목록이어야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    # Idempotency-Key: 이체·가입 중복 방지(Part 5 16장), X-User-Id: 개발용 회원 지정(AUTH_DEV_HEADER=true 일 때만)
    allow_headers=["Content-Type", "Idempotency-Key", "X-User-Id"],
    # 다른 포트의 화면이 세션 만료 시각(app/deps.py set_session_expires_header)을 읽을 수 있게
    expose_headers=["X-Session-Expires-At"],
)

app.include_router(auth.router)
app.include_router(signup.router)
app.include_router(password.router)
app.include_router(pin.router)
app.include_router(withdrawal.router)
app.include_router(users.router)
app.include_router(consents.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(transfer_targets.router)
app.include_router(favorites.router)
app.include_router(notifications.router)
app.include_router(external.router)
app.include_router(products.router)
app.include_router(subscriptions.router)
app.include_router(cards.router)
app.include_router(card_bills.router)
app.include_router(card_applications.router)
app.include_router(card_points.router)
app.include_router(agent.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
