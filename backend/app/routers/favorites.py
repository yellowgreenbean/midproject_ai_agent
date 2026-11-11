"""자주 쓰는 계좌 — 기획서 Part 5 6장 간편 송금, 16장 GET/POST/PATCH/DELETE /favorite-accounts (TRX-F05).

- 최대 20개, 별칭, 순서 바꾸기(sort_order 0 = 맨 위), 삭제. 등록할 때 받는 계좌를 확인하고 예금주를 저장한다.
- 같은 (은행, 계좌번호)를 또 등록하면 새로 만들지 않고 있던 줄을 돌려준다(표의 UNIQUE).
- 응답의 account_display: 두린은행 계좌는 하이픈 넣은 번호, 타행은 번호 그대로 (화면 SavedTarget)
"""

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.common.ownership import get_owned_or_404
from app.deps import DB, CurrentUserId
from app.errors import ApiError, not_found
from app.models import Account, FavoriteAccount
from app.routers.transfer_targets import find_target
from app.rules import FAVORITE_ACCOUNTS_MAX, OUR_BANK
from app.schemas import FavoriteAccountOut
from app.security import new_id

router = APIRouter(tags=["favorite-accounts"])
FavoriteId = Annotated[str, Path(alias="favoriteId")]


def _out(db, favs) -> list[FavoriteAccountOut]:
    ours = [f.account_no for f in favs if f.bank == OUR_BANK]
    display = dict(db.execute(select(Account.resAccount, Account.resAccountDisplay)
                              .where(Account.resAccount.in_(ours))).all()) if ours else {}
    return [FavoriteAccountOut(id=f.id, bank=f.bank, account_no=f.account_no, holder_name=f.holder_name,
                               nickname=f.nickname, sort_order=f.sort_order,
                               account_display=display.get(f.account_no, f.account_no) if f.bank == OUR_BANK else f.account_no)
            for f in favs]


def _mine(db, user_id: str) -> list[FavoriteAccount]:
    return list(db.scalars(select(FavoriteAccount).where(FavoriteAccount.user_id == user_id)
                           .order_by(FavoriteAccount.sort_order, FavoriteAccount.id)))


@router.get("/favorite-accounts", response_model=list[FavoriteAccountOut])
def list_favorite_accounts(db: DB, user_id: CurrentUserId):
    return _out(db, _mine(db, user_id))


class FavoriteIn(BaseModel):
    bank: str = Field(max_length=30)
    account_no: str = Field(max_length=20)
    nickname: str | None = Field(default=None, max_length=50)


@router.post("/favorite-accounts", response_model=FavoriteAccountOut, status_code=201)
def add_favorite_account(body: FavoriteIn, db: DB, user_id: CurrentUserId):
    same = db.scalar(select(FavoriteAccount).where(FavoriteAccount.user_id == user_id, FavoriteAccount.bank == body.bank,
                                                   FavoriteAccount.account_no == body.account_no))
    if same is not None:
        return _out(db, [same])[0]
    _, holder, _ = find_target(db, user_id, body.bank, body.account_no)  # 없는 계좌·자릿수 오류는 여기서 거절
    favs = _mine(db, user_id)
    if len(favs) >= FAVORITE_ACCOUNTS_MAX:
        raise ApiError(409, "FAVORITE_LIMIT_EXCEEDED", f"자주 쓰는 계좌는 {FAVORITE_ACCOUNTS_MAX}개까지 등록할 수 있어요.")
    f = FavoriteAccount(id=new_id("fav"), user_id=user_id, bank=body.bank, account_no=body.account_no, holder_name=holder,
                        nickname=body.nickname or None,
                        sort_order=(db.scalar(select(func.max(FavoriteAccount.sort_order))
                                              .where(FavoriteAccount.user_id == user_id)) or 0) + 1)
    db.add(f)
    db.commit()
    return _out(db, [f])[0]


class FavoritePatch(BaseModel):
    nickname: str | None = Field(default=None, max_length=50)  # null·"" = 별칭 지우기
    sort_order: int | None = Field(default=None, ge=0)  # 이 자리로 옮긴다 (0 = 맨 위)


def _favorite(db, favorite_id: str, user_id: str) -> FavoriteAccount:
    return get_owned_or_404(db, FavoriteAccount, favorite_id, user_id,
                            not_found("FAVORITE_NOT_FOUND", "자주 쓰는 계좌를 찾을 수 없어요."))


@router.patch("/favorite-accounts/{favoriteId}", response_model=list[FavoriteAccountOut])
def update_favorite_account(favorite_id: FavoriteId, body: FavoritePatch, db: DB, user_id: CurrentUserId):
    f = _favorite(db, favorite_id, user_id)
    if "nickname" in body.model_fields_set:
        f.nickname = body.nickname or None
    if body.sort_order is not None:  # 빼서 그 자리에 끼우고 0부터 다시 번호를 매긴다
        favs = [x for x in _mine(db, user_id) if x.id != f.id]
        favs.insert(min(body.sort_order, len(favs)), f)
        for i, x in enumerate(favs):
            x.sort_order = i
    db.commit()
    return _out(db, _mine(db, user_id))


@router.delete("/favorite-accounts/{favoriteId}", response_model=list[FavoriteAccountOut])
def delete_favorite_account(favorite_id: FavoriteId, db: DB, user_id: CurrentUserId):
    db.delete(_favorite(db, favorite_id, user_id))
    db.commit()
    return _out(db, _mine(db, user_id))
