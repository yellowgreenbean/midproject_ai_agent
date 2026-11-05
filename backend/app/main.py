from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.config import settings
from app.routers import accounts, favorites, transactions, transfer_targets, transfers

app = FastAPI(title="두린은행 계좌·거래 API", version="0.2.0")
errors.install(app)

# 화면(다른 포트)에서 이 API 를 부를 수 있게 허용한다. allow_credentials=True 라야 브라우저가
# 로그인 쿠키를 같이 보내고 받는다 — 이때 허용 주소는 "*" 가 아니라 정확한 목록이어야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    # Idempotency-Key: 이체·가입 중복 방지(Part 5 16장), X-User-Id: 로그인 전 임시 회원 지정(app/deps.py)
    allow_headers=["Content-Type", "Idempotency-Key", "X-User-Id"],
)

app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(transfer_targets.router)
app.include_router(favorites.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
