"""회원가입 — 기획서 Part 1 AUTH-F01(가입) · F02(아이디 중복 확인) · F03(이메일 인증) · F10(약관), 7장 API.

화면(frontend/src/pages/SignupPage.tsx) 순서
  GET  /terms                               가입 화면에 보여 줄 공통 약관
  GET  /terms/{terms_id}                    약관 본문 (「보기」 · 마이페이지 「자세히 보기」)
  GET  /auth/usernames/availability         아이디 중복 확인 (확인 결과는 예약이 아님 — 가입 때 다시 검사)
  POST /auth/email-verifications            인증번호 발송 — SMTP 메일로 보낸다(app/mailer.py). 번호는 응답에 없다
                                            (테스트만 EMAIL_DEV_CODE=true 로 응답 dev_code 에 받는다)
  POST /auth/email-verifications/confirm    인증번호 확인 → 인증 토큰
  POST /auth/register                       모든 값을 서버가 다시 검사 → users·auth_identities·local_credentials·
                                            user_consents 를 한 트랜잭션으로 만들고 바로 로그인(쿠키)

이메일 인증 행(email_verifications) 하나의 일생
  발송: challenge_digest = SHA-256(행 id:인증번호), expires_at = 지금+5분
  확인: 맞으면 used_at = 지금, challenge_digest 를 SHA-256(인증 토큰)으로 바꿔 「인증 완료 표」로 쓴다
  가입: 그 토큰으로 행을 찾아 확인한 뒤 행을 지운다(토큰 1회용)
  같은 이메일·용도로 새 번호를 받으면 가장 최근 행만 유효하다(이전 번호는 자동으로 무효).
"""

import re
import secrets
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import DB
from app.errors import ApiError
from app.mailer import MailError, send_code_mail
from app.models import AuthIdentity, EmailVerification, LocalCredential, Terms, User, UserConsent
from app.routers.auth import _audit, start_session
from app.rules import (
    EMAIL_CODE_MAX_ATTEMPTS,
    EMAIL_CODE_TTL,
    EMAIL_DAILY_SENDS,
    EMAIL_PURPOSES,
    EMAIL_RE,
    EMAIL_RESEND_WAIT,
    EMAIL_VERIFIED_TTL,
    NAME_RE,
    PASSWORD_MAX,
    PASSWORD_MIN,
    USERNAME_RE,
    now_kst,
)
from app.schemas import KstDatetime
from app.security import digest, hash_password, new_email_code, new_id

router = APIRouter(tags=["signup"])
Purpose = Literal[EMAIL_PURPOSES]


# --- 입력 검사 (화면 frontend/src/signupRules.ts 와 같은 규칙, 서버가 최종 판정) ---------------------------
def username_error(v: str) -> str | None:
    return None if re.fullmatch(USERNAME_RE, v) else "영문 소문자로 시작하는 4~20자(소문자·숫자·밑줄)로 입력해 주세요."


def password_error(pw: str, username: str) -> str | None:
    if not PASSWORD_MIN <= len(pw) <= PASSWORD_MAX:
        return f"비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자로 입력해 주세요."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"[0-9]", pw):
        return "비밀번호에 영문과 숫자를 모두 넣어 주세요."
    if username and username in pw.lower():
        return "아이디가 들어간 비밀번호는 쓸 수 없어요."
    return None


def normalize_email(v: str) -> str:
    email = v.strip().lower()  # 대소문자만 다른 이메일을 같은 주소로 본다
    if len(email) > 100 or not re.fullmatch(EMAIL_RE, email):
        raise ApiError(400, "INVALID_EMAIL", "이메일 형식을 확인해 주세요.")
    return email


def email_taken(db, email: str) -> bool:
    """1 이메일 = 1 계정. 탈퇴 회원의 이메일은 다시 쓸 수 있다."""
    return db.scalar(
        select(User.id).where(func.lower(User.email) == email, User.status != "WITHDRAWN").limit(1)
    ) is not None


def latest_verification(db, email: str, purpose: str, lock: bool = False) -> EmailVerification | None:
    q = (select(EmailVerification)
         .where(EmailVerification.email == email, EmailVerification.purpose == purpose)
         .order_by(EmailVerification.expires_at.desc()).limit(1))
    return db.scalar(q.with_for_update() if lock else q)


