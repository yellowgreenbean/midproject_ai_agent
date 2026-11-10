"""data/rag 의 모든 md 에서 '우리' 브랜드 이름을 '두린' 으로, terms/service_terms.md 의 '토스' 를 '두린 은행' 으로 바꾼다
(원본 PDF 는 그대로).

실행: py -3.13 scripts/rename_bank.py
여러 번 돌려도 결과가 같다. pdf_to_md.py 나 crawl_toss_terms.py 로 md 를 다시 만들면 원래 이름이 돌아오므로 그 뒤 다시 돌린다.
"""

import re
import sys
from pathlib import Path

RAG = Path(__file__).resolve().parents[1] / "data" / "rag"
# md 의 '우리' 는 우리은행·우리카드·우리 통장·우리FIS 등 전부 브랜드다(2026-11-09 전수 확인). '우리나라' 만 예외.
# shortcut: 새 문서에 대명사 '우리는'·'우리의' 등이 들어오면 이 예외 목록에 더한다
BRAND = re.compile(r"우리(?!나라)")
# 서비스 약관은 토스 약관 원문이라 '토스'(토스앱·토스머니 등)를 '두린 은행' 으로 바꾼다. 이 파일만.
TOSS_FILE = RAG / "terms" / "service_terms.md"

sys.stdout.reconfigure(encoding="utf-8")
total = 0
for md in sorted(RAG.rglob("*.md")):
    text = md.read_bytes().decode("utf-8")  # bytes 로 읽고 써서 줄바꿈(CRLF/LF)을 그대로 둔다
    text, n = BRAND.subn("두린", text)
    if md == TOSS_FILE:
        text, k = re.subn("토스", "두린 은행", text)
        n += k
    if n:
        md.write_bytes(text.encode("utf-8"))
        print(f"{md.relative_to(RAG).as_posix()}: {n}곳")
        total += n
print(f"\n합계 {total}곳 바꿈")
