"""표를 새로 만들고 학습용 가짜 데이터를 넣는다.

    python -m app.seed

실행할 때마다 표를 지우고 다시 만든다(같은 결과가 나온다).
데이터는 ERD 1.md 칸에 맞춰 지어낸 값이다. 잔액·거래 원장·이체가 서로 맞도록 짰다.

acc_001 (user_001 입출금)  시작 1,500,000
  10-01 trf_0001 국민 홍길동에게      -50,000          → 1,450,000
  10-05 trf_0002 acc_003 이서준에게  -120,000          → 1,330,000  (acc_003 +120,000 → 420,000)
  10-10 trf_0003 신한 김민지에게      -30,000 수수료 500 → 1,299,500
  10-15 카드 대금                     -45,000          → 1,254,500
  10-25 trf_0004 예약: acc_002로    -200,000          → 1,054,500  (acc_002 +200,000 → 1,000,000)
  11-01 trf_0005 한도 초과로 실패 (원장 기록 없음)
"""

from datetime import date, datetime

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.db import engine
from app.models import (
    CREATE_ACCOUNT_BALANCE_VIEW,
    Account,
    AccountBalance,
    Base,
    ExternalAccount,
    FavoriteAccount,
    ScheduledTransfer,
    Transaction,
    Transfer,
    TransferLimit,
    User,
)

DOORIN = "두린은행"


def reset_schema(eng: Engine) -> None:
    with eng.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS account_balance_view"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        conn.execute(CREATE_ACCOUNT_BALANCE_VIEW)


