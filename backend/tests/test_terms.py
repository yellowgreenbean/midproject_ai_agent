"""약관 본문 — GET /terms/{terms_id} (기획서 Part 1 AUTH-F10 정상 흐름 1 「적용 약관 내용 제공」 · 5 「마이페이지에서 열람」)."""

import pytest

from app.routers.signup import read_terms_body


def test_service_terms_body_is_toss_original_without_front_matter(client):
    r = client.get("/terms/trm_001")  # 로그인 없이(가입 화면에서도 본다)
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["title"], t["required"], t["version"]) == ("서비스 이용약관", True, "1.0")
    assert t["source"].startswith("https://toss.im/docs/11027")
    body = t["content"]
    assert not body.startswith("---") and not body.startswith("# ")  # 앞머리·맨 위 제목은 뺀다
    assert body.startswith("## 제1장 총칙") and "### 제1조 (목적)" in body


def test_electronic_terms_reads_md_conversion_not_pdf(client):
    t = client.get("/terms/trm_002").json()
    assert t["source"] == "electronic_financial_transactions_terms.pdf"
    assert "## 제1조(목적)" in t["content"]


@pytest.mark.parametrize("terms_id, title, headings", [
    # 개인정보 보호법 제15조 제2항이 알리라고 한 4가지(목적 · 항목 · 보유 기간 · 거부권과 불이익)가 다 있는지
    ("trm_003", "개인정보 수집·이용 동의", ["## 1. 수집·이용 목적", "## 2. 수집하는 개인정보 항목", "## 3. 보유 및 이용 기간",
                                    "## 4. 동의를 거부할 권리와 거부에 따른 불이익"]),
    ("trm_004", "마케팅 정보 수신 동의", ["## 1. 수집·이용 목적", "## 2. 이용하는 개인정보 항목", "## 4. 보유 및 이용 기간",
                                  "## 5. 동의를 거부할 권리와 철회 방법"]),
])
def test_written_consent_bodies_have_the_four_required_notices(client, terms_id, title, headings):
    t = client.get(f"/terms/{terms_id}").json()
    assert t["title"] == title and t["source"].startswith("두린은행 직접 작성")
    assert all(h in t["content"] for h in headings)


def test_unknown_terms_is_404(client):
    r = client.get("/terms/trm_999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "TERMS_NOT_FOUND"


@pytest.mark.parametrize("url", [
    "docs/terms/없는_파일.md",                         # 아직 본문 없음 → 화면이 「준비 중」
    "data/rag/terms/electronic_financial_transactions_terms.pdf",  # .md 만
    "backend/.env",                                   # 허용 폴더 밖
    "data/../backend/.env",                            # .. 로 빠져나가기
    "../../Windows/win.ini",
])
def test_body_is_none_for_missing_or_disallowed_files(url):
    assert read_terms_body(url) == (None, None)
