# 카드 부모 데이터를 더미에서 뽑아 INSERT SQL 로 만든다 (읽기만 함, DB 에 직접 넣지 않음)
#   card_companies 1 · card_products 5 · categories 13(+혜택 업종 7) · merchants 34 · billing_cycle_rules 3
#   + 혜택(data/dummy/cards/card_benefits.json): card_performance_tiers · card_benefit_limit_groups · card_benefits
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
#   - 연회비·한 줄 요약: card_benefits.json (실제 카드 참고, 사용자 결정 2026-11-10)
#   - 최소 나이·이미지·사업자번호 등: 더미에 없으므로 스키마 기본값 또는 NULL
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

    tiers, groups, benefits = benefit_rows(load_benefits(root), card_products, categories, errs)

    if errs:
        raise ValueError("\n".join(errs))
    tables = {
        "card_companies": [COMPANY],
        "card_products": card_products,
        "categories": categories,
        "merchants": merchants,
        "billing_cycle_rules": rules,
        "card_performance_tiers": tiers,
        "card_benefit_limit_groups": groups,
        "card_benefits": benefits,
    }
    lookup = {
        "card_product_id": {p["name"]: p["id"] for p in card_products},
        "merchant_id": {m["name"]: m["id"] for m in merchants},
    }
    return tables, lookup


# --- 혜택 (data/dummy/cards/card_benefits.json, 2026-11-10) ----------------------------------------------
# 실제 카드(카드고릴라 원문 data/cardgorilla/)를 사람이 칸에 옮긴 파일을 표 행으로 펼친다.
#   tiers "MONTH"/"QUARTER" → 그 기간의 실적 구간마다 한 행 (…_by_tier 는 구간 순서대로), null → 실적 조건 없는 한 행
#   id: 구간 cpt_<상품번호>_<M|Q><구간>, 통합 한도 cblg_<상품번호>_<key>_<M|Q><구간>, 혜택 cb_<상품번호>_<혜택번호>_<M|Q><구간>
BENEFITS_FILE = os.path.join("cards", "card_benefits.json")
BENEFIT_KEYS = {"category", "benefit_type", "value_type", "value", "value_by_tier", "tiers", "limit_group",
                "min_payment_amount", "monthly_limit_amount", "monthly_limit_by_tier", "monthly_limit_count",
                "description", "merchant_names", "payment_channel", "pay_methods", "days_of_week", "time_start",
                "time_end", "max_eligible_amount", "per_payment_max_benefit", "daily_limit_count"}
PERIOD_MARK = {"MONTH": "M", "QUARTER": "Q"}


def load_benefits(root):
    with open(os.path.join(root, BENEFITS_FILE), encoding="utf-8") as f:
        return json.load(f)


