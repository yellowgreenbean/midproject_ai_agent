"""다른 은행 내역 (CODEF) — 기획서 Part 5 10장, 15장 대응표, 16장.

    GET /external-transfers                                   다른 은행 이체내역 (TRX-F09) — docs/dummy/codef_transfer_results.json
    GET /external-deposit-accounts/{accountNo}/transactions   다른 은행 예적금 내역 (TRX-F14) — CODEF 샌드박스 실제 호출

- 우리 원장과 섞지 않고 잔액 계산에도 쓰지 않는다(읽기 전용).
- F09: 기획서 「개발 중에는 더미 데이터를 씁니다」. 샌드박스에 개인 이체결과 상품이 없다(CF-00003, 2026-11-10 실측).
- F14: 사용자 결정 2026-11-10 샌드박스 실호출. 샌드박스는 요청 조건과 상관없이 같은 견본 적금 계좌를 준다(실측).
- 회원과 연결된 다른 은행 계좌가 없어, 더미 예금주(김민준)와 같은 user_001 에게만 연결된 것으로 본다(사용자 결정 2026-11-10).
"""

import json
from datetime import datetime
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel

from app import codef
from app.deps import CurrentUserId
from app.errors import ApiError, not_found
from app.common.naming import KstDatetime, Money

router = APIRouter(tags=["external"])

# shortcut: 회원 ↔ 다른 은행 계좌 연결 표가 없어 여기 적는다 (기관 코드, 계좌번호). 마이데이터·CODEF 연결 기능을 만들면 표로 옮긴다
LINKED = {"user_001": {("0020", "1002440000000"),  # 우리은행 — 이체결과 더미의 출금 계좌
                       ("0004", "54780300000000")}}  # KB국민은행 — 샌드박스 견본 적금 계좌
TRANSFER_DUMMY = FilePath(__file__).resolve().parents[3] / "docs" / "dummy" / "codef_transfer_results.json"
STATUS = {"정상": "SUCCESS", "실패": "FAILED", "처리중": "PENDING"}  # CODEF 에는 취소가 없다 (15장)
CHANNEL = {"예약이체": "SCHEDULED", "자동이체": "AUTO"}  # 나머지(스마트뱅킹·인터넷뱅킹·오픈뱅킹)는 APP

OrderBy = Annotated[str, Query(alias="orderBy", pattern="^[01]$", description="0 최신순(기본) / 1 오래된 순")]


def _check(user_id: str, organization: str, account_no: str, start: str, end: str) -> None:
    if (organization, account_no) not in LINKED.get(user_id, set()):
        raise not_found("EXTERNAL_ACCOUNT_NOT_FOUND", "연결된 다른 은행 계좌가 아니에요.")
    if start > end:
        raise ApiError(400, "INVALID_PERIOD", "조회 시작일이 종료일보다 늦어요.")


class ExternalTransferOut(BaseModel):
    """15장 「CODEF 이체결과 필드와의 대응」으로 우리 이름에 맞춘 한 줄."""
    requested_at: KstDatetime
    status: str  # SUCCESS / FAILED / PENDING
    channel: str  # APP / SCHEDULED / AUTO
    trans_type: str  # CODEF 거래구분 그대로 (오픈뱅킹이면 화면이 「내 계좌로 옮기기」로 보여 준다)
    to_bank: str
    to_account_no: str
    to_holder_name: str
    amount: Money
    fee: Money
    my_display_name: str | None
    their_display_name: str | None


class ExternalTransfersOut(BaseModel):
    items: list[ExternalTransferOut]
    comm_start_date: str  # 실제로 조회된 기간 (10장 — 요청과 다르면 화면이 안내)
    comm_end_date: str


@router.get("/external-transfers", response_model=ExternalTransfersOut)
def list_external_transfers(
    user_id: CurrentUserId,
    organization: Annotated[str, Query(pattern=r"^\d{4}$", description="CODEF 기관 코드 (우리은행 0020)")],
    withdraw_account_no: Annotated[str, Query(alias="withdrawAccountNo")],
    start_date: Annotated[str, Query(alias="startDate", pattern=r"^\d{8}$")],
    end_date: Annotated[str, Query(alias="endDate", pattern=r"^\d{8}$")],
    order_by: OrderBy = "0",
):
    _check(user_id, organization, withdraw_account_no, start_date, end_date)
    dummy = json.loads(TRANSFER_DUMMY.read_text(encoding="utf-8"))["response"]["data"]
    rows = sorted((r for r in dummy if start_date <= r["resTransferDate"] <= end_date),
                  key=lambda r: r["resTransferDate"] + r["resTransferTime"], reverse=order_by == "0")
    items = [ExternalTransferOut(
        requested_at=datetime.strptime(r["resTransferDate"] + r["resTransferTime"], "%Y%m%d%H%M%S"),
        status=STATUS.get(r["resStatus"], r["resStatus"]), channel=CHANNEL.get(r["resTransType"], "APP"),
        trans_type=r["resTransType"], to_bank=r["resDepositBankName"], to_account_no=r["commDepositAccountNo"],
        to_holder_name=r["resAccountHolder"], amount=int(r["commTransferAmount"]), fee=int(r["resFee"] or 0),
        my_display_name=r["commWithdrawAccountDisplay"] or None, their_display_name=r["commDepositAccountDisplay"] or None,
    ) for r in rows]
    return ExternalTransfersOut(items=items, comm_start_date=start_date, comm_end_date=end_date)


@router.get("/external-deposit-accounts/{accountNo}/transactions")
def list_external_deposit_transactions(
    account_no: Annotated[str, Path(alias="accountNo")],
    user_id: CurrentUserId,
    organization: Annotated[str, Query(pattern=r"^\d{4}$", description="CODEF 기관 코드 (KB국민은행 0004)")],
    start_date: Annotated[str, Query(alias="startDate", pattern=r"^\d{8}$")],
    end_date: Annotated[str, Query(alias="endDate", pattern=r"^\d{8}$")],
    order_by: OrderBy = "0",
):
    """CODEF 예적금거래내역 응답의 data 를 이름 그대로 돌려준다(C-5 「CODEF 에서 온 칸은 CODEF 이름」, 15장 대응표는 화면이 쓴다)."""
    _check(user_id, organization, account_no, start_date, end_date)
    try:
        res = codef.request("/v1/kr/bank/p/installment-savings/transaction-list", {
            "organization": organization, "connectedId": codef.SANDBOX_CONNECTED_ID, "account": account_no,
            "startDate": start_date, "endDate": end_date, "orderBy": order_by, "inquiryType": "1"})  # 1 = 계좌 요약 포함
    except Exception:
        raise ApiError(503, "EXTERNAL_UNAVAILABLE", "다른 은행 내역을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
    code = res.get("result", {}).get("code")
    if code == "CF-13001":  # 종료일까지 조회 가능 기간을 벗어남 (10장)
        raise ApiError(422, "PERIOD_NOT_AVAILABLE", "이 은행은 해당 기간을 조회할 수 없어요.")
    if code != "CF-00000":
        raise ApiError(502, "EXTERNAL_ERROR", "다른 은행에서 내역을 주지 않았어요. 잠시 후 다시 시도해 주세요.")
    return res["data"]
