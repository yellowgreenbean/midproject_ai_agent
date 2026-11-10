"""토스 약관 페이지(toss.im/docs/<번호>)를 받아 Markdown 약관 파일로 저장한다 — 가입 약관 본문(terms.content_url)용.

    py -3.13 scripts/crawl_toss_terms.py                                   # 서비스 이용약관 → data/rag/terms/service_terms.md
    py -3.13 scripts/crawl_toss_terms.py https://toss.im/docs/11027 data/rag/terms/service_terms.md

설치: pip install requests beautifulsoup4
페이지 구조(2026-11-09 확인): <h1>제목</h1> · <div class="dropdown"> 시행일 목록(첫 항목 = 현재판) · <hr> 뒤 <p> 한 줄씩.
  「제N장」 → ##, 「제N조 (…)」 → ###, 「- 부칙 -」 → ## 부칙, 「- 부속약관 -」 → ## 부속약관 + 다음 줄을 ###. 나머지 <p> 는 문단 그대로.
내용은 고치지 않는다(회사 이름 「비바리퍼블리카」·「토스」도 원문 그대로) — 맨 위 앞머리(---)에 출처·시행일·받은 날을 적는다.
저장 위치는 data/rag/terms/ — 가입 약관 본문(terms.content_url)이면서 챗봇 RAG(scripts/rag_ingest.py)도 같은 파일을 읽는다.
구조가 바뀌어 제목·조항을 못 찾으면 멈춘다(빈 파일을 만들지 않게).
"""

import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://toss.im/docs/11027"
DEFAULT_OUT = ROOT / "data" / "rag" / "terms" / "service_terms.md"

CHAPTER = re.compile(r"^제\s*\d+\s*장")
ARTICLE = re.compile(r"^제\s*\d+\s*조(의\s*\d+)?\s*\(")
ANNEX = re.compile(r"^-\s*(부칙|부속약관)\s*-$")


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MidProject-study-crawler)"}, timeout=20)
    r.raise_for_status()  # 404·500 이면 여기서 멈춘다
    r.encoding = "utf-8"
    return r.text


def to_markdown(html: str, url: str, fetched: date) -> tuple[str, int, int]:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    body = h1.find_parent("div") if h1 else None
    if body is None:
        raise SystemExit("오류: <h1> 제목을 찾지 못했어요. 페이지 구조가 바뀌었는지 확인해 주세요.")
    title = h1.get_text(strip=True)

    version = soup.select_one("div.dropdown #version")  # 지금 보이는 판의 시행일
    current = soup.select_one("div.dropdown a.dropdown-item")  # 첫 항목 = 현재판 고유 주소
    effective = version.get_text(strip=True) if version else "확인 못 함"
    permalink = urljoin(url, current["href"]) if current else url

    # 앞머리는 pdf_to_md.py 와 같은 모양 — rag_ingest.py 가 source: 를 출처로 읽고, 본문 조각에는 넣지 않는다
    out = ["---", f"source: {permalink}", f"effective: {effective}", f"fetched: {fetched.isoformat()}", "---", "",
           f"# {title}", ""]
    chapters = articles = 0
    annex_next = False
    for p in body.find_all("p"):
        text = "\n".join(line.strip() for line in p.get_text("\n").splitlines() if line.strip())  # <br> 은 줄바꿈으로
        if not text:
            continue
        if CHAPTER.match(text):
            chapters += 1
            out += [f"## {text}", ""]
        elif ARTICLE.match(text):
            articles += 1
            out += [f"### {text}", ""]
        elif m := ANNEX.match(text):
            out += [f"## {m[1]}", ""]
            annex_next = m[1] == "부속약관"  # 부속약관은 다음 줄이 그 약관 이름
        elif annex_next:
            out += [f"### {text}", ""]
            annex_next = False
        else:
            out += [text.replace("\n", "  \n"), ""]  # 문단 안 줄바꿈 유지(줄 끝 공백 두 칸)
    if articles == 0:
        raise SystemExit("오류: 「제N조 (…)」 조항을 하나도 못 찾았어요. 페이지 구조가 바뀌었는지 확인해 주세요.")
    return "\n".join(out).rstrip() + "\n", chapters, articles


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    md, chapters, articles = to_markdown(fetch(url), url, date.today())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8", newline="\n")
    print(f"저장: {out_path} · 장 {chapters}개 · 조 {articles}개 · {len(md):,}자")
