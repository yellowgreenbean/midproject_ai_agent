# 더미에 없는 기능을 시험하기 위한 시드 SQL 만들기 (읽기만 함, DB 에 직접 넣지 않음)
# docs/세션_작업_정리_2026-11-05.md 「seed가 필요한 상황」 2번(이체·예약·자주 쓰는 계좌·한도·타행·포인트·알림)과
# 3번(로그인: 비밀번호·PIN 해시). 목 데이터는 load_dummy.py(더미) → 이 파일(시나리오 시드) 순서 하나뿐이다.
#
# 순서: 더미를 먼저 넣고(load_dummy.py) 이 시드를 넣는다. 시드는 더미의 회원·계좌·카드를 가리킨다.
#   python3 scripts/seed_scenarios.py > seed_scenarios.sql            # 처음 넣을 때
#   python3 scripts/seed_scenarios.py --reset > seed_scenarios.sql    # 이 시드 행을 지우고 다시 넣을 때(시각 새로 고침)
#   docker exec -i midproject-postgres psql -U app -d midproject -v ON_ERROR_STOP=1 < seed_scenarios.sql
# 필요: pip install argon2-cffi (backend/requirements.txt)
#
# 원칙
#   - 시험할 상황마다 최소한의 행만 만든다. 어떤 행이 무엇을 시험하는지는 SCENARIOS(출력 SQL 주석에도 나옴)에 적었다.
#   - 원장(transactions)·잔액(account_balances)을 바꾸는 행은 만들지 않는다 → 성공한 이체(SUCCESS)·포인트 현금화는 없음.
#     성공 기록은 원장 출금·입금이 같이 있어야 해서(기획서 Part 5 9장) 넣으면 더미 잔액과 어긋난다. 앱에서 이체해 만든다.
#   - 예약 시각·잠금 시각은 SQL 을 만드는 시각 기준이다. 만든 뒤 바로 넣는다(오래 두면 "곧 실행" 같은 상황이 지나간다).
#   - 시험용 비밀번호·PIN 은 환경변수 SEED_PASSWORD·SEED_PIN(없으면 backend/.env 의 값)에서 읽고,
#     SQL 에는 Argon2id 해시만 남는다(기획서 Part 1 「안전한 비밀번호 해시(예: Argon2id)」). 실제 비밀번호를 쓰지 말 것.
#   - 본인 확인(step_up_challenges)은 로그인 세션이 있어야 해서 만들지 않는다 → 예약·이체의 step_up_challenge_id 는 NULL.
import argparse, calendar, collections, datetime, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive_card_parents as parents  # noqa: E402
import load_dummy  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KST = datetime.timezone(datetime.timedelta(hours=9))
OUR_BANK = "두린은행"

# 기획서 Part 5 4장: 1회 500만 원, 1일 1,000만 원(예시)
DEFAULT_LIMIT = (5_000_000, 10_000_000)

# 기획서 Part 5 11장 「받는 은행 목록」·자릿수·앞자리. 두린은행(14자리, 110)과 겹치지 않는다
EXTERNAL = [  # (은행, 자릿수, 앞자리, 예금주)
    ("신한은행", 12, "110", "김가람"), ("토스뱅크", 12, "1000", "이나래"), ("케이뱅크", 12, "1001", "박다솜"),
    ("우리은행", 13, "1002", "(주)새봄상사"), ("카카오뱅크", 13, "3333", "최라온"), ("NH농협은행", 13, "302", "정마루"),
    ("새마을금고", 13, "9002", "강바다"), ("KB국민은행", 14, "940", "조사랑"), ("하나은행", 14, "248", "윤아름"),
    ("IBK기업은행", 14, "010", "장하람"),
]
# 11장 「특정 계좌번호는 PENDING 후 SUCCESS, 또는 FAILED」 — 앱이 이 계좌번호를 보고 결과를 정한다
EXTERNAL_TEST = [("신한은행", 12, "110", "임처리", "PENDING 후 SUCCESS"), ("KB국민은행", 14, "940", "오실패", "FAILED")]

