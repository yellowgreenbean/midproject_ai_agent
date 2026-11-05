# 더미 데이터 정합성 검사 (읽기만 함) — AGENTS.md 「게이트」 항목 + 날짜 순서 + 거래구분 대응
# 실행: python3 scripts/check_dummy.py  (다른 폴더를 검사하려면 경로를 인자로)
import collections, datetime, json, os, sys

R = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "dummy")
L = lambda p: json.load(open(os.path.join(R, p), encoding="utf-8"))
users = {u["id"]: u for u in L("users/users.json")["data"]}
accts = {a["id"]: a for a in L("accounts/accounts.json")["data"]}
txg = L("transactions/transactions.json")["data"]
cards = {c["id"]: c for c in L("cards/cards.json")["data"]}
apps = L("cards/card_approvals.json")["data"]
bills = L("cards/card_billing.json")["data"]
prod = L("products/products.json")
subs = L("products/subscriptions.json")["data"]
pays = L("products/subscription_payments.json")["data"]
errs = []
E = errs.append
by_disp = {a["resAccountDisplay"]: a for a in accts.values()}
by_num = {a["resAccount"]: a for a in accts.values()}
linked = lambda c: by_disp.get(c["resLinkedAccount"]) or by_num.get(c["resLinkedAccount"])
ymd = lambda iso: iso[:10].replace("-", "")  # 회원 시각(ISO) → 더미 날짜(YYYYMMDD)

# 1. 거래내역: 파일 순서(최신 먼저)로 계산 — 같은 시각 거래가 있어 시각으로 다시 정렬하면 틀린다
# 거래구분(resAccountDesc2) → 원장 type (거래·카드 기획서 C-2)
TYPE = {"이체": "TRANSFER_OUT", "이체입금": "TRANSFER_IN", "급여": "TRANSFER_IN", "자동이체": "TRANSFER_OUT",
        "체크카드": "CARD_PAYMENT", "카드대금": "CARD_PAYMENT", "적금납입": "SUBSCRIPTION_PAYMENT"}
txid = collections.Counter()
for g in txg:
    a = accts.get(g["account_id"])
    if not a: E(f"거래 묶음의 계좌 없음 {g['account_id']}"); continue
    rows = g["resTrHistoryList"]
    for r in rows:
        txid[r["id"]] += 1
        if r["resAccountDesc2"] not in TYPE: E(f"{r['id']} 거래구분 '{r['resAccountDesc2']}' 이 원장 type 에 대응 안 됨")
        if r["resAccountTrDate"] < a["resAccountStartDate"]: E(f"{r['id']} 계좌 개설 전 거래")
        if a["closed_at"] and r["resAccountTrDate"] > a["closed_at"]: E(f"{r['id']} 계좌 해지 뒤 거래")
        if int(r["resAfterTranBalance"]) < 0: E(f"{r['id']} 음수 잔액")
    if not rows: continue
    if rows[0]["resAfterTranBalance"] != a["resAccountBalance"]:
        E(f"{a['id']} 최신 거래 후 잔액 {rows[0]['resAfterTranBalance']} != 계좌 잔액 {a['resAccountBalance']}")
    old = rows[::-1]
    for prev, cur in zip(old, old[1:]):
        exp = int(prev["resAfterTranBalance"]) + int(cur["resAccountIn"]) - int(cur["resAccountOut"])
        if exp != int(cur["resAfterTranBalance"]): E(f"{cur['id']} 계산 틀림 {exp} != {cur['resAfterTranBalance']}")
for k, v in txid.items():
    if v > 1: E(f"거래 id 중복 {k}")

# 2. 계좌
for a in accts.values():
    if a["user_id"] not in users: E(f"{a['id']} 주인 없음"); continue
    if a["lifecycle_status"] == "CLOSED" and (a["resAccountBalance"] != "0" or not a["closed_at"]): E(f"해지 계좌 {a['id']} 잔액 0·closed_at 필요")
    if a["lifecycle_status"] != "CLOSED" and a["closed_at"] is not None: E(f"{a['id']} 해지 전인데 closed_at 있음")
    if a["resAccountStartDate"] < ymd(users[a["user_id"]]["created_at"]): E(f"{a['id']} 회원 가입 전 개설")

# 3. 카드: 주인, 연결·결제 계좌, 청구 = 승인, 9월 청구 = 10/14 카드대금, 10월 체크 승인 = 연결 계좌 출금, 한도
apid = collections.Counter(x["resApprovalNo"] for x in apps)
for k, v in apid.items():
    if v > 1: E(f"승인번호 중복 {k}")
net = collections.defaultdict(int)  # (카드, 사용월) → 취소 뺀 승인 합계
for x in apps:
    if x["resCancelYN"] == "0": net[(x["card_id"], x["resUsedDate"][:6])] += int(x["resUsedAmount"])
