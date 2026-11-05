from fastapi import FastAPI

from app.routers import accounts, external, favorites, transactions, transfers

app = FastAPI(title="MidProject 계좌·거래 API", version="0.1.0")

app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(favorites.router)
app.include_router(external.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