SCENARIOS = """
가입 약관 (AUTH-F10)
  - 공통 약관 4개: trm_001 서비스 이용약관 · trm_002 전자금융거래 이용약관 · trm_003 개인정보 수집·이용(이상 필수)
    · trm_004 마케팅 정보 수신(선택). 본문 파일: trm_001 토스 원문(scripts/crawl_toss_terms.py) · trm_002 우리은행 PDF,
    trm_003·004 의 content_url 은 아직 빈 자리
로그인 (3번)
  - 탈퇴(user_029)를 뺀 29명: auth_identities(LOCAL, username) + local_credentials. 탈퇴 회원은 해시를 지움(Part 1 즉시 삭제)
  - local_credentials.failed_attempts 는 본인 확인(step-up) 비밀번호 실패만 센다(기획서 6.3) — 로그인 실패는 세지 않음
  - user_026 본인 확인 실패 4회(한 번 더 틀리면 잠김) · user_027 본인 확인 잠김(실패 5회 = 영구 잠금, 영업점 방문 안내.
    시간이 지나도 풀리지 않으므로 locked_until 은 비움). 둘 다 로그인·조회는 되고 중요 작업만 STEP_UP_LOCKED
  - 정상 계좌가 있는 ACTIVE 회원: pin_credentials. user_019 PIN 잠김(locked_until = 지금 + 30분 — PIN 잠금 규칙은 3차에 정함)
  - 상태별 로그인: user_024 RESTRICTED · user_028 PENDING_VERIFICATION · user_029 WITHDRAWN(로그인 수단 없음)
이체 한도
  - 해지 안 된 계좌 모두 1회 500만 · 1일 1,000만. acc_007(user_002)만 1회 30만 · 1일 50만 → 한도 초과 시험
타행·자주 쓰는 계좌
  - external_accounts: 10개 은행에 1개씩 + 결과 시험용 2개(신한 PENDING→SUCCESS, KB국민 FAILED)
    + 탈퇴 안 한 회원 29명마다 본인 명의 계좌 1개(ext_user_001 …, 예금주 = 회원 이름) — 탈퇴 전 남은 돈을 옮길 곳
  - user_001: 이서연(acc_007) · 정지 계좌 정도윤(acc_011, ACCOUNT_NOT_ACTIVE 시험) · 신한 김가람(집주인)
  - user_002: 김민준(acc_001)
예약 송금·자동이체 (user_001, 출금 acc_001)
  - sch_001 내일 09:00 예약(변경·취소 가능) · sch_002 10분 안에 실행(변경 막힘) · sch_003 잔액보다 큰 금액(실행 때 잔액 부족)
  - sch_004 취소됨 · sch_005 어제 실행 실패(trf_0003 과 실패 알림)
  - sch_006 자동이체 월세 매월 27일(ACTIVE) · sch_007 자동이체 용돈 말일(PAUSED)
이체 실패 기록 (SUCCESS 는 만들지 않음)
  - trf_0001 잔액 부족 · trf_0002 1회 한도 초과(acc_007) · trf_0003 예약 실행 실패
카드 포인트
  - 카드가 있는 15명: 한빛포인트 = 취소 뺀 승인 합계의 0.5%. user_001 은 이번 달 말 소멸 예정 1,200점
알림
  - user_001: 거래 알림(읽음) · 예약 실패(안 읽음) · 결제 예정(card_002) · 포인트 소멸 예정
  - 결제 계좌 잔액 부족(LOW_BALANCE)은 만들지 않음: 더미에 결제 예정액보다 잔액이 적은 계좌가 없어 알림이 데이터와 어긋남
  - user_003: 결제 예정(읽음)
  - notification_preferences: 해지 안 된 계좌 모두 기본값. acc_001 은 1만 원 미만 알림 끔, acc_002 는 알림 끔
""".strip()


