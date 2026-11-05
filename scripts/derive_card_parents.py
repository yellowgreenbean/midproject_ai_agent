# 카드 부모 데이터를 더미에서 뽑아 INSERT SQL 로 만든다 (읽기만 함, DB 에 직접 넣지 않음)
#   card_companies 1 · card_products 5 · categories 13 · merchants 34 · billing_cycle_rules 3
# 더미 승인·보유카드를 DB 에 옮기려면 FK 부모가 먼저 있어야 하는데 더미에는 이 표들이 없다
# (docs/세션_작업_정리_2026-11-05.md 「seed가 필요한 상황」 1번). 그래서 지어내지 않고 더미의 이름에서 뽑는다.
#
# 실행: python3 scripts/derive_card_parents.py [더미 폴더] > card_parents.sql
#       docker exec -i midproject-postgres psql -U app -d midproject -v ON_ERROR_STOP=1 < card_parents.sql
# 나중에 더미 적재 스크립트는 derive() 를 import 해서 이름 → id 를 찾는다(card_product_id, merchant_id).
#
# 더미에 없어서 이 파일이 정하는 값 (기획서·ERD 근거가 생기면 여기만 고친다)
#   - 카드사: 더미 카드 30장은 모두 우리 서비스 발급(TOSS_ISSUED, 기획서 C-2) → 카드사 1곳.
#             이름은 상품 이름 앞말 '한빛'(5개 중 4개)에서 정함. '할인카드'도 같은 발급사로 둔다
#   - 업종 code: 더미 resMemberStoreType(한글) → 영문 code 대응표 CATEGORY_CODE. 상위 분류(parent_id)는 더미에 없어 NULL
#   - brand: 카드 번호 앞자리(IIN)로 정함. 4 → VISA, 62 → UNIONPAY …, 모르는 번호 → LOCAL
#   - billing_cycle_rules: 기획서 Part 4 1-4 표(결제일 1·14·25). 더미 결제일(14)이 이 안에 있는지 확인한다
#   - 연회비·최소 나이·이미지·사업자번호 등: 더미에 없으므로 스키마 기본값 또는 NULL
import json, os, sys

COMPANY = {"id": "cc_001", "code": "HANBIT", "name": "한빛카드"}

# 더미 resMemberStoreType → categories.code (값이 새로 생기면 여기 더해야 실행된다)
CATEGORY_CODE = {
    "편의점": "CONVENIENCE", "음식점": "RESTAURANT", "카페": "CAFE", "약국": "PHARMACY",
    "배달": "DELIVERY", "생활용품": "HOUSEHOLD", "구독": "SUBSCRIPTION", "주유": "FUEL",
    "마트": "MART", "온라인쇼핑": "ONLINE_SHOPPING", "영화": "MOVIE", "교통": "TRANSPORT",
    "서점": "BOOKSTORE",
}

# 기획서 Part 4 1-4 「이용 기간과 결제일이 다를 때」: 결제일 → (시작 월 차이, 시작일, 끝 월 차이, 끝일). 99 = 말일
BILLING_CYCLE = {
    1: (-2, 18, -1, 17),   # 전전월 18일 ~ 전월 17일
    14: (-1, 1, -1, 99),   # 전월 1일 ~ 전월 말일
    25: (-1, 12, 0, 11),   # 전월 12일 ~ 당월 11일
}


def brand_of(card_no):
    """카드 번호 앞자리(IIN) → card_products.brand"""
    if card_no.startswith("4"):
        return "VISA"
    if card_no[:2] in ("51", "52", "53", "54", "55") or "2221" <= card_no[:4] <= "2720":
        return "MASTER"
    if card_no[:2] in ("34", "37"):
        return "AMEX"
    if card_no[:2] == "35":
        return "JCB"
    if card_no[:2] == "62":
        return "UNIONPAY"
    return "LOCAL"


def card_type_of(res_card_type):
    """기획서 C-2 규칙 5: resCardType 앞부분이 체크 → CHECK, 신용 → CREDIT"""
    head = res_card_type.split("/")[0]
    if head == "체크":
        return "CHECK"
    if head == "신용":
        return "CREDIT"
    raise ValueError(f"resCardType '{res_card_type}' 을 CHECK/CREDIT 로 바꿀 수 없음")