for c in cards.values():
    if c["user_id"] not in users: E(f"카드 {c['id']} 주인 없음")
    if c["resCardType"].startswith("체크"):
        a = linked(c)
        if not a or a["user_id"] != c["user_id"] or a["account_type"] != "CHECKING": E(f"체크카드 {c['id']} 연결 계좌 이상 {c['resLinkedAccount']}")
for b in bills:
    a = by_disp.get(b["resPaymentAccount"])
    if not a or a["user_id"] != cards[b["card_id"]]["user_id"]: E(f"청구 {b['card_id']} 결제 계좌 주인 다름")
    if net[(b["card_id"], b["resBillingMonth"])] != int(b["resTotalAmount"]): E(f"청구 {b['card_id']} {b['resBillingMonth']} 합계 != 승인 합계")
txs = [(g["account_id"], r) for g in txg for r in g["resTrHistoryList"]]
for cid in {b["card_id"] for b in bills}:
    sept = net[(cid, "202609")]
    outs = [r for aid, r in txs if r["resAccountDesc2"] == "카드대금" and r["resAccountTrDate"] == "20261014"
            and accts[aid]["user_id"] == cards[cid]["user_id"] and int(r["resAccountOut"]) == sept]
    if sept and not outs: E(f"신용카드 {cid} 9월 사용 {sept} 과 같은 10/14 카드대금 출금 없음")
for c in cards.values():
    if c["resCardType"].startswith("체크"):
        a = linked(c)
        if not a: continue
        oct_ap = sorted(int(x["resUsedAmount"]) for x in apps if x["card_id"] == c["id"] and x["resUsedDate"][:6] == "202610" and x["resCancelYN"] == "0")
        oct_tx = sorted(int(r["resAccountOut"]) for aid, r in txs if aid == a["id"] and r["resAccountDesc2"] == "체크카드")
        if oct_ap != oct_tx: E(f"체크카드 {c['id']} 10월 승인 {sum(oct_ap)} != 연결 계좌 체크카드 출금 {sum(oct_tx)}")
    elif c["credit_limit"] is not None:
        used = sum(int(x["resUsedAmount"]) for x in apps if x["card_id"] == c["id"] and x["resCancelYN"] == "0")
        if used - net[(c["id"], "202609")] > int(c["credit_limit"]): E(f"신용카드 {c['id']} 한도 초과")

# 4. 상품
pids = {p["id"] for p in prod["products"]}
for s in subs:
    a = accts.get(s["source_account_id"])
    if not a or a["user_id"] != s["user_id"] or a["account_type"] != "CHECKING": E(f"{s['id']} 출금 계좌 이상"); continue
    if s["status"] in ("MATURED", "TERMINATED") and not s["closed_at"]: E(f"{s['id']} closed_at 없음")
    if s["product_id"] not in pids: E(f"{s['id']} 상품 없음")
    if s["start_date"] < a["resAccountStartDate"]: E(f"{s['id']} 출금 계좌 개설 전 시작")
    if s["start_date"] < ymd(users[s["user_id"]]["created_at"]): E(f"{s['id']} 회원 가입 전 시작")
ik = collections.Counter(s.get("idempotency_key") for s in subs)
for k, v in ik.items():
    if not k: E("가입 계약에 idempotency_key 없음")
    elif v > 1: E(f"idempotency_key 중복 {k}")
for p in pays:
    s = next(x for x in subs if x["id"] == p["subscription_id"])
    if not [r for aid, r in txs if aid == s["source_account_id"] and r["resAccountTrDate"] == p["paid_at"][:8] and r["resAccountOut"] == p["paid_amount"]]:
        E(f"납입 {p['id']} 과 같은 날·같은 금액 출금 없음")
rr = collections.defaultdict(list)
for r in prod["product_rates"]: rr[(r["product_id"], r["term_unit"], r["effective_from"])].append((r["term_min"], r["term_max"], r["id"]))
for k, v in rr.items():
    v.sort()
    for x, y in zip(v, v[1:]):
        if y[0] <= x[1]: E(f"금리 구간 겹침 {k} {x[2]} {y[2]}")

# 5. 회원
for u in users.values():
    datetime.date.fromisoformat(u["birth_date"])
    if u["gender"] not in ("M", "F"): E(f"{u['id']} 성별 값")
    if u["payday"] is not None and not 1 <= u["payday"] <= 31: E(f"{u['id']} 월급일 값")
    if (u["status"] == "WITHDRAWN") != (u["withdrawn_at"] is not None): E(f"{u['id']} 탈퇴 상태와 withdrawn_at 불일치")

print("오류", len(errs)); [print(" -", e) for e in errs]
sys.exit(1 if errs else 0)
