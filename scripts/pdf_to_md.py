"""PDF → Markdown 변환 (챗봇 RAG 문서용).

사용법:
    py -3.13 scripts/pdf_to_md.py                      # data/rag/terms 의 PDF 전부
    py -3.13 scripts/pdf_to_md.py data/rag/riders      # 상품 특약
    py -3.13 scripts/pdf_to_md.py data/rag/products    # 다른 폴더
    py -3.13 scripts/pdf_to_md.py data/rag/terms --out data/rag_md/terms

결과 .md 는 기본으로 PDF 와 같은 폴더에 같은 이름으로 만든다(이미 있으면 덮어씀).

설치: pip install pdfplumber rapidocr rapid-layout rapid-table onnxruntime
      (모델 파일은 처음 실행할 때 자동으로 내려받는다)

라이브러리 비교와 쓰임새:
  | 라이브러리              | 장점                                         | 단점                                       | 여기서 맡는 일 |
  | pdfplumber              | 글자층을 그대로 꺼내 오탈자 0, 글자 좌표·괘선  | 글자층 없는 스캔본은 못 읽음, 영역 구분 없음 | 본문 글자, 괘선 표, 칸 글자 |
  |                         | 좌표를 줘서 표 셀(병합 셀 포함)을 정확히 앎     | 바깥 테두리·행 구분선 없는 표는 셀을 놓침     |                |
  | RapidOCR (PP-OCRv5 한국어) | 스캔본·그림 속 글자를 읽음, CPU 로 빠름       | 비슷한 글자 오인식(을/울 등), 띄어쓰기 불안정 | 글자층 없는 페이지·큰 그림만 |
  | rapid-layout (PP-DocLayoutV3) | 머리말·꼬리말·쪽번호·로고·표·그림 영역 구분 | 글자는 안 읽음, 영역 경계가 몇 pt 어긋남    | 버릴 영역과 표 영역 찾기 |
  | rapid-table             | 선이 없거나 복잡한 표도 이미지로 구조(병합) 인식 | 글자는 OCR 에 의존, 비슷한 열을 합치기도 함  | 괘선 표·좌표 표가 안 될 때 |
  → 글자는 항상 가장 정확한 pdfplumber 를 쓰고, OCR 은 글자층이 없는 곳에만 쓴다.
    rapid-table 에도 OCR 대신 pdfplumber 글자를 넣어 구조 인식만 맡긴다.

처리 순서 (페이지마다):
  1. rapid-layout(pp_doc_layoutv3)으로 페이지 영역을 나눈다
     - 머리말·꼬리말·쪽번호·로고 영역은 버린다
     - 표 영역은 따로 표로 만든다
  2. 글자층이 있는 페이지: pdfplumber 로 글자를 그대로 꺼낸다 (OCR 보다 정확)
     글자층이 없는 페이지(스캔본): RapidOCR(PP-OCRv5 한국어)로 읽는다
     글자층이 있어도 큰 그림 안에 글자가 있으면 그 부분만 OCR 한다
  3. 표: 세 가지로 만들어 보고 고른다 (build_table 설명 참고)
     - pdfplumber 괘선 표 / 글자 좌표로 짠 표 / rapid-table(이미지로 구조 인식, 216 DPI)
     rapid-table 에는 OCR 결과 대신 pdfplumber 글자를 넣어 글자 오인식이 없게 한다
     (스캔본이면 OCR 결과를 넣음).
     괘선 표는 바깥 세로 테두리가 빠져 있으면 보충해서 찾는다.
  4. 줄을 문단으로 합치고 '제N조' 를 제목(##)으로, ①·1.·가. 항목을 새 문단으로 만든다.

줄바꿈 이음 (Joiner):
  이 문서들은 단어 중간('홈\\n페이지')과 단어 경계('거래에\\n적용하고') 모두에서 줄이 바뀐다.
  그래서 줄바꿈 자리의 앞뒤 글자가 같은 문서의 다른 곳에서 붙어 나왔는지('홈페이지')
  띄어 나왔는지('를 정')를 세어 많은 쪽을 따른다. 근거가 없으면 앞 글자가 조사·어미
  (은·는·을·를·에·의 …)면 띄우고 아니면 붙인다. 표 칸 안의 줄바꿈도 같은 규칙을 쓴다.

알려진 한계:
  - 줄바꿈 이음은 통계 추정이라 문서에 한 번만 나오는 단어는 틀릴 수 있다.
  - 병합 셀은 행으로 병합된 경우 아래 행에도 같은 값을 복사한다(행마다 뜻이 통하도록).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")  # rapid-table 진행 막대 끄기
logging.disable(logging.WARNING)  # pdfminer FontBBox 경고·모델 로그 끄기

import numpy as np  # noqa: E402
import pdfplumber  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "data" / "rag" / "terms"

DPI = 144  # 레이아웃 인식·OCR 용 렌더링 해상도
TABLE_DPI = 216  # 표 구조 인식용 (표 영역만 다시 렌더링)
SCALE = DPI / 72  # PDF 좌표(pt) → 이미지 픽셀
MIN_TEXT_CHARS = 30  # 이보다 글자가 적으면 스캔 페이지로 보고 OCR
MIN_IMAGE_AREA = 20000  # pt². 이보다 큰 그림 영역만 OCR (로고·아이콘 제외)
EDGE = 0.12  # 페이지 위·아래 12% 를 머리말·꼬리말 후보로 본다

# 우리은행 웹페이지를 PDF 로 저장한 문서의 메뉴·푸터 (guides/ 등에도 쓰임)
BOILERPLATE_LINES = [
    r"로그인 인증센터",
    r"고객상담 소비자정보 .*",
    r"고객광장 개인회원서비스 .*",
    r"홈페이지\s?가입고객",
    r"\d 약관동의( \d)+",
    r"확인 취소",
]
# 이 줄이 나오면 문서 끝까지 버린다 (웹페이지 하단 푸터)
TAIL_MARKERS = [r"인터넷뱅킹 이용안내.*", r"COPYRIGHTS WOORI BANK.*"]
PAGE_NUMBER = re.compile(r"[-–—]?\s*\d{1,3}\s*[-–—]?|\d{1,3}\s*/\s*\d{1,3}|page \d+", re.I)

ARTICLE = re.compile(r"^(?:[-–]\s*)?(제\s*\d+\s*조(?:\s*의\s*\d+)?)\s*(\([^)]{1,40}\)|（[^）]{1,40}）)?\s*(.*)$")
# '제11조 에 불구하고', '제5조(…)에 따라', '제3조 제2항' 처럼 조항을 인용하는 본문 줄
# ('이'·'가'·'은'·'는' 은 '제3조 이 자'·'제2조 이자' 같은 제목과 겹쳐서 넣지 않는다)
CROSS_REF = re.compile(r"^((에|의|을|를|와|과|및|부터|까지|에서|에도|에는|에 따라|에 불구하고)(\s|$)|제\s*\d+\s*[항호]|각\s*호|단서|후단|전단)")
DOC_TITLE = re.compile(r"^[^.。:]{2,30}(약관|특약|규약|규정)$")
CHAPTER = re.compile(r"^(제\s*\d+\s*[장편절])\s*(.*)$")
ANNEX = re.compile(r"^(부\s*칙)\s*(.*)$")
ITEM = re.compile(
    r"^([①-⑳]|\(\d{1,2}\)|\d{1,2}\.\s|\d{1,2}\)\s|주\s?\d{1,2}\)|[가-하]\.\s|[가-하]\)\s|[※*＊○•◦▶■□]|-\s|<[^>]{1,30}>$)"
)
SENTENCE_END = (".", "다", ":", "”", '"', "?", "!", "。")
# ')' 는 '…합니다)'·'…포함.)' 처럼 안에서 문장이 끝났을 때만 문장 끝 ('인터넷(스마트)' + '홈페이지를' 은 이어짐)
PAREN_END = re.compile(r"[.。다음함임됨]\s*[)）]$")

HANGUL = re.compile(r"[가-힣]")
SOME_TEXT = re.compile(r"[가-힣A-Za-z0-9]")  # 기호만 남은 줄(꼬리말 찌꺼기)은 버림
HANGUL_ORDER = "가나다라마바사아자차카타파하"
HANGUL_ITEM = re.compile(rf"^([{HANGUL_ORDER}])[.)]\s")  # '가.'·'다.' — 줄 앞 '다. 다만' 같은 문장 끝과 헷갈림
W = "가-힣A-Za-z0-9"  # 낱말 글자
WORD_FINAL = set("은는이가을를에의로와과고며서한된될할및등도만면게지")  # 어절 끝에 잘 오는 조사·어미
PARTICLE_START = set("이가을를은는의에으로와과도")  # ')' 뒤에 붙는 조사


def ends_sentence(t: str) -> bool:
    return t.endswith(SENTENCE_END) or bool(PAREN_END.search(t))


# ───────────────────────── 줄바꿈 이음 ─────────────────────────
class Corpus:
    """줄 단위 글자 모음. 정규식 출현 횟수를 세고 기억해 둔다."""

    def __init__(self, lines: list[str]):
        self.text = "\n".join(" ".join(t.split()) for t in lines)
        self._cache: dict[str, int] = {}

    def count(self, pattern: str) -> int:
        if pattern not in self._cache:
            self._cache[pattern] = len(re.findall(pattern, self.text))
        return self._cache[pattern]


class Joiner:
    """줄바꿈 자리를 붙여 쓸지 띄어 쓸지 다른 줄에 나온 형태를 보고 정한다 (모듈 설명 참고).
    corpora 는 가까운 순서(이 문서 → 같은 폴더 전체)로 준다.
    riders 줄 안 띄어쓰기로 시뮬레이션해 보니 '붙여야 할 곳' 99%, '띄어야 할 곳' 91% 를 맞혔다
    (이 문서만 볼 때 70%, 근거 없이 조사·어미 규칙만 쓸 때 45%)."""

    def __init__(self, *corpora: Corpus):
        self.corpora = [c for c in corpora if c is not None]

    def glue(self, a: str, b: str) -> bool:
        """a 의 끝과 b 의 앞을 띄어쓰기 없이 붙여야 하면 True."""
        a, b = a.rstrip(), b.lstrip()
        ma, mb = re.search(f"[{W}]+$", a), re.match(f"[{W}]+", b)
        if not a or not mb:
            return False
        c2 = b[0]
        if not ma:  # 앞이 문장부호로 끝남
            return a[-1] in ")]" and c2 in PARTICLE_START
        la, fb = ma.group(0), mb.group(0)
        # 줄바꿈 앞뒤 3·2·1글자로 '붙은 형태' 와 '띄운 형태' 의 출현 횟수를 비교 (긴 문맥·가까운 말뭉치 먼저)
        for k in (3, 2, 1):
            left = re.escape(la[-k:]) if len(la) > k else f"(?<![{W}])" + re.escape(la)
            right = re.escape(fb[:k]) if len(fb) > k else re.escape(fb) + f"(?![{W}])"
            for corpus in self.corpora:
                joined, spaced = corpus.count(left + right), corpus.count(left + " " + right)
                if joined != spaced:
                    return joined > spaced
        # 근거가 없을 때
        c1 = la[-1]
        if HANGUL.match(c1) and HANGUL.match(c2):
            return not (len(la) >= 2 and c1 in WORD_FINAL)
        return c1.isdigit()  # '제91' + '조의22', '100' + '만원'

    def join(self, a: str, b: str) -> str:
        if not a:
            return b
        return a + ("" if self.glue(a, b) else " ") + b


def read_lines(pdf_path: Path) -> list[str]:
    with pdfplumber.open(pdf_path) as pdf:
        return [ln for page in pdf.pages for ln in (page.extract_text() or "").splitlines()]


# ───────────────────────── 모델 (처음 쓸 때 만든다) ─────────────────────────
class Engines:
    def __init__(self):
        self._layout = self._ocr = self._table = None

    @property
    def layout(self):
        if self._layout is None:
            from rapid_layout import ModelType, RapidLayout, RapidLayoutInput

            self._layout = RapidLayout(cfg=RapidLayoutInput(model_type=ModelType.PP_DOC_LAYOUTV3))
        return self._layout

    @property
    def ocr(self):
        if self._ocr is None:
            self._ocr = _make_ocr()
        return self._ocr

    @property
    def table(self):
        if self._table is None:
            from rapid_table import RapidTable, RapidTableInput

            # OCR 결과는 항상 직접 넘기므로 rapid-table 안의 OCR 은 쓰지 않는다
            self._table = RapidTable(RapidTableInput(use_ocr=True, ocr_params=_ocr_params()))
            self._table.ocr_engine = None
        return self._table


def _ocr_params():
    from rapidocr import LangRec, ModelType, OCRVersion

    return {
        "Det.ocr_version": OCRVersion.PPOCRV5,
        "Det.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.lang_type": LangRec.KOREAN,
    }


def _make_ocr():
    from rapidocr import RapidOCR

    return RapidOCR(params=_ocr_params())


# ───────────────────────── 자료 구조 ─────────────────────────
@dataclass
class Line:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page: int
    page_width: float = 0.0
    page_height: float = 0.0


@dataclass
class TableBlock:
    rows: list[list[str]]
    top: float
    page: int
    source: str  # pdfplumber / rapid-table


@dataclass
class Region:
    label: str
    box: tuple[float, float, float, float]  # PDF pt (x0, top, x1, bottom)


@dataclass
class Stats:
    pages: int = 0
    ocr_pages: int = 0
    ocr_images: int = 0
    tables: dict = field(default_factory=lambda: {"pdfplumber": 0, "geometry": 0, "rapid-table": 0, "text": 0})


# ───────────────────────── 영역·좌표 도우미 ─────────────────────────
def inside(x, y, box, pad=3.0):
    return box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad


def center_in_any(obj, boxes, pad=3.0):
    cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
    return any(inside(cx, cy, b, pad) for b in boxes)


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def nonspace_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def detect_regions(engines: Engines, img: np.ndarray, w: float, h: float) -> list[Region]:
    res = engines.layout(img)
    regions = []
    for box, label in zip(res.boxes or [], res.class_names or []):
        x0, y0, x1, y1 = (v / SCALE for v in box)
        regions.append(Region(label, (x0, y0, x1, y1)))
    return regions


def split_regions(regions: list[Region], w: float, h: float):
    """버릴 영역 / 표 영역 / 그림 영역으로 나눈다."""
    drop, tables, images = [], [], []
    for r in regions:
        x0, y0, x1, y1 = r.box
        near_top_or_bottom = y1 < h * EDGE * 1.3 or y0 > h * (1 - EDGE)
        if r.label in ("header", "footer", "number") and near_top_or_bottom:
            drop.append(r.box)
        elif r.label in ("header_image", "footer_image", "seal"):
            drop.append(r.box)
        elif r.label == "aside_text" and (x1 < w * 0.1 or x0 > w * 0.9):
            drop.append(r.box)
        elif r.label == "table":
            if not any(iou(r.box, t) > 0.5 for t in tables):
                tables.append(r.box)
        elif r.label in ("image", "figure", "chart") and (x1 - x0) * (y1 - y0) >= MIN_IMAGE_AREA:
            images.append(r.box)
    return drop, tables, images


# ───────────────────────── 표 ─────────────────────────
def _cluster(values, tol=2.0):
    out = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _idx(coords, v, tol=2.0):
    return min(range(len(coords)), key=lambda i: abs(coords[i] - v)) if coords else 0


def _outer_borders(page, region) -> list[dict]:
    """가로선은 있는데 표 양 끝 세로 테두리가 없으면 (첫 열·끝 열이 셀로 안 잡힘) 세로선을 만든다."""
    x0, y0, x1, y1 = region
    hs = [
        e
        for e in page.edges
        if e["orientation"] == "h" and y0 - 5 <= e["top"] <= y1 + 5 and e["x1"] > x0 - 5 and e["x0"] < x1 + 5
    ]
    if len(hs) < 2:
        return []
    top, bottom = min(e["top"] for e in hs), max(e["top"] for e in hs)
    out = []
    for x in (min(e["x0"] for e in hs), max(e["x1"] for e in hs)):
        has = any(
            e["orientation"] == "v" and abs(e["x0"] - x) <= 2 and e["top"] <= top + 2 and e["bottom"] >= bottom - 2
            for e in page.edges
        )
        if not has:
            out.append(
                {
                    "object_type": "line",
                    "x0": x,
                    "x1": x,
                    "top": top,
                    "bottom": bottom,
                    "doctop": page.initial_doctop + top,
                    "y0": float(page.height) - bottom,
                    "y1": float(page.height) - top,
                    "width": 0.0,
                    "height": bottom - top,
                }
            )
    return out


def cell_text(words, joiner: Joiner) -> str:
    """칸 안 글자들을 줄로 묶고(위첨자도 같은 줄로) 줄바꿈을 Joiner 로 잇는다."""
    text = ""
    for ln in words_to_lines(words, 0):
        text = joiner.join(text, ln.text)
    return text


def plumber_table(page, region, joiner: Joiner) -> tuple[list[list[str]] | None, tuple | None]:
    """괘선으로 그려진 표를 셀 좌표로 다시 짜서 병합 셀까지 살린다."""
    best = None
    # 점선 행 구분선은 1pt 미만 점들로 그려진다 → 기본값(1pt 미만 먼저 버림)이면 선이 끊겨 행이 뭉친다
    settings: dict = {"edge_min_length_prefilter": 0.1}
    if borders := _outer_borders(page, region):
        settings["explicit_vertical_lines"] = borders
    tables = page.find_tables(settings)
    page_words = [(x["x0"], x["top"], x["x1"], x["bottom"], x["text"]) for x in page.extract_words()]
    for t in tables:
        score = iou(t.bbox, region)
        if score > 0.5 and (best is None or score > best[0]):
            best = (score, t)
    if best is None:
        return None, None
    table = best[1]
    cells = [c for c in table.cells if c[2] - c[0] > 1 and c[3] - c[1] > 1]
    xs = _cluster([c[0] for c in cells] + [c[2] for c in cells])
    ys = _cluster([c[1] for c in cells] + [c[3] for c in cells])
    if len(xs) < 3 or len(ys) < 3:
        return None, None
    grid = [[None] * (len(xs) - 1) for _ in range(len(ys) - 1)]
    for c in cells:
        c0, c1 = _idx(xs, c[0]), _idx(xs, c[2])
        r0, r1 = _idx(ys, c[1]), _idx(ys, c[3])
        if c1 <= c0 or r1 <= r0:
            continue
        text = cell_text([w for w in page_words if inside((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, c, 1.0)], joiner)
        for r in range(r0, r1):
            for col in range(c0, c1):
                if grid[r][col] is None:
                    # 행 병합은 값 복사, 열 병합은 첫 칸에만
                    grid[r][col] = text if col == c0 else ""
    rows = [[c or "" for c in row] for row in grid]
    rows = [r for r in rows if any(r)]
    return (rows or None), table.bbox


class _TableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._span = [], None, None, (1, 1)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            self._span = (int(a.get("rowspan", 1) or 1), int(a.get("colspan", 1) or 1))

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None:
            self._row.append((" ".join("".join(self._cell).split()), *self._span))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_to_grid(html: str) -> list[list[str]]:
    p = _TableHTML()
    p.feed(html)
    grid: dict[tuple[int, int], str] = {}
    for r, row in enumerate(p.rows):
        c = 0
        for text, rs, cs in row:
            while (r, c) in grid:
                c += 1
            for dr in range(rs):
                for dc in range(cs):
                    grid[(r + dr, c + dc)] = text if dc == 0 else ""
            c += cs
    if not grid:
        return []
    nr = max(k[0] for k in grid) + 1
    nc = max(k[1] for k in grid) + 1
    rows = [[grid.get((r, c), "") for c in range(nc)] for r in range(nr)]
    return [r for r in rows if any(r)]


def rapid_table(engines, page, region, words) -> list[list[str]] | None:
    """words: [(x0, top, x1, bottom, text)] PDF 좌표. 이미지에서 구조만 읽고 글자는 words 를 쓴다.
    표 부분만 TABLE_DPI 로 다시 렌더링한다 (144 DPI 에서는 두 줄 셀·병합 셀을 자주 틀림)."""
    pad = 4
    x0, y0 = max(0, region[0] - pad), max(0, region[1] - pad)
    x1, y1 = min(float(page.width), region[2] + pad), min(float(page.height), region[3] + pad)
    if x1 <= x0 or y1 <= y0 or not words:
        return None
    crop = np.array(page.crop((x0, y0, x1, y1)).to_image(resolution=TABLE_DPI).original.convert("RGB"))
    k = TABLE_DPI / 72
    boxes, txts = [], []
    for wx0, wt, wx1, wb, text in words:
        a, b, c, d = (wx0 - x0) * k, (wt - y0) * k, (wx1 - x0) * k, (wb - y0) * k
        boxes.append([[a, b], [c, b], [c, d], [a, d]])
        txts.append(text)
    try:
        out = engines.table(crop, ocr_results=[(np.array(boxes, dtype=np.float32), tuple(txts), tuple([1.0] * len(txts)))])
    except Exception as e:  # 표 인식 실패는 글자로 대신 낸다
        print(f"    ! rapid-table 실패: {e}", file=sys.stderr)
        return None
    html = out.pred_htmls[0] if out.pred_htmls else ""
    return html_to_grid(html) or None


def table_markdown(rows: list[list[str]]) -> str:
    width = max(len(r) for r in rows)
    esc = lambda s: (s or "").replace("|", "\\|").strip()  # noqa: E731
    rows = [[esc(c) for c in r] + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def geometry_table(page, region, words, joiner: Joiner) -> list[list[str]] | None:
    """글자 좌표로 표를 짠다 (세로선이 없거나 점선뿐인 표용).
    열 = 글자가 하나도 없는 세로 빈틈, 행 = 표 안의 가로선 + 첫 열 글자 덩어리."""
    if len(words) < 4:
        return None
    x0, y0, x1, y1 = region
    # 열: x 방향 투영의 빈틈
    spans = sorted((w[0], w[2]) for w in words)
    cols, (cs, ce) = [], spans[0]
    for s, e in spans[1:]:
        if s - ce >= 6:  # 6pt 이상 비면 열 경계
            cols.append((cs, ce))
            cs, ce = s, e
        else:
            ce = max(ce, e)
    cols.append((cs, ce))
    if len(cols) < 2:
        return None
    col_of = lambda w: next(i for i, (s, e) in enumerate(cols) if s - 0.5 <= w[0] <= e + 0.5)  # noqa: E731

    # 행 1단계: 표 폭의 절반 이상을 가로지르는 가로선 (칸마다 끊긴 선분은 같은 높이끼리 길이를 합친다)
    widths: dict[int, float] = {}
    for e in page.edges:
        if e["orientation"] == "h" and y0 - 2 <= e["top"] <= y1 + 2 and e["x1"] > x0 and e["x0"] < x1:
            y = round(e["top"])
            widths[y] = widths.get(y, 0) + min(e["x1"], x1) - max(e["x0"], x0)
    rules = _cluster([y for y, wd in widths.items() if wd >= (x1 - x0) * 0.5], tol=2.0)
    bounds = [y0 - 3] + [r for r in rules if y0 + 3 < r < y1 - 3] + [y1 + 3]
    bands = [[w for w in words if bounds[i] <= (w[1] + w[3]) / 2 < bounds[i + 1]] for i in range(len(bounds) - 1)]

    rows = []
    for band in (b for b in bands if b):
        # 행 2단계: 가로선 없이 붙은 행은 첫 열의 글자 덩어리(줄 간격이 벌어진 곳)로 나눈다
        first = sorted((w for w in band if col_of(w) == 0), key=lambda w: w[1])
        anchors, blk = [], []
        for w in first:
            if blk and w[1] - max(b[3] for b in blk) > 0.8 * (w[3] - w[1]):
                anchors.append(blk)
                blk = []
            blk.append(w)
        if blk:
            anchors.append(blk)
        centers = [(min(b[1] for b in a) + max(b[3] for b in a)) / 2 for a in anchors] or [0]
        groups = [[] for _ in centers]
        for w in band:
            cy = (w[1] + w[3]) / 2
            groups[min(range(len(centers)), key=lambda i: abs(centers[i] - cy))].append(w)
        for g in groups:
            cells = [[] for _ in cols]
            for w in g:
                cells[col_of(w)].append(w)
            rows.append(cells)
    if len(rows) < 2:
        return None

    # 한 행에만 글자가 있는 열은 '구 분' 처럼 자간이 벌어진 머리글이 쪼개진 것 → 가까운 옆 열에 합친다
    if len(rows) >= 3:
        j = 0
        while len(cols) > 2 and j < len(cols):
            if sum(1 for r in rows if r[j]) > 1:
                j += 1
                continue
            gap_l = cols[j][0] - cols[j - 1][1] if j > 0 else float("inf")
            gap_r = cols[j + 1][0] - cols[j][1] if j + 1 < len(cols) else float("inf")
            n = j - 1 if gap_l <= gap_r else j + 1
            for r in rows:
                r[n] = r[n] + r[j]
                del r[j]
            lo, hi = min(n, j), max(n, j)
            cols[lo] = (min(cols[lo][0], cols[hi][0]), max(cols[lo][1], cols[hi][1]))
            del cols[hi]
            j = 0
    return [[cell_text(c, joiner) for c in r] for r in rows]


def build_table(
    engines, page, region, words, stats, page_no, w, h, joiner: Joiner, text_layer=True
) -> TableBlock | list[Line]:
    """표 하나를 세 가지 방법으로 만들어 보고 고른다.
    - pdfplumber: 괘선이 다 그려진 표에서 가장 정확 → 표 안 글자를 다 담았으면 우선.
      단 행 구분선이 없어 여러 행이 한 칸에 뭉친 경우(좌표 표가 같은 열 수로 행을 더 많이 찾음)는 뺀다
    - geometry: 글자 좌표로 짠 표 → 열 수가 rapid-table 이상일 때 (rapid-table 은 선 없는 열을 합치기도 함.
      좌표 표가 열을 잘못 쪼개는 경우는 geometry_table 안에서 한 행에만 쓰인 열을 합쳐 막는다)
    - rapid-table: 이미지로 구조를 읽는다 → 위 둘이 안 되거나 스캔본일 때"""
    expected = sum(nonspace_len(w[4]) for w in words)

    def coverage(rows):
        # 표 영역의 단어 중 표 칸에 실제로 들어간 비율 (병합값 복사로 부풀지 않게 단어 단위로 센다)
        if not rows:
            return 0.0
        cells = re.sub(r"\s+", "", "".join(c for r in rows for c in r))
        found = sum(nonspace_len(w[4]) for w in words if re.sub(r"\s+", "", w[4]) in cells)
        return found / expected if expected else 0.0

    plumber = plumber_table(page, region, joiner)[0] if text_layer else None
    rapid = rapid_table(engines, page, region, words)
    geom = geometry_table(page, region, words, joiner) if text_layer else None
    ncols = lambda rows: max(len(r) for r in rows) if rows else 0  # noqa: E731
    # 괘선 표가 여러 행(행 구분선 없음)이나 여러 열(안쪽 세로선 없음)을 한 칸에 뭉쳤나.
    # 열은 좌표 표와 rapid-table 이 둘 다 더 많이 찾았을 때만 뭉친 것으로 본다
    lumped = bool(
        plumber
        and geom
        and coverage(geom) >= 0.98
        and (
            (ncols(geom) == ncols(plumber) and len(geom) > len(plumber))
            or (
                ncols(geom) > ncols(plumber)
                and len(geom) >= len(plumber)
                and rapid
                and ncols(rapid) >= ncols(geom)
            )
        )
    )

    if plumber and coverage(plumber) >= 0.98 and not lumped:
        choice = ("pdfplumber", plumber)
    elif geom and coverage(geom) >= 0.98 and (not rapid or ncols(geom) >= ncols(rapid)):
        choice = ("geometry", geom)
    else:
        cands = [(n, r) for n, r in (("rapid-table", rapid), ("pdfplumber", plumber), ("geometry", geom)) if r]
        choice = max(cands, key=lambda c: coverage(c[1])) if cands else None
    if choice and len(choice[1]) >= 2 and coverage(choice[1]) >= 0.8:
        name, rows = choice
        stats.tables[name] += 1
        return TableBlock(rows, region[1], page_no, name)
    # 표로 못 만들면 글자를 잃지 않도록 줄로 낸다
    stats.tables["text"] += 1
    return words_to_lines(words, page_no, w, h)


# ───────────────────────── 글자 → 줄 ─────────────────────────
def words_to_lines(words, page_no, w=0.0, h=0.0) -> list[Line]:
    """(x0, top, x1, bottom, text) 상자들을 세로 위치로 묶어 줄로 만든다.
    세로로 절반 이상 겹치면 같은 줄로 본다 (위첨자 '주8)' 가 다른 줄로 떨어지지 않게)."""
    lines: list[list] = []
    for wd in sorted(words, key=lambda b: (b[1], b[0])):
        if lines:
            last = lines[-1]
            lt, lb = min(b[1] for b in last), max(b[3] for b in last)
            overlap = min(lb, wd[3]) - max(lt, wd[1])
            if overlap >= 0.5 * min(lb - lt, wd[3] - wd[1]):
                last.append(wd)
                continue
        lines.append([wd])
    out = []
    for group in lines:
        group.sort(key=lambda b: b[0])
        out.append(
            Line(
                " ".join(b[4] for b in group),
                min(b[0] for b in group),
                max(b[2] for b in group),
                min(b[1] for b in group),
                max(b[3] for b in group),
                page_no,
                w,
                h,
            )
        )
    return out


def ocr_words(engines, img, offset=(0.0, 0.0)):
    """이미지를 OCR 해서 (x0, top, x1, bottom, text) 를 PDF 좌표로 돌려준다."""
    res = engines.ocr(img)
    if res is None or res.boxes is None or res.txts is None:
        return []
    out = []
    for box, text in zip(res.boxes, res.txts):
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append(
            (
                min(xs) / SCALE + offset[0],
                min(ys) / SCALE + offset[1],
                max(xs) / SCALE + offset[0],
                max(ys) / SCALE + offset[1],
                text.strip(),
            )
        )
    return [w for w in out if w[4]]


# ───────────────────────── 페이지 처리 ─────────────────────────
def process_page(engines, page, page_no, stats, joiner: Joiner) -> list:
    w, h = float(page.width), float(page.height)
    img = np.array(page.to_image(resolution=DPI).original.convert("RGB"))
    drop, table_boxes, image_boxes = split_regions(detect_regions(engines, img, w, h), w, h)

    text_chars = sum(1 for c in page.chars if c["text"].strip())
    items: list = []

    if text_chars >= MIN_TEXT_CHARS:
        # ── 글자층이 있는 페이지: pdfplumber
        # 표 영역의 글자 (rapid-table 에 넣을 words)
        all_words = page.extract_words()
        for tb in table_boxes:
            words = [(x["x0"], x["top"], x["x1"], x["bottom"], x["text"]) for x in all_words if center_in_any(x, [tb])]
            res = build_table(engines, page, tb, words, stats, page_no, w, h, joiner)
            items.extend(res if isinstance(res, list) else [res])

        # 큰 그림 안에 글자층이 없으면 OCR
        for ib in image_boxes:
            if any(center_in_any(c, [ib], 0) for c in page.chars if c["text"].strip()):
                continue
            x0, y0, x1, y1 = ib
            crop = img[int(y0 * SCALE) : int(y1 * SCALE), int(x0 * SCALE) : int(x1 * SCALE)]
            words = ocr_words(engines, crop, (x0, y0))
            if words:
                stats.ocr_images += 1
                items.extend(words_to_lines(words, page_no, w, h))

        excluded = drop + table_boxes
        body = page.filter(lambda o: o.get("object_type") != "char" or not center_in_any(o, excluded))
        for ln in body.extract_text_lines(strip=True, return_chars=False):
            if ln["text"].strip():
                items.append(Line(ln["text"].strip(), ln["x0"], ln["x1"], ln["top"], ln["bottom"], page_no, w, h))
    else:
        # ── 스캔 페이지: 전체 OCR
        stats.ocr_pages += 1
        words = ocr_words(engines, img)
        for tb in table_boxes:
            tw = [x for x in words if inside((x[0] + x[2]) / 2, (x[1] + x[3]) / 2, tb)]
            res = build_table(engines, page, tb, tw, stats, page_no, w, h, joiner, text_layer=False)
            items.extend(res if isinstance(res, list) else [res])
        excluded = drop + table_boxes
        words = [x for x in words if not any(inside((x[0] + x[2]) / 2, (x[1] + x[3]) / 2, b) for b in excluded)]
        items.extend(words_to_lines(words, page_no, w, h))

    items.sort(key=lambda it: it.top)
    return items


# ───────────────────────── 머리말·꼬리말·웹 메뉴 제거 ─────────────────────────
def strip_boilerplate(items: list, n_pages: int) -> list:
    def key(t):
        return re.sub(r"\d+", "#", re.sub(r"\s+", "", t))

    edge_count: dict[str, set] = {}
    for it in items:
        if isinstance(it, Line) and (it.top < it.page_height * EDGE or it.bottom > it.page_height * (1 - EDGE)):
            edge_count.setdefault(key(it.text), set()).add(it.page)
    repeated = {k for k, pages in edge_count.items() if n_pages >= 2 and len(pages) >= max(2, n_pages * 0.5)}

    bp = [re.compile(p + r"$") for p in BOILERPLATE_LINES]
    tail = [re.compile(p + r"$") for p in TAIL_MARKERS]
    out = []
    for it in items:
        if isinstance(it, Line):
            t = it.text.strip()
            if any(p.match(t) for p in tail):
                break
            if PAGE_NUMBER.fullmatch(t) or any(p.match(t) for p in bp) or not SOME_TEXT.search(t):
                continue
            is_edge = it.top < it.page_height * EDGE or it.bottom > it.page_height * (1 - EDGE)
            if is_edge and key(t) in repeated:
                continue
        out.append(it)
    return out


# ───────────────────────── 줄 → 마크다운 ─────────────────────────
def collapse_spaced(t: str) -> str:
    """'거 치 식 예 금 약 관' → '거치식예금약관'"""
    return t.replace(" ", "") if re.fullmatch(r"(\S )+\S", t) else t


def norm_article(t: str) -> str:
    t = re.sub(r"제\s*(\d+)\s*조", r"제\1조", t)
    t = re.sub(r"조\s*의\s*(\d+)", r"조의\1", t)
    return re.sub(r"제\s*(\d+)\s*([장편절])", r"제\1\2", t)


def squash(t: str) -> str:
    return re.sub(r"\s+", "", t.lstrip("#").strip())


def to_markdown(items: list, joiner: Joiner) -> str:
    lines = [it for it in items if isinstance(it, Line)]
    has_chapter = any(CHAPTER.match(norm_article(ln.text)) for ln in lines)
    h_article = "###" if has_chapter else "##"

    # 페이지별 본문 왼쪽·오른쪽 끝 (줄이 짧게 끝났는지 판단용)
    left, right = {}, {}
    for pg in {ln.page for ln in lines}:
        xs = [ln.x1 for ln in lines if ln.page == pg and len(ln.text) >= 15]
        right[pg] = statistics.quantiles(xs, n=10)[-1] if len(xs) >= 3 else max(xs or [0])
        left[pg] = min((ln.x0 for ln in lines if ln.page == pg), default=0)

    out: list[str] = []
    para = ""
    prev: Line | None = None
    prev_ended = True
    last_mark: int | None = None  # 마지막 '가.'·'나.' 항목의 순서

    def emit(text: str):
        # 바로 앞 블록과 글자가 같으면(웹페이지 제목 중복 등) 한 번만
        if out and squash(out[-1]) == squash(text):
            return
        out.append(text)

    def flush():
        nonlocal para
        if para.strip():
            emit(para.strip())
        para = ""

    for it in items:
        if isinstance(it, TableBlock):
            flush()
            out.append(table_markdown(it.rows))
            prev, prev_ended = None, True
            continue

        t = it.text.strip()
        if not out and not para:
            emit("# " + collapse_spaced(t))
            prev, prev_ended = it, True
            continue

        # 앞 줄이 오른쪽 끝까지 가지 않고 끝났나 (= 문단·항목이 끝났거나 제목 줄)
        gap = (right.get(prev.page, 0) - prev.x1) if prev else 0
        height = (prev.bottom - prev.top) if prev else 10
        short_prev = prev is None or gap > 2 * height
        very_short_prev = prev is None or gap > 0.35 * (right.get(prev.page, 0) - left.get(prev.page, 0))
        boundary = prev_ended or short_prev
        # 이 줄 자체가 짧은 '제N조 …' 줄이면 앞 줄이 꽉 찬 목록 항목이어도 제목으로 본다
        cur_short = right.get(it.page, 0) - it.x1 > 2 * (it.bottom - it.top)

        nt = norm_article(t)
        heading = None
        rest = ""
        if not boundary and cur_short and (m := ARTICLE.match(nt)):
            paren, after = m.group(2), m.group(3).strip()
            if (paren and not after) or (not paren and 0 < len(after) <= 40 and not after.endswith(SENTENCE_END)):
                boundary = True
        if boundary:
            if m := CHAPTER.match(nt):
                heading = f"## {m.group(1)} {m.group(2)}".strip()
            elif m := ANNEX.match(nt):
                heading, rest = "## 부칙", m.group(2)
            elif (m := ARTICLE.match(nt)) and not CROSS_REF.match(m.group(3).strip()):
                num, paren, rest = m.group(1), m.group(2), m.group(3).strip()
                if paren:
                    heading = f"{h_article} {num}{paren}"
                elif len(rest) <= 40 and not rest.endswith(SENTENCE_END[:2]):
                    heading, rest = f"{h_article} {num} {collapse_spaced(rest)}".strip(), ""
            elif very_short_prev and DOC_TITLE.match(t) and not ITEM.match(t):
                heading = "## " + t  # 한 PDF 안에 다른 약관이 이어지는 경우
        if heading:
            last_mark = None
            flush()
            emit(heading)
            para = rest
            prev, prev_ended = it, not rest or ends_sentence(rest)
            continue

        # '가.'·'나.' 항목은 순서가 맞을 때만 ('…않습니' 다음 줄 '다. 다만' 은 이어지는 문장)
        is_item = bool(ITEM.match(t))
        if m := HANGUL_ITEM.match(t):
            k = HANGUL_ORDER.index(m.group(1))
            is_item = k == 0 or (last_mark is not None and k == last_mark + 1)
            if is_item:
                last_mark = k
        if is_item or (boundary and (prev_ended or very_short_prev)):
            flush()
            para = t
        else:
            para = joiner.join(para, t)
        # 오른쪽 끝까지 찬 줄이 '다'·')' 로 끝나면 문장 끝이 아니라 줄바꿈일 수 있다 ('…사람으로서 다' + '음 각 호')
        ended = ends_sentence(t) and not (not cur_short and t.endswith(("다", ")")))
        prev, prev_ended = it, ended
    flush()
    return "\n\n".join(out) + "\n"


# ───────────────────────── 실행 ─────────────────────────
def convert(pdf_path: Path, out_path: Path, engines: Engines, shared: Corpus | None = None) -> Stats:
    """shared: 같은 폴더 PDF 전체 글자 (줄바꿈 이음 판단용, 없으면 이 문서만 본다)"""
    stats = Stats()
    items: list = []
    joiner = Joiner(Corpus(read_lines(pdf_path)), shared)
    with pdfplumber.open(pdf_path) as pdf:
        stats.pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            items.extend(process_page(engines, page, i, stats, joiner))
    items = strip_boilerplate(items, stats.pages)
    body = to_markdown(items, joiner)
    front = f"---\nsource: {pdf_path.name}\npages: {stats.pages}\n---\n\n"
    out_path.write_text(front + body, encoding="utf-8")
    return stats


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="PDF 를 RAG 용 Markdown 으로 변환")
    ap.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="PDF 폴더 또는 PDF 파일")
    ap.add_argument("--out", help="출력 폴더 (기본: PDF 와 같은 폴더)")
    args = ap.parse_args(argv)

    src = Path(args.input)
    pdfs = [src] if src.suffix.lower() == ".pdf" else sorted(src.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"PDF 가 없습니다: {src}")
    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    engines = Engines()
    # 줄바꿈 이음 판단용: 같은 폴더 PDF 들의 글자 전체 (파일 하나만 변환해도 폴더 단위 결과와 같게)
    siblings = sorted({p for pdf in pdfs for p in pdf.parent.glob("*.pdf")})
    shared = Corpus([ln for p in siblings for ln in read_lines(p)])
    failed = 0
    for pdf in pdfs:
        out = (out_dir or pdf.parent) / (pdf.stem + ".md")
        try:
            s = convert(pdf, out, engines, shared)
        except Exception as e:
            failed += 1
            print(f"✗ {pdf.name}: {e}", file=sys.stderr)
            continue
        t = s.tables
        print(
            f"✓ {pdf.name} → {out.name}  ({s.pages}쪽 | 표: pdfplumber {t['pdfplumber']}, 좌표 {t['geometry']},"
            f" rapid-table {t['rapid-table']}, 글자로 {t['text']} | OCR: 페이지 {s.ocr_pages}, 그림 {s.ocr_images})"
        )
    print(f"\n완료: {len(pdfs) - failed}/{len(pdfs)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
