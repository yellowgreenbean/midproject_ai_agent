from fastapi import FastAPI

from app import errors
from app.routers import accounts, favorites, transactions, transfer_targets, transfers

app = FastAPI(title="두린은행 계좌·거래 API", version="0.2.0")
errors.install(app)

app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(transfer_targets.router)
app.include_router(favorites.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