def take_email_proof(db, email: str, purpose: str, token: str) -> EmailVerification:
    """인증번호 확인(/confirm)이 준 토큰이 이 이메일·용도로 30분 안에 인증한 것인지 확인하고, 그 행을 잠가 돌려준다.
    잠그므로 같은 토큰을 동시에 두 번 써도 하나만 통과한다. 행을 지우는(토큰 1회용) 것은 부르는 쪽이 성공했을 때 한다."""
    proof = db.scalar(select(EmailVerification).where(
        EmailVerification.email == email, EmailVerification.purpose == purpose,
        EmailVerification.challenge_digest == digest(token),
        EmailVerification.used_at.is_not(None)).with_for_update())
    if proof is None or now_kst() > proof.used_at + EMAIL_VERIFIED_TTL:
        raise ApiError(400, "EMAIL_NOT_VERIFIED", "이메일 인증을 다시 해 주세요.")
    return proof


# --- 약관 (AUTH-F10) ----------------------------------------------------------------------------
class TermOut(BaseModel):
    id: str
    title: str
    required: bool
    version: str
    content_url: str


def common_terms(db) -> list[Terms]:
    """가입 때 동의받는 공통 약관(card_product_id 가 NULL). 필수 먼저."""
    return list(db.scalars(select(Terms).where(Terms.card_product_id.is_(None))
                           .order_by(Terms.required.desc(), Terms.id)))


@router.get("/terms", response_model=list[TermOut])
def list_terms(db: DB):
    return [TermOut(id=t.id, title=t.title, required=t.required, version=t.version, content_url=t.content_url)
            for t in common_terms(db)]


REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/routers/signup.py → 저장소 맨 위
TERMS_DIRS = (REPO_ROOT / "data", REPO_ROOT / "docs")  # 약관 본문은 이 두 폴더의 .md 만 읽는다(content_url 로 다른 파일을 못 열게)


class TermDetailOut(BaseModel):
    id: str
    title: str
    required: bool
    version: str
    effective_at: KstDatetime
    source: str | None  # 본문 파일 앞머리의 source: (원문 주소 또는 원본 PDF 이름)
    content: str | None  # Markdown 본문(앞머리·맨 위 # 제목 뺌). 파일이 아직 없으면 None → 화면이 「준비 중」


def read_terms_body(content_url: str) -> tuple[str | None, str | None]:
    """약관 본문 파일을 읽어 (본문, source) 를 돌려준다. 파일이 없거나 허용 폴더 밖이면 (None, None)."""
    path = (REPO_ROOT / content_url).resolve()
    if path.suffix != ".md" or not any(path.is_relative_to(d) for d in TERMS_DIRS) or not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    source = None
    if text.startswith("---\n"):  # 앞머리(crawl_toss_terms.py · pdf_to_md.py 가 적는 출처·시행일)
        head, _, text = text[4:].partition("\n---\n")
        source = next((line[7:].strip() for line in head.splitlines() if line.startswith("source:")), None)
    text = text.lstrip("\n")
    if text.startswith("# "):  # 제목은 화면이 따로 보여 준다
        text = text.partition("\n")[2]
    return text.strip() + "\n", source


@router.get("/terms/{terms_id}", response_model=TermDetailOut)
def get_terms(terms_id: str, db: DB):
    """약관 본문 — 가입 화면(로그인 전)과 마이페이지 「약관 및 동의 내역」이 같이 쓴다. 공개 정보라 로그인 없이."""
    t = db.get(Terms, terms_id)
    if t is None:
        raise ApiError(404, "TERMS_NOT_FOUND", "약관을 찾을 수 없어요.")
    content, source = read_terms_body(t.content_url)
    return TermDetailOut(id=t.id, title=t.title, required=t.required, version=t.version, effective_at=t.effective_at,
                         source=source, content=content)


# --- 아이디 중복 확인 (AUTH-F02) -------------------------------------------------------------------
@router.get("/auth/usernames/availability")
def username_availability(db: DB, username: str = Query(max_length=50)):
    """사용 가능 / 이미 있음(available=false) / 형식 오류(400) 를 구분한다.
    탈퇴 회원의 아이디도 users 에 남아 있으므로 다시 쓸 수 없다."""
    if err := username_error(username):
        raise ApiError(400, "INVALID_USERNAME", err)
    taken = db.scalar(select(User.id).where(User.username == username)) is not None
    return {"available": not taken}


# --- 이메일 인증 (AUTH-F03) ------------------------------------------------------------------------
class EmailSendIn(BaseModel):
    email: str = Field(max_length=254)
    purpose: Purpose = "SIGNUP"


class EmailSendOut(BaseModel):
    expires_at: KstDatetime
    resend_at: KstDatetime
    dev_code: str | None = None  # 테스트 전용(EMAIL_DEV_CODE=true 일 때만). 평소에는 번호가 메일로만 간다


