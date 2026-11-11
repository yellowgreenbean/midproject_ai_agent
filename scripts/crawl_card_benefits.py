"""카드고릴라(card-gorilla.com)에서 참고 카드 5장의 혜택 원문을 받아 data/cardgorilla/ 에 저장한다.

실행: py -3.13 scripts/crawl_card_benefits.py          (표준 라이브러리만 씀)

왜: 더미 카드(한빛 5종)는 CODEF 샌드박스의 가상 카드라 혜택 정보가 없다. 그래서 상품마다 비슷한 실제 카드(우리카드)를
하나씩 정해 그 혜택을 참고한다(사용자 결정 2026-11-10 — 카드 이름·발급 주체(두린은행)는 그대로, 혜택만 참고).
    한빛 라이프 체크   ← 카드의정석 칼퇴 CHECK (2760)      한빛체크카드 ← 카드의정석 EVERYDAY CHECK (2742)
    한빛 쇼핑 신용카드 ← 카드의정석2 SHOPPING+ (2687)       한빛신용카드 ← 카드의정석2 (2848)
    할인카드           ← D4카드의정석Ⅱ (2686)

출처: 카드고릴라 카드 상세 화면(https://www.card-gorilla.com/card/detail/<번호>)이 부르는 공개 API
      https://api.card-gorilla.com:8080/v1/cards/<번호>  (robots.txt 는 Allow: /, 2026-11-10 확인)
저장: data/cardgorilla/card_<번호>.json — 원문(HTML 을 줄글로 푼 것)만, 고치지 않는다. 참고 자료다.
앱이 읽는 혜택 표(data/dummy/cards/card_benefits.json)는 이 원문을 사람이 읽고 칸에 옮긴 것이다 — 원문을 다시 받으면
숫자가 바뀌었는지 diff 로 보고 그 파일을 손으로 고친다(혜택 문구가 줄글이라 자동 변환은 틀리기 쉽다).
"""

import datetime
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

CARDS = {2760: "한빛 라이프 체크", 2742: "한빛체크카드", 2687: "한빛 쇼핑 신용카드", 2848: "한빛신용카드", 2686: "할인카드"}
API = "https://api.card-gorilla.com:8080/v1/cards/{}"
OUT = Path(__file__).resolve().parents[1] / "data" / "cardgorilla"


def plain(fragment: str) -> str:
    """혜택 설명 HTML → 줄글 (줄 단위, 빈 줄 없음)"""
    t = re.sub(r"<(br|/p|/li|/tr|/h\d)[^>]*>", "\n", fragment or "")
    t = re.sub(r"</t[dh]>", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("﻿", "")
    return "\n".join(" ".join(line.split()) for line in t.splitlines() if line.strip())


def fetch(idx: int) -> dict:
    req = urllib.request.Request(API.format(idx), headers={"User-Agent": "Mozilla/5.0 (MidProject study crawler)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    for idx, ours in CARDS.items():
        d = fetch(idx)
        card = {
            "source_url": f"https://www.card-gorilla.com/card/detail/{idx}",
            "fetched_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds"),
            "used_for": ours,
            "idx": d["idx"],
            "name": d["name"],
            "company": d["corp"]["name"],
            "card_type": {"CRD": "CREDIT", "CHK": "CHECK"}[d["cate"]],
            "is_discontinued": d["is_discon"],
            "pre_month_money": d["pre_month_money"],
            "annual_fee_basic": d["annual_fee_basic"],
            "annual_fee_detail": plain(d["annual_fee_detail"]),
            "benefits": [{"title": b["title"], "summary": b.get("comment") or "", "text": plain(b["info"])}
                         for b in d["key_benefit"]],
        }
        path = OUT / f"card_{idx}.json"
        path.write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{ours} ← {card['name']} ({card['company']}, 혜택 {len(card['benefits'])}개) → {path.name}")
        time.sleep(1)  # 사이트에 부담을 주지 않게 한 장씩 천천히


if __name__ == "__main__":
    main()
