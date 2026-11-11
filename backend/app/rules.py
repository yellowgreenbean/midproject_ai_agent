"""기획서에서 정한 업무 규칙 값. 근거 절을 같이 적는다 — 기획서가 바뀌면 여기만 고친다."""

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

OUR_BANK = "두린은행"

# Part 2 ACCT-F01 계좌 개설 — 유형별 기본 계좌 이름(resAccountName, 더미 accounts.json 과 같음)과 계좌번호 모양
ACCOUNT_PRODUCT_NAMES = {"CHECKING": "입출금통장", "SAVINGS": "저축예금"}
ACCOUNT_NUMBER_PREFIX = "110"  # 더미 계좌번호가 모두 110 으로 시작하는 14자리 (BANK_ACCOUNT_DIGITS[OUR_BANK])
ACCOUNT_OPEN_CONSENT = "required_terms"  # 예금거래기본약관 · 입출금이 자유로운 예금 약관 (data/rag/terms/) 묶음 동의 (Part 2 9.1)

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


# Part 5 11장 「테스트용으로 특정 계좌번호는 PENDING 후 SUCCESS, 또는 FAILED」 — 시드 external_accounts 의 예금주 이름으로 고른다
EXTERNAL_PENDING_HOLDER = "임처리"  # 처리중(PENDING) → settle_pending_transfers(app/jobs.py)가 10분 뒤 확정
EXTERNAL_FAIL_HOLDER = "오실패"  # 받는 은행이 거절 → FAILED
PENDING_SETTLE_AFTER = timedelta(minutes=10)  # Part 5 9장 「10분이 지나도 PENDING 이면 배치가 결과를 확정」
TRANSFER_NAME_MAX = 10  # 통장 표시 이름 최대 글자 (Part 5 7장, 화면 TransferPage NAME_MAX 와 같음)
TRANSFER_FAILURE_MESSAGES = {  # Part 5 9장 실패 사유 코드 → 사용자 안내
    "INSUFFICIENT_BALANCE": "잔액이 부족해 보내지 못했어요.",
    "LIMIT_EXCEEDED": "이체 한도를 초과했어요.",
    "INVALID_ACCOUNT": "받는 계좌를 찾을 수 없어요.",
    "ACCOUNT_NOT_ACTIVE": "거래할 수 없는 계좌예요.",
    "SYSTEM_ERROR": "이체가 완료되지 않았어요. 잠시 후 다시 시도해 주세요.",
}

# Part 5 4장 「금액 오입력 방지」 재확인 화면 경고 — 기획서 예시 값 그대로(사용자 결정 2026-11-10)
WARN_FIRST_LARGE = 1_000_000  # 처음 보내는 받는 분에게 이 금액 이상
WARN_USUAL_MULTIPLE = 10  # 같은 받는 분에게 보낸 이전 금액 평균의 이 배수 이상
WARN_RECENT_SAME = timedelta(minutes=10)  # 같은 받는 분·같은 금액을 이 시간 안에 또

# Part 5 6장 간편 송금 목록 크기
RECENT_TARGETS_MAX = 10
FAVORITE_ACCOUNTS_MAX = 20

# Part 5 8장 예약 송금·자동이체
SCHEDULE_STEP_MINUTES = 10  # 실행 시각은 10분 단위
SCHEDULE_MIN_AHEAD = timedelta(minutes=10)  # 지금부터 10분 이후 ~
SCHEDULE_MAX_AHEAD = timedelta(days=365)  # ~ 1년 이내. 변경·취소도 실행 10분 전까지
AUTO_TRANSFER_HOUR = 6  # 자동이체는 지정일 06:00 (사용자 결정 2026-11-10: 재시도·연속 실패 정지 없음)
LAST_DAY_OF_MONTH = 99  # day_of_month 99 = 말일

# Part 5 4장 TRX-F13 한도 변경 상한 — 모의 값(사용자 결정 2026-11-10). 올릴 때만 본인 확인(TRANSFER), 1만 원 단위(화면 안내)
MAX_PER_TRANSFER_LIMIT = 100_000_000
MAX_DAILY_LIMIT = 500_000_000


# --- 로그인 세션 (Part 1 AUTH-F05 「세션 만료(유휴/최대)」, 12장 「세션」) ---------------------------
# 사용자 결정 2026-11-05: 유휴 10분, 최대 12시간 (기획서 12장에는 아직 기록 안 됨)
SESSION_COOKIE = "sid"
SESSION_IDLE = timedelta(minutes=10)  # 마지막 요청(last_seen_at)에서 이만큼 지나면 만료
SESSION_MAX = timedelta(hours=12)  # 로그인(created_at)에서 이만큼 지나면 만료 → expires_at. 써도 늘어나지 않음
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)  # last_seen_at 은 요청마다가 아니라 1분에 한 번만 갱신

# --- 로그인 실패 보호 (AUTH-F05 [설계 권고] 「속도 제한과 점진적 보호」, 「과도한 영구 잠금 금지」) --------
# 로그인 실패는 DB(local_credentials.failed_attempts)에 세지 않는다 — 6.3 표: 그 칸은 본인 확인 실패만 센다.
# 대신 서버 메모리에서 같은 아이디가 연속으로 틀리면 잠깐 기다리게 한다(서버를 다시 켜면 초기화).
LOGIN_THROTTLE_FAILURES = 5
LOGIN_THROTTLE_WAIT = timedelta(minutes=1)


# --- 회원가입 입력 규칙 (Part 1 AUTH-F01·F02) — frontend/src/signupRules.ts 와 같은 규칙. 바꿀 때 둘 다 고친다 ---
USERNAME_RE = r"^[a-z][a-z0-9_]{3,19}$"  # 영문 소문자로 시작, 소문자·숫자·밑줄 4~20자
PASSWORD_MIN, PASSWORD_MAX = 8, 64  # 영문과 숫자를 모두 넣고, 아이디가 들어가면 안 됨
EMAIL_RE = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
NAME_RE = r"^[가-힣a-zA-Z ]{2,20}$"

