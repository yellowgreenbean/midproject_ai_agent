"""두린은행 계좌·거래·상품·카드 서비스 - 목(mock) 데이터 생성기

docs/schema.sql 로 만든 DB에 넣을 INSERT 문(docs/seed.sql)을 만듭니다.

    py scripts/generate_seed.py                 # 회원 300명, seed 42
    py scripts/generate_seed.py --users 100     # 회원 수 조절
    py scripts/generate_seed.py --seed 7        # 다른 데이터 (같은 seed면 항상 같은 결과)

- 기준 시각(NOW)은 2026-11-03 09:00, 카드 이용 내역·계좌 거래는 2026-05-01부터 만듭니다.
- 카드 상품명과 혜택, 예금·적금 상품은 실제 상품을 참고한 가상 데이터입니다.
- ID는 문자열(user_001, tx_0001 ...), 금액은 원 단위 정수, 시각은 +09:00 입니다 (ERD 이름 규칙 C-5).
- 계좌 잔액(account_balances)은 거래 원장(transactions)을 시간순으로 쌓은 결과와 맞춥니다.
- 비밀번호·PIN·토큰은 실제 값이 아닌 가짜 해시입니다.
- 표준 라이브러리만 사용합니다 (Python 3.8+).
"""
import argparse
import calendar
import hashlib
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

NOW = datetime(2026, 11, 3, 9, 0, 0)
TODAY = NOW.date()
TX_START = date(2026, 5, 1)
APP_START = date(2025, 11, 1)
FX = {"USD": 1380, "JPY": 9.2}
PAYMENT_DAYS = [1, 5, 10, 14, 15, 17, 21, 23, 25, 27]
COUNTED_APP_STATUSES = ("APPROVED", "SHIPPING", "DELIVERED", "ACTIVATED")
ONLINE_CATEGORIES = {"ONLINE_SHOPPING", "OTT", "DELIVERY"}
PARTIAL_CANCEL_CATEGORIES = {"ONLINE_SHOPPING", "DEPT_STORE", "MART"}
# 2026년 공휴일 (이용 내역 기간 안, 대체공휴일 포함)
HOLIDAYS = {date(2026, 5, 5), date(2026, 5, 24), date(2026, 5, 25), date(2026, 6, 3), date(2026, 6, 6),
            date(2026, 8, 15), date(2026, 8, 17), date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26),
            date(2026, 10, 3), date(2026, 10, 5), date(2026, 10, 9)}

# INSERT 순서 = FK 의존 순서 (docs/schema.sql 과 같은 순서, card_applications 보다 추천이 먼저)
TABLE_ORDER = [
    # 1. 회원·인증
    "users", "auth_identities", "local_credentials", "email_verifications", "password_reset_tokens",
    "sessions", "pin_credentials", "auth_audit_logs", "step_up_challenges", "withdrawal_checks",
    # 2. 계좌
    "accounts", "account_activity_logs", "notification_preferences", "account_inactivity",
    "document_issuance_logs",
    # 3. 거래
    "account_balances", "scheduled_transfers", "transfers", "transactions", "favorite_accounts",
    "transfer_limits", "external_accounts",
    # 4. 예금·적금 상품
    "products", "product_rates", "product_rules", "product_documents", "subscriptions", "subscription_payments",
    # 5. 카드 — 상품·발급·보유
    "card_companies", "categories", "card_products", "card_performance_tiers", "card_benefits",
    "terms", "user_consents", "promotions", "card_recommendations", "card_recommendation_details",
    "card_applications", "application_status_histories", "application_term_agreements",
    "user_cards", "user_card_settings", "user_card_status_histories", "card_management_logs",
    "card_terminations",
    # 6. 카드 — 이용·청구·분석·포인트
    "merchants", "card_transactions", "billing_cycle_rules", "card_bills", "card_bill_items",
    "recurring_payments", "spending_forecasts", "daily_card_spending", "card_issuance_rankings",
    "card_points", "point_cashouts", "mydata_consents", "mydata_sync_logs",
    # 7. 알림
    "notifications",
]

# 문자열 ID 접두어 (ERD 예: user_001, prod_001, sub_001 은 3자리, 나머지는 4자리부터)
ID_PREFIX = {
    "users": ("user", 3), "auth_identities": ("aid", 4), "email_verifications": ("ev", 4),
    "password_reset_tokens": ("prt", 4), "sessions": ("ses", 4), "auth_audit_logs": ("aal", 4),
    "step_up_challenges": ("stp", 4), "withdrawal_checks": ("wdc", 4),
    "accounts": ("acc", 4), "account_activity_logs": ("acl", 4), "document_issuance_logs": ("doc", 4),
    "scheduled_transfers": ("sch", 4), "transfers": ("trf", 4), "transactions": ("tx", 4),
    "favorite_accounts": ("fav", 4), "external_accounts": ("ext", 4),
    "products": ("prod", 3), "product_rates": ("rate", 4), "product_rules": ("rule", 4),
    "product_documents": ("pdoc", 4), "subscriptions": ("sub", 3), "subscription_payments": ("spay", 4),
    "card_companies": ("cco", 3), "categories": ("cat", 3), "card_products": ("cprod", 3),
    "card_performance_tiers": ("tier", 3), "card_benefits": ("ben", 3), "terms": ("term", 3),
    "user_consents": ("ucon", 4), "promotions": ("promo", 3), "card_recommendations": ("rec", 4),
    "card_applications": ("app", 4), "application_status_histories": ("apph", 4), "user_cards": ("card", 4),
    "user_card_status_histories": ("cardh", 4), "card_management_logs": ("cml", 4),
    "card_terminations": ("cterm", 4), "merchants": ("mer", 3), "card_transactions": ("ctx", 4),
    "card_bills": ("bill", 4), "card_bill_items": ("bitem", 4), "recurring_payments": ("rcp", 4),
    "spending_forecasts": ("fcst", 4), "card_issuance_rankings": ("rank", 4), "card_points": ("cpt", 4),
    "point_cashouts": ("pco", 4), "mydata_consents": ("mdc", 4), "mydata_sync_logs": ("mds", 4),
    "notifications": ("ntf", 4),
}
BANK_NAME = "두린은행"
STEP_UP_ACTIONS = {"APPLICATION": "CARD_APPLICATION", "TERMINATION": "CARD_TERMINATION",
                   "CARD_MANAGEMENT": "CARD_MANAGEMENT"}

# ---------------------------------------------------------------------------
# 기준 데이터
# ---------------------------------------------------------------------------

COMPANIES = [  # code, name, 카드번호 앞 4자리(가상), 포인트 이름
    ("SHINHAN", "신한카드", "4518", "마이신한포인트"), ("SAMSUNG", "삼성카드", "5310", "삼성카드 포인트"),
    ("HYUNDAI", "현대카드", "5433", "M포인트"), ("KB", "KB국민카드", "4579", "포인트리"),
    ("LOTTE", "롯데카드", "5326", "L.POINT"), ("WOORI", "우리카드", "5365", "우리카드 포인트"),
    ("HANA", "하나카드", "4119", "하나머니"), ("BC", "BC카드", "9490", "TOP포인트"),
    ("NH", "NH농협카드", "5461", "NH포인트"), ("TOSSBANK", "토스뱅크", "5101", None),
]

CATEGORIES = [  # code, name, parent code
    ("ALL", "전체 가맹점", None),
    ("TRANSPORT", "교통", None),
    ("PUBLIC_TRANSIT", "대중교통", "TRANSPORT"), ("TAXI", "택시", "TRANSPORT"), ("FUEL", "주유", "TRANSPORT"),
    ("LIVING", "생활", None),
    ("CONVENIENCE", "편의점", "LIVING"), ("MART", "대형마트", "LIVING"), ("DELIVERY", "배달앱", "LIVING"),
    ("FOOD", "식음료", None),
    ("CAFE", "카페", "FOOD"), ("RESTAURANT", "음식점", "FOOD"), ("FASTFOOD", "패스트푸드", "FOOD"),
    ("SHOPPING", "쇼핑", None),
    ("ONLINE_SHOPPING", "온라인쇼핑", "SHOPPING"), ("DEPT_STORE", "백화점·전자제품", "SHOPPING"),
    ("TELECOM", "통신", None),
    ("SUBSCRIPTION", "구독", None), ("OTT", "OTT·디지털구독", "SUBSCRIPTION"),
    ("MEDICAL", "병원·약국", None),
    ("EDUCATION", "교육·도서", None),
    ("TRAVEL", "여행", None),
    ("AIRLINE", "항공", "TRAVEL"), ("HOTEL", "숙박", "TRAVEL"), ("OVERSEAS", "해외결제", "TRAVEL"),
    ("TAX", "세금·공과금", None),
    ("ETC", "기타", None),
]

# name, category, 최소 금액, 최대 금액, kind
#   kind: var = 일반 소비, big = 고액(할부) 구매, telecom/sub/utility = 정기결제
#   해외 가맹점은 금액이 현지 통화 기준 (MERCHANT_CURRENCY)
MERCHANTS = [
    ("서울교통공사", "PUBLIC_TRANSIT", 1400, 3200, "var"), ("티머니 버스", "PUBLIC_TRANSIT", 1500, 3000, "var"),
    ("카카오T 택시", "TAXI", 5800, 28000, "var"), ("우티 택시", "TAXI", 6000, 25000, "var"),
    ("SK에너지 주유소", "FUEL", 40000, 90000, "var"), ("GS칼텍스 주유소", "FUEL", 40000, 90000, "var"),
    ("S-OIL 주유소", "FUEL", 40000, 90000, "var"),
    ("GS25", "CONVENIENCE", 1200, 15000, "var"), ("CU", "CONVENIENCE", 1200, 15000, "var"),
    ("세븐일레븐", "CONVENIENCE", 1200, 13000, "var"), ("이마트24", "CONVENIENCE", 1200, 12000, "var"),
    ("이마트", "MART", 25000, 180000, "var"), ("홈플러스", "MART", 25000, 160000, "var"),
    ("롯데마트", "MART", 25000, 160000, "var"), ("코스트코", "MART", 60000, 300000, "var"),
    ("배달의민족", "DELIVERY", 14000, 38000, "var"), ("쿠팡이츠", "DELIVERY", 14000, 38000, "var"),
    ("요기요", "DELIVERY", 14000, 35000, "var"),
    ("스타벅스", "CAFE", 4500, 12000, "var"), ("이디야커피", "CAFE", 3200, 9000, "var"),
    ("메가MGC커피", "CAFE", 2000, 6000, "var"), ("투썸플레이스", "CAFE", 5000, 15000, "var"),
    ("컴포즈커피", "CAFE", 1800, 5000, "var"),
    ("한솥도시락", "RESTAURANT", 5000, 12000, "var"), ("본죽", "RESTAURANT", 9000, 16000, "var"),
    ("김밥천국", "RESTAURANT", 4000, 12000, "var"), ("명륜진사갈비", "RESTAURANT", 20000, 80000, "var"),
    ("아웃백스테이크하우스", "RESTAURANT", 40000, 120000, "var"), ("역전우동", "RESTAURANT", 6000, 12000, "var"),
    ("맥도날드", "FASTFOOD", 5500, 16000, "var"), ("버거킹", "FASTFOOD", 6000, 16000, "var"),
    ("롯데리아", "FASTFOOD", 5000, 14000, "var"), ("맘스터치", "FASTFOOD", 5000, 14000, "var"),
    ("쿠팡", "ONLINE_SHOPPING", 9000, 120000, "var"), ("11번가", "ONLINE_SHOPPING", 10000, 100000, "var"),
    ("G마켓", "ONLINE_SHOPPING", 10000, 100000, "var"), ("무신사", "ONLINE_SHOPPING", 20000, 150000, "var"),
    ("네이버쇼핑", "ONLINE_SHOPPING", 8000, 100000, "var"),
    ("신세계백화점", "DEPT_STORE", 40000, 400000, "var"), ("현대백화점", "DEPT_STORE", 40000, 400000, "var"),
    ("롯데백화점", "DEPT_STORE", 40000, 400000, "var"),
    ("롯데하이마트", "DEPT_STORE", 300000, 1800000, "big"), ("Apple Store 가로수길", "DEPT_STORE", 400000, 2500000, "big"),
    ("SKT", "TELECOM", 0, 0, "telecom"), ("KT", "TELECOM", 0, 0, "telecom"), ("LG U+", "TELECOM", 0, 0, "telecom"),
    ("넷플릭스", "OTT", 0, 0, "sub"), ("유튜브 프리미엄", "OTT", 0, 0, "sub"),
    ("티빙", "OTT", 0, 0, "sub"), ("디즈니+", "OTT", 0, 0, "sub"),
    ("쿠팡 와우 멤버십", "ONLINE_SHOPPING", 0, 0, "sub"),
    ("연세맑은내과의원", "MEDICAL", 5000, 30000, "var"), ("온누리약국", "MEDICAL", 3000, 25000, "var"),
    ("서울튼튼치과", "MEDICAL", 20000, 150000, "var"),
    ("클래스101", "EDUCATION", 19000, 150000, "var"), ("해커스어학원", "EDUCATION", 99000, 350000, "var"),
    ("교보문고", "EDUCATION", 12000, 50000, "var"),
    ("대한항공", "AIRLINE", 90000, 900000, "var"), ("아시아나항공", "AIRLINE", 90000, 800000, "var"),
    ("제주항공", "AIRLINE", 40000, 250000, "var"),
    ("야놀자", "HOTEL", 50000, 250000, "var"), ("여기어때", "HOTEL", 50000, 250000, "var"),
    ("AMAZON.COM", "OVERSEAS", 15, 150, "var"), ("APPLE.COM/BILL", "OVERSEAS", 1, 10, "var"),
    ("UNIQLO SHINJUKU", "OVERSEAS", 2000, 15000, "var"), ("FAMILYMART TOKYO", "OVERSEAS", 300, 2500, "var"),
    ("STARBUCKS TOKYO", "OVERSEAS", 500, 1500, "var"),
    ("한국전력공사", "TAX", 25000, 90000, "utility"), ("서울시 지방세", "TAX", 50000, 400000, "var"),
    ("다이소", "ETC", 2000, 25000, "var"), ("올리브영", "ETC", 8000, 60000, "var"),
    ("CGV", "ETC", 13000, 35000, "var"),
]
MERCHANT_CURRENCY = {"AMAZON.COM": "USD", "APPLE.COM/BILL": "USD", "UNIQLO SHINJUKU": "JPY",
                     "FAMILYMART TOKYO": "JPY", "STARBUCKS TOKYO": "JPY"}
SUB_PLANS = {"넷플릭스": [7000, 13500, 17000], "유튜브 프리미엄": [14900], "티빙": [10900, 13900],
             "디즈니+": [9900, 13900], "쿠팡 와우 멤버십": [7890]}
OTT_NAMES = ["넷플릭스", "유튜브 프리미엄", "티빙", "디즈니+"]

# 카테고리별 소비 비중 (사람마다 무작위로 흔들어서 씀)
ADULT_WEIGHTS = {
    "PUBLIC_TRANSIT": 18, "CONVENIENCE": 16, "CAFE": 14, "RESTAURANT": 12, "DELIVERY": 8,
    "ONLINE_SHOPPING": 8, "FASTFOOD": 6, "ETC": 6, "MART": 5, "TAXI": 4, "MEDICAL": 2,
    "DEPT_STORE": 1.5, "EDUCATION": 1, "FUEL": 0, "OVERSEAS": 0.3, "HOTEL": 0.4, "AIRLINE": 0.3, "TAX": 0.3,
}
YOUTH_WEIGHTS = {"PUBLIC_TRANSIT": 25, "CONVENIENCE": 25, "FASTFOOD": 12, "CAFE": 10, "ETC": 10,
                 "ONLINE_SHOPPING": 4, "EDUCATION": 2}
