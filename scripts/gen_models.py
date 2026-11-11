# 기획서 스키마(docs/sql)로 만든 DB 를 읽어 backend/app/models/*.py (SQLAlchemy 모델)를 만든다.
# docs/sql 이 원본이고, 모델은 그 표를 앱에서 쓰기 위한 매핑이다. 모델 파일은 손으로 고치지 않고 이 스크립트로 다시 만든다.
#
# 실행 (DB 에 docs/sql 이 반영돼 있어야 한다 — docs/sql 을 고쳤다면 backend 에서 docker compose down -v → up -d --wait 먼저):
#   backend/.venv/Scripts/python scripts/gen_models.py          (Windows)
#   backend/.venv/bin/python scripts/gen_models.py              (macOS·Linux)
# 접속: 환경변수 DATABASE_URL (없으면 postgresql+psycopg://app:app@localhost:5433/midproject)
# 검사: backend 에서 pytest tests/test_models_schema.py — 모델과 DB 의 칸·타입·NULL·기본값·키·제약·인덱스 비교
#
# 만드는 규칙
#   - docs/sql 파일 하나 = 모듈 하나 (01_users.sql → users.py ...), 표 순서도 파일 순서 그대로
#   - 표 위의 "-- " 주석 줄 → 클래스 설명, COMMENT ON COLUMN → 칸 끝 주석
#   - CHECK (칸 IN ('A', 'B')) → 클래스 상수 <칸>_VALUES 와 one_of(...) — 앱이 허용 값 목록을 이 상수로 쓴다
#   - 그 밖의 CHECK 는 docs/sql 의 식을 그대로 옮긴다
#   - 기본값은 server_default (DB 가 채움), 칸 이름이 SQLAlchemy 예약어(metadata)면 속성 이름 뒤에 _ 를 붙인다
import os, re, sys

from sqlalchemy import create_engine, inspect

sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949)에서도 한글 그대로
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backend", "app", "models")
URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5433/midproject")
insp = inspect(create_engine(URL))

FILES = [
    ("01_users.sql", "users", "1. 회원·인증"),
    ("02_accounts.sql", "accounts", "2. 계좌"),
    ("03_transactions.sql", "transactions", "3. 거래"),
    ("04_deposite_products.sql", "deposit_products", "4. 예금·적금 상품"),
    ("05_card_products.sql", "card_products", "5. 카드 — 상품·발급·보유"),
    ("06_card_usage.sql", "card_usage", "6. 카드 — 이용·청구·분석·포인트"),
    ("07_notifications.sql", "notifications", "7. 알림"),
]
CLASS = {
    "users": "User", "auth_identities": "AuthIdentity", "local_credentials": "LocalCredential",
    "email_verifications": "EmailVerification", "password_reset_tokens": "PasswordResetToken",
    "sessions": "AuthSession", "pin_credentials": "PinCredential", "auth_audit_logs": "AuthAuditLog",
    "step_up_challenges": "StepUpChallenge", "withdrawal_checks": "WithdrawalCheck",
    "accounts": "Account", "account_activity_logs": "AccountActivityLog",
    "notification_preferences": "NotificationPreference", "account_inactivity": "AccountInactivity",
    "document_issuance_logs": "DocumentIssuanceLog",
    "account_balances": "AccountBalance", "scheduled_transfers": "ScheduledTransfer", "transfers": "Transfer",
    "transactions": "Transaction", "favorite_accounts": "FavoriteAccount", "transfer_limits": "TransferLimit",
    "external_accounts": "ExternalAccount",
    "products": "Product", "product_rates": "ProductRate", "product_rules": "ProductRule",
    "product_documents": "ProductDocument", "subscriptions": "Subscription",
    "subscription_payments": "SubscriptionPayment",
    "card_companies": "CardCompany", "categories": "Category", "card_products": "CardProduct",
    "card_performance_tiers": "CardPerformanceTier", "card_benefit_limit_groups": "CardBenefitLimitGroup",
    "card_benefits": "CardBenefit", "terms": "Terms",
    "user_consents": "UserConsent", "promotions": "Promotion", "card_recommendations": "CardRecommendation",
    "card_recommendation_details": "CardRecommendationDetail", "card_applications": "CardApplication",
    "application_status_histories": "ApplicationStatusHistory",
    "application_term_agreements": "ApplicationTermAgreement", "user_cards": "UserCard",
    "user_card_settings": "UserCardSetting", "user_card_status_histories": "UserCardStatusHistory",
    "card_management_logs": "CardManagementLog", "card_terminations": "CardTermination",
    "merchants": "Merchant", "card_transactions": "CardTransaction", "billing_cycle_rules": "BillingCycleRule",
    "card_bills": "CardBill", "card_bill_items": "CardBillItem", "recurring_payments": "RecurringPayment",
    "spending_forecasts": "SpendingForecast", "daily_card_spending": "DailyCardSpending",
    "card_issuance_rankings": "CardIssuanceRanking", "card_points": "CardPoint",
    "point_cashouts": "PointCashout", "mydata_consents": "MydataConsent", "mydata_sync_logs": "MydataSyncLog",
    "notifications": "Notification",
}
RESERVED_ATTR = {"metadata": "metadata_"}


