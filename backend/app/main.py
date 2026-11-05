from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.config import settings
from app.routers import accounts, auth, favorites, transactions, transfer_targets, transfers, users

app = FastAPI(title="두린은행 계좌·거래 API", version="0.3.0")
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
app.include_router(users.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(transfer_targets.router)
app.include_router(favorites.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