HOURS = {"PUBLIC_TRANSIT": (7, 23), "CAFE": (8, 20), "RESTAURANT": (11, 22), "FASTFOOD": (11, 22),
         "DELIVERY": (17, 24), "CONVENIENCE": (7, 24)}


def B(cat, value, vtype="PERCENT", btype="DISCOUNT", min_pay=None, amt=None, cnt=None, tier=None, instant=False):
    """혜택 규칙 한 줄. tier=None 이면 실적 조건 없음."""
    return dict(cat=cat, value=value, vtype=vtype, btype=btype, min_pay=min_pay, amt=amt, cnt=cnt,
                tier=tier, instant=instant)


PRODUCTS = [
    dict(company="TOSSBANK", name="토스뱅크 체크카드", type="CHECK", brand="MASTER", fee=(0, 0), min_age=14, pop=10,
         released="2022-03-01", summary="대중교통·편의점·카페·패스트푸드 즉시 캐시백", tiers=[],
         benefits=[B("PUBLIC_TRANSIT", 100, "FIXED", "CASHBACK", cnt=30, instant=True),
                   B("CONVENIENCE", 300, "FIXED", "CASHBACK", min_pay=3000, cnt=10, instant=True),
                   B("CAFE", 300, "FIXED", "CASHBACK", min_pay=3000, cnt=10, instant=True),
                   B("FASTFOOD", 300, "FIXED", "CASHBACK", min_pay=3000, cnt=10, instant=True),
                   B("TAXI", 300, "FIXED", "CASHBACK", min_pay=5000, cnt=10, instant=True),
                   B("OVERSEAS", 3, btype="CASHBACK", amt=30000, instant=True)]),
    dict(company="TOSSBANK", name="토스 유스카드", type="CHECK", brand="MASTER", fee=(0, 0), min_age=12, pop=3,
         released="2021-10-01", summary="청소년 전용, 편의점·대중교통 캐시백", tiers=[],
         benefits=[B("CONVENIENCE", 100, "FIXED", "CASHBACK", min_pay=1000, cnt=20, instant=True),
                   B("PUBLIC_TRANSIT", 50, "FIXED", "CASHBACK", cnt=40, instant=True)]),
    dict(company="SHINHAN", name="신한 Daily Plus", type="CREDIT", brand="VISA", fee=(15000, 18000), min_age=19, pop=6,
         released="2024-04-01", summary="편의점·카페·대중교통 10% 할인", tiers=[300000, 700000],
         benefits=[B("CONVENIENCE", 10, amt=5000, tier=1), B("CONVENIENCE", 10, amt=10000, tier=2),
                   B("CAFE", 10, amt=5000, tier=1), B("CAFE", 10, amt=10000, tier=2),
                   B("PUBLIC_TRANSIT", 10, amt=5000, tier=1), B("PUBLIC_TRANSIT", 10, amt=8000, tier=2)]),
    dict(company="SHINHAN", name="신한 Deep Check", type="CHECK", brand="MASTER", fee=(0, 0), min_age=14, pop=5,
         released="2023-02-01", summary="배달앱·OTT·카페 캐시백", tiers=[200000],
         benefits=[B("DELIVERY", 5, btype="CASHBACK", min_pay=10000, amt=5000, tier=1),
                   B("OTT", 20, btype="CASHBACK", amt=3000, tier=1),
                   B("CAFE", 5, btype="CASHBACK", amt=3000, tier=1)]),
    dict(company="SAMSUNG", name="삼성 iD ON", type="CREDIT", brand="VISA", fee=(20000, 23000), min_age=19, pop=7,
         released="2024-09-01", summary="온라인쇼핑·배달앱 7% 할인", tiers=[400000, 800000],
         benefits=[B("ONLINE_SHOPPING", 7, min_pay=10000, amt=10000, tier=1),
                   B("ONLINE_SHOPPING", 7, min_pay=10000, amt=20000, tier=2),
                   B("DELIVERY", 7, amt=5000, tier=1), B("DELIVERY", 7, amt=10000, tier=2),
                   B("OTT", 7, amt=3000, tier=1)]),
    dict(company="SAMSUNG", name="삼성 taptap S", type="CREDIT", brand="MASTER", fee=(10000, 10000), min_age=19, pop=6,
         released="2022-06-01", summary="통신·대중교통 10%, 카페 50% 할인", tiers=[300000],
         benefits=[B("TELECOM", 10, amt=5000, tier=1), B("PUBLIC_TRANSIT", 10, amt=5000, tier=1),
                   B("CAFE", 50, min_pay=5000, amt=3000, tier=1)]),
    dict(company="HYUNDAI", name="현대 Zero Plus", type="CREDIT", brand="MASTER", fee=(10000, 10000), min_age=19, pop=9,
         released="2023-05-01", summary="실적 조건 없이 모든 가맹점 0.8%, 생활 영역 1.6% 할인", tiers=[],
         benefits=[B("ALL", 0.8), B("CONVENIENCE", 1.6), B("CAFE", 1.6), B("DELIVERY", 1.6),
                   B("PUBLIC_TRANSIT", 1.6)]),
    dict(company="HYUNDAI", name="현대 M Boost", type="CREDIT", brand="VISA", fee=(30000, 30000), min_age=19, pop=4,
         released="2024-01-01", summary="모든 가맹점 M포인트 최대 1.5% 적립", tiers=[500000],
         benefits=[B("ALL", 0.5, btype="POINT"), B("ALL", 1.5, btype="POINT", amt=50000, tier=1)]),
    dict(company="KB", name="KB 노리 Life", type="CREDIT", brand="VISA", fee=(12000, 15000), min_age=19, pop=5,
         released="2023-08-01", summary="OTT 30%, 카페 20%, 대중교통 10% 할인", tiers=[300000],
         benefits=[B("OTT", 30, amt=5000, tier=1), B("PUBLIC_TRANSIT", 10, amt=5000, tier=1),
                   B("CAFE", 20, amt=5000, tier=1), B("FASTFOOD", 10, amt=3000, tier=1)]),
    dict(company="KB", name="KB 청춘 Check", type="CHECK", brand="MASTER", fee=(0, 0), min_age=14, pop=4,
         released="2022-02-01", summary="실적 없이 카페·편의점 5% 캐시백", tiers=[],
         benefits=[B("CAFE", 5, btype="CASHBACK", amt=3000), B("CONVENIENCE", 5, btype="CASHBACK", amt=3000),
                   B("OTT", 10, btype="CASHBACK", amt=2000)]),
    dict(company="LOTTE", name="롯데 LOCA Mart", type="CREDIT", brand="VISA", fee=(15000, 18000), min_age=19, pop=3,
         released="2023-11-01", summary="대형마트·백화점 5% 할인", tiers=[500000],
         benefits=[B("MART", 5, min_pay=30000, amt=15000, tier=1), B("ONLINE_SHOPPING", 3, amt=7000, tier=1),
                   B("DEPT_STORE", 5, amt=10000, tier=1)]),
    dict(company="WOORI", name="우리 정석 Point", type="CREDIT", brand="MASTER", fee=(12000, 15000), min_age=19, pop=4,
         released="2022-09-01", summary="모든 가맹점 0.7% 포인트, 주유 5% 할인", tiers=[300000],
         benefits=[B("ALL", 0.7, btype="POINT"), B("FUEL", 5, amt=10000, tier=1),
                   B("RESTAURANT", 2, btype="POINT", amt=10000, tier=1)]),
    dict(company="HANA", name="하나 트래블GO", type="CHECK", brand="VISA", fee=(0, 0), min_age=14, pop=7,
         released="2024-07-01", summary="해외결제 2% 캐시백, 항공·숙박 3% 할인", tiers=[],
         benefits=[B("OVERSEAS", 2, btype="CASHBACK", amt=30000), B("AIRLINE", 3, amt=20000),
                   B("HOTEL", 3, amt=20000)]),
    dict(company="HANA", name="하나 원큐 Daily", type="CREDIT", brand="VISA", fee=(15000, 18000), min_age=19, pop=4,
         released="2023-03-01", summary="배달앱·편의점 10% 할인, 통신비 월 최대 5천원", tiers=[300000, 600000],
         benefits=[B("DELIVERY", 10, min_pay=15000, amt=5000, tier=1), B("DELIVERY", 10, min_pay=15000, amt=10000, tier=2),
                   B("CONVENIENCE", 10, amt=5000, tier=1), B("CONVENIENCE", 10, amt=8000, tier=2),
                   B("TELECOM", 3000, "FIXED", min_pay=30000, amt=3000, cnt=1, tier=1),
                   B("TELECOM", 5000, "FIXED", min_pay=30000, amt=5000, cnt=1, tier=2)]),
    dict(company="BC", name="BC 바로 Plus", type="CREDIT", brand="LOCAL", fee=(5000, 0), min_age=19, pop=3,
         released="2022-12-01", summary="국내 전용, 모든 가맹점 0.7% 할인", tiers=[],
         benefits=[B("ALL", 0.7)]),
    dict(company="NH", name="NH 올바른 Flex", type="CREDIT", brand="VISA", fee=(10000, 12000), min_age=19, pop=2,
         released="2023-06-01", summary="주유 7%, 마트 5%, 병원 10% 할인", tiers=[300000],
         benefits=[B("FUEL", 7, amt=10000, tier=1), B("MART", 5, amt=10000, tier=1),
                   B("MEDICAL", 10, amt=5000, tier=1)]),
    dict(company="SAMSUNG", name="삼성 Global Mile", type="CREDIT", brand="VISA", fee=(49000, 49000), min_age=19, pop=2,
         released="2021-05-01", summary="모든 가맹점 마일리지 적립, 항공 3%", tiers=[],
         benefits=[B("ALL", 1.0, btype="MILEAGE"), B("AIRLINE", 3, btype="MILEAGE"),
                   B("OVERSEAS", 2, btype="MILEAGE")]),
    dict(company="SHINHAN", name="신한 SOL Travel Check", type="CHECK", brand="MASTER", fee=(0, 0), min_age=14, pop=5,
         released="2024-02-01", summary="해외결제 3% 캐시백, 숙박 5% 할인", tiers=[],
         benefits=[B("OVERSEAS", 3, btype="CASHBACK", amt=20000), B("HOTEL", 5, amt=10000)]),
    dict(company="HYUNDAI", name="현대 Digital Lover", type="CREDIT", brand="MASTER", fee=(15000, 15000), min_age=19, pop=3,
         released="2022-04-01", summary="OTT 50%, 배달앱 10% 할인", tiers=[300000],
         benefits=[B("OTT", 50, amt=10000, tier=1), B("DELIVERY", 10, amt=5000, tier=1),
                   B("ONLINE_SHOPPING", 5, amt=5000, tier=1)]),
    dict(company="LOTTE", name="롯데 Like Cafe", type="CHECK", brand="MASTER", fee=(0, 0), min_age=14, pop=2,
         released="2023-01-01", summary="카페 20% 캐시백", tiers=[200000],
         benefits=[B("CAFE", 20, btype="CASHBACK", amt=5000, tier=1), B("FASTFOOD", 10, btype="CASHBACK", amt=3000, tier=1)]),
    dict(company="WOORI", name="우리 Edu Plus", type="CREDIT", brand="VISA", fee=(10000, 12000), min_age=19, pop=1,
         released="2022-01-01", summary="교육·도서 10% 할인", tiers=[300000],
         benefits=[B("EDUCATION", 10, amt=20000, tier=1), B("MEDICAL", 5, amt=5000, tier=1)]),
    dict(company="KB", name="KB 헬스케어 Care", type="CREDIT", brand="VISA", fee=(10000, 12000), min_age=19, pop=1,
         released="2020-03-01", summary="병원·약국 10% 할인 (단종)", tiers=[300000], active=False,
         benefits=[B("MEDICAL", 10, amt=10000, tier=1), B("MART", 3, amt=5000, tier=1)]),
    dict(company="NH", name="NH 농협 Daily Check", type="CHECK", brand="LOCAL", fee=(0, 0), min_age=14, pop=2,
         released="2021-07-01", summary="국내 전용, 마트·편의점 2% 캐시백", tiers=[],
         benefits=[B("MART", 2, btype="CASHBACK", amt=5000), B("CONVENIENCE", 2, btype="CASHBACK", amt=2000)]),
]

PROMOTIONS = [  # 상품명, 제목, 리워드, 조건 금액, 시작, 종료
    ("하나 원큐 Daily", "토스에서 발급하면 최대 13만원 돌려드려요", 130000, 300000, "2026-07-01", "2026-08-31"),
    ("하나 트래블GO", "해외여행 전 발급하면 2만원 캐시백", 20000, 50000, "2026-06-01", "2026-08-31"),
    ("신한 Daily Plus", "발급 후 30만원 이상 쓰면 10만원", 100000, 300000, "2026-08-01", "2026-09-30"),
    ("현대 Zero Plus", "토스에서 발급하면 최대 15만원", 150000, 300000, "2026-09-01", "2026-11-30"),
    ("KB 노리 Life", "가을맞이 8만원 캐시백", 80000, 200000, "2026-09-15", "2026-10-31"),
    ("삼성 iD ON", "연말까지 발급하면 12만원", 120000, 400000, "2026-10-01", "2026-12-31"),
]

SURNAMES = "김이박최정강조윤장임한오서신권황안송류홍"
GIVEN_NAMES = ["민준", "서연", "도윤", "서윤", "시우", "지우", "하준", "하윤", "지호", "지민", "준서", "수아",
               "예준", "지유", "건우", "채원", "현우", "다은", "우진", "예린", "선우", "유진", "민재", "소율",
               "태윤", "가은", "은우", "하린", "정우", "윤서"]
STREETS = ["강남구 테헤란로", "마포구 월드컵북로", "송파구 올림픽로", "서초구 반포대로", "관악구 관악로",
           "성동구 왕십리로", "영등포구 여의대로", "노원구 동일로"]
BANKS = ["국민은행", "신한은행", "우리은행", "하나은행", "카카오뱅크", "NH농협은행"]
JOBS = ["직장인", "자영업", "프리랜서", "공무원"]
PAYDAYS = [10, 15, 20, 21, 25, 25, 25, 31]
REJECT_REASONS = ["NO_INCOME", "DUPLICATE"]   # AGE 는 신청 단계에서 이미 걸러짐
EMPLOYERS = ["(주)한빛소프트", "(주)새솔물산", "누리식품(주)", "(주)온다랩", "바른회계법인", "(주)다온건설",
             "서울특별시청", "(주)미르전자"]
TRANSFER_FAILURES = ["RECIPIENT_ACCOUNT_SUSPENDED", "BANK_MAINTENANCE", "DAILY_LIMIT_EXCEEDED"]
AUTO_TRANSFER_PURPOSES = ["월세", "관리비", "부모님 용돈", "모임 회비", "보험료"]

