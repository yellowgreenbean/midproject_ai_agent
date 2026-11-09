"""상품설명서 md 의 '※ 위 그림은 …' 칸에 원본 PDF 그림(중도해지이율 구간 그래프)의 OCR 결과를 넣는다.

사용법:
    py -3.13 scripts/products_figure_ocr.py data/rag/products/prod_003.md
    py -3.13 scripts/products_figure_ocr.py data/rag/products          # 폴더의 md 전부

'• 계산방법(예시)' 뒤에 '계약일~3개월: 연0.1% · 3개월~6개월: 기본이율×50%×보유일수/계약일수 · … · 만기일: 약정이율'
한 줄을 넣는다. 다시 실행하면 넣은 줄을 바꿔 쓴다(중복 없음). pdf_to_md.py 로 md 를 다시 만들면 지워지므로 그 뒤 다시 돌린다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pdfplumber

import pdf_to_md as p2m  # 같은 scripts 폴더

MARK = "※ 위 그림은"
CELL = re.compile(r"(• 계산방법\(예시\)).*?(?= ※ 위 그림은)")  # 앞에 넣었던 문장까지 잡아 바꿔 씀
# shortcut: 이 그래프에서 실제로 본 OCR 오타만 고친다, 다른 파일에서 새 오타가 나오면 추가
FIX = {"약정이을": "약정이율"}


def ocr_engine():
    from rapidocr import RapidOCR

    # 방향 분류(cls)는 바로 선 가로줄도 180° 뒤집어 '9개월'→'H∠6' 처럼 읽어서 끈다
    return RapidOCR(params={**p2m._ocr_params(), "Global.use_cls": False})


def figures(pdf_path: Path):
    """'위 그림은' 문구마다 바로 위에 있는 그림을 216 DPI 이미지로 돌려준다 (문서 순서)."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for hit in page.search(r"위\s*그림은"):
                above = [im for im in page.images if im["bottom"] <= hit["top"] + 5 and im["x1"] > hit["x0"]]
                if not above:
                    yield None
                    continue
                im = max(above, key=lambda i: i["bottom"])
                crop = page.crop((im["x0"], im["top"], im["x1"], im["bottom"]))
                yield np.array(crop.to_image(resolution=p2m.TABLE_DPI).original.convert("RGB"))


def describe(boxes, txts) -> str:
    """맨 아래 줄(x축 눈금) 사이 구간마다 그 위 글자를 모아 '눈금~눈금: 글자' 로 잇는다."""
    items = [(min(p[0] for p in b), max(p[0] for p in b), min(p[1] for p in b), FIX.get(t, t)) for b, t in zip(boxes, txts)]
    bottom = max(i[2] for i in items)
    axis = sorted((i for i in items if i[2] > bottom - 15), key=lambda i: i[0])
    centers = [(a[0] + a[1]) / 2 for a in axis]
    parts: list[list] = [[] for _ in axis]
    for x0, x1, top, text in items:
        if top > bottom - 15:
            continue
        cx = (x0 + x1) / 2
        k = max([i for i, c in enumerate(centers) if c <= cx], default=0)
        parts[k].append((top, text))
    out = []
    for k, ps in enumerate(parts):
        if not ps:
            continue
        label = f"{axis[k][3]}~{axis[k + 1][3]}" if k + 1 < len(axis) else axis[k][3]
        out.append(f"{label}: " + "".join(t for _, t in sorted(ps)))
    return " · ".join(out)


def process(md: Path, engine) -> str:
    pdf = md.with_suffix(".pdf")
    lines = md.read_text(encoding="utf-8").split("\n")
    idx = [i for i, ln in enumerate(lines) if MARK in ln]
    if not idx:
        return "문구 없음"
    if not pdf.exists():
        return f"PDF 없음: {pdf.name}"
    figs = list(figures(pdf))
    if len(figs) != len(idx):
        return f"건너뜀: md 문구 {len(idx)}개 ≠ PDF 문구 {len(figs)}개"
    done = []
    for i, img in zip(idx, figs):
        if img is None:
            done.append("그림 없음")
            continue
        r = engine(img)
        if r.boxes is None or not r.txts:
            done.append("OCR 결과 없음")
            continue
        text = describe(r.boxes, r.txts)
        lines[i] = CELL.sub(lambda m: f"{m.group(1)} {text}", lines[i], count=1)
        done.append(text)
    md.write_text("\n".join(lines), encoding="utf-8")
    return "\n    ".join(done)


def _selftest():
    box = lambda x0, x1, y: [[x0, y], [x1, y], [x1, y + 10], [x0, y + 10]]  # noqa: E731
    boxes = [box(0, 40, 100), box(200, 240, 100), box(400, 440, 100), box(60, 120, 50), box(250, 330, 40), box(250, 330, 55), box(450, 500, 0)]
    txts = ["계약일", "3개월", "만기일", "연0.1%", "기본이율×50%", "×보유일수", "약정이을"]
    got = describe(boxes, txts)
    assert got == "계약일~3개월: 연0.1% · 3개월~만기일: 기본이율×50%×보유일수 · 만기일: 약정이율", got


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    _selftest()
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/rag/products")
    mds = [src] if src.suffix == ".md" else sorted(src.glob("*.md"))
    engine = ocr_engine()
    for md in mds:
        print(f"{md.name}: {process(md, engine)}")


if __name__ == "__main__":
    main()
