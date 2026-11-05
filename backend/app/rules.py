"""기획서에서 정한 업무 규칙 값. 근거 절을 같이 적는다 — 기획서가 바뀌면 여기만 고친다."""

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

OUR_BANK = "두린은행"

# Part 5 3장 「거래 유형」: 내역 표시 + (입금) 인 type. 나머지는 − (출금)
INCOMING_TYPES = ("TRANSFER_IN", "POINT_CASHOUT", "SUBSCRIPTION_PAYOUT")

# Part 5 4장 「1회 500만 원, 1일 1,000만 원(예시)」 — transfer_limits 행이 없는 계좌(계좌 1 : 0..1)에 쓴다
DEFAULT_PER_TRANSFER_LIMIT = 5_000_000
DEFAULT_DAILY_LIMIT = 10_000_000

# Part 5 4장 「1일 한도에는 그날 실행된 예약 송금·자동이체도 포함」 — 처리중(PENDING)도 돈이 나갈 수 있으므로 센다
LIMIT_COUNTED_TRANSFER_STATUSES = ("SUCCESS", "PENDING")

# Part 5 11장 「받는 은행 목록」과 은행별 계좌번호 자릿수 (앞자리로 은행을 가리지 않는다)
BANK_ACCOUNT_DIGITS = {
    OUR_BANK: 14,
    "우리은행": 13,
    "KB국민은행": 14,
    "신한은행": 12,
    "하나은행": 14,
    "NH농협은행": 13,
    "IBK기업은행": 14,
    "카카오뱅크": 13,
    "토스뱅크": 12,
    "케이뱅크": 12,
    "새마을금고": 13,
}


def now_kst() -> datetime:
    """DB 에 저장하는 모양(시간대 없는 한국 시각)의 지금."""
    return datetime.now(KST).replace(tzinfo=None)