# 예금·적금 상품 (상품 기획안 6장). 금리는 연 % 문자열
BANK_PRODUCTS = [
    dict(name="두린 정기예금", type="TIME_DEPOSIT", status="ON_SALE",
         description="목돈을 한 번에 맡기고 만기에 이자와 함께 돌려받는 예금",
         rates=[(1, 5, "2.80", None), (6, 11, "3.10", "0.20"), (12, 23, "3.30", "0.20"), (24, 36, "3.00", None)],
         rule=dict(min_amount=1_000_000, max_amount=100_000_000, min_months=1, max_months=36, max_per_user=3)),
    dict(name="두린 자유적금", type="INSTALLMENT_SAVINGS", status="ON_SALE",
         description="매달 정한 날 자동으로 모으는 적금",
         rates=[(6, 11, "3.20", "0.30"), (12, 23, "3.50", "0.50"), (24, 36, "3.40", "0.30")],
         rule=dict(min_amount=10_000, max_amount=1_000_000, min_months=6, max_months=36, max_per_user=2)),
    dict(name="두린 청년도약적금", type="INSTALLMENT_SAVINGS", status="ON_SALE",
         description="만 19~34세 청년 전용 고금리 적금",
         rates=[(12, 12, "4.50", "1.00"), (24, 24, "4.80", "1.00")],
         rule=dict(min_amount=10_000, max_amount=500_000, min_months=12, max_months=24, max_per_user=1,
                   rules_json='{"age_min": 19, "age_max": 34}')),
    dict(name="두린 회전정기예금", type="TIME_DEPOSIT", status="STOPPED",
         description="1년마다 금리가 바뀌는 회전식 예금 (판매 중지)",
         rates=[(12, 36, "2.90", None)],
         rule=dict(min_amount=3_000_000, max_amount=50_000_000, min_months=12, max_months=36, max_per_user=1)),
]
NICKNAMES = ["생활비 카드", "주유 전용", "구독 결제용", "회사 점심", "여행용"]
SYNC_ERRORS = ["카드사 API 응답 시간 초과", "토큰 만료 (401)", "요청 한도 초과 (429)"]
APP_MEMO = {"APPLIED": "신청 접수", "REVIEWING": "카드사 심사 중", "APPROVED": "발급 승인",
            "REJECTED": "발급 거절", "SHIPPING": "카드 배송 시작", "DELIVERED": "배송 완료",
            "ACTIVATED": "카드 등록 완료", "CANCELED": "고객 신청 취소"}
APP_NOTICE = {"APPROVED": "카드 발급이 승인됐어요", "SHIPPING": "카드가 배송을 시작했어요",
              "DELIVERED": "카드가 도착했어요. 등록하고 바로 써 보세요", "ACTIVATED": "카드 등록이 끝났어요",
              "REJECTED": "카드 발급이 어려워요"}
CARD_STATUS_NOTICE = {"LOST": "분실 신고가 접수됐어요. 새 카드를 보내드릴게요", "SUSPENDED": "카드 사용을 잠시 멈췄어요",
                      "TERMINATED": "카드 해지가 끝났어요", "EXPIRED": "유효기간이 끝나 새 카드로 바뀌었어요"}
TERMINATION_REASONS = {"LOW_BENEFIT": "혜택이 생각보다 적어요", "HIGH_FEE": "연회비가 부담돼요",
                       "NOT_USING": "거의 안 써요", "SWITCH_CARD": "다른 카드로 바꿨어요", "OTHER": None}
BENEFIT_WORD = {"DISCOUNT": "할인", "CASHBACK": "캐시백", "POINT": "포인트 적립", "MILEAGE": "마일리지 적립",
                "FEE_WAIVER": "수수료 면제"}


# ---------------------------------------------------------------------------
# 날짜 계산
# ---------------------------------------------------------------------------