def read_env():
    """backend/.env 의 KEY=VALUE (서버 app/config.py 와 같은 파일). 다른 칸(API 키 등)은 쓰지 않는다"""
    vals = {}
    path = os.path.join(HERE, "..", "backend", ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                vals[k] = v.strip().strip("\"'")
    return vals


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def last_day(y, m):
    return calendar.monthrange(y, m)[1]


def next_monthly(now, day):
    """매월 지정일(99 = 말일) 06:00 중 now 이후 첫 실행 시각 (기획서 Part 5 8장)"""
    y, m = now.year, now.month
    for _ in range(2):
        d = last_day(y, m) if day == 99 else day
        run = datetime.datetime(y, m, d, 6, 0)
        if run > now:
            return run
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    raise AssertionError


def build(root, now, password, pin):
    from argon2 import PasswordHasher
    ph = PasswordHasher()  # Argon2id, 매번 새 솔트
    d = load_dummy.build(root)
    users = {u["id"]: u for u in d["users"]}
    accts = {a["id"]: a for a in d["accounts"]}
    bal = {b["account_id"]: b["balance"] for b in d["account_balances"]}
    cards = {c["id"]: c for c in d["user_cards"]}
    bills = {b["id"]: b for b in d["card_bills"]}
    errs = []

    def need_acct(aid, user_id, status="ACTIVE"):
        a = accts.get(aid)
        if not a or a["user_id"] != user_id or a["lifecycle_status"] != status or a["account_type"] != "CHECKING":
            errs.append(f"시나리오가 가정한 계좌가 더미와 다름: {aid} ({user_id}, {status} CHECKING)")
        return a or {}

    def need_user(uid, status="ACTIVE"):
        if users.get(uid, {}).get("status") != status:
            errs.append(f"시나리오가 가정한 회원 상태가 더미와 다름: {uid} {status}")
        return users.get(uid, {})

    t = {}
    lock_until = fmt(now + datetime.timedelta(minutes=30))

    # 가입 약관 (AUTH-F10, 사용자 결정 2026-11-09: 토스식 4개). 카드 상품 약관이 아니라 card_product_id 는 NULL
    t["terms"] = [
        {"id": tid, "version": "1.0", "title": title, "required": req, "content_url": url,
         "effective_at": "2026-11-01 00:00:00", "card_product_id": None}
        for tid, title, req, url in [
            ("trm_001", "서비스 이용약관", True, "data/rag/terms/service_terms.md"),
            ("trm_002", "전자금융거래 이용약관", True, "data/rag/terms/electronic_financial_transactions_terms.pdf"),
            ("trm_003", "개인정보 수집·이용 동의", True, "docs/terms/privacy_consent.md"),
            ("trm_004", "마케팅 정보 수신 동의", False, "docs/terms/marketing_consent.md"),
        ]
    ]

    # 로그인 (3번)
    login_users = [u for u in d["users"] if u["status"] != "WITHDRAWN"]
    need_user("user_024", "RESTRICTED"), need_user("user_028", "PENDING_VERIFICATION"), need_user("user_029", "WITHDRAWN")
    need_user("user_026"), need_user("user_027")
    pw_hash = {u["id"]: ph.hash(password) for u in login_users}
    t["auth_identities"] = [
        {"id": f"aid_{u['id'][5:]}", "user_id": u["id"], "provider": "LOCAL", "provider_subject": u["username"],
         "linked_at": u["created_at"]} for u in login_users
    ]
    # 본인 확인 실패 횟수: 5회면 영구 잠금이라 locked_until(시간 잠금용)은 쓰지 않는다
    t["local_credentials"] = [
        {"user_id": u["id"], "password_hash": pw_hash[u["id"]], "password_updated_at": u["created_at"],
         "failed_attempts": {"user_026": 4, "user_027": 5}.get(u["id"], 0),
         "locked_until": None} for u in login_users
    ]
    pin_users = sorted({a["user_id"] for a in d["accounts"] if a["lifecycle_status"] == "ACTIVE"
                        and a["account_type"] == "CHECKING" and users[a["user_id"]]["status"] == "ACTIVE"})
    if "user_019" not in pin_users:
        errs.append("user_019 에 정상 계좌가 없어 PIN 잠금 시나리오를 만들 수 없음")
    t["pin_credentials"] = [
        {"user_id": uid, "pin_hash": ph.hash(pin), "enabled_at": users[uid]["created_at"],
         "failed_attempts": 5 if uid == "user_019" else 0, "locked_until": lock_until if uid == "user_019" else None}
        for uid in pin_users
    ]

    # 이체 한도
    acc_007 = need_acct("acc_007", "user_002")
    t["transfer_limits"] = [
        {"account_id": a["id"],
         "per_transfer_limit": 300_000 if a["id"] == "acc_007" else DEFAULT_LIMIT[0],
         "daily_limit": 500_000 if a["id"] == "acc_007" else DEFAULT_LIMIT[1], "updated_at": fmt(now)}
        for a in d["accounts"] if a["lifecycle_status"] != "CLOSED"
    ]

    # 타행 계좌
    ext = []
    for i, (bank, digits, prefix, holder) in enumerate(EXTERNAL, 1):
        ext.append({"id": f"ext_{i:03d}", "bank": bank, "account_no": prefix + str(i).zfill(digits - len(prefix)),
                    "holder_name": holder})
    for j, (bank, digits, prefix, holder, _) in enumerate(EXTERNAL_TEST, len(EXTERNAL) + 1):
        ext.append({"id": f"ext_{j:03d}", "bank": bank, "account_no": prefix + "9" * (digits - len(prefix) - 3) + str(j).zfill(3),
                    "holder_name": holder})
    # 회원마다 본인 명의 타행 계좌 1개 (사용자 결정 2026-11-09) — 탈퇴 ① 「남은 돈을 본인 명의 계좌로」의 받을 곳.
    # 은행은 EXTERNAL 순서대로 돌아가며, 번호는 앞자리 + 7…7 + 회원 번호 3자리(위 두 줄과 겹치지 않음)
    for n, u in enumerate(login_users):
        bank, digits, prefix, _ = EXTERNAL[n % len(EXTERNAL)]
        ext.append({"id": f"ext_{u['id']}", "bank": bank,
                    "account_no": prefix + "7" * (digits - len(prefix) - 3) + u["id"][-3:], "holder_name": u["name"]})
    t["external_accounts"] = ext
    landlord = ext[0]  # 신한은행 김가람

    # 자주 쓰는 계좌
    u1, u2 = need_user("user_001"), need_user("user_002")
    acc_001 = need_acct("acc_001", "user_001")
    acc_011 = need_acct("acc_011", "user_005", "SUSPENDED")
    name_of = lambda a: users[a["user_id"]]["name"]
    t["favorite_accounts"] = [
        {"id": "fav_001", "user_id": "user_001", "bank": OUR_BANK, "account_no": acc_007['"resAccount"'],
         "holder_name": name_of(acc_007), "nickname": "서연", "sort_order": 1},
        {"id": "fav_002", "user_id": "user_001", "bank": landlord["bank"], "account_no": landlord["account_no"],
         "holder_name": landlord["holder_name"], "nickname": "집주인", "sort_order": 2},
        {"id": "fav_003", "user_id": "user_001", "bank": OUR_BANK, "account_no": acc_011['"resAccount"'],
         "holder_name": name_of(acc_011), "nickname": "도윤(정지 계좌)", "sort_order": 3},
        {"id": "fav_004", "user_id": "user_002", "bank": OUR_BANK, "account_no": acc_001['"resAccount"'],
         "holder_name": name_of(acc_001), "nickname": None, "sort_order": 1},
    ]

    # 예약 송금·자동이체 (user_001 → 이서연 / 김가람)
    tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0)
    yesterday = (now - datetime.timedelta(days=1)).replace(hour=0, minute=0)
    soon = now + datetime.timedelta(minutes=10 - now.minute % 10)  # 다음 10분 단위 = 10분 안
    to_seoyeon = {"to_bank": OUR_BANK, "to_account_no": acc_007['"resAccount"'], "to_holder_name": name_of(acc_007)}
    to_landlord = {"to_bank": landlord["bank"], "to_account_no": landlord["account_no"], "to_holder_name": landlord["holder_name"]}
    base = {"user_id": "user_001", "from_account_id": "acc_001", "step_up_challenge_id": None}

    def sch(i, to, amount, my, their, typ, status, execute_at=None, day=None, start_ym=None, next_run=None, created=None):
        return {"id": f"sch_{i:03d}", **base, **to, "amount": amount, "my_display_name": my, "their_display_name": their,
                "type": typ, "execute_at": fmt(execute_at) if execute_at else None, "day_of_month": day,
                "start_ym": start_ym, "end_ym": None, "next_run_at": fmt(next_run) if next_run else None,
                "status": status, "created_at": fmt(created or now - datetime.timedelta(days=2)),
                "updated_at": fmt(created or now - datetime.timedelta(days=2))}

    ym = now.strftime("%Y%m")
    over = bal["acc_001"] + 750_000  # 잔액보다 큰 금액
    failed_at = yesterday.replace(hour=9)
    t["scheduled_transfers"] = [
        sch(1, to_seoyeon, 50_000, "이서연 생일", "생일축하", "ONCE", "SCHEDULED",
            execute_at=tomorrow.replace(hour=9), next_run=tomorrow.replace(hour=9)),
        sch(2, to_seoyeon, 30_000, "이서연 밥값", None, "ONCE", "SCHEDULED", execute_at=soon, next_run=soon),
        sch(3, to_seoyeon, over, "이서연 여행비", None, "ONCE", "SCHEDULED",
            execute_at=tomorrow.replace(hour=10), next_run=tomorrow.replace(hour=10)),
        sch(4, to_seoyeon, 20_000, "이서연 커피", None, "ONCE", "CANCELED", execute_at=tomorrow.replace(hour=12)),
        sch(5, to_seoyeon, over, "이서연 여행비", None, "ONCE", "FAILED", execute_at=failed_at),
        sch(6, to_landlord, 600_000, "월세", f"{now.month}월월세", "MONTHLY", "ACTIVE",
            day=27, start_ym=ym, next_run=next_monthly(now, 27)),
        sch(7, to_seoyeon, 100_000, "이서연 용돈", "용돈", "MONTHLY", "PAUSED", day=99, start_ym=ym),
    ]

    # 이체 실패 기록 (원장 없음)
    def trf(i, user_id, from_id, to, amount, my, their, reason, channel, at, sch_id=None):
        return {"id": f"trf_{i:04d}", "user_id": user_id, "from_account_id": from_id, **to, "amount": amount, "fee": 0,
                "my_display_name": my, "their_display_name": their, "status": "FAILED", "failure_reason": reason,
                "channel": channel, "scheduled_transfer_id": sch_id, "step_up_challenge_id": None,
                "idempotency_key": f"seed-trf_{i:04d}", "requested_at": fmt(at),
                "completed_at": fmt(at + datetime.timedelta(seconds=2))}

    to_minjun = {"to_bank": OUR_BANK, "to_account_no": acc_001['"resAccount"'], "to_holder_name": name_of(acc_001)}
    t["transfers"] = [
        trf(1, "user_001", "acc_001", to_seoyeon, bal["acc_001"] + 2_250_000, name_of(acc_007), name_of(acc_001),
            "INSUFFICIENT_BALANCE", "APP", yesterday.replace(hour=14)),
        trf(2, "user_002", "acc_007", to_minjun, 400_000, name_of(acc_001), name_of(acc_007),
            "LIMIT_EXCEEDED", "APP", yesterday.replace(hour=15)),
        trf(3, "user_001", "acc_001", to_seoyeon, over, "이서연 여행비", name_of(acc_001),
            "INSUFFICIENT_BALANCE", "SCHEDULED", failed_at, sch_id="sch_005"),
    ]
    if bal["acc_007"] < 400_000:
        errs.append("trf_0002 는 잔액이 아니라 한도 때문에 실패해야 함 — acc_007 잔액 확인")

    # 카드 포인트: 취소 뺀 승인 합계의 0.5%
    spent = collections.defaultdict(int)
    for x in d["card_transactions"]:
        spent[cards[x["user_card_id"]]["user_id"]] += x["amount"] - x["canceled_amount"]
    month_end = datetime.date(now.year, now.month, last_day(now.year, now.month))
    t["card_points"] = [
        {"id": f"pt_{uid[5:]}", "user_id": uid, "card_company_id": "cc_001", "point_name": "한빛포인트",
         "balance": spent[uid] * 5 // 1000,
         "expiring_amount": 1_200 if uid == "user_001" else 0,
         "expiring_date": month_end.isoformat() if uid == "user_001" else None, "synced_at": fmt(now)}
        for uid in sorted({c["user_id"] for c in cards.values()})
    ]
    if spent["user_001"] * 5 // 1000 < 1_200:
        errs.append("user_001 포인트가 소멸 예정 1,200점보다 적음")

    # 알림
    won = lambda n: f"{n:,}원"
    bill_02 = bills.get("bill_card_002_202611")
    bill_03 = bills.get("bill_card_003_202611")
    bill_05 = next((b for b in bills.values() if b["billing_ym"] == "202611"
                    and cards[b["user_card_id"]]["user_id"] == "user_003"), None)  # user_003 신용카드의 11월 청구서
    if not (bill_02 and bill_03 and bill_05):
        errs.append("알림 시나리오가 가정한 11월 청구서가 더미에 없음")
        bill_02 = bill_03 = bill_05 = {"total_amount": 0, "payment_date": "2026-11-14", "user_card_id": "", "id": ""}
    tx9 = next((x for x in d["transactions"] if x["id"] == "tx_0009"), None)
    if not tx9 or tx9["account_id"] != "acc_001":
        errs.append("tx_0009 가 acc_001 의 거래가 아님")
        tx9 = {"amount": 0, "display_name": "", "balance_after": 0, "created_at": fmt(now)}
    due = datetime.date.fromisoformat(bill_02["payment_date"])
    due_txt = f"{due.month}월 {due.day}일"
    product_name = {p["id"]: p["name"] for p in d["card_products"]}
    card_label = lambda cid: f"{product_name[cards[cid]['card_product_id']]}({cards[cid]['last4']})" if cid in cards else ""
    notes = [
        {"user_id": "user_001", "account_id": "acc_001", "user_card_id": None, "event_id": "tx_0009", "type": "TRANSACTION",
         "title": f"출금 {won(tx9['amount'])}", "body": f"{tx9['display_name']} · 잔액 {won(tx9['balance_after'])}",
         "read_at": tx9["created_at"], "created_at": tx9["created_at"]},
        {"user_id": "user_001", "account_id": "acc_001", "user_card_id": None, "event_id": "trf_0003", "type": "TRANSACTION",
         "title": "예약 송금을 보내지 못했어요",
         "body": f"잔액이 부족해 {name_of(acc_007)}님께 {won(over)}을 보내지 못했어요. 다시 보내기를 눌러 주세요.",
         "read_at": None, "created_at": fmt(failed_at + datetime.timedelta(seconds=5))},
        {"user_id": "user_001", "account_id": None, "user_card_id": "card_002", "event_id": bill_02["id"], "type": "PAYMENT_DUE",
         "title": f"{due_txt} 카드 대금 결제 예정", "body": f"{card_label('card_002')} {won(bill_02['total_amount'])}",
         "read_at": None, "created_at": fmt(now.replace(hour=8, minute=0))},
    ]
    notes += [
        {"user_id": "user_001", "account_id": None, "user_card_id": None, "event_id": f"pt_001_{month_end:%Y%m}",
         "type": "POINT_EXPIRING", "title": "한빛포인트 1,200점이 곧 사라져요",
         "body": f"{month_end.month}월 {month_end.day}일에 소멸돼요. 현금으로 바꿔 보세요.",
         "read_at": None, "created_at": fmt(now.replace(hour=8, minute=0))},
        {"user_id": "user_003", "account_id": None, "user_card_id": bill_05["user_card_id"] or None, "event_id": bill_05["id"], "type": "PAYMENT_DUE",
         "title": f"{due_txt} 카드 대금 결제 예정", "body": f"{card_label(bill_05['user_card_id'])} {won(bill_05['total_amount'])}",
         "read_at": fmt(now.replace(hour=9, minute=0)), "created_at": fmt(now.replace(hour=8, minute=0))},
    ]
    t["notifications"] = [{"id": f"ntf_{i:03d}", **n} for i, n in enumerate(notes, 1)]
    t["notification_preferences"] = [
        {"user_id": a["user_id"], "account_id": a["id"], "enabled": a["id"] != "acc_002",
         "minimum_amount": 10_000 if a["id"] == "acc_001" else 0}
        for a in d["accounts"] if a["lifecycle_status"] != "CLOSED"
    ]

    if errs:
        raise ValueError("\n".join(errs))
    return t


