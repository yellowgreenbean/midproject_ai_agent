"""data/rag 의 모든 md 에서 '우리' 브랜드 이름을 '두린' 으로 바꾼다 (원본 PDF 는 그대로).

실행: py -3.13 scripts/rename_bank.py
여러 번 돌려도 결과가 같다. pdf_to_md.py 로 md 를 다시 만들면 원래 이름이 돌아오므로 그 뒤 다시 돌린다.
"""

import sys
from pathlib import Path

RAG = Path(__file__).resolve().parents[1] / "data" / "rag"
# 이 이름들만 바꾼다 — 그냥 '우리'(대명사 '우리는' 등)는 건드리지 않는다
NAMES = {"우리은행": "두린은행", "우리카드": "두린카드", "우리WON": "두린WON", "우리 WON": "두린 WON", "우리금융": "두린금융"}

sys.stdout.reconfigure(encoding="utf-8")
total = 0
for md in sorted(RAG.rglob("*.md")):
    text = md.read_bytes().decode("utf-8")  # bytes 로 읽고 써서 줄바꿈(CRLF/LF)을 그대로 둔다
    if n := sum(text.count(old) for old in NAMES):
        for old, new in NAMES.items():
            text = text.replace(old, new)
        md.write_bytes(text.encode("utf-8"))
        print(f"{md.relative_to(RAG).as_posix()}: {n}곳")
        total += n
print(f"\n합계 {total}곳 바꿈")
