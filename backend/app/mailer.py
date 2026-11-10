"""인증번호 메일 보내기 (AUTH-F03) — 표준 라이브러리 smtplib 로 SMTP 서버에 보낸다(새 패키지 없음).

설정(backend/.env, app/config.py)
  SMTP_HOST · SMTP_PORT · SMTP_USER · SMTP_PASSWORD · MAIL_FROM
  Gmail 예: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USER=내주소@gmail.com,
           SMTP_PASSWORD=<Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호 16자리>  (계정 비밀번호가 아님)
  포트 465 면 처음부터 SSL, 그 밖(587 등)이면 STARTTLS 로 암호화한다.

SMTP_HOST 가 비어 있으면 메일 대신 서버 콘솔(로그)에 번호를 찍는다 — 메일 설정 없이 돌려 보는 팀원용.
번호가 화면·응답으로 나가지는 않으므로, 이때도 서버 콘솔을 본 사람만 인증할 수 있다.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

log = logging.getLogger(__name__)

BANK = "두린은행"
# 쓰임(purpose)마다 메일 제목에 들어갈 말
PURPOSE_TEXT = {
    "SIGNUP": "회원가입",
    "EMAIL_CHANGE": "이메일 변경",
    "USERNAME_RECOVERY": "아이디 찾기",
    "PASSWORD_RESET": "비밀번호 재설정",
}


class MailError(Exception):
    """메일 서버 접속·로그인·발송 실패."""


def build_code_mail(to: str, code: str, purpose: str, ttl_minutes: int) -> EmailMessage:
    what = PURPOSE_TEXT.get(purpose, "본인 확인")
    msg = EmailMessage()
    msg["Subject"] = f"[{BANK}] {what} 인증번호 {code}"
    msg["From"] = formataddr((BANK, settings.mail_from or settings.smtp_user))
    msg["To"] = to
    msg.set_content(
        f"{BANK} {what} 인증번호입니다.\n\n"
        f"    인증번호: {code}\n\n"
        f"{ttl_minutes}분 안에 화면에 입력해 주세요.\n"
        "본인이 요청하지 않았다면 이 메일을 무시해 주세요. 인증번호를 다른 사람에게 알려 주지 마세요.\n"
    )
    return msg


def send_code_mail(to: str, code: str, purpose: str, ttl_minutes: int) -> None:
    """인증번호 메일을 보낸다. 실패하면 MailError — 부르는 쪽이 인증 행을 저장하지 않도록."""
    if not settings.smtp_host:
        log.warning("SMTP_HOST 가 없어 메일 대신 콘솔에 찍습니다: [%s] %s 인증번호 %s", purpose, to, code)
        return
    msg = build_code_mail(to, code, purpose, ttl_minutes)
    ctx = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10, context=ctx)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with server:
            if settings.smtp_port != 465:
                server.starttls(context=ctx)
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        # 받는 주소·번호는 로그에 남기지 않는다(개인정보) — 어떤 종류의 실패인지만
        log.error("인증 메일 발송 실패: %s", type(e).__name__)
        raise MailError from e