def dt(s: str) -> datetime:
    """'2026-10-01 09:10' → 한국 시각 datetime"""
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def insert_seed(db: Session) -> None:
    users = [
        User(
            id="user_001", username="doorin", name="김두린", email="doorin@example.com",
            email_verified_at=dt("2026-01-05 10:02"), birth_date=date(1998, 3, 14), gender="F",
            payday=25, status="ACTIVE", created_at=dt("2026-01-05 10:00"),
        ),
        User(
            id="user_002", username="seojun", name="이서준", email="seojun@example.com",
            email_verified_at=dt("2026-02-10 14:31"), birth_date=date(1995, 7, 2), gender="M",
            payday=None, status="ACTIVE", created_at=dt("2026-02-10 14:30"),
        ),
    ]

    accounts = [
        Account(
            id="acc_001", user_id="user_001", resAccount="11000000001",
            resAccountDisplay="110-00-000001", resAccountName="두린 입출금통장",
            account_type="CHECKING", lifecycle_status="ACTIVE", resAccountNickName="생활비",
            is_favorite=True, resAccountStartDate="20260105",
        ),
        Account(
            id="acc_002", user_id="user_001", resAccount="11000000002",
            resAccountDisplay="110-00-000002", resAccountName="두린 자유저축통장",
            account_type="SAVINGS", lifecycle_status="ACTIVE", resAccountNickName=None,
            is_favorite=False, resAccountStartDate="20260301",
        ),
        Account(
            id="acc_003", user_id="user_002", resAccount="11000000003",
            resAccountDisplay="110-00-000003", resAccountName="두린 입출금통장",
            account_type="CHECKING", lifecycle_status="ACTIVE", resAccountNickName="월급통장",
            is_favorite=True, resAccountStartDate="20260210",
        ),
    ]

    balances = [
        AccountBalance(account_id="acc_001", currency="KRW", balance=1_054_500, updated_at=dt("2026-10-25 09:00")),
        AccountBalance(account_id="acc_002", currency="KRW", balance=1_000_000, updated_at=dt("2026-10-25 09:00")),
        AccountBalance(account_id="acc_003", currency="KRW", balance=420_000, updated_at=dt("2026-10-05 12:30")),
    ]

    limits = [
        TransferLimit(account_id="acc_001", per_transfer_limit=1_000_000, daily_limit=5_000_000, updated_at=dt("2026-01-05 10:00")),
        TransferLimit(account_id="acc_002", per_transfer_limit=1_000_000, daily_limit=5_000_000, updated_at=dt("2026-03-01 10:00")),
        TransferLimit(account_id="acc_003", per_transfer_limit=500_000, daily_limit=2_000_000, updated_at=dt("2026-02-10 14:30")),
    ]

    externals = [
        ExternalAccount(id="ext_001", bank="국민은행", account_no="12345678901234", holder_name="홍길동"),
        ExternalAccount(id="ext_002", bank="신한은행", account_no="110123456789", holder_name="김민지"),
        ExternalAccount(id="ext_003", bank="우리은행", account_no="1002345678901", holder_name="박지훈"),
    ]

    scheduled = [
        ScheduledTransfer(
            id="sch_001", user_id="user_001", from_account_id="acc_001", to_bank=DOORIN,
            to_account_no="11000000002", to_holder_name="김두린", amount=200_000, type="MONTHLY",
            execute_at=None, day_of_month=25, start_ym="202610", end_ym="202709",
            next_run_at=dt("2026-11-25 09:00"), status="ACTIVE", step_up_challenge_id=None,
            created_at=dt("2026-09-30 20:00"),
        ),
        ScheduledTransfer(
            id="sch_002", user_id="user_001", from_account_id="acc_001", to_bank="국민은행",
            to_account_no="12345678901234", to_holder_name="홍길동", amount=30_000, type="ONCE",
            execute_at=dt("2026-11-20 10:00"), day_of_month=None, start_ym=None, end_ym=None,
            next_run_at=dt("2026-11-20 10:00"), status="ACTIVE", step_up_challenge_id=None,
            created_at=dt("2026-11-02 18:00"),
        ),
    ]

    def transfer(id, from_acc, to_bank, to_no, to_name, amount, at, *, fee=0, status="SUCCESS",
                 failure_reason=None, channel="APP", scheduled_id=None, mine=None, theirs="김두린"):
        return Transfer(
            id=id, user_id="user_001", from_account_id=from_acc, to_bank=to_bank,
            to_account_no=to_no, to_holder_name=to_name, amount=amount, fee=fee,
            my_display_name=mine or to_name, their_display_name=theirs, status=status,
            failure_reason=failure_reason, channel=channel, scheduled_transfer_id=scheduled_id,
            step_up_challenge_id=None, idempotency_key=f"idem-{id}",
            requested_at=at, completed_at=at,
        )

    transfers = [
        transfer("trf_0001", "acc_001", "국민은행", "12345678901234", "홍길동", 50_000, dt("2026-10-01 09:10")),
        transfer("trf_0002", "acc_001", DOORIN, "11000000003", "이서준", 120_000, dt("2026-10-05 12:30")),
        transfer("trf_0003", "acc_001", "신한은행", "110123456789", "김민지", 30_000, dt("2026-10-10 18:45"), fee=500),
        transfer("trf_0004", "acc_001", DOORIN, "11000000002", "김두린", 200_000, dt("2026-10-25 09:00"),
                 channel="SCHEDULED", scheduled_id="sch_001", mine="저축"),
        transfer("trf_0005", "acc_001", "우리은행", "1002345678901", "박지훈", 5_000_000, dt("2026-11-01 11:00"),
                 status="FAILED", failure_reason="LIMIT_EXCEEDED"),
    ]

    txs = [
        Transaction(id="tx_0001", account_id="acc_001", type="TRANSFER_OUT", amount=50_000, fee=0,
                    balance_after=1_450_000, transfer_id="trf_0001", counterpart_bank="국민은행",
                    counterpart_account_no="12345678901234", display_name="홍길동",
                    created_at=dt("2026-10-01 09:10")),
        Transaction(id="tx_0002", account_id="acc_001", type="TRANSFER_OUT", amount=120_000, fee=0,
                    balance_after=1_330_000, transfer_id="trf_0002", counterpart_bank=DOORIN,
                    counterpart_account_no="11000000003", display_name="이서준",
                    created_at=dt("2026-10-05 12:30")),
        Transaction(id="tx_0003", account_id="acc_003", type="TRANSFER_IN", amount=120_000, fee=0,
                    balance_after=420_000, transfer_id="trf_0002", counterpart_bank=DOORIN,
                    counterpart_account_no="11000000001", display_name="김두린",
                    created_at=dt("2026-10-05 12:30")),
        Transaction(id="tx_0004", account_id="acc_001", type="TRANSFER_OUT", amount=30_000, fee=500,
                    balance_after=1_299_500, transfer_id="trf_0003", counterpart_bank="신한은행",
                    counterpart_account_no="110123456789", display_name="김민지",
                    created_at=dt("2026-10-10 18:45")),
        Transaction(id="tx_0005", account_id="acc_001", type="CARD_PAYMENT", amount=45_000, fee=0,
                    balance_after=1_254_500, transfer_id=None, counterpart_bank=None,
                    counterpart_account_no=None, display_name="두린카드 대금",
                    created_at=dt("2026-10-15 07:00")),
        Transaction(id="tx_0006", account_id="acc_001", type="TRANSFER_OUT", amount=200_000, fee=0,
                    balance_after=1_054_500, transfer_id="trf_0004", counterpart_bank=DOORIN,
                    counterpart_account_no="11000000002", display_name="저축",
                    created_at=dt("2026-10-25 09:00")),
        Transaction(id="tx_0007", account_id="acc_002", type="TRANSFER_IN", amount=200_000, fee=0,
                    balance_after=1_000_000, transfer_id="trf_0004", counterpart_bank=DOORIN,
                    counterpart_account_no="11000000001", display_name="김두린",
                    created_at=dt("2026-10-25 09:00")),
    ]

    favorites = [
        FavoriteAccount(id="fav_001", user_id="user_001", bank="국민은행", account_no="12345678901234",
                        holder_name="홍길동", nickname="길동이", sort_order=1),
        FavoriteAccount(id="fav_002", user_id="user_001", bank="신한은행", account_no="110123456789",
                        holder_name="김민지", nickname=None, sort_order=2),
        FavoriteAccount(id="fav_003", user_id="user_002", bank=DOORIN, account_no="11000000001",
                        holder_name="김두린", nickname="두린", sort_order=1),
    ]

    # FK 순서대로 넣는다: 부모(users, accounts) → 자식
    for group in (users, accounts, balances, limits, externals, scheduled, transfers, txs, favorites):
        db.add_all(group)
        db.flush()


def main(eng: Engine = engine) -> None:
    reset_schema(eng)
    with Session(eng) as db:
        insert_seed(db)
        db.commit()
    print("seed done:", eng.url.render_as_string(hide_password=True))


if __name__ == "__main__":
    main()