@router.post("/auth/email-verifications", response_model=EmailSendOut, status_code=201)
def send_email_code(body: EmailSendIn, db: DB):
    email = normalize_email(body.email)
    if body.purpose == "SIGNUP" and email_taken(db, email):
        raise ApiError(409, "EMAIL_TAKEN", "이미 가입된 이메일이에요. 아이디 찾기를 이용해 주세요.")

    now = now_kst()
    last = latest_verification(db, email, body.purpose)
    if last is not None and now < last.expires_at - EMAIL_CODE_TTL + EMAIL_RESEND_WAIT:  # 보낸 시각 = 만료 − 5분
        raise ApiError(429, "EMAIL_RESEND_TOO_SOON", "잠시 뒤에 다시 받아 주세요.")
    sent_today = db.scalar(select(func.count()).select_from(EmailVerification).where(  # 지난 24시간에 보낸 횟수
        EmailVerification.email == email, EmailVerification.purpose == body.purpose,
        EmailVerification.expires_at > now - timedelta(days=1) + EMAIL_CODE_TTL))
    if sent_today >= EMAIL_DAILY_SENDS:
        raise ApiError(429, "EMAIL_SEND_LIMIT", "오늘은 인증번호를 더 받을 수 없어요. 내일 다시 시도해 주세요.")

    code = new_email_code()
    row = EmailVerification(id=new_id("evf"), email=email, purpose=body.purpose, expires_at=now + EMAIL_CODE_TTL,
                            attempt_count=0)
    row.challenge_digest = digest(f"{row.id}:{code}")  # 행 id 를 섞어 같은 번호라도 해시가 다르게
    db.add(row)
    # 메일을 먼저 보내고 성공해야 저장한다 — 못 보낸 번호가 재발송 대기·하루 횟수를 잡아먹지 않게
    try:
        send_code_mail(email, code, body.purpose, int(EMAIL_CODE_TTL.total_seconds() // 60))
    except MailError:
        db.rollback()
        raise ApiError(503, "EMAIL_SEND_FAILED", "인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.")
    db.commit()
    return EmailSendOut(expires_at=row.expires_at, resend_at=now + EMAIL_RESEND_WAIT,
                        dev_code=code if settings.email_dev_code else None)


class EmailConfirmIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=10, repr=False)
    purpose: Purpose = "SIGNUP"


@router.post("/auth/email-verifications/confirm")
def confirm_email_code(body: EmailConfirmIn, db: DB):
    email = normalize_email(body.email)
    row = latest_verification(db, email, body.purpose, lock=True)  # 동시에 두 번 맞혀도 토큰은 하나만
    if row is None or row.used_at is not None:
        raise ApiError(400, "EMAIL_VERIFICATION_NOT_FOUND", "인증번호를 먼저 받아 주세요.")
    if now_kst() >= row.expires_at:
        raise ApiError(400, "EMAIL_VERIFICATION_EXPIRED", "인증 시간이 만료되었습니다. 다시 요청해 주세요.")
    if row.attempt_count >= EMAIL_CODE_MAX_ATTEMPTS:
        raise ApiError(429, "EMAIL_VERIFICATION_LOCKED", "인증번호를 여러 번 틀렸어요. 인증번호를 다시 받아 주세요.")
    if not secrets.compare_digest(row.challenge_digest, digest(f"{row.id}:{body.code}")):
        row.attempt_count += 1
        db.commit()
        left = EMAIL_CODE_MAX_ATTEMPTS - row.attempt_count
        raise ApiError(400, "EMAIL_CODE_MISMATCH",
                       f"인증번호가 맞지 않아요. ({left}번 더 시도할 수 있어요)" if left else
                       "인증번호를 여러 번 틀렸어요. 인증번호를 다시 받아 주세요.")

    token = secrets.token_urlsafe(32)
    row.used_at = now_kst()
    row.challenge_digest = digest(token)  # 이제 이 행은 「이 이메일은 인증됨」 표. 토큰 원문은 DB 에 없다
    db.commit()
    return {"token": token}


# --- 회원가입 (AUTH-F01) --------------------------------------------------------------------------
class RegisterIn(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=128, repr=False)  # repr=False: 로그·오류 출력에 원문이 안 남게
    password_confirm: str = Field(max_length=128, repr=False)
    email: str = Field(max_length=254)
    email_verification_token: str = Field(max_length=100, repr=False)
    name: str = Field(max_length=50)
    birth_date: date
    gender: Literal["M", "F"]
    payday: int | None = Field(default=None, ge=1, le=31)
    agreed_term_ids: list[str] = Field(default_factory=list, max_length=50)


class RegisterOut(BaseModel):
    user_id: str
    username: str
    name: str
    status: str


@router.post("/auth/register", response_model=RegisterOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: DB):
    # 1. 입력값 다시 검사 (화면 검사는 편의일 뿐, AUTH-F01 정상 흐름 5)
    if err := username_error(body.username):
        raise ApiError(400, "INVALID_USERNAME", err)
    if err := password_error(body.password, body.username):
        raise ApiError(400, "INVALID_PASSWORD", err)
    if body.password != body.password_confirm:
        raise ApiError(400, "PASSWORD_MISMATCH", "비밀번호가 일치하지 않아요.")
    email = normalize_email(body.email)
    name = body.name.strip()
    if not re.fullmatch(NAME_RE, name):
        raise ApiError(400, "INVALID_NAME", "이름은 한글 또는 영문 2~20자로 입력해 주세요.")
    now = now_kst()
    if not date(1900, 1, 1) <= body.birth_date <= now.date():
        raise ApiError(400, "INVALID_BIRTH_DATE", "생년월일을 다시 확인해 주세요.")

    # 2. 이메일 인증 토큰 — 이 이메일·가입 용도로 30분 안에 인증한 것만. 잠가서 같은 토큰 두 번 가입을 막는다
    proof = take_email_proof(db, email, "SIGNUP", body.email_verification_token)

    # 3. 약관 — 공통 약관만 받고, 필수는 모두 동의해야 한다(AUTH-F10)
    terms = common_terms(db)
    agreed = set(body.agreed_term_ids)
    if not agreed <= {t.id for t in terms}:
        raise ApiError(400, "INVALID_TERMS", "약관 정보가 바뀌었어요. 새로고침 후 다시 동의해 주세요.")
    if not terms or any(t.required and t.id not in agreed for t in terms):
        raise ApiError(400, "REQUIRED_TERMS_NOT_AGREED", "필수 약관에 동의해 주세요.")

    # 4. 중복 — 가입 직전에 다시 확인. 동시에 같은 아이디가 들어오면 DB 고유 제약(uk_users_username)이 최종으로 막는다
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise ApiError(409, "USERNAME_TAKEN", "이미 사용 중인 아이디예요.")
    if email_taken(db, email):
        # shortcut: users.email 에 고유 제약이 없어 같은 이메일 동시 가입은 이 검사만 막는다, 실제 서비스면 docs/sql 에 부분 고유 색인 추가
        raise ApiError(409, "EMAIL_TAKEN", "이미 가입된 이메일이에요. 아이디 찾기를 이용해 주세요.")

    # 5. 만들기 — 회원·로그인 수단·비밀번호 해시·약관 동의를 한 트랜잭션으로 (하나라도 실패하면 모두 취소)
    user = User(id=new_id("user"), username=body.username, name=name, email=email, email_verified_at=proof.used_at,
                birth_date=body.birth_date, gender=body.gender, payday=body.payday, status="ACTIVE", created_at=now)
    db.add(user)
    try:
        # 회원을 먼저 넣는다: 모델에 relationship 이 없어 SQLAlchemy 가 표 순서를 모르므로(자식이 먼저 들어가면 외래 키 오류)
        db.flush()  # 동시에 같은 아이디로 가입하면 여기서 고유 제약 위반
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "USERNAME_TAKEN", "이미 사용 중인 아이디예요.")
    db.add(AuthIdentity(id=new_id("aid"), user_id=user.id, provider="LOCAL", provider_subject=body.username,
                        linked_at=now))
    db.add(LocalCredential(user_id=user.id, password_hash=hash_password(body.password), password_updated_at=now))
    for t in terms:  # '모두 동의'여도 항목별로, 동의 안 한 선택 약관도 agreed=false 로 남긴다
        db.add(UserConsent(id=new_id("cns"), user_id=user.id, terms_id=t.id, version=t.version,
                           agreed=t.id in agreed, recorded_at=now))
    db.delete(proof)  # 인증 토큰은 한 번만 쓴다

    # 6. 바로 로그인 (사용자 결정 2026-11-09: 가입 직후 ACTIVE + 자동 로그인)
    start_session(db, request, response, user.id)
    _audit(db, user.id, "SIGNUP", "SUCCESS", uuid.uuid4().hex)
    db.commit()
    return RegisterOut(user_id=user.id, username=user.username, name=user.name, status=user.status)
