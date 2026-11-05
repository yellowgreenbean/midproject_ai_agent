# 더미 데이터(data/dummy) → 기획서 스키마(docs/sql) INSERT SQL 만들기 (읽기만 함, DB 에 직접 넣지 않음)
# 변환 규칙은 docs/기획서.md Part 6 C-2 「더미 → 기획서 변환 규칙」 1~6 을 따른다. 더미에 없는 기능의 시험용 행은 seed_scenarios.py 가 이 뒤에 덧붙인다.
#
# 실행: python3 scripts/load_dummy.py [더미 폴더] > dummy.sql
#       docker exec -i midproject-postgres psql -U app -d midproject -v ON_ERROR_STOP=1 < dummy.sql
# 카드 부모 데이터(카드사·상품·업종·가맹점·결제일 규칙)는 derive_card_parents.py 에서 같이 만든다.
# 모든 INSERT 는 ON CONFLICT DO NOTHING — 여러 번 넣어도 결과가 같다. 한 트랜잭션이라 하나라도 실패하면 아무것도 안 들어간다.
#
# 더미에 없어서 이 파일이 정하는 값 (기획서에 규칙이 생기면 여기만 고친다)
#   - card_transactions.id = 'ctx_' + 승인번호, card_bills.id = 'bill_' + 카드 id + '_' + 결제 연월 (더미에 id 가 없음)
#   - transactions.display_name = 적요(resAccountDesc3). 상대 은행·계좌번호는 더미에 없어 NULL
#   - user_cards.card_number_masked = 카드 번호를 4자리씩 '-' 로 끊음 (예: 4214-****-****-0001)
#   - 기준 시각 = 계좌 잔액 기준 시각(balance_as_of)의 최댓값. 청구서 상태(규칙 2)를 이 시각으로 정한다
#   - 더미에 없는 칸(card_bills.confirmed_at, user_cards.last_used_at, canceled_at 등)은 NULL 또는 스키마 기본값
import collections, calendar, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive_card_parents as parents  # noqa: E402

KST = datetime.timezone(datetime.timedelta(hours=9))

# 기획서 C-2: 거래구분(resAccountDesc2) → 원장 type (check_dummy.py 의 TYPE 과 같아야 함)
TX_TYPE = {"이체": "TRANSFER_OUT", "이체입금": "TRANSFER_IN", "급여": "TRANSFER_IN", "자동이체": "TRANSFER_OUT",
           "체크카드": "CARD_PAYMENT", "카드대금": "CARD_PAYMENT", "적금납입": "SUBSCRIPTION_PAYMENT"}


def num(v):
    """더미의 금액 문자열 → 정수 (null·빈 값은 None)"""
    return None if v in (None, "") else int(v)


def kst(iso):
    """회원 시각 ISO(+09:00) → 한국 시각 'YYYY-MM-DD HH:MM:SS' (DB 시간대 Asia/Seoul)"""
    if iso is None:
        return None
    return datetime.datetime.fromisoformat(iso).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def ts(ymd, hms="000000"):
    """CODEF 날짜·시각 문자열 → 'YYYY-MM-DD HH:MM:SS'"""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]} {hms[:2]}:{hms[2:4]}:{hms[4:6]}"


def add_months(year, month, offset):
    m = year * 12 + (month - 1) + offset
    return m // 12, m % 12 + 1


def day_in(year, month, day):
    """end_day 99 = 말일 (billing_cycle_rules)"""
    last = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, last if day == 99 else min(day, last))