def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def month_end(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def day_of(month_first, day):
    """해당 월의 day 일. 99 또는 말일보다 큰 값이면 말일."""
    return month_first.replace(day=min(day, calendar.monthrange(month_first.year, month_first.month)[1]))


def default_cycle_rule(payment_day):
    """(start_month_offset, start_day, end_month_offset, end_day). 결제일 14일 = 전월 1일 ~ 전월 말일."""
    if payment_day <= 10:
        return -2, payment_day + 17, -1, payment_day + 16
    if payment_day == 14:
        return -1, 1, -1, 99
    return -1, payment_day - 13, 0, payment_day - 14


def usage_period(p, rule):
    """결제일 p 의 이용 기간 (시작일, 끝일)."""
    so, sd, eo, ed = rule
    first = p.replace(day=1)
    return day_of(add_months(first, so), sd), day_of(add_months(first, eo), ed)


def payment_date_for(d, payment_day, rule):
    """이용일 d 가 청구되는 결제일."""
    first = d.replace(day=1)
    for k in range(4):
        p = add_months(first, k).replace(day=payment_day)
        s, e = usage_period(p, rule)
        if s <= d <= e:
            return p
    raise ValueError(f"no billing cycle for {d} (payment day {payment_day})")


def anniversary_after(issued, d, inclusive=False):
    """d 이후 첫 발급 기념일 (연회비 청구일)."""
    a = issued.replace(year=d.year, day=min(issued.day, 28))
    if a < d or (a == d and not inclusive):
        a = a.replace(year=a.year + 1)
    return a


def age_on(birth, d):
    return d.year - birth.year - ((d.month, d.day) < (birth.month, birth.day))


def age_group(age):
    return "10s" if age < 20 else "50s+" if age >= 50 else f"{age // 10 * 10}s"


def round10(x):
    return int(x) // 10 * 10


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def ymd(d):
    return f"{d:%Y%m%d}"


def ymdhms(dt):
    return f"{dt:%Y%m%d%H%M%S}"


def describe(b, cat_name):
    value = f"{b['value']:g}%" if b["vtype"] == "PERCENT" else f"건당 {b['value']:,}원"
    text = f"{cat_name} {value} {BENEFIT_WORD[b['btype']]}"
    limits = []
    if b["amt"]:
        limits.append(f"월 {b['amt']:,}원")
    if b["cnt"]:
        limits.append(f"월 {b['cnt']}회")
    return text + (f" ({', '.join(limits)} 한도)" if limits else "")


def sql_value(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, datetime):
        return f"'{v:%Y-%m-%d %H:%M:%S}'"
    if isinstance(v, date):
        return f"'{v:%Y-%m-%d}'"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# 생성기
# ---------------------------------------------------------------------------

class SeedBuilder:
    def __init__(self, n_users=300, seed=42):
        self.rng = random.Random(seed)
        self.n_users = n_users
        self.seed = seed
        self.rows = defaultdict(list)   # table -> INSERT 할 행
        self.seq = defaultdict(int)
        # 아래는 계산용 메타데이터 (INSERT 에는 안 들어감)
        self.company, self.category, self.merchant = {}, {}, {}
        self.rules = {}                 # (company code, 결제일) -> 이용 기간 규칙
        self.accounts = {}
        self.products, self.promotions, self.common_terms = [], [], []
        self.users, self.apps, self.recurring = [], [], []
        self.cards = {}
        self.txs = []
        self.bills = {}
        self.termination_requests = []
        self.consents = {}              # (user id, company code) -> row
        self.user_by_id = {}
        self.signup_terms = []
        self.ledger = defaultdict(list)  # account id -> [거래 원장 행] (잔액 계산 전)

    # --- 공통 유틸 -----------------------------------------------------------

    def next_id(self, table):
        self.seq[table] += 1
        prefix, width = ID_PREFIX[table]
        return f"{prefix}_{self.seq[table]:0{width}d}"

    def add(self, table, **cols):
        row = {"id": self.next_id(table)}
        row.update(cols)
        self.rows[table].append(row)
        return row

    def put(self, table, **cols):
        self.rows[table].append(cols)
        return cols

    def rdt(self, a, b):
        """a 이상 b 미만의 무작위 시각."""
        if not isinstance(a, datetime):
            a = datetime.combine(a, time())
        if not isinstance(b, datetime):
            b = datetime.combine(b, time())
        span = int((b - a).total_seconds())
        return a + timedelta(seconds=self.rng.randint(0, max(span - 1, 0)))

    def poisson(self, lam):
        if lam <= 0:
            return 0
        if lam > 30:
            return max(0, round(self.rng.gauss(lam, lam ** 0.5)))
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def wsample(self, items, weights, k):
        """가중치 비복원 추출."""
        items, weights, out = list(items), list(weights), []
        for _ in range(min(k, len(items))):
            i = self.rng.choices(range(len(items)), weights=weights)[0]
            out.append(items.pop(i))
            weights.pop(i)
        return out

    @staticmethod
    def is_active(card, at):
        return card["start"] <= at and (card["end"] is None or at < card["end"])

    @staticmethod
    def card_name(card):
        return f"{card['prod']['name']}({card['row']['last4']})"

    def login(self, u, at):
        """로그인 세션 1건 + 인증 기록. 가끔 비밀번호를 한 번 틀린 뒤 성공. session id 를 돌려줌."""
        rng = self.rng
        request_id = "req-" + sha(f"{self.seed}-{u['id']}-{at}")[:16]
        if rng.random() < 0.03:
            self.add("auth_audit_logs", user_id=u["id"], event_type="LOGIN",
                     occurred_at=at - timedelta(seconds=40), outcome="FAILED_PASSWORD", request_id=request_id + "f")
        row = self.add("sessions", user_id=u["id"], created_at=at,
                       last_seen_at=min(at + timedelta(minutes=rng.randint(1, 25)), NOW),
                       expires_at=at + timedelta(minutes=30),
                       revoked_at=min(at + timedelta(minutes=rng.randint(5, 29)), NOW) if rng.random() < 0.3 else None)
        self.add("auth_audit_logs", user_id=u["id"], event_type="LOGIN", occurred_at=at, outcome="SUCCESS",
                 request_id=request_id)
        return row["id"]

    def step_up(self, u, action, at):
        """본인 확인 (PIN·비밀번호 재확인). 가끔 한 번은 시간 초과로 버려짐. 사용한 challenge id 를 돌려줌."""
        rng = self.rng
        action = STEP_UP_ACTIONS.get(action, action)
        session = self.login(u, at - timedelta(minutes=rng.randint(2, 15)))
        if rng.random() < 0.03:
            self.add("step_up_challenges", user_id=u["id"], action=action, session_id=session,
                     expires_at=at - timedelta(minutes=1), consumed_at=None)
        row = self.add("step_up_challenges", user_id=u["id"], action=action, session_id=session,
                       expires_at=at + timedelta(minutes=4), consumed_at=at - timedelta(seconds=30))
        return row["id"]

    # --- 1. 기준 데이터 -------------------------------------------------------

    def build_reference(self):
        rng = self.rng
        for code, name, bin_, point_name in COMPANIES:
            row = self.add("card_companies", code=code, name=name,
                           logo_url=f"https://static.example.com/companies/{code.lower()}.png", customer_center=None)
            self.company[code] = dict(id=row["id"], bin=bin_, point_name=point_name)
            if code == "TOSSBANK":   # 토스뱅크는 체크카드만 있어서 결제일 규칙이 없음
                continue
            for pd in PAYMENT_DAYS:
                rule = default_cycle_rule(pd)
                self.rules[(code, pd)] = rule
                self.put("billing_cycle_rules", card_company_id=row["id"], payment_day=pd,
                         start_month_offset=rule[0], start_day=rule[1], end_month_offset=rule[2], end_day=rule[3])
        for code, name, parent in CATEGORIES:
            row = self.add("categories", parent_id=self.category[parent]["id"] if parent else None, code=code, name=name)
            self.category[code] = row

        for p in PRODUCTS:
            released = date.fromisoformat(p["released"])
            row = self.add("card_products", card_company_id=self.company[p["company"]]["id"], name=p["name"],
                           card_type=p["type"], brand=p["brand"], annual_fee_domestic=p["fee"][0],
                           annual_fee_overseas=p["fee"][1], min_age=p["min_age"], image_url=None,
                           summary=p["summary"], is_active=p.get("active", True), released_at=released,
                           created_at=datetime.combine(released, time(10)))
            pid = row["id"]
            row["image_url"] = f"https://static.example.com/cards/{pid}.png"
            meta = dict(id=pid, company=p["company"], name=p["name"], type=p["type"], brand=p["brand"],
                        fee=p["fee"][0], fee_overseas=p["fee"][1], min_age=p["min_age"], pop=p["pop"],
                        active=p.get("active", True), tiers=[], tier_ids={}, benefits=[])
            for level, min_spend in enumerate(p["tiers"], 1):
                max_spend = p["tiers"][level] if level < len(p["tiers"]) else None
                t = self.add("card_performance_tiers", card_product_id=pid, tier_level=level,
                             min_spend=min_spend, max_spend=max_spend)
                meta["tiers"].append((level, min_spend))
                meta["tier_ids"][level] = t["id"]
            for b in p["benefits"]:
                assert b["tier"] is None or b["tier"] in meta["tier_ids"], (p["name"], b)
                br = self.add("card_benefits", card_product_id=pid,
                              tier_id=meta["tier_ids"][b["tier"]] if b["tier"] else None,
                              category_id=self.category[b["cat"]]["id"], benefit_type=b["btype"],
                              value_type=b["vtype"], benefit_value=float(b["value"]),
                              min_payment_amount=b["min_pay"], monthly_limit_amount=b["amt"],
                              monthly_limit_count=b["cnt"], is_instant=b["instant"],
                              description=describe(b, self.category[b["cat"]]["name"]))
                meta["benefits"].append(dict(b, id=br["id"]))
            self.products.append(meta)
        product_by_name = {p["name"]: p for p in self.products}

        for title, required in [("서비스 이용약관", True), ("개인정보 수집·이용 동의", True),
                                ("전자금융거래 기본약관", True), ("마케팅 정보 수신 동의", False)]:
            self.signup_terms.append(self.add_term(None, title, required))
        for title, required in [("개인(신용)정보 수집·이용 동의", True), ("개인(신용)정보 조회 동의", True),
                                ("카드 상품 마케팅 정보 수신 동의", False)]:
            self.common_terms.append(self.add_term(None, title, required))
        for p in self.products:
            p["term_id"] = self.add_term(p["id"], f"{p['name']} 상품설명서", True)["id"]

        for name, title, reward, min_spend, start, end in PROMOTIONS:
            prod = product_by_name[name]
            row = self.add("promotions", card_product_id=prod["id"], title=title, reward_amount=reward,
                           min_spend_condition=min_spend,
                           condition_desc=f"발급 후 다음 달 말일까지 {min_spend:,}원 이상 쓰면 {reward:,}원 지급",
                           starts_at=datetime.fromisoformat(start),
                           ends_at=datetime.combine(date.fromisoformat(end), time(23, 59, 59)))
            self.promotions.append(dict(id=row["id"], product=prod["id"],
                                        start=row["starts_at"], end=row["ends_at"]))

        business_nos = set()
        for name, cat, lo, hi, kind in MERCHANTS:
            while True:
                bno = f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(10000, 99999)}"
                if bno not in business_nos:
                    business_nos.add(bno)
                    break
            row = self.add("merchants", category_id=self.category[cat]["id"], name=name,
                           business_no=bno)
            self.merchant[name] = dict(id=row["id"], name=name, cat=cat, lo=lo, hi=hi, kind=kind,
                                       ccy=MERCHANT_CURRENCY.get(name))
        self.var_merchants = defaultdict(list)
        for m in self.merchant.values():
            if m["kind"] == "var":
                self.var_merchants[m["cat"]].append(m)
        self.big_merchants = [m for m in self.merchant.values() if m["kind"] == "big"]
        self.build_bank_reference()

    def build_bank_reference(self):
        """예금·적금 상품과 가상 타행 계좌(예금주 조회용 시드)."""
        rng = self.rng
        self.bank_products = []
        for p in BANK_PRODUCTS:
            row = self.add("products", bank=BANK_NAME, name=p["name"], type=p["type"], description=p["description"],
                           status=p["status"], source_url=None, verified_at="20261020")
            row["source_url"] = f"https://static.example.com/products/{row['id']}.html"
            for lo, hi, base, bonus in p["rates"]:
                self.add("product_rates", product_id=row["id"], term_min=lo, term_max=hi, term_unit="MONTH",
                         base_rate=base, bonus_rate=bonus, effective_from="20260701")
            rule = p["rule"]
            self.add("product_rules", product_id=row["id"], min_amount=rule["min_amount"],
                     max_amount=rule["max_amount"], min_months=rule["min_months"], max_months=rule["max_months"],
                     max_per_user=rule["max_per_user"], rules_json=rule.get("rules_json"))
            for title in ("상품설명서", "상품 약관"):
                d = self.add("product_documents", product_id=row["id"], title=f"{p['name']} {title}",
                             source_url=None, version_date="20260701")
                d["source_url"] = f"https://static.example.com/products/{d['id']}.pdf"
            self.bank_products.append(dict(p, id=row["id"]))

        self.external = []
        seen = set()
        while len(self.external) < 40:
            bank = rng.choice(BANKS)
            no = f"{rng.randint(100, 999)}{rng.randint(10 ** 8, 10 ** 9 - 1)}"
            if (bank, no) in seen:
                continue
            seen.add((bank, no))
            holder = rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES)
            row = self.add("external_accounts", bank=bank, account_no=no, holder_name=holder)
            self.external.append(row)

    def add_term(self, card_product_id, title, required):
        return self.add("terms", version="1.0", title=title, required=required,
                        effective_at=datetime(2025, 1, 1), card_product_id=card_product_id)

    def promotion_for(self, prod, at):
        for promo in self.promotions:
            if promo["product"] == prod["id"] and promo["start"] <= at <= promo["end"]:
                return promo
        return None

    # --- 2. 회원 / 계좌 -------------------------------------------------------

    def build_users(self):
        rng = self.rng
        for _ in range(self.n_users):
            youth = rng.random() < 0.08
            if youth:
                birth = date(rng.randint(2008, 2012), rng.randint(1, 12), rng.randint(1, 28))
                created = self.rdt(date(2025, 3, 1), date(2025, 11, 1))
            else:
                lo, hi = rng.choices([(20, 29), (30, 39), (40, 49), (50, 65)], weights=[38, 32, 18, 12])[0]
                birth = date(TODAY.year - rng.randint(lo, hi), rng.randint(1, 12), rng.randint(1, 28))
                created = self.rdt(date(2020, 1, 1), date(2025, 11, 1))
            # 마이데이터 동의 시각은 users 칸이 아니라 카드사별 mydata_consents 로 남김 (계산용 메타데이터)
            mydata = None if youth or rng.random() < 0.15 else self.rdt(created, datetime(2026, 4, 30))
            n = self.seq["users"] + 1
            email = f"user{n:04d}@example.com" if rng.random() < 0.6 else None
            row = self.add("users", username=f"user{n:04d}", name=rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES),
                           email=email,
                           email_verified_at=created - timedelta(minutes=rng.randint(1, 5)) if email else None,
                           birth_date=birth, gender=rng.choice("MF"),
                           payday=rng.choice(PAYDAYS) if not youth and rng.random() < 0.75 else None,
                           status="ACTIVE", created_at=created, withdrawn_at=None)
            u = dict(id=row["id"], name=row["name"], birth=birth, youth=youth, created=created, mydata=mydata,
                     cards=[], gender=row["gender"], payday=row["payday"], accounts=[])
            self.user_by_id[u["id"]] = u
            self.build_auth(u, email)
            u["primary"] = self.add_account(u, "CHECKING", created, primary=True)
            if rng.random() < 0.3:
                self.add_account(u, "SAVINGS", self.rdt(created, NOW - timedelta(days=200)))
            self.users.append(u)

    def build_auth(self, u, email):
        """가입 때 생기는 인증 데이터: 로그인 수단, 비밀번호, 이메일 인증, 약관 동의, PIN."""
        rng = self.rng
        created = u["created"]
        if email:
            self.add("email_verifications", email=email, purpose="SIGNUP",
                     challenge_digest=sha(f"email-{self.seed}-{u['id']}"),
                     expires_at=created + timedelta(minutes=5), attempt_count=rng.choice([1, 1, 1, 2]),
                     used_at=created - timedelta(minutes=1))
        self.add("auth_identities", user_id=u["id"], provider="LOCAL", provider_subject=u["id"], linked_at=created)
        if email and rng.random() < 0.25:
            self.add("auth_identities", user_id=u["id"], provider="GOOGLE",
                     provider_subject=str(10 ** 20 + int(sha(f"google-{self.seed}-{u['id']}")[:12], 16)),
                     linked_at=self.rdt(created, NOW - timedelta(days=1)))
        pw_updated = self.rdt(created, NOW - timedelta(days=1)) if rng.random() < 0.2 else created
        locked = rng.random() < 0.01
        self.put("local_credentials", user_id=u["id"],
                 password_hash="$2b$12$" + sha(f"pw-{self.seed}-{u['id']}")[:53],   # 가짜 bcrypt 형식
                 password_updated_at=pw_updated, failed_attempts=5 if locked else rng.choice([0, 0, 0, 1]),
                 locked_until=NOW + timedelta(minutes=20) if locked else None)
        if pw_updated != created:
            self.add("password_reset_tokens", user_id=u["id"], token_digest=sha(f"reset-{self.seed}-{u['id']}"),
                     expires_at=pw_updated + timedelta(minutes=25), used_at=pw_updated)
        for term in self.signup_terms:
            self.add("user_consents", user_id=u["id"], terms_id=term["id"], version=term["version"],
                     agreed=True if term["required"] else rng.random() < 0.5, recorded_at=created)
        if rng.random() < 0.65:
            enabled = created + timedelta(minutes=rng.randint(2, 30))
            self.put("pin_credentials", user_id=u["id"], pin_hash="$2b$12$" + sha(f"pin-{self.seed}-{u['id']}")[:53],
                     enabled_at=enabled,
                     changed_at=self.rdt(enabled, NOW - timedelta(days=1)) if rng.random() < 0.1 else None,
                     failed_attempts=rng.choice([0, 0, 0, 0, 1]), locked_until=None)
        self.login(u, created + timedelta(minutes=1))

    def add_account(self, u, account_type, created, primary=False):
        """두린은행 계좌. 잔액은 거래 원장을 다 만든 뒤(build_ledger) account_balances 에 넣음."""
        rng = self.rng
        number = f"110{self.seq['accounts'] + 1:08d}"
        name = "두린 입출금통장" if account_type == "CHECKING" else "두린 저축예금"
        nickname = rng.choice(["생활비", "월급통장", "비상금", "여행자금"]) if rng.random() < 0.15 else None
        row = self.add("accounts", user_id=u["id"], resAccount=number,
                       resAccountDisplay=f"{number[:3]}-{number[3:5]}-{number[5:]}", resAccountName=name,
                       account_type=account_type, lifecycle_status="ACTIVE", resAccountNickName=nickname,
                       is_favorite=primary, resAccountStartDate=ymd(created), closed_at=None, version=0)
        self.accounts[row["id"]] = dict(row=row, user=u, created=created, type=account_type)
        u["accounts"].append(row["id"])
        self.add("account_activity_logs", account_id=row["id"], actor_id=u["id"], action="OPEN",
                 occurred_at=created, metadata=f'{{"account_type": "{account_type}"}}')
        if nickname:
            self.add("account_activity_logs", account_id=row["id"], actor_id=u["id"], action="NICKNAME_CHANGE",
                     occurred_at=created + timedelta(hours=1), metadata=f'{{"after": "{nickname}"}}')
        alerts = rng.random() < 0.9
        self.accounts[row["id"]]["prefs"] = self.put(
            "notification_preferences", user_id=u["id"], account_id=row["id"], enabled=alerts,
            deposit_enabled=alerts, withdrawal_enabled=alerts,
            minimum_amount=rng.choice([0, 0, 0, 10000, 50000]), channel="PUSH")
        if account_type == "CHECKING":
            self.put("transfer_limits", account_id=row["id"], per_transfer_limit=rng.choice([5_000_000, 10_000_000]),
                     daily_limit=rng.choice([10_000_000, 30_000_000]), updated_at=created)
        if rng.random() < 0.05:
            issued = self.rdt(max(created, datetime(2026, 1, 1)), NOW)
            self.add("document_issuance_logs", account_id=row["id"],
                     document_type=rng.choice(["BALANCE_CERTIFICATE", "ACCOUNT_CERTIFICATE"]),
                     requested_by=u["id"], issued_at=issued, status="ISSUED")
        return row["id"]

    # --- 3. 카드 / 발급 신청 -------------------------------------------------

    def create_card(self, u, prod, source, issued, activated, application_id=None, account=None,
                    payment_day=None, reissued_from=None, nickname=None, annual_fee=None, credit_limit=None):
        rng = self.rng
        last4 = f"{rng.randint(0, 9999):04d}"
        if annual_fee is None:   # 국내전용/해외겸용 중 하나
            overseas = prod["brand"] != "LOCAL" and rng.random() < 0.7
            annual_fee = prod["fee_overseas"] if overseas else prod["fee"]
        row = self.add("user_cards", user_id=u["id"], card_product_id=prod["id"],
                       application_id=application_id, reissued_from_id=reissued_from, source=source,
                       org_card_id=None, nickname=nickname,
                       card_number_masked=f"{self.company[prod['company']]['bin']}-****-****-{last4}", last4=last4,
                       expires_at=month_end(add_months(issued.date(), 60)), linked_account_id=account,
                       payment_day=payment_day, credit_limit=credit_limit if prod["type"] == "CREDIT" else None,
                       status="ACTIVE", annual_fee_amount=annual_fee,
                       next_annual_fee_date=None, last_used_at=None, issued_at=issued, activated_at=activated,
                       terminated_at=None,
                       created_at=issued if source == "TOSS_ISSUED" else max(issued, u["mydata"] or issued))
        credit = prod["type"] == "CREDIT"
        card = dict(id=row["id"], row=row, user=u, prod=prod, credit=credit, pd=payment_day,
                    rule=self.rules[(prod["company"], payment_day)] if credit else None,
                    start=activated, end=None, settings=None, account=account, source=source)
        self.cards[card["id"]] = card
        u["cards"].append(card)
        return card

    def close_card(self, card, status, at, reason):
        card["end"] = at
        card["row"]["status"] = status
        self.add_card_history(card, "ACTIVE", status, reason, at)

    def add_card_history(self, card, from_status, to_status, reason, at):
        self.add("user_card_status_histories", user_card_id=card["id"], from_status=from_status,
                 to_status=to_status, reason=reason, changed_at=at)

    def log_management(self, card, action, before, after, at, result="SUCCESS"):
        self.add("card_management_logs", user_card_id=card["id"], action_type=action,
                 before_value=before, after_value=after, result=result, requested_at=at)

    def create_settings(self, card, copy_from=None):
        """카드 관리 설정. 새 카드는 등록 직후 사용자가 바꾼 설정을 관리 이력으로 남김."""
        rng = self.rng
        if copy_from:
            values = {k: v for k, v in copy_from.items() if k not in ("user_card_id", "updated_at")}
            card["settings"] = self.put("user_card_settings", user_card_id=card["id"], **values,
                                        updated_at=card["start"])
            return
        youth = card["user"]["youth"]
        values = dict(overseas_payment_blocked=rng.random() < 0.3, online_payment_blocked=rng.random() < 0.05,
                      daily_limit=rng.choice([300000, 500000, 1000000]) if rng.random() < 0.1 else None,
                      monthly_limit=300000 if youth else (
                          rng.choice([1000000, 2000000, 3000000]) if rng.random() < 0.15 else None),
                      payment_alert_enabled=rng.random() < 0.9)
        at = card["start"]
        changes = []
        if values["overseas_payment_blocked"]:
            changes.append(("BLOCK_OVERSEAS", "false", "true"))
        if values["online_payment_blocked"]:
            changes.append(("BLOCK_ONLINE", "false", "true"))
        if values["daily_limit"]:
            changes.append(("LIMIT_CHANGE", None, f"DAILY:{values['daily_limit']}"))
        if values["monthly_limit"]:
            changes.append(("LIMIT_CHANGE", None, f"MONTHLY:{values['monthly_limit']}"))
        for action, before, after in changes:
            at = min(at + timedelta(minutes=rng.randint(1, 10)), NOW)
            self.log_management(card, action, before, after, at)
        card["settings"] = self.put("user_card_settings", user_card_id=card["id"], **values, updated_at=at)
        if rng.random() < 0.1 and card["start"] < NOW - timedelta(days=1):   # 비밀번호 변경 (값은 저장 안 함)
            at = self.rdt(card["start"], NOW)
            self.step_up(card["user"], "CARD_MANAGEMENT", at)
            if rng.random() < 0.05:
                self.log_management(card, "PIN_CHANGE", None, None, at - timedelta(seconds=30), "FAILED")
            self.log_management(card, "PIN_CHANGE", None, None, at)

    def reissue(self, card, issued, activated):
        new = self.create_card(card["user"], card["prod"], card["source"], issued, activated,
                               account=card["account"], payment_day=card["pd"], reissued_from=card["id"],
                               nickname=card["row"]["nickname"], annual_fee=card["row"]["annual_fee_amount"],
                               credit_limit=card["row"]["credit_limit"])
        if card["settings"]:
            self.create_settings(new, copy_from=card["settings"])
        if new["source"] == "TOSS_ISSUED":
            self.add_card_history(new, None, "ACTIVE", "재발급 카드 등록", activated)
        return new

    def build_mydata_cards(self):
        rng = self.rng
        pool = [p for p in self.products if p["company"] != "TOSSBANK"]
        for u in self.users:
            if not u["mydata"]:
                continue
            lo = max(date(2021, 1, 1), u["birth"].replace(year=u["birth"].year + 19))
            hi = date(2026, 3, 31)
            if lo >= hi:
                continue
            for prod in self.wsample(pool, [p["pop"] for p in pool], rng.choice([0, 1, 1, 2, 2, 3])):
                issued = self.rdt(lo, hi)
                card = self.create_card(u, prod, "MYDATA", issued, issued,
                                        payment_day=rng.choice(PAYMENT_DAYS) if prod["type"] == "CREDIT" else None,
                                        nickname=rng.choice(NICKNAMES) if rng.random() < 0.1 else None,
                                        credit_limit=rng.choice([3, 5, 8, 10, 15]) * 1_000_000)
                expires = card["row"]["expires_at"]
                if expires < TODAY:   # 유효기간 만료 → 갱신 발급
                    end = datetime.combine(expires + timedelta(days=1), time())
                    self.close_card(card, "EXPIRED", end, "유효기간 만료")
                    self.reissue(card, datetime.combine(expires - timedelta(days=20), time(10)), end)

    def build_applications(self):
        rng = self.rng
        recent_from = datetime.combine(TODAY - timedelta(days=91), time())
        app_start = datetime.combine(APP_START, time())
        latest = NOW - timedelta(minutes=30)
        for u in self.users:
            n = (1 + (rng.random() < 0.3)) if u["youth"] else self.poisson(2.0)
            times = []
            for i in range(n):
                if u["youth"] and i == 0:   # 청소년은 이용 내역이 생기도록 첫 카드를 일찍 발급
                    lo, hi = max(app_start, u["created"]), datetime(2026, 4, 30)
                elif rng.random() < 0.6:
                    lo, hi = max(recent_from, u["created"]), latest
                else:
                    lo, hi = max(app_start, u["created"]), recent_from
                if lo >= hi:
                    lo, hi = max(app_start, u["created"]), latest
                times.append(self.rdt(lo, hi))
            applied_products = {c["prod"]["id"] for c in u["cards"]}
            for applied in sorted(times):
                age = age_on(u["birth"], applied.date())
                cands = [p for p in self.products
                         if p["active"] and p["min_age"] <= age and p["id"] not in applied_products]
                if u["youth"]:
                    cands = [p for p in cands if p["type"] == "CHECK"]
                if not cands:
                    continue
                weights = [p["pop"] * (2.5 if self.promotion_for(p, applied) else 1) for p in cands]
                prod = rng.choices(cands, weights=weights)[0]
                applied_products.add(prod["id"])
                self.create_application(u, prod, applied)

    def app_timeline(self, applied, credit):
        rng = self.rng
        steps = [("APPLIED", applied), ("REVIEWING", applied + timedelta(minutes=rng.randint(1, 30)))]
        r = rng.random()
        if r < 0.05:
            return steps + [("CANCELED", applied + timedelta(hours=rng.uniform(1, 20)))]
        t = steps[-1][1] + (timedelta(hours=rng.uniform(4, 30)) if credit else timedelta(minutes=rng.randint(1, 10)))
        if credit and r < 0.17:
            return steps + [("REJECTED", t)]
        steps.append(("APPROVED", t))
        t += timedelta(hours=rng.uniform(12, 30))
        steps.append(("SHIPPING", t))
        t += timedelta(hours=rng.uniform(24, 72))
        steps.append(("DELIVERED", t))
        if rng.random() < 0.93:
            steps.append(("ACTIVATED", t + timedelta(hours=rng.uniform(1, 96))))
        return steps

    def create_application(self, u, prod, applied):
        rng = self.rng
        credit = prod["type"] == "CREDIT"
        promo = self.promotion_for(prod, applied)
        account = u["primary"]   # 결제·출금 계좌는 두린은행 입출금 계좌
        steps = [s for s in self.app_timeline(applied, credit) if s[1] <= NOW]
        at = dict(steps)
        status = steps[-1][0]
        income = rng.randrange(28, 121) * 1_000_000 if credit else None
        row = self.add("card_applications", user_id=u["id"], card_product_id=prod["id"],
                       promotion_id=promo["id"] if promo else None, recommendation_id=None,
                       step_up_challenge_id=self.step_up(u, "APPLICATION", applied), status=status,
                       job_type=rng.choice(JOBS) if credit else None, annual_income=income,
                       linked_account_id=account, payment_day=rng.choice(PAYMENT_DAYS) if credit else None,
                       approved_credit_limit=min(income // 4 // 1_000_000 * 1_000_000, 20_000_000)
                       if credit and "APPROVED" in at else None,
                       delivery_address=f"서울시 {rng.choice(STREETS)} {rng.randint(1, 300)}, "
                                        f"{rng.randint(101, 120)}동 {rng.randint(1, 25)}0{rng.randint(1, 4)}호",
                       tracking_no=str(rng.randint(10 ** 11, 10 ** 12 - 1)) if "SHIPPING" in at else None,
                       reject_reason=rng.choice(REJECT_REASONS) if status == "REJECTED" else None,
                       applied_at=applied, decided_at=at.get("APPROVED") or at.get("REJECTED"),
                       updated_at=steps[-1][1])
        aid = row["id"]
        prev = None
        for st, t in steps:
            self.add("application_status_histories", application_id=aid, from_status=prev,
                     to_status=st, memo=APP_MEMO[st], changed_at=t)
            prev = st
        for term in self.common_terms:
            self.put("application_term_agreements", application_id=aid, terms_id=term["id"],
                     agreed=True if term["required"] else rng.random() < 0.6, agreed_at=applied)
        self.put("application_term_agreements", application_id=aid, terms_id=prod["term_id"], agreed=True,
                 agreed_at=applied)
        self.apps.append(dict(id=aid, user=u, prod=prod, status=status, applied=applied, row=row))
        if status == "ACTIVATED":
            card = self.create_card(u, prod, "TOSS_ISSUED", at["APPROVED"], at["ACTIVATED"], application_id=aid,
                                    account=account, payment_day=row["payment_day"],
                                    credit_limit=row["approved_credit_limit"])
            self.add_card_history(card, None, "ACTIVE", "카드 등록 완료", at["ACTIVATED"])
            self.create_settings(card)

    def build_card_events(self):
        """분실 재발급, 일시정지, 해지 이벤트. 토스에서 처리한 해지만 card_terminations 에 남김."""
        rng = self.rng
        window_start = datetime.combine(TX_START, time())
        for card in list(self.cards.values()):
            if card["end"] is not None or card["start"] > NOW - timedelta(days=40):
                continue
            toss = card["source"] == "TOSS_ISSUED"
            lo = max(card["start"], window_start) + timedelta(days=10)
            r = rng.random()
            if r < 0.02 and lo < NOW - timedelta(days=6):
                at = self.rdt(lo, NOW - timedelta(days=6))
                if toss:
                    self.step_up(card["user"], "CARD_MANAGEMENT", at)
                self.close_card(card, "LOST", at, "분실 신고")
                self.reissue(card, at + timedelta(days=1), at + timedelta(days=4 if toss else 1))
            elif r < 0.04:
                at = self.rdt(max(lo, NOW - timedelta(days=40)), NOW - timedelta(days=1))
                if toss:
                    self.step_up(card["user"], "CARD_MANAGEMENT", at)
                self.close_card(card, "SUSPENDED", at, "고객 요청 일시정지")
            elif r < 0.09 and lo + timedelta(days=20) < NOW - timedelta(days=3):
                at = self.rdt(lo + timedelta(days=20), NOW - timedelta(days=3))
                self.close_card(card, "TERMINATED", at, "고객 해지 신청")
                card["row"]["terminated_at"] = at
                if toss:
                    self.termination_requests.append(
                        (card, "COMPLETED", at - timedelta(hours=rng.uniform(1, 48)), at))
        active = [c for c in self.cards.values() if c["source"] == "TOSS_ISSUED" and c["end"] is None
                  and c["start"] < NOW - timedelta(days=60)]
        for i, card in enumerate(rng.sample(active, min(3, len(active)))):
            if i < 2:
                self.termination_requests.append((card, "REQUESTED", NOW - timedelta(hours=rng.uniform(1, 20)), None))
            else:
                self.termination_requests.append((card, "CANCELED", NOW - timedelta(days=20), None))

    # --- 4. 이용 내역 -------------------------------------------------------

    def active_cards(self, u, at, cat):
        out = []
        for c in u["cards"]:
            if not self.is_active(c, at):
                continue
            s = c["settings"]
            if cat == "OVERSEAS" and (c["prod"]["brand"] == "LOCAL" or (s and s["overseas_payment_blocked"])):
                continue
            if cat in ONLINE_CATEGORIES and s and s["online_payment_blocked"]:
                continue
            out.append(c)
        return out

    def build_subscriptions(self):
        rng = self.rng
        for u in self.users:
            subs = []
            if not u["youth"]:
                if rng.random() < 0.92:
                    subs.append((self.merchant[rng.choice(["SKT", "KT", "LG U+"])], rng.randrange(4500, 9501) * 10))
                for name in rng.sample(OTT_NAMES, rng.choice([0, 1, 1, 2])):
                    subs.append((self.merchant[name], rng.choice(SUB_PLANS[name])))
                if rng.random() < 0.3:
                    subs.append((self.merchant["쿠팡 와우 멤버십"], 7890))
                if rng.random() < 0.25:
                    subs.append((self.merchant["한국전력공사"], None))   # 매달 금액이 달라짐
            elif rng.random() < 0.3:
                subs.append((self.merchant["유튜브 프리미엄"], 14900))

            for merchant, amount in subs:
                day = rng.randint(1, 28)
                card, history = None, []
                m = TX_START.replace(day=1)
                while m <= TODAY:
                    at = datetime.combine(m.replace(day=day), time(rng.randint(3, 6), rng.randint(0, 59), rng.randint(0, 59)))
                    m = add_months(m, 1)
                    if at.date() < TX_START or at >= NOW:
                        continue
                    if card is None or not self.is_active(card, at):
                        cands = self.active_cards(u, at, merchant["cat"])
                        if not cands:
                            continue
                        card = rng.choice([c for c in cands if c["credit"]] or cands)
                    amt = amount or rng.randrange(2500, 9001) * 10
                    self.txs.append(dict(card=card, merchant=merchant, dt=at, amount=amt, inst=0, recurring=True,
                                         ccy=None, fx=None))
                    history.append((card, at, amt))
                self.add_recurring(u, merchant, day, history, variable=amount is None)

    def add_recurring(self, u, merchant, day, history, variable):
        if not history:
            return
        by_card = {}
        for card, at, amt in history:
            by_card.setdefault(card["id"], (card, []))[1].append((at, amt))
        last_card = history[-1][0]
        for cid, (card, pays) in by_card.items():
            if len(pays) >= 2:
                detected, created = "AUTO", pays[1][0] + timedelta(days=1)
            else:
                detected, created = "USER", pays[0][0] + timedelta(hours=2)
            amounts = [a for _, a in pays]
            row = self.add("recurring_payments", user_id=u["id"], user_card_id=cid,
                           merchant_id=merchant["id"], pay_cycle="MONTHLY",
                           expected_amount=round10(sum(amounts) / len(amounts)) if variable else amounts[-1],
                           expected_day=day, last_paid_at=pays[-1][0].date(), detected_by=detected,
                           is_active=card is last_card and card["end"] is None, created_at=min(created, NOW))
            self.recurring.append(dict(row=row, card=card, merchant=merchant, day=day, first=pays[0][0]))

    def build_spending(self):
        rng = self.rng
        months = []
        m = TX_START.replace(day=1)
        while m <= TODAY:
            months.append(m)
            m = add_months(m, 1)
        window_start = datetime.combine(TX_START, time())
        for u in self.users:
            if not u["cards"]:
                continue
            base = YOUTH_WEIGHTS if u["youth"] else ADULT_WEIGHTS
            weights = {c: w * rng.lognormvariate(0, 0.6) for c, w in base.items()}
            if not u["youth"] and rng.random() < 0.4:      # 자가용 운전자
                weights["FUEL"] = 5 * rng.lognormvariate(0, 0.4)
                weights["PUBLIC_TRANSIT"] *= 0.5
            if not u["youth"] and rng.random() < 0.15:     # 여행을 자주 가는 사람
                for c in ("OVERSEAS", "AIRLINE", "HOTEL"):
                    weights[c] *= 6
            cats, ws = list(weights), list(weights.values())
            lam = rng.uniform(8, 25) if u["youth"] else rng.uniform(15, 55)
            u["main"] = None
            if len(u["cards"]) >= 2:   # 카드가 여러 장이면 거의 안 쓰는 카드가 생김
                for c in u["cards"]:
                    c["dormant"] = rng.random() < 0.15
            for ms in months:
                lo = max(datetime.combine(ms, time()), window_start)
                hi = min(datetime.combine(add_months(ms, 1), time()), NOW)
                if lo >= hi:
                    continue
                frac = (hi - lo) / timedelta(days=30)
                for _ in range(self.poisson(lam * frac * rng.uniform(0.8, 1.2))):
                    cat = rng.choices(cats, weights=ws)[0]
                    merchant = rng.choice(self.var_merchants[cat])
                    day = self.rdt(lo, hi).date()
                    if u["payday"] and rng.random() < 0.2:   # 월급일 직후 소비가 몰림
                        day = day_of(ms, u["payday"]) + timedelta(days=rng.randint(0, 4))
                    h0, h1 = HOURS.get(cat, (9, 22))
                    at = datetime.combine(day, time(rng.randint(h0, h1 - 1), rng.randint(0, 59), rng.randint(0, 59)))
                    if lo <= at < hi:
                        self.spend(u, merchant, at)
                if not u["youth"] and rng.random() < 0.10 * frac:
                    at = datetime.combine(self.rdt(lo, hi).date(), time(rng.randint(11, 20), rng.randint(0, 59)))
                    if lo <= at < hi:
                        self.spend(u, rng.choice(self.big_merchants), at, big=True)

    def spend(self, u, merchant, at, big=False):
        rng = self.rng
        cat = merchant["cat"]
        cards = self.active_cards(u, at, cat)
        if not cards:
            return
        weights = []
        for c in cards:
            w = 3.0 if c is u["main"] else 1.0
            if any(b["cat"] == cat for b in c["prod"]["benefits"]):
                w *= 2
            if c.get("dormant"):
                w *= 0.01
            weights.append(w)
        card = rng.choices(cards, weights=weights)[0]
        if u["main"] is None or not self.is_active(u["main"], at):
            u["main"] = card
        r = rng.random() ** 1.6
        fx = None
        if merchant["ccy"]:
            fx = merchant["lo"] + (merchant["hi"] - merchant["lo"]) * r
            fx = round(fx, 2) if merchant["ccy"] == "USD" else float(round(fx))
            amount = round10(fx * FX[merchant["ccy"]])
        else:
            amount = round10(merchant["lo"] + (merchant["hi"] - merchant["lo"]) * r)
        inst = 0
        if card["credit"]:
            if big:
                inst = rng.choices([0, 2, 3, 6, 10, 12], weights=[10, 15, 25, 25, 10, 15])[0]
            elif amount >= 100000 and rng.random() < 0.25:
                inst = rng.choice([2, 3])
        self.txs.append(dict(card=card, merchant=merchant, dt=at, amount=amount, inst=inst, recurring=False,
                             ccy=merchant["ccy"], fx=fx))

    @staticmethod
    def period_fns(card):
        """(이용일 → 기간 키, 직전 기간 키, 기간 시작일). 신용카드는 결제일 기준, 체크카드는 달력 월."""
        if card["credit"]:
            pd, rule = card["pd"], card["rule"]
            return (lambda dt: payment_date_for(dt.date(), pd, rule), lambda k: add_months(k, -1),
                    lambda k: usage_period(k, rule)[0])
        return lambda dt: dt.date().replace(day=1), lambda k: add_months(k, -1), lambda k: k

    @staticmethod
    def achieved_tier(prod, perf):
        level = 0
        for lvl, min_spend in prod["tiers"]:
            if perf >= min_spend:
                level = lvl
        return level

    def run_benefits(self, prod, txs, key_of, prev_of, start_of, floor):
        """시간순 거래 목록에 상품 혜택을 적용해 [(혜택 규칙, 금액)] 을 돌려줌.
        직전 기간 실적으로 구간을 정하고, 직전 기간 데이터가 없으면 이번 기간 실적으로 대신함."""
        keys = [key_of(tx["dt"]) for tx in txs]
        perf = defaultdict(int)
        for tx, k in zip(txs, keys):
            if tx["counted"] and tx["status"] != "CANCELED":
                perf[k] += tx["net"]
        tiers = {}
        for k in set(keys):
            pk = prev_of(k)
            tiers[k] = self.achieved_tier(prod, perf[pk] if start_of(pk) >= floor else perf[k])
        used = defaultdict(lambda: [0, 0])
        out = []
        for tx, k in zip(txs, keys):
            if tx["status"] == "CANCELED" or tx["cat"] == "TAX":
                out.append((None, 0))
                continue
            tier = tiers[k]
            best, best_v = None, 0
            for b in prod["benefits"]:
                if b["cat"] not in (tx["cat"], "ALL"):
                    continue
                if (b["tier"] is not None and b["tier"] != tier) or (b["min_pay"] and tx["net"] < b["min_pay"]):
                    continue
                u = used[(k, b["id"])]
                if b["cnt"] and u[1] >= b["cnt"]:
                    continue
                v = round10(tx["net"] * b["value"] / 100) if b["vtype"] == "PERCENT" else int(b["value"])
                if b["amt"]:
                    v = min(v, b["amt"] - u[0])
                if v > best_v:
                    best, best_v = b, v
            if best:
                u = used[(k, best["id"])]
                u[0] += best_v
                u[1] += 1
            out.append((best, best_v))
        return out

    def build_transactions(self):
        rng = self.rng
        self.txs.sort(key=lambda t: t["dt"])
        for tx in self.txs:
            cat = tx["merchant"]["cat"]
            status, canceled, canceled_at = "APPROVED", 0, None
            if not tx["recurring"]:
                r = rng.random()
                cancel_at = tx["dt"] + timedelta(minutes=rng.randint(10, 4320))
                if cancel_at < NOW and r < 0.015:
                    status, canceled, canceled_at = "CANCELED", tx["amount"], cancel_at
                elif cancel_at < NOW and r < 0.023 and cat in PARTIAL_CANCEL_CATEGORIES:
                    canceled = round10(tx["amount"] * rng.uniform(0.2, 0.6))
                    status, canceled_at = "PARTIAL_CANCELED", cancel_at
            tx.update(cat=cat, status=status, canceled=canceled, canceled_at=canceled_at,
                      net=tx["amount"] - canceled, counted=cat != "TAX")

        by_card = defaultdict(list)
        for tx in self.txs:
            by_card[tx["card"]["id"]].append(tx)
        for cid, txs in by_card.items():
            card = self.cards[cid]
            floor = max(TX_START, card["start"].date())
            for tx, (b, v) in zip(txs, self.run_benefits(card["prod"], txs, *self.period_fns(card), floor)):
                tx["benefit"], tx["benefit_amount"] = b, v

        for i, tx in enumerate(self.txs):
            row = self.add("card_transactions", user_card_id=tx["card"]["id"],
                           merchant_id=tx["merchant"]["id"], approval_no=f"{(i * 7919 + 13579) % 10 ** 8:08d}",
                           transacted_at=tx["dt"], amount=tx["amount"], installment_months=tx["inst"],
                           is_overseas=tx["ccy"] is not None, currency=tx["ccy"] or "KRW", foreign_amount=tx["fx"],
                           status=tx["status"], canceled_amount=tx["canceled"], canceled_at=tx["canceled_at"],
                           applied_benefit_id=tx["benefit"]["id"] if tx["benefit"] else None,
                           benefit_amount=tx["benefit_amount"], is_performance_counted=tx["counted"],
                           created_at=tx["dt"])
            tx["id"] = row["id"]

    def build_daily_spending(self):
        """카드별 일별 집계 (어제까지, 거래가 있는 날만)."""
        days = {}
        for tx in self.txs:
            d = tx["dt"].date()
            if d >= TODAY:
                continue
            agg = days.setdefault((tx["card"]["id"], d), [0, 0, 0])
            if tx["status"] != "CANCELED":
                agg[0] += tx["net"]
                agg[1] += tx["net"] if tx["recurring"] else 0
                agg[2] += 1
        for (cid, d), (total, fixed, count) in sorted(days.items()):
            payday = self.cards[cid]["user"]["payday"]
            since = None
            if payday:
                pay = day_of(d.replace(day=1), payday)
                if pay > d:
                    pay = day_of(add_months(d.replace(day=1), -1), payday)
                since = (d - pay).days
            self.put("daily_card_spending", user_card_id=cid, spend_date=d, total_amount=total, fixed_amount=fixed,
                     tx_count=count, weekday=d.isoweekday(), days_from_payday=since, is_holiday=d in HOLIDAYS)

    # --- 5. 청구 / 해지 스냅샷 ----------------------------------------------

    def build_bills(self):
        rng = self.rng
        items = defaultdict(list)   # (card_id, 결제일) -> [(tx, 회차, 원금, 수수료)]
        for tx in self.txs:
            card = tx["card"]
            if not card["credit"] or tx["status"] == "CANCELED":
                continue
            n = max(1, tx["inst"])
            base = tx["net"] // n
            p0 = payment_date_for(tx["dt"].date(), card["pd"], card["rule"])
            remaining = tx["net"]
            for seq in range(1, n + 1):
                principal = tx["net"] - base * (n - 1) if seq == 1 else base
                fee = round10(remaining * 0.012) if tx["inst"] > 3 else 0
                items[(card["id"], add_months(p0, seq - 1))].append((tx, seq, principal, fee))
                remaining -= principal
        for card in self.cards.values():   # 진행 중인 이용 기간 청구서는 사용액이 없어도 만들어 둠
            if card["credit"] and card["end"] is None:
                items.setdefault((card["id"], payment_date_for(TODAY, card["pd"], card["rule"])), [])

        for cid, p in sorted(items):
            entries = items[(cid, p)]
            s, e = usage_period(p, self.cards[cid]["rule"])
            total = sum(pr + fee for _, _, pr, fee in entries)
            if p <= TODAY:
                status = "OVERDUE" if (TODAY - p).days <= 30 and total and rng.random() < 0.02 else "PAID"
            elif e < TODAY:
                status = "CONFIRMED"
            else:
                status = "SCHEDULED"
            row = self.add("card_bills", user_card_id=cid, billing_ym=f"{p:%Y%m}", usage_start=s,
                           usage_end=e, payment_date=p, total_amount=total,
                           paid_amount=total if status == "PAID" else 0, status=status,
                           confirmed_at=datetime.combine(e + timedelta(days=1), time(6)) if status != "SCHEDULED" else None,
                           paid_at=datetime.combine(p, time(7)) if status == "PAID" else None)
            self.bills[(cid, p)] = dict(row=row, items=entries)
            for tx, seq, principal, fee in entries:
                self.add("card_bill_items", bill_id=row["id"], card_transaction_id=tx["id"],
                         installment_seq=seq, principal_amount=principal, fee_amount=fee)

    def build_terminations(self):
        rng = self.rng
        point_by_card = defaultdict(list)
        for tx in self.txs:
            if tx["benefit"] and tx["benefit"]["btype"] == "POINT":
                point_by_card[tx["card"]["id"]].append(tx)
        for card, status, requested, completed in self.termination_requests:
            after = [(p, entry) for (cid, p), bill in self.bills.items() if cid == card["id"] and p > requested.date()
                     for entry in bill["items"] if entry[0]["dt"] <= requested]
            next_p = min((p for p, _ in after), default=None)
            unpaid = sum(pr + fee for p, (_, _, pr, fee) in after if p == next_p)
            remaining = sum(pr for p, (_, _, pr, _) in after if p != next_p)
            recurring = sum(1 for r in self.recurring if r["card"] is card and r["first"] <= requested
                            and r["row"]["last_paid_at"] >= requested.date() - timedelta(days=35))
            same_company = [c for c in card["user"]["cards"] if c is not card
                            and c["prod"]["company"] == card["prod"]["company"] and self.is_active(c, requested)]
            points = 0 if same_company else sum(tx["benefit_amount"] for tx in point_by_card[card["id"]]
                                                if tx["dt"] <= requested)
            anniv = anniversary_after(card["row"]["issued_at"].date(), requested.date())
            refund = round10(card["row"]["annual_fee_amount"] * (anniv - requested.date()).days / 365)
            reason = rng.choice(list(TERMINATION_REASONS))
            self.add("card_terminations", user_card_id=card["id"],
                     step_up_challenge_id=self.step_up(card["user"], "TERMINATION", requested), status=status,
                     reason_code=reason, reason_detail=TERMINATION_REASONS[reason], unpaid_amount=unpaid,
                     remaining_installment_amount=remaining, linked_recurring_count=recurring,
                     forfeited_points=points, refunded_annual_fee=refund, requested_at=requested,
                     completed_at=completed)

    # --- 6. 예측 / 추천 / 순위 ----------------------------------------------

    def build_forecasts(self):
        rec_by_card = defaultdict(list)
        for r in self.recurring:
            rec_by_card[r["card"]["id"]].append(r)
        for card in self.cards.values():
            if not card["credit"] or card["end"] is not None:
                continue
            rule = card["rule"]
            floor = max(TX_START, card["start"].date())
            p_now = payment_date_for(TODAY, card["pd"], rule)
            targets = [(p_now, TODAY - timedelta(days=1))]       # 진행 중인 기간 (어제까지 데이터)
            for k in (1, 2):                                    # 지난 기간: 중간 시점 예측 (정확도 비교용)
                p = add_months(p_now, -k)
                s = usage_period(p, rule)[0]
                if s >= floor:
                    targets.append((p, s + timedelta(days=14)))
            for p, base in targets:
                if base < usage_period(p, rule)[0]:
                    continue
                for model in ("LINEAR", "MOVING_AVG"):
                    self.add_forecast(card, p, base, model, rec_by_card[card["id"]], floor)

    def add_forecast(self, card, p, base, model, recurring, floor):
        rule = card["rule"]
        s, e = usage_period(p, rule)
        entries = self.bills.get((card["id"], p), {}).get("items", [])
        spent = sum(pr + fee for tx, seq, pr, fee in entries if seq == 1 and tx["dt"].date() <= base)
        confirmed = sum(pr + fee for tx, seq, pr, fee in entries if seq > 1)
        elapsed, total_days = (base - s).days + 1, (e - s).days + 1
        remaining_days = total_days - elapsed
        fixed = 0
        if model == "LINEAR":
            variable = max(0, round10(spent * total_days / elapsed) - spent)
        else:
            for r in recurring:
                if r["first"].date() > base or not (r["row"]["is_active"] or r["row"]["last_paid_at"] > base):
                    continue
                for month in (base.replace(day=1), add_months(base.replace(day=1), 1)):
                    if base < month.replace(day=r["day"]) <= e:
                        fixed += r["row"]["expected_amount"]
            hist_amount, hist_days = 0, 0
            for k in (1, 2, 3):
                hp = add_months(p, -k)
                hs, he = usage_period(hp, rule)
                if hs < floor:
                    break
                hist_amount += sum(pr + fee for tx, seq, pr, fee in self.bills.get((card["id"], hp), {}).get("items", [])
                                   if seq == 1 and not tx["recurring"])
                hist_days += (he - hs).days + 1
            if not hist_days:   # 지난 기간 데이터가 없으면 이번 기간 변동지출로 추정
                hist_amount = sum(pr + fee for tx, seq, pr, fee in entries
                                  if seq == 1 and not tx["recurring"] and tx["dt"].date() <= base)
                hist_days = elapsed
            variable = round10(hist_amount / hist_days * remaining_days)
        self.add("spending_forecasts", user_card_id=card["id"], billing_ym=f"{p:%Y%m}",
                 base_date=base, spent_to_date=spent, confirmed_installment=confirmed, fixed_expected=fixed,
                 variable_expected=variable, predicted_total=spent + confirmed + fixed + variable,
                 model_type=model, created_at=datetime.combine(base + timedelta(days=1), time(3)))

    def build_recommendations(self):
        """매월 1일 03시 배치. 직전 3개월 소비에 각 상품 혜택을 적용해 순혜택 상위 5개를 추천."""
        month_key = (lambda dt: dt.date().replace(day=1), lambda k: add_months(k, -1), lambda k: k)
        tx_by_user = defaultdict(list)
        for tx in self.txs:
            tx_by_user[tx["card"]["user"]["id"]].append(tx)
        batches_by_user = defaultdict(list)   # user id -> [(배치 시각, {product id: recommendation id})]
        for month in (8, 9, 10, 11):
            created = datetime(2026, month, 1, 3, 0)
            a_end = created.date() - timedelta(days=1)
            a_start = add_months(created.date(), -3)
            sim_start = max(TX_START, add_months(a_start, -1))   # 첫 달 실적 구간 계산용으로 한 달 더
            for u in self.users:
                txs = [tx for tx in tx_by_user[u["id"]] if sim_start <= tx["dt"].date() <= a_end]
                if len(txs) < 10:
                    continue
                age = age_on(u["birth"], a_end)
                held = {c["prod"]["id"] for c in u["cards"] if self.is_active(c, created)}
                spend = defaultdict(int)
                for tx in txs:
                    if tx["dt"].date() >= a_start and tx["counted"] and tx["status"] != "CANCELED":
                        spend[tx["cat"]] += tx["net"]
                results = []
                for prod in self.products:
                    if not prod["active"] or prod["min_age"] > age or prod["id"] in held:
                        continue
                    benefit = defaultdict(int)
                    for tx, (_, v) in zip(txs, self.run_benefits(prod, txs, *month_key, sim_start)):
                        if tx["dt"].date() >= a_start and v:
                            benefit[tx["cat"]] += v
                    monthly = round10(sum(benefit.values()) / 3)
                    results.append((monthly * 12 - prod["fee"], monthly, prod, benefit))
                results.sort(key=lambda r: (-r[0], r[2]["id"]))
                recs = {}
                for rank, (net, monthly, prod, benefit) in enumerate([r for r in results if r[0] > 0][:5], 1):
                    top = max(benefit, key=benefit.get)
                    row = self.add("card_recommendations", user_id=u["id"],
                                   card_product_id=prod["id"], analysis_start=a_start, analysis_end=a_end,
                                   expected_monthly_benefit=monthly, annual_fee=prod["fee"], net_annual_benefit=net,
                                   rank_no=rank,
                                   reason=f"최근 3개월 {self.category[top]['name']}에 월평균 "
                                          f"{round10(spend[top] / 3):,}원 썼어요",
                                   created_at=created)
                    recs[prod["id"]] = row["id"]
                    top_cats = sorted(benefit, key=lambda c: (-benefit[c], c))[:5]   # 혜택이 큰 카테고리 5개
                    for cat in top_cats:
                        if round10(benefit[cat] / 3):
                            self.put("card_recommendation_details", recommendation_id=row["id"],
                                     category_id=self.category[cat]["id"],
                                     spend_amount=round10(spend[cat] / 3), benefit_amount=round10(benefit[cat] / 3))
                batches_by_user[u["id"]].append((created, recs))

        # 추천 후 한 달 안에 추천받은 카드를 신청했다면 추천 경유로 연결
        for a in self.apps:
            batches = [b for b in batches_by_user[a["user"]["id"]] if b[0] <= a["applied"]]
            if batches:
                created, recs = batches[-1]
                if a["prod"]["id"] in recs and a["applied"] - created <= timedelta(days=31):
                    a["row"]["recommendation_id"] = recs[a["prod"]["id"]]

    def build_rankings(self):
        counted = [a for a in self.apps if a["status"] in COUNTED_APP_STATUSES]
        segments = [("ALL", "ALL", "ALL"), ("ALL", "ALL", "CREDIT"), ("ALL", "ALL", "CHECK"),
                    ("ALL", "M", "ALL"), ("ALL", "F", "ALL")] + \
                   [(g, "ALL", "ALL") for g in ("10s", "20s", "30s", "40s", "50s+")]

        def in_segment(a, seg):
            age, gender, ctype = seg
            return ((age == "ALL" or age_group(age_on(a["user"]["birth"], a["applied"].date())) == age)
                    and (gender == "ALL" or a["user"]["gender"] == gender)
                    and (ctype == "ALL" or a["prod"]["type"] == ctype))

        last_monday = TODAY - timedelta(days=TODAY.weekday())
        weekly = [("WEEKLY", last_monday - timedelta(weeks=k), last_monday - timedelta(weeks=k - 1))
                  for k in range(9, 0, -1)]
        monthly = [("MONTHLY", date(2026, m, 1), add_months(date(2026, m, 1), 1)) for m in (7, 8, 9, 10)]
        for series in (weekly, monthly):   # 각 시리즈의 첫 기간은 '직전 순위' 계산용으로만 씀
            prev_order = {}
            for i, (ptype, start, end) in enumerate(series):
                for seg in segments:
                    counts = Counter(a["prod"]["id"] for a in counted
                                     if start <= a["applied"].date() < end and in_segment(a, seg))
                    order = sorted(counts, key=lambda pid: (-counts[pid], pid))
                    if i > 0:
                        prev = prev_order.get(seg, [])
                        for rank, pid in enumerate(order[:10], 1):
                            self.add("card_issuance_rankings", period_type=ptype, period_start=start,
                                     segment_age=seg[0], segment_gender=seg[1], card_type=seg[2], card_product_id=pid,
                                     rank_no=rank, issue_count=counts[pid],
                                     prev_rank_no=prev.index(pid) + 1 if pid in prev else None,
                                     created_at=datetime.combine(end, time(4)))
                    prev_order[seg] = order

    # --- 7. 마이데이터 / 포인트 / 알림 --------------------------------------

    def build_mydata(self):
        """마이데이터 동의(카드사별)와 최근 3일 동기화 이력. 연동된 카드에 카드사 측 card_id 를 붙임."""
        rng = self.rng
        tx_count = Counter((tx["card"]["id"], tx["dt"].date()) for tx in self.txs)
        for u in self.users:
            if not u["mydata"]:
                continue
            for code in sorted({c["prod"]["company"] for c in u["cards"]} - {"TOSSBANK"}):
                consented = u["mydata"]
                while consented + timedelta(days=365) < NOW:   # 동의 유효기간 1년, 만료 전에 재동의
                    consented += timedelta(days=365)
                revoked_at = NOW - timedelta(days=rng.randint(1, 5), hours=rng.randint(0, 12)) \
                    if rng.random() < 0.03 else None
                key = sha(f"token-{self.seed}-{u['id']}-{code}")
                row = self.add("mydata_consents", user_id=u["id"], card_company_id=self.company[code]["id"],
                               access_token_enc=f"enc:v1:{key}{key[::-1]}",
                               refresh_token_enc=f"enc:v1:{sha(key)}",
                               scope="card.list card.approval card.bill card.point",
                               status="REVOKED" if revoked_at else "ACTIVE", consented_at=consented,
                               expires_at=consented + timedelta(days=365), last_synced_at=None)
                self.consents[(u["id"], code)] = row
                cards = [c for c in u["cards"] if c["prod"]["company"] == code]
                for c in cards:
                    c["row"]["org_card_id"] = f"{code}-{sha(f'org-{self.seed}-{c['id']}')[:20]}"
                for days_ago in (2, 1, 0):
                    day = TODAY - timedelta(days=days_ago)
                    started = datetime.combine(day, time(6, rng.randint(0, 29), rng.randint(0, 59)))
                    if started > NOW or (revoked_at and started > revoked_at):
                        continue
                    for api in ("CARDS", "APPROVALS", "BILLS", "POINTS"):
                        failed = rng.random() < 0.03
                        finished = started + timedelta(seconds=rng.randint(1, 20))
                        fetched = {"CARDS": len(cards),
                                   "APPROVALS": sum(tx_count[(c["id"], day - timedelta(days=1))] for c in cards),
                                   "BILLS": sum(1 for c in cards if c["credit"]), "POINTS": 1}[api]
                        self.add("mydata_sync_logs", mydata_consent_id=row["id"], api_type=api,
                                 started_at=started, finished_at=finished, result="FAILED" if failed else "SUCCESS",
                                 fetched_count=0 if failed else fetched,
                                 error_message=rng.choice(SYNC_ERRORS) if failed else None)
                        if not failed:
                            row["last_synced_at"] = finished
                        started = finished + timedelta(seconds=1)

    def build_points(self):
        """카드사별 포인트. 마이데이터로 연동된 카드사만 조회됨."""
        rng = self.rng
        earned = defaultdict(int)
        for tx in self.txs:
            if tx["benefit"] and tx["benefit"]["btype"] == "POINT":
                earned[(tx["card"]["user"]["id"], tx["card"]["prod"]["company"])] += tx["benefit_amount"]
        self.point_rows = []
        for (uid, code), consent in sorted(self.consents.items()):
            u = self.user_by_id[uid]
            base = rng.randint(500, 30000) if rng.random() < 0.65 else 0
            cashout = None
            if base >= 3000 and rng.random() < 0.2:
                amount = base // 1000 * 1000
                status = "FAILED" if rng.random() < 0.05 else "COMPLETED"
                cashout = (amount, status, self.rdt(date(2026, 8, 1), date(2026, 11, 1)))
                if status == "COMPLETED":
                    base -= amount
            balance = base + earned[(uid, code)]
            expiring = min(balance, rng.randint(100, 5000)) if balance and rng.random() < 0.3 else 0
            row = self.add("card_points", user_id=uid, card_company_id=self.company[code]["id"],
                           point_name=self.company[code]["point_name"], balance=balance, expiring_amount=expiring,
                           expiring_date=TODAY + timedelta(days=rng.randint(1, 60)) if expiring else None,
                           synced_at=consent["last_synced_at"] or consent["consented_at"])
            self.point_rows.append((u, row))
            if cashout:
                amount, status, requested = cashout
                self.add("point_cashouts", card_point_id=row["id"],
                         account_id=u["primary"], amount=amount, status=status, requested_at=requested,
                         completed_at=requested + timedelta(minutes=2) if status == "COMPLETED" else None)

    def finalize_cards(self):
        """배치로 갱신하는 카드 컬럼: 마지막 사용 시각, 다음 연회비 청구일."""
        for tx in self.txs:
            row = tx["card"]["row"]
            if row["last_used_at"] is None or tx["dt"] > row["last_used_at"]:
                row["last_used_at"] = tx["dt"]
        for card in self.cards.values():
            if card["end"] is None and card["row"]["annual_fee_amount"]:
                card["row"]["next_annual_fee_date"] = anniversary_after(card["row"]["issued_at"].date(), TODAY,
                                                                        inclusive=True)

    # --- 8. 계좌 거래 (이체 / 예약·자동이체 / 예금·적금 / 원장) -----------------

    def ledger_add(self, account_id, dt, ttype, amount, display_name, transfer_id=None, bank=None, account_no=None,
                   source=None):
        """거래 원장에 넣을 성공 거래 1건. 잔액(balance_after)은 build_ledger 에서 시간순으로 계산."""
        self.ledger[account_id].append(dict(dt=dt, type=ttype, amount=amount, display_name=display_name,
                                            transfer_id=transfer_id, bank=bank, account_no=account_no,
                                            source=source))

    def other_bank_account(self):
        return self.rng.choice(BANKS), f"{self.rng.randint(100, 999)}{self.rng.randint(10 ** 8, 10 ** 9 - 1)}"

    def build_income(self):
        """급여(월급일) / 용돈 입금. 다른 은행에서 들어온 돈이라 transfers 행은 없음."""
        rng = self.rng
        for u in self.users:
            if u["youth"]:
                amount, who, day = rng.randrange(5, 21) * 10000, "엄마", rng.randint(1, 28)
            elif u["payday"]:
                amount, who, day = rng.randrange(220, 601) * 10000, rng.choice(EMPLOYERS), u["payday"]
            else:
                amount, who, day = rng.randrange(150, 401) * 10000, rng.choice(EMPLOYERS), rng.choice([10, 25])
            bank, no = self.other_bank_account()
            m = TX_START.replace(day=1)
            while m <= TODAY:
                at = datetime.combine(day_of(m, day), time(9, rng.randint(0, 30)))
                m = add_months(m, 1)
                if TX_START <= at.date() and at < NOW:
                    self.ledger_add(u["primary"], at, "TRANSFER_IN", amount, who, bank=bank, account_no=no)

    def build_card_payments(self):
        """카드값 출금: 신용카드는 결제일에 청구서 금액, 체크카드는 승인 즉시. 포인트 현금화는 입금."""
        for (cid, p), bill in sorted(self.bills.items()):
            card, row = self.cards[cid], bill["row"]
            if card["account"] and row["status"] == "PAID" and row["paid_amount"]:
                company = next(n for c, n, *_ in COMPANIES if c == card["prod"]["company"])
                self.ledger_add(card["account"], datetime.combine(p, time(7)), "CARD_PAYMENT", row["paid_amount"],
                                f"{company} 결제대금")
        for tx in self.txs:
            card = tx["card"]
            if not card["credit"] and card["account"] and tx["status"] != "CANCELED":
                self.ledger_add(card["account"], tx["dt"], "CARD_PAYMENT", tx["net"], tx["merchant"]["name"],
                                source="card_tx")
        for row in self.rows["point_cashouts"]:
            if row["status"] == "COMPLETED":
                point = next(r for _, r in self.point_rows if r["id"] == row["card_point_id"])
                self.ledger_add(row["account_id"], row["completed_at"], "POINT_CASHOUT", row["amount"],
                                point["point_name"] or "카드 포인트")

    def add_transfer(self, u, at, target, amount, channel="APP", scheduled=None, step_up=None, key=None,
                     my_name=None):
        """이체 1건. target = dict(bank, account_no, holder, account_id(우리 은행이면)).
        성공하면 출금(및 우리 은행 계좌면 입금) 원장을 함께 남김."""
        rng = self.rng
        failed = rng.random() < 0.04
        if amount >= 1_000_000 and step_up is None and channel == "APP":
            step_up = self.step_up(u, "TRANSFER", at)
        my_name = my_name or target["holder"]
        row = self.add("transfers", user_id=u["id"], from_account_id=u["primary"], to_bank=target["bank"],
                       to_account_no=target["account_no"], to_holder_name=target["holder"], amount=amount, fee=0,
                       my_display_name=my_name, their_display_name=u["name"],
                       status="FAILED" if failed else "SUCCESS",
                       failure_reason=rng.choice(TRANSFER_FAILURES) if failed else None, channel=channel,
                       scheduled_transfer_id=scheduled, step_up_challenge_id=step_up,
                       idempotency_key=key or "APP-" + sha(f"{self.seed}-{u['id']}-{at}-{amount}")[:24],
                       requested_at=at, completed_at=at + timedelta(seconds=rng.randint(1, 5)))
        if not failed:
            done = row["completed_at"]
            self.ledger_add(u["primary"], done, "TRANSFER_OUT", amount, my_name, transfer_id=row["id"],
                            bank=target["bank"], account_no=target["account_no"])
            if target.get("account_id"):
                self.ledger_add(target["account_id"], done, "TRANSFER_IN", amount, u["name"], transfer_id=row["id"],
                                bank=BANK_NAME, account_no=self.accounts[u["primary"]]["row"]["resAccount"])
        return row

    def target_of(self, other=None, ext=None):
        if other:
            acc = self.accounts[other["primary"]]["row"]
            return dict(bank=BANK_NAME, account_no=acc["resAccount"], holder=other["name"], account_id=acc["id"])
        return dict(bank=ext["bank"], account_no=ext["account_no"], holder=ext["holder_name"])

    def build_transfers(self):
        """앱 송금 + 예약 송금(ONCE) + 자동이체(MONTHLY). 자주 보낸 계좌는 자주 쓰는 계좌로 등록."""
        rng = self.rng
        window_start = datetime.combine(TX_START, time())
        specs = []   # (시각, 사용자, 받는 계좌, 금액) — 시간순으로 이체 ID를 매기려고 모아 둠
        for u in self.users:
            friends = [self.target_of(ext=e) for e in rng.sample(self.external, 3)] + \
                      [self.target_of(other=o) for o in rng.sample(self.users, 2) if o is not u]
            for _ in range(self.poisson(1.0 if u["youth"] else 4.0)):
                amount = rng.randrange(1, 300) * 1000 if rng.random() < 0.9 else rng.randrange(10, 51) * 100_000
                if u["youth"]:
                    amount = rng.randrange(1, 50) * 1000
                specs.append((self.rdt(window_start, NOW - timedelta(hours=1)), u, rng.choice(friends), amount))
            u["friends"] = friends
        sent = Counter()
        for at, u, target, amount in sorted(specs, key=lambda s: (s[0], s[1]["id"])):
            if self.add_transfer(u, at, target, amount)["status"] == "SUCCESS":
                sent[(u["id"], target["bank"], target["account_no"])] += 1

        for u in self.users:
            if u["youth"]:
                continue
            r = rng.random()
            if r < 0.12:
                self.add_auto_transfer(u)
            elif r < 0.22:
                self.add_reserved_transfer(u)

        for u in self.users:
            order = 0
            for t in u["friends"]:
                if sent[(u["id"], t["bank"], t["account_no"])] >= 2:
                    order += 1
                    self.add("favorite_accounts", user_id=u["id"], bank=t["bank"], account_no=t["account_no"],
                             holder_name=t["holder"], nickname=rng.choice([None, None, "친구", "가족", "회비"]),
                             sort_order=order)

    def scheduled_row(self, u, created, target, amount, purpose, **cols):
        step = self.step_up(u, "SCHEDULED_TRANSFER", created)
        return self.add("scheduled_transfers", user_id=u["id"], from_account_id=u["primary"], to_bank=target["bank"],
                        to_account_no=target["account_no"], to_holder_name=target["holder"], amount=amount,
                        my_display_name=purpose, their_display_name=u["name"], type=cols["type"],
                        execute_at=cols.get("execute_at"), day_of_month=cols.get("day_of_month"),
                        start_ym=cols.get("start_ym"), end_ym=cols.get("end_ym"), next_run_at=cols.get("next_run_at"),
                        status=cols["status"], step_up_challenge_id=step, created_at=created,
                        updated_at=cols.get("updated_at", created))

    def add_auto_transfer(self, u):
        """자동이체: 매월 day_of_month 09시. 10% 는 몇 번 돌고 해지됨."""
        rng = self.rng
        target = self.target_of(ext=rng.choice(self.external))
        purpose = rng.choice(AUTO_TRANSFER_PURPOSES)
        amount = rng.randrange(5, 101) * 10000
        created = self.rdt(datetime(2026, 3, 1), datetime(2026, 9, 1))
        start = add_months(created.date().replace(day=1), 1)
        day = rng.choice([1, 5, 10, 15, 25, 28, 99])
        runs = []
        m = start
        while True:
            at = datetime.combine(day_of(m, day), time(9))
            if at >= NOW:
                break
            if at.date() >= TX_START:
                runs.append(at)
            m = add_months(m, 1)
        canceled = rng.random() < 0.1 and len(runs) >= 2
        if canceled:
            runs = runs[:rng.randint(1, len(runs) - 1)]
            end = runs[-1] + timedelta(days=3)
        row = self.scheduled_row(u, created, target, amount, purpose, type="MONTHLY", day_of_month=day,
                                 start_ym=f"{start:%Y%m}", end_ym=f"{end:%Y%m}" if canceled else None,
                                 next_run_at=None if canceled else datetime.combine(day_of(m, day), time(9)),
                                 status="CANCELED" if canceled else "ACTIVE",
                                 updated_at=end if canceled else (runs[-1] if runs else created))
        for at in runs:
            self.add_transfer(u, at, target, amount, channel="AUTO", scheduled=row["id"],
                              key=f"SCH-{row['id']}-{at:%Y%m%d}", my_name=purpose)

    def add_reserved_transfer(self, u):
        """예약 송금(1회): 이미 실행됐거나, 앞으로 실행 예정이거나, 취소됨."""
        rng = self.rng
        target = rng.choice(u["friends"])
        amount = rng.randrange(1, 100) * 10000
        r = rng.random()
        if r < 0.5:
            execute = datetime.combine(self.rdt(TX_START, TODAY - timedelta(days=2)).date(), time(rng.choice([9, 12, 18])))
            created = execute - timedelta(days=rng.randint(1, 20))
            row = self.scheduled_row(u, created, target, amount, None, type="ONCE", execute_at=execute,
                                     status="PROCESSING", updated_at=execute)
            t = self.add_transfer(u, execute, target, amount, channel="SCHEDULED", scheduled=row["id"],
                                  key=f"SCH-{row['id']}-{execute:%Y%m%d}")
            row["status"] = t["status"]
            row["my_display_name"] = t["my_display_name"]
        else:
            execute = datetime.combine(TODAY + timedelta(days=rng.randint(1, 14)), time(rng.choice([9, 12, 18])))
            created = NOW - timedelta(days=rng.randint(1, 10), hours=rng.randint(0, 12))
            canceled = r > 0.85
            self.scheduled_row(u, created, target, amount, target["holder"], type="ONCE", execute_at=execute,
                               next_run_at=None if canceled else execute,
                               status="CANCELED" if canceled else "SCHEDULED",
                               updated_at=created + timedelta(hours=2) if canceled else created)

    def build_deposits(self):
        """예금·적금 가입과 납입. 가입·납입은 SUBSCRIPTION_PAYMENT 출금, 중도 해지는 SUBSCRIPTION_PAYOUT 입금."""
        rng = self.rng
        on_sale = [p for p in self.bank_products if p["status"] == "ON_SALE"]
        self.deposits = []
        for u in self.users:
            if u["youth"] or rng.random() > 0.22:
                continue
            start_dt = self.rdt(TX_START, TODAY - timedelta(days=3))
            age = age_on(u["birth"], start_dt.date())
            cands = [p for p in on_sale if "청년" not in p["name"] or 19 <= age <= 34]
            p = rng.choice(cands)
            lo, hi, base, bonus = rng.choice(p["rates"])
            term = rng.choice([t for t in (6, 12, 24, 36) if lo <= t <= hi] or [lo])
            rate = f"{float(base) + (float(bonus) if bonus and rng.random() < 0.6 else 0):.2f}"
            rule = p["rule"]
            savings = p["type"] == "INSTALLMENT_SAVINGS"
            amount = (min(rng.choice([10, 20, 30, 50, 100]) * 10000, rule["max_amount"]) if savings
                      else rng.choice([1, 3, 5, 10, 20]) * 1_000_000)
            terminated = rng.random() < 0.08
            start = start_dt.date()
            row = self.add("subscriptions", user_id=u["id"], product_id=p["id"], source_account_id=u["primary"],
                           principal=None if savings else amount, monthly_amount=amount if savings else None,
                           applied_rate=rate, start_date=ymd(start), maturity_date=ymd(add_months(start, term)),
                           status="ACTIVE", closed_at=None,
                           idempotency_key="SUB-" + sha(f"{self.seed}-{u['id']}-{start_dt}")[:24])
            self.step_up(u, "SUBSCRIPTION", start_dt)
            paid, k = [], 0
            while True:
                at = datetime.combine(add_months(start, k), start_dt.time()) if k else start_dt
                if at >= NOW or (k and not savings):
                    break
                paid.append(at)
                k += 1
            if terminated and len(paid) >= 2:
                paid = paid[:-1]
            for at in paid:
                if savings:
                    self.add("subscription_payments", subscription_id=row["id"], paid_amount=amount,
                             paid_at=ymdhms(at))
                self.ledger_add(u["primary"], at, "SUBSCRIPTION_PAYMENT", amount, p["name"])
            if terminated:
                closed = min(paid[-1] + timedelta(days=rng.randint(5, 25)), NOW - timedelta(hours=1))
                closed = max(closed, paid[-1] + timedelta(minutes=30))
                total = amount * len(paid)
                row["status"], row["closed_at"] = "TERMINATED", ymd(closed)
                self.ledger_add(u["primary"], closed, "SUBSCRIPTION_PAYOUT", total + round10(total * 0.001),
                                f"{p['name']} 해지")
            self.deposits.append(dict(row=row, user=u, product=p))

    def build_ledger(self):
        """원장을 시간순으로 쌓아 거래 ID·거래 후 잔액·현재 잔액을 정함.
        창 이전 잔액(opening)은 잔액이 음수가 되지 않도록 넉넉히 잡음."""
        rng = self.rng
        self.balance = {}
        opening = {}
        for acc_id, meta in self.accounts.items():
            events = sorted(self.ledger[acc_id], key=lambda e: e["dt"])
            running, low = 0, 0
            for e in events:
                running += e["amount"] if e["type"] in ("TRANSFER_IN", "POINT_CASHOUT", "SUBSCRIPTION_PAYOUT") \
                    else -e["amount"]
                low = min(low, running)
            opening[acc_id] = round10(min(rng.lognormvariate(13.0, 1.0), 30_000_000)) - low
            self.balance[acc_id] = opening[acc_id]
        flat = sorted(((e["dt"], acc_id, i, e) for acc_id, evs in self.ledger.items() for i, e in enumerate(evs)),
                      key=lambda x: (x[0], x[1], x[2]))
        self.ledger_rows = []
        for dt, acc_id, _, e in flat:
            sign = 1 if e["type"] in ("TRANSFER_IN", "POINT_CASHOUT", "SUBSCRIPTION_PAYOUT") else -1
            self.balance[acc_id] += sign * e["amount"]
            row = self.add("transactions", account_id=acc_id, type=e["type"], amount=e["amount"], fee=0,
                           balance_after=self.balance[acc_id], transfer_id=e["transfer_id"],
                           counterpart_bank=e["bank"], counterpart_account_no=e["account_no"],
                           display_name=e["display_name"], created_at=dt)
            self.ledger_rows.append((row, e))
        last = {}
        for row, _ in self.ledger_rows:
            last[row["account_id"]] = row["created_at"]
        for acc_id, meta in self.accounts.items():
            self.put("account_balances", account_id=acc_id, currency="KRW", balance=self.balance[acc_id],
                     updated_at=last.get(acc_id, meta["created"]))
            seen = last.get(acc_id, meta["created"])
            inactive = seen < NOW - timedelta(days=365)
            self.put("account_inactivity", account_id=acc_id, last_activity_at=seen, inactivity_flag=inactive,
                     flagged_at=seen + timedelta(days=365) if inactive else None)

    def build_withdrawal_checks(self):
        """탈퇴를 점검하다 그만둔 회원 몇 명 (모든 회원은 ACTIVE)."""
        rng = self.rng
        for u in rng.sample(self.users, max(1, len(self.users) // 100)):
            started = self.rdt(NOW - timedelta(days=60), NOW - timedelta(days=1))
            self.add("withdrawal_checks", user_id=u["id"], status="CANCELED", started_at=started,
                     balance_verified_at=started + timedelta(minutes=1), data_review_confirmed_at=None,
                     data_review_version=None, linked_services_confirmed_at=None, completed_at=None)

    def build_bank(self):
        self.build_income()
        self.build_card_payments()
        self.build_transfers()
        self.build_deposits()
        self.build_ledger()
        self.build_withdrawal_checks()

    def build_notifications(self):
        """알림. event_id = 원인 이벤트 (같은 이벤트·회원·종류로 두 번 보내지 않음)."""
        rng = self.rng
        notes = []   # (회원, 카드, 계좌 id, 종류, 제목, 본문, 시각, event_id)

        def note(u, ntype, title, body, at, event, card=None, account=None):
            notes.append((u, card, account, ntype, title, body, at, event))

        txs_by_card = defaultdict(list)
        for tx in self.txs:
            txs_by_card[tx["card"]["id"]].append(tx)
        for a in self.apps:
            at = a["row"]["updated_at"]
            if a["status"] in APP_NOTICE and at >= NOW - timedelta(days=30):
                note(a["user"], "APPLICATION", APP_NOTICE[a["status"]],
                     f"{a['prod']['name']} · {APP_MEMO[a['status']]}", at, f"{a['id']}:{a['status']}")
        for (cid, p), bill in sorted(self.bills.items()):
            row, card = bill["row"], self.cards[cid]
            if row["status"] != "CONFIRMED" or not row["total_amount"]:
                continue
            note(card["user"], "PAYMENT_DUE", "카드값 결제 예정",
                 f"{p.month}월 {p.day}일에 {self.card_name(card)} {row['total_amount']:,}원이 결제될 예정이에요",
                 row["confirmed_at"] + timedelta(hours=3), row["id"], card=card)
            acc = card["account"]
            if acc and self.balance[acc] < row["total_amount"]:
                display = self.accounts[acc]["row"]["resAccountDisplay"]
                note(card["user"], "LOW_BALANCE", "결제 계좌 잔액이 부족해요",
                     f"{p.month}월 {p.day}일 결제 예정 금액보다 {BANK_NAME} {display} 계좌 잔액이 "
                     f"{row['total_amount'] - self.balance[acc]:,}원 부족해요",
                     row["confirmed_at"] + timedelta(hours=4), row["id"], card=card, account=acc)
        for h in self.rows["user_card_status_histories"]:
            if h["to_status"] in CARD_STATUS_NOTICE and NOW - timedelta(days=60) <= h["changed_at"] <= NOW:
                card = self.cards[h["user_card_id"]]
                note(card["user"], "CARD_STATUS", CARD_STATUS_NOTICE[h["to_status"]], self.card_name(card),
                     h["changed_at"] + timedelta(minutes=1), h["id"], card=card)
        for card in self.cards.values():
            if card["end"] is not None or card["start"] > NOW:
                continue
            prod, row = card["prod"], card["row"]
            if card["credit"] and prod["tiers"]:
                s, e = usage_period(payment_date_for(TODAY, card["pd"], card["rule"]), card["rule"])
                perf = sum(tx["net"] for tx in txs_by_card[card["id"]] if tx["counted"]
                           and tx["status"] != "CANCELED" and s <= tx["dt"].date() <= e)
                nxt = [m for _, m in prod["tiers"] if m > perf]
                if nxt:
                    note(card["user"], "PERFORMANCE", "다음 달 혜택까지 조금 남았어요",
                         f"{self.card_name(card)} 실적 {perf:,}원, {nxt[0] - perf:,}원 더 쓰면 다음 구간 혜택을 받아요",
                         datetime.combine(TODAY, time(8)), f"{card['id']}:{TODAY:%Y%m%d}", card=card)
            fee_date = row["next_annual_fee_date"]
            if fee_date and (fee_date - TODAY).days <= 30:
                note(card["user"], "ANNUAL_FEE", "연회비 청구 예정",
                     f"{fee_date.month}월 {fee_date.day}일에 {self.card_name(card)} 연회비 "
                     f"{row['annual_fee_amount']:,}원이 청구될 예정이에요",
                     NOW - timedelta(hours=rng.randint(1, 72)), f"{card['id']}:{fee_date:%Y%m%d}", card=card)
            unused_since = row["last_used_at"] or card["start"]
            if card["start"] < NOW - timedelta(days=90) and unused_since < NOW - timedelta(days=60):
                fee = f" 연회비 {row['annual_fee_amount']:,}원이 나가고 있어요" if row["annual_fee_amount"] else ""
                note(card["user"], "UNUSED_CARD", "60일 넘게 안 쓴 카드가 있어요",
                     f"{self.card_name(card)}를 오래 안 쓰셨어요.{fee}", datetime.combine(TODAY, time(8, 30)),
                     f"{card['id']}:{TODAY:%Y%m%d}", card=card)
        for u, row in self.point_rows:
            if row["expiring_amount"]:
                d = row["expiring_date"]
                note(u, "POINT_EXPIRING", "포인트가 곧 사라져요",
                     f"{d.month}월 {d.day}일에 {row['point_name']} {row['expiring_amount']:,}점이 소멸돼요. "
                     f"지금 현금으로 바꿔 보세요", NOW - timedelta(hours=rng.randint(1, 48)), row["id"])
        for d in self.deposits:
            row = d["row"]
            maturity = datetime.strptime(row["maturity_date"], "%Y%m%d").date()
            if row["status"] == "ACTIVE" and 0 <= (maturity - TODAY).days <= 30:
                note(d["user"], "MATURITY", "만기가 다가와요",
                     f"{d['product']['name']}이 {maturity.month}월 {maturity.day}일에 만기돼요",
                     datetime.combine(TODAY, time(8)), row["id"], account=row["source_account_id"])
        for tx in self.txs:   # 카드 결제 알림
            s = tx["card"]["settings"]
            if tx["dt"] >= NOW - timedelta(days=2) and s and s["payment_alert_enabled"]:
                note(tx["card"]["user"], "TRANSACTION", "결제 알림",
                     f"{tx['merchant']['name']} {tx['amount']:,}원 결제 ({self.card_name(tx['card'])})",
                     tx["dt"], tx["id"], card=tx["card"])
        for row, e in self.ledger_rows:   # 계좌 입출금 알림 (체크카드 결제는 위 카드 알림으로 대신함)
            meta = self.accounts[row["account_id"]]
            prefs = meta["prefs"]
            deposit = row["type"] in ("TRANSFER_IN", "POINT_CASHOUT", "SUBSCRIPTION_PAYOUT")
            if (row["created_at"] < NOW - timedelta(days=2) or e["source"] == "card_tx" or not prefs["enabled"]
                    or not (prefs["deposit_enabled"] if deposit else prefs["withdrawal_enabled"])
                    or row["amount"] < prefs["minimum_amount"]):
                continue
            word = "입금" if deposit else "출금"
            note(meta["user"], "TRANSACTION", f"{word} 알림",
                 f"{row['display_name']} {row['amount']:,}원 {word} · 잔액 {row['balance_after']:,}원",
                 row["created_at"], row["id"], account=row["account_id"])

        for u, card, account, ntype, title, body, at, event in sorted(notes, key=lambda n: (n[6], n[0]["id"], n[7])):
            if at > NOW:
                continue
            read_at = at + timedelta(minutes=rng.randint(1, 600)) \
                if at < NOW - timedelta(days=1) and rng.random() < 0.8 else None
            self.add("notifications", user_id=u["id"], account_id=account, user_card_id=card["id"] if card else None,
                     event_id=event, type=ntype, title=title, body=body, status="READ" if read_at else "SENT",
                     read_at=min(read_at, NOW) if read_at else None, created_at=at)

    # --- 실행 ---------------------------------------------------------------

    def build(self):
        self.build_reference()
        self.build_users()
        self.build_mydata_cards()
        self.build_applications()
        self.build_card_events()
        self.build_subscriptions()
        self.build_spending()
        self.build_transactions()
        self.build_daily_spending()
        self.build_bills()
        self.build_terminations()
        self.build_forecasts()
        self.build_recommendations()
        self.build_rankings()
        self.build_mydata()
        self.build_points()
        self.finalize_cards()
        self.build_bank()
        self.build_notifications()
        return self

    def write_sql(self, path):
        lines = [
            "-- 두린은행 계좌·거래·상품·카드 서비스 - 목 데이터",
            f"-- scripts/generate_seed.py 로 생성 (users={self.n_users}, seed={self.seed}, 기준 시각 {NOW:%Y-%m-%d %H:%M})",
            "-- docs/schema.sql 실행 후 이 파일을 실행하세요. 다시 실행하면 기존 데이터를 지우고 새로 넣습니다.",
            "",
            "SET NAMES utf8mb4;",
            "USE toss_card;",
            "SET time_zone = '+09:00';",
            "SET FOREIGN_KEY_CHECKS = 0;",
        ]
        lines += [f"TRUNCATE TABLE {t};" for t in reversed(TABLE_ORDER)]
        lines.append("SET FOREIGN_KEY_CHECKS = 1;")
        for table in TABLE_ORDER:
            rows = self.rows[table]
            if not rows:
                continue
            cols = list(rows[0])
            lines.append(f"\n-- {table}: {len(rows):,}건")
            for i in range(0, len(rows), 500):
                values = ",\n".join("(" + ", ".join(sql_value(r[c]) for c in cols) + ")" for r in rows[i:i + 500])
                lines.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values};")
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="두린은행 서비스 목 데이터 생성")
    parser.add_argument("--users", type=int, default=300, help="회원 수 (기본 300)")
    parser.add_argument("--seed", type=int, default=42, help="난수 seed (기본 42)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "seed.sql"))
    args = parser.parse_args()

    builder = SeedBuilder(args.users, args.seed).build()
    builder.write_sql(args.out)
    print(f"생성 완료: {args.out}")
    for table in TABLE_ORDER:
        print(f"  {table:<30} {len(builder.rows[table]):>8,}")


if __name__ == "__main__":
    main()