PK = {"local_credentials": ("user_id",), "pin_credentials": ("user_id",), "transfer_limits": ("account_id",),
      "notification_preferences": ("user_id", "account_id")}


def reset_sql(tables):
    """이 시드가 만든 행만 지운다(자식 → 부모). 앱이 만든 행은 건드리지 않음"""
    out = []
    for table, rows in reversed(list(tables.items())):
        if table == "terms":  # 앱이 만든 가입 동의(user_consents)가 가리키므로 지우지 않는다(다시 넣을 때 ON CONFLICT 로 그대로)
            continue
        cols = PK.get(table, ("id",))
        keys = ", ".join("(" + ", ".join(parents.sql_value(r[c]) for c in cols) + ")" for r in rows)
        out.append(f"DELETE FROM {table} WHERE ({', '.join(cols)}) IN ({keys});")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=os.path.join(HERE, "..", "data", "dummy"))
    ap.add_argument("--reset", action="store_true", help="이 시드 행을 먼저 지우고 다시 넣기")
    args = ap.parse_args()
    sys.stderr.reconfigure(encoding="utf-8")
    env = read_env()
    password = os.environ.get("SEED_PASSWORD") or env.get("SEED_PASSWORD")
    pin = os.environ.get("SEED_PIN") or env.get("SEED_PIN")
    if not password or not pin or not (len(pin) == 6 and pin.isdigit()):
        print("오류: SEED_PASSWORD 와 6자리 숫자 SEED_PIN 이 필요함 (환경변수 또는 backend/.env)", file=sys.stderr)
        sys.exit(1)
    now = datetime.datetime.now(KST).replace(tzinfo=None, second=0, microsecond=0)
    try:
        tables = build(args.root, now, password, pin)
    except ValueError as e:
        print(f"오류:\n{e}", file=sys.stderr)
        sys.exit(1)
    sql = parents.to_sql(tables, header=f"scripts/seed_scenarios.py 가 만든 시나리오 시드 (기준 시각 {fmt(now)})")
    head = "\n".join("-- " + line for line in SCENARIOS.splitlines())
    if args.reset:
        sql = sql.replace("BEGIN;", "BEGIN;\n" + "\n".join(reset_sql(tables)), 1)
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write(head + "\n" + sql)
    print(" · ".join(f"{t} {len(r)}" for t, r in tables.items()), file=sys.stderr)