def derive(root):
    """더미 폴더 → {표 이름: [행 dict]} 와 이름 → id 찾기표"""
    load = lambda p: json.load(open(os.path.join(root, p), encoding="utf-8"))["data"]
    cards, approvals, bills = load("cards/cards.json"), load("cards/card_approvals.json"), load("cards/card_billing.json")
    errs = []

    # card_products: 이름마다 종류·카드 번호 앞자리가 하나여야 한다
    prod = {}
    for c in cards:
        key = (card_type_of(c["resCardType"]), brand_of(c["resCardNo"]))
        prev = prod.setdefault(c["resCardName"], key)
        if prev != key:
            errs.append(f"상품 '{c['resCardName']}' 의 종류·브랜드가 카드마다 다름 {prev} / {key}")
    card_products = [
        {"id": f"cp_{i:03d}", "card_company_id": COMPANY["id"], "name": name, "card_type": t, "brand": b}
        for i, (name, (t, b)) in enumerate(sorted(prod.items()), 1)
    ]

    # categories · merchants: 가맹점 이름마다 업종이 하나여야 한다
    store_type = {}
    for a in approvals:
        t = store_type.setdefault(a["resMemberStoreName"], a["resMemberStoreType"])
        if t != a["resMemberStoreType"]:
            errs.append(f"가맹점 '{a['resMemberStoreName']}' 업종이 둘 ({t} / {a['resMemberStoreType']})")
    missing = sorted(set(store_type.values()) - CATEGORY_CODE.keys())
    if missing:
        errs.append(f"CATEGORY_CODE 에 없는 업종 {missing} — 대응표에 code 를 더할 것")
    categories = [
        {"id": f"cat_{i:03d}", "parent_id": None, "code": CATEGORY_CODE.get(name, "?"), "name": name}
        for i, name in enumerate(sorted(set(store_type.values())), 1)
    ]
    cat_id = {c["name"]: c["id"] for c in categories}
    merchants = [
        {"id": f"mer_{i:03d}", "category_id": cat_id[t], "name": name, "business_no": None}
        for i, (name, t) in enumerate(sorted(store_type.items()), 1)
    ]

    # billing_cycle_rules: 더미 청구서 결제일이 규칙에 있어야 이용 기간을 계산할 수 있다 (기획서 C-2 규칙 1)
    for d in sorted({int(b["resPaymentDueDate"][6:]) for b in bills} - BILLING_CYCLE.keys()):
        errs.append(f"더미 결제일 {d}일 의 이용 기간 규칙이 BILLING_CYCLE 에 없음")
    rules = [
        {"card_company_id": COMPANY["id"], "payment_day": day, "start_month_offset": s_m, "start_day": s_d,
         "end_month_offset": e_m, "end_day": e_d}
        for day, (s_m, s_d, e_m, e_d) in sorted(BILLING_CYCLE.items())
    ]

    if errs:
        raise ValueError("\n".join(errs))
    tables = {
        "card_companies": [COMPANY],
        "card_products": card_products,
        "categories": categories,
        "merchants": merchants,
        "billing_cycle_rules": rules,
    }
    lookup = {
        "card_product_id": {p["name"]: p["id"] for p in card_products},
        "merchant_id": {m["name"]: m["id"] for m in merchants},
    }
    return tables, lookup


def sql_value(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)  # JSONB 칸
    return "'" + str(v).replace("'", "''") + "'"


def to_sql(tables, header="scripts/derive_card_parents.py 가 data/dummy 에서 만든 카드 부모 데이터"):
    out = [f"-- {header}. 손으로 고치지 말 것", "SET client_encoding = 'UTF8';", "BEGIN;"]
    for table, rows in tables.items():  # 부모 → 자식 순서 (dict 순서)
        if not rows:
            continue
        cols = list(rows[0])
        out.append(f"\n-- {table} {len(rows)}")
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES")
        out.append(",\n".join("  (" + ", ".join(sql_value(r[c]) for c in cols) + ")" for r in rows))
        out.append("ON CONFLICT DO NOTHING;")
    out.append("\nCOMMIT;")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "dummy")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        tables, _ = derive(root)
    except ValueError as e:
        print(f"오류:\n{e}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write(to_sql(tables))
    print(" · ".join(f"{t} {len(r)}" for t, r in tables.items()), file=sys.stderr)