def parse_sql(path):
    """table order, preceding '-- ' comment lines, CHECK source text by constraint name"""
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    tables, docs = [], {}
    for i, ln in enumerate(lines):
        m = re.match(r"CREATE TABLE (\w+)", ln)
        if m:
            t = m.group(1)
            tables.append(t)
            j, buf = i - 1, []
            while j >= 0 and lines[j].startswith("-- ") and not lines[j].startswith("-- ----"):
                buf.insert(0, lines[j][3:].strip())
                j -= 1
            docs[t] = buf
    checks = {}
    for m in re.finditer(r"CONSTRAINT (\w+) CHECK \((.*?)\)(?:,?\n|\n\);)", text, re.S):
        checks[m.group(1)] = " ".join(m.group(2).split())
    return tables, docs, checks


def type_code(t):
    n = type(t).__name__
    if n == "VARCHAR":
        return f"String({t.length})", "str"
    if n == "CHAR":
        return f"CHAR({t.length})", "str"
    if n == "BIGINT":
        return "BigInteger", "int"
    if n == "INTEGER":
        return "Integer", "int"
    if n == "SMALLINT":
        return "SmallInteger", "int"
    if n == "BOOLEAN":
        return "Boolean", "bool"
    if n == "DATE":
        return "Date", "date"
    if n == "TIMESTAMP":
        assert t.precision == 0, t
        return "TS", "datetime"
    if n == "TIME":
        assert t.precision == 0, t
        return "TM", "time"
    if n == "NUMERIC":
        return f"Numeric({t.precision}, {t.scale})", "Decimal"
    if n == "JSONB":
        return "JSONB", "Any"
    raise ValueError(n)


def default_code(d):
    if d is None:
        return None
    m = re.fullmatch(r"'(.*)'::[\w ]+", d)
    if m:
        return repr(m.group(1)).replace("'", '"')
    if d == "CURRENT_TIMESTAMP":
        return "NOW"
    if d in ("true", "false"):
        return d.upper()
    if re.fullmatch(r"\d+", d):
        return f'text("{d}")'
    raise ValueError(d)


IN_RE = re.compile(r"^\(?\"?(\w+)\"?\)?(?:::text)? = ANY")


def gen_table(t, doc, checks_src):
    cls = CLASS[t]
    cols = insp.get_columns(t)
    pk = insp.get_pk_constraint(t)["constrained_columns"]
    fks = {fk["constrained_columns"][0]: fk for fk in insp.get_foreign_keys(t)}
    uqs = insp.get_unique_constraints(t)
    cks = insp.get_check_constraints(t)
    idxs = [i for i in insp.get_indexes(t) if not i.get("duplicates_constraint")]
    tcomment = insp.get_table_comment(t)["text"]

    out = [f"class {cls}(Base):"]
    docl = doc or [tcomment or t]
    if tcomment and tcomment not in " ".join(docl):
        docl = [f"{tcomment} — " + docl[0]] + docl[1:]
    if len(docl) == 1:
        out.append(f'    """{docl[0]}"""')
    else:
        out.append(f'    """{docl[0]}')
        out.append("")
        for d in docl[1:]:
            out.append(f"    {d}")
        out.append('    """')
    out.append("")
    out.append(f'    __tablename__ = "{t}"')

    # value lists for IN checks
    consts, args = [], []
    for ck in sorted(cks, key=lambda c: c["name"]):
        src = checks_src[ck["name"]]
        m = re.fullmatch(r"(\"?\w+\"?) IN \((.*)\)", src)
        if m:
            col = m.group(1).strip('"')
            vals = re.findall(r"'([^']*)'", m.group(2))
            const = f"{col.upper()}_VALUES"
            consts.append(f"    {const} = ({', '.join(repr(v).replace(chr(39), chr(34)) for v in vals)}{',' if len(vals) == 1 else ''})")
            args.append(f'        one_of("{col}", {const}, "{ck["name"]}"),')
        else:
            args.append(f'        CheckConstraint("{src}", name="{ck["name"]}"),')
    for uq in sorted(uqs, key=lambda u: u["name"]):
        cs = ", ".join(f'"{c}"' for c in uq["column_names"])
        args.append(f'        UniqueConstraint({cs}, name="{uq["name"]}"),')
    for ix in sorted(idxs, key=lambda i: i["name"]):
        cs = ", ".join(f'"{c}"' for c in ix["column_names"])
        args.append(f'        Index("{ix["name"]}", {cs}),')
    if consts:
        out.extend(consts)
    if args:
        out.append("    __table_args__ = (")
        out.extend(args)
        out.append("    )")
    out.append("")

    version_col = None
    for c in cols:
        name = c["name"]
        attr = RESERVED_ATTR.get(name, name)
        tc, py = type_code(c["type"])
        parts = []
        if attr != name:
            parts.append(f'"{name}"')
        parts.append(tc)
        if name in fks:
            fk = fks[name]
            ref = f'"{fk["referred_table"]}.{fk["referred_columns"][0]}"'
            od = fk.get("options", {}).get("ondelete")
            parts.append(f'ForeignKey({ref}, ondelete="{od}")' if od else f"ForeignKey({ref})")
        if name in pk:
            parts.append("primary_key=True")
        d = default_code(c["default"])
        if d:
            parts.append(f"server_default={d}")
        ann = py if not c["nullable"] or name in pk else f"{py} | None"
        line = f"    {attr}: Mapped[{ann}] = mapped_column({', '.join(parts)})"
        if c.get("comment"):
            line += f"  # {c['comment']}"
        out.append(line)
        if name == "version" and t == "accounts":
            version_col = attr
    if version_col:
        out.append("")
        out.append("    # 낙관적 잠금: UPDATE 때마다 version 을 1 올리고, 그 사이 다른 요청이 고쳤으면 실패한다.")
        out.append(f'    __mapper_args__ = {{"version_id_col": {version_col}}}')
    return cls, "\n".join(out)