# --- 이메일 인증 (AUTH-F03 「예시 정책: 5분 만료 / 60초 재발송 대기 / 연속 오류 제한」) ----------------
# 사용자 결정 2026-11-09: 기획서 예시값 + 하루 10번 발송 + 인증 후 30분 안에 가입. 1 이메일 = 1 계정(탈퇴 회원 제외)
EMAIL_CODE_TTL = timedelta(minutes=5)
EMAIL_RESEND_WAIT = timedelta(seconds=60)
EMAIL_CODE_MAX_ATTEMPTS = 5  # 5번 틀리면 그 번호는 못 쓰고 새로 받아야 함
EMAIL_DAILY_SENDS = 10  # 같은 이메일·용도로 24시간 안에 보낼 수 있는 횟수
EMAIL_VERIFIED_TTL = timedelta(minutes=30)  # 인증을 마친 뒤 이 시간 안에 가입해야 함
EMAIL_PURPOSES = ("SIGNUP", "EMAIL_CHANGE", "USERNAME_RECOVERY", "PASSWORD_RESET")  # 쓰임마다 따로 센다


# --- 본인 확인 (Part 1 7장 POST /auth/step-up, 6.3 local_credentials) — 사용자 결정 2026-11-09 -----------------
STEP_UP_TTL = timedelta(minutes=5)  # 받은 본인 확인 번호를 쓸 수 있는 시간 (한 번만, 그 action 에만, 그 세션에서만)
STEP_UP_MAX_FAILURES = 5  # 비밀번호를 연속으로 이만큼 틀리면 영구 잠금(STEP_UP_LOCKED) — 시드 user_027 과 같은 규칙

# --- 간편 비밀번호 PIN (AUTH-F11~F13) — 사용자 결정 2026-11-10. 금지 규칙은 frontend/src/pinRules.ts 와 같다 ------
# PIN 실패는 pin_credentials 에 센다(비밀번호 본인 확인의 local_credentials 와 따로). 5번 틀리면 10분 잠금 —
# 잠금 시간이 지나면 다시 5번, 그 전에 풀려면 로그인 비밀번호로 「다시 정하기」(PIN_RESET).
PIN_LENGTH = 6
PIN_MAX_FAILURES = 5
PIN_LOCK = timedelta(minutes=10)


def pin_error(pin: str, birth_date: date | None) -> str | None:
    """새 PIN 이 쓸 수 있는 번호인지. 문제없으면 None. 지금 PIN 과 같은지는 해시를 봐야 해서 부르는 쪽이 따로 본다."""
    if len(pin) != PIN_LENGTH or not pin.isascii() or not pin.isdigit():
        return f"숫자 {PIN_LENGTH}자리로 정해 주세요."
    if len(set(pin)) == 1:
        return "같은 숫자만 쓸 수는 없어요."
    steps = {int(b) - int(a) for a, b in zip(pin, pin[1:])}
    if steps in ({1}, {-1}):
        return "이어지는 숫자(123456 같은)는 쓸 수 없어요."
    if birth_date is not None and pin == birth_date.strftime("%y%m%d"):
        return "생년월일은 쓸 수 없어요."
    return None


# --- 아이디 찾기 · 비밀번호 재설정 · 비밀번호 변경 (AUTH-F06 · F08) — 사용자 결정 2026-11-10 ------------------
PASSWORD_RESET_TTL = timedelta(minutes=5)  # 재설정 ①이 준 재설정 토큰을 ②에서 쓸 수 있는 시간 (한 번만, 새로 받으면 이전 것은 무효)
RECOVERABLE_STATUSES = ("ACTIVE", "RESTRICTED", "PENDING_VERIFICATION")  # 탈퇴(WITHDRAWN)는 찾지도 바꾸지도 않는다
USERNAME_VISIBLE = 3  # 아이디 찾기 결과에서 보여 줄 앞 글자 수 — 나머지는 글자 수만큼 *

# --- 회원 탈퇴 (Part 1 AUTH-F09) — 사용자 결정 2026-11-09 ------------------------------------------------
# ② 「삭제될 데이터」 안내문 버전. 화면(frontend/src/pages/WithdrawPage.tsx 의 DATA_GROUPS)을 바꾸면 같이 올린다 → 예전 확인은 무효
WITHDRAWAL_DATA_REVIEW_VERSION = "2026-11-09"
WITHDRAWN_NAME = "탈퇴회원"  # 탈퇴 1개월 뒤 가명 처리 때 이름 (아이디는 다른 사람이 못 쓰게 그대로 둔다)


# --- 카드 포인트 · 연회비 (Part 4 1-1-7 · 1-1-8, CARD-F12·F13) — 사용자 결정 2026-11-11 --------------------------
POINT_EXPIRY_ALERT_DAYS = 30  # 포인트 소멸 며칠 전에 알릴지 (한 번)
ANNUAL_FEE_ALERT_DAYS = 30  # 연회비 청구 며칠 전에 알릴지 (한 번, 기획서 「D-30」)


def next_year(d: date) -> date:
    """1년 뒤 같은 날 (2월 29일은 2월 28일) — 연회비 청구일은 발급일 기준 매년 (1-1-8)."""
    return d.replace(year=d.year + 1, day=28) if (d.month, d.day) == (2, 29) else d.replace(year=d.year + 1)


def now_kst() -> datetime:
    """DB 에 저장하는 모양(시간대 없는 한국 시각)의 지금."""
    return datetime.now(KST).replace(tzinfo=None)
