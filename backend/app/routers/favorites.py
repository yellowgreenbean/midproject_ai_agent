from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DB, CurrentUserId
from app.models import FavoriteAccount
from app.schemas import FavoriteAccountOut

router = APIRouter(tags=["favorite-accounts"])


# 자주 쓰는 계좌 (Part 5 16장, 2차 — 지금은 조회만), sort_order 순
@router.get("/favorite-accounts", response_model=list[FavoriteAccountOut])
def list_favorite_accounts(db: DB, user_id: CurrentUserId):
    return db.scalars(
        select(FavoriteAccount)
        .where(FavoriteAccount.user_id == user_id)
        .order_by(FavoriteAccount.sort_order, FavoriteAccount.id)
    ).all()