def build(root):
    load = lambda p: json.load(open(os.path.join(root, p), encoding="utf-8"))
    users = load("users/users.json")["data"]
    accts = load("accounts/accounts.json")["data"]
    txg = load("transactions/transactions.json")["data"]
    cards = load("cards/cards.json")["data"]
    approvals = load("cards/card_approvals.json")["data"]
    bills = load("cards/card_billing.json")["data"]
    prod = load("products/products.json")
    subs = load("products/subscriptions.json")["data"]
    pays = load("products/subscription_payments.json")["data"]
    tables, lookup = parents.derive(root)
    errs = []

    acc_by_id = {a["id"]: a for a in accts}
    acc_by_disp = {a["resAccountDisplay"]: a for a in accts}
    acc_by_num = {a["resAccount"]: a for a in accts}
    ref = max(a["balance_as_of"] for a in accts)          # 더미 기준 시각
    ref_date = datetime.date(int(ref[:4]), int(ref[4:6]), int(ref[6:8]))

    # 회원 · 계좌 · 잔액
    tables["users"] = [
        {"id": u["id"], "username": u["username"], "name": u["name"], "email": u["email"],
         "email_verified_at": kst(u["email_verified_at"]), "birth_date": u["birth_date"], "gender": u["gender"],
         "payday": u["payday"], "status": u["status"], "created_at": kst(u["created_at"]),
         "withdrawn_at": kst(u["withdrawn_at"])}
        for u in users
    ]
    tables["accounts"] = [
        {"id": a["id"], "user_id": a["user_id"], '"resAccount"': a["resAccount"],
         '"resAccountDisplay"': a["resAccountDisplay"], '"resAccountName"': a["resAccountName"],
         "account_type": a["account_type"], "lifecycle_status": a["lifecycle_status"],
         '"resAccountNickName"': a["resAccountNickName"], "is_favorite": a["is_favorite"],
         '"resAccountStartDate"': a["resAccountStartDate"], "closed_at": a["closed_at"]}
        for a in accts
    ]
    tables["account_balances"] = [
        {"account_id": a["id"], "currency": a["resAccountCurrency"], "balance": num(a["resAccountBalance"]),
         "updated_at": ts(a["balance_as_of"][:8], a["balance_as_of"][8:])}
        for a in accts
    ]

    # 원장: 입금·출금 중 하나만 0 이 아니어야 한다. 파일은 최신이 먼저 — 넣는 순서는 상관없음
    ledger = []
    for g in txg:
        for r in g["resTrHistoryList"]:
            tin, tout = num(r["resAccountIn"]), num(r["resAccountOut"])
            if (tin > 0) == (tout > 0):
                errs.append(f"{r['id']} 입금·출금이 둘 다 있거나 둘 다 0")
            if r["resAccountDesc2"] not in TX_TYPE:
                errs.append(f"{r['id']} 거래구분 '{r['resAccountDesc2']}' 이 원장 type 에 대응 안 됨")
            ledger.append({"id": r["id"], "account_id": g["account_id"], "type": TX_TYPE.get(r["resAccountDesc2"], "?"),
                           "amount": tin or tout, "balance_after": num(r["resAfterTranBalance"]),
                           "display_name": r["resAccountDesc3"] or None,
                           "created_at": ts(r["resAccountTrDate"], r["resAccountTrTime"])})
    tables["transactions"] = ledger

    # 예금·적금 상품과 가입
    tables["products"] = [{k: p[k] for k in ("id", "bank", "name", "type", "description", "status", "source_url", "verified_at")}
                          for p in prod["products"]]
    tables["product_rates"] = [{k: r[k] for k in ("id", "product_id", "term_min", "term_max", "term_unit", "base_rate",
                                                   "bonus_rate", "effective_from")} for r in prod["product_rates"]]
    tables["product_rules"] = [
        {"id": r["id"], "product_id": r["product_id"], "min_amount": num(r["min_amount"]), "max_amount": num(r["max_amount"]),
         "min_months": r["min_months"], "max_months": r["max_months"], "max_per_user": r["max_per_user"],
         "rules_json": r["rules_json"]}
        for r in prod["product_rules"]
    ]
    tables["subscriptions"] = [
        {**{k: s[k] for k in ("id", "user_id", "product_id", "source_account_id")},
         "principal": num(s["principal"]), "monthly_amount": num(s["monthly_amount"]),
         **{k: s[k] for k in ("applied_rate", "start_date", "maturity_date", "status", "closed_at", "idempotency_key")}}
        for s in subs
    ]
    tables["subscription_payments"] = [
        {"id": p["id"], "subscription_id": p["subscription_id"], "paid_amount": num(p["paid_amount"]), "paid_at": p["paid_at"]}
        for p in pays
    ]

    # 보유 카드 (규칙 5·6). 신용카드의 결제 계좌·결제일은 청구서에서 읽는다
    bills_by_card = collections.defaultdict(list)
    for b in bills:
        bills_by_card[b["card_id"]].append(b)
    user_cards = []
    for c in cards:
        credit = parents.card_type_of(c["resCardType"]) == "CREDIT"
        if credit:
            pay_accts = {b["resPaymentAccount"] for b in bills_by_card[c["id"]]}
            pay_days = {int(b["resPaymentDueDate"][6:]) for b in bills_by_card[c["id"]]}
            if len(pay_accts) > 1 or len(pay_days) > 1:
                errs.append(f"신용카드 {c['id']} 청구서마다 결제 계좌·결제일이 다름 {pay_accts} {pay_days}")
            acct = acc_by_disp.get(next(iter(pay_accts))) if pay_accts else None
            payment_day = next(iter(pay_days)) if pay_days else None
        else:
            link = c.get("resLinkedAccount", "")
            acct = acc_by_disp.get(link) or acc_by_num.get(link)
            payment_day = None
        if acct is None and (credit and bills_by_card[c["id"]] or not credit and c.get("resLinkedAccount")):
            errs.append(f"카드 {c['id']} 의 연결·결제 계좌를 찾을 수 없음")
        no = c["resCardNo"]
        valid = c["resValidPeriod"]  # YYYYMM → 그 달 말일 (빈 값이면 NULL, 규칙 6)
        user_cards.append({
            "id": c["id"], "user_id": c["user_id"], "card_product_id": lookup["card_product_id"][c["resCardName"]],
            "source": "TOSS_ISSUED", "card_number_masked": "-".join(no[i:i + 4] for i in range(0, len(no), 4)),
            "last4": no[-4:],
            "expires_at": day_in(int(valid[:4]), int(valid[4:6]), 99).isoformat() if valid else None,
            "linked_account_id": acct["id"] if acct else None, "payment_day": payment_day,
            "credit_limit": c["credit_limit"], "status": c["status"],
            "issued_at": ts(c["resIssueDate"]) if c["resIssueDate"] else None,
        })
    tables["user_cards"] = user_cards

    # 승인 내역 (규칙 3·4)
    ctx = []
    for a in approvals:
        used, canceled = num(a["resUsedAmount"]), (num(a["resCancelAmount"]) or 0)
        if a["resCancelYN"] == "0":
            status, canceled = "APPROVED", 0
        else:
            status = "CANCELED" if canceled == used else "PARTIAL_CANCELED"
        ctx.append({
            "id": f"ctx_{a['resApprovalNo']}", "user_card_id": a["card_id"],
            "merchant_id": lookup["merchant_id"][a["resMemberStoreName"]], "approval_no": a["resApprovalNo"],
            "transacted_at": ts(a["resUsedDate"], a["resUsedTime"]), "amount": used,
            "installment_months": num(a["resInstallmentMonth"]) or 0, "is_overseas": a["resHomeForeignType"] != "1",
            "currency": a["resAccountCurrency"], "status": status, "canceled_amount": canceled,
        })
    tables["card_transactions"] = ctx

    # 청구서 (규칙 1·2): 결제 연월 = 결제일의 연월, 이용 기간 = billing_cycle_rules, 상태는 기준 시각으로
    rules = {(r["card_company_id"], r["payment_day"]): r for r in tables["billing_cycle_rules"]}
    company_of = {p["id"]: p["card_company_id"] for p in tables["card_products"]}
    card_row = {c["id"]: c for c in user_cards}
    card_payments = [(g["account_id"], r) for g in txg for r in g["resTrHistoryList"] if r["resAccountDesc2"] == "카드대금"]
    used_tx = set()
    card_bills = []
    for b in sorted(bills, key=lambda x: (x["card_id"], x["resPaymentDueDate"])):
        due = b["resPaymentDueDate"]
        y, m = int(due[:4]), int(due[4:6])
        rule = rules.get((company_of[card_row[b["card_id"]]["card_product_id"]], int(due[6:])))
        if rule is None:
            errs.append(f"청구 {b['card_id']} {due} 결제일 규칙 없음"); continue
        start = day_in(*add_months(y, m, rule["start_month_offset"]), rule["start_day"])
        end = day_in(*add_months(y, m, rule["end_month_offset"]), rule["end_day"])
        pay_date = datetime.date(y, m, int(due[6:]))
        total = num(b["resTotalAmount"])
        pay_acct = acc_by_disp.get(b["resPaymentAccount"])
        paid = next((r for aid, r in card_payments
                     if r["id"] not in used_tx and pay_acct and aid == pay_acct["id"]
                     and r["resAccountTrDate"] == due and num(r["resAccountOut"]) == total), None)
        if ref_date <= end:
            status = "SCHEDULED"
        elif paid:
            status = "PAID"
            used_tx.add(paid["id"])
        elif ref_date <= pay_date:
            status = "CONFIRMED"
        else:
            status = "OVERDUE"
        card_bills.append({
            "id": f"bill_{b['card_id']}_{due[:6]}", "user_card_id": b["card_id"], "billing_ym": due[:6],
            "usage_start": start.isoformat(), "usage_end": end.isoformat(), "payment_date": pay_date.isoformat(),
            "total_amount": total, "paid_amount": total if status == "PAID" else 0, "status": status,
            "paid_at": ts(paid["resAccountTrDate"], paid["resAccountTrTime"]) if status == "PAID" else None,
        })
    tables["card_bills"] = card_bills

    if errs:
        raise ValueError("\n".join(errs))
    # FK 순서: 부모가 먼저. derive() 의 카드 부모 표 뒤에 회원 → 계좌 → … → 카드 순
    order = ["users", "accounts", "account_balances", "transactions", "products", "product_rates", "product_rules",
             "subscriptions", "subscription_payments", "card_companies", "card_products", "categories", "merchants",
             "billing_cycle_rules", "user_cards", "card_transactions", "card_bills"]
    return {t: tables[t] for t in order}


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "dummy")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        tables = build(root)
    except ValueError as e:
        print(f"오류:\n{e}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write(parents.to_sql(tables, header="scripts/load_dummy.py 가 data/dummy 에서 만든 적재 SQL"))
    print(" · ".join(f"{t} {len(r)}" for t, r in tables.items()), file=sys.stderr)