def benefit_rows(ben, card_products, categories, errs):
    """card_benefits.json → (card_performance_tiers, card_benefit_limit_groups, card_benefits) 행. 업종·상품도 여기서 보탠다."""
    code_id = {c["code"]: c["id"] for c in categories}
    for c in ben["categories"]:  # 혜택에만 나오는 업종 (부모는 더미 업종)
        if c["code"] in code_id:
            errs.append(f"혜택 업종 {c['code']} 이 이미 있음")
            continue
        parent = c["parent_code"] and code_id.get(c["parent_code"])
        if c["parent_code"] and parent is None:
            errs.append(f"혜택 업종 {c['code']} 의 상위 업종 {c['parent_code']} 이 없음")
        categories.append({"id": c["id"], "parent_id": parent or None, "code": c["code"], "name": c["name"]})
        code_id[c["code"]] = c["id"]

    by_name = {p["name"]: p for p in card_products}
    for p in card_products:  # 혜택 파일에 없는 상품도 같은 칸을 갖게 (to_sql 은 첫 행의 칸을 쓴다)
        p.update(annual_fee_domestic=0, annual_fee_overseas=0, summary=None)
    tiers, groups, rows = [], [], []
    for spec in ben["data"]:
        p = by_name.get(spec["product_name"])
        if p is None:
            errs.append(f"혜택 상품 '{spec['product_name']}' 이 더미 카드에 없음")
            continue
        p.update(annual_fee_domestic=spec["annual_fee_domestic"], annual_fee_overseas=spec["annual_fee_overseas"],
                 summary=spec["summary"])
        no = p["id"][3:]  # cp_001 → 001

        tier_ids, last = {"MONTH": [], "QUARTER": []}, {}
        for t in spec["tiers"]:
            ids = tier_ids[t["period"]]
            prev = last.get(t["period"])
            if prev and prev["max_spend"] != t["min_spend"]:
                errs.append(f"{p['name']} {t['period']} 구간이 이어지지 않음 ({prev['max_spend']} → {t['min_spend']})")
            if t["max_spend"] is not None and t["max_spend"] <= t["min_spend"]:
                errs.append(f"{p['name']} 구간 상한이 하한보다 작음 {t}")
            ids.append(f"cpt_{no}_{PERIOD_MARK[t['period']]}{len(ids) + 1}")
            last[t["period"]] = {"id": ids[-1], "card_product_id": p["id"], "period": t["period"], "tier_level": len(ids),
                                 "min_spend": t["min_spend"], "max_spend": t["max_spend"]}
            tiers.append(last[t["period"]])

        def expand(item, what):
            """[(tier_id 또는 None, 구간 번호 0…, id 꼬리)] — tiers 에 맞춰 펼친다"""
            if item["tiers"] is None:
                return [(None, None, "")]
            ids = tier_ids.get(item["tiers"])
            if not ids:
                errs.append(f"{p['name']} {what}: {item['tiers']} 실적 구간이 없음")
                return []
            return [(tid, i, f"_{tid.split('_')[-1]}") for i, tid in enumerate(ids)]

        def per_tier(item, key, i, what):
            vals = item.get(key)
            if vals is None:
                return None
            if i is None or len(vals) != len(tier_ids[item["tiers"]]):
                errs.append(f"{p['name']} {what}: {key} 개수가 실적 구간 수와 다름")
                return None
            return vals[i]

        group_id = {}  # (key, tier_id) → id
        for g in spec["limit_groups"]:
            for tid, i, tail in expand(g, g["key"]):
                gid = f"cblg_{no}_{g['key']}{tail}"
                group_id[(g["key"], tid)] = gid
                limit = per_tier(g, "monthly_limit_by_tier", i, g["key"]) if tid else g.get("monthly_limit")
                groups.append({"id": gid, "card_product_id": p["id"], "tier_id": tid, "name": g["name"],
                               "monthly_limit_amount": limit})

        for j, b in enumerate(spec["benefits"], 1):
            what = f"혜택 {j}"
            unknown = set(b) - BENEFIT_KEYS
            if unknown:
                errs.append(f"{p['name']} {what}: 모르는 칸 {sorted(unknown)}")
            if b["category"] is not None and b["category"] not in code_id:
                errs.append(f"{p['name']} {what}: 업종 {b['category']} 이 없음")
            for tid, i, tail in expand(b, what):
                gkey = b.get("limit_group")
                if gkey and (gkey, tid) not in group_id:
                    errs.append(f"{p['name']} {what}: 통합 한도 {gkey} 가 이 구간에 없음")
                value = per_tier(b, "value_by_tier", i, what) if "value_by_tier" in b else b["value"]
                limit = per_tier(b, "monthly_limit_by_tier", i, what) if "monthly_limit_by_tier" in b else b.get("monthly_limit_amount")
                rows.append({
                    "id": f"cb_{no}_{j:02d}{tail}", "card_product_id": p["id"], "tier_id": tid,
                    "category_id": code_id.get(b["category"]), "benefit_type": b["benefit_type"],
                    "value_type": b["value_type"], "benefit_value": value,
                    "min_payment_amount": b.get("min_payment_amount"), "monthly_limit_amount": limit,
                    "monthly_limit_count": b.get("monthly_limit_count"), "is_instant": False,
                    "description": b.get("description"), "limit_group_id": group_id.get((gkey, tid)) if gkey else None,
                    "merchant_names": b.get("merchant_names"), "payment_channel": b.get("payment_channel"),
                    "pay_methods": b.get("pay_methods"), "days_of_week": b.get("days_of_week"),
                    "time_start": b.get("time_start"), "time_end": b.get("time_end"),
                    "max_eligible_amount": b.get("max_eligible_amount"),
                    "per_payment_max_benefit": b.get("per_payment_max_benefit"),
                    "daily_limit_count": b.get("daily_limit_count"),
                })
    return tiers, groups, rows


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