HEADER = '''"""{title} — docs/sql/{file} 의 표 {n}개.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것 — docs/sql 을 고치고 다시 만든다.
tests/test_models_schema.py 가 DB 와 칸·타입·NULL·기본값·키·제약·인덱스가 같은지 검사한다.
"""
'''

# 보기(view)는 표가 아니므로 ViewBase 에 둔다 → Base.metadata(표 61개)에 섞이지 않는다.
VIEWS = {
    "transactions": '''class AccountBalanceView(ViewBase):
    """잔액 읽기용 보기 account_balance_view — 계좌 파트와 다른 파트는 잔액을 이것으로만 읽는다(기획서 C-5).

    account_balances 를 CODEF 이름으로 보여 준다. 읽기 전용.
    """

    __tablename__ = "account_balance_view"

    account_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    resAccountCurrency: Mapped[str] = mapped_column(CHAR(3))  # = account_balances.currency
    resAccountBalance: Mapped[int] = mapped_column(BigInteger)  # = account_balances.balance
    balance_as_of: Mapped[str] = mapped_column(String(14))  # = account_balances.updated_at, YYYYMMDDHHmmss''',
}

# 모듈 맨 위 import 후보 — 본문에 실제로 나온 이름만 넣는다
IMPORTS = [
    ("from datetime import {}", ["date", "datetime", "time"]),
    ("from decimal import {}", ["Decimal"]),
    ("from typing import {}", ["Any"]),
    ("", None),
    ("from sqlalchemy import {}", ["CHAR", "BigInteger", "Boolean", "CheckConstraint", "Date", "ForeignKey", "Index",
                                   "Integer", "Numeric", "SmallInteger", "String", "UniqueConstraint", "text"]),
    ("from sqlalchemy.dialects.postgresql import {}", ["JSONB"]),
    ("from sqlalchemy.orm import {}", ["Mapped", "mapped_column"]),
    ("", None),
    ("from app.models._base import {}", ["FALSE", "NOW", "TRUE", "TM", "TS", "Base", "ViewBase", "one_of"]),
]


def import_block(body):
    out = []
    for tmpl, names in IMPORTS:
        if names is None:
            if out and out[-1] != "":
                out.append("")
            continue
        used = [n for n in names if re.search(rf"(?<![\w.\"]){re.escape(n)}\b", body)]
        if used:
            out.append(tmpl.format(", ".join(used)))
    return "\n".join(out).strip("\n")


init_lines, all_names, total = [], [], 0
for fname, mod, title in FILES:
    tables, docs, checks_src = parse_sql(os.path.join(ROOT, "docs", "sql", fname))
    codes, names = [], []
    for t in tables:
        cls, code = gen_table(t, docs.get(t), checks_src)
        names.append(cls)
        codes.append(code)
    if mod in VIEWS:
        codes.append(VIEWS[mod])
        names.append(VIEWS[mod].split("(")[0].removeprefix("class "))
    body = "\n\n\n".join(codes)
    src = HEADER.format(title=title, file=fname, n=len(tables)) + "\n" + import_block(body) + "\n\n\n" + body + "\n"
    with open(os.path.join(OUT, mod + ".py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    init_lines.append(f"from app.models.{mod} import (  # docs/sql/{fname}\n" + "".join(f"    {n},\n" for n in names) + ")")
    all_names += names
    total += len(tables)
    print(f"{mod}.py: 표 {len(tables)}")

init = '''"""기획서 스키마(docs/sql/01~07) 표 61개 + 보기 1개의 SQLAlchemy 모델.

scripts/gen_models.py 가 만든 파일이다. 손으로 고치지 말 것.
쓰는 법: from app.models import Account, Transaction ...
"""

from app.models._base import Base, ViewBase
''' + "\n".join(init_lines) + "\n\n__all__ = [\n    \"Base\",\n    \"ViewBase\",\n" + "".join(f'    "{n}",\n' for n in all_names) + "]\n"
with open(os.path.join(OUT, "__init__.py"), "w", encoding="utf-8", newline="\n") as f:
    f.write(init)
print(f"합계: 표 {total}")
