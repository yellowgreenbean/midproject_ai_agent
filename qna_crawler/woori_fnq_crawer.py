"""
우리은행 인터넷/스마트뱅킹 FAQ 크롤러
- 대상: 지정한 categoryid의 FAQ 목록
- 출력: JSON
- 주의: 사이트의 상세보기 링크/답변 영역 구조가 변경되면
        DETAIL_SELECTORS 또는 extract_answer()를 조정해야 합니다.

설치:
    pip install requests beautifulsoup4

실행:
    python woori_faq_crawler.py

선택 실행:
    python woori_faq_crawler.py --max-pages 5 --output woori_faq.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://spot.wooribank.com/pot/Dream"
START_PARAMS = {
    "withyou": "CQCCS0002",
    "cc": "c006332:c009213",
    "categoryid": "NODE0000000673",
    "PageNo": "1",
    "sortType": "Date",
    "gu": "per",
    "categoryFocus": "y",
}
CATEGORY_NAME = "인터넷/스마트뱅킹"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

# 사이트 HTML 구조가 바뀌었을 때 우선 확인할 상세 답변 후보 영역
DETAIL_SELECTORS = [
    ".faq_view",
    ".faqView",
    ".view_cont",
    ".view-cont",
    ".board_view",
    ".board-view",
    ".bbs_view",
    ".bbs-view",
    "#contents",
    "main",
]


def clean_text(value: str) -> str:
    """공백/개행을 정리하고 불필요한 공백을 제거합니다."""
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n", value)
    return value.strip()


def make_page_url(page_no: int) -> str:
    params = dict(START_PARAMS)
    params["PageNo"] = str(page_no)
    response = requests.Request("GET", BASE_URL, params=params).prepare()
    return response.url


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    # 은행 사이트의 응답 인코딩을 우선 사용하고, 없으면 apparent_encoding 사용
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def find_faq_table(soup: BeautifulSoup) -> Optional[Tag]:
    """'번호/제목/조회' 헤더가 있는 표를 우선 탐색합니다."""
    for table in soup.find_all("table"):
        text = clean_text(table.get_text(" ", strip=True))